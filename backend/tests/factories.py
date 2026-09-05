"""Shared test factories. Later phases add Attendance and Activity factories here."""

import datetime as dt
from decimal import Decimal

import factory
from django.contrib.auth import get_user_model
from django.utils import timezone

from accounts.models import Role
from computers.models import Computer, ComputerStatus, hash_token
from employees.models import Employee, EmployeeShift, EmployeeStatus

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
