from django.contrib import admin

from .models import Event, EventGrant


class EventGrantInline(admin.TabularInline):
    model = EventGrant
    extra = 0
    autocomplete_fields = ["grantee", "granted_by"]


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ["title", "owner", "start", "end", "status"]
    list_filter = ["status", "all_day"]
    search_fields = ["title", "owner__name", "owner__employee_id"]
    autocomplete_fields = ["owner"]
    inlines = [EventGrantInline]


@admin.register(EventGrant)
class EventGrantAdmin(admin.ModelAdmin):
    list_display = ["event", "grantee", "granted_by", "granted_at"]
    autocomplete_fields = ["event", "grantee", "granted_by"]
