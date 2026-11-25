"""Authentication model.

Defined in the first migration on purpose: swapping AUTH_USER_MODEL after tables
exist is a painful manual migration, and this project knows it needs email login
and a role field from day one (PLAN.md §2).
"""

import hashlib
import secrets

from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django.utils import timezone

# 32 bytes of urlsafe randomness — same size and rationale as computers.models'
# device token: 256 bits of entropy needs no slow KDF, just a lookup hash.
TOKEN_BYTES = 32


def generate_auth_token() -> str:
    return secrets.token_urlsafe(TOKEN_BYTES)


def hash_token(token: str) -> str:
    return hashlib.sha256((token or "").encode("utf-8")).hexdigest()


class Role(models.TextChoices):
    ADMIN = "ADMIN", "Admin"
    EMPLOYEE = "EMPLOYEE", "Employee"


class UserManager(BaseUserManager):
    use_in_migrations = True

    def _create_user(self, email, password, **extra):
        if not email:
            raise ValueError("Users must have an email address")
        user = self.model(email=self.normalize_email(email), **extra)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra):
        extra.setdefault("role", Role.EMPLOYEE)
        extra.setdefault("is_staff", False)
        extra.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra)

    def create_superuser(self, email, password=None, **extra):
        extra.setdefault("role", Role.ADMIN)
        extra.setdefault("is_staff", True)
        extra.setdefault("is_superuser", True)
        if extra["is_staff"] is not True:
            raise ValueError("Superuser must have is_staff=True")
        if extra["is_superuser"] is not True:
            raise ValueError("Superuser must have is_superuser=True")
        return self._create_user(email, password, **extra)


class User(AbstractBaseUser, PermissionsMixin):
    email = models.EmailField(unique=True)
    role = models.CharField(max_length=16, choices=Role.choices, default=Role.EMPLOYEE)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    date_joined = models.DateTimeField(default=timezone.now)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    class Meta:
        ordering = ["email"]

    def __str__(self):
        return self.email

    @property
    def is_admin(self):
        return self.role == Role.ADMIN


class AuthToken(models.Model):
    """A bearer credential for native clients (the Android app) that can't carry
    session cookies the way a browser does.

    Deliberately separate from `computers.Computer`'s device token: that one grants
    "report this machine's activity" and belongs to a device; this one grants "act as
    this person" and belongs to a user, the same thing their session already grants.
    One user can hold several (web session + phone + a reinstall all coexist) — each
    login mints its own, so logging out on one device never touches another's.
    """

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="auth_tokens")
    token_hash = models.CharField(max_length=64, unique=True)
    label = models.CharField(max_length=120, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user.email} ({self.label or 'token'})"
