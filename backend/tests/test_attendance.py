"""Phase 3: GPS attendance, shift matching, late minutes and absence.

The pure functions are tested exhaustively because they decide pay-adjacent facts —
whether someone was late, how long they worked, whether they were absent.
"""

import datetime as dt
from decimal import Decimal

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from attendance.geo import haversine_meters, location_status, validate_coordinates
from attendance.models import (
    AppSettings,
    Attendance,
    AttendancePunch,
    AttendanceStatus,
    Holiday,
)
from attendance.services import AttendanceError, check_in, check_out, mark_absentees, set_leave
from attendance.shift_matching import late_minutes_for, match_punch_to_shift
from tests.factories import AdminFactory, EmployeeFactory

DHAKA = dt.timezone(dt.timedelta(hours=6))

# Office at a round location makes the distance arithmetic easy to reason about.
OFFICE_LAT = Decimal("23.780000")
OFFICE_LNG = Decimal("90.400000")


@pytest.fixture
def office(db):
    settings_obj = AppSettings.load()
    settings_obj.latitude = OFFICE_LAT
    settings_obj.longitude = OFFICE_LNG
    settings_obj.radius_meters = 200
    settings_obj.timezone = "Asia/Dhaka"
    settings_obj.weekend_days = [4, 5]
    settings_obj.save()
    return settings_obj


def utc(year, month, day, hour, minute=0):
    """A UTC instant expressed as Dhaka local wall-clock time, which is how the
    business thinks about it."""
    return dt.datetime(year, month, day, hour, minute, tzinfo=DHAKA).astimezone(dt.timezone.utc)


class TestHaversine:
    def test_zero_distance(self):
        assert haversine_meters(23.78, 90.4, 23.78, 90.4) == pytest.approx(0, abs=0.001)

    def test_one_degree_of_latitude(self):
        # One degree of latitude is ~111.2 km anywhere on Earth.
        distance = haversine_meters(0, 0, 1, 0)
        assert distance == pytest.approx(111_195, rel=0.001)

    def test_symmetric(self):
        a = haversine_meters(23.78, 90.4, 23.79, 90.41)
        b = haversine_meters(23.79, 90.41, 23.78, 90.4)
        assert a == pytest.approx(b)

    def test_small_office_scale_distance(self):
        # ~0.001 degree of latitude is about 111 m.
        distance = haversine_meters(23.780, 90.400, 23.781, 90.400)
        assert 110 < distance < 113

    def test_antipodal_does_not_blow_up(self):
        distance = haversine_meters(0, 0, 0, 180)
        assert distance == pytest.approx(20_015_000, rel=0.001)

    @pytest.mark.parametrize(
        "lat,lng",
        [(91, 0), (-91, 0), (0, 181), (0, -181)],
    )
    def test_impossible_coordinates_rejected(self, lat, lng):
        with pytest.raises(ValueError):
            validate_coordinates(lat, lng)

    def test_location_status_boundary_is_inclusive(self):
        assert location_status(200.0, 200) == "INSIDE"
        assert location_status(200.1, 200) == "OUTSIDE"


class FakeShift:
    def __init__(self, id, sequence, start_time):
        self.id = id
        self.sequence = sequence
        self.start_time = start_time


class TestShiftMatching:
    def test_single_shift_always_matches(self):
        shifts = [FakeShift(1, 1, dt.time(9, 0))]
        assert match_punch_to_shift(dt.time(9, 17), shifts).id == 1
        assert match_punch_to_shift(dt.time(6, 0), shifts).id == 1
        assert match_punch_to_shift(dt.time(22, 0), shifts).id == 1

    def test_split_shift_picks_the_nearest_start(self):
        shifts = [FakeShift(1, 1, dt.time(9, 0)), FakeShift(2, 2, dt.time(14, 0))]
        assert match_punch_to_shift(dt.time(9, 5), shifts).id == 1
        assert match_punch_to_shift(dt.time(14, 5), shifts).id == 2
        # Midday: 11:30 is 150 min from 09:00 and 150 min from 14:00 — a tie.
        assert match_punch_to_shift(dt.time(11, 30), shifts).id == 1

    def test_already_matched_shift_is_not_reused(self):
        shifts = [FakeShift(1, 1, dt.time(9, 0)), FakeShift(2, 2, dt.time(14, 0))]
        # Second punch at 09:30 cannot take shift 1 again, so it takes shift 2.
        assert match_punch_to_shift(dt.time(9, 30), shifts, already_matched_ids=[1]).id == 2

    def test_returns_none_when_all_shifts_are_used(self):
        shifts = [FakeShift(1, 1, dt.time(9, 0)), FakeShift(2, 2, dt.time(14, 0))]
        assert match_punch_to_shift(dt.time(16, 0), shifts, already_matched_ids=[1, 2]) is None

    def test_employee_who_missed_the_morning_matches_the_afternoon(self):
        shifts = [FakeShift(1, 1, dt.time(9, 0)), FakeShift(2, 2, dt.time(14, 0))]
        assert match_punch_to_shift(dt.time(14, 3), shifts).id == 2


class TestLateMinutes:
    def test_on_time_is_zero(self):
        assert late_minutes_for(dt.time(9, 0), dt.time(9, 0)) == 0

    def test_late_is_the_difference(self):
        # §8's worked example.
        assert late_minutes_for(dt.time(9, 17), dt.time(9, 0)) == 17

    def test_early_arrival_is_never_negative(self):
        assert late_minutes_for(dt.time(8, 30), dt.time(9, 0)) == 0

    def test_no_schedule_means_no_late_minutes(self):
        assert late_minutes_for(dt.time(9, 17), None) == 0


@pytest.mark.django_db
class TestCheckInCheckOut:
    def test_check_in_records_position_and_distance(self, office):
        employee = EmployeeFactory()
        punch = check_in(
            employee,
            latitude=23.780500,
            longitude=90.400000,
            accuracy_m=15,
            now=utc(2026, 8, 19, 9, 8),
        )
        assert punch.check_in_distance_m == pytest.approx(55.6, abs=2)
        assert punch.check_in_location_status == "INSIDE"
        assert punch.check_in_accuracy_m == 15
        assert punch.sequence == 1

    def test_outside_radius_is_flagged_not_blocked(self, office):
        """D2: the shipped default never rejects on distance."""
        employee = EmployeeFactory()
        punch = check_in(
            employee, latitude=23.800000, longitude=90.400000, now=utc(2026, 8, 19, 9, 0)
        )
        assert punch.check_in_location_status == "OUTSIDE"
        assert punch.check_in_distance_m > 200
        assert Attendance.objects.filter(employee=employee).exists()

    def test_an_office_can_require_check_in_inside_the_radius(self, office):
        """§5: the company decides. Turning it on refuses the punch outright."""
        office.require_check_in_inside_radius = True
        office.save()
        employee = EmployeeFactory()

        with pytest.raises(AttendanceError) as excinfo:
            check_in(employee, latitude=23.800000, longitude=90.400000, now=utc(2026, 8, 19, 9, 0))

        # The message has to be actionable: someone in the lobby on a bad GPS fix needs
        # to know how far off they read and what the limit is.
        assert "200 m" in str(excinfo.value)
        assert "away" in str(excinfo.value)

    def test_a_refused_check_in_writes_nothing(self, office):
        """A blocked attempt must not leave a half-open punch or an empty day behind."""
        office.require_check_in_inside_radius = True
        office.save()
        employee = EmployeeFactory()

        with pytest.raises(AttendanceError):
            check_in(employee, latitude=23.800000, longitude=90.400000, now=utc(2026, 8, 19, 9, 0))

        assert not AttendancePunch.objects.filter(attendance__employee=employee).exists()

    def test_inside_the_radius_still_works_when_the_rule_is_on(self, office):
        office.require_check_in_inside_radius = True
        office.save()
        employee = EmployeeFactory()

        punch = check_in(
            employee, latitude=23.780500, longitude=90.400000, now=utc(2026, 8, 19, 9, 0)
        )
        assert punch.check_in_location_status == "INSIDE"

    def test_the_rule_never_blocks_check_out(self, office):
        """Someone who checked in at their desk and left must still be able to close
        the punch, or they stay checked in for ever."""
        office.require_check_in_inside_radius = True
        office.save()
        employee = EmployeeFactory()
        check_in(employee, latitude=23.780500, longitude=90.400000, now=utc(2026, 8, 19, 9, 0))

        punch = check_out(
            employee, latitude=23.800000, longitude=90.400000, now=utc(2026, 8, 19, 18, 0)
        )
        assert punch.check_out_location_status == "OUTSIDE"
        assert punch.check_out_at is not None

    def test_late_minutes_calculated_against_the_shift(self, office):
        employee = EmployeeFactory()
        check_in(employee, latitude=23.78, longitude=90.4, now=utc(2026, 8, 19, 9, 17))

        attendance = Attendance.objects.get(employee=employee)
        assert attendance.late_minutes == 17
        assert attendance.status == AttendanceStatus.LATE

    def test_on_time_check_in_is_present(self, office):
        employee = EmployeeFactory()
        check_in(employee, latitude=23.78, longitude=90.4, now=utc(2026, 8, 19, 8, 58))

        attendance = Attendance.objects.get(employee=employee)
        assert attendance.late_minutes == 0
        assert attendance.status == AttendanceStatus.PRESENT

    def test_scheduled_start_is_snapshotted(self, office):
        """Changing the schedule later must not rewrite history."""
        employee = EmployeeFactory()
        check_in(employee, latitude=23.78, longitude=90.4, now=utc(2026, 8, 19, 9, 17))

        shift = employee.shifts.first()
        shift.start_time = dt.time(10, 0)
        shift.save()

        punch = Attendance.objects.get(employee=employee).punches.first()
        assert punch.scheduled_start == dt.time(9, 0)
        assert punch.late_minutes == 17

    def test_double_check_in_is_rejected(self, office):
        employee = EmployeeFactory()
        check_in(employee, latitude=23.78, longitude=90.4, now=utc(2026, 8, 19, 9, 0))
        with pytest.raises(AttendanceError, match="already checked in"):
            check_in(employee, latitude=23.78, longitude=90.4, now=utc(2026, 8, 19, 9, 5))

    def test_check_out_without_check_in_is_rejected(self, office):
        employee = EmployeeFactory()
        with pytest.raises(AttendanceError, match="not checked in"):
            check_out(employee, latitude=23.78, longitude=90.4, now=utc(2026, 8, 19, 18, 0))

    def test_full_day_records_duration(self, office):
        employee = EmployeeFactory()
        check_in(employee, latitude=23.78, longitude=90.4, now=utc(2026, 8, 19, 9, 8))
        check_out(employee, latitude=23.78, longitude=90.4, now=utc(2026, 8, 19, 18, 4))

        attendance = Attendance.objects.get(employee=employee)
        # §7's worked example: 09:08 to 18:04 is 8h 56m.
        assert attendance.worked_seconds == 8 * 3600 + 56 * 60
        assert attendance.last_check_out_at is not None

    def test_inactive_employee_cannot_check_in(self, office):
        employee = EmployeeFactory(status="INACTIVE")
        with pytest.raises(AttendanceError, match="not active"):
            check_in(employee, latitude=23.78, longitude=90.4, now=utc(2026, 8, 19, 9, 0))

    def test_impossible_coordinates_rejected(self, office):
        employee = EmployeeFactory()
        with pytest.raises(AttendanceError):
            check_in(employee, latitude=999, longitude=90.4, now=utc(2026, 8, 19, 9, 0))

    def test_late_night_check_in_files_against_local_date(self, office):
        """23:30 UTC is already the next day in Dhaka — the date must follow local time."""
        employee = EmployeeFactory()
        instant = dt.datetime(2026, 8, 18, 23, 30, tzinfo=dt.timezone.utc)
        check_in(employee, latitude=23.78, longitude=90.4, now=instant)

        attendance = Attendance.objects.get(employee=employee)
        assert attendance.date == dt.date(2026, 8, 19)

    def test_check_out_after_midnight_closes_yesterdays_punch(self, office):
        employee = EmployeeFactory()
        check_in(employee, latitude=23.78, longitude=90.4, now=utc(2026, 8, 19, 23, 50))
        check_out(employee, latitude=23.78, longitude=90.4, now=utc(2026, 8, 20, 0, 10))

        assert Attendance.objects.filter(employee=employee).count() == 1
        attendance = Attendance.objects.get(employee=employee)
        assert attendance.date == dt.date(2026, 8, 19)
        assert attendance.worked_seconds == 20 * 60


@pytest.mark.django_db
class TestSplitShiftAttendance:
    @pytest.fixture
    def split_employee(self, office):
        employee = EmployeeFactory(
            shifts=[(dt.time(9, 0), dt.time(13, 0)), (dt.time(14, 0), dt.time(18, 0))]
        )
        return employee

    def test_two_punches_match_two_shifts(self, split_employee):
        check_in(split_employee, latitude=23.78, longitude=90.4, now=utc(2026, 8, 19, 9, 5))
        check_out(split_employee, latitude=23.78, longitude=90.4, now=utc(2026, 8, 19, 13, 0))
        check_in(split_employee, latitude=23.78, longitude=90.4, now=utc(2026, 8, 19, 14, 10))
        check_out(split_employee, latitude=23.78, longitude=90.4, now=utc(2026, 8, 19, 18, 0))

        attendance = Attendance.objects.get(employee=split_employee)
        punches = list(attendance.punches.order_by("sequence"))
        assert len(punches) == 2
        assert punches[0].matched_shift.sequence == 1
        assert punches[1].matched_shift.sequence == 2
        # 5 minutes late in the morning, 10 in the afternoon.
        assert attendance.late_minutes == 15

    def test_worked_time_excludes_the_gap_between_shifts(self, split_employee):
        check_in(split_employee, latitude=23.78, longitude=90.4, now=utc(2026, 8, 19, 9, 0))
        check_out(split_employee, latitude=23.78, longitude=90.4, now=utc(2026, 8, 19, 13, 0))
        check_in(split_employee, latitude=23.78, longitude=90.4, now=utc(2026, 8, 19, 14, 0))
        check_out(split_employee, latitude=23.78, longitude=90.4, now=utc(2026, 8, 19, 18, 0))

        attendance = Attendance.objects.get(employee=split_employee)
        # 8 hours worked, not the 9 hours that last-minus-first would report.
        assert attendance.worked_seconds == 8 * 3600
        assert (
            attendance.last_check_out_at - attendance.first_check_in_at
        ).total_seconds() == 9 * 3600

    def test_surplus_punch_is_stored_unmatched_and_flagged(self, split_employee):
        """Storing beats rejecting: the afternoon still gets recorded, and an admin sees it."""
        for hour in (9, 14, 16):
            check_in(split_employee, latitude=23.78, longitude=90.4, now=utc(2026, 8, 19, hour, 0))
            check_out(
                split_employee, latitude=23.78, longitude=90.4, now=utc(2026, 8, 19, hour + 1, 0)
            )

        attendance = Attendance.objects.get(employee=split_employee)
        punches = list(attendance.punches.order_by("sequence"))
        assert len(punches) == 3
        assert punches[2].matched_shift is None
        assert punches[2].late_minutes == 0  # no schedule to be late against
        assert attendance.needs_review is True

    def test_missing_the_morning_matches_the_afternoon_shift(self, split_employee):
        check_in(split_employee, latitude=23.78, longitude=90.4, now=utc(2026, 8, 19, 14, 3))

        punch = Attendance.objects.get(employee=split_employee).punches.first()
        assert punch.matched_shift.sequence == 2
        assert punch.late_minutes == 3


@pytest.mark.django_db
class TestAbsenteeMarking:
    def test_marks_active_employees_absent_on_a_working_day(self, office):
        EmployeeFactory()
        EmployeeFactory()
        result = mark_absentees(dt.date(2026, 8, 19))  # Wednesday

        assert result["created"] == 2
        assert Attendance.objects.filter(status=AttendanceStatus.ABSENT).count() == 2

    def test_skips_the_configured_weekend(self, office):
        EmployeeFactory()
        friday = mark_absentees(dt.date(2026, 8, 21))
        assert friday["skipped"] == "not a working day"
        assert Attendance.objects.count() == 0

    def test_weekend_setting_actually_changes_the_outcome(self, office):
        """D4 end to end: the same date flips with the setting."""
        EmployeeFactory()
        sunday = dt.date(2026, 8, 23)

        assert mark_absentees(sunday)["created"] == 1  # Fri/Sat weekend: Sunday works

        Attendance.objects.all().delete()
        office.weekend_days = [5, 6]
        office.save()

        assert mark_absentees(sunday)["skipped"] == "not a working day"

    def test_skips_holidays(self, office):
        EmployeeFactory()
        Holiday.objects.create(date=dt.date(2026, 8, 19), name="Test Holiday")
        assert mark_absentees(dt.date(2026, 8, 19))["skipped"] == "not a working day"

    def test_does_not_overwrite_an_existing_record(self, office):
        employee = EmployeeFactory()
        check_in(employee, latitude=23.78, longitude=90.4, now=utc(2026, 8, 19, 9, 0))

        mark_absentees(dt.date(2026, 8, 19))
        attendance = Attendance.objects.get(employee=employee)
        assert attendance.status == AttendanceStatus.PRESENT

    def test_ignores_inactive_employees(self, office):
        EmployeeFactory(status="INACTIVE")
        assert mark_absentees(dt.date(2026, 8, 19))["created"] == 0

    def test_ignores_employees_who_had_not_joined_yet(self, office):
        EmployeeFactory(joining_date=dt.date(2026, 9, 1))
        assert mark_absentees(dt.date(2026, 8, 19))["created"] == 0

    def test_dry_run_writes_nothing(self, office):
        EmployeeFactory()
        result = mark_absentees(dt.date(2026, 8, 19), dry_run=True)
        assert result["created"] == 1
        assert Attendance.objects.count() == 0


@pytest.mark.django_db
class TestLeaveMarking:
    def test_full_day_leave_consumes_a_day(self, office):
        employee = EmployeeFactory(leave_total=Decimal("12.0"))
        attendance = set_leave(employee, dt.date(2026, 8, 19), Decimal("1.0"))

        employee.refresh_from_db()
        assert attendance.status == AttendanceStatus.LEAVE
        assert employee.leave_used == Decimal("1.0")
        assert employee.leave_remaining == Decimal("11.0")

    def test_half_day_is_blocked_while_disabled(self, office):
        employee = EmployeeFactory()
        with pytest.raises(AttendanceError, match="disabled"):
            set_leave(employee, dt.date(2026, 8, 19), Decimal("0.5"))

    def test_half_day_leave_plus_worked_afternoon(self, office):
        """D6's whole reason for a separate leave_fraction column."""
        office.allow_half_day_leave = True
        office.save()

        employee = EmployeeFactory(leave_total=Decimal("12.0"))
        set_leave(employee, dt.date(2026, 8, 19), Decimal("0.5"))
        check_in(employee, latitude=23.78, longitude=90.4, now=utc(2026, 8, 19, 14, 0))

        attendance = Attendance.objects.get(employee=employee)
        employee.refresh_from_db()
        assert attendance.leave_fraction == Decimal("0.5")
        # Still a worked day, with the half-day recorded alongside it.
        assert attendance.status in (AttendanceStatus.PRESENT, AttendanceStatus.LATE)
        assert employee.leave_used == Decimal("0.5")

    def test_cannot_take_more_leave_than_remaining(self, office):
        employee = EmployeeFactory(leave_total=Decimal("0.0"))
        with pytest.raises(AttendanceError, match="enough leave"):
            set_leave(employee, dt.date(2026, 8, 19), Decimal("1.0"))

    def test_leave_creates_an_adjustment_trail(self, office):
        employee = EmployeeFactory(leave_total=Decimal("12.0"))
        set_leave(employee, dt.date(2026, 8, 19), Decimal("1.0"))
        assert employee.leave_adjustments.filter(target="USED").count() == 1


@pytest.mark.django_db
class TestAttendanceApi:
    def test_employee_checks_in_and_out_through_the_api(self, office):
        employee = EmployeeFactory()
        client = APIClient()
        client.force_authenticate(user=employee.user)

        response = client.post(
            "/api/attendance/check-in/",
            {"latitude": 23.7805, "longitude": 90.4, "accuracy_m": 12},
            format="json",
        )
        assert response.status_code == 201, response.json()
        assert response.json()["punches"][0]["check_in_location_status"] == "INSIDE"

        response = client.post(
            "/api/attendance/check-out/",
            {"latitude": 23.7805, "longitude": 90.4},
            format="json",
        )
        assert response.status_code == 200
        assert response.json()["last_check_out_at"] is not None

    def test_today_endpoint_drives_the_button_state(self, office):
        employee = EmployeeFactory()
        client = APIClient()
        client.force_authenticate(user=employee.user)

        assert client.get("/api/attendance/today/").json()["checked_in"] is False

        client.post(
            "/api/attendance/check-in/", {"latitude": 23.78, "longitude": 90.4}, format="json"
        )
        body = client.get("/api/attendance/today/").json()
        assert body["checked_in"] is True
        assert body["office"]["radius_meters"] == 200

    def test_employee_sees_only_their_own_history(self, office):
        mine = EmployeeFactory()
        theirs = EmployeeFactory()
        check_in(theirs, latitude=23.78, longitude=90.4, now=utc(2026, 8, 19, 9, 0))
        check_in(mine, latitude=23.78, longitude=90.4, now=utc(2026, 8, 19, 9, 0))

        client = APIClient()
        client.force_authenticate(user=mine.user)
        results = client.get("/api/attendance/my/").json()

        assert len(results) == 1
        assert results[0]["employee"] == mine.id

    def test_employee_cannot_reach_the_admin_attendance_list(self, office):
        employee = EmployeeFactory()
        client = APIClient()
        client.force_authenticate(user=employee.user)
        assert client.get("/api/attendance/").status_code == 403

    def test_employee_cannot_mark_leave(self, office):
        employee = EmployeeFactory()
        client = APIClient()
        client.force_authenticate(user=employee.user)
        response = client.post(
            "/api/attendance/mark-leave/",
            {"employee": employee.id, "date": "2026-08-19", "fraction": "1.0"},
            format="json",
        )
        assert response.status_code == 403

    def test_admin_corrects_a_punch_and_it_is_audited(self, office):
        from core.models import AuditLog

        employee = EmployeeFactory()
        check_in(employee, latitude=23.78, longitude=90.4, now=utc(2026, 8, 19, 9, 30))
        check_out(employee, latitude=23.78, longitude=90.4, now=utc(2026, 8, 19, 18, 0))
        attendance = Attendance.objects.get(employee=employee)
        punch = attendance.punches.first()
        assert attendance.late_minutes == 30

        client = APIClient()
        client.force_authenticate(user=AdminFactory())
        response = client.patch(
            f"/api/attendance/{attendance.id}/punches/{punch.id}/",
            {"check_in_at": utc(2026, 8, 19, 9, 0).isoformat(), "note": "Gate queue"},
            format="json",
        )
        assert response.status_code == 200, response.json()

        attendance.refresh_from_db()
        assert attendance.late_minutes == 0
        assert attendance.status == AttendanceStatus.PRESENT
        assert attendance.is_manually_adjusted is True
        assert AuditLog.objects.filter(action=AuditLog.Action.ATTENDANCE_CORRECTED).exists()

    def test_correction_rejects_checkout_before_checkin(self, office):
        employee = EmployeeFactory()
        check_in(employee, latitude=23.78, longitude=90.4, now=utc(2026, 8, 19, 9, 0))
        check_out(employee, latitude=23.78, longitude=90.4, now=utc(2026, 8, 19, 18, 0))
        attendance = Attendance.objects.get(employee=employee)
        punch = attendance.punches.first()

        client = APIClient()
        client.force_authenticate(user=AdminFactory())
        response = client.patch(
            f"/api/attendance/{attendance.id}/punches/{punch.id}/",
            {"check_out_at": utc(2026, 8, 19, 8, 0).isoformat()},
            format="json",
        )
        assert response.status_code == 400

    def test_admin_can_filter_by_outside_location(self, office):
        inside = EmployeeFactory()
        outside = EmployeeFactory()
        check_in(inside, latitude=23.78, longitude=90.4, now=utc(2026, 8, 19, 9, 0))
        check_in(outside, latitude=23.80, longitude=90.4, now=utc(2026, 8, 19, 9, 0))

        client = APIClient()
        client.force_authenticate(user=AdminFactory())
        results = client.get("/api/attendance/?location=OUTSIDE").json()["results"]
        assert len(results) == 1
        assert results[0]["employee"] == outside.id


@pytest.mark.django_db
class TestManagementCommand:
    def test_refuses_to_process_today(self, office):
        from django.core.management import call_command
        from django.core.management.base import CommandError

        today = timezone.now().astimezone(DHAKA).date()
        with pytest.raises(CommandError, match="Refusing"):
            call_command("mark_absentees", f"--date={today.isoformat()}")

    def test_marks_a_past_working_day(self, office):
        from django.core.management import call_command

        EmployeeFactory()
        call_command("mark_absentees", "--date=2026-08-12")  # a past Wednesday
        assert Attendance.objects.filter(status=AttendanceStatus.ABSENT).count() == 1
