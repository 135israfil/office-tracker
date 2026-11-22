"""Work credential store: encryption round-trip, the same data-isolation exit
criterion test_dashboards.py enforces for activity data, and the
admin-visibility disclosure/audit-logging decisions from the design.
"""

from __future__ import annotations

import pytest
from rest_framework.test import APIClient

from core.models import AuditLog
from tests.factories import AdminFactory, EmployeeFactory, VaultEntryFactory
from vault.crypto import decrypt_secret, encrypt_secret
from vault.models import VaultEntry

# --- Pure logic ---------------------------------------------------------------


class TestCrypto:
    def test_encrypting_then_decrypting_returns_the_original_string(self):
        ciphertext = encrypt_secret("correct-horse-battery-staple")
        assert decrypt_secret(ciphertext) == "correct-horse-battery-staple"

    def test_the_stored_ciphertext_is_never_the_plaintext_itself(self):
        ciphertext = encrypt_secret("correct-horse-battery-staple")
        assert b"correct-horse-battery-staple" not in ciphertext


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
class TestVaultEntryIsolation:
    def test_unauthenticated_is_refused(self):
        entry = VaultEntryFactory()
        assert APIClient().get(f"/api/vault-entries/{entry.pk}/").status_code == 403

    def test_an_uninvolved_employee_cannot_see_the_entry(self):
        alice = EmployeeFactory()
        entry = VaultEntryFactory()  # owned by someone else entirely
        response = client_for(alice).get(f"/api/vault-entries/{entry.pk}/")
        assert response.status_code == 404

    def test_the_owner_sees_their_own_entry(self):
        entry = VaultEntryFactory()
        assert client_for(entry.owner).get(f"/api/vault-entries/{entry.pk}/").status_code == 200

    def test_a_grantee_who_is_not_the_owner_sees_the_entry(self):
        bob = EmployeeFactory()
        entry = VaultEntryFactory(grantees=[bob])
        assert client_for(bob).get(f"/api/vault-entries/{entry.pk}/").status_code == 200

    def test_an_admin_sees_everything(self, admin_client):
        client, _ = admin_client
        entry = VaultEntryFactory()
        assert client.get(f"/api/vault-entries/{entry.pk}/").status_code == 200

    def test_an_owner_with_zero_grantees_still_sees_their_own_entry_in_the_list(self):
        entry = VaultEntryFactory()
        body = client_for(entry.owner).get("/api/vault-entries/").json()
        assert body["count"] == 1

    def test_the_list_excludes_entries_owned_by_someone_else(self):
        alice = EmployeeFactory()
        VaultEntryFactory()  # someone else's entry
        body = client_for(alice).get("/api/vault-entries/").json()
        assert body["count"] == 0

    def test_the_decrypted_password_is_never_present_on_list_or_retrieve(self):
        entry = VaultEntryFactory()
        detail = client_for(entry.owner).get(f"/api/vault-entries/{entry.pk}/").json()
        assert "password" not in detail
        listing = client_for(entry.owner).get("/api/vault-entries/").json()
        assert "password" not in listing["results"][0]


# --- API: creating entries ---------------------------------------------------


@pytest.mark.django_db
class TestCreate:
    def test_creating_an_entry_without_a_password_is_rejected(self):
        owner = EmployeeFactory()
        response = client_for(owner).post(
            "/api/vault-entries/", {"title": "No secret"}, format="json"
        )
        assert response.status_code == 400

    def test_creating_an_entry_stores_it_encrypted_and_owned_by_the_creator(self):
        owner = EmployeeFactory()
        response = client_for(owner).post(
            "/api/vault-entries/",
            {"title": "Vendor portal", "username": "svc-account", "password": "s3cr3t"},
            format="json",
        )
        assert response.status_code == 201
        entry = VaultEntry.objects.get(pk=response.json()["id"])
        assert entry.owner_id == owner.id
        assert decrypt_secret(entry.secret_ciphertext) == "s3cr3t"


# --- API: the reveal action and its conditional audit logging ---------------


@pytest.mark.django_db
class TestReveal:
    def test_the_owner_can_reveal_their_own_password(self):
        entry = VaultEntryFactory()
        response = client_for(entry.owner).post(f"/api/vault-entries/{entry.pk}/reveal/")
        assert response.status_code == 200
        assert response.json()["password"] == "test-password-123"

    def test_an_owner_reveal_is_never_audit_logged(self):
        entry = VaultEntryFactory()
        client_for(entry.owner).post(f"/api/vault-entries/{entry.pk}/reveal/")
        assert not AuditLog.objects.filter(
            action=AuditLog.Action.VAULT_ENTRY_REVEALED_BY_ADMIN
        ).exists()

    def test_a_grantee_reveal_is_never_audit_logged(self):
        bob = EmployeeFactory()
        entry = VaultEntryFactory(grantees=[bob])
        client_for(bob).post(f"/api/vault-entries/{entry.pk}/reveal/")
        assert not AuditLog.objects.filter(
            action=AuditLog.Action.VAULT_ENTRY_REVEALED_BY_ADMIN
        ).exists()

    def test_an_admin_reveal_of_a_non_shared_entry_is_audit_logged(self, admin_client):
        client, admin = admin_client
        entry = VaultEntryFactory()
        response = client.post(f"/api/vault-entries/{entry.pk}/reveal/")
        assert response.status_code == 200
        log = AuditLog.objects.get(action=AuditLog.Action.VAULT_ENTRY_REVEALED_BY_ADMIN)
        assert log.actor_id == admin.pk
        assert log.target_type == "VaultEntry"
        assert log.target_id == str(entry.pk)

    def test_the_logged_admin_reveal_is_surfaced_back_to_the_owner(self, admin_client):
        client, _ = admin_client
        entry = VaultEntryFactory()
        client.post(f"/api/vault-entries/{entry.pk}/reveal/")
        detail = client_for(entry.owner).get(f"/api/vault-entries/{entry.pk}/").json()
        assert detail["last_admin_reveal"] is not None

    def test_an_uninvolved_employee_cannot_reveal(self):
        alice = EmployeeFactory()
        entry = VaultEntryFactory()
        response = client_for(alice).post(f"/api/vault-entries/{entry.pk}/reveal/")
        assert response.status_code == 404

    def test_unauthenticated_is_refused(self):
        entry = VaultEntryFactory()
        assert APIClient().post(f"/api/vault-entries/{entry.pk}/reveal/").status_code == 403


# --- API: sharing and revoking -----------------------------------------------


@pytest.mark.django_db
class TestShareAndRevoke:
    def test_the_owner_can_share_with_another_employee(self):
        entry = VaultEntryFactory()
        bob = EmployeeFactory()
        response = client_for(entry.owner).post(
            f"/api/vault-entries/{entry.pk}/share/", {"employee": bob.pk}, format="json"
        )
        assert response.status_code == 200
        assert [g["grantee"]["id"] for g in response.json()["grants"]] == [bob.pk]

    def test_sharing_response_itself_reflects_the_new_state(self):
        # Not just the database afterward: a bare .create() on a prefetched
        # relation does not invalidate get_object()'s own cache, the same
        # staleness risk Task Tracking's add_assignee/remove_assignee hit.
        entry = VaultEntryFactory()
        bob = EmployeeFactory()
        response = client_for(entry.owner).post(
            f"/api/vault-entries/{entry.pk}/share/", {"employee": bob.pk}, format="json"
        )
        assert len(response.json()["grants"]) == 1

    def test_sharing_with_an_already_shared_employee_is_rejected(self):
        bob = EmployeeFactory()
        entry = VaultEntryFactory(grantees=[bob])
        response = client_for(entry.owner).post(
            f"/api/vault-entries/{entry.pk}/share/", {"employee": bob.pk}, format="json"
        )
        assert response.status_code == 400

    def test_a_grantee_cannot_share_the_entry_further(self):
        bob = EmployeeFactory()
        carol = EmployeeFactory()
        entry = VaultEntryFactory(grantees=[bob])
        response = client_for(bob).post(
            f"/api/vault-entries/{entry.pk}/share/", {"employee": carol.pk}, format="json"
        )
        assert response.status_code == 403

    def test_the_owner_may_revoke_any_grantee(self):
        bob = EmployeeFactory()
        entry = VaultEntryFactory(grantees=[bob])
        response = client_for(entry.owner).delete(f"/api/vault-entries/{entry.pk}/grants/{bob.pk}/")
        assert response.status_code == 200
        assert entry.grants.count() == 0

    def test_the_revoke_response_itself_reflects_the_new_state(self):
        bob = EmployeeFactory()
        entry = VaultEntryFactory(grantees=[bob])
        response = client_for(entry.owner).delete(f"/api/vault-entries/{entry.pk}/grants/{bob.pk}/")
        assert response.json()["grants"] == []

    def test_a_grantee_may_revoke_their_own_access(self):
        bob = EmployeeFactory()
        entry = VaultEntryFactory(grantees=[bob])
        response = client_for(bob).delete(f"/api/vault-entries/{entry.pk}/grants/{bob.pk}/")
        assert response.status_code == 200

    def test_a_grantee_cannot_revoke_another_grantees_access(self):
        bob = EmployeeFactory()
        carol = EmployeeFactory()
        entry = VaultEntryFactory(grantees=[bob, carol])
        response = client_for(bob).delete(f"/api/vault-entries/{entry.pk}/grants/{carol.pk}/")
        assert response.status_code == 403
        assert entry.grants.filter(grantee=carol).exists()

    def test_revoking_an_employee_with_no_grant_is_a_404(self):
        entry = VaultEntryFactory()
        alice = EmployeeFactory()
        response = client_for(entry.owner).delete(
            f"/api/vault-entries/{entry.pk}/grants/{alice.pk}/"
        )
        assert response.status_code == 404


# --- API: write permissions (owner-only edit/delete; admin cannot override) -


@pytest.mark.django_db
class TestWritePermissions:
    def test_a_grantee_cannot_edit_the_entry(self):
        bob = EmployeeFactory()
        entry = VaultEntryFactory(grantees=[bob])
        response = client_for(bob).patch(
            f"/api/vault-entries/{entry.pk}/", {"title": "Renamed"}, format="json"
        )
        assert response.status_code == 403

    def test_a_grantee_cannot_delete_the_entry(self):
        bob = EmployeeFactory()
        entry = VaultEntryFactory(grantees=[bob])
        assert client_for(bob).delete(f"/api/vault-entries/{entry.pk}/").status_code == 403

    def test_the_owner_can_edit_the_entry(self):
        entry = VaultEntryFactory()
        response = client_for(entry.owner).patch(
            f"/api/vault-entries/{entry.pk}/", {"title": "Renamed"}, format="json"
        )
        assert response.status_code == 200

    def test_updating_without_a_password_keeps_the_existing_secret(self):
        entry = VaultEntryFactory()
        client_for(entry.owner).patch(
            f"/api/vault-entries/{entry.pk}/", {"title": "Renamed"}, format="json"
        )
        entry.refresh_from_db()
        assert decrypt_secret(entry.secret_ciphertext) == "test-password-123"

    def test_the_owner_can_delete_the_entry(self):
        entry = VaultEntryFactory()
        assert client_for(entry.owner).delete(f"/api/vault-entries/{entry.pk}/").status_code == 204

    def test_an_admin_cannot_edit_someone_elses_entry(self, admin_client):
        client, _ = admin_client
        entry = VaultEntryFactory()
        response = client.patch(
            f"/api/vault-entries/{entry.pk}/", {"title": "Renamed"}, format="json"
        )
        assert response.status_code == 403

    def test_an_admin_cannot_delete_someone_elses_entry(self, admin_client):
        client, _ = admin_client
        entry = VaultEntryFactory()
        assert client.delete(f"/api/vault-entries/{entry.pk}/").status_code == 403

    def test_an_admin_cannot_share_someone_elses_entry(self, admin_client):
        client, _ = admin_client
        entry = VaultEntryFactory()
        carol = EmployeeFactory()
        response = client.post(
            f"/api/vault-entries/{entry.pk}/share/", {"employee": carol.pk}, format="json"
        )
        assert response.status_code == 403
