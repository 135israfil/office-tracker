"""Shared test factories. Later phases add Attendance and Activity factories here."""

import datetime as dt
from decimal import Decimal

import factory
from django.contrib.auth import get_user_model
from django.utils import timezone

from accounts.models import Role
from computers.models import Computer, ComputerStatus, hash_token
from employees.models import Employee, EmployeeShift, EmployeeStatus
from events.models import Event
from notifications.models import Notification
from screenshots.models import ScreenshotCapture
from tasks.models import Task, TaskAssignee
from vault.crypto import encrypt_secret
from vault.models import VaultEntry, VaultEntryGrant

User = get_user_model()


class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = User
        skip_postgeneration_save = True

    email = factory.Sequence(lambda n: f"user{n}@example.com")
    role = Role.EMPLOYEE

    @factory.post_generation
    def password(obj, create, extracted, **kwargs):
        if not create:
            return
        obj.set_password(extracted or "test-password-123")
        obj.save()


class AdminFactory(UserFactory):
    email = factory.Sequence(lambda n: f"admin{n}@example.com")
    role = Role.ADMIN
    is_staff = True


class EmployeeFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Employee
        skip_postgeneration_save = True

    user = factory.SubFactory(UserFactory)
    employee_id = factory.Sequence(lambda n: f"EMP-{n:03d}")
    name = factory.Sequence(lambda n: f"Employee {n}")
    department = "Development"
    designation = "Engineer"
    joining_date = dt.date(2026, 1, 1)
    leave_total = Decimal("12.0")
    leave_used = Decimal("0.0")
    status = EmployeeStatus.ACTIVE

    @factory.post_generation
    def shifts(obj, create, extracted, **kwargs):
        """Give every employee a single default shift, matching how the API seeds them.

        Pass shifts=[(start, end), ...] for a split-shift employee.
        """
        if not create:
            return
        windows = extracted or [(dt.time(9, 0), dt.time(18, 0))]
        for index, (start, end) in enumerate(windows, start=1):
            EmployeeShift.objects.create(
                employee=obj, sequence=index, start_time=start, end_time=end
            )


class ComputerFactory(factory.django.DjangoModelFactory):
    """A registered computer, as it exists after a successful enrolment.

    Tests that care about the enrolment path itself issue their own code; this default
    skips straight to "already registered" because most tests are about what happens
    afterwards.
    """

    class Meta:
        model = Computer

    employee = factory.SubFactory(EmployeeFactory)
    computer_name = factory.Sequence(lambda n: f"DEV-PC-{n:02d}")
    operating_system = "Windows 11"
    agent_version = "0.1.0"
    status = ComputerStatus.OFFLINE
    device_token_hash = factory.Sequence(lambda n: hash_token(f"test-token-{n}"))
    registered_at = factory.LazyFunction(timezone.now)


class TaskFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Task
        skip_postgeneration_save = True

    title = factory.Sequence(lambda n: f"Task {n}")
    created_by = factory.SubFactory(EmployeeFactory)

    @factory.post_generation
    def assignees(obj, create, extracted, **kwargs):
        """Pass assignees=[employee, ...] to assign on creation, assigned by the
        task's own creator — the common case in tests."""
        if not create or not extracted:
            return
        for employee in extracted:
            TaskAssignee.objects.create(task=obj, employee=employee, assigned_by=obj.created_by)


class TaskAssigneeFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = TaskAssignee

    task = factory.SubFactory(TaskFactory)
    employee = factory.SubFactory(EmployeeFactory)
    assigned_by = factory.SubFactory(EmployeeFactory)


class VaultEntryFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = VaultEntry
        skip_postgeneration_save = True

    title = factory.Sequence(lambda n: f"Entry {n}")
    username = factory.Sequence(lambda n: f"user{n}")
    owner = factory.SubFactory(EmployeeFactory)
    secret_ciphertext = factory.LazyFunction(lambda: encrypt_secret("test-password-123"))

    @factory.post_generation
    def grantees(obj, create, extracted, **kwargs):
        """Pass grantees=[employee, ...] to share on creation, granted by the
        entry's own owner — the common case in tests."""
        if not create or not extracted:
            return
        for employee in extracted:
            VaultEntryGrant.objects.create(entry=obj, grantee=employee, granted_by=obj.owner)


class VaultEntryGrantFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = VaultEntryGrant

    entry = factory.SubFactory(VaultEntryFactory)
    grantee = factory.SubFactory(EmployeeFactory)
    granted_by = factory.SubFactory(EmployeeFactory)


class EventFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Event

    title = factory.Sequence(lambda n: f"Event {n}")
    owner = factory.SubFactory(EmployeeFactory)


class NotificationFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Notification

    recipient = factory.SubFactory(EmployeeFactory)
    message = factory.Sequence(lambda n: f"Notification {n}")


class ScreenshotCaptureFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = ScreenshotCapture

    employee = factory.SubFactory(EmployeeFactory)
    computer = factory.SubFactory(ComputerFactory)
    captured_at = factory.LazyFunction(timezone.now)
    file = factory.django.FileField(data=b"not a real png, just test bytes", filename="test.png")
