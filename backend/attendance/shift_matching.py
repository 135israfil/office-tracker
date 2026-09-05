"""Punch-to-shift matching and late-minute calculation (§8, D7).

This is the one genuinely ambiguous piece of the attendance model: with split shifts an
employee can punch at times that do not map cleanly onto their schedule. Every rule and
every edge case is decided here, in pure functions, and nowhere else — so the behaviour
is testable and there is a single place to change it when reality disagrees.

Rules, in order:

1. A punch matches the *unmatched* shift whose start time is nearest to it.
2. Ties go to the earlier shift.
3. If every shift is already matched, the punch is stored **unmatched** rather than
   rejected or guessed at, and the day is flagged for admin review.
4. Late minutes are `max(0, punch_time - matched_shift.start_time)`. Arriving early is
   never negative late.
5. An unmatched punch contributes 0 late minutes: there is no schedule to be late
   against, and inventing one would corrupt the total.

For a single-shift employee this collapses to exactly §8's behaviour, so the common
case is unaffected by any of the split-shift machinery.
"""

from __future__ import annotations

import datetime as dt


def _minutes(value: dt.time) -> int:
    return value.hour * 60 + value.minute


def match_punch_to_shift(punch_time: dt.time, shifts, already_matched_ids=()):
    """Return the shift this punch belongs to, or None if every shift is taken.

    `shifts` is any iterable of objects with `id`, `sequence` and `start_time`.
    """
    already_matched = set(already_matched_ids or ())
    available = [shift for shift in shifts if shift.id not in already_matched]
    if not available:
        return None

    punch_minutes = _minutes(punch_time)
    # Sort by distance from the punch, then by sequence so ties resolve to the earlier
    # shift deterministically rather than depending on queryset ordering.
    return min(
        available,
        key=lambda shift: (abs(_minutes(shift.start_time) - punch_minutes), shift.sequence),
    )


def late_minutes_for(punch_time: dt.time, scheduled_start: dt.time | None) -> int:
    """Minutes late, floored at zero. Returns 0 when there is no schedule to compare to."""
    if scheduled_start is None:
        return 0
    return max(0, _minutes(punch_time) - _minutes(scheduled_start))


def summarise_day(punches):
    """Fold a day's punches into the values stored on the Attendance row.

    Worked time is the sum of *closed* punches, never last-out minus first-in: a two
    hour lunch gap between two shifts is not worked time, and treating it as such would
    overstate every split-shift employee's day.
    """
    first_in = None
    last_out = None
    worked_seconds = 0
    late_total = 0
    has_open_punch = False
    unmatched = 0

    for punch in punches:
        if punch.check_in_at is None:
            continue
        if first_in is None or punch.check_in_at < first_in:
            first_in = punch.check_in_at

        late_total += punch.late_minutes or 0
        if punch.matched_shift_id is None:
            unmatched += 1

        if punch.check_out_at is None:
            has_open_punch = True
            continue

        if last_out is None or punch.check_out_at > last_out:
            last_out = punch.check_out_at
        worked_seconds += int((punch.check_out_at - punch.check_in_at).total_seconds())

    return {
        "first_check_in_at": first_in,
        "last_check_out_at": last_out,
        "worked_seconds": worked_seconds,
        "late_minutes": late_total,
        "has_open_punch": has_open_punch,
        "unmatched_punches": unmatched,
    }
