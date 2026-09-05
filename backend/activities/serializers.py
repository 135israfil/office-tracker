"""Validation for agent-submitted activity sessions (§18, §19).

This is a trust boundary. Everything here arrives from a program running on someone's
desk, so nothing is taken on faith: the employee and computer are never read from the
body (they come from the device token), timestamps are sanity-checked against the
server's clock, and the website field is re-validated as a bare domain even though the
agent already truncated it. Defence in depth on §17 is cheap and the failure it prevents
is a privacy incident.
"""

from __future__ import annotations

from rest_framework import serializers

from .models import Activity, ActivityType

# Types an agent may submit. PC_ON and PC_OFF are server-owned — they are derived from
# heartbeats and missed heartbeats, and letting a client assert them would let a broken
# agent rewrite its own uptime.
AGENT_ACTIVITY_TYPES = [
    ActivityType.ACTIVE,
    ActivityType.IDLE,
    ActivityType.APPLICATION,
    ActivityType.WEBSITE,
]

# Anything that means this is a URL, not a domain.
URL_MARKERS = ("/", "?", "#", "@", "\\", " ")

MAX_BATCH_SIZE = 500


class ActivitySessionSerializer(serializers.Serializer):
    """One closed session from the agent."""

    client_event_id = serializers.UUIDField()
    activity_type = serializers.ChoiceField(choices=AGENT_ACTIVITY_TYPES)
    application_name = serializers.CharField(max_length=200, required=False, allow_blank=True)
    executable_name = serializers.CharField(max_length=200, required=False, allow_blank=True)
    website_domain = serializers.CharField(max_length=253, required=False, allow_blank=True)
    start_time = serializers.DateTimeField()
    end_time = serializers.DateTimeField()

    # duration_seconds is deliberately absent: the server derives it from the two
    # timestamps. A client-supplied duration that disagrees with its own start and end
    # is a bug report, not a data point.

    def validate_website_domain(self, value):
        value = (value or "").strip().lower()
        if not value:
            return value
        if any(marker in value for marker in URL_MARKERS):
            # §17: paths, query strings and credentials must never reach storage. The
            # agent truncates before sending; this refuses the request if it ever stops.
            raise serializers.ValidationError("Only a bare domain may be stored, never a URL.")
        # A port is not part of the domain and carries no useful reporting signal.
        host = value.split(":")[0]
        if not host or ".." in host:
            raise serializers.ValidationError("Not a valid domain.")
        return host

    def validate(self, attrs):
        if attrs["end_time"] < attrs["start_time"]:
            raise serializers.ValidationError({"end_time": "End time precedes start time."})

        activity_type = attrs["activity_type"]
        if activity_type == ActivityType.APPLICATION and not attrs.get("application_name"):
            raise serializers.ValidationError(
                {"application_name": "Application sessions need an application name."}
            )
        if activity_type == ActivityType.WEBSITE and not attrs.get("website_domain"):
            raise serializers.ValidationError({"website_domain": "Website sessions need a domain."})
        return attrs


class SyncRequestSerializer(serializers.Serializer):
    """The batch envelope.

    A batch is capped rather than unbounded: an agent that has been offline for a week
    should upload in chunks it can retry, not in one request that times out at the proxy
    and gets replayed whole.
    """

    sessions = serializers.ListField(
        child=serializers.DictField(), allow_empty=True, max_length=MAX_BATCH_SIZE
    )


class ActivitySerializer(serializers.ModelSerializer):
    """Read shape for the activity list. Includes which machine produced the session,
    because "was this the laptop or the desktop?" is the first question anyone asks of a
    row that looks wrong."""

    computer_name = serializers.CharField(source="computer.computer_name", read_only=True)

    class Meta:
        model = Activity
        fields = [
            "id",
            "activity_type",
            "application_name",
            "executable_name",
            "website_domain",
            "start_time",
            "end_time",
            "duration_seconds",
            "computer",
            "computer_name",
            "closed_by_server",
        ]
