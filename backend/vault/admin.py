"""Django admin registration for VaultEntry/VaultEntryGrant.

Deliberately excludes `secret_ciphertext` from every list/detail view, with
no decrypt action anywhere here. Admin visibility into a password belongs
to the product API's `reveal` action (disclosed and audit-logged) — this
is operational visibility only (who owns what, who has access), not a
second, unlogged way to read a password.
"""

from django.contrib import admin

from .models import VaultEntry, VaultEntryGrant


class VaultEntryGrantInline(admin.TabularInline):
    model = VaultEntryGrant
    extra = 0
    autocomplete_fields = ["grantee", "granted_by"]


@admin.register(VaultEntry)
class VaultEntryAdmin(admin.ModelAdmin):
    list_display = ["title", "owner", "username", "created_at"]
    search_fields = ["title", "owner__name", "owner__employee_id"]
    autocomplete_fields = ["owner"]
    exclude = ["secret_ciphertext"]
    inlines = [VaultEntryGrantInline]


@admin.register(VaultEntryGrant)
class VaultEntryGrantAdmin(admin.ModelAdmin):
    list_display = ["entry", "grantee", "granted_by", "granted_at"]
    autocomplete_fields = ["entry", "grantee", "granted_by"]
