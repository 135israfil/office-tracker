"""In-app notifications: the `notify()` helper's dedupe/no-op behavior, and
the API's per-employee visibility and read/read-all actions.
"""

from __future__ import annotations

import pytest
from rest_framework.test import APIClient

from notifications.models import Notification
from notifications.services import notify
from tests.factories import EmployeeFactory, NotificationFactory


def client_for(employee):
    client = APIClient()
    client.force_authenticate(user=employee.user)
    return client


@pytest.mark.django_db
class TestNotifyService:
    def test_it_creates_a_notification_for_the_recipient(self):
        alice = EmployeeFactory()
        result = notify(alice, "Hello", url="/tasks/1")
        assert result is not None
        assert Notification.objects.get(recipient=alice).message == "Hello"

    def test_a_none_recipient_is_a_silent_no_op(self):
        # Callers pass optional fields (e.g. event.assigned_lead) directly,
        # without a None-guard of their own.
        assert notify(None, "Hello") is None
        assert not Notification.objects.exists()

    def test_a_repeated_dedupe_key_sends_nothing_twice(self):
        alice = EmployeeFactory()
        first = notify(alice, "Reminder", dedupe_key="event-alert-1-2026-12-01-1")
        second = notify(alice, "Reminder", dedupe_key="event-alert-1-2026-12-01-1")
        assert first is not None
        assert second is None
        assert Notification.objects.count() == 1

    def test_different_dedupe_keys_both_send(self):
        alice = EmployeeFactory()
        notify(alice, "One", dedupe_key="key-1")
        notify(alice, "Two", dedupe_key="key-2")
        assert Notification.objects.count() == 2


@pytest.mark.django_db
class TestVisibility:
    def test_unauthenticated_is_refused(self):
        assert APIClient().get("/api/notifications/").status_code == 401

    def test_an_employee_sees_only_their_own_notifications(self):
        alice = EmployeeFactory()
        NotificationFactory(recipient=alice)
        NotificationFactory()  # someone else's
        body = client_for(alice).get("/api/notifications/").json()
        assert body["count"] == 1

    def test_an_employee_cannot_retrieve_someone_elses_notification(self):
        alice = EmployeeFactory()
        other = NotificationFactory()
        response = client_for(alice).get(f"/api/notifications/{other.pk}/")
        assert response.status_code == 404

    def test_the_unread_filter_excludes_already_read_notifications(self):
        alice = EmployeeFactory()
        NotificationFactory(recipient=alice)
        NotificationFactory(recipient=alice, read_at="2026-01-01T00:00:00Z")
        body = client_for(alice).get("/api/notifications/?unread=true").json()
        assert body["count"] == 1


@pytest.mark.django_db
class TestMarkRead:
    def test_marking_a_notification_read_sets_read_at(self):
        alice = EmployeeFactory()
        notification = NotificationFactory(recipient=alice)
        response = client_for(alice).post(f"/api/notifications/{notification.pk}/read/")
        assert response.status_code == 200
        assert response.json()["read_at"] is not None

    def test_marking_an_already_read_notification_is_a_no_op(self):
        alice = EmployeeFactory()
        notification = NotificationFactory(recipient=alice, read_at="2026-01-01T00:00:00Z")
        response = client_for(alice).post(f"/api/notifications/{notification.pk}/read/")
        assert response.status_code == 200
        assert response.json()["read_at"].startswith("2026-01-01")

    def test_an_employee_cannot_mark_someone_elses_notification_read(self):
        alice = EmployeeFactory()
        other = NotificationFactory()
        response = client_for(alice).post(f"/api/notifications/{other.pk}/read/")
        assert response.status_code == 404
        other.refresh_from_db()
        assert other.read_at is None

    def test_mark_all_read_only_touches_the_requesters_own_notifications(self):
        alice = EmployeeFactory()
        mine = NotificationFactory(recipient=alice)
        someone_elses = NotificationFactory()
        response = client_for(alice).post("/api/notifications/read_all/")
        assert response.status_code == 204
        mine.refresh_from_db()
        someone_elses.refresh_from_db()
        assert mine.read_at is not None
        assert someone_elses.read_at is None
