# Task Tracking

*   **Author:** Israfil
*   **Status:** Draft
*   **Date:** 2026-11-21

--------------------------------------------------------------------------------

## Overview

A task/ticket-tracking feature for the existing employee attendance and PC
activity tracking system. Any authenticated user can create a task, assign it
to one or more people, and break it into sub-tasks that can be reassigned to
anyone, including the assignee. There is no separate "Project" entity — the
task/sub-task relationship is the only grouping mechanism. Visibility follows
the same strict per-employee isolation this system already enforces for
attendance and activity data. Notifications and reminders are out of scope
for this design.

This feature was reviewed by seven independent lenses during brainstorming
(see `concepts_brief.md`). One of those reviews raised a Blocker-severity
objection that this document does not resolve: every other feature in this
system is one-directional (an admin observes an employee), while task
tracking is bidirectional and peer-collaborative — a different
job-to-be-done. That question is carried forward below as the first Open
Question rather than settled here.

## The Problem

This system currently has no way for employees or admins to create, assign,
or track discrete units of work. Every existing feature — GPS attendance, PC
activity sessions, admin dashboards — is about observing what already
happened, not organizing what needs to happen next. Teams using this system
for people-management (it already knows who the employees are, their roles,
and their departments) have no connected way to assign and follow up on work
items; that information currently lives, if anywhere, in a disconnected tool
(chat, spreadsheets, verbal handoffs) with no link back to the employee
records this system already maintains.

## Goals

*   Any authenticated user (admin or employee) can create a task.
*   A task supports multiple simultaneous assignees, modeled so that
    per-assignee state (who assigned whom, when) can be tracked.
*   A task can have sub-tasks, one level deep, each independently assignable
    to anyone, including the assignee themselves.
*   A task may carry an optional deadline, with overdue status computed and
    surfaced at read time (no push or email notification).
*   Visibility enforces the same strict per-employee isolation this system
    already applies to attendance and activity data: an employee sees only
    tasks and sub-tasks they created or are assigned to; admins see
    everything, across all employees.

## Non-Goals

*   No separate "Project" or "Team" entity grouping tasks (deferred; adding
    one later is a cheap, additive change if real usage demands it).
*   No explicit blocking dependencies between unrelated tasks (e.g. "Task B
    can't start until Task A is done") — the task/sub-task relationship is
    the only structural relationship.
*   No sub-task nesting beyond one level (a sub-task cannot itself have
    sub-tasks in this design).
*   No push notifications, email alerts, or any background job queue or
    scheduled-reminder mechanism.

## Open Questions

*   **Product fit**: Should this feature live in this codebase as designed,
    or does its peer-collaborative shape (a genuine first for this system)
    warrant its own bounded app or permission module rather than reuse of
    the existing admin-centric permission classes? Raised at Blocker
    severity during brainstorming; not resolved by this document.

Resolved since the previous draft (see Detailed Implementation below):
status values and transition authority, delete/cascade authority,
self-unassignment and removal authority, visibility on removal, zero-assignee
tasks, and deadline precision/timezone.

--------------------------------------------------------------------------------

## Technical Plan (Architecture)

This follows the existing one-app-per-domain structure already used by
`accounts`, `activities`, `attendance`, `computers`, `core`, and `employees`:
a new Django app, `tasks`, holding the models, permissions, serializers, and
views for this feature, plus a matching Vue route and views on the frontend.

### Data model

Two new models, both in the new `tasks` app:

*   **`Task`** — `title`, `description` (blank-allowed text), `deadline`
    (nullable `DateField` — a bare date, not a timestamp, evaluated against
    the office-local date as described in Detailed Implementation), `status`
    (a `TextChoices` field with five values: TODO, IN_PROGRESS, BLOCKED,
    DONE, CANCELLED — following the same pattern as
    `EmployeeStatus`/`AttendanceStatus` elsewhere in this codebase),
    `created_by` (FK to `Employee`), `parent` (FK to `self`, nullable),
    `created_at`/`updated_at` (`auto_now_add`/`auto_now`, matching
    `Employee`'s own timestamp fields).

    The one-level depth limit (a Non-Goal above) is enforced in the model's
    `clean()`, the same place `AppSettings.clean()` already enforces
    cross-field rules in this codebase: a `Task` may only be set as another
    task's `parent` if its own `parent` is `None`. This single rule also
    removes the need for any separate cycle-detection logic, since a cycle
    would require a root task to become a sub-task of its own child, which
    this rule makes structurally impossible.

*   **`TaskAssignee`** — the through-model for the task/assignee
    relationship, rather than a bare `ManyToManyField`: `task` (FK),
    `employee` (FK), `assigned_by` (FK to `Employee`), `assigned_at`
    (`auto_now_add`), with a `unique_together` on `(task, employee)`. Using
    an explicit through-model now avoids a breaking migration later if
    per-assignee state (acknowledgement, individual completion) is ever
    needed — converting a bare M2M to a through-model after the fact touches
    every caller of `.assignees.add()`/`.set()`.

### Visibility and permissions

A new permission class is needed — `IsAdmin` and `IsAdminOrReadOnlySelf`
both assume an employee is either locked out entirely or read-only of their
own data, and this is the first feature in this codebase where an ordinary
employee needs write access to a resource that also involves other people.

Visibility is enforced the same way `activities/views.py`'s
`resolve_employee()` already enforces it for activity data — in the
queryset, not only the permission class, so a view that forgets a permission
check still cannot leak:

```text
# Employees: own + assigned tasks only. Admins: unfiltered.
Task.objects.filter(
    Q(created_by=employee) | Q(assignees=employee)
).distinct()
```

The `.distinct()` is required because the `assignees` leg joins through
`TaskAssignee`; without it, a task with multiple matching assignee rows
would appear more than once in the result set.

Sub-tasks are **not** filtered by inheriting their parent's visibility —
every reviewer who considered this during brainstorming converged on the
same conclusion, since Django has no native recursive-query support and a
Python-side walk up the parent chain risks N+1 queries. A sub-task has its
own independent `created_by`/`TaskAssignee` rows and is visible under the
exact same query above. To avoid an assignee seeing a sub-task with no
context at all, the sub-task's serializer includes a minimal parent stub
(`id` and `title` only) regardless of whether the viewer can see the full
parent task.

### API shape

A single `TaskViewSet` (list, retrieve, create, update, destroy) under
`/api/tasks/`, with sub-tasks addressed as ordinary `Task` rows filtered by
`?parent=<id>`, rather than a separate nested resource — this keeps one
viewset and one permission/visibility path for both tasks and sub-tasks,
instead of two code paths that could drift apart. Assignee management
(adding/removing a `TaskAssignee` row) is a nested action on the same
viewset, following the pattern `AttendanceViewSet.correct_punch` already
uses in this codebase for a sub-operation on a resource.

### Data flow

```text
Employee/Admin                 TaskViewSet                  Database
     |                              |                            |
     |-- POST /api/tasks/  ------->|                            |
     |   {title, assignees[],      |-- validate assignees exist->|
     |    parent?, deadline?}      |   (Employee rows)          |
     |                              |-- Task.full_clean()        |
     |                              |   (enforces 1-level depth) |
     |                              |-- save Task + TaskAssignee |
     |                              |   rows ------------------->|
     |<-- 201 {task, assignees} ---|                            |
     |                              |                            |
     |-- GET /api/tasks/?parent=X ->|                            |
     |                              |-- Task.objects.filter(     |
     |                              |     Q(created_by=emp)      |
     |                              |     | Q(assignees=emp)     |
     |                              |   ).distinct() ----------->|
     |<-- 200 [tasks + is_overdue] -|                            |
```

### Frontend

A new `/tasks` route in `frontend/src/router/index.js`, gated by
`meta.requiresAuth` only (not `requiresAdmin` — unlike most existing routes,
this one is for both roles), with a list view and a detail/create view
following the existing `api/client.js` `request()` pattern used throughout
the rest of the frontend. The task list surfaces the read-time `is_overdue`
indicator from the API directly (sorted overdue-first), rather than
computing urgency client-side, so the server's
office-timezone handling stays the single source of truth for what counts as
"overdue."

--------------------------------------------------------------------------------

## Alternatives Considered

### Alternative A: Single-assignee task model

*   **Pros**: A single nullable `assigned_to` FK is simpler than a
    through-table, trivially matches the existing `Attendance`-style FK +
    queryset-filter idiom already used elsewhere in this codebase, and
    avoids the `.distinct()` pitfall entirely.
*   **Cons**: Cannot represent a task genuinely co-owned by more than one
    person without forcing it into a creator-plus-one-sub-task-per-person
    shape.
*   **Reason for Rejection**: Rejected by author: multi-assignee support was
    an explicit requirement stated during brainstorming, before the
    scope/YAGNI review's later recommendation to simplify to single-assignee
    was raised.

### Alternative B: Sub-task visibility inherited from the parent task

*   **Pros**: Simpler mental model for end users — "I can see the whole task
    tree I'm part of" — with fewer visibility rules to document and explain.
*   **Cons**: Django has no native recursive-query (CTE) support, so this
    either requires an added dependency or a Python-side walk up the parent
    chain that risks N+1 queries at scale; it also doesn't resolve the case
    of a sub-task assignee who has no relationship to the parent's own
    assignee list.
*   **Reason for Rejection**: Technical rejection raised independently by
    multiple reviewers during brainstorming — no existing precedent for
    recursive visibility queries in this codebase, and the performance/
    complexity cost outweighs the UX gain once a lightweight parent stub
    (id + title) is shown for context instead.

### Alternative C: Bare `ManyToManyField` for task assignees

*   **Pros**: Fewer lines to declare initially than an explicit through-model
    with its own fields.
*   **Cons**: Cannot record who assigned whom or when without a later
    migration; converting a bare M2M to a through-model after the fact
    requires rewriting every caller of `.assignees.add()`/`.set()`.
*   **Reason for Rejection**: Technical rejection — the per-assignee metadata
    (`assigned_by`, `assigned_at`) is foreseeable now and effectively free to
    add at the start; retrofitting it later is not.

### Alternative D: Build full notification infrastructure (email/push) now

*   **Pros**: Would make deadlines immediately actionable via proactive
    reminders, closing the "decorative deadline" gap completely instead of
    partially.
*   **Cons**: Requires building an email backend and a background job queue
    from scratch — infrastructure nothing else in this codebase needs today
    — as a speculative investment with no other consumer.
*   **Reason for Rejection**: Rejected by author: notifications were
    explicitly deferred during brainstorming scoping, in favor of a
    read-time-computed overdue indicator that captures most of the value
    with no new infrastructure.

--------------------------------------------------------------------------------

## Non-Functional Requirements

*   **Security & Privacy**: Task content (titles, descriptions) is
    employee-authored free text, not covered by this codebase's existing
    §31-style activity-monitoring privacy rules, but still subject to the
    same per-employee isolation enforced at the queryset level, never only
    the permission class (see Technical Plan).
*   **Performance**: The visibility query (`Q(created_by=emp) |
    Q(assignees=emp)).distinct()`) is a single indexed query per request;
    add a composite index on `TaskAssignee(employee, task)` and on
    `Task(created_by)` to keep it cheap as task volume grows. Sub-task
    lookups by `?parent=<id>` should index `Task(parent)`.
*   **Rollout**: Purely additive — a new app, new tables, a new frontend
    route. No existing model, endpoint, or migration is touched, so this
    ships independently of any other work in flight and needs no feature
    flag.

--------------------------------------------------------------------------------

## Detailed Implementation Plan

Decisions resolved during drafting, carried into the plan below: status is
`TODO` / `IN_PROGRESS` / `BLOCKED` / `DONE` / `CANCELLED`; any assignee may
set any status except `CANCELLED`, which is creator/admin-only; a task may be
deleted by its creator or an admin, and deleting a parent task cascades to
its sub-tasks; an assignee may remove themselves at any time, but removing
someone else requires being the creator or an admin; removal from a task
means immediate loss of visibility (no assignment-history table); a task may
have zero assignees and simply falls back to creator+admin visibility under
the existing query, with no extra rule needed; deadline is a date (not a
date-and-time), evaluated against the existing office-timezone setting
already used for attendance.

### Target Files to Create/Modify

#### 1. `backend/tasks/__init__.py` (Create)

*   **Type / Scope**: Python package marker.
*   **Proposed Changes**: Empty, matching every other app's `__init__.py`.

#### 2. `backend/tasks/apps.py` (Create)

*   **Type / Scope**: Django app config.
*   **Proposed Changes**: `TasksConfig(AppConfig)` with `default_auto_field`
    and `name = "tasks"`, matching `EmployeesConfig`/`ActivitiesConfig`.

#### 3. `backend/tasks/models.py` (Create)

*   **Type / Scope**: Django models.
*   **Proposed Changes**:
    *   `TaskStatus(TextChoices)`: `TODO`, `IN_PROGRESS`, `BLOCKED`, `DONE`,
        `CANCELLED` — following the same `TextChoices` pattern as
        `EmployeeStatus`/`AttendanceStatus`.
    *   `Task`: `title` (CharField), `description` (TextField, blank=True),
        `status` (CharField with `TaskStatus.choices`, default `TODO`),
        `deadline` (`DateField`, null=True, blank=True), `created_by` (FK to
        `employees.Employee`, `on_delete=PROTECT` — an employee record must
        not silently vanish out from under tasks they created), `parent`
        (FK to `self`, null=True, blank=True, `on_delete=CASCADE`,
        `related_name="subtasks"`), `created_at`/`updated_at`
        (`auto_now_add`/`auto_now`).
    *   `Task.clean()`: raises `ValidationError` if `parent` is set and
        `parent.parent_id` is not `None` — enforces the one-level depth
        limit and, as a side effect, makes a cycle structurally impossible
        (see Technical Plan).
    *   `is_overdue` property (pure, no DB access): `self.deadline is not
        None and self.status not in (DONE, CANCELLED) and self.deadline <
        office_local_today()` — reuses `attendance.calendar_rules.local_date`
        (via today's instant) for the office-timezone-aware "today," rather
        than a naive `date.today()`.
    *   `TaskAssignee`: `task` (FK to `Task`, `on_delete=CASCADE`,
        `related_name="assignees"`), `employee` (FK to `employees.Employee`,
        `on_delete=CASCADE`), `assigned_by` (FK to `employees.Employee`,
        `on_delete=PROTECT`), `assigned_at` (`auto_now_add`). Meta:
        `unique_together = ("task", "employee")`.

#### 4. `backend/tasks/migrations/__init__.py` (Create)

*   **Type / Scope**: Migrations package marker.
*   **Proposed Changes**: Empty.

#### 5. `backend/tasks/migrations/0001_initial.py` (Create)

*   **Type / Scope**: Django migration.
*   **Proposed Changes**: Generated by `python manage.py makemigrations
    tasks` from the models above — not hand-written. Creates the `Task` and
    `TaskAssignee` tables and the indexes named under Non-Functional
    Requirements.

#### 6. `backend/tasks/admin.py` (Create)

*   **Type / Scope**: Django admin registration.
*   **Proposed Changes**: Register `Task` and `TaskAssignee` with a basic
    `ModelAdmin` (list display, search fields on title/employee), matching
    `EmployeeAdmin`/`ComputerAdmin` — gives admins a backstop management UI
    independent of the new frontend views.

#### 7. `backend/tasks/permissions.py` (Create)

*   **Type / Scope**: DRF permission class.
*   **Proposed Changes**: `IsTaskParticipantOrAdmin` — admins always pass;
    non-admins pass `has_permission` (any authenticated user may list/create);
    `has_object_permission` requires the requesting employee to be the
    creator or a current assignee for read/update, the creator for delete,
    and additionally blocks a non-admin, non-creator assignee from setting
    `status=CANCELLED` (checked here or in the serializer's `validate_status`
    — whichever keeps the rule in one place once written). This is a new
    permission shape for this codebase (see Technical Plan) — it is not an
    extension of `IsAdmin`/`IsAdminOrReadOnlySelf`.

#### 8. `backend/tasks/serializers.py` (Create)

*   **Type / Scope**: DRF serializers.
*   **Proposed Changes**: `TaskAssigneeSerializer` (employee id/name,
    `assigned_by`, `assigned_at`, read-only). `TaskSerializer`: `id`,
    `title`, `description`, `status`, `deadline`, `is_overdue`
    (`SerializerMethodField`, delegating to the model property), `created_by`
    (read-only), `assignees` (nested `TaskAssigneeSerializer`, read-only —
    written via the dedicated assignee actions below, not by editing the
    list in place), `parent` (writable on create only, validated against the
    one-level-depth rule via the model's `clean()`), `parent_stub`
    (`SerializerMethodField` returning `{"id": ..., "title": ...}` when
    `parent_id` is set, regardless of whether the viewer can see the full
    parent task), `created_at`/`updated_at`.

#### 9. `backend/tasks/views.py` (Create)

*   **Type / Scope**: DRF viewset.
*   **Proposed Changes**: `TaskViewSet(ModelViewSet)` with
    `permission_classes = [IsAuthenticated, IsTaskParticipantOrAdmin]`.
    `get_queryset()` implements the visibility filter from the Technical
    Plan (admins unfiltered; employees via `Q(created_by=emp) |
    Q(assignees__employee=emp)).distinct()`), with optional `?parent=<id>`
    filtering for sub-tasks. `perform_create()` sets `created_by` from
    `request.user.employee`, validates every assignee id in the request
    body resolves to a real `Employee`, and creates the initial
    `TaskAssignee` rows with `assigned_by=request.user.employee`.
    `perform_destroy()` is reachable only for the creator or an admin (the
    permission class already enforces this); cascading deletion of
    sub-tasks is handled at the database level by `on_delete=CASCADE`, no
    extra view code needed. Two extra routed actions: `add_assignee` (POST,
    any current assignee or the creator may add; validates the target
    employee isn't already assigned) and `remove_assignee` (DELETE, allowed
    for self-removal by the target themselves, or for the creator/an admin
    removing someone else — per the resolved rule above).

#### 10. `backend/tasks/urls.py` (Create)

*   **Type / Scope**: URL routing.
*   **Proposed Changes**: DRF `DefaultRouter` registering `TaskViewSet` at
    `tasks`, matching the per-app `urls.py` pattern already used by
    `reports/urls.py`.

#### 11. `backend/config/settings.py` (Modify)

*   **Type / Scope**: Django settings.
*   **Proposed Changes**: Add `"tasks"` to `INSTALLED_APPS`.

#### 12. `backend/config/urls.py` (Modify)

*   **Type / Scope**: Root URL configuration.
*   **Proposed Changes**: `include("tasks.urls")` under the existing
    `/api/` prefix, alongside the other apps' includes.

#### 13. `backend/tests/factories.py` (Modify)

*   **Type / Scope**: Test factories.
*   **Proposed Changes**: Add `TaskFactory` (`SubFactory(EmployeeFactory)`
    for `created_by`) and `TaskAssigneeFactory`, following the existing
    `post_generation`-hook style already used for `EmployeeFactory`'s
    `shifts`.

#### 14. `backend/tests/test_tasks.py` (Create)

*   **Type / Scope**: Pytest — pure-function tests plus DB-backed API tests.
*   **Proposed Changes**: Pure tests (Fake-object style, mirroring
    `test_dashboards.py`) for `is_overdue` and the one-level-depth `clean()`
    rule. API/permission tests mirroring `TestEmployeeIsolation`: 401
    unauthenticated; 403 for an employee uninvolved with a task (not a
    silently-filtered empty list); admin sees everything; an
    assignee-but-not-creator can see and act on their task;
    creator-with-zero-assignees still sees their own task; `CANCELLED` is
    rejected from a non-creator, non-admin assignee; self-removal succeeds,
    removing another assignee as a non-creator, non-admin fails; deleting a
    parent task cascades to its sub-tasks; creating a sub-task of a sub-task
    is rejected.

#### 15. `frontend/src/api/client.js` (Modify)

*   **Type / Scope**: Frontend API client.
*   **Proposed Changes**: Add `listTasks`, `getTask`, `createTask`,
    `updateTask`, `deleteTask`, `addTaskAssignee`, `removeTaskAssignee`,
    following the existing `request()`-wrapping pattern already used for
    `listEmployees`/`activitySummary`.

#### 16. `frontend/src/router/index.js` (Modify)

*   **Type / Scope**: Vue Router configuration.
*   **Proposed Changes**: Add `/tasks` (list) and `/tasks/:id` (detail,
    `"new"` as the id for create) routes, `meta: { requiresAuth: true }`
    only — unlike most existing routes, this feature is for both roles.

#### 17. `frontend/src/views/TasksView.vue` (Create)

*   **Type / Scope**: Vue view — list.
*   **Proposed Changes**: Table of tasks visible to the current user
    (own + assigned), sorted overdue-first using the API's `is_overdue`
    field, with status and deadline columns and a "New task" entry point.

#### 18. `frontend/src/views/TaskDetailView.vue` (Create)

*   **Type / Scope**: Vue view — detail/create/edit.
*   **Proposed Changes**: Title/description/deadline fields; status
    dropdown with `CANCELLED` shown only to the creator or an admin (a UX
    nicety — the server re-enforces this regardless); assignee list with
    add/remove ("remove self" always available, "remove other" only shown
    to the creator/admin); sub-task list with an "add sub-task" action
    (hidden entirely when viewing a sub-task, since sub-tasks cannot have
    their own sub-tasks); a parent-stub link (id/title only) shown when
    viewing a sub-task.

#### 19. `frontend/src/lib/format.js` (Modify)

*   **Type / Scope**: Shared formatting helpers.
*   **Proposed Changes**: Add a `dateOnly(value)` helper alongside the
    existing `clockTime`/`dateTime` helpers, since `deadline` is a bare date
    rather than a timestamp and the existing helpers are time-inclusive.

### Verification Plan

*   **Compilation/Build**: `python manage.py check` (backend); `npm run
    build` (frontend) — both already used elsewhere in this project.
*   **Unit Tests**: `pytest backend/tests/test_tasks.py`, plus the full
    existing suite (`pytest`) to confirm nothing elsewhere regresses, since
    this change touches `settings.py` and `config/urls.py`.
*   **Static Analysis & Linting**: `ruff check` and `black --check` on the
    new `backend/tasks/` files; existing `eslint` run on the new/modified
    frontend files.
*   **Test Coverage Requirement**: This codebase has no project-wide numeric
    coverage threshold found elsewhere; match the depth of the existing
    `TestEmployeeIsolation` pattern (401/403/200/admin-override paths,
    listed under file 14 above) rather than target a percentage.
*   **E2E/Integration**: No existing browser-automation/E2E framework was
    found in this codebase; verification is the pytest API-test suite above
    plus a manual smoke test of the new `/tasks` route in the running
    frontend.

--------------------------------------------------------------------------------

<!-- Provenance: Indicates initial structural drafting via EGM. -->

*Drafted with EGM*
