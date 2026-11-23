"""Phase 9: hardening and the retention job (§30, §31, D5).

Security settings are ordinarily not worth testing — they are declarations, and a test
that asserts a constant equals itself proves nothing. These are the exceptions:

**The retention job destroys data**, so it gets the same scrutiny as the code that
creates it. What it must not touch is tested as explicitly as what it must.

**The insecure-by-accident cases**, where the failure is silent. A deploy with
`DEBUG=false` and a placeholder secret key looks healthy and is not; a hasher that
quietly reverted to something weak looks identical from outside. Both are asserted here
because nothing else would notice.
"""

import datetime as dt
import importlib

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import identify_hasher
from django.core.management import call_command
from django.core.management.base import CommandError
from django.utils import timezone
from rest_framework.test import APIClient

from activities.models import Activity, ActivityType
from activities.retention import (
    MINIMUM_RETENTION_DAYS,
    expired_activity,
    purge_activity,
    retention_cutoff,
)
from attendance.models import AppSettings, Attendance, AttendancePunch, AttendanceStatus
from core.models import AuditLog
from tests.factories import AdminFactory, ComputerFactory, EmployeeFactory

DHAKA = dt.timezone(dt.timedelta(hours=6))
User = get_user_model()

# Long enough to satisfy the deploy check's own minimum-entropy rule, so a test of the
# production configuration is not quietly testing a configuration nobody would ship.
REALISTIC_SECRET_KEY = "k7Qx2mVpZ9dLr4Tn8sWbEyH3gJuC6aFo1iN5tRvXqM0zPlSdKw"

# A valid Fernet key, required in production the same way DJANGO_SECRET_KEY is.
REALISTIC_VAULT_ENCRYPTION_KEY = "jzmHUs1_LoWrALAvo5r1NnzCrKic-iWOkrOM6IhYSuQ="


@pytest.fixture
def office(db):
    settings_obj = AppSettings.load()
    settings_obj.timezone = "Asia/Dhaka"
    settings_obj.activity_retention_days = 90
    settings_obj.save()
    return settings_obj


def session(employee, computer, start, end, activity_type=ActivityType.ACTIVE):
    return Activity.objects.create(
        employee=employee,
        computer=computer,
        activity_type=activity_type,
        start_time=start,
        end_time=end,
        duration_seconds=int((end - start).total_seconds()) if end else 0,
    )


def days_ago(days, hour=10):
    return timezone.now().astimezone(DHAKA).replace(
        hour=hour, minute=0, second=0, microsecond=0
    ) - dt.timedelta(days=days)


# --- Retention window -------------------------------------------------------


class TestRetentionCutoff:
    def test_cutoff_is_a_whole_number_of_office_local_days(self, office):
        """ "We keep the last 90 days" must not mean something different at 02:00."""
        morning = dt.datetime(2026, 8, 19, 3, 0, tzinfo=dt.timezone.utc)  # 09:00 Dhaka
        evening = dt.datetime(2026, 8, 19, 17, 0, tzinfo=dt.timezone.utc)  # 23:00 Dhaka

        assert retention_cutoff(office, morning) == retention_cutoff(office, evening)

    def test_cutoff_is_the_configured_number_of_days_back(self, office):
        office.activity_retention_days = 30
        now = dt.datetime(2026, 8, 19, 6, 0, tzinfo=dt.timezone.utc)
        cutoff, days = retention_cutoff(office, now)

        assert days == 30
        # 30 days before 2026-08-19 is 2026-07-20; midnight in Dhaka is 18:00 UTC prior.
        assert cutoff == dt.datetime(2026, 7, 19, 18, 0, tzinfo=dt.timezone.utc)

    def test_a_window_below_the_floor_is_raised_to_it(self, office):
        """A settings row edited straight in the database must not wipe everything."""
        office.activity_retention_days = 1
        _, days = retention_cutoff(office)
        assert days == MINIMUM_RETENTION_DAYS


# --- What is and is not eligible --------------------------------------------


@pytest.mark.django_db
class TestEligibility:
    @pytest.fixture
    def setup(self, office):
        employee = EmployeeFactory()
        return employee, ComputerFactory(employee=employee)

    def test_a_session_that_ended_before_the_cutoff_is_eligible(self, office, setup):
        employee, computer = setup
        old = session(employee, computer, days_ago(200), days_ago(200) + dt.timedelta(hours=1))

        cutoff, _ = retention_cutoff(office)
        assert list(expired_activity(cutoff)) == [old]

    def test_a_session_inside_the_window_is_not(self, office, setup):
        employee, computer = setup
        session(employee, computer, days_ago(10), days_ago(10) + dt.timedelta(hours=1))

        cutoff, _ = retention_cutoff(office)
        assert expired_activity(cutoff).count() == 0

    def test_a_session_straddling_the_cutoff_is_kept(self, office, setup):
        """It is partly inside the window people were promised. Deleting it shortens
        their history by an amount nobody asked for."""
        employee, computer = setup
        cutoff, _ = retention_cutoff(office)
        session(employee, computer, cutoff - dt.timedelta(hours=2), cutoff + dt.timedelta(hours=2))

        assert expired_activity(cutoff).count() == 0

    def test_an_open_session_is_never_eligible(self, office, setup):
        """It has not ended, so there is no end date to judge it by — however old its
        start is."""
        employee, computer = setup
        Activity.objects.create(
            employee=employee,
            computer=computer,
            activity_type=ActivityType.PC_ON,
            start_time=days_ago(400),
            end_time=None,
        )

        cutoff, _ = retention_cutoff(office)
        assert expired_activity(cutoff).count() == 0


# --- The job ----------------------------------------------------------------


@pytest.mark.django_db
class TestPurge:
    @pytest.fixture
    def seeded(self, office):
        employee = EmployeeFactory()
        computer = ComputerFactory(employee=employee)
        for age in (400, 300, 200):
            session(employee, computer, days_ago(age), days_ago(age) + dt.timedelta(hours=1))
        for age in (30, 10, 1):
            session(employee, computer, days_ago(age), days_ago(age) + dt.timedelta(hours=1))
        return employee, computer

    def test_it_deletes_only_what_is_outside_the_window(self, office, seeded):
        result = purge_activity()

        assert result["deleted"] == 3
        assert Activity.objects.count() == 3
        cutoff, _ = retention_cutoff(office)
        assert all(row.end_time >= cutoff for row in Activity.objects.all())

    def test_a_dry_run_deletes_nothing_and_reports_the_same_count(self, office, seeded):
        dry = purge_activity(dry_run=True)

        assert dry["eligible"] == 3
        assert dry["deleted"] == 0
        assert Activity.objects.count() == 6

        # What the dry run promised is what the real run does.
        assert purge_activity()["deleted"] == dry["eligible"]

    def test_attendance_and_leave_are_never_touched(self, office, seeded):
        """A6: attendance is a business record, not surveillance data."""
        employee, _ = seeded
        record = Attendance.objects.create(
            employee=employee,
            date=dt.date(2024, 1, 15),  # far older than any retention window
            first_check_in_at=days_ago(600),
            last_check_out_at=days_ago(600) + dt.timedelta(hours=8),
            worked_seconds=8 * 3600,
            status=AttendanceStatus.PRESENT,
        )
        AttendancePunch.objects.create(
            attendance=record,
            sequence=1,
            check_in_at=days_ago(600),
            check_out_at=days_ago(600) + dt.timedelta(hours=8),
        )
        leave_before = employee.leave_used

        purge_activity()

        assert Attendance.objects.filter(pk=record.pk).exists()
        assert AttendancePunch.objects.filter(attendance=record).count() == 1
        employee.refresh_from_db()
        assert employee.leave_used == leave_before

    def test_every_run_is_audited_including_one_that_deleted_nothing(self, office):
        """ "The job ran and found nothing" and "the job did not run" must not look
        identical in the audit trail."""
        purge_activity()

        entry = AuditLog.objects.get(action=AuditLog.Action.ACTIVITY_PURGED)
        assert entry.payload["deleted"] == 0
        assert entry.payload["retention_days"] == 90
        assert entry.payload["dry_run"] is False
        assert "cutoff" in entry.payload

    def test_the_audit_entry_records_how_much_was_destroyed(self, office, seeded):
        purge_activity()

        entry = AuditLog.objects.filter(action=AuditLog.Action.ACTIVITY_PURGED).first()
        assert entry.payload["eligible"] == 3
        assert entry.payload["deleted"] == 3

    def test_a_dry_run_is_audited_as_a_dry_run(self, office, seeded):
        purge_activity(dry_run=True)

        entry = AuditLog.objects.filter(action=AuditLog.Action.ACTIVITY_PURGED).first()
        assert entry.payload["dry_run"] is True
        assert entry.payload["deleted"] == 0

    def test_deletion_batches_cover_everything(self, office, monkeypatch):
        """More rows than one batch must still all go."""
        import activities.retention as retention

        monkeypatch.setattr(retention, "BATCH_SIZE", 2)
        employee = EmployeeFactory()
        computer = ComputerFactory(employee=employee)
        for index in range(7):
            start = days_ago(200) + dt.timedelta(minutes=index * 10)
            session(employee, computer, start, start + dt.timedelta(minutes=5))

        assert retention.purge_activity()["deleted"] == 7
        assert Activity.objects.count() == 0


@pytest.mark.django_db
class TestPurgeCommand:
    def test_the_command_runs_and_reports(self, office, capsys):
        employee = EmployeeFactory()
        computer = ComputerFactory(employee=employee)
        session(employee, computer, days_ago(200), days_ago(200) + dt.timedelta(hours=1))

        call_command("purge_activity", "--dry-run")
        assert Activity.objects.count() == 1

        call_command("purge_activity")
        assert Activity.objects.count() == 0

    def test_a_days_override_below_the_floor_is_refused(self, office):
        with pytest.raises(CommandError):
            call_command("purge_activity", "--days", "1")

    def test_a_days_override_does_not_become_the_configured_policy(self, office):
        employee = EmployeeFactory()
        computer = ComputerFactory(employee=employee)
        session(employee, computer, days_ago(40), days_ago(40) + dt.timedelta(hours=1))

        call_command("purge_activity", "--days", "30")

        assert Activity.objects.count() == 0
        office.refresh_from_db()
        assert office.activity_retention_days == 90


# --- Shortening the window (D5) ---------------------------------------------


@pytest.mark.django_db
class TestRetentionSettingGuard:
    @pytest.fixture
    def admin_client(self, office):
        client = APIClient()
        client.force_authenticate(user=AdminFactory())
        return client

    def test_shortening_retention_needs_confirmation(self, admin_client):
        response = admin_client.patch("/api/settings/", {"activity_retention_days": 30})

        assert response.status_code == 400
        assert "confirm_shorter_retention" in str(response.data)
        assert AppSettings.load().activity_retention_days == 90

    def test_shortening_retention_succeeds_when_confirmed(self, admin_client):
        response = admin_client.patch(
            "/api/settings/",
            {"activity_retention_days": 30, "confirm_shorter_retention": True},
        )

        assert response.status_code == 200
        assert AppSettings.load().activity_retention_days == 30

    def test_lengthening_retention_needs_no_confirmation(self, admin_client):
        """Keeping data longer destroys nothing, so it is not a confirmed action."""
        assert (
            admin_client.patch("/api/settings/", {"activity_retention_days": 180}).status_code
            == 200
        )

    def test_a_window_below_the_enforced_minimum_is_refused_outright(self, admin_client):
        response = admin_client.patch(
            "/api/settings/",
            {"activity_retention_days": 1, "confirm_shorter_retention": True},
        )
        assert response.status_code == 400


# --- Passwords (§30) --------------------------------------------------------


@pytest.mark.django_db
class TestPasswordHandling:
    def test_passwords_are_hashed_with_argon2_and_never_stored_as_given(self, settings):
        # conftest swaps in MD5 to keep the suite fast. This is the one test that has to
        # see what production actually does, so it puts the real list back.
        import config.settings as production

        settings.PASSWORD_HASHERS = production.PASSWORD_HASHERS
        user = User.objects.create_user(email="hash@example.com", password="correct-horse-42")

        assert user.password != "correct-horse-42"
        assert "correct-horse-42" not in user.password
        assert identify_hasher(user.password).algorithm == "argon2"
        assert user.check_password("correct-horse-42")

    def test_a_short_password_is_refused_by_the_validators(self):
        from django.contrib.auth.password_validation import validate_password
        from django.core.exceptions import ValidationError

        with pytest.raises(ValidationError):
            validate_password("short1!")

    def test_a_common_password_is_refused(self):
        from django.contrib.auth.password_validation import validate_password
        from django.core.exceptions import ValidationError

        with pytest.raises(ValidationError):
            validate_password("password123")


# --- Deployment configuration ------------------------------------------------


class TestDeploymentGuards:
    """The failures here are silent ones: the system starts, looks fine, and is not."""

    def _load_settings(self, monkeypatch, **env):
        """Evaluate settings.py fresh under a given environment.

        Into a throwaway module rather than reloading `config.settings` in place: the
        real one is what every other test in the process reads, and a reload under
        `DEBUG=false` would leave the suite running against production settings — or,
        for the cases below that are *supposed* to raise, leave it with no settings at
        all.
        """
        for key, value in env.items():
            monkeypatch.setenv(key, value)

        import config.settings as installed

        spec = importlib.util.spec_from_file_location("config._settings_probe", installed.__file__)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_a_placeholder_secret_key_is_fatal_in_production(self, monkeypatch):
        with pytest.raises(RuntimeError, match="placeholder"):
            self._load_settings(
                monkeypatch,
                DJANGO_DEBUG="false",
                DJANGO_SECRET_KEY="change-me-in-production",
            )

    def test_a_missing_secret_key_is_fatal_in_production(self, monkeypatch):
        monkeypatch.delenv("DJANGO_SECRET_KEY", raising=False)
        with pytest.raises(RuntimeError, match="DJANGO_SECRET_KEY"):
            self._load_settings(monkeypatch, DJANGO_DEBUG="false")

    def test_production_defaults_are_secure_without_any_configuration(self, monkeypatch, tmp_path):
        """A deploy that sets only DEBUG and a key must still be hardened."""
        settings_module = self._load_settings(
            monkeypatch,
            DJANGO_DEBUG="false",
            DJANGO_SECRET_KEY=REALISTIC_SECRET_KEY,
            VAULT_ENCRYPTION_KEY=REALISTIC_VAULT_ENCRYPTION_KEY,
            SCREENSHOT_STORAGE_ROOT=str(tmp_path / "screenshots"),
        )

        assert settings_module.SESSION_COOKIE_SECURE is True
        assert settings_module.CSRF_COOKIE_SECURE is True
        assert settings_module.SECURE_SSL_REDIRECT is True
        assert settings_module.SECURE_HSTS_SECONDS == 31_536_000
        assert settings_module.SECURE_HSTS_INCLUDE_SUBDOMAINS is True
        # Preload is close to irreversible and stays an explicit decision.
        assert settings_module.SECURE_HSTS_PRELOAD is False
        assert settings_module.SECURE_PROXY_SSL_HEADER == ("HTTP_X_FORWARDED_PROTO", "https")

    def test_hsts_can_be_disabled_for_a_first_deploy(self, monkeypatch, tmp_path):
        """A wrong HSTS header is remembered by every visitor and cannot be withdrawn."""
        settings_module = self._load_settings(
            monkeypatch,
            DJANGO_DEBUG="false",
            DJANGO_SECRET_KEY=REALISTIC_SECRET_KEY,
            VAULT_ENCRYPTION_KEY=REALISTIC_VAULT_ENCRYPTION_KEY,
            SCREENSHOT_STORAGE_ROOT=str(tmp_path / "screenshots"),
            DJANGO_SECURE_HSTS_SECONDS="0",
        )
        assert settings_module.SECURE_HSTS_SECONDS == 0

    def test_django_deploy_checks_pass_in_a_production_configuration(self, monkeypatch, tmp_path):
        """`manage.py check --deploy` is the check nobody remembers to run."""
        from django.core.management import call_command
        from django.test import override_settings

        settings_module = self._load_settings(
            monkeypatch,
            DJANGO_DEBUG="false",
            DJANGO_SECRET_KEY=REALISTIC_SECRET_KEY,
            VAULT_ENCRYPTION_KEY=REALISTIC_VAULT_ENCRYPTION_KEY,
            SCREENSHOT_STORAGE_ROOT=str(tmp_path / "screenshots"),
        )

        overrides = {
            name: getattr(settings_module, name)
            for name in (
                "DEBUG",
                "SECRET_KEY",
                "SESSION_COOKIE_SECURE",
                "CSRF_COOKIE_SECURE",
                "SECURE_SSL_REDIRECT",
                "SECURE_HSTS_SECONDS",
                "SECURE_HSTS_INCLUDE_SUBDOMAINS",
                "SECURE_HSTS_PRELOAD",
                "SECURE_CONTENT_TYPE_NOSNIFF",
                "X_FRAME_OPTIONS",
                "SILENCED_SYSTEM_CHECKS",
            )
        }
        overrides["ALLOWED_HOSTS"] = ["office.example.com"]

        with override_settings(**overrides):
            # Raises SystemCheckError on any deploy warning that has not been silenced
            # with a documented reason in settings.py.
            call_command("check", "--deploy", "--fail-level", "WARNING")


# --- Rate limiting (§30) ----------------------------------------------------


@pytest.mark.django_db
class TestRateLimiting:
    def test_login_is_throttled_far_harder_than_anything_else(self):
        """Login is the one endpoint where brute forcing is useful."""
        client = APIClient()
        statuses = []
        for _ in range(12):
            response = client.post(
                "/api/auth/login/",
                {"email": "nobody@example.com", "password": "wrong-password"},
                format="json",
            )
            statuses.append(response.status_code)

        assert 429 in statuses
        assert statuses.index(429) <= 10
