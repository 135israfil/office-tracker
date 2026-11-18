"""Phase 7: dashboards, the activity page and data isolation (§20-§24, §30).

Two themes. The first is arithmetic that has to survive contact with reality — sessions
that cross midnight, sessions still open, parallel tracks that must never be summed.

The second is the exit criterion the plan names explicitly: **employee A cannot read
employee B's data through any endpoint**. That is tested per endpoint rather than once,
because "it is enforced in the base class" is exactly the assumption that leaks.
"""

import datetime as dt
from decimal import Decimal

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from activities.models import Activity, ActivityType
from activities.queries import build_timeline, minute_buckets, overlap_seconds, summarise
from attendance.models import AppSettings, Attendance, AttendanceStatus
from computers.models import ComputerStatus
from core.dashboards import attendance_counts, computer_counts, employee_roster
from tests.factories import AdminFactory, ComputerFactory, EmployeeFactory

DHAKA_OFFSET = dt.timedelta(hours=6)
DAY = dt.date(2026, 8, 18)


@pytest.fixture
def office(db):
    settings_obj = AppSettings.load()
    settings_obj.timezone = "Asia/Dhaka"
    settings_obj.save()
    return settings_obj


@pytest.fixture
def admin_client(db):
    admin = AdminFactory()
    client = APIClient()
    client.force_authenticate(user=admin)
    return client, admin


def local(hour, minute=0, day=DAY):
    """An office-local wall-clock time as a UTC instant."""
    return dt.datetime.combine(day, dt.time(hour, minute), tzinfo=dt.timezone(DHAKA_OFFSET))


def session(employee, computer, activity_type, start, end, **fields):
    return Activity.objects.create(
        employee=employee,
        computer=computer,
        activity_type=activity_type,
        start_time=start,
        end_time=end,
        duration_seconds=int((end - start).total_seconds()) if end else 0,
        **fields,
    )


class Fake:
    """A session-shaped object for the pure functions, with no database behind it."""

    def __init__(self, activity_type, start, end, **fields):
        self.activity_type = activity_type
        self.start_time = start
        self.end_time = end
        self.application_name = fields.get("application_name", "")
        self.website_domain = fields.get("website_domain", "")
        self.closed_by_server = fields.get("closed_by_server", False)


# --- Arithmetic -------------------------------------------------------------


class TestOverlap:
    def setup_method(self):
        self.start = dt.datetime(2026, 8, 18, 0, 0, tzinfo=dt.timezone.utc)
        self.end = self.start + dt.timedelta(days=1)

    def test_a_session_inside_the_window_counts_in_full(self):
        entry = Fake(
            "ACTIVE", self.start + dt.timedelta(hours=9), self.start + dt.timedelta(hours=10)
        )
        assert overlap_seconds(entry, self.start, self.end) == 3600

    def test_a_session_crossing_midnight_is_split_between_days(self):
        # 22:00 to 02:00: two hours belong to each date, not four to one.
        entry = Fake(
            "PC_ON",
            self.start + dt.timedelta(hours=22),
            self.start + dt.timedelta(hours=26),
        )
        assert overlap_seconds(entry, self.start, self.end) == 2 * 3600

        next_day_start = self.end
        next_day_end = next_day_start + dt.timedelta(days=1)
        assert overlap_seconds(entry, next_day_start, next_day_end) == 2 * 3600

    def test_an_open_session_counts_up_to_now(self):
        now = self.start + dt.timedelta(hours=11)
        entry = Fake("PC_ON", self.start + dt.timedelta(hours=9), None)
        assert overlap_seconds(entry, self.start, self.end, now=now) == 2 * 3600

    def test_an_open_session_from_a_past_day_stops_at_midnight(self):
        # Otherwise a session nobody ever closed would grow every time the page loads.
        now = self.start + dt.timedelta(days=5)
        entry = Fake("PC_ON", self.start + dt.timedelta(hours=23), None)
        assert overlap_seconds(entry, self.start, self.end, now=now) == 3600

    def test_a_session_outside_the_window_counts_for_nothing(self):
        entry = Fake("ACTIVE", self.end + dt.timedelta(hours=1), self.end + dt.timedelta(hours=2))
        assert overlap_seconds(entry, self.start, self.end) == 0


class TestSummarise:
    def setup_method(self):
        self.start = dt.datetime(2026, 8, 18, 0, 0, tzinfo=dt.timezone.utc)
        self.end = self.start + dt.timedelta(days=1)

    def hours(self, offset, length):
        return (
            self.start + dt.timedelta(hours=offset),
            self.start + dt.timedelta(hours=offset + length),
        )

    def test_totals_are_per_type_and_never_summed_across(self):
        pc_start, pc_end = self.hours(9, 9)
        active_start, active_end = self.hours(9, 7)
        idle_start, idle_end = self.hours(16, 2)
        app_start, app_end = self.hours(9, 4)

        result = summarise(
            [
                Fake(ActivityType.PC_ON, pc_start, pc_end),
                Fake(ActivityType.ACTIVE, active_start, active_end),
                Fake(ActivityType.IDLE, idle_start, idle_end),
                Fake(ActivityType.APPLICATION, app_start, app_end, application_name="VS Code"),
            ],
            self.start,
            self.end,
        )

        assert result["pc_on_seconds"] == 9 * 3600
        assert result["active_seconds"] == 7 * 3600
        assert result["idle_seconds"] == 2 * 3600
        # The application session overlaps the active one entirely; both are correct and
        # neither is added to the other.
        assert result["top_applications"] == [{"name": "VS Code", "seconds": 4 * 3600}]

    def test_applications_are_ranked_and_the_tail_is_bucketed(self):
        sessions = [
            Fake(ActivityType.APPLICATION, *self.hours(9 + index, 1), application_name=name)
            for index, name in enumerate(["A", "B", "C", "D", "E", "F", "G"])
        ]
        # Give A a clear lead so ranking is unambiguous.
        sessions.append(Fake(ActivityType.APPLICATION, *self.hours(17, 3), application_name="A"))

        result = summarise(sessions, self.start, self.end)

        assert result["top_applications"][0] == {"name": "A", "seconds": 4 * 3600}
        assert len(result["top_applications"]) == 5
        # The two that did not make the list are still counted, so the totals add up.
        assert result["other_application_seconds"] == 2 * 3600

    def test_websites_are_bucketed_by_domain(self):
        result = summarise(
            [
                Fake(ActivityType.WEBSITE, *self.hours(9, 1), website_domain="github.com"),
                Fake(ActivityType.WEBSITE, *self.hours(11, 2), website_domain="github.com"),
                Fake(ActivityType.WEBSITE, *self.hours(14, 1), website_domain="google.com"),
            ],
            self.start,
            self.end,
        )
        assert result["top_websites"] == [
            {"name": "github.com", "seconds": 3 * 3600},
            {"name": "google.com", "seconds": 3600},
        ]

    def test_an_empty_day_is_all_zeroes_not_an_error(self):
        result = summarise([], self.start, self.end)
        assert result["pc_on_seconds"] == 0
        assert result["top_applications"] == []


class TestMinuteBuckets:
    def setup_method(self):
        self.start = dt.datetime(2026, 8, 18, 0, 0, tzinfo=dt.timezone.utc)
        self.end = self.start + dt.timedelta(days=1)

    def at(self, hour, minute=0):
        return self.start + dt.timedelta(hours=hour, minutes=minute)

    def test_a_day_with_nothing_recorded_is_all_off(self):
        buckets = minute_buckets([], self.start, self.end)
        assert len(buckets) == 24 * 60
        assert set(buckets) == {"O"}

    def test_active_and_idle_paint_over_the_pc_on_baseline(self):
        buckets = minute_buckets(
            [
                Fake(ActivityType.PC_ON, self.at(9), self.at(18)),
                Fake(ActivityType.ACTIVE, self.at(9), self.at(12)),
                Fake(ActivityType.IDLE, self.at(12), self.at(13)),
            ],
            self.start,
            self.end,
        )
        # PC on but neither active nor idle (13:00-18:00) stays "O", same as off — the
        # UI only draws three states.
        assert buckets[9 * 60] == "A"
        assert buckets[11 * 60 + 59] == "A"
        assert buckets[12 * 60] == "I"
        assert buckets[12 * 60 + 59] == "I"
        assert buckets[13 * 60] == "O"
        assert buckets[8 * 60 + 59] == "O"

    def test_a_session_ending_on_a_minute_boundary_does_not_paint_the_next_minute(self):
        buckets = minute_buckets(
            [Fake(ActivityType.ACTIVE, self.at(9, 0), self.at(9, 1))], self.start, self.end
        )
        assert buckets[9 * 60] == "A"
        assert buckets[9 * 60 + 1] == "O"

    def test_an_open_session_counts_up_to_now(self):
        now = self.at(10, 30)
        buckets = minute_buckets(
            [Fake(ActivityType.ACTIVE, self.at(9), None)], self.start, self.end, now=now
        )
        assert buckets[10 * 60 + 29] == "A"
        assert buckets[10 * 60 + 31] == "O"


class TestTimeline:
    def setup_method(self):
        self.start = dt.datetime(2026, 8, 18, 0, 0, tzinfo=dt.timezone.utc)
        self.end = self.start + dt.timedelta(days=1)

    def at(self, hour, minute=0):
        return self.start + dt.timedelta(hours=hour, minutes=minute)

    def test_the_narrative_reads_in_order(self):
        result = build_timeline(
            [
                Fake(ActivityType.PC_ON, self.at(9, 2), self.at(18, 3)),
                Fake(
                    ActivityType.APPLICATION,
                    self.at(9, 5),
                    self.at(9, 42),
                    application_name="Chrome",
                ),
                Fake(
                    ActivityType.WEBSITE, self.at(9, 5), self.at(9, 42), website_domain="github.com"
                ),
                Fake(
                    ActivityType.APPLICATION,
                    self.at(9, 42),
                    self.at(10, 30),
                    application_name="VS Code",
                ),
                Fake(ActivityType.IDLE, self.at(10, 30), self.at(10, 38)),
            ],
            self.start,
            self.end,
        )

        labels = [(entry["label"], entry["detail"]) for entry in result["entries"]]
        assert labels == [
            ("PC started", ""),
            # §23's "09:05 - Chrome / github.com": the parallel tracks make this joinable.
            ("Chrome", "github.com"),
            ("VS Code", ""),
            ("Idle", ""),
            ("PC shutdown", ""),
        ]

    def test_an_inferred_shutdown_says_so(self):
        result = build_timeline(
            [Fake(ActivityType.PC_ON, self.at(9), self.at(18), closed_by_server=True)],
            self.start,
            self.end,
        )
        # "Stopped responding" and "was shut down" are different facts, and a timeline
        # that conflates them is lying about a power cut.
        assert result["entries"][-1]["label"] == "PC stopped responding"

    def test_a_session_still_open_has_no_end_entry(self):
        result = build_timeline(
            [Fake(ActivityType.PC_ON, self.at(9), None)],
            self.start,
            self.end,
            now=self.at(11),
        )
        assert [entry["label"] for entry in result["entries"]] == ["PC started"]

    def test_a_busy_day_is_capped_and_says_how_much_was_dropped(self):
        sessions = [
            Fake(
                ActivityType.APPLICATION,
                self.at(9) + dt.timedelta(minutes=index),
                self.at(9) + dt.timedelta(minutes=index + 1),
                application_name=f"App {index}",
            )
            for index in range(250)
        ]
        result = build_timeline(sessions, self.start, self.end)

        assert len(result["entries"]) == 200
        assert result["truncated"] == 50


# --- Dashboard counts -------------------------------------------------------


@pytest.mark.django_db
class TestDashboardCounts:
    def test_attendance_counts_separate_absent_from_not_yet_arrived(self, office):
        present = EmployeeFactory()
        late = EmployeeFactory()
        absent = EmployeeFactory()
        EmployeeFactory()  # no row at all: has not arrived yet

        Attendance.objects.create(employee=present, date=DAY, status=AttendanceStatus.PRESENT)
        Attendance.objects.create(employee=late, date=DAY, status=AttendanceStatus.LATE)
        Attendance.objects.create(employee=absent, date=DAY, status=AttendanceStatus.ABSENT)

        counts = attendance_counts(DAY, office)

        assert counts["employees"] == 4
        assert counts["present"] == 1
        assert counts["late"] == 1
        assert counts["absent"] == 1
        # At 10am, "no row" means "not here yet", not "absent". Absence is derived
        # nightly (A4), and showing it early would be wrong for most of the day.
        assert counts["not_recorded"] == 1

    def test_pc_counts_treat_online_as_active_plus_idle(self, db):
        ComputerFactory(status=ComputerStatus.ONLINE)
        ComputerFactory(status=ComputerStatus.ONLINE)
        ComputerFactory(status=ComputerStatus.IDLE)
        ComputerFactory(status=ComputerStatus.OFFLINE)
        ComputerFactory(status=ComputerStatus.DISABLED)

        counts = computer_counts()

        assert counts["active"] == 2
        assert counts["idle"] == 1
        assert counts["online"] == 3  # §20's example breaks 39 online into 34 + 5
        assert counts["offline"] == 1
        assert counts["disabled"] == 1
        assert counts["total"] == 5

    def test_roster_joins_attendance_pc_status_and_activity(self, office):
        employee = EmployeeFactory(name="Rahim Ahmed", department="Development")
        computer = ComputerFactory(employee=employee, status=ComputerStatus.ONLINE)
        Attendance.objects.create(
            employee=employee,
            date=DAY,
            status=AttendanceStatus.LATE,
            first_check_in_at=local(9, 12),
            last_check_out_at=local(18, 3),
            late_minutes=12,
        )
        session(employee, computer, ActivityType.ACTIVE, local(9, 12), local(16, 12))
        session(employee, computer, ActivityType.IDLE, local(16, 12), local(17, 12))

        row = employee_roster(DAY, settings_obj=office)[0]

        assert row["name"] == "Rahim Ahmed"
        assert row["attendance_status"] == AttendanceStatus.LATE
        assert row["late_minutes"] == 12
        assert row["pc_status"] == ComputerStatus.ONLINE
        assert row["active_seconds"] == 7 * 3600
        assert row["idle_seconds"] == 3600

    def test_roster_reports_the_liveliest_of_several_machines(self, office):
        employee = EmployeeFactory()
        ComputerFactory(employee=employee, status=ComputerStatus.OFFLINE)
        ComputerFactory(employee=employee, status=ComputerStatus.ONLINE)

        row = employee_roster(DAY, settings_obj=office)[0]
        # Someone with a desktop and a laptop is at work if either is answering.
        assert row["pc_status"] == ComputerStatus.ONLINE
        assert row["computer_count"] == 2

    def test_roster_is_a_fixed_number_of_queries(self, office, django_assert_num_queries):
        for _ in range(6):
            employee = EmployeeFactory()
            ComputerFactory(employee=employee)

        # Employees, attendance, computers, activity. A per-employee loop would be 4xN
        # and would look perfectly fine on a developer's five-row database.
        with django_assert_num_queries(4):
            employee_roster(DAY, settings_obj=office)


# --- API --------------------------------------------------------------------


@pytest.mark.django_db
class TestDashboardApi:
    def test_admin_dashboard_returns_both_panels(self, admin_client, office):
        employee = EmployeeFactory()
        Attendance.objects.create(employee=employee, date=DAY, status=AttendanceStatus.PRESENT)
        ComputerFactory(status=ComputerStatus.ONLINE)
        client, _ = admin_client

        body = client.get(f"/api/dashboard/?date={DAY}").json()

        assert body["attendance"]["present"] == 1
        assert body["computers"]["online"] == 1

    def test_dashboard_sweeps_stale_computers_first(self, admin_client, office):
        from computers.services import record_heartbeat

        client, _ = admin_client
        computer = ComputerFactory()
        record_heartbeat(computer, now=timezone.now() - dt.timedelta(hours=2))

        body = client.get("/api/dashboard/").json()
        # A machine that died two hours ago must not still be counted as online.
        assert body["computers"]["online"] == 0
        assert body["computers"]["offline"] == 1

    def test_activity_summary_matches_the_section_22_shape(self, admin_client, office):
        client, _ = admin_client
        employee = EmployeeFactory(name="Rahim Ahmed")
        computer = ComputerFactory(employee=employee)
        Attendance.objects.create(
            employee=employee,
            date=DAY,
            status=AttendanceStatus.PRESENT,
            first_check_in_at=local(9, 2),
            last_check_out_at=local(18, 3),
        )
        session(employee, computer, ActivityType.PC_ON, local(9, 1), local(18, 5))
        session(employee, computer, ActivityType.ACTIVE, local(9, 1), local(16, 23))
        session(employee, computer, ActivityType.IDLE, local(16, 23), local(18, 2))
        session(
            employee,
            computer,
            ActivityType.APPLICATION,
            local(9, 5),
            local(13, 17),
            application_name="Visual Studio Code",
            executable_name="Code.exe",
        )
        session(
            employee,
            computer,
            ActivityType.WEBSITE,
            local(9, 5),
            local(10, 47),
            website_domain="github.com",
        )

        body = client.get(f"/api/activity/summary/?employee={employee.pk}&date={DAY}").json()

        assert body["employee"]["name"] == "Rahim Ahmed"
        assert body["attendance"]["status"] == AttendanceStatus.PRESENT
        activity = body["activity"]
        assert activity["pc_on_seconds"] == 9 * 3600 + 4 * 60
        assert activity["top_applications"][0]["name"] == "Visual Studio Code"
        assert activity["top_websites"][0]["name"] == "github.com"
        assert activity["timeline"]["entries"][0]["label"] == "PC started"
        assert len(activity["minute_buckets"]) == 24 * 60
        assert activity["minute_buckets"][9 * 60 + 1] == "A"

    def test_every_payload_carries_the_office_timezone(self, admin_client, office):
        """The pages render clock times, and they must not drift with the viewer.

        An admin looking at the dashboard from another country has to see a 09:02
        check-in as 09:02: the *date* a session belongs to was already decided in
        office-local terms, so a display in the viewer's zone could put the morning on
        the wrong day entirely.
        """
        client, _ = admin_client
        employee = EmployeeFactory()

        assert client.get("/api/dashboard/").json()["timezone"] == "Asia/Dhaka"
        assert client.get("/api/dashboard/employees/").json()["timezone"] == "Asia/Dhaka"
        assert (
            client.get(f"/api/activity/summary/?employee={employee.pk}").json()["timezone"]
            == "Asia/Dhaka"
        )

        own = APIClient()
        own.force_authenticate(user=employee.user)
        assert own.get("/api/me/summary/").json()["timezone"] == "Asia/Dhaka"

    def test_activity_list_filters_by_type_and_date(self, admin_client, office):
        client, _ = admin_client
        employee = EmployeeFactory()
        computer = ComputerFactory(employee=employee)
        session(employee, computer, ActivityType.ACTIVE, local(9), local(10))
        session(
            employee,
            computer,
            ActivityType.APPLICATION,
            local(9),
            local(10),
            application_name="VS Code",
        )
        session(
            employee,
            computer,
            ActivityType.ACTIVE,
            local(9, day=DAY - dt.timedelta(days=1)),
            local(10, day=DAY - dt.timedelta(days=1)),
        )

        body = client.get(f"/api/activity/?employee={employee.pk}&date={DAY}&type=ACTIVE").json()
        assert body["count"] == 1

    def test_employee_dashboard_is_own_data_only(self, db, office):
        employee = EmployeeFactory(leave_total=Decimal("12.0"), leave_used=Decimal("4.0"))
        computer = ComputerFactory(employee=employee)
        today = dt.date.today()
        Attendance.objects.create(employee=employee, date=today, status=AttendanceStatus.PRESENT)
        session(
            employee,
            computer,
            ActivityType.PC_ON,
            timezone.now() - dt.timedelta(hours=2),
            timezone.now() - dt.timedelta(hours=1),
        )

        client = APIClient()
        client.force_authenticate(user=employee.user)
        body = client.get("/api/me/summary/").json()

        assert body["employee"]["id"] == employee.pk
        assert body["leave"]["remaining"] == "8.0"
        assert body["activity"]["pc_on_seconds"] == 3600
        assert body["computers"][0]["computer_name"] == computer.computer_name


# --- Data isolation (§30) ---------------------------------------------------


@pytest.mark.django_db
class TestEmployeeIsolation:
    """The plan's exit criterion: employee A cannot read employee B's data anywhere."""

    @pytest.fixture
    def two_employees(self, office):
        alice = EmployeeFactory(name="Alice")
        bob = EmployeeFactory(name="Bob")
        bob_pc = ComputerFactory(employee=bob)
        session(
            bob,
            bob_pc,
            ActivityType.APPLICATION,
            local(9),
            local(10),
            application_name="Bob's Secret App",
        )
        client = APIClient()
        client.force_authenticate(user=alice.user)
        return alice, bob, client

    def test_activity_list_refuses_another_employees_id(self, two_employees):
        alice, bob, client = two_employees
        response = client.get(f"/api/activity/?employee={bob.pk}")
        # A 403, not a silent fall-back to Alice's own data: quietly returning something
        # else hides the attempt from the caller and from whoever reads the logs.
        assert response.status_code == 403

    def test_activity_list_without_a_parameter_shows_only_own_data(self, two_employees):
        alice, bob, client = two_employees
        body = client.get("/api/activity/").json()
        assert body["count"] == 0

    def test_activity_summary_refuses_another_employees_id(self, two_employees):
        alice, bob, client = two_employees
        assert client.get(f"/api/activity/summary/?employee={bob.pk}").status_code == 403

    def test_admin_dashboard_is_admin_only(self, two_employees):
        alice, bob, client = two_employees
        assert client.get("/api/dashboard/").status_code == 403
        assert client.get("/api/dashboard/employees/").status_code == 403

    def test_my_summary_has_no_employee_parameter_to_abuse(self, two_employees):
        alice, bob, client = two_employees
        body = client.get(f"/api/me/summary/?employee={bob.pk}").json()
        # The parameter is not validated, it simply does not exist: the employee comes
        # from request.user and there is nothing to tamper with.
        assert body["employee"]["id"] == alice.pk

    def test_an_admin_may_read_anyone(self, two_employees, admin_client):
        alice, bob, _ = two_employees
        client, _ = admin_client
        body = client.get(f"/api/activity/summary/?employee={bob.pk}&date={DAY}").json()
        assert body["employee"]["id"] == bob.pk
        assert body["activity"]["top_applications"][0]["name"] == "Bob's Secret App"

    def test_an_unknown_employee_id_is_refused_not_500(self, admin_client):
        client, _ = admin_client
        assert client.get("/api/activity/summary/?employee=999999").status_code == 403
        assert client.get("/api/activity/summary/?employee=nonsense").status_code == 403
