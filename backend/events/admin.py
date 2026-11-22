from django.contrib import admin

from .models import Event


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ["title", "owner", "alert_on", "booking_status"]
    list_filter = ["booking_status"]
    search_fields = ["title", "owner__name", "owner__employee_id", "agency_name", "venue_name"]
    autocomplete_fields = ["owner", "assigned_lead"]
