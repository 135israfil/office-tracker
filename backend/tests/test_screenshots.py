"""Screenshot capture: admin-only visibility, unconditional view audit logging
(the one place this feature deliberately differs from the Vault's conditional
logging, since there is no owner/grantee tier here at all), and retention.
"""

from __future__ import annotations

import datetime as dt

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

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
        assert APIClient().get(f"/api/screenshots/{capture.pk}/").status_code == 403

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

    def test_the_list_never_includes_the_image_or_a_url_to_it(self, admin_client):
        client, _ = admin_client
        ScreenshotCaptureFactory()
        body = client.get("/api/screenshots/").json()
        assert "file" not in body["results"][0]


# --- API: the `view` action and unconditional audit logging -------------------


@pytest.mark.django_db
class TestViewAndAuditLogging:
    def test_an_admin_can_view_the_image(self, admin_client):
        client, _ = admin_client
        capture = ScreenshotCaptureFactory()
        response = client.get(f"/api/screenshots/{capture.pk}/view/")
        assert response.status_code == 200
        assert b"".join(response.streaming_content) == b"not a real png, just test bytes"

    def test_every_view_is_logged_unconditionally(self, admin_client):
        client, admin = admin_client
        capture = ScreenshotCaptureFactory()
        client.get(f"/api/screenshots/{capture.pk}/view/")
        log = AuditLog.objects.get(action=AuditLog.Action.SCREENSHOT_VIEWED_BY_ADMIN)
        assert log.actor_id == admin.pk
        assert log.target_type == "ScreenshotCapture"
        assert log.target_id == str(capture.pk)

    def test_the_view_count_and_last_viewer_are_surfaced_in_the_metadata(self, admin_client):
        client, admin = admin_client
        capture = ScreenshotCaptureFactory()
        client.get(f"/api/screenshots/{capture.pk}/view/")
        detail = client.get(f"/api/screenshots/{capture.pk}/").json()
        assert detail["view_count"] == 1
        assert detail["last_viewed_by"]["admin"] == admin.email

    def test_a_non_admin_cannot_view_the_image(self):
        capture = ScreenshotCaptureFactory()
        response = client_for(capture.employee).get(f"/api/screenshots/{capture.pk}/view/")
        assert response.status_code == 403
        assert not AuditLog.objects.filter(
            action=AuditLog.Action.SCREENSHOT_VIEWED_BY_ADMIN
        ).exists()


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
