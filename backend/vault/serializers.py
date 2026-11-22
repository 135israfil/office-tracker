"""Vault entry serialization.

The decrypted password is never present on `VaultEntrySerializer` — not list,
not retrieve, not even write-only-masked on output — because list/retrieve
must stay cheap (see the design's Technical Plan) and because exposing it
anywhere but the dedicated `reveal` action would bypass that action's
throttling and conditional admin-reveal audit logging.

`password` here is a plain input field, not a model field: it is encrypted
with `crypto.encrypt_secret()` before being stored as `secret_ciphertext`,
and is required on create but optional on update (omit it to leave the
stored secret unchanged).
"""

from __future__ import annotations

from rest_framework import serializers

from core.audit import AuditLog
from employees.models import Employee

from .crypto import encrypt_secret
from .models import VaultEntry, VaultEntryGrant


class _EmployeeStubSerializer(serializers.ModelSerializer):
    class Meta:
        model = Employee
        fields = ["id", "employee_id", "name"]


class VaultEntryGrantSerializer(serializers.ModelSerializer):
    grantee = _EmployeeStubSerializer(read_only=True)
    granted_by = _EmployeeStubSerializer(read_only=True)

    class Meta:
        model = VaultEntryGrant
        fields = ["id", "grantee", "granted_by", "granted_at"]
        read_only_fields = fields


class VaultEntrySerializer(serializers.ModelSerializer):
    owner = _EmployeeStubSerializer(read_only=True)
    grants = VaultEntryGrantSerializer(many=True, read_only=True)
    visible_to = serializers.SerializerMethodField()
    last_admin_reveal = serializers.SerializerMethodField()
    password = serializers.CharField(write_only=True, required=False, allow_blank=False)

    class Meta:
        model = VaultEntry
        fields = [
            "id",
            "title",
            "username",
            "password",
            "url",
            "notes",
            "owner",
            "grants",
            "visible_to",
            "last_admin_reveal",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "owner",
            "grants",
            "visible_to",
            "last_admin_reveal",
            "created_at",
            "updated_at",
        ]

    def validate(self, attrs):
        if self.instance is None and not attrs.get("password"):
            raise serializers.ValidationError({"password": "This field is required."})
        return attrs

    def get_visible_to(self, obj):
        # A plain disclosure line, not an access-control structure in its own
        # right — the "Visible to: ..." mechanism from the design's Technical
        # Plan that makes blanket admin visibility disclosed rather than silent.
        names = [obj.owner.name] + [grant.grantee.name for grant in obj.grants.all()]
        return names + ["All admins"]

    def get_last_admin_reveal(self, obj):
        entry = (
            AuditLog.objects.filter(
                action=AuditLog.Action.VAULT_ENTRY_REVEALED_BY_ADMIN,
                target_type="VaultEntry",
                target_id=str(obj.pk),
            )
            .order_by("-created_at")
            .first()
        )
        if entry is None:
            return None
        return {"admin": entry.actor.email if entry.actor else None, "at": entry.created_at}

    def create(self, validated_data):
        password = validated_data.pop("password")
        validated_data["secret_ciphertext"] = encrypt_secret(password)
        return super().create(validated_data)

    def update(self, instance, validated_data):
        password = validated_data.pop("password", None)
        if password:
            validated_data["secret_ciphertext"] = encrypt_secret(password)
        return super().update(instance, validated_data)
