"""Registered PCs and their device credentials (§12, §29).

Two secrets live here and they are deliberately different in kind:

- the **enrollment code** is a short-lived, single-use, human-transcribable string the
  admin hands to an employee. It is stored in plain text because the admin has to be
  able to read it back off the screen, and it is worthless once used or expired.
- the **device token** is a long random string the agent keeps for the life of the
  install. It is stored only as a SHA-256 hash and shown exactly once, at registration.

Without the enrollment step the §28 register endpoint has no trust anchor at all —
anyone who could reach the API could enrol a device and post activity for someone else.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import secrets

from django.db import models
from django.utils import timezone

# Base32 without the characters people mistype when reading a code aloud or off a
# sticky note: no 0/O, no 1/I/L, no U (which turns codes into unfortunate words).
CODE_ALPHABET = "ABCDEFGHJKMNPQRSTVWXYZ23456789"
CODE_LENGTH = 10
CODE_GROUP = 5

# A code is a rollout convenience, not a standing credential. A week is long enough for
# "IT sets up the PC next Tuesday" and short enough that a leaked code goes stale.
ENROLLMENT_CODE_TTL = dt.timedelta(days=7)

# 32 bytes of urlsafe randomness. Not configurable: there is no reason to want less.
TOKEN_BYTES = 32


def generate_enrollment_code() -> str:
    """A grouped, unambiguous code such as `ABCDE-FGHJK`."""
    raw = "".join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LENGTH))
    return "-".join(raw[i : i + CODE_GROUP] for i in range(0, CODE_LENGTH, CODE_GROUP))


def normalise_code(code: str) -> str:
    """Accept what a human typed: any case, with or without the separator or spaces."""
    return (code or "").strip().upper().replace(" ", "").replace("-", "")


def generate_device_token() -> str:
    return secrets.token_urlsafe(TOKEN_BYTES)


def hash_token(token: str) -> str:
    """SHA-256, not a password hash.

    A device token is 256 bits of randomness rather than a memorable secret, so there is
    nothing for a slow KDF to defend against, and heartbeat authentication happens on
    every agent request — bcrypt here would be pure cost.
    """
    return hashlib.sha256((token or "").encode("utf-8")).hexdigest()


class ComputerStatus(models.TextChoices):
    ONLINE = "ONLINE", "Online"
    IDLE = "IDLE", "Idle"
    OFFLINE = "OFFLINE", "Offline"
    DISABLED = "DISABLED", "Disabled"


class LifecycleEvent(models.TextChoices):
    """PC lifecycle transitions the agent reports (§13, §34 system collector)."""

    STARTUP = "STARTUP", "Startup"
    SHUTDOWN = "SHUTDOWN", "Shutdown"
    SLEEP = "SLEEP", "Sleep"
    WAKE = "WAKE", "Wake"
    LOCK = "LOCK", "Lock"
    UNLOCK = "UNLOCK", "Unlock"


# Events that mean "this PC has stopped being on" and close the open PC_ON session.
CLOSING_EVENTS = {LifecycleEvent.SHUTDOWN, LifecycleEvent.SLEEP}


class Computer(models.Model):
    """One registered PC, always associated with exactly one employee (§29)."""

    employee = models.ForeignKey(
        "employees.Employee",
        on_delete=models.PROTECT,
        related_name="computers",
        help_text="Owner of this machine. Activity is attributed to them.",
    )
    computer_name = models.CharField(
        max_length=120,
        help_text="Machine name. Filled by the admin at enrolment and confirmed by the agent.",
    )
    operating_system = models.CharField(max_length=120, blank=True)
    agent_version = models.CharField(max_length=32, blank=True)

    # --- Enrolment ---
    enrollment_code = models.CharField(max_length=32, unique=True, null=True, blank=True)
    enrollment_expires_at = models.DateTimeField(null=True, blank=True)

    # --- Device credential ---
    # Unique so a token collision cannot silently authenticate two machines, and
    # nullable rather than blank so many un-registered rows can coexist.
    device_token_hash = models.CharField(max_length=64, unique=True, null=True, blank=True)
    registered_at = models.DateTimeField(null=True, blank=True)

    # --- Liveness ---
    last_seen_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(
        max_length=16, choices=ComputerStatus.choices, default=ComputerStatus.OFFLINE
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["computer_name", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["employee", "computer_name"], name="unique_computer_name_per_employee"
            )
        ]
        indexes = [
            models.Index(fields=["status"]),
            models.Index(fields=["last_seen_at"]),
        ]

    def __str__(self):
        return f"{self.computer_name} ({self.employee.name})"

    # --- Derived state -----------------------------------------------------

    @property
    def is_registered(self) -> bool:
        return bool(self.device_token_hash)

    @property
    def is_disabled(self) -> bool:
        return self.status == ComputerStatus.DISABLED

    @property
    def enrollment_valid(self) -> bool:
        if not self.enrollment_code or not self.enrollment_expires_at:
            return False
        return self.enrollment_expires_at > timezone.now()

    # --- Credential lifecycle ----------------------------------------------

    def issue_enrollment_code(self, *, ttl: dt.timedelta = ENROLLMENT_CODE_TTL) -> str:
        """Generate and store a fresh code, returning it for display.

        Issuing a code does not revoke an existing token: a working agent keeps working
        until the new registration actually completes. Revoking a device is a separate,
        explicit action (`disable`), because "I lost the code" and "someone stole the
        laptop" deserve different answers.
        """
        for _ in range(5):
            code = generate_enrollment_code()
            if not Computer.objects.filter(enrollment_code=normalise_code(code)).exists():
                break
        else:  # pragma: no cover - 30^10 collisions five times running
            raise RuntimeError("Could not generate a unique enrollment code")

        self.enrollment_code = normalise_code(code)
        self.enrollment_expires_at = timezone.now() + ttl
        return code

    def issue_device_token(self) -> str:
        """Replace the device credential and return the plaintext token, once."""
        token = generate_device_token()
        self.device_token_hash = hash_token(token)
        self.registered_at = timezone.now()
        # The code is single use: consumed here so a replay of the same registration
        # request cannot mint a second token.
        self.enrollment_code = None
        self.enrollment_expires_at = None
        return token

    @property
    def formatted_enrollment_code(self) -> str | None:
        """The stored code re-grouped for display."""
        if not self.enrollment_code:
            return None
        code = self.enrollment_code
        return "-".join(code[i : i + CODE_GROUP] for i in range(0, len(code), CODE_GROUP))
