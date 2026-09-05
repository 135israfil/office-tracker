"""Uploading the queue (§19, §34 Sync Service).

The loop is deliberately dull: take the oldest batch, post it, mark it synced only if
the server said 2xx, back off if it did not. Nothing clever, because the interesting
cases here are all failures — a dropped response, a proxy timeout, a laptop that was
asleep for a weekend — and cleverness in a retry path is how duplicate or lost data
happens.

Two behaviours are worth stating outright:

- **A dropped response means the batch is sent again.** That is safe by construction:
  ingestion upserts on `client_event_id`, so the server counts the second copy as a
  duplicate and stores nothing new.
- **A session the server calls invalid is dropped locally.** Otherwise one malformed row
  sits at the head of the queue forever, retried every cycle, blocking everything behind
  it — an outage caused by a single bad record.
"""

from __future__ import annotations

import logging

from ..api import AgentApiError, backoff_seconds

log = logging.getLogger(__name__)

# Big enough that a long outage drains quickly, small enough to retry cheaply and stay
# well inside the server's 500-row batch limit.
BATCH_SIZE = 100


class SyncService:
    def __init__(self, queue, client, batch_size: int = BATCH_SIZE):
        self.queue = queue
        self.client = client
        self.batch_size = batch_size
        self.consecutive_failures = 0
        self.last_error: str | None = None
        self.last_result: dict | None = None

    def sync_once(self) -> dict:
        """Upload one batch. Returns a summary; never raises for a network failure."""
        batch = self.queue.pending(self.batch_size)
        if not batch:
            self.consecutive_failures = 0
            return {"uploaded": 0, "pending": 0, "status": "empty"}

        row_ids = [row.pop("id") for row in batch]

        try:
            result = self.client.sync(batch)
        except AgentApiError as exc:
            self.consecutive_failures += 1
            self.last_error = str(exc)
            self.queue.record_attempt(row_ids)
            log.warning(
                "Sync of %s session(s) failed (%s in a row): %s",
                len(batch),
                self.consecutive_failures,
                exc,
            )
            return {"uploaded": 0, "pending": self.queue.pending_count(), "status": "failed"}

        # 2xx: everything in this batch is now the server's problem, including the rows
        # it counted as duplicates — those are already stored from an earlier attempt.
        self.queue.mark_synced(row_ids)
        self.consecutive_failures = 0
        self.last_error = None
        self.last_result = result

        rejected = result.get("rejected") or []
        if rejected:
            # Named individually by the server, so only the bad ones are discarded.
            rejected_ids = {str(item.get("client_event_id")) for item in rejected}
            discarded = [
                row_id
                for row_id, row in zip(row_ids, batch, strict=False)
                if str(row.get("client_event_id")) in rejected_ids
            ]
            self.queue.discard(discarded)
            log.error("Server rejected %s session(s); dropped locally: %s", len(rejected), rejected)

        return {
            "uploaded": result.get("accepted", 0),
            "duplicates": result.get("duplicates", 0),
            "rejected": len(rejected),
            "pending": self.queue.pending_count(),
            "status": "ok",
        }

    def drain(self, max_batches: int = 20) -> dict:
        """Upload until the queue is empty, a batch fails, or the cap is reached.

        The cap exists so a machine returning from a long outage cannot monopolise its
        own sync thread — it catches up over several cycles instead of one long one.
        """
        totals = {"uploaded": 0, "duplicates": 0, "rejected": 0, "batches": 0}
        for _ in range(max_batches):
            result = self.sync_once()
            totals["batches"] += 1
            totals["uploaded"] += result.get("uploaded", 0)
            totals["duplicates"] += result.get("duplicates", 0)
            totals["rejected"] += result.get("rejected", 0)
            if result["status"] != "ok":
                break
        totals["pending"] = self.queue.pending_count()
        return totals

    def next_delay(self, base_interval: int) -> int:
        """How long to wait before the next attempt."""
        if not self.consecutive_failures:
            return base_interval
        # Cap the exponent so a week-long outage does not compute an absurd delay before
        # the cap clamps it anyway.
        return max(base_interval, backoff_seconds(min(self.consecutive_failures - 1, 6)))
