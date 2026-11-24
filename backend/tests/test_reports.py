"""Phase 8: reports and export (§25, §26, §37 Reports).

Three things are worth testing here and the rest is plumbing.

**The numbers must match the dashboards.** A report and an activity page that disagree
about how long Tuesday was are worse than either alone, so the tests assert the same
midnight-splitting and no-summing-across-types rules Phase 7 established — against the
report path this time.

**Worked time is not last-minus-first.** With split shifts the two differ by the length
of the lunch break, and only one of them is the number an employee is paid for.

**The export must contain what the report shows.** A CSV that quietly stops at the page
size, or an Excel file whose durations are text, is a report that lied.
"""

import datetime as dt
import io

import pytest
from rest_framework.test import APIClient

from activities.models import Activity, ActivityType
from attendance.models import AppSettings, Attendance, AttendancePunch, AttendanceStatus
from core.models import AuditLog
from employees.models import EmployeeStatus
from reports.exporters import hhmm
from reports.filters import FilterError, ReportFilters
from reports.queries import activity_rows, attendance_rows, page
from tests.factories import AdminFactory, ComputerFactory, EmployeeFactory

DHAKA = dt.timezone(dt.timedelta(hours=6))
DAY = dt.date(2026, 8, 18)
NEXT_DAY = dt.date(2026, 8, 19)


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
    return client


def local(hour, minute=0, day=DAY):
    """An office-local wall-clock time, as the UTC instant it really is."""
    return dt.datetime.combine(day, dt.time(hour, minute), tzinfo=DHAKA)


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


def attendance(employee, day=DAY, **fields):
    defaults = {
        "first_check_in_at": local(9, 2, day),
        "last_check_out_at": local(18, 0, day),
        "worked_seconds": 8 * 3600 + 58 * 60,
        "late_minutes": 2,
        "status": AttendanceStatus.LATE,
    }
    defaults.update(fields)
    return Attendance.objects.create(employee=employee, date=day, **defaults)


def punch(record, sequence, check_in, check_out, **fields):
    return AttendancePunch.objects.create(
        attendance=record,
        sequence=sequence,
        check_in_at=check_in,
        check_out_at=check_out,
        **fields,
    )


def filters_for(office, **params):
    return ReportFilters(params, office)


# --- Filters ----------------------------------------------------------------


class TestFilters:
    def test_date_defaults_to_today_in_office_terms(self, office):
        # 20:30 UTC on the 18th is already the 19th in Dhaka. The report must agree with
        # the attendance rows, which were filed against the office-local date.
        with_time = dt.datetime(2026, 8, 18, 20, 30, tzinfo=dt.timezone.utc)
        from freezegun import freeze_time

        with freeze_time(with_time):
            filters = filters_for(office)
        assert filters.date_from == NEXT_DAY
        assert filters.date_to == NEXT_DAY

    def test_a_single_date_is_a_one_day_range(self, office):
        filters = filters_for(office, date="2026-08-18")
        assert filters.date_from == filters.date_to == DAY
        assert filters.day_count == 1

    def test_date_range_is_inclusive_at_both_ends(self, office):
        filters = filters_for(office, date_from="2026-08-18", date_to="2026-08-20")
        assert list(filters.days) == [DAY, NEXT_DAY, dt.date(2026, 8, 20)]

    def test_a_backwards_range_is_refused(self, office):
        with pytest.raises(FilterError):
            filters_for(office, date_from="2026-08-20", date_to="2026-08-18")

    def test_an_absurd_range_is_refused_rather_than_attempted(self, office):
        # A mistyped year is the realistic way this happens, and the failure mode
        # without a cap is a timeout rather than an error message.
        with pytest.raises(FilterError) as exc:
            filters_for(office, date_from="2016-01-01", date_to="2026-08-18")
        assert "maximum" in str(exc.value)

    def test_an_unknown_status_is_refused(self, office):
        with pytest.raises(FilterError):
            filters_for(office, status="SLEEPING")

    def test_limit_is_clamped_rather_than_trusted(self, office):
        assert filters_for(office, limit="100000").limit == 1000
        assert filters_for(office, limit="0").limit == 1

    def test_inactive_employees_are_excluded_by_default_but_can_be_included(self, office):
        active = EmployeeFactory()
        left = EmployeeFactory(status=EmployeeStatus.INACTIVE)

        assert list(filters_for(office).employees()) == [active]
        assert set(filters_for(office, include_inactive="1").employees()) == {active, left}


# --- Attendance report ------------------------------------------------------


class TestAttendanceReport:
    def test_row_carries_every_section_25_column(self, office):
        employee = EmployeeFactory(name="Ayesha Rahman", department="Development")
        record = attendance(employee)
        punch(
            record,
            1,
            local(9, 2),
            local(18, 0),
            late_minutes=2,
            check_in_location_status="INSIDE",
            check_in_distance_m=41.0,
            check_in_accuracy_m=18.0,
        )

        (row,) = list(attendance_rows(filters_for(office, date="2026-08-18")))

        assert row["employee_name"] == "Ayesha Rahman"
        assert row["date"] == DAY
        assert row["first_check_in_at"] == local(9, 2)
        assert row["last_check_out_at"] == local(18, 0)
        assert row["late_minutes"] == 2
        assert row["status"] == AttendanceStatus.LATE
        assert row["check_in_location"] == "INSIDE"
        assert row["check_in_distance_m"] == 41.0
        assert row["punch_count"] == 1

    def test_worked_time_is_not_last_check_out_minus_first_check_in(self, office):
        """A split shift with a two-hour lunch is not a ten-hour day (D7)."""
        employee = EmployeeFactory(
            shifts=[(dt.time(9, 0), dt.time(13, 0)), (dt.time(15, 0), dt.time(19, 0))]
        )
        record = attendance(
            employee,
            first_check_in_at=local(9, 0),
            last_check_out_at=local(19, 0),
            worked_seconds=8 * 3600,
            late_minutes=0,
            status=AttendanceStatus.PRESENT,
        )
        punch(record, 1, local(9, 0), local(13, 0))
        punch(record, 2, local(15, 0), local(19, 0))

        (row,) = list(attendance_rows(filters_for(office, date="2026-08-18")))

        elapsed = (row["last_check_out_at"] - row["first_check_in_at"]).total_seconds()
        assert elapsed == 10 * 3600
        assert row["worked_seconds"] == 8 * 3600
        assert row["punch_count"] == 2

    def test_status_filter_narrows_the_rows(self, office):
        present = EmployeeFactory(name="A")
        late = EmployeeFactory(name="B")
        attendance(present, status=AttendanceStatus.PRESENT, late_minutes=0)
        attendance(late, status=AttendanceStatus.LATE)

        rows = list(attendance_rows(filters_for(office, date="2026-08-18", status="late")))
        assert [row["employee_id"] for row in rows] == [late.pk]

    def test_department_filter_narrows_the_rows(self, office):
        dev = EmployeeFactory(name="A", department="Development")
        sales = EmployeeFactory(name="B", department="Sales")
        attendance(dev)
        attendance(sales)

        rows = list(attendance_rows(filters_for(office, date="2026-08-18", department="sales")))
        assert [row["employee_id"] for row in rows] == [sales.pk]

    def test_rows_are_ordered_by_date_then_name(self, office):
        zoe = EmployeeFactory(name="Zoe")
        adam = EmployeeFactory(name="Adam")
        for employee in (zoe, adam):
            attendance(employee, day=DAY)
            attendance(employee, day=NEXT_DAY)

        rows = list(
            attendance_rows(filters_for(office, date_from="2026-08-18", date_to="2026-08-19"))
        )
        assert [(row["date"], row["employee_name"]) for row in rows] == [
            (DAY, "Adam"),
            (DAY, "Zoe"),
            (NEXT_DAY, "Adam"),
            (NEXT_DAY, "Zoe"),
        ]

    def test_a_day_with_no_record_produces_no_row(self, office):
        EmployeeFactory()
        assert list(attendance_rows(filters_for(office, date="2026-08-18"))) == []


# --- PC activity report -----------------------------------------------------


class TestActivityReport:
    @pytest.fixture
    def employee(self, office):
        return EmployeeFactory(name="Ayesha Rahman", department="Development")

    @pytest.fixture
    def computer(self, employee):
        return ComputerFactory(employee=employee)

    def test_row_carries_every_section_25_column(self, office, employee, computer):
        session(employee, computer, ActivityType.PC_ON, local(9, 0), local(18, 0))
        session(employee, computer, ActivityType.ACTIVE, local(9, 0), local(16, 0))
        session(employee, computer, ActivityType.IDLE, local(16, 0), local(18, 0))
        session(
            employee,
            computer,
            ActivityType.APPLICATION,
            local(9, 0),
            local(14, 0),
            application_name="Visual Studio Code",
        )
        session(
            employee,
            computer,
            ActivityType.APPLICATION,
            local(14, 0),
            local(16, 0),
            application_name="Google Chrome",
        )
        session(
            employee,
            computer,
            ActivityType.WEBSITE,
            local(14, 0),
            local(15, 30),
            website_domain="github.com",
        )

        (row,) = list(activity_rows(filters_for(office, date="2026-08-18")))

        assert row["employee_name"] == "Ayesha Rahman"
        assert row["date"] == DAY
        assert row["pc_on_seconds"] == 9 * 3600
        assert row["active_seconds"] == 7 * 3600
        assert row["idle_seconds"] == 2 * 3600
        assert row["top_application"] == {"name": "Visual Studio Code", "seconds": 5 * 3600}
        assert row["top_website"] == {"name": "github.com", "seconds": 90 * 60}

    def test_nothing_is_summed_across_activity_types(self, office, employee, computer):
        """ACTIVE and APPLICATION cover the same minutes. Adding them means nothing."""
        session(employee, computer, ActivityType.ACTIVE, local(9, 0), local(10, 0))
        session(
            employee,
            computer,
            ActivityType.APPLICATION,
            local(9, 0),
            local(10, 0),
            application_name="Excel",
        )

        (row,) = list(activity_rows(filters_for(office, date="2026-08-18")))
        assert row["active_seconds"] == 3600
        assert row["top_application"]["seconds"] == 3600

    def test_a_session_crossing_midnight_is_split_between_the_two_dates(
        self, office, employee, computer
    ):
        # 22:00 to 02:00 local: two hours on each date, not four on one of them. ACTIVE,
        # not PC_ON: "PC on" is reported as active+idle (see summarise()), and the
        # day-splitting behaviour under test is identical for either type.
        session(employee, computer, ActivityType.ACTIVE, local(22, 0), local(2, 0, NEXT_DAY))

        rows = list(
            activity_rows(filters_for(office, date_from="2026-08-18", date_to="2026-08-19"))
        )
        assert [(row["date"], row["pc_on_seconds"]) for row in rows] == [
            (DAY, 2 * 3600),
            (NEXT_DAY, 2 * 3600),
        ]

    def test_an_open_session_stops_at_midnight_for_a_past_day(self, office, employee, computer):
        """A session nobody closed must not grow every time the report is opened."""
        # ACTIVE, not PC_ON: see the note on the midnight-split test above.
        session(employee, computer, ActivityType.ACTIVE, local(22, 0), None)

        now = local(12, 0, dt.date(2026, 9, 1))
        (row,) = list(activity_rows(filters_for(office, date="2026-08-18"), now=now))
        assert row["pc_on_seconds"] == 2 * 3600

    def test_grouping_by_employee_totals_the_range_and_drops_the_date(
        self, office, employee, computer
    ):
        session(employee, computer, ActivityType.ACTIVE, local(9, 0), local(12, 0))
        session(
            employee, computer, ActivityType.ACTIVE, local(9, 0, NEXT_DAY), local(13, 0, NEXT_DAY)
        )

        (row,) = list(
            activity_rows(
                filters_for(office, date_from="2026-08-18", date_to="2026-08-19", group="employee")
            )
        )
        assert row["date"] is None
        assert row["active_seconds"] == 7 * 3600

    def test_grouped_totals_equal_the_sum_of_the_daily_rows(self, office, employee, computer):
        """The two groupings are two views of one number, not two numbers."""
        session(employee, computer, ActivityType.ACTIVE, local(22, 0), local(2, 0, NEXT_DAY))

        daily = list(
            activity_rows(filters_for(office, date_from="2026-08-18", date_to="2026-08-19"))
        )
        (grouped,) = list(
            activity_rows(
                filters_for(office, date_from="2026-08-18", date_to="2026-08-19", group="employee")
            )
        )
        assert grouped["active_seconds"] == sum(row["active_seconds"] for row in daily)

    def test_an_employee_with_no_activity_produces_no_row(self, office, employee):
        assert list(activity_rows(filters_for(office, date="2026-08-18"))) == []

    def test_query_count_scales_with_days_not_with_headcount(
        self, office, django_assert_num_queries
    ):
        """The N+1 that matters here is per-employee, and it is the one that is absent.

        One query per day covers the whole roster; adding people does not add queries.
        Memory stays flat for the same reason — a year-long export never holds more than
        one day of sessions at a time.
        """
        for index in range(6):
            employee = EmployeeFactory(name=f"Employee {index}")
            computer = ComputerFactory(employee=employee)
            session(employee, computer, ActivityType.ACTIVE, local(9, 0), local(17, 0))

        filters = filters_for(office, date="2026-08-18")
        # One for the employee list, one for that day's sessions.
        with django_assert_num_queries(2):
            rows = list(activity_rows(filters))
        assert len(rows) == 6


# --- Pagination -------------------------------------------------------------


class TestPagination:
    def test_a_page_reports_whether_more_follows(self):
        rows, has_more = page(iter(range(10)), limit=3, offset=0)
        assert rows == [0, 1, 2]
        assert has_more is True

    def test_the_last_page_says_so(self):
        rows, has_more = page(iter(range(10)), limit=5, offset=5)
        assert rows == [5, 6, 7, 8, 9]
        assert has_more is False

    def test_an_offset_past_the_end_is_empty_rather_than_an_error(self):
        rows, has_more = page(iter(range(3)), limit=5, offset=99)
        assert rows == []
        assert has_more is False


# --- API --------------------------------------------------------------------


@pytest.mark.django_db
class TestReportEndpoints:
    def test_attendance_report_returns_rows_and_echoes_its_filters(self, office, admin_client):
        employee = EmployeeFactory(name="Ayesha Rahman")
        record = attendance(employee)
        punch(record, 1, local(9, 2), local(18, 0), check_in_location_status="INSIDE")

        response = admin_client.get("/api/reports/attendance/?date=2026-08-18")

        assert response.status_code == 200
        assert response.data["report"] == "attendance"
        assert response.data["timezone"] == "Asia/Dhaka"
        assert response.data["filters"]["date_from"] == "2026-08-18"
        assert response.data["has_more"] is False
        assert len(response.data["rows"]) == 1
        assert response.data["rows"][0]["employee_name"] == "Ayesha Rahman"

    def test_activity_report_is_filterable_by_date(self, office, admin_client):
        employee = EmployeeFactory()
        computer = ComputerFactory(employee=employee)
        session(employee, computer, ActivityType.ACTIVE, local(9, 0), local(17, 0))

        on_the_day = admin_client.get("/api/reports/activity/?date=2026-08-18")
        the_day_after = admin_client.get("/api/reports/activity/?date=2026-08-20")

        assert len(on_the_day.data["rows"]) == 1
        assert on_the_day.data["rows"][0]["active_seconds"] == 8 * 3600
        assert the_day_after.data["rows"] == []

    def test_a_bad_date_is_a_400_with_a_readable_message(self, office, admin_client):
        response = admin_client.get("/api/reports/attendance/?date=last-tuesday")
        assert response.status_code == 400
        assert "last-tuesday" in response.data["detail"]

    def test_an_over_long_range_is_refused(self, office, admin_client):
        response = admin_client.get(
            "/api/reports/attendance/?date_from=2016-01-01&date_to=2026-08-18"
        )
        assert response.status_code == 400

    def test_paging_walks_the_whole_report(self, office, admin_client):
        for index in range(5):
            attendance(EmployeeFactory(name=f"Employee {index}"))

        first = admin_client.get("/api/reports/attendance/?date=2026-08-18&limit=2")
        second = admin_client.get("/api/reports/attendance/?date=2026-08-18&limit=2&offset=4")

        assert len(first.data["rows"]) == 2
        assert first.data["has_more"] is True
        assert len(second.data["rows"]) == 1
        assert second.data["has_more"] is False

    def test_an_unknown_report_is_a_404(self, office, admin_client):
        assert admin_client.get("/api/reports/payroll/export/?format=csv").status_code == 404


@pytest.mark.django_db
class TestReportPermissions:
    """Reports read every employee's data, so there is no employee-facing variant."""

    def _employee_client(self):
        employee = EmployeeFactory()
        client = APIClient()
        client.force_authenticate(user=employee.user)
        return client

    @pytest.mark.parametrize(
        "path",
        [
            "/api/reports/attendance/",
            "/api/reports/activity/",
            "/api/reports/attendance/export/?format=csv",
            "/api/reports/activity/export/?format=xlsx",
        ],
    )
    def test_an_employee_is_refused(self, office, path):
        assert self._employee_client().get(path).status_code == 403

    @pytest.mark.parametrize(
        "path", ["/api/reports/attendance/", "/api/reports/activity/export/?format=csv"]
    )
    def test_an_anonymous_caller_is_refused(self, office, path):
        assert APIClient().get(path).status_code in (401, 403)


# --- Export -----------------------------------------------------------------


def csv_text(response):
    return b"".join(response.streaming_content).decode("utf-8-sig")


@pytest.mark.django_db
class TestExport:
    @pytest.fixture
    def seeded(self, office):
        employee = EmployeeFactory(name="Ayesha Rahman", department="Development")
        computer = ComputerFactory(employee=employee)
        record = attendance(employee)
        punch(
            record,
            1,
            local(9, 2),
            local(18, 0),
            late_minutes=2,
            check_in_location_status="INSIDE",
            check_in_distance_m=41.0,
        )
        session(employee, computer, ActivityType.PC_ON, local(9, 0), local(18, 0))
        session(employee, computer, ActivityType.ACTIVE, local(9, 0), local(16, 0))
        # Without this, "PC on" (= active + idle, see summarise()) would be 7h, not 9h:
        # the fixture's own PC_ON span runs to 18:00, so sampler coverage needs to too.
        session(employee, computer, ActivityType.IDLE, local(16, 0), local(18, 0))
        session(
            employee,
            computer,
            ActivityType.APPLICATION,
            local(9, 0),
            local(14, 0),
            application_name="Visual Studio Code",
        )
        return employee

    def test_attendance_csv_has_a_header_and_the_row(self, admin_client, seeded):
        response = admin_client.get("/api/reports/attendance/export/?format=csv&date=2026-08-18")

        assert response.status_code == 200
        assert response["Content-Type"].startswith("text/csv")
        assert 'filename="attendance-2026-08-18.csv"' in response["Content-Disposition"]

        lines = csv_text(response).strip().splitlines()
        assert lines[0].split(",")[:4] == ["Employee ID", "Employee", "Department", "Date"]
        assert "Ayesha Rahman" in lines[1]
        assert "2026-08-18" in lines[1]

    def test_csv_clock_times_are_office_local(self, admin_client, seeded):
        """09:02 in Dhaka is 03:02 UTC. A report that said 03:02 would be wrong."""
        body = csv_text(
            admin_client.get("/api/reports/attendance/export/?format=csv&date=2026-08-18")
        )
        assert "2026-08-18 09:02" in body
        assert "2026-08-18 03:02" not in body

    def test_csv_starts_with_a_byte_order_mark(self, admin_client, seeded):
        """Without it Excel on Windows reads UTF-8 names as the system code page."""
        raw = b"".join(
            admin_client.get(
                "/api/reports/attendance/export/?format=csv&date=2026-08-18"
            ).streaming_content
        )
        assert raw.startswith(b"\xef\xbb\xbf")

    def test_export_ignores_the_page_size(self, admin_client, office):
        """An export that stopped at the page size would be a silent truncation."""
        for index in range(7):
            attendance(EmployeeFactory(name=f"Employee {index}"))

        response = admin_client.get(
            "/api/reports/attendance/export/?format=csv&date=2026-08-18&limit=2"
        )
        rows = csv_text(response).strip().splitlines()
        assert len(rows) == 8  # header + seven employees

    def test_activity_csv_carries_the_top_application(self, admin_client, seeded):
        body = csv_text(
            admin_client.get("/api/reports/activity/export/?format=csv&date=2026-08-18")
        )
        header, row = body.strip().splitlines()
        assert "Top application" in header
        assert "Visual Studio Code" in row
        # PC on 9h, active 7h — rendered as elapsed hours, not clock time.
        assert "9:00" in row and "7:00" in row

    def test_punch_detail_rows_are_opt_in(self, admin_client, office):
        employee = EmployeeFactory(name="Split Shift")
        record = attendance(employee, first_check_in_at=local(9, 0), last_check_out_at=local(19, 0))
        punch(record, 1, local(9, 0), local(13, 0))
        punch(record, 2, local(15, 0), local(19, 0))

        plain = csv_text(
            admin_client.get("/api/reports/attendance/export/?format=csv&date=2026-08-18")
        )
        detailed = csv_text(
            admin_client.get(
                "/api/reports/attendance/export/?format=csv&date=2026-08-18&detail=punches"
            )
        )

        assert len(plain.strip().splitlines()) == 2
        assert len(detailed.strip().splitlines()) == 4
        assert "Punch 2" in detailed

    def test_xlsx_is_a_workbook_whose_durations_are_real_durations(self, admin_client, seeded):
        from openpyxl import load_workbook

        response = admin_client.get("/api/reports/activity/export/?format=xlsx&date=2026-08-18")

        assert response.status_code == 200
        assert 'filename="activity-2026-08-18.xlsx"' in response["Content-Disposition"]

        workbook = load_workbook(io.BytesIO(response.content))
        sheet = workbook.active
        headers = [cell.value for cell in sheet[1]]
        row = dict(zip(headers, sheet[2], strict=True))

        assert row["Employee"].value == "Ayesha Rahman"
        # A duration Excel can sum: stored as a fraction of a day under an elapsed-hours
        # format, not as the string "9:00" that no SUM() would ever touch. openpyxl
        # reads that pair back as a timedelta, which a text cell could never produce.
        assert row["PC on time"].value == dt.timedelta(hours=9)
        assert row["PC on time"].number_format == "[h]:mm"
        assert row["Active time"].value == dt.timedelta(hours=7)
        assert row["Top application"].value == "Visual Studio Code"

    def test_an_unknown_format_is_refused(self, admin_client, seeded):
        assert admin_client.get("/api/reports/attendance/export/?format=pdf").status_code == 400

    def test_excel_is_accepted_as_a_spelling_of_xlsx(self, admin_client, seeded):
        response = admin_client.get("/api/reports/attendance/export/?format=excel&date=2026-08-18")
        assert response.status_code == 200
        assert response["Content-Disposition"].endswith('.xlsx"')

    def test_an_export_is_audited_with_who_what_and_how_many(self, admin_client, seeded):
        response = admin_client.get("/api/reports/attendance/export/?format=csv&date=2026-08-18")
        csv_text(response)  # the stream must be consumed before the entry is written

        entry = AuditLog.objects.get(action=AuditLog.Action.REPORT_EXPORTED)
        assert entry.actor is not None
        assert entry.payload["report"] == "attendance"
        assert entry.payload["format"] == "csv"
        assert entry.payload["rows"] == 1
        assert entry.payload["filters"]["date_from"] == "2026-08-18"

    def test_a_csv_export_is_not_audited_before_it_is_delivered(self, admin_client, seeded):
        """A download the client abandoned should not be logged as one that happened."""
        admin_client.get("/api/reports/attendance/export/?format=csv&date=2026-08-18")
        assert not AuditLog.objects.filter(action=AuditLog.Action.REPORT_EXPORTED).exists()


# --- Formatting -------------------------------------------------------------


class TestDurationFormatting:
    @pytest.mark.parametrize(
        ("seconds", "text"),
        [
            (0, "0:00"),
            (59, "0:00"),
            (60, "0:01"),
            (3600, "1:00"),
            (8 * 3600 + 58 * 60, "8:58"),
            # Elapsed hours, not clock hours: a fortnight of PC time is not "3:30".
            (99 * 3600 + 30 * 60, "99:30"),
        ],
    )
    def test_durations_render_as_elapsed_hours(self, seconds, text):
        assert hhmm(seconds) == text

    def test_a_missing_duration_is_blank_not_zero(self):
        assert hhmm(None) == ""
