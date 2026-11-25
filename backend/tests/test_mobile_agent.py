"""Mobile (Android) agent endpoints: register, heartbeat, sync, config.

No enrollment code and no device token here, unlike the desktop agent — every one of
these views is authenticated by the user's own bearer token (accounts.authentication.
BearerTokenAuthentication) and resolves its Computer row via get_or_create_mobile_device,
so the single theme worth testing on its own is: the phone's own login is the only trust
boundary, and it behaves like one (one row per employee, disable actually blocks it,
logging out actually blocks it).
"""

import datetime as dt
import uuid

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from activities.models import Activity, ActivityType
from computers.models import Computer, ComputerStatus, DeviceType
from tests.factories import ComputerFactory, EmployeeFactory, UserFactory

PASSWORD = "test-password-123"


def bearer_client(employee):
    token = (
        APIClient()
        .post("/api/auth/token/", {"email": employee.user.email, "password": PASSWORD})
        .json()["token"]
    )
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    return client


@pytest.mark.django_db
class TestMobileRegister:
    def test_first_call_creates_an_android_computer_row(self):
        employee = EmployeeFactory()
        client = bearer_client(employee)

        response = client.post(
            "/api/agent/mobile/register/",
            {"computer_name": "Pixel 8 Pro", "operating_system": "Android 15"},
        )

        assert response.status_code == 201
        computer = Computer.objects.get()
        assert computer.employee_id == employee.pk
        assert computer.device_type == DeviceType.ANDROID
        assert computer.computer_name == "Pixel 8 Pro"
        assert response.json()["computer"]["employee_name"] == employee.name

    def test_a_second_call_reuses_the_same_row_instead_of_duplicating(self):
        """A reinstalled app logging in again must not pile up Computer rows."""
        employee = EmployeeFactory()
        client = bearer_client(employee)
        client.post("/api/agent/mobile/register/", {"computer_name": "Pixel 8 Pro"})
        client.post("/api/agent/mobile/register/", {"computer_name": "Pixel 8 Pro (renamed)"})

        assert (
            Computer.objects.filter(employee=employee, device_type=DeviceType.ANDROID).count() == 1
        )
        assert Computer.objects.get().computer_name == "Pixel 8 Pro (renamed)"

    def test_a_pc_and_a_phone_for_the_same_employee_are_separate_rows(self):
        employee = EmployeeFactory()
        ComputerFactory(employee=employee)  # the PC
        client = bearer_client(employee)

        client.post("/api/agent/mobile/register/", {})

        assert Computer.objects.filter(employee=employee).count() == 2
        assert Computer.objects.filter(employee=employee, device_type=DeviceType.PC).count() == 1
        assert (
            Computer.objects.filter(employee=employee, device_type=DeviceType.ANDROID).count() == 1
        )

    def test_an_account_with_no_linked_employee_is_refused(self):
        user = UserFactory()  # no Employee attached
        token = (
            APIClient()
            .post("/api/auth/token/", {"email": user.email, "password": PASSWORD})
            .json()["token"]
        )
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

        response = client.post("/api/agent/mobile/register/", {})
        assert response.status_code == 400

    def test_unauthenticated_is_refused(self):
        assert APIClient().post("/api/agent/mobile/register/", {}).status_code == 401

    def test_a_disabled_phone_refuses_re_registration(self):
        employee = EmployeeFactory()
        client = bearer_client(employee)
        client.post("/api/agent/mobile/register/", {})
        Computer.objects.filter(employee=employee).update(status=ComputerStatus.DISABLED)

        response = client.post("/api/agent/mobile/register/", {})
        assert response.status_code == 400


@pytest.mark.django_db
class TestMobileHeartbeat:
    def test_heartbeat_marks_the_phone_online_and_stamps_last_seen(self):
        employee = EmployeeFactory()
        client = bearer_client(employee)

        response = client.post("/api/agent/mobile/heartbeat/", {})

        assert response.status_code == 200
        computer = Computer.objects.get()
        assert computer.status == ComputerStatus.ONLINE
        assert computer.last_seen_at is not None

    def test_heartbeat_opens_no_pc_on_session(self):
        """A phone has no PC_ON-style liveness session — Android's own ACTIVE/IDLE
        sessions already say when it was in use (see record_mobile_heartbeat)."""
        employee = EmployeeFactory()
        client = bearer_client(employee)
        client.post("/api/agent/mobile/heartbeat/", {})
        assert not Activity.objects.filter(activity_type=ActivityType.PC_ON).exists()

    def test_a_disabled_phone_cannot_heartbeat(self):
        employee = EmployeeFactory()
        client = bearer_client(employee)
        client.post("/api/agent/mobile/register/", {})
        Computer.objects.filter(employee=employee).update(status=ComputerStatus.DISABLED)

        assert client.post("/api/agent/mobile/heartbeat/", {}).status_code == 400


@pytest.mark.django_db
class TestMobileSync:
    def _session_payload(self, **overrides):
        start = timezone.now() - dt.timedelta(minutes=10)
        end = start + dt.timedelta(minutes=5)
        payload = {
            "client_event_id": str(uuid.uuid4()),
            "activity_type": ActivityType.ACTIVE,
            "start_time": start.isoformat(),
            "end_time": end.isoformat(),
        }
        payload.update(overrides)
        return payload

    def test_sessions_are_attributed_to_the_employees_own_phone(self):
        employee = EmployeeFactory()
        client = bearer_client(employee)

        response = client.post(
            "/api/agent/mobile/sync/", {"sessions": [self._session_payload()]}, format="json"
        )

        assert response.status_code == 200
        assert response.json()["accepted"] == 1
        stored = Activity.objects.get()
        assert stored.employee_id == employee.pk
        assert stored.computer.device_type == DeviceType.ANDROID

    def test_logging_out_stops_further_sync(self):
        employee = EmployeeFactory()
        token = (
            APIClient()
            .post("/api/auth/token/", {"email": employee.user.email, "password": PASSWORD})
            .json()["token"]
        )
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        client.post("/api/agent/mobile/sync/", {"sessions": []}, format="json")

        client.post("/api/auth/token/revoke/")
        response = client.post("/api/agent/mobile/sync/", {"sessions": []}, format="json")
        assert response.status_code == 401

    def test_a_disabled_phone_cannot_sync(self):
        employee = EmployeeFactory()
        client = bearer_client(employee)
        client.post("/api/agent/mobile/register/", {})
        Computer.objects.filter(employee=employee).update(status=ComputerStatus.DISABLED)

        response = client.post("/api/agent/mobile/sync/", {"sessions": []}, format="json")
        assert response.status_code == 400


@pytest.mark.django_db
class TestMobileConfig:
    def test_config_reflects_the_phones_own_computer_identity(self):
        employee = EmployeeFactory()
        client = bearer_client(employee)
        client.post("/api/agent/mobile/register/", {"computer_name": "Pixel 8 Pro"})

        body = client.get("/api/agent/mobile/config/").json()
        assert body["computer_name"] == "Pixel 8 Pro"
        assert body["employee_name"] == employee.name
