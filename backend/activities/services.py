"""Ingestion of agent-submitted sessions (§19).

The contract with the agent is: **replaying a batch must be harmless**. The agent marks
a session synced only after a 2xx, so any dropped response means it will send that batch
again — which is the correct behaviour on its side and only works because ingestion here
is an upsert keyed on `(computer, client_event_id)`.

First write wins. Agents only ever send closed sessions, so a second copy carries no new
information, and preferring the later copy would let a retry with a drifted clock quietly
rewrite history.
"""

from __future__ import annotations

import datetime as dt

from django.db import IntegrityError, transaction
from django.utils import timezone

from .models import Activity
from .serializers import ActivitySessionSerializer

# A single session longer than this is not a fact about someone's day, it is a clock
# that stepped or a builder that failed to close. The agent caps its own sessions at 15
# minutes, so anything approaching an hour is already wrong; the server clamps rather
# than rejects so the time is not simply lost.
MAX_SESSION_SECONDS = 3600

# Allowance for ordinary clock skew between a PC and the server. Beyond this, a
# timestamp in the future is not skew, it is wrong.
FUTURE_SKEW = dt.timedelta(minutes=5)


def _clamp(session: dict, now) -> tuple[dict, list[str]]:
    """Bring one session's times into a range the server is willing to believe."""
    notes = []
    start = session["start_time"]
    end = session["end_time"]

    horizon = now + FUTURE_SKEW
    if start > horizon:
        # A PC whose clock is a day fast would otherwise file tomorrow's activity, where
        # no report would ever look for it.
        notes.append("start_in_future")
        shift = start - now
        start = now
        end = max(now, end - shift)
    if end > horizon:
        notes.append("end_in_future")
        end = now

    if end < start:
        end = start

    duration = int((end - start).total_seconds())
    if duration > MAX_SESSION_SECONDS:
        notes.append("duration_clamped")
        duration = MAX_SESSION_SECONDS
        end = start + dt.timedelta(seconds=duration)

    session["start_time"] = start
    session["end_time"] = end
    session["duration_seconds"] = duration
    return session, notes


def ingest_sessions(computer, raw_sessions, now=None) -> dict:
    """Validate and store a batch. Never raises for one bad row.

    A single malformed session must not cost the agent the other 99 in the batch: it
    would retry the whole batch forever and never drain its queue. Bad rows come back
    named in `rejected` so they can be dropped locally.
    """
    now = now or timezone.now()
    accepted = duplicates = clamped = 0
    rejected = []

    for index, raw in enumerate(raw_sessions):
        serializer = ActivitySessionSerializer(data=raw)
        if not serializer.is_valid():
            rejected.append(
                {
                    "index": index,
                    "client_event_id": str(raw.get("client_event_id", "")),
                    "errors": serializer.errors,
                }
            )
            continue

        session, notes = _clamp(dict(serializer.validated_data), now)
        if notes:
            clamped += 1

        try:
            with transaction.atomic():
                Activity.objects.create(
                    employee=computer.employee,
                    computer=computer,
                    activity_type=session["activity_type"],
                    application_name=session.get("application_name", ""),
                    executable_name=session.get("executable_name", ""),
                    website_domain=session.get("website_domain", ""),
                    start_time=session["start_time"],
                    end_time=session["end_time"],
                    duration_seconds=session["duration_seconds"],
                    client_event_id=session["client_event_id"],
                )
        except IntegrityError:
            # The unique constraint on (computer, client_event_id) is the whole
            # anti-duplicate mechanism §19 asks for. Hitting it means the agent is
            # retrying a batch whose response it never saw — expected, not an error.
            duplicates += 1
            continue

        accepted += 1

    return {
        "accepted": accepted,
        "duplicates": duplicates,
        "clamped": clamped,
        "rejected": rejected,
    }
