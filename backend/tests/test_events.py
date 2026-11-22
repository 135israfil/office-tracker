"""Event calendar: the phase pure function, the same data-isolation exit
criterion test_dashboards.py enforces for activity data, and the
admin-visibility disclosure/audit-logging decisions from the design — with
one deliberate difference from test_vault.py: list must never log, only
retrieve.
"""

from __future__ import annotations

import datetime as dt

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from core.models import AuditLog
from events.models import EventPhase, event_phase
from tests.factories import AdminFactory, EmployeeFactory, EventFactory

# --- Pure logic ---------------------------------------------------------------


class TestEventPhase:
    def test_an_event_that_has_not_started_is_upcoming(self):
        now = dt.datetime(2026, 1, 1, 12, 0, tzinfo=dt.timezone.utc)
        start = dt.datetime(2026, 1, 2, 9, 0, tzinfo=dt.timezone.utc)
        assert event_phase(start, None, now) == EventPhase.UPCOMING

    def test_an_event_within_its_start_and_end_is_in_progress(self):
        now = dt.datetime(2026, 1, 1, 12, 0, tzinfo=dt.timezone.utc)
        start = dt.datetime(2026, 1, 1, 9, 0, tzinfo=dt.timezone.utc)
        end = dt.datetime(2026, 1, 1, 17, 0, tzinfo=dt.timezone.utc)
        assert event_phase(start, end, now) == EventPhase.IN_PROGRESS

    def test_an_event_past_its_end_is_past(self):
        now = dt.datetime(2026, 1, 2, 12, 0, tzinfo=dt.timezone.utc)
        start = dt.datetime(2026, 1, 1, 9, 0, tzinfo=dt.timezone.utc)
        end = dt.datetime(2026, 1, 1, 17, 0, tzinfo=dt.timezone.utc)
        assert event_phase(start, end, now) == EventPhase.PAST

    def test_a_point_in_time_event_with_no_end_is_past_once_its_start_has_passed(self):
        now = dt.datetime(2026, 1, 2, 12, 0, tzinfo=dt.timezone.utc)
        start = dt.datetime(2026, 1, 1, 9, 0, tzinfo=dt.timezone.utc)
        assert event_phase(start, None, now) == EventPhase.PAST

    def test_an_event_starting_exactly_now_with_no_end_is_past_not_in_progress(self):
        # No end means no "in progress" state is reachable at all.
        now = dt.datetime(2026, 1, 1, 9, 0, tzinfo=dt.timezone.utc)
        start = now
        assert event_phase(start, None, now) == EventPhase.PAST


# --- API: data isolation (mirrors TestEmployeeIsolation in test_dashboards.py) ---


@pytest.fixture
def admin_client(db):
    admin = AdminFactory()
    client = APIClient()
    client.force_authenticate(user=admin)
    return client, admin


def client_for(employee):
    client = APIClient()
    client.force_authenticate(user=employee.user)
    return client


@pytest.mark.django_db
class TestEventIsolation:
    def test_unauthenticated_is_refused(self):
        event = EventFactory()
        assert APIClient().get(f"/api/events/{event.pk}/").status_code == 403

    def test_an_uninvolved_employee_cannot_see_the_event(self):
        alice = EmployeeFactory()
        event = EventFactory()  # owned by someone else entirely
        response = client_for(alice).get(f"/api/events/{event.pk}/")
        assert response.status_code == 404

    def test_the_owner_sees_their_own_event(self):
        event = EventFactory()
        assert client_for(event.owner).get(f"/api/events/{event.pk}/").status_code == 200

    def test_a_grantee_who_is_not_the_owner_sees_the_event(self):
        bob = EmployeeFactory()
        event = EventFactory(grantees=[bob])
        assert client_for(bob).get(f"/api/events/{event.pk}/").status_code == 200

    def test_an_admin_sees_everything(self, admin_client):
        client, _ = admin_client
        event = EventFactory()
        assert client.get(f"/api/events/{event.pk}/").status_code == 200

    def test_an_owner_with_zero_grantees_still_sees_their_own_event_in_the_list(self):
        event = EventFactory()
        body = client_for(event.owner).get("/api/events/").json()
        assert body["count"] == 1

    def test_the_list_excludes_events_owned_by_someone_else(self):
        alice = EmployeeFactory()
        EventFactory()  # someone else's event
        body = client_for(alice).get("/api/events/").json()
        assert body["count"] == 0


# --- API: creating events -----------------------------------------------------


@pytest.mark.django_db
class TestCreate:
    def test_creating_an_event_stores_it_owned_by_the_creator(self):
        owner = EmployeeFactory()
        start = (timezone.now() + dt.timedelta(days=1)).isoformat()
        response = client_for(owner).post(
            "/api/events/", {"title": "Standup", "start": start}, format="json"
        )
        assert response.status_code == 201
        assert response.json()["owner"]["id"] == owner.id

    def test_an_event_ending_before_it_starts_is_rejected(self):
        owner = EmployeeFactory()
        start = timezone.now() + dt.timedelta(days=1)
        end = start - dt.timedelta(hours=1)
        response = client_for(owner).post(
            "/api/events/",
            {"title": "Bad event", "start": start.isoformat(), "end": end.isoformat()},
            format="json",
        )
        assert response.status_code == 400

    def test_a_newly_created_event_exposes_its_phase(self):
        owner = EmployeeFactory()
        start = (timezone.now() + dt.timedelta(days=1)).isoformat()
        response = client_for(owner).post(
            "/api/events/", {"title": "Standup", "start": start}, format="json"
        )
        assert response.json()["phase"] == EventPhase.UPCOMING


# --- API: retrieve-level admin audit logging (list must never log) ----------


@pytest.mark.django_db
class TestAdminViewAuditLogging:
    def test_the_owner_retrieving_their_own_event_is_never_logged(self):
        event = EventFactory()
        client_for(event.owner).get(f"/api/events/{event.pk}/")
        assert not AuditLog.objects.filter(action=AuditLog.Action.EVENT_VIEWED_BY_ADMIN).exists()

    def test_a_grantee_retrieving_a_shared_event_is_never_logged(self):
        bob = EmployeeFactory()
        event = EventFactory(grantees=[bob])
        client_for(bob).get(f"/api/events/{event.pk}/")
        assert not AuditLog.objects.filter(action=AuditLog.Action.EVENT_VIEWED_BY_ADMIN).exists()

    def test_an_admin_retrieving_a_non_shared_event_is_logged(self, admin_client):
        client, admin = admin_client
        event = EventFactory()
        response = client.get(f"/api/events/{event.pk}/")
        assert response.status_code == 200
        log = AuditLog.objects.get(action=AuditLog.Action.EVENT_VIEWED_BY_ADMIN)
        assert log.actor_id == admin.pk
        assert log.target_type == "Event"
        assert log.target_id == str(event.pk)

    def test_the_logged_admin_view_is_surfaced_back_to_the_owner(self, admin_client):
        client, _ = admin_client
        event = EventFactory()
        client.get(f"/api/events/{event.pk}/")
        detail = client_for(event.owner).get(f"/api/events/{event.pk}/").json()
        assert detail["last_admin_view"] is not None

    def test_an_admin_listing_events_never_logs_anything(self, admin_client):
        # The one place this feature's audit behavior deliberately differs
        # from the Vault's: browsing a calendar is routine, unlike revealing
        # a password, so list must never generate an audit entry.
        client, _ = admin_client
        EventFactory()
        EventFactory()
        response = client.get("/api/events/")
        assert response.status_code == 200
        assert not AuditLog.objects.filter(action=AuditLog.Action.EVENT_VIEWED_BY_ADMIN).exists()


# --- API: sharing and revoking -----------------------------------------------


@pytest.mark.django_db
class TestShareAndRevoke:
    def test_the_owner_can_share_with_another_employee(self):
        event = EventFactory()
        bob = EmployeeFactory()
        response = client_for(event.owner).post(
            f"/api/events/{event.pk}/share/", {"employee": bob.pk}, format="json"
        )
        assert response.status_code == 200
        assert [g["grantee"]["id"] for g in response.json()["grants"]] == [bob.pk]

    def test_sharing_response_itself_reflects_the_new_state(self):
        event = EventFactory()
        bob = EmployeeFactory()
        response = client_for(event.owner).post(
            f"/api/events/{event.pk}/share/", {"employee": bob.pk}, format="json"
        )
        assert len(response.json()["grants"]) == 1

    def test_sharing_with_an_already_shared_employee_is_rejected(self):
        bob = EmployeeFactory()
        event = EventFactory(grantees=[bob])
        response = client_for(event.owner).post(
            f"/api/events/{event.pk}/share/", {"employee": bob.pk}, format="json"
        )
        assert response.status_code == 400

    def test_a_grantee_cannot_share_the_event_further(self):
        bob = EmployeeFactory()
        carol = EmployeeFactory()
        event = EventFactory(grantees=[bob])
        response = client_for(bob).post(
            f"/api/events/{event.pk}/share/", {"employee": carol.pk}, format="json"
        )
        assert response.status_code == 403

    def test_the_owner_may_revoke_any_grantee(self):
        bob = EmployeeFactory()
        event = EventFactory(grantees=[bob])
        response = client_for(event.owner).delete(f"/api/events/{event.pk}/grants/{bob.pk}/")
        assert response.status_code == 200
        assert event.grants.count() == 0

    def test_the_revoke_response_itself_reflects_the_new_state(self):
        bob = EmployeeFactory()
        event = EventFactory(grantees=[bob])
        response = client_for(event.owner).delete(f"/api/events/{event.pk}/grants/{bob.pk}/")
        assert response.json()["grants"] == []

    def test_a_grantee_may_revoke_their_own_access(self):
        bob = EmployeeFactory()
        event = EventFactory(grantees=[bob])
        response = client_for(bob).delete(f"/api/events/{event.pk}/grants/{bob.pk}/")
        assert response.status_code == 200

    def test_a_grantee_cannot_revoke_another_grantees_access(self):
        bob = EmployeeFactory()
        carol = EmployeeFactory()
        event = EventFactory(grantees=[bob, carol])
        response = client_for(bob).delete(f"/api/events/{event.pk}/grants/{carol.pk}/")
        assert response.status_code == 403
        assert event.grants.filter(grantee=carol).exists()

    def test_revoking_an_employee_with_no_grant_is_a_404(self):
        event = EventFactory()
        alice = EmployeeFactory()
        response = client_for(event.owner).delete(f"/api/events/{event.pk}/grants/{alice.pk}/")
        assert response.status_code == 404


# --- API: write permissions (owner-only edit/delete; admin cannot override) -


@pytest.mark.django_db
class TestWritePermissions:
    def test_a_grantee_cannot_edit_the_event(self):
        bob = EmployeeFactory()
        event = EventFactory(grantees=[bob])
        response = client_for(bob).patch(
            f"/api/events/{event.pk}/", {"title": "Renamed"}, format="json"
        )
        assert response.status_code == 403

    def test_a_grantee_cannot_delete_the_event(self):
        bob = EmployeeFactory()
        event = EventFactory(grantees=[bob])
        assert client_for(bob).delete(f"/api/events/{event.pk}/").status_code == 403

    def test_the_owner_can_edit_the_event(self):
        event = EventFactory()
        response = client_for(event.owner).patch(
            f"/api/events/{event.pk}/", {"title": "Renamed"}, format="json"
        )
        assert response.status_code == 200

    def test_the_owner_can_cancel_the_event(self):
        event = EventFactory()
        response = client_for(event.owner).patch(
            f"/api/events/{event.pk}/", {"status": "CANCELLED"}, format="json"
        )
        assert response.status_code == 200
        assert response.json()["status"] == "CANCELLED"

    def test_the_owner_can_delete_the_event(self):
        event = EventFactory()
        assert client_for(event.owner).delete(f"/api/events/{event.pk}/").status_code == 204

    def test_an_admin_cannot_edit_someone_elses_event(self, admin_client):
        client, _ = admin_client
        event = EventFactory()
        response = client.patch(f"/api/events/{event.pk}/", {"title": "Renamed"}, format="json")
        assert response.status_code == 403

    def test_an_admin_cannot_delete_someone_elses_event(self, admin_client):
        client, _ = admin_client
        event = EventFactory()
        assert client.delete(f"/api/events/{event.pk}/").status_code == 403

    def test_an_admin_cannot_share_someone_elses_event(self, admin_client):
        client, _ = admin_client
        event = EventFactory()
        carol = EmployeeFactory()
        response = client.post(
            f"/api/events/{event.pk}/share/", {"employee": carol.pk}, format="json"
        )
        assert response.status_code == 403
