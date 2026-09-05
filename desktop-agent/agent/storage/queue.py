"""The offline buffer (§19, §34 Local Storage).

Every closed session is written here *before* anything tries to upload it, and the
`synced` flag is set only after the server answers 2xx. That ordering is the whole
design: the failure mode it rules out is "uploaded but lost", and the failure mode it
accepts — "uploaded twice" — is harmless because the server upserts on
`client_event_id`.

SQLite with WAL and `synchronous=FULL` because the thing this file has to survive is a
power cut, which is exactly the event that also loses the in-memory session. Writes are
a handful per minute, so the durability costs nothing that matters.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
from pathlib import Path

from ..config import data_dir

log = logging.getLogger(__name__)

QUEUE_FILENAME = "queue.sqlite3"

SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    client_event_id TEXT NOT NULL UNIQUE,
    payload TEXT NOT NULL,
    created_at TEXT NOT NULL,
    synced INTEGER NOT NULL DEFAULT 0,
    synced_at TEXT,
    attempts INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS sessions_pending ON sessions (synced, id);
"""

# An agent offline for a month must not fill the disk. At roughly 300 sessions a day
# this is about three months of buffer, and the drop is logged rather than silent.
MAX_PENDING_ROWS = 50_000


class SessionQueue:
    """Durable FIFO of closed sessions awaiting upload."""

    def __init__(self, path: Path | str | None = None):
        self.path = Path(path) if path else (data_dir() / QUEUE_FILENAME)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # The sampler thread writes and the sync thread reads, so the connection is
        # shared across threads with its own lock rather than one connection per thread
        # fighting over the same file.
        self._lock = threading.Lock()
        self._connection = sqlite3.connect(str(self.path), check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        with self._connection:
            self._connection.execute("PRAGMA journal_mode=WAL")
            self._connection.execute("PRAGMA synchronous=FULL")
            self._connection.executescript(SCHEMA)

    def close(self):
        with self._lock:
            self._connection.close()

    # --- Writing -----------------------------------------------------------

    def enqueue(self, session: dict) -> bool:
        """Store one closed session. Returns False if it was already stored.

        Re-enqueuing the same `client_event_id` is ignored rather than treated as an
        error: the builder assigns the id at creation, so a duplicate means the same
        session arrived twice, which is precisely what the id exists to make harmless.
        """
        with self._lock, self._connection:
            if self._pending_count() >= MAX_PENDING_ROWS:
                log.error(
                    "Offline queue is full (%s pending); dropping session %s",
                    MAX_PENDING_ROWS,
                    session.get("client_event_id"),
                )
                return False
            try:
                self._connection.execute(
                    "INSERT INTO sessions (client_event_id, payload, created_at) VALUES (?, ?, ?)",
                    (
                        session["client_event_id"],
                        json.dumps(session),
                        session.get("end_time", ""),
                    ),
                )
            except sqlite3.IntegrityError:
                return False
        return True

    def enqueue_many(self, sessions) -> int:
        return sum(1 for session in sessions if self.enqueue(session))

    # --- Reading -----------------------------------------------------------

    def pending(self, limit: int = 100) -> list[dict]:
        """Oldest-first batch of sessions still awaiting a 2xx."""
        with self._lock:
            rows = self._connection.execute(
                "SELECT id, payload FROM sessions WHERE synced = 0 ORDER BY id LIMIT ?",
                (limit,),
            ).fetchall()
        return [{"id": row["id"], **json.loads(row["payload"])} for row in rows]

    def pending_count(self) -> int:
        with self._lock:
            return self._pending_count()

    def _pending_count(self) -> int:
        return self._connection.execute(
            "SELECT COUNT(*) FROM sessions WHERE synced = 0"
        ).fetchone()[0]

    # --- Bookkeeping -------------------------------------------------------

    def mark_synced(self, row_ids) -> int:
        row_ids = list(row_ids)
        if not row_ids:
            return 0
        placeholders = ",".join("?" * len(row_ids))
        with self._lock, self._connection:
            cursor = self._connection.execute(
                f"UPDATE sessions SET synced = 1, synced_at = datetime('now') "  # noqa: S608
                f"WHERE id IN ({placeholders})",
                row_ids,
            )
        return cursor.rowcount

    def record_attempt(self, row_ids) -> int:
        """Count a failed upload against a batch, so a poison row is visible."""
        row_ids = list(row_ids)
        if not row_ids:
            return 0
        placeholders = ",".join("?" * len(row_ids))
        with self._lock, self._connection:
            cursor = self._connection.execute(
                f"UPDATE sessions SET attempts = attempts + 1 WHERE id IN ({placeholders})",  # noqa: S608
                row_ids,
            )
        return cursor.rowcount

    def discard(self, row_ids) -> int:
        """Drop rows the server refused as invalid.

        Without this a single malformed session would sit at the head of the queue
        forever, retried on every cycle and blocking everything behind it.
        """
        row_ids = list(row_ids)
        if not row_ids:
            return 0
        placeholders = ",".join("?" * len(row_ids))
        with self._lock, self._connection:
            cursor = self._connection.execute(
                f"DELETE FROM sessions WHERE id IN ({placeholders})", row_ids  # noqa: S608
            )
        return cursor.rowcount

    def purge_synced(self, keep_days: int = 1) -> int:
        """Delete rows the server has confirmed, after a short grace period.

        The grace period is for people, not for correctness: when someone asks why an
        afternoon looks wrong, the last day of uploads is still on the machine.
        """
        with self._lock, self._connection:
            cursor = self._connection.execute(
                "DELETE FROM sessions WHERE synced = 1 " "AND synced_at < datetime('now', ?)",
                (f"-{int(keep_days)} days",),
            )
        return cursor.rowcount

    def stats(self) -> dict:
        with self._lock:
            row = self._connection.execute(
                "SELECT COUNT(*) AS total, "
                "SUM(CASE WHEN synced = 0 THEN 1 ELSE 0 END) AS pending, "
                "MAX(attempts) AS max_attempts FROM sessions"
            ).fetchone()
        return {
            "total": row["total"] or 0,
            "pending": row["pending"] or 0,
            "max_attempts": row["max_attempts"] or 0,
        }
