"""Office configuration, policy settings and the working-day calendar.

`AppSettings` is the concrete backing for §35 and the home of decisions D4–D8. Every
policy value is read from here at use time; none are duplicated as code constants.
"""

from decimal import Decimal

from django.conf import settings as django_settings
from django.contrib.postgres.fields import ArrayField
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

# Python's date.weekday(): Monday is 0, Sunday is 6. Used consistently everywhere so
# there is never a second convention to translate between.
WEEKDAY_CHOICES = [
    (0, "Monday"),
    (1, "Tuesday"),
    (2, "Wednesday"),
    (3, "Thursday"),
    (4, "Friday"),
    (5, "Saturday"),
    (6, "Sunday"),
]

DEFAULT_WEEKEND_DAYS = [4, 5]  # Friday, Saturday


def default_weekend_days():
    # A callable, not a shared list literal: a mutable default would be shared across
    # every row created in a process.
    return list(DEFAULT_WEEKEND_DAYS)


class AppSettings(models.Model):
    """Singleton. Always accessed through `AppSettings.load()`."""

    SINGLETON_PK = 1

    # --- Office (§5) ---
    office_name = models.CharField(max_length=120, default="Main Office")
    latitude = models.DecimalField(max_digits=9, decimal_places=6, default=0)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, default=0)
    radius_meters = models.PositiveIntegerField(
        default=200, validators=[MinValueValidator(10), MaxValueValidator(50_000)]
    )

    # D2 — §5 asks the company to decide whether a check-in from outside the radius is
    # permitted, so it is a setting rather than a fixed policy.
    #
    # The default is permissive, and deliberately so: distance comes from a phone's GPS,
    # which is wrong often enough that a hard block would lock genuine staff out of their
    # own attendance on a bad fix. Recording and flagging the punch loses nothing — the
    # distance and INSIDE/OUTSIDE status are stored either way, and admins filter on
    # them — whereas a refused check-in leaves no record at all of someone who did turn
    # up. An office that needs the harder rule turns it on knowingly.
    #
    # It governs check-in only. Blocking check-*out* would strand anyone who checked in
    # at their desk and left the building before closing the punch, which is a worse
    # failure than the one it would prevent.
    require_check_in_inside_radius = models.BooleanField(default=False)

    # --- Work schedule (§35) ---
    timezone = models.CharField(
        max_length=64,
        default="Asia/Dhaka",
        help_text="Office-local timezone. Decides which calendar date a punch belongs to.",
    )
    default_start_time = models.TimeField(default="09:00")
    default_end_time = models.TimeField(default="18:00")

    # D4 — admin-configurable weekend
    weekend_days = ArrayField(
        models.PositiveSmallIntegerField(choices=WEEKDAY_CHOICES),
        default=default_weekend_days,
        blank=True,
        help_text="Weekday numbers treated as weekend (Monday=0 … Sunday=6).",
    )

    # D7 — split shifts
    allow_split_shift = models.BooleanField(default=False)

    # D6 — half-day leave
    allow_half_day_leave = models.BooleanField(default=False)

    # --- Activity (§35) ---
    idle_threshold_seconds = models.PositiveIntegerField(
        default=300, validators=[MinValueValidator(60), MaxValueValidator(7200)]
    )
    heartbeat_interval_seconds = models.PositiveIntegerField(
        default=60, validators=[MinValueValidator(15), MaxValueValidator(600)]
    )
    sync_interval_seconds = models.PositiveIntegerField(
        default=60, validators=[MinValueValidator(15), MaxValueValidator(3600)]
    )

    # Fleet kill switch (PLAN.md §5). Turning this off tells every agent to stop
    # collecting at its next config poll, without touching any installation. Agents
    # keep heartbeating while disabled, so the fleet can be switched back on centrally.
    agent_enabled = models.BooleanField(
        default=True,
        help_text="When off, agents stop collecting activity but keep reporting liveness.",
    )

    # D5 — retention. Minimum enforced so nobody can set 0 and wipe everything nightly.
    activity_retention_days = models.PositiveIntegerField(
        default=90,
        validators=[MinValueValidator(7), MaxValueValidator(3650)],
        help_text="Applies to raw activity sessions only. Attendance is never auto-deleted.",
    )

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "settings"
        verbose_name_plural = "settings"

    def __str__(self):
        return f"Settings ({self.office_name})"

    def save(self, *args, **kwargs):
        # Force the singleton pk so a second row cannot be created by accident, and
        # drop force_insert so that `objects.create()` updates the existing row instead
        # of failing on a duplicate key. Writing settings should be idempotent, not a
        # trap that depends on whether the row happens to exist yet.
        self.pk = self.SINGLETON_PK
        kwargs.pop("force_insert", None)
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Settings cannot be deleted.")

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=cls.SINGLETON_PK)
        return obj

    def clean(self):
        errors = {}
        if self.default_start_time and self.default_end_time:
            if self.default_start_time >= self.default_end_time:
                errors["default_end_time"] = "End time must be after start time."

        days = list(self.weekend_days or [])
        if len(set(days)) != len(days):
            errors["weekend_days"] = "Duplicate weekday values."
        if any(day < 0 or day > 6 for day in days):
            errors["weekend_days"] = "Weekday values must be between 0 (Monday) and 6 (Sunday)."
        if len(days) >= 7:
            # Every day a weekend means nobody is ever expected at work, which would
            # make the absentee job a no-op and silently hide a misconfiguration.
            errors["weekend_days"] = "At least one day must be a working day."

        if self.timezone:
            try:
                from zoneinfo import ZoneInfo

                ZoneInfo(self.timezone)
            except Exception:
                errors["timezone"] = f"Unknown timezone: {self.timezone}"

        if errors:
            raise ValidationError(errors)


class Holiday(models.Model):
    """A non-working calendar day. Combined with `AppSettings.weekend_days` (D4) to
    decide whether a date should count toward absence."""

    date = models.DateField(unique=True)
    name = models.CharField(max_length=120)

    class Meta:
        ordering = ["date"]

    def __str__(self):
        return f"{self.date} {self.name}"


class AttendanceStatus(models.TextChoices):
    PRESENT = "PRESENT", "Present"
    LATE = "LATE", "Late"
    ABSENT = "ABSENT", "Absent"
    LEAVE = "LEAVE", "Leave"


class LocationStatus(models.TextChoices):
    INSIDE = "INSIDE", "Inside office"
    OUTSIDE = "OUTSIDE", "Outside office"


class Attendance(models.Model):
    """One row per employee per office-local date: the day-level summary.

    The individual in/out pairs live in AttendancePunch (D7). The denormalised
    first/last/worked/late values here exist so list and report queries do not have to
    aggregate punches for every row.
    """

    employee = models.ForeignKey(
        "employees.Employee", on_delete=models.CASCADE, related_name="attendance"
    )
    date = models.DateField()

    first_check_in_at = models.DateTimeField(null=True, blank=True)
    last_check_out_at = models.DateTimeField(null=True, blank=True)
    worked_seconds = models.PositiveIntegerField(default=0)
    late_minutes = models.PositiveIntegerField(default=0)

    status = models.CharField(
        max_length=16, choices=AttendanceStatus.choices, default=AttendanceStatus.PRESENT
    )
    # D6: kept separate from status so "half-day leave plus a worked afternoon" is
    # representable without a HALF_DAY status that every report would special-case.
    leave_fraction = models.DecimalField(max_digits=2, decimal_places=1, default=Decimal("0.0"))

    # Set when punches could not be matched to shifts, so an admin can look rather than
    # the system silently guessing.
    needs_review = models.BooleanField(default=False)

    is_manually_adjusted = models.BooleanField(default=False)
    adjusted_by = models.ForeignKey(
        django_settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="attendance_adjustments",
    )
    adjustment_note = models.CharField(max_length=300, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-date", "employee_id"]
        constraints = [
            models.UniqueConstraint(
                fields=["employee", "date"], name="unique_attendance_per_employee_day"
            )
        ]
        indexes = [
            models.Index(fields=["-date"]),
            models.Index(fields=["employee", "-date"]),
            models.Index(fields=["status"]),
        ]

    def __str__(self):
        return f"{self.employee.employee_id} {self.date} {self.status}"

    @property
    def open_punch(self):
        return self.punches.filter(check_out_at__isnull=True).order_by("sequence").first()


class AttendancePunch(models.Model):
    """One check-in/check-out pair (D7). A normal day has exactly one."""

    attendance = models.ForeignKey(Attendance, on_delete=models.CASCADE, related_name="punches")
    sequence = models.PositiveSmallIntegerField(default=1)

    check_in_at = models.DateTimeField()
    check_in_latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    check_in_longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    check_in_accuracy_m = models.FloatField(null=True, blank=True)
    check_in_distance_m = models.FloatField(null=True, blank=True)
    check_in_location_status = models.CharField(
        max_length=8, choices=LocationStatus.choices, blank=True
    )

    check_out_at = models.DateTimeField(null=True, blank=True)
    check_out_latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    check_out_longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    check_out_accuracy_m = models.FloatField(null=True, blank=True)
    check_out_distance_m = models.FloatField(null=True, blank=True)
    check_out_location_status = models.CharField(
        max_length=8, choices=LocationStatus.choices, blank=True
    )

    matched_shift = models.ForeignKey(
        "employees.EmployeeShift",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="punches",
    )
    # Snapshot, not a lookup: editing an employee's schedule must not silently rewrite
    # months of late history.
    scheduled_start = models.TimeField(null=True, blank=True)
    late_minutes = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["attendance_id", "sequence"]
        constraints = [
            models.UniqueConstraint(
                fields=["attendance", "sequence"], name="unique_punch_sequence_per_day"
            )
        ]

    def __str__(self):
        return f"punch {self.sequence} on {self.attendance_id}"

    @property
    def duration_seconds(self) -> int:
        if not self.check_out_at:
            return 0
        return int((self.check_out_at - self.check_in_at).total_seconds())
