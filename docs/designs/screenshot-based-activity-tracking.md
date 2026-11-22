# Screenshot-Based Activity Tracking

*   **Author:** Israfil
*   **Status:** Draft — contingent, not authorized to build
*   **Date:** 2026-11-22

--------------------------------------------------------------------------------

## Overview

**This document is a technical design, not an authorization to implement
it.** The brainstorm this draft is built from (`concepts_brief_screenshot_
tracking.md`) concluded explicitly: *"This feature does not proceed to
design or implementation from this brief"* — because the feature as
proposed directly conflicts with an already-published, CI-structurally-
enforced employee privacy commitment (`docs/employee-privacy-notice.md`:
*"Screenshots or screen recording. Ever, including on request"*, backed by
`scripts/check_privacy.py`, which fails CI on any import of a screen-
capture library). That conflict is not resolved by this document and is
not something a design doc can resolve — it requires the governance steps
described in the brainstorm (a deliberate revision of README.txt §31,
a reissued privacy notice, per-employee re-acknowledgment, and legal
review) to complete first, in that order, before any of what follows here
may legitimately be built. This draft exists so that, if and only if that
governance process completes, a technical starting point already exists
rather than being designed from scratch under time pressure. Every section
below carries that contingency forward rather than treating it as settled.

The feature itself, as a technical proposal: the desktop agent would
periodically capture a screenshot of the employee's screen (similar
cadence to existing activity sampling), viewable by admins/HR only, with
its own (not reused) retention mechanism.

## The Problem

The stated underlying need — richer insight into what an employee is
doing than the existing app-name/domain/idle signals provide — is not,
on its own terms, demonstrated by any concrete use case in the brainstorm.
The brainstorm's own zoom-out and design reviews independently identified
a lighter alternative (richer activity-change signals, finer idle/dwell
timelines, structural UI-tree signals) that could address that same
underlying need without capturing screen content at all, and recommended
it as a separate, decoupled feature rather than a scoped-down version of
this one. This document does not pursue that alternative — it documents
the literal, as-proposed screenshot feature's technical shape, per the
user's explicit choice to draft it anyway.

## Goals

*   Document a technical design for periodic screenshot capture, admin/HR-
    only visibility, and its own retention mechanism — contingent on the
    governance prerequisites in Open Questions, not ready to build as-is.
*   Treat screenshots as a new, dedicated subsystem (its own app, model,
    storage path, and retention job) rather than an extension of the
    existing `Activity`/`ActivityType` model, per the brainstorm's
    structural and design findings that grafting it onto `Activity` would
    reintroduce the per-sample row growth that model was built to avoid.
*   Apply at least the same disclosure/audit rigor this codebase already
    built for its other high-sensitivity disclosure case (the Password
    Vault's `reveal` action: dedicated throttled action, per-view audit
    log entry, surfaced back to the subject), given the brainstorm's
    finding that a screenshot is at least as sensitive as a vault
    credential and the hypothesis as given proposed less protection, not
    more.
*   Include a redaction/review gate between capture and the first human
    view, given the brainstorm's finding that screenshots have no
    equivalent to the client-side minimization (domain-only, title-hash-
    discard) every other collector in this codebase already uses to bound
    incidental third-party exposure.

## Non-Goals

*   Resolving, bypassing, or working around the governance prerequisites.
    This document does not touch `scripts/check_privacy.py`,
    `README.txt` §31, or `docs/employee-privacy-notice.md`, and no
    implementation work following from this document should either, until
    those are resolved through their own process.
*   A metadata-only, non-screen-content alternative. Recorded in the
    brainstorm as a separate, future feature — not drafted here.
*   Legal/jurisdictional compliance design. The brainstorm identified this
    as a prerequisite review whose output could reshape the permitted
    technical design (e.g., mandatory blurring, no persistent storage at
    all) — out of scope for this document to anticipate.
*   Actual implementation. No code should be written from this document
    until the Open Questions below are resolved.

## Open Questions

*   **Governance sequence (carried forward from the brainstorm,
    unresolved by this document):** (a) has README.txt §31 been
    deliberately revised by whoever owns it; (b) has
    `docs/employee-privacy-notice.md` been reissued (not amended) with
    this capability described at the same specificity as other
    PC-activity items; (c) has every current employee given a positive
    re-acknowledgment, completed before the capability is enabled for
    them; (d) has a legal/jurisdictional review completed, and did its
    output change anything below. None of these are resolved by this
    document.
*   **Storage backend choice**: object storage (e.g. S3-compatible) vs.
    something else — this codebase has no existing precedent beyond
    Django's default `FileSystemStorage`, which is unconfigured for media
    today.
*   **Capture-to-session correlation**: does a screenshot reference a
    specific in-progress `Activity` row, or correlate only by timestamp?
    The brainstorm's structural review flagged both options have
    different failure modes and neither is free.
*   **Redaction mechanism specifics**: automated (e.g., blur known-
    sensitive regions) vs. a human review step before first admin view —
    not decided by the brainstorm, and likely an input from the legal
    review above rather than a free technical choice.
*   **Capacity planning**: the brainstorm's rough estimate (a 50-PC fleet
    at 60-second cadence: ~24,000 images/day, 200–600 GB resident at a
    90-day-equivalent retention window) was not validated against this
    deployment's actual fleet size or available infrastructure budget.

## Critical User Journeys (CUJs)

### CUJ 1: An admin views a captured screenshot (with disclosure)

*   **Given**: The governance prerequisites above have been satisfied and
    the feature is enabled.
*   **When**: An admin opens a specific employee's activity view and
    selects a captured screenshot.
*   **Then**: The screenshot passes through its redaction/review gate (if
    not already cleared), the view is recorded in the audit log the same
    way the Vault's `reveal` action is, and the employee can see, in their
    own activity view, that this specific screenshot was viewed by that
    admin and when.

### CUJ 2: Scheduled retention deletes aging screenshots

*   **Given**: A screenshot has passed its own (not the general activity)
    retention window.
*   **When**: The dedicated screenshot retention job runs.
*   **Then**: Both the database record and the backing stored file are
    deleted together, and the deletion is logged — addressing the
    brainstorm's finding that deleting a DB row without deleting its file
    would silently leak storage past the existing activity retention
    job's audited guarantee.

## Technical Plan (Architecture)

### Storage backend: local filesystem, dedicated directory

Per the architecture decision made before drafting this section: a new,
dedicated storage path on the app server's own disk (e.g.
`SCREENSHOT_STORAGE_ROOT`, a new setting, never served by
`whitenoise`/`STATIC_ROOT` or any public URL), using a second
`FileSystemStorage` instance separate from Django's `default` storage —
not an object-storage service. This keeps the feature self-contained
within this deployment's existing single-server model, at the cost of not
scaling past what this server's disk can hold; the capacity-planning Open
Question above should be revisited before this is enabled for a fleet
larger than what a single disk comfortably holds at the chosen retention
window.

### Data model

A new `screenshots` Django app — a dedicated subsystem, not a field on
`Activity`, per the brainstorm's finding that `Activity`'s schema is
deliberately interval-shaped to bound row growth, which a point-in-time,
blob-backed capture would reintroduce if grafted on:

*   **`ScreenshotCapture`**: `employee` (FK → Employee,
    `on_delete=PROTECT`, the same choice every other owner/creator FK in
    this codebase makes), `computer` (FK → Computer, `on_delete=PROTECT`,
    for the same reason), `activity` (FK → `activities.Activity`,
    `null=True`, `on_delete=SET_NULL` — per the capture-correlation
    decision above: a screenshot references the Activity session that was
    open at capture time, but `SET_NULL` rather than `CASCADE` or
    `PROTECT` because the two records have independent retention windows
    and neither should block or cascade-delete the other), `captured_at`
    (DateTimeField), `file` (FileField, using the dedicated storage above,
    never a public URL), `review_status` (`TextChoices`: `PENDING_REVIEW`,
    `CLEARED`; default `PENDING_REVIEW` — the redaction/review gate from
    Goals; the exact redaction mechanism stays an Open Question, but the
    gate itself is structural: no `view` action succeeds while a capture
    is `PENDING_REVIEW`), `created_at`.
*   Deliberately no employee-facing visibility into the image itself —
    per the anchored hypothesis, only admins/HR can ever view a
    screenshot's contents. The employee does get visibility into *that* a
    specific capture was viewed and by whom (see disclosure below),
    mirroring the Vault's `visible_to`/`last_admin_reveal` disclosure
    pattern applied to a one-way-visible resource rather than a shared
    one — this asymmetry (disclosed that it happened, but never shown the
    content itself) is a deliberate reading of the hypothesis as given,
    not an oversight.

### Permissions and the redaction/review gate

A new `IsAdminOnly` permission class (no owner/grantee tier at all, unlike
every other feature in this codebase — the anchored hypothesis explicitly
excludes the captured employee from viewing their own screenshot). The
`view` action (see below) additionally checks `review_status ==
CLEARED` before returning image bytes, regardless of permission — a
`PENDING_REVIEW` capture 403s for every admin, not just non-admins, until
whatever process resolves the redaction Open Question marks it `CLEARED`.

### Disclosure and audit logging — at least as strong as the Vault's `reveal`

Mirroring `vault.views.VaultEntryViewSet.reveal` structurally, not just in
spirit, per the Goals' explicit requirement that this be at least as
protected as the Vault's pattern, given a screenshot is at least as
sensitive as a vault credential:

*   A dedicated `view` action (not the default `retrieve`), returning the
    image only when `review_status == CLEARED`.
*   A new `screenshot-view` DRF throttle scope, following the precedent
    set by `vault-reveal` — viewing raw screen content is exactly the
    class of action that earns its own rate limit, the same reasoning
    that applied to decrypting a password.
*   Every `view` call — not conditionally, unlike the Vault's "only log
    the non-owner/grantee case" — writes a new `SCREENSHOT_VIEWED_BY_ADMIN`
    `AuditLog.Action` entry, since there is no owner/grantee tier here for
    an "expected" view to be exempted from; every view is an admin
    exercising access the employee themselves doesn't have.
*   The employee's own activity view surfaces a `last_viewed_by` /
    `view_count` summary per capture (who most recently viewed it and
    when, and how many times) — the disclosure half of this pattern,
    applied to a resource the employee can know *about* but never *see*.

### Retention: a dedicated job, not a reuse of `activities/retention.py`

A new `screenshots/retention.py`, modeled on `activities/retention.py`'s
discipline (a narrowly-scoped queryset, dry-run-equals-real-run auditing,
an `AuditLog` entry per run including empty runs) but **not the same
job or the same `AppSettings` field** — a new, dedicated
`screenshot_retention_days` setting, independent of
`activity_retention_days`, per the Goals' explicit requirement that this
not be a reused mechanism. Each run deletes both the `ScreenshotCapture`
row and its backing file together, in that order with the file deletion
verified before the row delete commits (or both wrapped in a pattern that
surfaces a mismatch rather than silently leaving an orphaned file) — this
directly addresses the brainstorm's finding that a DB-row-only delete
would silently leak storage past the audited guarantee
`activities/retention.py` currently provides for rows alone.

### API surface

*   `GET /api/screenshots/` — list (metadata only: `id`, `employee`,
    `computer`, `captured_at`, `review_status`, `view_count`,
    `last_viewed_by` — never the image itself); admin-only.
*   `GET /api/screenshots/{id}/view/` — the only endpoint that ever
    returns image bytes; admin-only; blocked while `PENDING_REVIEW`;
    throttled; audit-logged unconditionally.
*   No create/update/delete endpoints exposed via the API at all — rows
    are created only by the desktop agent's own ingest path (out of
    scope for this document's API surface, since the ingest/sync
    mechanism itself is an unresolved capacity/transport question per the
    brainstorm) and removed only by the retention job, never by a user
    action.

### Data flow (admin view, with the redaction gate)

```text
Admin                        DRF View                    DB / Storage / AuditLog
  |                             |                                  |
  |  GET /screenshots/{id}/view/|                                  |
  |---------------------------->|                                  |
  |                             | fetch ScreenshotCapture row       |
  |                             |--------------------------------->|
  |                             |<---------------------------------|
  |                             | review_status == PENDING_REVIEW? |
  |                             |   yes -> 403, no log              |
  |                             |   no (CLEARED) -> continue        |
  |                             | record(SCREENSHOT_VIEWED_BY_ADMIN)|
  |                             |--------------------------------->|
  |                             | read file from dedicated storage  |
  |                             |--------------------------------->|
  |<----------------------------|  image bytes                      |
```

## Non-Functional Requirements

*   **Security & Privacy**: No employee-facing visibility into image
    content, ever — only into the fact and timing of admin views. Every
    view is logged unconditionally (stronger than the Vault's conditional
    logging, since there is no "expected" owner/grantee view here to
    exempt). A `PENDING_REVIEW` capture is unreadable by anyone, including
    admins, until cleared — the redaction/review gate is enforced at the
    `view` action itself, not left to caller discipline.
*   **Performance & Storage**: Local-filesystem storage means this
    feature's practical ceiling is this deployment's own disk capacity —
    the unresolved capacity-planning Open Question (an estimated
    200-600GB resident at a 90-day-equivalent window, for a 50-PC fleet)
    is a hard operational constraint under this storage choice, not just
    a cost estimate, and should be sized against this deployment's actual
    fleet and available disk before enabling.
*   **Rollout**: Entirely new app, new routes, new settings
    (`SCREENSHOT_STORAGE_ROOT`, `screenshot_retention_days`); does not
    modify any existing endpoint's behavior. Still gated, per the Overview,
    on the governance prerequisites completing first — this section
    describes what would need to be built, not a rollout this document
    authorizes.

## Alternatives Considered

### Alternative A: A scoped-down screenshot variant (lower frequency, on-demand/admin-triggered, blurred or cropped region, shorter retention)

*   **Pros**: Smaller engineering lift than continuous full-screen capture;
    narrower audience/frequency intuitively reads as "more proportionate."
*   **Cons**: Every one of these variants is still, in substance, a
    screenshot — and the published privacy notice's wording ("Ever,
    including on request") specifically and explicitly forecloses the
    on-demand framing by name, not by implication. The CI guard also bans
    the capability by import, not by a usage pattern of it, so a lower
    cadence or narrower crop trips the same check the same way.
*   **Reason for Rejection**: Rejected by author, following the
    brainstorm's converged finding across multiple lenses: no scope
    reduction on the capture axis changes who needs to agree to this or
    removes the governance prerequisite. This is recorded here for
    completeness, not because any version of it was found viable.

### Alternative B: Dodge the privacy guard via a non-named capture technique (raw `ctypes` Win32 calls, shelling out to an external process)

*   **Pros**: Technically avoids tripping `scripts/check_privacy.py`'s
    named import/call checks, confirmed by direct analysis during the
    brainstorm.
*   **Cons**: The guard's own output text explicitly pre-empts this exact
    move: "If this is a false positive, change the guard deliberately in
    scripts/check_privacy.py rather than working around it." A bypass
    that avoids editing the file is the specific outcome the guard's
    authors documented as undesirable, not an overlooked loophole to use.
*   **Reason for Rejection**: Rejected by author. Not a legitimate path
    regardless of its technical feasibility.

### Alternative C: A metadata-only, non-screen-content richer-activity-signal alternative

*   **Pros**: Fits this codebase's existing "extract a minimal signal,
    discard the rest" architecture (window-title hashing, domain-only
    extraction, input-timing-only idle detection) with zero new storage
    class, zero new sync channel, and zero new retention mechanism — and
    does not conflict with the published privacy notice or its guard at
    all.
*   **Cons**: Does not deliver viewable screenshots, so it does not
    actually satisfy the anchored hypothesis as given.
*   **Reason for Rejection**: Not rejected on its merits — recorded in
    the brainstorm as a separate, future feature rather than adopted here,
    since this document was explicitly asked to draft the literal
    screenshot feature, conflict carried forward, rather than substitute
    a different feature for it.

### Alternative D: Extend the existing `Activity`/`ActivityType` model with a new screenshot type

*   **Pros**: Reuses an existing, already-built, already-tested model and
    viewset rather than standing up a new app.
*   **Cons**: `Activity`'s schema is deliberately interval-shaped
    (`start_time`/`end_time`/`duration_seconds`) specifically to bound
    per-PC row counts to "a few hundred rows per day" rather than tens of
    thousands; a screenshot is a point-in-time, blob-backed artifact with
    no interval semantics, and would force permanently-null interval
    fields onto every screenshot row or reintroduce the exact per-sample
    row growth this model's design was built to avoid.
*   **Reason for Rejection**: Rejected by author, per the brainstorm's
    structural and design findings. A new, dedicated app was chosen
    instead, consistent with how `tasks`, `vault`, and `events` were each
    introduced as their own app.

### Alternative E: Cloud or self-hosted object storage instead of local filesystem

*   **Pros**: Scales past a single server's disk capacity, which the
    brainstorm's own estimate (200-600GB resident at this feature's
    retention window, for a modest fleet) suggests local storage may not
    comfortably hold at real scale; a self-hosted option (e.g. MinIO)
    would also match this project's existing self-hosted, single-target
    deployment pattern better than a cloud vendor would.
*   **Cons**: Both add new infrastructure this codebase has never
    needed — either a new third-party cloud vendor dependency and
    credential-management surface, or a new self-hosted service to run,
    monitor, and back up.
*   **Reason for Rejection**: Rejected by author in favor of local
    filesystem storage, accepting the capacity ceiling as an explicit,
    named constraint (see Non-Functional Requirements) rather than taking
    on new infrastructure for a feature that is not yet authorized to be
    built at all.

### Alternative F: Timestamp-only correlation instead of an FK to the open `Activity` session

*   **Pros**: Avoids any cross-retention dangling-reference risk entirely,
    since there is no foreign key to manage across two records with
    independent retention windows.
*   **Cons**: Answering "what was foreground when this was captured"
    needs a secondary time-range query instead of a direct join, every
    time it's asked.
*   **Reason for Rejection**: Rejected by author in favor of a nullable
    FK with `on_delete=SET_NULL` — this gets the direct-join convenience
    while still fully avoiding the dangling-reference risk, since the
    reference simply clears rather than blocking or cascading when the
    `Activity` row purges first.

--------------------------------------------------------------------------------

## Detailed Implementation Plan

**Deliberate omission, stated explicitly rather than left silent:** this
plan enumerates the backend/frontend plumbing around *stored* screenshot
data (viewing, disclosure, retention) but does **not** enumerate the
desktop-agent capture collector itself. Designing that component's exact
shape would mean designing the specific thing `scripts/check_privacy.py`
exists to reject, before the governance prerequisites in Open Questions
have resolved — and the brainstorm separately identified the agent-side
sync/transport mechanism (binary upload, local buffering, bandwidth) as
its own unresolved capacity question, not a known quantity this plan could
responsibly fill in. If the governance prerequisites resolve, the
capture-side design is its own follow-up work, not an extension of this
plan.

### Target Files to Create/Modify

#### 1. `backend/screenshots/__init__.py` (Create)

*   **Type / Scope**: Django app package marker.
*   **Proposed Changes**: Empty file marking `screenshots` as a new Django
    app, mirroring every other app in `backend/`.

#### 2. `backend/screenshots/apps.py` (Create)

*   **Type / Scope**: Django app config.
*   **Proposed Changes**: `ScreenshotsConfig(AppConfig)` with
    `default_auto_field` and `name = "screenshots"`.

#### 3. `backend/screenshots/models.py` (Create)

*   **Type / Scope**: Django models.
*   **Proposed Changes**: `ReviewStatus(TextChoices)`: `PENDING_REVIEW`,
    `CLEARED`. `ScreenshotCapture`: `employee` (FK → Employee,
    `on_delete=PROTECT`), `computer` (FK → Computer,
    `on_delete=PROTECT`), `activity` (FK → `activities.Activity`,
    `null=True`, `on_delete=SET_NULL`), `captured_at` (DateTimeField),
    `file` (FileField, using a dedicated `FileSystemStorage` instance
    pointed at `settings.SCREENSHOT_STORAGE_ROOT`), `review_status`
    (CharField, choices=`ReviewStatus.choices`, default
    `PENDING_REVIEW`), `created_at`. Indexes on `employee` and
    `captured_at` (the latter because retention and any future "capture
    around this time" query both filter on it).

#### 4. `backend/screenshots/permissions.py` (Create)

*   **Type / Scope**: DRF permission class.
*   **Proposed Changes**: `IsAdminOnly` — `has_permission` requires
    `user.is_admin`; no owner/grantee branch at all, unlike every other
    feature in this codebase, per the anchored hypothesis's explicit
    exclusion of the captured employee from viewing their own data.

#### 5. `backend/screenshots/serializers.py` (Create)

*   **Type / Scope**: DRF serializers.
*   **Proposed Changes**: `ScreenshotCaptureSerializer` — `id`, `employee`
    (stub), `computer` (stub), `captured_at`, `review_status`,
    `view_count` and `last_viewed_by` (both `SerializerMethodField`,
    reading `AuditLog` entries filtered to
    `action=SCREENSHOT_VIEWED_BY_ADMIN` for this capture). Never includes
    the image or a URL to it — the `file` field is deliberately absent
    from this serializer; only the dedicated `view` action ever returns
    image bytes.

#### 6. `backend/screenshots/views.py` (Create)

*   **Type / Scope**: DRF views.
*   **Proposed Changes**: `ScreenshotCaptureViewSet(ReadOnlyModelViewSet)`
    — list/retrieve only, no create/update/delete via the API (rows are
    written only by the out-of-scope agent ingest path and removed only
    by the retention job). `get_queryset()` returns everything for admins,
    `.none()` for everyone else — no employee-scoped branch at all, since
    there is no employee-visible tier of this resource. A `view` detail
    action (`GET`), decorated with the new `screenshot-view` throttle
    scope: 403s if `review_status != CLEARED`; otherwise calls
    `core.audit.record(actor=request.user,
    action=AuditLog.Action.SCREENSHOT_VIEWED_BY_ADMIN, target=capture)`
    unconditionally, then streams the file (e.g. via
    `FileResponse`) rather than embedding it in a JSON body.

#### 7. `backend/screenshots/admin.py` (Create)

*   **Type / Scope**: Django admin registration.
*   **Proposed Changes**: Registers `ScreenshotCapture` for operational
    visibility (who/when/status), explicitly excluding the `file` field
    from every list/detail view and providing no way to render the image
    via Django admin at all — mirroring the Vault's admin registration,
    and for the same reason: every view of the actual content must go
    through the audited `view` action, never a second, unlogged path.

#### 8. `backend/screenshots/retention.py` (Create)

*   **Type / Scope**: Retention job.
*   **Proposed Changes**: A dedicated purge routine, modeled on
    `activities/retention.py`'s discipline (narrowly-scoped queryset on
    `ScreenshotCapture` alone, dry-run-equals-real-run auditing, an
    `AuditLog` entry per run including empty runs) but reading a new,
    separate `AppSettings.screenshot_retention_days` field — never
    `activity_retention_days`. Deletes the backing file and the DB row
    together per capture, verifying the file delete before committing the
    row delete, so a failure leaves an identifiable orphaned file rather
    than a silently vanished row with a leaked file.

#### 9. `backend/screenshots/management/commands/purge_screenshots.py` (Create)

*   **Type / Scope**: Django management command.
*   **Proposed Changes**: Thin wrapper invoking `retention.py`, mirroring
    `activities/management/commands/purge_activity.py`'s shape (the
    existing scheduled-job entry point convention).

#### 10. `backend/screenshots/migrations/0001_initial.py` (Create)

*   **Type / Scope**: Django migration.
*   **Proposed Changes**: Generated via `makemigrations screenshots`;
    creates the `ScreenshotCapture` table and its indexes.

#### 11. `backend/attendance/models.py` (Modify)

*   **Type / Scope**: `AppSettings` singleton.
*   **Proposed Changes**: Add `screenshot_retention_days` (IntegerField,
    admin-configurable, with its own default — not inherited from
    whatever `activity_retention_days` is set to), plus a corresponding
    migration. Kept as its own field specifically so changing one
    retention window never silently changes the other, per the
    brainstorm's tech-debt/coupling finding.

#### 12. `backend/config/settings.py` (Modify)

*   **Type / Scope**: Django settings.
*   **Proposed Changes**: Add `"screenshots"` to `INSTALLED_APPS`. Add
    `SCREENSHOT_STORAGE_ROOT` (a new setting, a directory outside
    `STATIC_ROOT`/`MEDIA_ROOT`'s web-served path, required in production
    the same `DEBUG`-only-fallback way `VAULT_ENCRYPTION_KEY` is). Add a
    `screenshots.storage.ScreenshotStorage` `FileSystemStorage` subclass
    instance pointed at that root, used only by `ScreenshotCapture.file`.
    Add a `"screenshot-view"` entry to
    `REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]`.

#### 13. `backend/config/urls.py` (Modify)

*   **Type / Scope**: URL routing.
*   **Proposed Changes**: Import `ScreenshotCaptureViewSet` from
    `screenshots.views`; register `router.register("screenshots",
    ScreenshotCaptureViewSet, basename="screenshot")`, following this
    codebase's established direct-router-registration convention.

#### 14. `backend/core/models.py` (Modify)

*   **Type / Scope**: Shared `AuditLog` model.
*   **Proposed Changes**: Add `SCREENSHOT_VIEWED_BY_ADMIN = (
    "SCREENSHOT_VIEWED_BY_ADMIN", "Screenshot viewed by admin")` to
    `AuditLog.Action`.

#### 15. `backend/tests/factories.py` (Modify)

*   **Type / Scope**: Factory Boy test factories.
*   **Proposed Changes**: Add `ScreenshotCaptureFactory`, defaulting
    `review_status=CLEARED` (tests that specifically need
    `PENDING_REVIEW` behavior override it explicitly).

#### 16. `backend/tests/test_screenshots.py` (Create)

*   **Type / Scope**: Pytest test suite.
*   **Proposed Changes**: Test classes covering: admin-only visibility
    (unauthenticated → 403; non-admin employee, including the captured
    employee themselves → 403/empty queryset; admin → 200); the
    `review_status` gate (a `PENDING_REVIEW` capture's `view` action 403s
    for every admin; a `CLEARED` one succeeds); unconditional audit
    logging on every successful `view` (not conditional the way the
    Vault's is, since there is no owner/grantee exemption here); the
    `screenshot-view` throttle actually limits repeated calls; retention
    (`retention.py` deletes both the file and the row together, and a
    simulated file-delete failure does not silently delete the row).

### Frontend

#### 17. `frontend/src/api/client.js` (Modify)

*   **Type / Scope**: API client.
*   **Proposed Changes**: Add `listScreenshots`, `getScreenshot`,
    `viewScreenshot` (the last one hitting the `view` action specifically,
    not a generic detail fetch).

#### 18. `frontend/src/views/ScreenshotsView.vue` (Create)

*   **Type / Scope**: Vue view — admin-only list.
*   **Proposed Changes**: List of captures (employee, computer,
    captured_at, review-status badge, view count) — never an inline
    thumbnail or preview, consistent with the "only the dedicated `view`
    action ever returns image bytes" rule. A `PENDING_REVIEW` row shows no
    way to open it at all, reinforcing the gate in the UI rather than
    only in the API.

#### 19. `frontend/src/views/ScreenshotDetailView.vue` (Create)

*   **Type / Scope**: Vue view — admin-only detail/view.
*   **Proposed Changes**: Mirrors the Vault's explicit-reveal-click
    pattern: the image is never auto-fetched on page load; an explicit
    "View screenshot" click calls the `view` action, so opening this page
    to read metadata does not itself generate an audit log entry — only
    actually choosing to view the image does. Shows the `last_viewed_by`/
    `view_count` disclosure.

#### 20. `frontend/src/router/index.js` (Modify)

*   **Type / Scope**: Vue Router.
*   **Proposed Changes**: Add `/screenshots` and `/screenshots/:id`
    routes, `meta: { requiresAuth: true, requiresAdmin: true }` — unlike
    every other feature added so far, this is admin-only at the route
    level too, since there is no employee-facing view of this resource at
    all.

#### 21. `frontend/src/App.vue` (Modify)

*   **Type / Scope**: Navigation shell.
*   **Proposed Changes**: Add a nav entry to the admin link array only
    (not the employee array, unlike Tasks/Vault/Events, which both role
    arrays include).

#### 22. `frontend/src/components/NavIcon.vue` (Modify)

*   **Type / Scope**: Icon set.
*   **Proposed Changes**: Add a new icon distinct from the existing
    `calendar`/`calendar-event` glyphs.

### Verification Plan

*   **Compilation/Build**: `backend`: `./.venv/Scripts/python.exe
    manage.py check`; `frontend`: `npm run build`.
*   **Unit Tests**: `pytest backend/tests/test_screenshots.py` (and the
    full suite) with `SCREENSHOT_STORAGE_ROOT` set to a test-scoped
    temporary directory.
*   **Static Analysis & Linting**: `ruff check .`, `black --check .`,
    `npx eslint src/` — and, unlike every prior feature in this project,
    `python scripts/check_privacy.py` must also be re-run and must still
    pass, since this feature's whole premise is that it does **not**
    touch the capture mechanism the guard polices. If implementing this
    plan ever causes that guard to fail, that is a signal the governance
    prerequisites were not actually satisfied first.
*   **Test Coverage Requirement**: Every admin-only branch, the
    `PENDING_REVIEW` gate, unconditional audit logging on `view`, and the
    retention job's paired file+row deletion must each have a dedicated
    test.
*   **E2E/Integration**: Deliberately not specified here. Live browser
    verification of this feature would require real captured screenshot
    data to exist, which depends on the out-of-scope agent capture
    component — this plan's verification stops at the server-side
    plumbing it actually defines.

--------------------------------------------------------------------------------

<!-- Provenance: Indicates initial structural drafting via EGM. -->

*Drafted with EGM*
