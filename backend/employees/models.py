"""Employee records, work shifts and leave balance (§4, §10).

Two model choices worth knowing about:

* Work hours live in `EmployeeShift` rows rather than two columns on `Employee` (D7), so
  a split-shift employee is just an employee with two rows and the late-minute logic
  loops instead of branching.
* Leave is `Decimal` in 0.5 steps (D6), and `leave_remaining` is derived, never stored,
  so the displayed balance cannot drift out of sync with its inputs.
"""

from decimal import Decimal

from django.conf import settings as django_settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models


class EmployeeStatus(models.TextChoices):
    ACTIVE = "ACTIVE", "Active"
    INACTIVE = "INACTIVE", "Inactive"


class Employee(models.Model):
    user = models.OneToOneField(
        django_settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="employee"
    )
    employee_id = models.CharField(max_length=32, unique=True)
    name = models.CharField(max_length=120)
    phone = models.CharField(max_length=32, blank=True)
    department = models.CharField(max_length=80, blank=True)
    designation = models.CharField(max_length=80, blank=True)
    joining_date = models.DateField(null=True, blank=True)

    # D6 — half-day granularity means these cannot be integers.
    leave_total = models.DecimalField(
        max_digits=5, decimal_places=1, default=Decimal("0.0"), validators=[MinValueValidator(0)]
    )
    leave_used = models.DecimalField(
        max_digits=5, decimal_places=1, default=Decimal("0.0"), validators=[MinValueValidator(0)]
    )

    status = models.CharField(
        max_length=16, choices=EmployeeStatus.choices, default=EmployeeStatus.ACTIVE
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["employee_id"]
        indexes = [
            models.Index(fields=["department"]),
            models.Index(fields=["status"]),
        ]

    def __str__(self):
        return f"{self.employee_id} {self.name}"

    @property
    def leave_remaining(self) -> Decimal:
        return self.leave_total - self.leave_used

    @property
    def is_active(self) -> bool:
        return self.status == EmployeeStatus.ACTIVE

    @property
    def is_split_shift(self) -> bool:
        return self.shifts.count() > 1

    def clean(self):
        if self.leave_used > self.leave_total:
            raise ValidationError({"leave_used": "Leave used cannot exceed the total balance."})


class EmployeeShift(models.Model):
    """One work window. A single row is a normal employee; two rows is a split shift (D7)."""

    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="shifts")
    sequence = models.PositiveSmallIntegerField(default=1)
    start_time = models.TimeField()
    end_time = models.TimeField()

    class Meta:
        ordering = ["employee_id", "sequence"]
        constraints = [
            models.UniqueConstraint(
                fields=["employee", "sequence"], name="unique_shift_sequence_per_employee"
            )
        ]

    def __str__(self):
        return (
            f"{self.employee.employee_id} shift {self.sequence}: {self.start_time}-{self.end_time}"
        )

    def clean(self):
        if self.start_time and self.end_time and self.start_time >= self.end_time:
            # Overnight shifts are out of MVP scope; §8's late calculation assumes a
            # shift starts and ends on the same calendar day.
            raise ValidationError({"end_time": "Shift end must be after its start."})


class LeaveAdjustment(models.Model):
    """Append-only record of every change to a leave balance (§10).

    Without this, a balance is just a number nobody can explain. `target` distinguishes
    granting entitlement from consuming it, so marking someone on leave in Phase 3 uses
    the same trail rather than a parallel mechanism.
    """

    class Target(models.TextChoices):
        TOTAL = "TOTAL", "Total entitlement"
        USED = "USED", "Leave used"

    employee = models.ForeignKey(
        Employee, on_delete=models.CASCADE, related_name="leave_adjustments"
    )
    target = models.CharField(max_length=8, choices=Target.choices, default=Target.TOTAL)
    delta = models.DecimalField(max_digits=5, decimal_places=1)
    reason = models.CharField(max_length=200, blank=True)
    created_by = models.ForeignKey(
        django_settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="leave_adjustments_made",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self):
        sign = "+" if self.delta >= 0 else ""
        return f"{self.employee.employee_id} {self.target} {sign}{self.delta}"
