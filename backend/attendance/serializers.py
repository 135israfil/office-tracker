from rest_framework import serializers

from .models import AppSettings, Holiday


class AppSettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = AppSettings
        fields = [
            "office_name",
            "latitude",
            "longitude",
            "radius_meters",
            "require_check_in_inside_radius",
            "timezone",
            "default_start_time",
            "default_end_time",
            "weekend_days",
            "allow_split_shift",
            "allow_half_day_leave",
            "idle_threshold_seconds",
            "heartbeat_interval_seconds",
            "sync_interval_seconds",
            "agent_enabled",
            "activity_retention_days",
            "updated_at",
        ]
        read_only_fields = ["updated_at"]

    def validate(self, attrs):
        # Run the model's own clean() so the API and the admin enforce identical rules
        # instead of drifting apart.
        instance = self.instance or AppSettings.load()
        for field, value in attrs.items():
            setattr(instance, field, value)
        instance.full_clean(exclude=["id"])
        return attrs

    def validate_activity_retention_days(self, value):
        current = (self.instance or AppSettings.load()).activity_retention_days
        if value < current:
            # Not a rejection: shortening retention is legitimate, but it permanently
            # destroys data, so the client must confirm rather than do it by accident.
            request = self.context.get("request")
            confirmed = str(
                request.data.get("confirm_shorter_retention") if request else ""
            ).lower() in {"true", "1", "yes"}
            if not confirmed:
                raise serializers.ValidationError(
                    f"Shortening retention from {current} to {value} days permanently "
                    "deletes activity outside the new window. Resend with "
                    "confirm_shorter_retention=true to proceed."
                )
        return value


class HolidaySerializer(serializers.ModelSerializer):
    class Meta:
        model = Holiday
        fields = ["id", "date", "name"]
