"""Work credential store: who owns an entry, and who else it's shared with.

Only `secret_ciphertext` is encrypted (see `crypto.py`) — title, username, url
and notes stay plaintext so list/search views never decrypt rows just to
render metadata (resolved during design; see docs/designs/work-credential-
store.md's Technical Plan).

Sharing is an explicit through-model (`VaultEntryGrant`), not a bare
`ManyToManyField`, for the same reason `tasks.TaskAssignee` is one: per-grant
state (who granted it, when) is needed from day one, and a grant is always a
live reference to the entry, never a snapshot of the secret — a later
password change is immediately visible to every existing grantee.
"""

from __future__ import annotations

from django.db import models

from employees.models import Employee


class VaultEntry(models.Model):
    # PROTECT, not CASCADE: resolves the design's open "owner-deleted cascade"
    # question the same way Task.created_by resolves it — an employee record
    # must not silently take every credential they ever owned with it if it is
    # ever removed, which would also strand any grantee still relying on it.
    owner = models.ForeignKey(Employee, on_delete=models.PROTECT, related_name="vault_entries")
    title = models.CharField(max_length=200)
    username = models.CharField(max_length=200, blank=True)
    secret_ciphertext = models.BinaryField()
    url = models.URLField(max_length=500, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["owner"]),
        ]

    def __str__(self):
        return self.title


class VaultEntryGrant(models.Model):
    """One employee's view-only access to one entry — the through-model for
    `VaultEntry.grants`."""

    entry = models.ForeignKey(VaultEntry, on_delete=models.CASCADE, related_name="grants")
    grantee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="vault_grants")
    # PROTECT: who granted access is part of this entry's history and must not
    # be erased by that person's own employee record being removed later.
    granted_by = models.ForeignKey(
        Employee, on_delete=models.PROTECT, related_name="vault_grants_made"
    )
    granted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["granted_at"]
        constraints = [
            models.UniqueConstraint(fields=["entry", "grantee"], name="unique_grant_per_entry")
        ]
        indexes = [
            models.Index(fields=["grantee", "entry"]),
        ]

    def __str__(self):
        return f"entry {self.entry_id} -> employee {self.grantee_id}"
