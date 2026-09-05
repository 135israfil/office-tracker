"""Phase 5: activity sync ingestion (§18, §19).

The property that matters most is idempotency. The agent marks a session synced only
after a 2xx, so every dropped response produces a replay — which is correct behaviour on
its side and only safe because ingestion here refuses to store the same
`client_event_id` twice for the same computer.

The second theme is that this is a trust boundary. Nothing about ownership comes from
the request body, timestamps are checked against the server's clock, and the domain
field is re-validated as a bare host even though the agent already truncated it.
"""

import datetime as dt
import uuid

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from activities.models import Activity, ActivityType
from activities.services import FUTURE_SKEW, MAX_SESSION_SECONDS, ingest_sessions
from computers.models import ComputerStatus
from tests.factories import AdminFactory, ComputerFactory, EmployeeFactory


def session_payload(**overrides):
    start = overrides.pop("start", timezone.now() - dt.timedelta(minutes=10))
    end = overrides.pop("end", start + dt.timedelta(minutes=5))
    payload = {
        "client_event_id": str(uuid.uuid4()),
        "activity_type": ActivityType.APPLICATION,
        "application_name": "Visual Studio Code",
        "executable_name": "Code.exe",
        "start_time": start.isoformat(),
        "end_time": end.isoformat(),
    }
    payload.update(overrides)
    return payload


def device_client(token):
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Device {token}")
    return client


@pytest.fixture
def enrolled(db):
    """A registered computer and a client carrying its token."""
    computer = ComputerFactory()
    code = computer.issue_enrollment_code()
    computer.save()
    token = (
        APIClient().post("/api/agent/register/", {"enrollment_code": code}).json()["device_token"]
    )
    computer.refresh_from_db()
    return computer, device_client(token)


@pytest.mark.django_db
class TestSyncEndpoint:
    def test_batch_is_stored_and_attributed_to_the_device_owner(self, enrolled):
        computer, client = enrolled
        body = {"sessions": [session_payload(), session_payload(activity_type=ActivityType.ACTIVE)]}

        response = client.post("/api/agent/sync/", body, format="json")
        assert response.status_code == 200
        assert response.json()["accepted"] == 2

        stored = Activity.objects.all()
        assert stored.count() == 2
        # Ownership comes from the token, never from the body.
        assert {row.employee_id for row in stored} == {computer.employee_id}
        assert {row.computer_id for row in stored} == {computer.pk}

    def test_duration_is_derived_from_the_timestamps(self, enrolled):
        _, client = enrolled
        start = timezone.now() - dt.timedelta(minutes=30)
        client.post(
            "/api/agent/sync/",
            {
                "sessions": [
                    session_payload(
                        start=start,
                        end=start + dt.timedelta(minutes=12),
                        # A client-supplied duration that disagrees with its own start
                        # and end is a bug report, not a data point — it is ignored.
                        duration_seconds=99999,
                    )
                ]
            },
            format="json",
        )
        assert Activity.objects.get().duration_seconds == 12 * 60

    def test_replaying_a_batch_stores_nothing_twice(self, enrolled):
        _, client = enrolled
        body = {"sessions": [session_payload(), session_payload()]}

        first = client.post("/api/agent/sync/", body, format="json").json()
        second = client.post("/api/agent/sync/", body, format="json").json()

        assert first["accepted"] == 2
        assert second["accepted"] == 0
        assert second["duplicates"] == 2
        assert Activity.objects.count() == 2

    def test_first_write_wins_on_a_replay(self, enrolled):
        """A retry with a drifted clock must not rewrite what is already stored."""
        _, client = enrolled
        event_id = str(uuid.uuid4())
        start = timezone.now() - dt.timedelta(hours=1)

        client.post(
            "/api/agent/sync/",
            {"sessions": [session_payload(client_event_id=event_id, start=start)]},
            format="json",
        )
        client.post(
            "/api/agent/sync/",
            {
                "sessions": [
                    session_payload(
                        client_event_id=event_id,
                        start=start,
                        end=start + dt.timedelta(minutes=45),
                        application_name="Something Else",
                    )
                ]
            },
            format="json",
        )

        stored = Activity.objects.get()
        assert stored.application_name == "Visual Studio Code"
        assert stored.duration_seconds == 5 * 60

    def test_the_same_event_id_from_another_computer_is_a_separate_session(self, enrolled):
        _, client = enrolled
        other = ComputerFactory()
        code = other.issue_enrollment_code()
        other.save()
        other_token = (
            APIClient()
            .post("/api/agent/register/", {"enrollment_code": code})
            .json()["device_token"]
        )

        payload = session_payload()
        client.post("/api/agent/sync/", {"sessions": [payload]}, format="json")
        device_client(other_token).post("/api/agent/sync/", {"sessions": [payload]}, format="json")

        # Uniqueness is per computer: two machines generating the same UUID is
        # vanishingly unlikely, but it must not silently discard one of their days.
        assert Activity.objects.count() == 2

    def test_one_bad_session_does_not_cost_the_batch(self, enrolled):
        _, client = enrolled
        good = session_payload()
        bad = session_payload(activity_type="APPLICATION", application_name="")

        result = client.post("/api/agent/sync/", {"sessions": [good, bad]}, format="json").json()

        assert result["accepted"] == 1
        assert len(result["rejected"]) == 1
        # Named individually so the agent can drop exactly that row instead of retrying
        # the whole batch forever.
        assert result["rejected"][0]["client_event_id"] == bad["client_event_id"]

    def test_empty_batch_is_accepted(self, enrolled):
        _, client = enrolled
        response = client.post("/api/agent/sync/", {"sessions": []}, format="json")
        assert response.status_code == 200
        assert response.json()["accepted"] == 0

    def test_oversized_batch_is_refused(self, enrolled):
        _, client = enrolled
        response = client.post(
            "/api/agent/sync/", {"sessions": [session_payload() for _ in range(501)]}, format="json"
        )
        assert response.status_code == 400

    def test_response_carries_the_current_config(self, enrolled):
        _, client = enrolled
        body = client.post("/api/agent/sync/", {"sessions": []}, format="json").json()
        assert body["config"]["heartbeat_interval_seconds"] == 60


@pytest.mark.django_db
class TestSyncAuthorisation:
    def test_unauthenticated_sync_is_rejected(self):
        assert (
            APIClient().post("/api/agent/sync/", {"sessions": []}, format="json").status_code == 401
        )

    def test_disabled_device_cannot_sync(self, enrolled):
        computer, client = enrolled
        admin = APIClient()
        admin.force_authenticate(user=AdminFactory())
        admin.post(f"/api/computers/{computer.pk}/disable/")

        response = client.post("/api/agent/sync/", {"sessions": [session_payload()]}, format="json")
        assert response.status_code == 401
        assert Activity.objects.count() == 0

    def test_browser_session_cannot_post_activity(self, db):
        employee = EmployeeFactory()
        client = APIClient()
        client.force_authenticate(user=employee.user)
        response = client.post("/api/agent/sync/", {"sessions": []}, format="json")
        assert response.status_code in (401, 403)

    def test_device_of_an_inactive_employee_cannot_sync(self, enrolled):
        computer, client = enrolled
        admin = APIClient()
        admin.force_authenticate(user=AdminFactory())
        admin.post(f"/api/employees/{computer.employee_id}/disable/")

        assert client.post("/api/agent/sync/", {"sessions": []}, format="json").status_code == 401


@pytest.mark.django_db
class TestIngestionRules:
    def test_pc_sessions_cannot_be_asserted_by_an_agent(self, enrolled):
        _, client = enrolled
        result = client.post(
            "/api/agent/sync/",
            {"sessions": [session_payload(activity_type=ActivityType.PC_ON)]},
            format="json",
        ).json()

        # PC on/off is derived from heartbeats. Letting a client assert it would let a
        # broken agent rewrite its own uptime.
        assert result["accepted"] == 0
        assert len(result["rejected"]) == 1

    def test_urls_are_refused_even_though_the_agent_truncates(self, enrolled):
        _, client = enrolled
        rejected = client.post(
            "/api/agent/sync/",
            {
                "sessions": [
                    session_payload(
                        activity_type=ActivityType.WEBSITE,
                        application_name="",
                        website_domain="example.com/private/account?id=123&token=xxx",
                    )
                ]
            },
            format="json",
        ).json()["rejected"]

        # §17. The agent truncates before sending; this is what happens if it ever stops.
        assert len(rejected) == 1
        assert Activity.objects.count() == 0

    def test_domain_is_normalised_and_the_port_dropped(self, enrolled):
        _, client = enrolled
        client.post(
            "/api/agent/sync/",
            {
                "sessions": [
                    session_payload(
                        activity_type=ActivityType.WEBSITE,
                        application_name="",
                        website_domain="GitHub.com:443",
                    )
                ]
            },
            format="json",
        )
        assert Activity.objects.get().website_domain == "github.com"

    def test_backwards_session_is_rejected(self, enrolled):
        _, client = enrolled
        start = timezone.now()
        result = client.post(
            "/api/agent/sync/",
            {"sessions": [session_payload(start=start, end=start - dt.timedelta(minutes=5))]},
            format="json",
        ).json()
        assert len(result["rejected"]) == 1

    def test_absurd_duration_is_clamped_rather_than_lost(self, db):
        computer = ComputerFactory()
        start = timezone.now() - dt.timedelta(days=1)
        result = ingest_sessions(
            computer,
            [session_payload(start=start, end=start + dt.timedelta(hours=9))],
        )

        assert result["accepted"] == 1
        assert result["clamped"] == 1
        # The agent caps its own sessions at 15 minutes, so nine hours means a clock
        # stepped or a builder failed to close. Clamping keeps the time rather than
        # discarding it entirely.
        assert Activity.objects.get().duration_seconds == MAX_SESSION_SECONDS

    def test_future_timestamps_are_pulled_back_to_now(self, db):
        computer = ComputerFactory()
        now = timezone.now()
        far_future = now + dt.timedelta(days=1)

        result = ingest_sessions(
            computer,
            [session_payload(start=far_future, end=far_future + dt.timedelta(minutes=5))],
            now=now,
        )

        assert result["accepted"] == 1
        stored = Activity.objects.get()
        # A PC whose clock is a day fast would otherwise file tomorrow's activity, where
        # no report would ever look for it.
        assert stored.start_time <= now + FUTURE_SKEW
        assert stored.end_time <= now + FUTURE_SKEW
        assert stored.duration_seconds == 5 * 60

    def test_ordinary_clock_skew_is_left_alone(self, db):
        computer = ComputerFactory()
        now = timezone.now()
        slightly_ahead = now + dt.timedelta(minutes=2)

        ingest_sessions(
            computer,
            [session_payload(start=slightly_ahead - dt.timedelta(minutes=5), end=slightly_ahead)],
            now=now,
        )
        # Two minutes of skew is a normal, unsynchronised PC — not something to correct.
        assert Activity.objects.get().end_time == slightly_ahead

    def test_parallel_tracks_may_cover_the_same_minute(self, db):
        computer = ComputerFactory()
        start = timezone.now() - dt.timedelta(minutes=20)
        end = start + dt.timedelta(minutes=10)

        ingest_sessions(
            computer,
            [
                session_payload(start=start, end=end, activity_type=ActivityType.ACTIVE),
                session_payload(start=start, end=end),
                session_payload(
                    start=start,
                    end=end,
                    activity_type=ActivityType.WEBSITE,
                    application_name="",
                    website_domain="github.com",
                ),
            ],
        )

        # §18: the tracks run in parallel and nothing sums across them. An ACTIVE, an
        # APPLICATION and a WEBSITE session covering one wall-clock minute is correct.
        assert Activity.objects.count() == 3

    def test_sync_does_not_change_liveness(self, enrolled):
        computer, client = enrolled
        client.post("/api/agent/sync/", {"sessions": [session_payload()]}, format="json")

        computer.refresh_from_db()
        # Liveness is the heartbeat's job. A batch uploaded after an outage says nothing
        # about whether the machine is on right now.
        assert computer.status == ComputerStatus.OFFLINE
        assert computer.last_seen_at is None
