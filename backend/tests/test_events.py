"""Event declarations: company-wide visibility once LOCKED, the admin-only
visibility and write access of the budget/document/financial-status fields,
and the admin-visibility disclosure/audit-logging decisions — with one
deliberate difference from test_vault.py: list must never log, only
retrieve.
"""

from __future__ import annotations

import pytest
from rest_framework.test import APIClient

from core.models import AuditLog
from notifications.models import Notification
from tests.factories import AdminFactory, EmployeeFactory, EventFactory

# --- API: visibility -----------------------------------------------------------


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
class TestEventVisibility:
    def test_unauthenticated_is_refused(self):
        event = EventFactory()
        assert APIClient().get(f"/api/events/{event.pk}/").status_code == 401

    def test_an_uninvolved_employee_cannot_see_an_unlocked_event(self):
        alice = EmployeeFactory()
        event = EventFactory()  # ON_COMMUNICATION by default, owned by someone else
        response = client_for(alice).get(f"/api/events/{event.pk}/")
        assert response.status_code == 404

    def test_any_employee_can_see_a_locked_event(self):
        alice = EmployeeFactory()
        event = EventFactory(booking_status="LOCKED")
        assert client_for(alice).get(f"/api/events/{event.pk}/").status_code == 200

    def test_the_owner_sees_their_own_event_even_when_not_locked(self):
        event = EventFactory()
        assert client_for(event.owner).get(f"/api/events/{event.pk}/").status_code == 200

    def test_an_admin_sees_everything(self, admin_client):
        client, _ = admin_client
        event = EventFactory()
        assert client.get(f"/api/events/{event.pk}/").status_code == 200

    def test_an_owner_with_no_locked_events_still_sees_their_own_event_in_the_list(self):
        event = EventFactory()
        body = client_for(event.owner).get("/api/events/").json()
        assert body["count"] == 1

    def test_the_list_includes_locked_events_owned_by_someone_else(self):
        alice = EmployeeFactory()
        EventFactory(booking_status="LOCKED")
        body = client_for(alice).get("/api/events/").json()
        assert body["count"] == 1

    def test_the_list_excludes_unlocked_events_owned_by_someone_else(self):
        alice = EmployeeFactory()
        EventFactory()  # someone else's, still ON_COMMUNICATION
        body = client_for(alice).get("/api/events/").json()
        assert body["count"] == 0


# --- API: creating events -----------------------------------------------------


@pytest.mark.django_db
class TestCreate:
    def test_creating_an_event_stores_it_owned_by_the_creator(self):
        owner = EmployeeFactory()
        response = client_for(owner).post("/api/events/", {"title": "Standup"}, format="json")
        assert response.status_code == 201
        assert response.json()["owner"]["id"] == owner.id

    def test_booking_fields_round_trip_including_the_assigned_lead(self):
        owner = EmployeeFactory()
        lead = EmployeeFactory()
        response = client_for(owner).post(
            "/api/events/",
            {
                "title": "Annual dinner",
                "agency_name": "Acme Events",
                "venue_name": "Grand Hall",
                "setup": "Theatre, 200 seats",
                "assigned_lead_id": lead.pk,
                "booking_status": "LOCKED",
                "alert_on": "2026-12-01",
            },
            format="json",
        )
        assert response.status_code == 201, response.json()
        body = response.json()
        assert body["agency_name"] == "Acme Events"
        assert body["venue_name"] == "Grand Hall"
        assert body["assigned_lead"]["id"] == lead.id
        assert body["booking_status"] == "LOCKED"
        assert body["alert_on"] == "2026-12-01"

    def test_setup_is_sanitized_against_stored_xss(self):
        # Setup is rich text from the frontend's editor, rendered back to
        # every viewer once an event is LOCKED — a script tag must never
        # survive to be stored, let alone rendered back to someone else.
        owner = EmployeeFactory()
        response = client_for(owner).post(
            "/api/events/",
            {"title": "Standup", "setup": "<p>Stage left</p><script>alert(1)</script>"},
            format="json",
        )
        assert response.status_code == 201
        assert "<script>" not in response.json()["setup"]
        assert "Stage left" in response.json()["setup"]


# --- API: budget/document/financial status are admin-only --------------------


@pytest.mark.django_db
class TestFinancials:
    def test_they_are_absent_from_the_response_for_a_non_admin(self):
        event = EventFactory()
        body = client_for(event.owner).get(f"/api/events/{event.pk}/").json()
        assert "budget" not in body
        assert "document_status" not in body
        assert "financial_status" not in body

    def test_they_are_present_for_an_admin(self, admin_client):
        client, _ = admin_client
        event = EventFactory()
        body = client.get(f"/api/events/{event.pk}/").json()
        assert body["budget"] is None
        assert body["document_status"] == ""
        assert body["financial_status"] == ""

    def test_an_admin_can_set_them_even_on_someone_elses_event(self, admin_client):
        client, _ = admin_client
        event = EventFactory()
        response = client.patch(
            f"/api/events/{event.pk}/financials/",
            {"budget": "2000.00", "document_status": "WORK_ORDER", "financial_status": "ADVANCE"},
            format="json",
        )
        assert response.status_code == 200, response.json()
        body = response.json()
        assert body["budget"] == "2000.00"
        assert body["document_status"] == "WORK_ORDER"
        assert body["financial_status"] == "ADVANCE"

    def test_the_owner_cannot_set_them_through_the_ordinary_update(self):
        event = EventFactory()
        response = client_for(event.owner).patch(
            f"/api/events/{event.pk}/", {"budget": "500.00"}, format="json"
        )
        # Not an error: budget is read-only on the main serializer, so the
        # request succeeds but silently leaves budget untouched.
        assert response.status_code == 200
        event.refresh_from_db()
        assert event.budget is None

    def test_the_owner_cannot_use_the_financials_action_either(self):
        event = EventFactory()
        response = client_for(event.owner).patch(
            f"/api/events/{event.pk}/financials/", {"budget": "500.00"}, format="json"
        )
        assert response.status_code == 403


# --- API: assigned lead/booking status are owner- or admin-editable ----------


@pytest.mark.django_db
class TestCoordination:
    def test_the_owner_can_set_them_through_the_ordinary_update(self):
        event = EventFactory()
        lead = EmployeeFactory()
        response = client_for(event.owner).patch(
            f"/api/events/{event.pk}/",
            {"assigned_lead_id": lead.pk, "booking_status": "LOCKED"},
            format="json",
        )
        assert response.status_code == 200
        body = response.json()
        assert body["assigned_lead"]["id"] == lead.id
        assert body["booking_status"] == "LOCKED"

    def test_an_admin_can_set_them_even_on_someone_elses_event(self, admin_client):
        client, _ = admin_client
        event = EventFactory()
        lead = EmployeeFactory()
        response = client.patch(
            f"/api/events/{event.pk}/coordination/",
            {"assigned_lead_id": lead.pk, "booking_status": "LOCKED"},
            format="json",
        )
        assert response.status_code == 200, response.json()
        body = response.json()
        assert body["assigned_lead"]["id"] == lead.id
        assert body["booking_status"] == "LOCKED"

    def test_the_owner_cannot_use_the_coordination_action(self):
        event = EventFactory()
        response = client_for(event.owner).patch(
            f"/api/events/{event.pk}/coordination/", {"booking_status": "LOCKED"}, format="json"
        )
        assert response.status_code == 403

    def test_an_uninvolved_employee_cannot_use_the_coordination_action(self):
        # Not merely refused: an unlocked event owned by someone else is
        # invisible to Bob entirely, so get_queryset() filters it out before
        # the permission check is ever reached — a 404, not a 403.
        bob = EmployeeFactory()
        event = EventFactory()
        response = client_for(bob).patch(
            f"/api/events/{event.pk}/coordination/", {"booking_status": "LOCKED"}, format="json"
        )
        assert response.status_code == 404


# --- API: retrieve-level admin audit logging (list must never log) ----------


@pytest.mark.django_db
class TestAdminViewAuditLogging:
    def test_the_owner_retrieving_their_own_event_is_never_logged(self):
        event = EventFactory()
        client_for(event.owner).get(f"/api/events/{event.pk}/")
        assert not AuditLog.objects.filter(action=AuditLog.Action.EVENT_VIEWED_BY_ADMIN).exists()

    def test_an_employee_retrieving_a_locked_event_they_do_not_own_is_never_logged(self):
        # Routine, expected visibility now that locking makes an event
        # company-wide — not an anomaly worth auditing, unlike an admin's.
        alice = EmployeeFactory()
        event = EventFactory(booking_status="LOCKED")
        client_for(alice).get(f"/api/events/{event.pk}/")
        assert not AuditLog.objects.filter(action=AuditLog.Action.EVENT_VIEWED_BY_ADMIN).exists()

    def test_an_admin_retrieving_someone_elses_event_is_logged(self, admin_client):
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


# --- API: write permissions (owner-only edit/delete; admin cannot override) -


@pytest.mark.django_db
class TestWritePermissions:
    def test_an_uninvolved_employee_cannot_edit_a_locked_event(self):
        bob = EmployeeFactory()
        event = EventFactory(booking_status="LOCKED")
        response = client_for(bob).patch(
            f"/api/events/{event.pk}/", {"title": "Renamed"}, format="json"
        )
        assert response.status_code == 403

    def test_an_uninvolved_employee_cannot_delete_a_locked_event(self):
        bob = EmployeeFactory()
        event = EventFactory(booking_status="LOCKED")
        assert client_for(bob).delete(f"/api/events/{event.pk}/").status_code == 403

    def test_the_owner_can_edit_the_event(self):
        event = EventFactory()
        response = client_for(event.owner).patch(
            f"/api/events/{event.pk}/", {"title": "Renamed"}, format="json"
        )
        assert response.status_code == 200

    def test_the_owner_can_lock_the_event(self):
        event = EventFactory()
        response = client_for(event.owner).patch(
            f"/api/events/{event.pk}/", {"booking_status": "LOCKED"}, format="json"
        )
        assert response.status_code == 200
        assert response.json()["booking_status"] == "LOCKED"

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


# --- Notifications: owner and assigned lead, once an event becomes LOCKED ----


@pytest.mark.django_db
class TestLockNotifications:
    def test_creating_an_event_already_locked_notifies_the_assigned_lead(self):
        owner = EmployeeFactory()
        lead = EmployeeFactory()
        client_for(owner).post(
            "/api/events/",
            {"title": "Gala", "assigned_lead_id": lead.pk, "booking_status": "LOCKED"},
            format="json",
        )
        notification = Notification.objects.get(recipient=lead)
        assert "Gala" in notification.message

    def test_creating_it_does_not_notify_the_owner_themselves(self):
        owner = EmployeeFactory()
        client_for(owner).post(
            "/api/events/", {"title": "Gala", "booking_status": "LOCKED"}, format="json"
        )
        assert not Notification.objects.exists()

    def test_the_owner_locking_it_later_notifies_the_assigned_lead(self):
        lead = EmployeeFactory()
        event = EventFactory(assigned_lead=lead)
        client_for(event.owner).patch(
            f"/api/events/{event.pk}/", {"booking_status": "LOCKED"}, format="json"
        )
        notification = Notification.objects.get(recipient=lead)
        assert event.title in notification.message

    def test_an_admin_locking_it_via_coordination_notifies_owner_and_lead(self, admin_client):
        client, _ = admin_client
        lead = EmployeeFactory()
        event = EventFactory(assigned_lead=lead)
        client.patch(
            f"/api/events/{event.pk}/coordination/", {"booking_status": "LOCKED"}, format="json"
        )
        recipients = set(Notification.objects.values_list("recipient_id", flat=True))
        assert recipients == {event.owner_id, lead.pk}

    def test_moving_an_already_locked_event_to_done_does_not_renotify(self):
        lead = EmployeeFactory()
        event = EventFactory(assigned_lead=lead, booking_status="LOCKED")
        client_for(event.owner).patch(
            f"/api/events/{event.pk}/", {"booking_status": "DONE"}, format="json"
        )
        assert not Notification.objects.exists()

    def test_a_non_status_edit_of_a_locked_event_does_not_renotify(self):
        lead = EmployeeFactory()
        event = EventFactory(assigned_lead=lead, booking_status="LOCKED")
        client_for(event.owner).patch(
            f"/api/events/{event.pk}/", {"title": "Renamed"}, format="json"
        )
        assert not Notification.objects.exists()


# --- Management command: alert-date reminders --------------------------------


@pytest.mark.django_db
class TestSendEventAlerts:
    def test_notifies_owner_and_lead_on_the_alert_date(self):
        from django.core.management import call_command

        lead = EmployeeFactory()
        event = EventFactory(assigned_lead=lead, alert_on="2026-12-01")
        call_command("send_event_alerts", "--date=2026-12-01")
        recipients = set(Notification.objects.values_list("recipient_id", flat=True))
        assert recipients == {event.owner_id, lead.pk}

    def test_an_event_whose_alert_date_is_not_today_is_skipped(self):
        from django.core.management import call_command

        EventFactory(alert_on="2026-12-02")
        call_command("send_event_alerts", "--date=2026-12-01")
        assert not Notification.objects.exists()

    def test_running_it_twice_the_same_day_does_not_double_send(self):
        from django.core.management import call_command

        event = EventFactory(alert_on="2026-12-01")
        call_command("send_event_alerts", "--date=2026-12-01")
        call_command("send_event_alerts", "--date=2026-12-01")
        assert Notification.objects.filter(recipient=event.owner).count() == 1
