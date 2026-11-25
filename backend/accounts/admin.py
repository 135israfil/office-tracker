from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import AuthToken, User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    ordering = ["email"]
    list_display = ["email", "role", "is_active", "is_staff"]
    list_filter = ["role", "is_active", "is_staff"]
    search_fields = ["email"]
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Role", {"fields": ("role",)}),
        (
            "Permissions",
            {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")},
        ),
        ("Dates", {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = (
        (None, {"classes": ("wide",), "fields": ("email", "role", "password1", "password2")}),
    )


@admin.register(AuthToken)
class AuthTokenAdmin(admin.ModelAdmin):
    """Visibility and revocation only — tokens are minted by TokenLoginView, never here."""

    list_display = ["user", "label", "created_at", "last_used_at"]
    list_filter = ["created_at"]
    search_fields = ["user__email", "label"]
    readonly_fields = ["user", "token_hash", "label", "created_at", "last_used_at"]

    def has_add_permission(self, request):
        return False
