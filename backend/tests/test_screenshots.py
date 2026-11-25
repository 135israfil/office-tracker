"""Screenshot capture: admin-only visibility and retention.

Viewing used to be unconditionally audit-logged; that was reversed
2026-11-23 by request, so admins can review captures as freely as any other
report until retention deletes them (see TestViewing below).
"""

from __future__ import annotations

import datetime as dt

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from attendance.calendar_rules import local_date
from attendance.models import AppSettings
from core.models import AuditLog
from screenshots.retention import purge_screenshots
from tests.factories import AdminFactory, EmployeeFactory, ScreenshotCaptureFactory

# --- API: admin-only visibility ------------------------------------------------


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
class TestVisibility:
    def test_unauthenticated_is_refused(self):
        capture = ScreenshotCaptureFactory()
        assert APIClient().get(f"/api/screenshots/{capture.pk}/").status_code == 401

    def test_the_captured_employee_cannot_see_their_own_capture(self):
        # Deliberate: unlike every other feature in this codebase, the subject
        # of the data gets no API access to it at all.
        capture = ScreenshotCaptureFactory()
        response = client_for(capture.employee).get(f"/api/screenshots/{capture.pk}/")
        assert response.status_code == 403

    def test_an_uninvolved_employee_cannot_see_it_either(self):
        alice = EmployeeFactory()
        capture = ScreenshotCaptureFactory()
        assert client_for(alice).get(f"/api/screenshots/{capture.pk}/").status_code == 403

    def test_an_admin_sees_the_metadata(self, admin_client):
        client, _ = admin_client
        capture = ScreenshotCaptureFactory()
        response = client.get(f"/api/screenshots/{capture.pk}/")
        assert response.status_code == 200
        assert "file" not in response.json()

    def test_the_list_includes_a_view_link_but_never_the_raw_file_field(self, admin_client):
        client, _ = admin_client
        capture = ScreenshotCaptureFactory()
        row = client.get("/api/screenshots/").json()["results"][0]
        assert "file" not in row
        assert row["image_url"].endswith(f"/api/screenshots/{capture.pk}/view/")

    def test_listing_can_be_filtered_to_one_employee_and_day(self, admin_client):
        """The activity page asks for exactly the employee and day it is already
        showing — without this, it would get every capture ever taken."""
        client, _ = admin_client
        wanted = ScreenshotCaptureFactory(captured_at=timezone.now())
        ScreenshotCaptureFactory()  # a different employee, same day
        ScreenshotCaptureFactory(
            employee=wanted.employee, captured_at=timezone.now() - dt.timedelta(days=5)
        )

        day = local_date(timezone.now(), AppSettings.load())
        body = client.get(
            "/api/screenshots/", {"employee": wanted.employee_id, "date": day.isoformat()}
        ).json()

        assert [row["id"] for row in body["results"]] == [wanted.pk]


# --- API: the `view` action -----------------------------------------------


@pytest.mark.django_db
class TestViewing:
    def test_an_admin_can_view_the_image(self, admin_client):
        client, _ = admin_client
        capture = ScreenshotCaptureFactory()
        # HTTP_ACCEPT matches what the frontend's fetchImageObjectUrl actually sends
        # (client.js) - DRF's content negotiation 406s the whole request before the
        # view body runs if no configured renderer can satisfy it, which plain
        # client.get() (no explicit Accept) does not exercise.
        response = client.get(f"/api/screenshots/{capture.pk}/view/", HTTP_ACCEPT="image/*")
        assert response.status_code == 200
        assert b"".join(response.streaming_content) == b"not a real png, just test bytes"

    def test_viewing_is_not_audit_logged(self, admin_client):
        """Reversed 2026-11-23, by request: admins review captures as freely as
        any other report, with no per-view record and no special rate limit."""
        client, _ = admin_client
        capture = ScreenshotCaptureFactory()
        client.get(f"/api/screenshots/{capture.pk}/view/")
        client.get(f"/api/screenshots/{capture.pk}/view/")
        assert not AuditLog.objects.filter(
            action=AuditLog.Action.SCREENSHOT_VIEWED_BY_ADMIN
        ).exists()

    def test_a_non_admin_cannot_view_the_image(self):
        capture = ScreenshotCaptureFactory()
        response = client_for(capture.employee).get(f"/api/screenshots/{capture.pk}/view/")
        assert response.status_code == 403


# --- Retention ------------------------------------------------------------------


@pytest.mark.django_db
class TestRetention:
    def test_a_capture_older_than_the_window_is_deleted(self):
        old = ScreenshotCaptureFactory(captured_at=timezone.now() - dt.timedelta(days=10))
        recent = ScreenshotCaptureFactory(captured_at=timezone.now() - dt.timedelta(days=1))

        result = purge_screenshots()

        assert result["deleted"] == 1
        assert not type(old).objects.filter(pk=old.pk).exists()
        assert type(recent).objects.filter(pk=recent.pk).exists()

    def test_dry_run_deletes_nothing(self):
        capture = ScreenshotCaptureFactory(captured_at=timezone.now() - dt.timedelta(days=10))
        result = purge_screenshots(dry_run=True)
        assert result["eligible"] == 1
        assert result["deleted"] == 0
        assert type(capture).objects.filter(pk=capture.pk).exists()

    def test_retention_run_is_audit_logged_even_when_nothing_is_deleted(self):
        purge_screenshots()
        assert AuditLog.objects.filter(action=AuditLog.Action.SCREENSHOT_PURGED).exists()
