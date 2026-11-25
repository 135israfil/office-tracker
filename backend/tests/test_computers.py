"""Phase 4: computer enrolment, device tokens, heartbeats and offline inference.

The two things worth the most test effort here are the credential path — a device token
must never be readable after registration, and a code must never work twice — and the
offline inference, because it is the only part of PC tracking that has to be right when
nothing is reporting.
"""

import datetime as dt

import pytest
from django.conf import settings
from django.core.management import call_command
from django.utils import timezone
from rest_framework.test import APIClient

from activities.models import Activity, ActivityType
from attendance.models import AppSettings
from computers.models import (
    Computer,
    ComputerStatus,
    DeviceType,
    generate_enrollment_code,
    hash_token,
    normalise_code,
)
from computers.services import (
    ANDROID_HEARTBEAT_INTERVAL_SECONDS,
    MISSED_HEARTBEATS_BEFORE_OFFLINE,
    RegistrationError,
    offline_after,
    record_heartbeat,
    record_mobile_heartbeat,
    register_device,
    sweep_offline_computers,
)
from core.models import AuditLog
from employees.models import EmployeeStatus
from tests.factories import AdminFactory, ComputerFactory, EmployeeFactory


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


def device_client(token):
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Device {token}")
    return client


def enrol(employee, **kwargs):
    """A computer with a live enrollment code, as the admin API would leave it."""
    computer = ComputerFactory(employee=employee, **kwargs)
    code = computer.issue_enrollment_code()
    computer.save()
    return computer, code


# --- Codes and tokens -------------------------------------------------------


class TestCredentials:
    def test_generated_codes_avoid_ambiguous_characters(self):
        for _ in range(50):
            code = generate_enrollment_code()
            # Nobody should ever have to decide whether that was a zero or an O.
            assert not set(code) & set("01ILOU")
            assert code.count("-") == 1

    def test_code_normalisation_accepts_what_people_type(self):
        assert normalise_code("abcde-fghjk") == "ABCDEFGHJK"
        assert normalise_code(" ABCDE FGHJK ") == "ABCDEFGHJK"
        assert normalise_code("") == ""

    def test_token_is_stored_only_as_a_hash(self, db):
        employee = EmployeeFactory()
        computer, code = enrol(employee)
        computer, token = register_device(enrollment_code=code, computer_name="DEV-PC-01")

        computer.refresh_from_db()
        assert computer.device_token_hash == hash_token(token)
        assert token not in computer.device_token_hash
        # Nothing anywhere on the row can be turned back into the token.
        stored = " ".join(str(value) for value in computer.__dict__.values())
        assert token not in stored


# --- Registration -----------------------------------------------------------


@pytest.mark.django_db
class TestRegistration:
    def test_registration_consumes_the_code_and_returns_a_token_once(self):
        employee = EmployeeFactory()
        computer, code = enrol(employee)

        response = APIClient().post(
            "/api/agent/register/",
            {
                "enrollment_code": code.lower(),  # agents may send what the user typed
                "computer_name": "DEV-PC-01",
                "operating_system": "Windows 11",
                "agent_version": "0.1.0",
            },
        )
        assert response.status_code == 201
        body = response.json()
        assert body["device_token"]
        assert body["computer"]["employee_name"] == employee.name
        assert body["config"]["heartbeat_interval_seconds"] == 60

        computer.refresh_from_db()
        assert computer.is_registered
        assert computer.enrollment_code is None
        assert computer.computer_name == "DEV-PC-01"
        assert computer.operating_system == "Windows 11"
        # Registered but never heard from is not the same as online.
        assert computer.status == ComputerStatus.OFFLINE

    def test_replaying_a_used_code_is_refused(self):
        computer, code = enrol(EmployeeFactory())
        client = APIClient()
        assert client.post("/api/agent/register/", {"enrollment_code": code}).status_code == 201

        second = client.post("/api/agent/register/", {"enrollment_code": code})
        assert second.status_code == 400
        assert "already-used" in second.json()["detail"]

    def test_expired_code_is_refused(self):
        computer, code = enrol(EmployeeFactory())
        computer.enrollment_expires_at = timezone.now() - dt.timedelta(minutes=1)
        computer.save(update_fields=["enrollment_expires_at"])

        response = APIClient().post("/api/agent/register/", {"enrollment_code": code})
        assert response.status_code == 400
        assert "expired" in response.json()["detail"]

    def test_unknown_code_is_refused(self):
        response = APIClient().post("/api/agent/register/", {"enrollment_code": "ZZZZZ-ZZZZZ"})
        assert response.status_code == 400

    def test_disabled_computer_cannot_be_registered(self):
        computer, code = enrol(EmployeeFactory())
        computer.status = ComputerStatus.DISABLED
        computer.save(update_fields=["status"])

        with pytest.raises(RegistrationError):
            register_device(enrollment_code=code)

    def test_registration_writes_an_audit_entry(self):
        computer, code = enrol(EmployeeFactory())
        APIClient().post("/api/agent/register/", {"enrollment_code": code})

        entry = AuditLog.objects.get(action=AuditLog.Action.DEVICE_REGISTERED)
        # No actor: the machine registered itself, nobody clicked anything.
        assert entry.actor is None
        assert entry.target_id == str(computer.pk)


# --- Device authentication --------------------------------------------------


@pytest.mark.django_db
class TestDeviceAuthentication:
    def test_valid_token_is_accepted(self):
        _, code = enrol(EmployeeFactory())
        token = (
            APIClient()
            .post("/api/agent/register/", {"enrollment_code": code})
            .json()["device_token"]
        )
        assert device_client(token).get("/api/agent/config/").status_code == 200

    def test_missing_and_invalid_tokens_are_rejected(self):
        assert APIClient().get("/api/agent/config/").status_code == 401
        assert device_client("not-a-real-token").get("/api/agent/config/").status_code == 401

    def test_disabled_device_is_rejected(self, admin_client):
        client, _ = admin_client
        computer, code = enrol(EmployeeFactory())
        token = (
            APIClient()
            .post("/api/agent/register/", {"enrollment_code": code})
            .json()["device_token"]
        )

        assert client.post(f"/api/computers/{computer.pk}/disable/").status_code == 200
        assert device_client(token).post("/api/agent/heartbeat/", {}).status_code == 401

    def test_device_of_an_inactive_employee_is_rejected(self, admin_client):
        client, _ = admin_client
        employee = EmployeeFactory()
        _, code = enrol(employee)
        token = (
            APIClient()
            .post("/api/agent/register/", {"enrollment_code": code})
            .json()["device_token"]
        )

        client.post(f"/api/employees/{employee.pk}/disable/")
        assert device_client(token).post("/api/agent/heartbeat/", {}).status_code == 401

    def test_device_token_does_not_unlock_the_web_api(self):
        employee = EmployeeFactory()
        _, code = enrol(employee)
        token = (
            APIClient()
            .post("/api/agent/register/", {"enrollment_code": code})
            .json()["device_token"]
        )
        client = device_client(token)

        # Device auth is not in DEFAULT_AUTHENTICATION_CLASSES, so these endpoints see
        # an anonymous request no matter what the header says.
        assert client.get("/api/employees/").status_code in (401, 403)
        assert client.get("/api/attendance/my/").status_code in (401, 403)

    def test_browser_session_cannot_post_heartbeats(self, employee_client):
        client, _ = employee_client
        assert client.post("/api/agent/heartbeat/", {}).status_code in (401, 403)


# --- Heartbeats and PC sessions ---------------------------------------------


@pytest.mark.django_db
class TestHeartbeat:
    def test_first_heartbeat_brings_the_pc_online_and_opens_a_session(self):
        employee = EmployeeFactory()
        _, code = enrol(employee)
        token = (
            APIClient()
            .post("/api/agent/register/", {"enrollment_code": code})
            .json()["device_token"]
        )

        response = device_client(token).post(
            "/api/agent/heartbeat/", {"state": "ONLINE", "event": "STARTUP"}
        )
        assert response.status_code == 200
        assert response.json()["status"] == ComputerStatus.ONLINE

        session = Activity.objects.get(activity_type=ActivityType.PC_ON)
        assert session.end_time is None
        assert session.employee_id == employee.pk

    def test_repeated_heartbeats_do_not_open_more_sessions(self):
        computer = ComputerFactory()
        for _ in range(3):
            record_heartbeat(computer)
        assert Activity.objects.filter(activity_type=ActivityType.PC_ON).count() == 1

    def test_idle_state_is_reflected_without_closing_the_session(self):
        computer = ComputerFactory()
        record_heartbeat(computer)
        record_heartbeat(computer, state=ComputerStatus.IDLE)

        computer.refresh_from_db()
        assert computer.status == ComputerStatus.IDLE
        assert Activity.objects.get(activity_type=ActivityType.PC_ON).end_time is None

    def test_shutdown_closes_the_session_and_marks_the_pc_offline(self):
        computer = ComputerFactory()
        start = timezone.now() - dt.timedelta(hours=8)
        record_heartbeat(computer, now=start)

        end = start + dt.timedelta(hours=8)
        record_heartbeat(computer, event="SHUTDOWN", now=end)

        computer.refresh_from_db()
        assert computer.status == ComputerStatus.OFFLINE
        session = Activity.objects.get(activity_type=ActivityType.PC_ON)
        assert session.end_time == end
        assert session.duration_seconds == 8 * 3600
        # Reported, not inferred: the agent told us.
        assert session.closed_by_server is False

    def test_sleep_closes_the_session_and_wake_starts_a_new_one(self):
        computer = ComputerFactory()
        record_heartbeat(computer)
        record_heartbeat(computer, event="SLEEP")
        record_heartbeat(computer, event="WAKE")

        sessions = Activity.objects.filter(activity_type=ActivityType.PC_ON).order_by("start_time")
        assert sessions.count() == 2
        assert sessions[0].end_time is not None
        assert sessions[1].end_time is None

    def test_startup_after_a_crash_closes_the_stale_session_at_the_last_heartbeat(self):
        computer = ComputerFactory()
        crash_time = timezone.now() - dt.timedelta(hours=5)
        record_heartbeat(computer, now=crash_time)  # last sign of life before the crash

        record_heartbeat(computer, event="STARTUP")

        sessions = Activity.objects.filter(activity_type=ActivityType.PC_ON).order_by("start_time")
        assert sessions.count() == 2
        # The old session ends when we last heard from it, not when the PC came back:
        # otherwise a crash at 13:00 and a reboot at 18:00 would claim five hours of use.
        assert sessions[0].end_time == crash_time
        assert sessions[0].closed_by_server is True

    def test_unknown_lifecycle_event_is_rejected_by_the_api(self):
        _, code = enrol(EmployeeFactory())
        token = (
            APIClient()
            .post("/api/agent/register/", {"enrollment_code": code})
            .json()["device_token"]
        )
        response = device_client(token).post("/api/agent/heartbeat/", {"event": "FORMAT_DISK"})
        assert response.status_code == 400

    def test_heartbeat_updates_the_reported_agent_version(self):
        computer = ComputerFactory(agent_version="0.1.0")
        record_heartbeat(computer, agent_version="0.2.0")
        computer.refresh_from_db()
        assert computer.agent_version == "0.2.0"


# --- Offline inference ------------------------------------------------------


@pytest.mark.django_db
class TestOfflineSweep:
    def test_silence_marks_the_pc_offline_and_closes_its_session_at_the_last_heartbeat(self):
        computer = ComputerFactory()
        last_seen = timezone.now() - dt.timedelta(minutes=30)
        record_heartbeat(computer, now=last_seen)

        result = sweep_offline_computers()

        computer.refresh_from_db()
        assert computer.status == ComputerStatus.OFFLINE
        assert result["marked_offline"] == 1
        session = Activity.objects.get(activity_type=ActivityType.PC_ON)
        assert session.end_time == last_seen
        assert session.closed_by_server is True

    def test_a_recent_heartbeat_is_left_alone(self):
        computer = ComputerFactory()
        record_heartbeat(computer)
        sweep_offline_computers()

        computer.refresh_from_db()
        assert computer.status == ComputerStatus.ONLINE
        assert Activity.objects.get(activity_type=ActivityType.PC_ON).end_time is None

    def test_threshold_follows_the_configured_heartbeat_interval(self):
        settings_obj = AppSettings.load()
        settings_obj.heartbeat_interval_seconds = 30
        settings_obj.save()

        computer = ComputerFactory()
        # Just inside three intervals: still considered alive.
        record_heartbeat(computer, now=timezone.now() - dt.timedelta(seconds=80))
        sweep_offline_computers()
        computer.refresh_from_db()
        assert computer.status == ComputerStatus.ONLINE

        # Just outside.
        record_heartbeat(
            computer,
            now=timezone.now() - dt.timedelta(seconds=30 * MISSED_HEARTBEATS_BEFORE_OFFLINE + 5),
        )
        sweep_offline_computers()
        computer.refresh_from_db()
        assert computer.status == ComputerStatus.OFFLINE

    def test_androids_window_is_longer_than_a_desktops(self):
        # The collector can only heartbeat every 15 minutes (WorkManager's floor), so its
        # window must outlast that gap, unlike the ~60s-interval desktop agent.
        settings_obj = AppSettings.load()
        assert offline_after(settings_obj, DeviceType.ANDROID) > dt.timedelta(
            seconds=ANDROID_HEARTBEAT_INTERVAL_SECONDS
        )
        assert offline_after(settings_obj, DeviceType.ANDROID) > offline_after(
            settings_obj, DeviceType.PC
        )

    def test_a_phone_heartbeat_within_its_own_window_is_left_alone(self):
        phone = ComputerFactory(device_type=DeviceType.ANDROID)
        # Past the desktop's ~3 minute window but well inside Android's own ~45 minutes.
        record_mobile_heartbeat(phone, now=timezone.now() - dt.timedelta(minutes=20))

        sweep_offline_computers()

        phone.refresh_from_db()
        assert phone.status == ComputerStatus.ONLINE

    def test_a_phone_past_its_own_window_is_marked_offline(self):
        phone = ComputerFactory(device_type=DeviceType.ANDROID)
        record_mobile_heartbeat(phone, now=timezone.now() - dt.timedelta(minutes=50))

        result = sweep_offline_computers()

        phone.refresh_from_db()
        assert phone.status == ComputerStatus.OFFLINE
        assert result["marked_offline"] == 1

    def test_sweep_does_not_resurrect_or_touch_disabled_computers(self):
        computer = ComputerFactory(status=ComputerStatus.DISABLED)
        computer.last_seen_at = timezone.now() - dt.timedelta(days=2)
        computer.save()

        sweep_offline_computers()
        computer.refresh_from_db()
        assert computer.status == ComputerStatus.DISABLED

    def test_management_command_reports_and_writes(self, capsys):
        computer = ComputerFactory()
        record_heartbeat(computer, now=timezone.now() - dt.timedelta(hours=2))

        call_command("mark_offline_computers", "--dry-run")
        computer.refresh_from_db()
        assert computer.status == ComputerStatus.ONLINE  # dry run changed nothing

        call_command("mark_offline_computers")
        computer.refresh_from_db()
        assert computer.status == ComputerStatus.OFFLINE

    def test_admin_list_sweeps_before_answering(self, admin_client):
        client, _ = admin_client
        computer = ComputerFactory()
        record_heartbeat(computer, now=timezone.now() - dt.timedelta(hours=1))

        body = client.get("/api/computers/").json()
        # Without the sweep this row would still claim ONLINE, which is the one thing
        # the screen exists to tell the truth about.
        assert body["results"][0]["status"] == ComputerStatus.OFFLINE


# --- Admin API --------------------------------------------------------------


@pytest.mark.django_db
class TestComputerAdminApi:
    def test_admin_enrols_a_computer_and_gets_a_code(self, admin_client):
        client, admin = admin_client
        employee = EmployeeFactory()

        response = client.post(
            "/api/computers/", {"employee": employee.pk, "computer_name": "DEV-PC-01"}
        )
        assert response.status_code == 201
        body = response.json()
        assert body["enrollment_code"]
        assert body["is_registered"] is False
        assert body["status"] == ComputerStatus.OFFLINE

        assert AuditLog.objects.filter(action=AuditLog.Action.DEVICE_CREATED).exists()

    def test_employee_cannot_read_or_enrol_computers(self, employee_client):
        client, employee = employee_client
        assert client.get("/api/computers/").status_code == 403
        response = client.post(
            "/api/computers/", {"employee": employee.pk, "computer_name": "SNEAKY-PC"}
        )
        assert response.status_code == 403

    def test_computers_cannot_be_deleted(self, admin_client):
        client, _ = admin_client
        computer = ComputerFactory()
        assert client.delete(f"/api/computers/{computer.pk}/").status_code == 405

    def test_enrolling_for_an_inactive_employee_is_refused(self, admin_client):
        client, _ = admin_client
        employee = EmployeeFactory(status=EmployeeStatus.INACTIVE)
        response = client.post(
            "/api/computers/", {"employee": employee.pk, "computer_name": "OLD-PC"}
        )
        assert response.status_code == 400

    def test_duplicate_computer_name_for_one_employee_is_refused(self, admin_client):
        client, _ = admin_client
        employee = EmployeeFactory()
        client.post("/api/computers/", {"employee": employee.pk, "computer_name": "DEV-PC-01"})
        second = client.post(
            "/api/computers/", {"employee": employee.pk, "computer_name": "DEV-PC-01"}
        )
        assert second.status_code == 400

    def test_issuing_a_new_code_leaves_an_existing_agent_working(self, admin_client):
        client, _ = admin_client
        computer, code = enrol(EmployeeFactory())
        token = (
            APIClient()
            .post("/api/agent/register/", {"enrollment_code": code})
            .json()["device_token"]
        )

        response = client.post(f"/api/computers/{computer.pk}/issue-code/")
        assert response.status_code == 200
        assert response.json()["enrollment_code"]
        # A rebuilt machine gets a new code; the machine still running keeps its token
        # until the new registration actually completes.
        assert device_client(token).get("/api/agent/config/").status_code == 200

    def test_disable_revokes_the_token_and_closes_the_session(self, admin_client):
        client, _ = admin_client
        computer, code = enrol(EmployeeFactory())
        token = (
            APIClient()
            .post("/api/agent/register/", {"enrollment_code": code})
            .json()["device_token"]
        )
        device_client(token).post("/api/agent/heartbeat/", {})

        client.post(f"/api/computers/{computer.pk}/disable/")

        computer.refresh_from_db()
        assert computer.status == ComputerStatus.DISABLED
        assert computer.device_token_hash is None
        assert Activity.objects.get(activity_type=ActivityType.PC_ON).end_time is not None
        assert AuditLog.objects.filter(action=AuditLog.Action.DEVICE_DISABLED).exists()

    def test_enable_requires_re_enrolment(self, admin_client):
        client, _ = admin_client
        computer = ComputerFactory(status=ComputerStatus.DISABLED)

        response = client.post(f"/api/computers/{computer.pk}/enable/")
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == ComputerStatus.OFFLINE
        # A disabled machine was disabled for a reason; it comes back through the front
        # door with a fresh code rather than resuming on its old credential.
        assert body["enrollment_code"]

        computer.refresh_from_db()
        assert computer.device_token_hash is None

    def test_double_disable_and_double_enable_are_refused(self, admin_client):
        client, _ = admin_client
        computer = ComputerFactory()
        assert client.post(f"/api/computers/{computer.pk}/enable/").status_code == 400
        assert client.post(f"/api/computers/{computer.pk}/disable/").status_code == 200
        assert client.post(f"/api/computers/{computer.pk}/disable/").status_code == 400

    def test_list_filters(self, admin_client):
        client, _ = admin_client
        alice = EmployeeFactory()
        ComputerFactory(employee=alice, computer_name="ALICE-PC")
        ComputerFactory(computer_name="BOB-PC")

        by_employee = client.get(f"/api/computers/?employee={alice.pk}").json()
        assert [row["computer_name"] for row in by_employee["results"]] == ["ALICE-PC"]

        by_search = client.get("/api/computers/?search=bob").json()
        assert [row["computer_name"] for row in by_search["results"]] == ["BOB-PC"]


# --- Config -----------------------------------------------------------------


@pytest.mark.django_db
class TestAgentConfig:
    def test_config_reflects_admin_settings_including_the_kill_switch(self, admin_client):
        client, _ = admin_client
        _, code = enrol(EmployeeFactory())
        token = (
            APIClient()
            .post("/api/agent/register/", {"enrollment_code": code})
            .json()["device_token"]
        )

        before = device_client(token).get("/api/agent/config/").json()
        assert before["enabled"] is True
        assert before["idle_threshold_seconds"] == 300

        client.patch(
            "/api/settings/", {"idle_threshold_seconds": 600, "agent_enabled": False}, format="json"
        )

        after = device_client(token).get("/api/agent/config/").json()
        assert after["idle_threshold_seconds"] == 600
        assert after["enabled"] is False
        # Changing settings must be detectable without diffing every field.
        assert after["config_version"] > before["config_version"]

    def test_heartbeat_response_carries_the_same_config(self):
        _, code = enrol(EmployeeFactory())
        token = (
            APIClient()
            .post("/api/agent/register/", {"enrollment_code": code})
            .json()["device_token"]
        )
        client = device_client(token)

        config = client.get("/api/agent/config/").json()
        heartbeat = client.post("/api/agent/heartbeat/", {}).json()["config"]
        assert heartbeat["idle_threshold_seconds"] == config["idle_threshold_seconds"]
        assert heartbeat["heartbeat_interval_seconds"] == config["heartbeat_interval_seconds"]


# --- Throttling -------------------------------------------------------------


@pytest.mark.django_db
class TestAgentThrottling:
    def test_registration_is_rate_limited_per_client(self):
        """Registration is unauthenticated, so the code itself is the credential.

        The limit is not what makes guessing hopeless — a single-use, expiring
        ten-character code already is — but an unthrottled unauthenticated endpoint is
        an invitation, and this asserts the scope is actually wired up rather than
        merely declared.
        """
        client = APIClient()
        limit = int(
            settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]["agent-register"].split("/")[0]
        )

        statuses = {
            client.post("/api/agent/register/", {"enrollment_code": "ZZZZZ-ZZZZZ"}).status_code
            for _ in range(limit + 1)
        }
        assert 429 in statuses


# --- Session arithmetic -----------------------------------------------------


@pytest.mark.django_db
class TestActivitySession:
    def test_backwards_clock_cannot_produce_a_negative_duration(self):
        computer = ComputerFactory()
        start = timezone.now()
        session = Activity.objects.create(
            employee=computer.employee,
            computer=computer,
            activity_type=ActivityType.PC_ON,
            start_time=start,
        )

        session.close(start - dt.timedelta(minutes=10))
        assert session.duration_seconds == 0
        assert session.end_time == start

    def test_client_event_id_is_unique_per_computer(self):
        computer = ComputerFactory()
        first = Activity.objects.create(
            employee=computer.employee,
            computer=computer,
            activity_type=ActivityType.PC_ON,
            start_time=timezone.now(),
        )
        # The same event id on a different machine is fine; on the same machine it is
        # the duplicate that sync is designed to swallow.
        other = ComputerFactory()
        Activity.objects.create(
            employee=other.employee,
            computer=other,
            activity_type=ActivityType.PC_ON,
            start_time=timezone.now(),
            client_event_id=first.client_event_id,
        )

        with pytest.raises(Exception):  # noqa: B017 - IntegrityError type varies by backend
            Activity.objects.create(
                employee=computer.employee,
                computer=computer,
                activity_type=ActivityType.PC_ON,
                start_time=timezone.now(),
                client_event_id=first.client_event_id,
            )


@pytest.mark.django_db
def test_registered_computer_reports_its_employee_and_name():
    employee = EmployeeFactory(name="Rahim Ahmed")
    computer = ComputerFactory(employee=employee, computer_name="DEV-PC-01")
    assert str(computer) == "DEV-PC-01 (Rahim Ahmed)"
    assert Computer.objects.filter(employee=employee).count() == 1
