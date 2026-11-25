"""Task tracking: the model rules, and the same data-isolation exit criterion
test_dashboards.py enforces for activity data, applied here to tasks.
"""

from __future__ import annotations

import datetime as dt

import pytest
from django.core.exceptions import ValidationError
from rest_framework.test import APIClient

from notifications.models import Notification
from tasks.models import Task, TaskStatus, task_is_overdue
from tests.factories import AdminFactory, EmployeeFactory, TaskFactory

# --- Pure logic ---------------------------------------------------------------


class TestIsOverdue:
    def test_a_task_past_its_deadline_is_overdue(self):
        assert task_is_overdue(dt.date(2026, 1, 1), TaskStatus.TODO, dt.date(2026, 1, 2)) is True

    def test_a_task_due_today_is_not_yet_overdue(self):
        assert task_is_overdue(dt.date(2026, 1, 2), TaskStatus.TODO, dt.date(2026, 1, 2)) is False

    def test_a_task_with_no_deadline_is_never_overdue(self):
        assert task_is_overdue(None, TaskStatus.TODO, dt.date(2026, 1, 2)) is False

    def test_a_done_task_is_never_overdue_whatever_its_deadline(self):
        assert task_is_overdue(dt.date(2026, 1, 1), TaskStatus.DONE, dt.date(2026, 1, 2)) is False

    def test_a_cancelled_task_is_never_overdue_whatever_its_deadline(self):
        assert (
            task_is_overdue(dt.date(2026, 1, 1), TaskStatus.CANCELLED, dt.date(2026, 1, 2)) is False
        )


# --- Model rules ----------------------------------------------------------------


@pytest.mark.django_db
class TestOneLevelDepth:
    def test_a_sub_task_cannot_itself_have_sub_tasks(self):
        root = TaskFactory()
        child = TaskFactory(parent=root)
        grandchild = Task(title="too deep", created_by=child.created_by, parent=child)
        with pytest.raises(ValidationError):
            grandchild.clean()

    def test_a_task_may_be_a_sub_task_of_a_root_task(self):
        root = TaskFactory()
        # Does not raise.
        Task(title="fine", created_by=root.created_by, parent=root).clean()


# --- API: data isolation (mirrors TestEmployeeIsolation in test_dashboards.py) ---


@pytest.fixture
def admin_client(db):
    admin = AdminFactory()
    client = APIClient()
    client.force_authenticate(user=admin)
    return client, admin


def client_for(employee):
    client = APIClient()
    client.force_authenticate(user=employee.user)
    return client


@pytest.mark.django_db
class TestTaskIsolation:
    def test_unauthenticated_is_refused(self):
        task = TaskFactory()
        assert APIClient().get(f"/api/tasks/{task.pk}/").status_code == 401

    def test_an_uninvolved_employee_cannot_see_the_task(self):
        alice = EmployeeFactory()
        task = TaskFactory()  # created by someone else entirely
        response = client_for(alice).get(f"/api/tasks/{task.pk}/")
        assert response.status_code == 404

    def test_the_creator_sees_their_own_task(self):
        task = TaskFactory()
        assert client_for(task.created_by).get(f"/api/tasks/{task.pk}/").status_code == 200

    def test_a_sub_tasks_own_detail_page_is_reachable_directly(self):
        # A plain GET /tasks/<id>/ for a sub-task carries no ?parent= param — the
        # list view's "top-level only by default" filter must not apply here, or
        # every sub-task's own detail page 404s for its own creator.
        root = TaskFactory()
        child = TaskFactory(parent=root, created_by=root.created_by)
        response = client_for(root.created_by).get(f"/api/tasks/{child.pk}/")
        assert response.status_code == 200

    def test_an_assignee_who_is_not_the_creator_sees_the_task(self):
        bob = EmployeeFactory()
        task = TaskFactory(assignees=[bob])
        assert client_for(bob).get(f"/api/tasks/{task.pk}/").status_code == 200

    def test_an_admin_sees_everything(self, admin_client):
        client, _ = admin_client
        task = TaskFactory()
        assert client.get(f"/api/tasks/{task.pk}/").status_code == 200

    def test_a_creator_with_zero_assignees_still_sees_their_own_task(self):
        task = TaskFactory()
        body = client_for(task.created_by).get("/api/tasks/").json()
        assert body["count"] == 1

    def test_the_list_excludes_tasks_created_by_someone_else(self):
        alice = EmployeeFactory()
        TaskFactory()  # someone else's task
        body = client_for(alice).get("/api/tasks/").json()
        assert body["count"] == 0


@pytest.mark.django_db
class TestAssignableEmployees:
    """A non-admin employee needs to see who exists to assign a task to — unlike
    EmployeeViewSet, which is admin-only and exposes full HR fields."""

    def test_an_ordinary_employee_can_list_assignable_employees(self):
        alice = EmployeeFactory(name="Alice")
        EmployeeFactory(name="Bob")
        response = client_for(alice).get("/api/tasks/assignable-employees/")
        assert response.status_code == 200
        names = {row["name"] for row in response.json()}
        assert names == {"Alice", "Bob"}

    def test_only_minimal_fields_are_exposed(self):
        alice = EmployeeFactory()
        response = client_for(alice).get("/api/tasks/assignable-employees/")
        assert set(response.json()[0].keys()) == {"id", "employee_id", "name"}

    def test_unauthenticated_is_refused(self):
        assert APIClient().get("/api/tasks/assignable-employees/").status_code == 401


# --- API: status transitions and lifecycle rules ---------------------------------


@pytest.mark.django_db
class TestStatusAndLifecycle:
    def test_an_assignee_may_move_status_between_ordinary_states(self):
        bob = EmployeeFactory()
        task = TaskFactory(assignees=[bob])
        response = client_for(bob).patch(
            f"/api/tasks/{task.pk}/", {"status": TaskStatus.IN_PROGRESS}, format="json"
        )
        assert response.status_code == 200
        assert response.json()["status"] == TaskStatus.IN_PROGRESS

    def test_a_non_creator_assignee_cannot_cancel_the_task(self):
        bob = EmployeeFactory()
        task = TaskFactory(assignees=[bob])
        response = client_for(bob).patch(
            f"/api/tasks/{task.pk}/", {"status": TaskStatus.CANCELLED}, format="json"
        )
        assert response.status_code == 403

    def test_the_creator_may_cancel_the_task(self):
        task = TaskFactory()
        response = client_for(task.created_by).patch(
            f"/api/tasks/{task.pk}/", {"status": TaskStatus.CANCELLED}, format="json"
        )
        assert response.status_code == 200

    def test_self_removal_succeeds(self):
        bob = EmployeeFactory()
        task = TaskFactory(assignees=[bob])
        response = client_for(bob).delete(f"/api/tasks/{task.pk}/assignees/{bob.pk}/")
        assert response.status_code == 200
        assert task.assignees.count() == 0

    def test_the_removal_response_itself_reflects_the_new_state(self):
        # Not just the database afterward: get_object()'s prefetch_related cache on
        # the task instance is not invalidated by a bare .filter().delete(), so the
        # response serialized from that same instance could silently show the
        # assignee who was just removed.
        bob = EmployeeFactory()
        task = TaskFactory(assignees=[bob])
        response = client_for(bob).delete(f"/api/tasks/{task.pk}/assignees/{bob.pk}/")
        assert response.json()["assignees"] == []

    def test_the_add_assignee_response_itself_reflects_the_new_state(self):
        # Same staleness risk in the other direction: TaskAssignee.objects.create()
        # does not update the prefetch cache either.
        task = TaskFactory()
        bob = EmployeeFactory()
        response = client_for(task.created_by).post(
            f"/api/tasks/{task.pk}/add_assignee/", {"employee": bob.pk}, format="json"
        )
        assert [a["employee"]["id"] for a in response.json()["assignees"]] == [bob.pk]

    def test_removing_another_assignee_as_a_non_creator_non_admin_fails(self):
        bob = EmployeeFactory()
        carol = EmployeeFactory()
        task = TaskFactory(assignees=[bob, carol])
        response = client_for(bob).delete(f"/api/tasks/{task.pk}/assignees/{carol.pk}/")
        assert response.status_code == 403
        assert task.assignees.filter(employee=carol).exists()

    def test_the_creator_may_remove_any_assignee(self):
        bob = EmployeeFactory()
        task = TaskFactory(assignees=[bob])
        response = client_for(task.created_by).delete(f"/api/tasks/{task.pk}/assignees/{bob.pk}/")
        assert response.status_code == 200

    def test_deleting_a_parent_task_cascades_to_its_sub_tasks(self):
        root = TaskFactory()
        child = TaskFactory(parent=root, created_by=root.created_by)
        response = client_for(root.created_by).delete(f"/api/tasks/{root.pk}/")
        assert response.status_code == 204
        assert not Task.objects.filter(pk=child.pk).exists()

    def test_a_non_creator_assignee_cannot_delete_the_task(self):
        bob = EmployeeFactory()
        task = TaskFactory(assignees=[bob])
        assert client_for(bob).delete(f"/api/tasks/{task.pk}/").status_code == 403

    def test_creating_a_sub_task_of_a_sub_task_is_rejected(self):
        root = TaskFactory()
        child = TaskFactory(parent=root, created_by=root.created_by)
        response = client_for(root.created_by).post(
            "/api/tasks/",
            {"title": "too deep", "parent": child.pk, "assignees": []},
            format="json",
        )
        assert response.status_code == 400

    def test_an_uninvolved_employee_cannot_attach_a_sub_task_to_someone_elses_task(self):
        alice = EmployeeFactory()
        root = TaskFactory()  # created by someone else, alice has no relationship to it
        response = client_for(alice).post(
            "/api/tasks/",
            {"title": "unwanted sub-task", "parent": root.pk, "assignees": []},
            format="json",
        )
        assert response.status_code == 400
        assert not root.subtasks.exists()

    def test_an_assignee_of_the_parent_may_attach_a_sub_task(self):
        bob = EmployeeFactory()
        root = TaskFactory(assignees=[bob])
        response = client_for(bob).post(
            "/api/tasks/",
            {"title": "a sub-task bob adds", "parent": root.pk, "assignees": []},
            format="json",
        )
        assert response.status_code == 201


# --- Notifications ---------------------------------------------------------------


@pytest.mark.django_db
class TestNotifications:
    def test_assigning_at_creation_notifies_the_assignee(self):
        creator = EmployeeFactory()
        bob = EmployeeFactory()
        client_for(creator).post(
            "/api/tasks/",
            {"title": "New task", "assignees": [bob.pk]},
            format="json",
        )
        notification = Notification.objects.get(recipient=bob)
        assert "New task" in notification.message

    def test_assigning_yourself_at_creation_does_not_notify_you(self):
        creator = EmployeeFactory()
        client_for(creator).post(
            "/api/tasks/",
            {"title": "New task", "assignees": [creator.pk]},
            format="json",
        )
        assert not Notification.objects.exists()

    def test_add_assignee_notifies_the_added_employee(self):
        task = TaskFactory()
        bob = EmployeeFactory()
        client_for(task.created_by).post(
            f"/api/tasks/{task.pk}/add_assignee/", {"employee": bob.pk}, format="json"
        )
        notification = Notification.objects.get(recipient=bob)
        assert task.title in notification.message

    def test_a_status_change_notifies_the_creator_and_other_assignees(self):
        bob = EmployeeFactory()
        carol = EmployeeFactory()
        task = TaskFactory(assignees=[bob, carol])
        client_for(bob).patch(
            f"/api/tasks/{task.pk}/", {"status": TaskStatus.IN_PROGRESS}, format="json"
        )
        recipients = set(Notification.objects.values_list("recipient_id", flat=True))
        assert recipients == {task.created_by_id, carol.pk}
        assert bob.pk not in recipients

    def test_a_non_status_edit_does_not_notify_anyone(self):
        bob = EmployeeFactory()
        task = TaskFactory(assignees=[bob])
        client_for(bob).patch(f"/api/tasks/{task.pk}/", {"title": "Renamed"}, format="json")
        assert not Notification.objects.exists()
