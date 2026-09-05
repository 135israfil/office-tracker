"""Phase 0 exit tests: the user model behaves and the stack is wired end to end."""

import pytest
from django.contrib.auth import get_user_model
from django.db.utils import IntegrityError
from rest_framework.test import APIClient

from accounts.models import Role
from tests.factories import AdminFactory, UserFactory

User = get_user_model()


@pytest.mark.django_db
class TestUserModel:
    def test_create_user_defaults_to_employee(self):
        user = User.objects.create_user(email="a@example.com", password="pw-123456")
        assert user.role == Role.EMPLOYEE
        assert user.is_active is True
        assert user.is_staff is False
        assert user.is_admin is False

    def test_create_superuser_is_admin(self):
        user = User.objects.create_superuser(email="root@example.com", password="pw-123456")
        assert user.role == Role.ADMIN
        assert user.is_admin is True
        assert user.is_superuser is True

    def test_password_is_hashed_never_stored_plaintext(self):
        user = User.objects.create_user(email="b@example.com", password="pw-123456")
        assert user.password != "pw-123456"
        assert user.check_password("pw-123456") is True

    def test_email_is_normalised_and_unique(self):
        User.objects.create_user(email="c@Example.COM", password="pw-123456")
        assert User.objects.filter(email="c@example.COM").exists() is False
        assert User.objects.get(email__iexact="c@example.com")

        with pytest.raises(IntegrityError):
            User.objects.create_user(email="c@example.com", password="pw-123456")

    def test_email_is_required(self):
        with pytest.raises(ValueError, match="email"):
            User.objects.create_user(email="", password="pw-123456")

    def test_factories_produce_usable_logins(self):
        employee = UserFactory()
        admin = AdminFactory()
        assert employee.check_password("test-password-123")
        assert employee.is_admin is False
        assert admin.is_admin is True


@pytest.mark.django_db
class TestHealthEndpoint:
    def test_health_reports_ok_without_authentication(self):
        response = APIClient().get("/api/health/")
        assert response.status_code == 200
        assert response.json() == {"status": "ok", "database": "ok"}
