"""Phase 2 API tests: auth, employee management, shifts, leave and settings.

Emphasis on the two things most likely to go quietly wrong: an employee reaching admin
endpoints (§30 data isolation), and a policy toggle being enforced in the UI but not the
API (D6/D7).
"""

import datetime as dt
from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from core.models import AuditLog
from employees.models import Employee, EmployeeStatus, LeaveAdjustment
from tests.factories import AdminFactory, EmployeeFactory, UserFactory

PASSWORD = "test-password-123"


@pytest.fixture
def admin_client(db):
    admin = AdminFactory()
    client = APIClient()
    client.force_authenticate(user=admin)
    return client, admin


@pytest.fixture
def employee_client(db):
    employee = EmployeeFactory()
    client = APIClient()
    client.force_authenticate(user=employee.user)
    return client, employee


@pytest.mark.django_db
class TestAuthentication:
    def test_login_succeeds_and_returns_profile(self):
        employee = EmployeeFactory()
        client = APIClient()
        response = client.post(
            "/api/auth/login/",
            {"email": employee.user.email, "password": PASSWORD},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["email"] == employee.user.email
        assert body["role"] == "EMPLOYEE"
        assert body["employee"]["employee_id"] == employee.employee_id

    def test_login_is_case_insensitive_on_email(self):
        employee = EmployeeFactory()
        client = APIClient()
        response = client.post(
            "/api/auth/login/",
            {"email": employee.user.email.upper(), "password": PASSWORD},
        )
        assert response.status_code == 200

    def test_wrong_password_is_rejected(self):
        employee = EmployeeFactory()
        response = APIClient().post(
            "/api/auth/login/", {"email": employee.user.email, "password": "wrong-password"}
        )
        assert response.status_code == 400

    def test_unknown_and_wrong_password_give_the_same_message(self):
        """Distinguishing them would confirm which emails have accounts."""
        employee = EmployeeFactory()
        unknown = APIClient().post(
            "/api/auth/login/", {"email": "nobody@example.com", "password": "whatever-123"}
        )
        wrong = APIClient().post(
            "/api/auth/login/", {"email": employee.user.email, "password": "wrong-password"}
        )
        assert unknown.json() == wrong.json()

    def test_disabled_account_cannot_log_in(self):
        employee = EmployeeFactory()
        employee.user.is_active = False
        employee.user.save()
        response = APIClient().post(
            "/api/auth/login/", {"email": employee.user.email, "password": PASSWORD}
        )
        assert response.status_code == 400

    def test_me_requires_authentication(self):
        # 401: BearerTokenAuthentication is in DEFAULT_AUTHENTICATION_CLASSES and does
        # send a WWW-Authenticate challenge, so DRF's "no authenticator offered a
        # challenge, fall back to 403" rule no longer applies — same as any other
        # endpoint in this suite now.
        assert APIClient().get("/api/auth/me/").status_code == 401

    def test_csrf_endpoint_sets_the_cookie(self):
        response = APIClient().get("/api/auth/csrf/")
        assert response.status_code == 200
        assert "csrftoken" in response.cookies


@pytest.mark.django_db
class TestTokenAuthentication:
    """The bearer-token login a native client (the Android app) uses instead of a
    session cookie — see accounts/authentication.py."""

    def test_token_login_returns_a_token_and_profile(self):
        employee = EmployeeFactory()
        response = APIClient().post(
            "/api/auth/token/", {"email": employee.user.email, "password": PASSWORD}
        )
        assert response.status_code == 201
        body = response.json()
        assert body["user"]["email"] == employee.user.email
        assert len(body["token"]) > 20

    def test_wrong_password_is_rejected(self):
        employee = EmployeeFactory()
        response = APIClient().post(
            "/api/auth/token/", {"email": employee.user.email, "password": "wrong-password"}
        )
        assert response.status_code == 400

    def test_token_login_creates_no_session(self):
        """Stays stateless: unlike /api/auth/login/, this must never call Django's
        login() — a native client holds its own token, not a browser's session cookie."""
        employee = EmployeeFactory()
        response = APIClient().post(
            "/api/auth/token/", {"email": employee.user.email, "password": PASSWORD}
        )
        assert "sessionid" not in response.cookies

    def test_the_token_authenticates_later_requests(self):
        employee = EmployeeFactory()
        token = (
            APIClient()
            .post("/api/auth/token/", {"email": employee.user.email, "password": PASSWORD})
            .json()["token"]
        )

        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        response = client.get("/api/auth/me/")
        assert response.status_code == 200
        assert response.json()["email"] == employee.user.email

    def test_an_invalid_token_is_rejected(self):
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION="Bearer not-a-real-token")
        assert client.get("/api/auth/me/").status_code == 401

    def test_a_disabled_accounts_token_is_rejected(self):
        employee = EmployeeFactory()
        token = (
            APIClient()
            .post("/api/auth/token/", {"email": employee.user.email, "password": PASSWORD})
            .json()["token"]
        )
        employee.user.is_active = False
        employee.user.save()

        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        assert client.get("/api/auth/me/").status_code == 401

    def test_revoking_the_token_logs_out(self):
        employee = EmployeeFactory()
        token = (
            APIClient()
            .post("/api/auth/token/", {"email": employee.user.email, "password": PASSWORD})
            .json()["token"]
        )

        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        assert client.post("/api/auth/token/revoke/").status_code == 204
        assert client.get("/api/auth/me/").status_code == 401

    def test_revoke_without_a_token_is_a_no_op(self, admin_client):
        """A session-authenticated caller has no bearer token on the request to revoke."""
        client, _ = admin_client
        assert client.post("/api/auth/token/revoke/").status_code == 400

    def test_logging_in_twice_issues_two_independent_tokens(self):
        """One user, two devices (e.g. the web app and a phone): each login's token
        must keep working after the other is revoked."""
        employee = EmployeeFactory()

        def login():
            return (
                APIClient()
                .post("/api/auth/token/", {"email": employee.user.email, "password": PASSWORD})
                .json()["token"]
            )

        token_a, token_b = login(), login()

        client_a = APIClient()
        client_a.credentials(HTTP_AUTHORIZATION=f"Bearer {token_a}")
        client_a.post("/api/auth/token/revoke/")

        client_b = APIClient()
        client_b.credentials(HTTP_AUTHORIZATION=f"Bearer {token_b}")
        assert client_b.get("/api/auth/me/").status_code == 200

    def test_session_auth_still_works_alongside_bearer_auth(self):
        """Both authentication classes are active on the same endpoint (settings.py) —
        a browser session must keep working exactly as before."""
        employee = EmployeeFactory()
        client = APIClient()
        client.post("/api/auth/login/", {"email": employee.user.email, "password": PASSWORD})
        response = client.get("/api/auth/me/")
        assert response.status_code == 200
        assert response.json()["email"] == employee.user.email


@pytest.mark.django_db
class TestEmployeePermissions:
    def test_employee_cannot_list_employees(self, employee_client):
        client, _ = employee_client
        assert client.get("/api/employees/").status_code == 403

    def test_employee_cannot_create_employees(self, employee_client):
        client, _ = employee_client
        response = client.post("/api/employees/", {"employee_id": "EMP-999", "name": "X"})
        assert response.status_code == 403

    def test_employee_cannot_change_settings(self, employee_client):
        client, _ = employee_client
        assert client.patch("/api/settings/", {"radius_meters": 5000}).status_code == 403

    def test_employee_can_read_settings(self, employee_client):
        """The check-in page needs the office coordinates and radius."""
        client, _ = employee_client
        response = client.get("/api/settings/")
        assert response.status_code == 200
        assert "radius_meters" in response.json()

    def test_anonymous_is_refused_everywhere(self):
        client = APIClient()
        for path in ("/api/employees/", "/api/settings/", "/api/holidays/"):
            assert client.get(path).status_code in (401, 403)


@pytest.mark.django_db
class TestEmployeeManagement:
    def test_admin_creates_employee_with_login_and_default_shift(self, admin_client):
        client, admin = admin_client
        response = client.post(
            "/api/employees/",
            {
                "employee_id": "EMP-001",
                "name": "Rahim Ahmed",
                "email": "rahim@example.com",
                "password": "a-good-password-1",
                "department": "Development",
                "designation": "Engineer",
                "joining_date": "2026-01-15",
                "leave_total": "12.0",
            },
        )
        assert response.status_code == 201, response.json()
        body = response.json()
        assert body["employee_id"] == "EMP-001"
        assert body["leave_remaining"] == "12.0"

        employee = Employee.objects.get(employee_id="EMP-001")
        assert employee.user.check_password("a-good-password-1")
        assert employee.user.role == "EMPLOYEE"

        # §4: an employee is unusable without a schedule, so one is seeded.
        shifts = list(employee.shifts.all())
        assert len(shifts) == 1
        assert shifts[0].start_time == dt.time(9, 0)

        assert AuditLog.objects.filter(action=AuditLog.Action.EMPLOYEE_CREATED).count() == 1

    def test_creating_without_password_is_rejected(self, admin_client):
        client, _ = admin_client
        response = client.post(
            "/api/employees/",
            {"employee_id": "EMP-002", "name": "No Password", "email": "np@example.com"},
        )
        assert response.status_code == 400
        assert "password" in response.json()

    def test_duplicate_email_is_rejected(self, admin_client):
        client, _ = admin_client
        existing = EmployeeFactory()
        response = client.post(
            "/api/employees/",
            {
                "employee_id": "EMP-003",
                "name": "Clash",
                "email": existing.user.email.upper(),
                "password": "a-good-password-1",
            },
        )
        assert response.status_code == 400
        assert "email" in response.json()

    def test_disable_deactivates_the_login_too(self, admin_client):
        client, _ = admin_client
        employee = EmployeeFactory()

        response = client.post(f"/api/employees/{employee.id}/disable/")
        assert response.status_code == 200

        employee.refresh_from_db()
        employee.user.refresh_from_db()
        assert employee.status == EmployeeStatus.INACTIVE
        # The important half: a disabled employee must not still be able to log in.
        assert employee.user.is_active is False

        login = APIClient().post(
            "/api/auth/login/", {"email": employee.user.email, "password": PASSWORD}
        )
        assert login.status_code == 400

    def test_enable_restores_access(self, admin_client):
        client, _ = admin_client
        employee = EmployeeFactory()
        client.post(f"/api/employees/{employee.id}/disable/")
        response = client.post(f"/api/employees/{employee.id}/enable/")
        assert response.status_code == 200

        employee.user.refresh_from_db()
        assert employee.user.is_active is True

    def test_employees_cannot_be_deleted(self, admin_client):
        client, _ = admin_client
        employee = EmployeeFactory()
        response = client.delete(f"/api/employees/{employee.id}/")
        assert response.status_code == 405
        assert Employee.objects.filter(pk=employee.pk).exists()

    def test_update_records_only_changed_fields(self, admin_client):
        client, _ = admin_client
        employee = EmployeeFactory(department="Development")

        response = client.patch(
            f"/api/employees/{employee.id}/", {"department": "Design"}, format="json"
        )
        assert response.status_code == 200

        entry = AuditLog.objects.filter(action=AuditLog.Action.EMPLOYEE_UPDATED).first()
        assert entry is not None
        changes = entry.payload["changes"]
        assert changes == {"department": {"from": "Development", "to": "Design"}}

    def test_search_and_filter(self, admin_client):
        client, _ = admin_client
        EmployeeFactory(name="Rahim Ahmed", department="Development")
        EmployeeFactory(name="Karim Uddin", department="Sales")

        results = client.get("/api/employees/?search=Rahim").json()["results"]
        assert len(results) == 1
        assert results[0]["name"] == "Rahim Ahmed"

        results = client.get("/api/employees/?department=sales").json()["results"]
        assert len(results) == 1
        assert results[0]["name"] == "Karim Uddin"


@pytest.mark.django_db
class TestShifts:
    def test_split_shift_is_rejected_while_the_toggle_is_off(self, admin_client):
        """D7 must be enforced by the API, not just hidden in the UI."""
        client, _ = admin_client
        employee = EmployeeFactory()

        response = client.put(
            f"/api/employees/{employee.id}/shifts/",
            {
                "shifts": [
                    {"start_time": "09:00", "end_time": "13:00"},
                    {"start_time": "14:00", "end_time": "18:00"},
                ]
            },
            format="json",
        )
        assert response.status_code == 400
        assert "Split shifts are disabled" in str(response.json())

    def test_split_shift_is_accepted_once_enabled(self, admin_client):
        client, _ = admin_client
        client.patch("/api/settings/", {"allow_split_shift": True}, format="json")
        employee = EmployeeFactory()

        response = client.put(
            f"/api/employees/{employee.id}/shifts/",
            {
                "shifts": [
                    {"start_time": "09:00", "end_time": "13:00"},
                    {"start_time": "14:00", "end_time": "18:00"},
                ]
            },
            format="json",
        )
        assert response.status_code == 200
        employee.refresh_from_db()
        assert employee.shifts.count() == 2
        assert employee.is_split_shift is True
        assert AuditLog.objects.filter(action=AuditLog.Action.SHIFTS_UPDATED).exists()

    def test_overlapping_shifts_are_rejected(self, admin_client):
        client, _ = admin_client
        client.patch("/api/settings/", {"allow_split_shift": True}, format="json")
        employee = EmployeeFactory()

        response = client.put(
            f"/api/employees/{employee.id}/shifts/",
            {
                "shifts": [
                    {"start_time": "09:00", "end_time": "14:00"},
                    {"start_time": "13:00", "end_time": "18:00"},
                ]
            },
            format="json",
        )
        assert response.status_code == 400
        assert "overlap" in str(response.json()).lower()

    def test_at_least_one_shift_is_required(self, admin_client):
        client, _ = admin_client
        employee = EmployeeFactory()
        response = client.put(
            f"/api/employees/{employee.id}/shifts/", {"shifts": []}, format="json"
        )
        assert response.status_code == 400

    def test_replacing_shifts_renumbers_by_start_time(self, admin_client):
        client, _ = admin_client
        client.patch("/api/settings/", {"allow_split_shift": True}, format="json")
        employee = EmployeeFactory()

        client.put(
            f"/api/employees/{employee.id}/shifts/",
            {
                "shifts": [
                    {"start_time": "14:00", "end_time": "18:00"},
                    {"start_time": "09:00", "end_time": "13:00"},
                ]
            },
            format="json",
        )
        shifts = list(employee.shifts.order_by("sequence"))
        assert [s.sequence for s in shifts] == [1, 2]
        assert shifts[0].start_time == dt.time(9, 0)


@pytest.mark.django_db
class TestLeaveAdjustments:
    def test_adjustment_updates_the_balance_and_audits_it(self, admin_client):
        client, _ = admin_client
        employee = EmployeeFactory(leave_total=Decimal("12.0"))

        response = client.post(
            "/api/leave-adjustments/",
            {"employee": employee.id, "target": "TOTAL", "delta": "3.0", "reason": "Carry over"},
            format="json",
        )
        assert response.status_code == 201, response.json()

        employee.refresh_from_db()
        assert employee.leave_total == Decimal("15.0")
        assert employee.leave_remaining == Decimal("15.0")
        assert AuditLog.objects.filter(action=AuditLog.Action.LEAVE_ADJUSTED).exists()

    def test_half_day_is_rejected_while_the_toggle_is_off(self, admin_client):
        """D6 enforced server-side."""
        client, _ = admin_client
        employee = EmployeeFactory()

        response = client.post(
            "/api/leave-adjustments/",
            {"employee": employee.id, "target": "TOTAL", "delta": "0.5"},
            format="json",
        )
        assert response.status_code == 400
        assert "increments" in str(response.json())

    def test_half_day_is_accepted_once_enabled(self, admin_client):
        client, _ = admin_client
        client.patch("/api/settings/", {"allow_half_day_leave": True}, format="json")
        employee = EmployeeFactory(leave_total=Decimal("12.0"))

        response = client.post(
            "/api/leave-adjustments/",
            {"employee": employee.id, "target": "USED", "delta": "0.5", "reason": "Half day"},
            format="json",
        )
        assert response.status_code == 201, response.json()

        employee.refresh_from_db()
        assert employee.leave_used == Decimal("0.5")
        assert employee.leave_remaining == Decimal("11.5")

    def test_cannot_use_more_leave_than_available(self, admin_client):
        client, _ = admin_client
        employee = EmployeeFactory(leave_total=Decimal("2.0"))

        response = client.post(
            "/api/leave-adjustments/",
            {"employee": employee.id, "target": "USED", "delta": "5.0"},
            format="json",
        )
        assert response.status_code == 400

    def test_cannot_drop_total_below_leave_already_used(self, admin_client):
        client, _ = admin_client
        employee = EmployeeFactory(leave_total=Decimal("10.0"), leave_used=Decimal("6.0"))

        response = client.post(
            "/api/leave-adjustments/",
            {"employee": employee.id, "target": "TOTAL", "delta": "-8.0"},
            format="json",
        )
        assert response.status_code == 400

    def test_zero_adjustment_is_rejected(self, admin_client):
        client, _ = admin_client
        employee = EmployeeFactory()
        response = client.post(
            "/api/leave-adjustments/",
            {"employee": employee.id, "delta": "0"},
            format="json",
        )
        assert response.status_code == 400

    def test_adjustments_cannot_be_edited_or_deleted(self, admin_client):
        client, _ = admin_client
        employee = EmployeeFactory()
        client.post(
            "/api/leave-adjustments/",
            {"employee": employee.id, "delta": "1.0"},
            format="json",
        )
        adjustment = LeaveAdjustment.objects.first()
        assert client.patch(f"/api/leave-adjustments/{adjustment.id}/", {}).status_code == 405
        assert client.delete(f"/api/leave-adjustments/{adjustment.id}/").status_code == 405


@pytest.mark.django_db
class TestSettingsApi:
    def test_admin_updates_weekend_days(self, admin_client):
        client, _ = admin_client
        response = client.patch("/api/settings/", {"weekend_days": [5, 6]}, format="json")
        assert response.status_code == 200
        assert response.json()["weekend_days"] == [5, 6]
        assert AuditLog.objects.filter(action=AuditLog.Action.SETTINGS_UPDATED).exists()

    def test_every_day_as_weekend_is_rejected(self, admin_client):
        client, _ = admin_client
        response = client.patch(
            "/api/settings/", {"weekend_days": [0, 1, 2, 3, 4, 5, 6]}, format="json"
        )
        assert response.status_code == 400

    def test_unknown_timezone_is_rejected(self, admin_client):
        client, _ = admin_client
        response = client.patch("/api/settings/", {"timezone": "Nowhere/Fake"}, format="json")
        assert response.status_code == 400

    def test_shortening_retention_requires_explicit_confirmation(self, admin_client):
        """D5 is destructive in one direction only, so that direction asks first."""
        client, _ = admin_client

        response = client.patch("/api/settings/", {"activity_retention_days": 30}, format="json")
        assert response.status_code == 400
        assert "confirm_shorter_retention" in str(response.json())

        response = client.patch(
            "/api/settings/",
            {"activity_retention_days": 30, "confirm_shorter_retention": True},
            format="json",
        )
        assert response.status_code == 200
        assert response.json()["activity_retention_days"] == 30

    def test_lengthening_retention_needs_no_confirmation(self, admin_client):
        client, _ = admin_client
        response = client.patch("/api/settings/", {"activity_retention_days": 365}, format="json")
        assert response.status_code == 200

    def test_retention_floor_is_enforced(self, admin_client):
        client, _ = admin_client
        response = client.patch(
            "/api/settings/",
            {"activity_retention_days": 0, "confirm_shorter_retention": True},
            format="json",
        )
        assert response.status_code == 400


@pytest.mark.django_db
class TestHolidays:
    def test_admin_creates_and_deletes_holidays(self, admin_client):
        client, _ = admin_client
        response = client.post(
            "/api/holidays/", {"date": "2026-12-16", "name": "Victory Day"}, format="json"
        )
        assert response.status_code == 201
        holiday_id = response.json()["id"]
        assert AuditLog.objects.filter(action=AuditLog.Action.HOLIDAY_CREATED).exists()

        assert client.delete(f"/api/holidays/{holiday_id}/").status_code == 204
        assert AuditLog.objects.filter(action=AuditLog.Action.HOLIDAY_DELETED).exists()

    def test_admin_updates_holiday_writes_audit_log(self, admin_client):
        client, _ = admin_client
        response = client.post(
            "/api/holidays/", {"date": "2026-12-16", "name": "Victory Day"}, format="json"
        )
        holiday_id = response.json()["id"]

        response = client.patch(
            f"/api/holidays/{holiday_id}/", {"name": "Victory Day (updated)"}, format="json"
        )
        assert response.status_code == 200
        entry = AuditLog.objects.get(action=AuditLog.Action.HOLIDAY_UPDATED)
        assert entry.payload["changes"]["name"] == {
            "from": "Victory Day",
            "to": "Victory Day (updated)",
        }

    def test_employee_cannot_create_holidays(self, employee_client):
        client, _ = employee_client
        response = client.post(
            "/api/holidays/", {"date": "2026-12-16", "name": "Victory Day"}, format="json"
        )
        assert response.status_code == 403

    def test_duplicate_holiday_date_is_rejected(self, admin_client):
        client, _ = admin_client
        client.post("/api/holidays/", {"date": "2026-12-16", "name": "Victory Day"}, format="json")
        response = client.post(
            "/api/holidays/", {"date": "2026-12-16", "name": "Duplicate"}, format="json"
        )
        assert response.status_code == 400


@pytest.mark.django_db
class TestAuditLogIntegrity:
    def test_audit_survives_deleting_the_actor(self, admin_client):
        client, admin = admin_client
        employee = EmployeeFactory()
        client.post(f"/api/employees/{employee.id}/disable/")

        assert AuditLog.objects.count() >= 1
        admin.delete()

        entry = AuditLog.objects.filter(action=AuditLog.Action.EMPLOYEE_DISABLED).first()
        assert entry is not None
        # The record of what happened must outlive the account that did it.
        assert entry.actor is None
        assert entry.target_id == str(employee.id)


@pytest.mark.django_db
class TestUserRoles:
    def test_admin_flag_follows_the_role(self):
        assert AdminFactory().is_admin is True
        assert UserFactory().is_admin is False
