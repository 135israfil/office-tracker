# Event Calendar

*   **Author:** Israfil
*   **Status:** Draft
*   **Date:** 2026-11-22

--------------------------------------------------------------------------------

## Overview

A calendar feature for the existing employee attendance & PC activity
tracking system, letting an employee create events (meetings, personal
reminders-to-self, deadlines) and optionally share them with named
coworkers. The feature is deliberately named "Event Calendar," not "Event
Calendar with Reminders" — the brainstorm review flagged, at Blocker
severity, that "reminders" promises proactive notification (push/email)
this design does not deliver, the same naming mistake the Password Vault's
own brainstorm caught and fixed for "vault" implying a privacy guarantee it
didn't deliver either. What this feature actually provides is a passive,
read-time-computed "upcoming / in progress / past" indicator — visible
when a user opens the app, not something that reaches them otherwise.

## The Problem

There is currently no way for an employee to track their own meetings,
personal deadlines, or shared commitments inside this system — only
`Task` (work items with status/assignees) and the admin-managed `Holiday`
list (company-wide non-working days) exist today, and neither covers
"this is happening on this date/time" in the way a calendar does. The
proposed solution is a lightweight event model: personal by default,
optionally shared with named coworkers, with a passive on-screen indicator
for what's coming up soon — explicitly not a notification system.

## Goals

*   An employee can create a calendar event: title, optional description,
    start datetime, optional end datetime, optional location.
*   An event is personal by default — visible only to its creator and
    admins — mirroring this codebase's existing admin-visibility
    convention for attendance/activity/task/vault data.
*   Unlike that convention elsewhere, every event discloses who can see it
    (a persistent "Visible to: ..." line) and an admin's view of a
    non-shared event is audit-logged and surfaced back to the owner —
    reusing the Password Vault's already-built disclosure/audit mechanism
    verbatim, rather than reintroducing the same undisclosed-blanket-access
    gap the Vault's own brainstorm already resolved once.
*   The creator can share an event with one or more named coworkers,
    unilateral and visibility-only (mirroring `VaultEntryGrant` — no
    accept/decline/RSVP workflow).
*   A read-time-computed "upcoming / in progress / past" status is exposed
    per event — its own explicit three-state rule, not a reuse of Task
    Tracking's binary `is_overdue` threshold, since an event has a start
    *and* optional end rather than a single deadline date.
*   The existing, separate `Holiday` model is untouched; if "everything on
    my calendar this month" is addressed at all, it's via a read-only
    aggregation of Holiday + Event for display only, never a data-model
    merge.

## Non-Goals

*   Any proactive notification — push, email, or otherwise — and any
    background job queue or email backend to support one. The in-app
    "upcoming" indicator is read-time only.
*   Recurring/repeating events. Named explicitly as deferred, not silently
    assumed away, since it's likely the first thing a real user tries
    (e.g. "team standup every Monday"). If picked up later, the cheapest
    fallback is generating concrete rows up front for a bounded repeat,
    not a recurrence-rule engine.
*   RSVP/attendance semantics (accept/decline/tentative) for a shared
    event. Sharing means visibility only.
*   Overlap or double-booking detection/warnings.
*   Any notification — even in-app — to a coworker at the moment they're
    shared with an event. This is silent by design, consistent with
    deferring all proactive notification, not an oversight.
*   Merging `Holiday` and `Event` at the data-model level.

## Open Questions

*   **Company-wide visibility**: the brainstorm review flagged this as the
    single largest source of unresolved design risk in this feature — five
    of seven reviewers raised concerns from different angles (no
    authority gate on an ordinary employee broadcasting to literally
    everyone; no demonstrated use case; and the wrong implementation
    mechanism — a grant row per employee — would not scale, versus the
    right one, a boolean flag checked at the queryset level, which has
    direct precedent in how this codebase's admin-short-circuit visibility
    already works). This draft defers deciding company-wide's fate to the
    next step of this process (see the gate immediately following this
    section) rather than resolving it unilaterally, since it is exactly
    the kind of architecture decision with more than one defensible answer
    that the author should choose.
*   **`all_day` handling**: does a null `end` datetime mean a point-in-time
    event, an all-day event, or something open-ended? Every reviewer who
    touched this flagged it as currently undefined.
*   **Cancellation vs. hard delete**: does a shared event need a
    `CANCELLED`-equivalent state distinct from deletion, the way `Task`
    does, since other people may already be relying on its existence?
*   **Creator's `on_delete` behavior**: `Task.created_by` and
    `VaultEntry.owner` both chose `PROTECT`; this feature should make the
    same explicit choice rather than inherit Django's CASCADE default.

## Critical User Journeys (CUJs)

### CUJ 1: An employee creates a personal event

*   **Given**: An authenticated employee wants to track an upcoming
    personal commitment (e.g. a dentist appointment).
*   **When**: They create an event with a title and start datetime.
*   **Then**: The event is visible only to them (and, disclosed on the
    event, to admins) until they choose to share it.

### CUJ 2: An employee shares a meeting with coworkers

*   **Given**: An employee is organizing a meeting with two coworkers.
*   **When**: They create the event and share it with those two named
    coworkers.
*   **Then**: Both coworkers can see the event (visibility only — no
    RSVP); the event's "Visible to" line lists the organizer, both
    coworkers, and "All admins."

### CUJ 3: An admin views a non-shared personal event

*   **Given**: An employee has a personal event not shared with anyone.
*   **When**: An admin opens that employee's calendar and views the event.
*   **Then**: The view succeeds (admins always have access), it is
    recorded in the audit log, and the event's owner can see it was last
    viewed by that admin, mirroring the Password Vault's `reveal`
    disclosure exactly.

### CUJ 4: An employee checks what's coming up

*   **Given**: An employee has several events at various points in time.
*   **When**: They open their calendar.
*   **Then**: Events display an "upcoming," "in progress," or "past"
    status computed at read time — no notification was sent to them in
    advance; this is the only place the status is ever surfaced.

## Technical Plan (Architecture)

### Company-wide visibility: cut from this iteration

Per the architecture decision made before drafting this section,
company-wide visibility is **not part of this feature's v1**. Every
visibility rule below is two-tier only: owner, or an explicit named
grantee (plus the admin override). If real usage later demonstrates a need
for a broadcast-to-everyone event, that is a separate, later design
decision — not an extension bolted onto this one, since the brainstorm
review's own finding was that it needs a structurally different mechanism
(a boolean flag checked at the queryset level) than named-sharing's
through-model, not a natural growth of it.

### Data model

A new `events` Django app, mirroring how `tasks` and `vault` were each
added as their own app. Deliberately not named `calendar`: that would
collide with Python's own standard-library `calendar` module (used
internally by `http.cookiejar` and parts of `email`, among others) once
this app sits on `sys.path` as a top-level package the way every other app
in `backend/` does — a real, concrete shadowing risk, not a hypothetical
one, caught here rather than during implementation:

*   **`Event`**: `owner` (FK → Employee, `on_delete=PROTECT` — the same
    choice `Task.created_by` and `VaultEntry.owner` both made, so a
    dependent (a grantee relying on a shared event) is never silently
    stranded by the owner's employee record being removed), `title`,
    `description` (blank), `start` (DateTimeField), `end` (DateTimeField,
    null=True, blank=True), `all_day` (BooleanField, default False —
    resolves the brainstorm's open `all_day` question explicitly rather
    than overloading a missing `end`), `location` (blank),
    `status` (`TextChoices`: `ACTIVE`, `CANCELLED`, default `ACTIVE` —
    resolves the brainstorm's open cancellation question the same way
    `Task` has a `CANCELLED` status distinct from deletion, since a
    grantee may be relying on a shared event's continued existence),
    `created_at`, `updated_at`.
*   **`EventGrant`** (through-model, mirroring `VaultEntryGrant`): `event`
    (FK → Event, `on_delete=CASCADE`), `grantee` (FK → Employee,
    `on_delete=CASCADE`), `granted_by` (FK → Employee,
    `on_delete=PROTECT`), `granted_at`. `UniqueConstraint` on
    `(event, grantee)`. Explicitly documented, in the model's own
    docstring, as visibility-only — no accept/decline/RSVP state — so this
    doesn't silently grow into an invitation workflow later.

### Permissions

A new `IsEventOwnerOrGranteeOrAdmin` permission class, modeled directly on
`vault.permissions.IsVaultEntryOwnerOrGranteeOrAdmin`:

*   The **owner** can view, edit, delete/cancel, share, and revoke.
*   A **grantee** can only view — never edit, delete, share, or revoke
    another grantee (can revoke their own access, self-removal, mirroring
    both Task Tracking's `remove_assignee` and the Vault's
    `revoke_grant`).
*   An **admin** can view any event, but cannot edit, delete, or manage
    another employee's shares — the same deliberately narrow,
    read-only override the Vault uses, not a full admin-takeover.

### Visibility enforcement

`EventViewSet.get_queryset()` filters to "owner, or an explicit grantee, or
admin sees all" at the queryset level, the same pattern as
`resolve_employee()`, `TaskViewSet.get_queryset()`, and
`VaultEntryViewSet.get_queryset()`.

### Visibility disclosure and admin-view audit logging

Every `Event` serializer response includes the same `visible_to` computed
field the Vault uses (owner, every current grantee, and "All admins").
Unlike the Vault, where the sensitive action is an occasional, deliberate
`reveal` of a secret, viewing a calendar event's detail is an ordinary,
frequent browsing action — logging every list-row would flood the audit
log in a way the Vault's `reveal` action never does. This feature
therefore logs only on `retrieve` (a specific event's own detail view),
not on `list`: when the requester is neither the owner nor a grantee (i.e.
an admin exercising the blanket-visibility override), `retrieve` calls
`core.audit.record()` with a new `EVENT_VIEWED_BY_ADMIN` `AuditLog.Action`
value, and the event's serializer surfaces the most recent such view back
to the owner as `last_admin_view` (mirroring the Vault's
`last_admin_reveal` field exactly). This is a deliberate adaptation of the
Vault's pattern to a different action shape, not a literal copy — flagged
in Non-Functional Requirements as a volume trade-off to watch.

### The "upcoming / in progress / past" indicator

A new pure function, `event_phase(start, end, now)`, explicitly three-state
rather than Task Tracking's binary `task_is_overdue`:

*   `now < start` → `UPCOMING`
*   `end is not None and start <= now <= end` → `IN_PROGRESS`
*   otherwise (`now > end`, or `end is None and now >= start`) → `PAST`

`Event.phase` is a thin, DB-touching property wrapping this pure function
with `django.utils.timezone.now()` — no office-timezone conversion is
needed for the comparison itself, since `start`/`end` are already
timezone-aware datetimes under this project's `USE_TZ=True` storage
(unlike `Task.deadline`, a bare date, which is why `is_overdue` needed
`attendance.calendar_rules.local_date`). Office-timezone-aware
*formatting* for display, if wanted, is a separate, later concern — and
may belong in the Vue frontend rather than a server-side lookup.

### API surface

*   `GET/POST /api/events/` — list (metadata only; owner + shared +
    admin-sees-all) / create.
*   `GET/PATCH/DELETE /api/events/{id}/` — retrieve (audit-logged per
    above when applicable) / update (owner only; includes setting
    `status=CANCELLED`) / delete (owner only).
*   `POST /api/events/{id}/share/` — owner-only; body `{employee}`;
    creates an `EventGrant`.
*   `DELETE /api/events/{id}/grants/{employee_id}/` — revokes a grant; the
    owner can revoke any grantee, and a grantee can revoke their own
    access.
*   Reuses `tasks.views.AssignableEmployeesView` (via the frontend's
    existing `listAssignableEmployees` call) for the "pick a coworker to
    share with" picker, the same reuse the Vault already established —
    not a third near-identical endpoint.

### Data flow (retrieve, admin view)

```text
Admin                       DRF View                   DB / AuditLog
  |                            |                             |
  |  GET /events/{id}/         |                             |
  |--------------------------->|                             |
  |                            | get_object() -- queryset    |
  |                            | admin sees all, else 404    |
  |                            |---------------------------->|
  |                            |   fetch Event row            |
  |                            |<----------------------------|
  |                            | requester is admin, not      |
  |                            | owner/grantee -> log it       |
  |                            |---------------------------->|
  |                            | record(EVENT_VIEWED_BY_ADMIN)|
  |<---------------------------|  serialized Event response   |
```

## Non-Functional Requirements

*   **Security & Privacy**: Personal events are disclosed, not silently
    admin-visible — every event states who can see it, and a non-shared
    admin retrieve is logged and surfaced to the owner. Volume trade-off:
    because retrieving a calendar event's detail is an ordinary, frequent
    action (unlike the Vault's occasional `reveal`), an admin who
    regularly browses employees' calendars will generate a
    correspondingly regular stream of `EVENT_VIEWED_BY_ADMIN` entries —
    this is accepted as the cost of disclosure, not deferred, but is worth
    monitoring if `AuditLog` volume becomes a concern later.
*   **Performance**: Visibility filtering stays queryset-level
    (`Q(owner=...) | Q(grants__grantee=...)`), the same two-branch shape
    already proven by `Task`/`VaultEntry`; no company-wide third branch
    exists in this iteration, so no new query-shape risk is introduced.
*   **Rollout**: New app, new routes; does not modify any existing
    endpoint's behavior, so no feature flag or data migration of existing
    records is required to ship it.

## Alternatives Considered

### Alternative A: Company-wide visibility, admin-only creation

*   **Pros**: Satisfies a real (if undemonstrated) need for all-hands
    announcements or company-wide notices, while matching this codebase's
    existing `Holiday` precedent (admin-write, everyone-read) for exactly
    this kind of broadcast capability.
*   **Cons**: Adds a structurally new visibility mechanism (a boolean flag
    checked at the queryset level, a third branch alongside owner/grantee)
    for a use case nobody has actually asked for yet, and a second admin
    gate specific to this feature where `Holiday` already exists as the
    established path for admin-driven, company-wide calendar content.
*   **Reason for Rejection**: Rejected by author: cut from this iteration
    entirely (see Alternative C) rather than built now; this option is
    recorded as the fallback if a real need for employee-initiated (but
    admin-approved) company-wide events emerges later.

### Alternative B: Company-wide visibility, open to all employees, audit-logged

*   **Pros**: No admin bottleneck — any employee could post a team-wide
    notice immediately; the audit log at least makes every company-wide
    creation traceable after the fact, rather than silent.
*   **Cons**: An audit trail is a record of a broadcast that already
    happened — it does nothing to prevent an inappropriate or spam-like
    company-wide post from reaching every employee's calendar before
    anyone reviews it. This is strictly weaker than Alternative A for the
    one risk every reviewer who raised this flagged (an ungated broadcast
    capability with no demonstrated need).
*   **Reason for Rejection**: Rejected by author: the weakest of the three
    options considered for company-wide visibility, superseded by cutting
    it entirely (Alternative C).

### Alternative C: Cut company-wide visibility from this iteration entirely (chosen)

*   **Pros**: Removes the single largest source of new design risk this
    brainstorm identified (five of seven reviewers raised concerns) with
    zero new mechanism, zero new authority question, and zero scale risk.
    Personal + named-sharing already covers every concretely demonstrated
    use case from scoping. Revisiting this later, if real usage shows a
    genuine need, is a cheap additive feature — a boolean flag plus one
    more `Q()` branch — not a breaking change to anything built now.
*   **Cons**: An all-hands announcement or company notice has no home in
    this feature for now; `Holiday` remains the only company-wide-visible
    calendar-adjacent content.
*   **Reason for Rejection**: N/A — this is the option chosen. Recorded
    here for symmetry with the other two, which were weighed against it
    and rejected.

### Alternative D: Office-timezone-aware comparison for the "upcoming/in progress/past" indicator

*   **Pros**: Consistency with Task Tracking's `is_overdue`, which reuses
    `attendance.calendar_rules.local_date`/`AppSettings` for exactly this
    kind of read-time computation.
*   **Cons**: Solves a problem that doesn't exist here. `local_date`
    answers "which office-local calendar date does this bare date belong
    to" — relevant for `Task.deadline`, a bare `DateField` with no
    timezone of its own. An `Event`'s `start`/`end` are already
    timezone-aware datetimes under this project's `USE_TZ=True` storage;
    comparing `now() < start` needs no office-timezone conversion to be
    correct.
*   **Reason for Rejection**: Rejected by author, following the
    codebase-details review's direct verification: this machinery is, at
    most, relevant to *display formatting*, not the phase computation
    itself, and even that may belong in the Vue frontend rather than a
    server-side lookup.

### Alternative E: Merge `Holiday` into `Event` as a special company-wide event type

*   **Pros**: One unified calendar model; no presentation-layer merge
    logic needed to answer "what's on my calendar this month."
*   **Cons**: `Holiday` is functionally coupled to absence accounting
    (combined with `AppSettings.weekend_days` to decide whether a date
    counts toward absence) and is admin-authority, immutable-to-employees
    data — genuinely different semantics from a creator-owned, purely
    informational `Event`, not redundant modeling pretending to be
    separate.
*   **Reason for Rejection**: Rejected by the user early in scoping,
    before this review ran; confirmed independently by the structural and
    inventive-catalyst reviews as the right call. A read-only aggregation
    view (or client-side merge) resolves the "one place to look" UX gap
    instead, without touching either model.

### Alternative F: RSVP/attendance semantics for shared events

*   **Pros**: Matches the everyday meaning of "calendar event" more
    closely — real calendar tools let an invitee accept/decline/mark
    tentative.
*   **Cons**: A full invitation workflow is substantially more state (an
    RSVP status per grantee, notification of status changes, an
    organizer-facing summary) than this codebase's existing unilateral
    sharing precedent (`TaskAssignee`, `VaultEntryGrant`) has ever needed,
    for a need not yet demonstrated by any stated use case.
*   **Reason for Rejection**: Rejected by author: sharing is scoped to
    visibility only, the same shape as `VaultEntryGrant`, explicitly
    documented as such in the model to prevent this from growing in
    silently later.

--------------------------------------------------------------------------------

## Detailed Implementation Plan

### Target Files to Create/Modify

#### 1. `backend/events/__init__.py` (Create)

*   **Type / Scope**: Django app package marker.
*   **Proposed Changes**: Empty file marking `events` as a new Django app,
    mirroring `backend/tasks/__init__.py` and `backend/vault/__init__.py`.

#### 2. `backend/events/apps.py` (Create)

*   **Type / Scope**: Django app config.
*   **Proposed Changes**: `EventsConfig(AppConfig)` with
    `default_auto_field` and `name = "events"`.

#### 3. `backend/events/models.py` (Create)

*   **Type / Scope**: Django models.
*   **Proposed Changes**:
    *   `EventStatus(TextChoices)`: `ACTIVE`, `CANCELLED` — resolves the
        brainstorm's open cancellation question, mirroring `TaskStatus`'s
        pattern of a status distinct from deletion.
    *   `EventPhase` (a plain `TextChoices` or string constants, not a
        model field): `UPCOMING`, `IN_PROGRESS`, `PAST`.
    *   `event_phase(start, end, now) -> str`: pure function implementing
        the three-state rule from the Technical Plan. No DB/clock
        dependency, matching this codebase's established convention
        (`task_is_overdue`, `activities.queries`'s date-arithmetic
        functions).
    *   `Event`: `owner` (FK → Employee, `on_delete=PROTECT`), `title`,
        `description` (blank), `start` (DateTimeField), `end`
        (DateTimeField, null=True, blank=True), `all_day` (BooleanField,
        default False), `location` (blank), `status`
        (`CharField`, choices=`EventStatus.choices`, default `ACTIVE`),
        `created_at`, `updated_at`. `clean()` validates `end >= start`
        when `end` is set (mirroring `AppSettings.clean()`'s
        `default_start_time < default_end_time` validation).
    *   `Event.phase` property: thin wrapper calling `event_phase(self.
        start, self.end, timezone.now())` — no office-timezone lookup, per
        the Technical Plan's correction of the `Task.is_overdue` analogy.
    *   `EventGrant`: `event` (FK → Event, `on_delete=CASCADE`), `grantee`
        (FK → Employee, `on_delete=CASCADE`), `granted_by` (FK → Employee,
        `on_delete=PROTECT`), `granted_at` (auto_now_add).
        `UniqueConstraint(fields=["event", "grantee"],
        name="unique_grant_per_event")`. Module/model docstring states
        explicitly: visibility only, no accept/decline/RSVP state.

#### 4. `backend/events/permissions.py` (Create)

*   **Type / Scope**: DRF permission class.
*   **Proposed Changes**: `IsEventOwnerOrGranteeOrAdmin`, modeled directly
    on `vault.permissions.IsVaultEntryOwnerOrGranteeOrAdmin`: owner → full
    control (view/edit/delete/share/revoke-any); grantee → view only, plus
    self-revoke of their own grant; admin → view only, never
    edit/destroy/share/revoke_grant on an event they don't own.

#### 5. `backend/events/serializers.py` (Create)

*   **Type / Scope**: DRF serializers.
*   **Proposed Changes**:
    *   `_EmployeeStubSerializer` (private copy, id/employee_id/name —
        matching the convention `tasks` and `vault` each already follow
        rather than sharing one across apps).
    *   `EventGrantSerializer`: grantee stub, granted_by stub, granted_at.
    *   `EventSerializer`: title, description, start, end, all_day,
        location, status, `phase` (read-only, from `Event.phase`), `owner`
        (stub), `grants` (nested, read-only), `visible_to`
        (SerializerMethodField: owner name + grantee names + "All
        admins"), `last_admin_view` (SerializerMethodField reading the
        most recent matching `AuditLog` row, mirroring the Vault's
        `last_admin_reveal`), created_at, updated_at.
    *   `validate()` enforces `end >= start` when both are present,
        matching the model's own `clean()` (defense in depth, the same
        reason `VaultEntrySerializer.validate()` duplicates a model-level
        rule).

#### 6. `backend/events/views.py` (Create)

*   **Type / Scope**: DRF views.
*   **Proposed Changes**:
    *   `EventViewSet(viewsets.ModelViewSet)`: `get_queryset()` filters to
        `Q(owner=employee) | Q(grants__grantee=employee)` for non-admins
        (`.distinct()` required), unfiltered for admins — mirroring
        `VaultEntryViewSet.get_queryset()`.
    *   `perform_create()`: sets `owner=employee`.
    *   **Overridden `retrieve()`**: calls the default `get_object()` /
        serialization flow, but first checks whether the requester is
        neither the owner nor an existing grantee; if so, calls
        `core.audit.record(actor=request.user,
        action=AuditLog.Action.EVENT_VIEWED_BY_ADMIN, target=event)`
        before returning the response. This is the one place this
        feature's audit logging differs structurally from the Vault's
        (which audits a custom `reveal` action, not the default
        `retrieve`) — see the Technical Plan's note on why `list` is
        deliberately never logged.
    *   `@action(detail=True, methods=["post"]) def share(...)`:
        owner-only; body `{"employee": <id>}`; creates an `EventGrant`;
        re-fetches and re-serializes afterward (the same prefetch-cache
        staleness fix Task Tracking and the Vault both needed for their
        own `add_assignee`/`share` actions).
    *   `@action(detail=True, methods=["delete"],
        url_path="grants/(?P<employee_id>[^/.]+)") def revoke_grant(...)`:
        deletes the matching `EventGrant`; owner can revoke any grantee, a
        grantee can revoke only themselves; re-fetches and re-serializes
        afterward.
    *   Reuses `tasks.views.AssignableEmployeesView` directly (imported,
        not duplicated) for the "pick a coworker to share with" picker —
        the same reuse the Vault already established.

#### 7. `backend/events/admin.py` (Create)

*   **Type / Scope**: Django admin registration.
*   **Proposed Changes**: Registers `Event` (list display:
    title/owner/start/end/status) and `EventGrant`, mirroring
    `tasks/admin.py`'s `TaskAssigneeInline` pattern for showing grants
    inline on the event's admin page. No secret/sensitive field to
    exclude here (unlike the Vault's admin registration), so this is a
    standard registration.

#### 8. `backend/events/migrations/0001_initial.py` (Create)

*   **Type / Scope**: Django migration.
*   **Proposed Changes**: Generated via `makemigrations events`; creates
    the `Event` and `EventGrant` tables, the unique constraint, and an
    index on `(owner,)` and `(start,)` (the latter because the "upcoming"
    computation is, by definition, a `start`/`end`-range read on every
    app-open — an unindexed scan would degrade as event volume grows, the
    same point the design lens raised about this read path specifically).

#### 9. `backend/config/settings.py` (Modify)

*   **Type / Scope**: Django settings.
*   **Proposed Changes**: Add `"events"` to `INSTALLED_APPS`. No new
    environment variable, throttle scope, or security setting is needed —
    unlike the Vault, this feature introduces no new secret or
    high-sensitivity action.

#### 10. `backend/config/urls.py` (Modify)

*   **Type / Scope**: URL routing.
*   **Proposed Changes**: Import `EventViewSet` from `events.views`;
    register `router.register("events", EventViewSet,
    basename="event")`, following the same direct-router-registration
    convention Task Tracking and the Vault both used.

#### 11. `backend/core/models.py` (Modify)

*   **Type / Scope**: Shared `AuditLog` model.
*   **Proposed Changes**: Add `EVENT_VIEWED_BY_ADMIN = (
    "EVENT_VIEWED_BY_ADMIN", "Calendar event viewed by admin")` to
    `AuditLog.Action` — the second non-admin-initiated-action precedent
    extension after `VAULT_ENTRY_REVEALED_BY_ADMIN`, so no longer a novel
    precedent to flag, just a continuation of it.

#### 12. `backend/tests/factories.py` (Modify)

*   **Type / Scope**: Factory Boy test factories.
*   **Proposed Changes**: Add `EventFactory` (default `start` one day in
    the future, so new events are `UPCOMING` by default; a `grantees=[...]`
    `post_generation` hook mirroring `TaskFactory`'s/the Vault's) and
    `EventGrantFactory`.

#### 13. `backend/tests/test_events.py` (Create)

*   **Type / Scope**: Pytest test suite, mirroring `test_tasks.py`/
    `test_vault.py`'s structure and the same `TestEmployeeIsolation`
    exit-criterion pattern.
*   **Proposed Changes**: Test classes covering: `event_phase()` pure
    function (all three states, including the no-`end` case explicitly);
    data isolation (unauthenticated → 403; uninvolved employee → 404;
    owner, grantee, and admin can all see; list excludes others' events);
    retrieve-level admin audit logging (owner/grantee retrieve is never
    logged; admin retrieve of a non-shared event is logged and surfaces
    via `last_admin_view`; **list never logs**, confirmed with a
    dedicated test given this is the one place this feature's audit
    behavior deliberately differs from the Vault's); `share`/`revoke_grant`
    (owner can share/revoke any grantee; a grantee can revoke only
    themselves; responses reflect the new state immediately — the same
    prefetch-cache-staleness regression pattern Task Tracking and the
    Vault both needed); `end >= start` validation; write permissions
    (grantee cannot edit/delete/share; admin cannot edit/delete/share
    someone else's event, only view it).

### Frontend

#### 14. `frontend/src/api/client.js` (Modify)

*   **Type / Scope**: API client.
*   **Proposed Changes**: Add `listEvents`, `getEvent`, `createEvent`,
    `updateEvent`, `deleteEvent`, `shareEvent`, `revokeEventGrant` —
    following the exact calling convention of the existing `api.listTasks`/
    `api.listVaultEntries` groups. Reuses the existing
    `listAssignableEmployees` call, no change needed there.

#### 15. `frontend/src/views/EventsView.vue` (Create)

*   **Type / Scope**: Vue view — list + create.
*   **Proposed Changes**: List of the current user's visible events
    (title, start, phase badge — Upcoming/In progress/Past — "shared with
    N people" indicator), a create form (title, description, start, end,
    all_day checkbox, location). Mirrors `TasksView.vue`'s structure.
    Sorts upcoming-first, the same `sortedTasks` computed-sort pattern
    `TasksView.vue` already uses for overdue-first.

#### 16. `frontend/src/views/EventDetailView.vue` (Create)

*   **Type / Scope**: Vue view — detail/edit/share.
*   **Proposed Changes**: Edit form for title/description/start/end/
    all_day/location (owner-only), a status control for marking an event
    cancelled (owner-only), the `visible_to` disclosure line rendered
    verbatim from the API response, the `last_admin_view` notice when
    present, share form (reusing the assignable-employees picker pattern
    from `TaskDetailView.vue`/`VaultEntryDetailView.vue`), a revoke button
    per grantee. No "reveal" step is needed here (unlike the Vault) since
    nothing on an event is encrypted — the detail view's own load is the
    `retrieve` call that triggers admin-view logging when applicable.

#### 17. `frontend/src/router/index.js` (Modify)

*   **Type / Scope**: Vue Router.
*   **Proposed Changes**: Add `/events` and `/events/:id` routes,
    available to both roles, mirroring `/tasks` and `/vault`.

#### 18. `frontend/src/App.vue` (Modify)

*   **Type / Scope**: Navigation shell.
*   **Proposed Changes**: Add an "Events" nav entry to both the admin and
    employee link arrays, following the existing `icon: "..."` convention.

#### 19. `frontend/src/components/NavIcon.vue` (Modify)

*   **Type / Scope**: Icon set.
*   **Proposed Changes**: Add a new icon distinct from the existing
    `calendar` glyph already used for "All attendance" (reusing that exact
    icon for a different nav entry would be confusing in the sidebar) —
    e.g. a calendar page with a single marked date.

### Verification Plan

*   **Compilation/Build**: `backend`: `./.venv/Scripts/python.exe
    manage.py check`; `frontend`: `npm run build`.
*   **Unit Tests**: `backend`: `pytest backend/tests/test_events.py` (and
    the full suite, to confirm no regression elsewhere) via the project's
    usual `DJANGO_SECRET_KEY=... DJANGO_DEBUG=true ...
    ./.venv/Scripts/python.exe -m pytest -q` invocation (no new required
    environment variable, unlike the Vault's `VAULT_ENCRYPTION_KEY`).
*   **Static Analysis & Linting**: `ruff check .` and `black --check .`
    for the backend; `npx eslint src/` for the frontend.
*   **Test Coverage Requirement**: Every permission branch (owner,
    grantee, admin, uninvolved employee) and both audit-logging paths
    (logged on admin retrieve vs. never logged on list) must have at
    least one dedicated test.
*   **E2E/Integration**: Live browser verification via the project's
    `preview_start` dev-server workflow — create an event, share it with a
    second employee, confirm that employee sees it, revoke it and confirm
    a 404 on their next retrieve, view a non-shared event as an admin and
    confirm the owner's `last_admin_view` field updates, and confirm
    listing events as that same admin does **not** produce a second log
    entry — the specific behavior this feature's tests must catch that
    the Vault's never needed to.

--------------------------------------------------------------------------------

<!-- Provenance: Indicates initial structural drafting via EGM. -->

*Drafted with EGM*
