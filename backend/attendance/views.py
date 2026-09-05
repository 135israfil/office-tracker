"""Settings and holiday calendar API (§35).

Settings are readable by any authenticated user — the employee check-in page needs the
office coordinates and radius — but writable only by admins.
"""

from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.audit import diff, record
from core.models import AuditLog
from core.permissions import IsAdmin

from .models import AppSettings, Holiday
from .serializers import AppSettingsSerializer, HolidaySerializer


class AppSettingsView(APIView):
    """Singleton resource: GET to read, PATCH to update."""

    def get_permissions(self):
        if self.request.method in ("PATCH", "PUT"):
            return [IsAdmin()]
        return [IsAuthenticated()]

    def get(self, request):
        return Response(AppSettingsSerializer(AppSettings.load()).data)

    def patch(self, request):
        instance = AppSettings.load()
        before = AppSettingsSerializer(instance).data

        serializer = AppSettingsSerializer(
            instance, data=request.data, partial=True, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()

        after = AppSettingsSerializer(instance).data
        changes = diff(dict(before), dict(after))
        changes.pop("updated_at", None)
        if changes:
            record(
                request.user,
                AuditLog.Action.SETTINGS_UPDATED,
                target=instance,
                payload={"changes": changes},
            )
        return Response(after)


class HolidayViewSet(viewsets.ModelViewSet):
    serializer_class = HolidaySerializer
    queryset = Holiday.objects.all()

    def get_permissions(self):
        if self.request.method in ("GET", "HEAD", "OPTIONS"):
            return [IsAuthenticated()]
        return [IsAdmin()]

    def get_queryset(self):
        queryset = Holiday.objects.all()
        params = self.request.query_params
        if params.get("year"):
            queryset = queryset.filter(date__year=params["year"])
        if params.get("date_from"):
            queryset = queryset.filter(date__gte=params["date_from"])
        if params.get("date_to"):
            queryset = queryset.filter(date__lte=params["date_to"])
        return queryset

    def perform_create(self, serializer):
        holiday = serializer.save()
        record(
            self.request.user,
            AuditLog.Action.HOLIDAY_CREATED,
            target=holiday,
            payload={"date": str(holiday.date), "name": holiday.name},
        )

    def perform_update(self, serializer):
        before = {"date": str(serializer.instance.date), "name": serializer.instance.name}
        holiday = serializer.save()
        after = {"date": str(holiday.date), "name": holiday.name}
        changes = diff(before, after)
        if changes:
            record(
                self.request.user,
                AuditLog.Action.HOLIDAY_UPDATED,
                target=holiday,
                payload={"changes": changes},
            )

    def perform_destroy(self, instance):
        payload = {"date": str(instance.date), "name": instance.name}
        record(
            self.request.user,
            AuditLog.Action.HOLIDAY_DELETED,
            target_type="Holiday",
            target_id=str(instance.pk),
            payload=payload,
        )
        instance.delete()
