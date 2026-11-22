# Work Credential Store

*   **Author:** Israfil
*   **Status:** Draft
*   **Date:** 2026-11-22

--------------------------------------------------------------------------------

## Overview

A credential-storage feature for the existing employee attendance & PC
activity tracking system, letting an employee store logins for shared work
resources (vendor portals, shared tools, service accounts) and share a
specific entry with named coworkers. It is scoped and labeled explicitly as
a work-credential store, not a general personal password manager — a
naming/framing decision made during brainstorming to resolve a dissent about
whether this product should hold personal secrets at all.

## The Problem

There is currently no built-in place in this system for an employee to store
or share a login for a shared work resource. In practice this means
passwords for vendor portals, shared SaaS tools, or service accounts get
passed around through chat messages, shared spreadsheets, or sticky notes —
channels this system has no visibility into and no control over. The
proposed solution is a credential store, scoped to work logins, with
server-side encryption and explicit per-entry sharing to named coworkers.

## Goals

*   An employee can store a credential entry (title, username/login, secret
    password, optional URL, optional notes) for a work-related login.
*   An entry's owner can share it with one or more specific named coworkers;
    a recipient can view/reveal the password but cannot edit the entry or
    re-share it onward.
*   The owner can revoke a coworker's access to an entry at any time.
*   Credentials are encrypted at rest; the backend can decrypt them to serve
    the UI (not a zero-knowledge/client-side model — chosen for simplicity).
*   Admins can view any employee's entries, shared or not, consistent with
    this codebase's existing admin-visibility pattern for attendance,
    activity, and task data — but unlike those existing features, every
    entry discloses this to the employee, and every admin reveal of a
    non-shared entry is logged and surfaced back to the entry's owner. This
    resolves a brainstorm-stage dissent that blanket admin access here would
    otherwise be a silent, undisclosed power with no equivalent elsewhere in
    this codebase's audit trail.
*   The feature is named and onboarded explicitly as a work-credential
    store — not a "personal vault" — so its framing doesn't promise a
    privacy guarantee (sole, private ownership) the design doesn't deliver.

## Non-Goals

*   Zero-knowledge/client-side encryption — the backend can always decrypt
    stored credentials; this was weighed against zero-knowledge encryption
    and rejected for simplicity.
*   Teams/groups as a sharing target — this codebase has no such concept;
    sharing is always to one or more individually named employees.
*   Edit or re-share rights for a share recipient — only the owner can edit
    an entry or change who it's shared with.
*   Folders, categories, tags, or any grouping mechanism beyond a flat list
    of entries per employee.
*   Expiring or time-bound shares (e.g. auto-revoke after N days).
*   Tracking when a password was last changed/rotated.
*   Any technical enforcement of the "work credentials only" framing (e.g. a
    classifier blocking personal-looking entries) — this is a naming and
    onboarding-copy decision only; nothing stops an employee from storing a
    personal credential anyway, and that limit is accepted, not hidden.
*   Key rotation tooling — see Open Questions; the absence of a rotation
    story is an accepted risk for this iteration, not a solved problem.

## Open Questions

*   **Build vs. buy**: Should this be built in-house at all, versus adopting
    an existing purpose-built tool (e.g. Bitwarden, 1Password Teams) that
    already solves shared-credential storage with a stronger security
    posture than this design's "simplicity first" choice? Not resolved by
    the brainstorm brief or this draft — a conscious answer is still needed
    before implementation starts.
*   **Key management**: Where does the encryption key live (beyond "a
    dedicated env var, never `DJANGO_SECRET_KEY`"), is there any backup or
    rotation plan, or is permanent, irrecoverable data loss on key loss an
    explicitly accepted risk? This codebase has no existing precedent for a
    server-held, reversible-encryption secret to extend.
*   **Owner-disabled/deleted cascade behavior**: What happens to an entry
    and its live shares when the owning employee is disabled or removed —
    cascade delete, block the removal, or something else? Every comparable
    foreign key elsewhere in this codebase (e.g. `Task.created_by`) makes a
    deliberate choice here rather than taking Django's CASCADE default.
*   **Encryption granularity**: Is only the password field encrypted, or the
    whole entry row? This determines whether list/search views (including
    any admin "browse all" view) stay cheap, or require decrypting every row
    just to render a title.
*   **`cryptography`/Fernet packaging**: Is adding this dependency actually
    orthogonal to the existing Django 4.0.10/psycopg2/PostgreSQL 10.23
    version pin, given `backend/Dockerfile`'s base image? Not yet confirmed.
*   **Activity-tracking interaction**: Could this product's own PC
    activity-tracking engine capture a password while it's being viewed or
    typed into this feature? This draft does not resolve that question —
    it is acknowledged as the most likely source of employee concern if the
    two features' interaction is ever found to be unaddressed.

## Critical User Journeys (CUJs)

### CUJ 1: An employee stores a work credential

*   **Given**: An authenticated employee has a login for a shared work tool
    they need to keep track of.
*   **When**: They create a new entry with a title, username, password, and
    optional URL/notes.
*   **Then**: The entry is stored encrypted, visible only to them (and,
    disclosed on the entry, to admins) until they choose to share it.

### CUJ 2: An owner shares an entry with a coworker, who reveals it

*   **Given**: An employee owns a credential entry for a shared vendor
    portal that a coworker also needs to use.
*   **When**: The owner shares the entry with that specific coworker; the
    coworker opens the entry and reveals the password.
*   **Then**: The coworker can see the password but cannot edit the entry or
    share it onward to anyone else; the entry's visibility disclosure now
    lists that coworker as well.

### CUJ 3: An owner revokes a coworker's access

*   **Given**: A coworker was previously granted view access to an entry.
*   **When**: The owner revokes that access.
*   **Then**: The coworker can no longer view the entry going forward — but
    the revoke action's own confirmation states plainly that this doesn't
    undo any knowledge the coworker already gained from previously viewing
    it, and suggests rotating the actual credential if that's a concern.

### CUJ 4: An admin views an employee's entry that wasn't shared with them

*   **Given**: An employee has a credential entry that is not shared with
    any admin.
*   **When**: An admin opens that employee's vault and reveals the entry.
*   **Then**: The reveal succeeds (admins always have access), it is
    recorded in the audit log, and the entry's owner can see that it was
    last viewed by that admin on that date.

## Technical Plan (Architecture)

### Data model

A new `vault` Django app, mirroring how `tasks` was added as its own app:

*   **`VaultEntry`**: `owner` (FK → Employee), `title` (plaintext),
    `username` (plaintext), `secret_ciphertext` (encrypted, see below),
    `url` (plaintext, optional), `notes` (plaintext, optional),
    `created_at`, `updated_at`. Only `secret_ciphertext` is encrypted —
    title, username, URL, and notes stay as ordinary plaintext columns, so
    list/search views never need to decrypt anything just to render an
    entry's metadata.
*   **`VaultEntryGrant`** (through-model, mirroring `TaskAssignee`):
    `entry` (FK → VaultEntry), `grantee` (FK → Employee), `granted_by` (FK →
    Employee), `granted_at`. A `UniqueConstraint` on `(entry, grantee)`
    prevents duplicate grants. A grant is always a live reference to
    `entry` — never a copy of the secret — so a later password change is
    immediately reflected for every existing grantee, with no separate
    "stale grant" state possible.

### Encryption

A new `vault/crypto.py` module wraps the `cryptography` package's Fernet
symmetric encryption: `encrypt_secret(plaintext) -> bytes` and
`decrypt_secret(ciphertext) -> str`. The key is read from a new,
dedicated `VAULT_ENCRYPTION_KEY` environment variable in
`backend/config/settings.py` — never a reuse of `DJANGO_SECRET_KEY` — and
is required in production the same way `DJANGO_SECRET_KEY` already is
(`env("VAULT_ENCRYPTION_KEY", required=not DEBUG)`).

### Permissions

A new `IsVaultEntryOwnerOrGranteeOrAdmin` permission class (the fourth
distinct permission shape in this codebase, after `IsAdmin`,
`IsAdminOrReadOnlySelf`, and Task Tracking's `IsTaskParticipantOrAdmin`):

*   The **owner** can view, edit, delete, share, and revoke.
*   A **grantee** can only view/reveal — never edit, delete, share, or
    revoke another grantee.
*   An **admin** can view/reveal any entry, but cannot edit, delete, or
    manage another employee's shares (this is deliberately a visibility
    override only, not a full admin-takeover of someone else's entry).

### Visibility enforcement

`VaultEntryViewSet.get_queryset()` filters to "owner, or an explicit
grantee, or admin sees all" at the queryset level — the same pattern as
`activities/views.py`'s `resolve_employee()` and Task Tracking's
`TaskViewSet.get_queryset()` — so a view that omits a permission check
still cannot leak another employee's entries.

### The "reveal" action is separate from list/retrieve

List and retrieve responses never include the decrypted password — only
metadata (title, username, URL, notes, and the per-entry visibility
disclosure described below). A dedicated `POST
/api/vault-entries/{id}/reveal/` action is the only place the decrypted
secret is ever returned. This separation is what makes two other decisions
clean to implement:

*   **Rate limiting**: a new `vault-reveal` DRF throttle scope applies only
    to this action, following the precedent already set for `login`
    (`DEFAULT_THROTTLE_RATES`) — the blanket `2000/hour` default `user`
    throttle never has to cover a decrypt operation.
*   **Conditional audit logging**: the `reveal` action checks whether the
    requester is the owner or an explicit grantee. If not — meaning an
    admin is exercising the blanket-visibility override — it calls
    `core.audit.record()` with a new `VAULT_ENTRY_REVEALED_BY_ADMIN`
    `AuditLog.Action` value, and the entry's own serializer surfaces the
    most recent such event back to the owner (e.g. "Last viewed by
    [admin] on [date]"). Owner and grantee reveals are not logged — only
    the admin blanket-access case, since that is the specific contradiction
    the brainstorm review flagged as needing disclosure and accountability.

### Visibility disclosure

Every `VaultEntry` serializer response includes a computed field listing
exactly who can currently see it: the owner, every current grantee, and a
fixed "all admins" notice — the mechanism described in the Goals section
that makes blanket admin access disclosed rather than silent.

### API surface

*   `GET/POST /api/vault-entries/` — list (metadata only; owner + shared +
    admin-sees-all) / create.
*   `GET/PATCH/DELETE /api/vault-entries/{id}/` — retrieve (metadata only) /
    update (owner only) / delete (owner only).
*   `POST /api/vault-entries/{id}/reveal/` — returns the decrypted
    password; throttled; conditionally audit-logged (see above).
*   `POST /api/vault-entries/{id}/share/` — owner-only; body `{employee}`;
    creates a `VaultEntryGrant`.
*   `DELETE /api/vault-entries/{id}/grants/{employee_id}/` — revokes a
    grant; the owner can revoke any grantee, and a grantee can revoke their
    own access (self-removal), mirroring Task Tracking's `remove_assignee`.
*   `GET /api/vault-entries/assignable-employees/` (or a shared/reused
    endpoint) — reuses Task Tracking's `AssignableEmployeesView` pattern for
    the "pick a coworker to share with" UI, rather than building a second,
    near-identical endpoint.

### Data flow (reveal action)

```text
Employee/Admin                DRF View                   DB / crypto
     |                            |                             |
     |  POST .../reveal/          |                             |
     |--------------------------->|                             |
     |                            | get_object() -- queryset    |
     |                            | filters to owner/grantee/   |
     |                            | admin, else 404              |
     |                            |---------------------------->|
     |                            |   fetch VaultEntry row       |
     |                            |<----------------------------|
     |                            | permission check:            |
     |                            |  owner/grantee -> no log     |
     |                            |  admin, not grantee -> log   |
     |                            |---------------------------->|
     |                            |  decrypt_secret(ciphertext)  |
     |                            |<----------------------------|
     |<---------------------------|  {password: "..."}           |
```

## Alternatives Considered

### Alternative A: Zero-knowledge, client-side encryption

*   **Pros**: The backend never sees plaintext or holds a key that can
    decrypt stored secrets; a database breach or malicious admin cannot
    expose any password. Matches the trust model of dedicated password
    managers (1Password, Bitwarden).
*   **Cons**: Significantly more implementation complexity (key derivation
    from a user passphrase, client-side crypto in the Vue frontend, no
    server-side password recovery if a user forgets their passphrase).
    Sharing an entry with a coworker also becomes harder, since the server
    can't re-encrypt a secret it can't read — each share needs its own
    client-side re-encryption step.
*   **Reason for Rejection**: Rejected by author: explicitly chosen against
    in favor of server-side decryption, for implementation simplicity, with
    the resulting blast-radius risk accepted and compensated for elsewhere
    (dedicated key, audit logging of admin reveals) rather than eliminated.

### Alternative B: Admins locked out of entries not explicitly shared with them

*   **Pros**: Removes the exact contradiction the brainstorm review
    flagged at Blocker severity — a vault that markets peer-level privacy
    via sharing/revocation would no longer simultaneously grant a third
    party (admins) silent blanket access.
*   **Cons**: Breaks from every other feature in this codebase (attendance,
    activity, task visibility), all of which give admins blanket access;
    would also remove any path for IT/support to assist an employee locked
    out of their own account recovery, or to investigate misuse, without a
    separate break-glass mechanism this design doesn't otherwise need.
*   **Reason for Rejection**: Rejected by author: consistency with this
    codebase's existing admin-visibility convention was chosen over
    matching the privacy expectation a password manager normally sets. The
    resulting contradiction is addressed with a cheaper compensating
    control instead — per-entry disclosure plus audit logging of admin
    reveals — rather than by removing blanket access outright.

### Alternative C: A flatter, admin-curated shared-credential list instead of per-entry, multi-grantee sharing

*   **Pros**: Much less authorization surface to build — a single shared
    list with a plain list of viewer IDs needs no distinct grant entity, no
    revocation action, and no new permission class, since the existing
    owner/admin visibility already covers it.
*   **Cons**: Doesn't give an individual employee their own private entries
    at all — only a single shared pool — which doesn't match the stated
    goal of each employee having a personal set of entries they can
    optionally choose to share.
*   **Reason for Rejection**: Rejected by author: the user specified a
    personal vault with per-entry sharing explicitly during brainstorming,
    before this alternative was raised. Recorded here as a smaller fallback
    if real usage later shows the fine-grained sharing/revocation machinery
    isn't earning its keep.

### Alternative D: Soft-delete / revocation-history table for shares

*   **Pros**: Preserves a full history of who was ever granted or revoked
    access to an entry, which could matter for a security-sensitive
    feature like this one.
*   **Cons**: No comparable relation anywhere else in this codebase keeps
    this kind of history (Task Tracking's `remove_assignee` is a plain
    delete); building it here would be new, speculative infrastructure with
    no stated requirement driving it.
*   **Reason for Rejection**: Rejected by author: a plain `grant.delete()`,
    mirroring Task Tracking's existing `remove_assignee` pattern, was chosen
    instead — if a real need for grant history emerges later, the admin
    audit log already covers the one case (admin reveals) that most needed
    a trail.

### Alternative E: Bare `ManyToManyField` for sharing instead of a through-model

*   **Pros**: Less code to write initially — no separate `VaultEntryGrant`
    model or migration.
*   **Cons**: Can't carry `granted_by`/`granted_at` metadata; converting a
    bare M2M to a through-model later is a breaking migration touching every
    caller, the same lesson Task Tracking's `TaskAssignee` design was built
    around.
*   **Reason for Rejection**: Rejected by author: the explicit
    `VaultEntryGrant` through-model was chosen from the start for the same
    reason Task Tracking adopted `TaskAssignee` — the per-grant metadata is
    needed immediately, not added speculatively.

--------------------------------------------------------------------------------

## Non-Functional Requirements

*   **Security & Privacy**: Secrets are encrypted at rest (password field
    only); the decryption key is a dedicated environment-held secret,
    never reused from `DJANGO_SECRET_KEY`. Admin access to a non-shared
    entry is always disclosed on the entry and audit-logged. Key loss means
    permanent, unrecoverable data loss for every stored entry — accepted as
    a known risk for this iteration (see Open Questions), not solved here.
*   **Performance**: Because only the password field is encrypted, list and
    search views query and sort on plaintext columns directly and never
    decrypt rows in bulk; decryption only happens on the single-row
    `reveal` action.
*   **Rollout**: This is new functionality behind a new app and new API
    routes; it does not modify any existing endpoint's behavior, so no
    feature flag or migration of existing data is required to ship it.

--------------------------------------------------------------------------------

## Detailed Implementation Plan

### Target Files to Create/Modify

#### 1. `backend/vault/__init__.py` (Create)

*   **Type / Scope**: Django app package marker.
*   **Proposed Changes**: Empty file marking `vault` as a new Django app,
    mirroring `backend/tasks/__init__.py`.

#### 2. `backend/vault/apps.py` (Create)

*   **Type / Scope**: Django app config.
*   **Proposed Changes**: `VaultConfig(AppConfig)` with `default_auto_field`
    and `name = "vault"`, mirroring `backend/tasks/apps.py`.

#### 3. `backend/vault/models.py` (Create)

*   **Type / Scope**: Django models.
*   **Proposed Changes**:
    *   `VaultEntry`: `owner` (FK → `Employee`, `on_delete` per the open
        cascade-behavior question below), `title` (CharField), `username`
        (CharField), `secret_ciphertext` (BinaryField or TextField storing
        Fernet ciphertext — never a plaintext column), `url` (URLField,
        blank), `notes` (TextField, blank), `created_at`, `updated_at`.
    *   `VaultEntryGrant`: `entry` (FK → `VaultEntry`, `on_delete=CASCADE` —
        a grant has no independent existence once its entry is gone),
        `grantee` (FK → `Employee`), `granted_by` (FK → `Employee`,
        `on_delete=PROTECT`, mirroring `TaskAssignee.assigned_by`),
        `granted_at` (auto_now_add). `UniqueConstraint(fields=["entry",
        "grantee"], name="unique_grant_per_entry")`.
    *   Model-level docstring records the still-open question (see Open
        Questions) about `VaultEntry.owner`'s `on_delete` behavior, so it
        isn't silently decided by whichever value ships first.

#### 4. `backend/vault/crypto.py` (Create)

*   **Type / Scope**: Encryption helper module.
*   **Proposed Changes**: `encrypt_secret(plaintext: str) -> bytes` and
    `decrypt_secret(ciphertext: bytes) -> str`, wrapping
    `cryptography.fernet.Fernet` keyed from
    `settings.VAULT_ENCRYPTION_KEY`. No clock/IO dependency beyond that
    setting, so this module is trivially unit-testable in isolation
    (encrypt then decrypt round-trips to the original string).

#### 5. `backend/vault/permissions.py` (Create)

*   **Type / Scope**: DRF permission class.
*   **Proposed Changes**: `IsVaultEntryOwnerOrGranteeOrAdmin`, branching on
    `view.action` the same way Task Tracking's `IsTaskParticipantOrAdmin`
    does: owner → full control (view/edit/delete/share/revoke-any); grantee
    → `retrieve`/`reveal` only; self-revoke of their own grant allowed via a
    `revoke_grant` action check comparing the requester to the grant's
    `grantee`; admin → `retrieve`/`reveal` always, but not
    `update`/`destroy`/`share`/`revoke_grant` on an entry they don't own.

#### 6. `backend/vault/serializers.py` (Create)

*   **Type / Scope**: DRF serializers.
*   **Proposed Changes**:
    *   `_EmployeeStubSerializer` (reused shape from `tasks/serializers.py`
        — id/employee_id/name only).
    *   `VaultEntryGrantSerializer`: grantee stub, granted_by stub,
        granted_at. Never includes any secret.
    *   `VaultEntrySerializer`: title, username, url, notes, `grants`
        (nested `VaultEntryGrantSerializer` list), `visible_to`
        (SerializerMethodField computing `[owner stub] + [grant.grantee for
        grant in grants] + ["All admins"]` — the disclosure line from the
        Technical Plan), `last_admin_reveal` (SerializerMethodField reading
        the most recent matching `AuditLog` row for this entry, or `null`).
        The secret/password field is deliberately never present on this
        serializer — not even write-only-masked — because create/update use
        a separate explicit field (see below) and reveal uses a separate
        response serializer entirely.
    *   `VaultEntryWriteSerializer` (or a `password` field added only on
        create/update): accepts a plaintext `password` on input, calls
        `encrypt_secret()` before saving, never returns it in the response.
    *   `VaultEntryRevealSerializer`: the only serializer that ever exposes
        `password` (plaintext, decrypted on the fly) — used solely by the
        `reveal` action's response.

#### 7. `backend/vault/views.py` (Create)

*   **Type / Scope**: DRF views.
*   **Proposed Changes**:
    *   `VaultEntryViewSet(viewsets.ModelViewSet)`: `get_queryset()` filters
        to `Q(owner=employee) | Q(grants__grantee=employee)` for
        non-admins (`.distinct()` required, the same Django trap Task
        Tracking named explicitly), unfiltered for admins — mirroring
        `TaskViewSet.get_queryset()`.
    *   `perform_create()`: sets `owner=employee`, encrypts the submitted
        plaintext password via `crypto.encrypt_secret()` before save.
    *   `@action(detail=True, methods=["post"]) def reveal(...)`: calls
        `get_object()` (enforcing visibility/permission as usual), decrypts
        via `crypto.decrypt_secret()`, and — only if the requester is
        neither the owner nor an existing grantee — calls
        `core.audit.record(actor=request.user,
        action=AuditLog.Action.VAULT_ENTRY_REVEALED_BY_ADMIN,
        target_type="VaultEntry", target_id=entry.pk)` before returning the
        decrypted value via `VaultEntryRevealSerializer`. Decorated with a
        dedicated `vault-reveal` DRF throttle scope.
    *   `@action(detail=True, methods=["post"]) def share(...)`: owner-only
        (enforced by the permission class); body `{"employee": <id>}`;
        creates a `VaultEntryGrant`; re-fetches and re-serializes the entry
        fresh from the DB afterward, following Task Tracking's
        `_reserialize()` pattern, since a bare `.create()` call on a
        prefetched relation does not invalidate an already-fetched
        instance's cache.
    *   `@action(detail=True, methods=["delete"],
        url_path="grants/(?P<employee_id>[^/.]+)") def revoke_grant(...)`:
        deletes the matching `VaultEntryGrant`; allowed for the owner (any
        grantee) or the grantee themselves (self-removal only); re-fetches
        and re-serializes afterward for the same cache-staleness reason.
    *   Reuses `tasks.views.AssignableEmployeesView` directly (imported, not
        duplicated) for the "pick a coworker to share with" picker, since
        its shape (id/employee_id/name, any authenticated user) is already
        exactly what this feature needs.

#### 8. `backend/vault/admin.py` (Create)

*   **Type / Scope**: Django admin registration.
*   **Proposed Changes**: Registers `VaultEntry` and `VaultEntryGrant` for
    visibility in the Django admin, but the `VaultEntry` admin explicitly
    excludes `secret_ciphertext` from every list/detail view and provides
    no decrypt action — Django admin is for operational visibility
    (counts, who owns what, grant records), not a second way to read
    passwords. This is a deliberate scope limit, not an oversight, and
    should be called out in review.

#### 9. `backend/vault/migrations/0001_initial.py` (Create)

*   **Type / Scope**: Django migration.
*   **Proposed Changes**: Generated via `makemigrations vault`; creates the
    `VaultEntry` and `VaultEntryGrant` tables, the unique constraint, and
    any indexes DRF's default ordering needs (e.g. an index on
    `VaultEntry.owner`).

#### 10. `backend/config/settings.py` (Modify)

*   **Type / Scope**: Django settings.
*   **Proposed Changes**: Add `"vault"` to `INSTALLED_APPS`. Add
    `VAULT_ENCRYPTION_KEY = env("VAULT_ENCRYPTION_KEY", required=not
    DEBUG)`, with the same `DEBUG`-only insecure-fallback pattern
    `DJANGO_SECRET_KEY` already uses — never defaulting silently in
    production. Add a `"vault-reveal"` entry to
    `REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]` at a rate tighter than the
    blanket `user` scope (exact rate is an implementation-time judgment
    call, not an architectural one).

#### 11. `backend/config/urls.py` (Modify)

*   **Type / Scope**: URL routing.
*   **Proposed Changes**: Import `VaultEntryViewSet` from `vault.views`;
    register `router.register("vault-entries", VaultEntryViewSet,
    basename="vault-entry")`, following the same direct-router-registration
    convention Task Tracking used (not a separate `vault/urls.py`).

#### 12. `backend/core/models.py` (Modify)

*   **Type / Scope**: Shared `AuditLog` model.
*   **Proposed Changes**: Add `VAULT_ENTRY_REVEALED_BY_ADMIN =
    "VAULT_ENTRY_REVEALED_BY_ADMIN", "Vault entry revealed by admin"` to
    `AuditLog.Action`. This is the first `Action` value ever logged for an
    *admin's own read* rather than an admin's write/correction of something
    else — worth flagging explicitly in review, per the brainstorm brief's
    own note that this is a precedent extension, not a drop-in reuse.

#### 13. `backend/requirements.txt` (Modify)

*   **Type / Scope**: Python dependencies.
*   **Proposed Changes**: Add a pinned `cryptography` entry (exact version
    range to be confirmed against `backend/Dockerfile`'s base image per the
    open packaging question).

#### 14. `backend/Dockerfile` (Modify, if needed)

*   **Type / Scope**: Container build.
*   **Proposed Changes**: Confirm the base image can build/install
    `cryptography`'s compiled extension (it already builds `psycopg2-binary`
    and `argon2-cffi`, both of which have native extensions, so this is
    likely a non-change, but must be verified rather than assumed — see
    Open Questions).

#### 15. `backend/.env.example` (Modify)

*   **Type / Scope**: Example environment file.
*   **Proposed Changes**: Add a `VAULT_ENCRYPTION_KEY=` line with a comment
    explaining it must be a Fernet-compatible key and must never be
    regenerated against a database that already has encrypted entries.

#### 16. `backend/tests/factories.py` (Modify)

*   **Type / Scope**: Factory Boy test factories.
*   **Proposed Changes**: Add `VaultEntryFactory` (encrypts a default
    plaintext password via `crypto.encrypt_secret()` in a `post_generation`
    hook, mirroring `TaskFactory`'s `assignees=[...]` hook) and
    `VaultEntryGrantFactory`.

#### 17. `backend/tests/test_vault.py` (Create)

*   **Type / Scope**: Pytest test suite, mirroring `test_tasks.py`'s
    structure and the same `TestEmployeeIsolation` exit-criterion pattern.
*   **Proposed Changes**: Test classes covering: `crypto.py` round-trip
    (encrypt then decrypt returns the original string); data isolation
    (unauthenticated → 403; uninvolved employee → 404; owner, grantee, and
    admin can all see; list excludes others' entries); the `reveal` action
    (owner/grantee reveal is never audit-logged; admin reveal of a
    non-shared entry is audit-logged and shows up via `last_admin_reveal`;
    the `vault-reveal` throttle actually limits repeated calls); `share`
    and `revoke_grant` (owner can share/revoke any grantee; a grantee can
    revoke only themselves; the response reflects the new state
    immediately, the same prefetch-cache-staleness regression test pattern
    Task Tracking added); one-level permission checks (grantee cannot edit
    or delete; grantee cannot re-share).

### Frontend

#### 18. `frontend/src/api/client.js` (Modify)

*   **Type / Scope**: API client.
*   **Proposed Changes**: Add `listVaultEntries`, `getVaultEntry`,
    `createVaultEntry`, `updateVaultEntry`, `deleteVaultEntry`,
    `revealVaultEntry`, `shareVaultEntry`, `revokeVaultEntryGrant` —
    following the exact calling convention of the existing `api.listTasks`
    etc. group. Reuses the existing `listAssignableEmployees` call (no
    change needed there — it's generic to "any employee," not Task-specific
    despite living under `/api/tasks/`).

#### 19. `frontend/src/views/VaultView.vue` (Create)

*   **Type / Scope**: Vue view — list + create.
*   **Proposed Changes**: List of the current user's visible entries
    (title, username, URL, a masked password placeholder, and a "shared
    with N people" indicator), a create form (title, username, password,
    optional URL/notes). Mirrors `TasksView.vue`'s structure. Never fetches
    or displays a decrypted password on this screen — only the detail view
    does, and only after an explicit reveal click.

#### 20. `frontend/src/views/VaultEntryDetailView.vue` (Create)

*   **Type / Scope**: Vue view — detail/edit/reveal/share.
*   **Proposed Changes**: Edit form for title/username/URL/notes
    (owner-only); a password field that starts masked and only calls
    `api.revealVaultEntry()` on an explicit "Reveal" click (never
    auto-fetched on page load, to avoid an unnecessary audit-logged admin
    reveal every time an admin merely opens the page); the `visible_to`
    disclosure line rendered verbatim from the API response; the
    `last_admin_reveal` notice when present; share form (reusing the same
    assignable-employees picker pattern as `TaskDetailView.vue`); a revoke
    button per grantee, with confirmation copy stating plainly that revoke
    does not undo anything the grantee already saw (per the brainstorm
    brief's UI-copy recommendation).

#### 21. `frontend/src/router/index.js` (Modify)

*   **Type / Scope**: Vue Router.
*   **Proposed Changes**: Add `/vault` and `/vault/:id` routes, available
    to both roles, mirroring the `/tasks` and `/tasks/:id` entries.

#### 22. `frontend/src/App.vue` (Modify)

*   **Type / Scope**: Navigation shell.
*   **Proposed Changes**: Add a "Credentials" (or similar — see the Goals
    section's naming decision) nav entry to both the admin and employee
    link arrays, following the existing `icon: "..."` convention.

#### 23. `frontend/src/components/NavIcon.vue` (Modify)

*   **Type / Scope**: Icon set.
*   **Proposed Changes**: Add a new icon (e.g. a key or lock glyph) matching
    the existing SVG style, for the new nav entry.

### Verification Plan

*   **Compilation/Build**: `backend`: `./.venv/Scripts/python.exe
    manage.py check`; `frontend`: `npm run build`.
*   **Unit Tests**: `backend`: `pytest backend/tests/test_vault.py` (and the
    full suite, to confirm no regression elsewhere) via the project's usual
    `DJANGO_SECRET_KEY=... DJANGO_DEBUG=true ...
    ./.venv/Scripts/python.exe -m pytest -q` invocation, with
    `VAULT_ENCRYPTION_KEY` also set.
*   **Static Analysis & Linting**: `ruff check .` and `black --check .` for
    the backend; `npx eslint src/` for the frontend.
*   **Test Coverage Requirement**: Every new permission branch (owner,
    grantee, admin, uninvolved employee) and both reveal-logging paths
    (logged vs. not logged) must have at least one dedicated test — matched
    to how `test_tasks.py` covers every branch of
    `IsTaskParticipantOrAdmin`.
*   **E2E/Integration**: Live browser verification via the project's
    `preview_start` dev-server workflow — create an entry, share it with a
    second employee, reveal it as that employee, revoke it and confirm a
    404 on the next reveal attempt, and reveal a non-shared entry as an
    admin and confirm the owner's `last_admin_reveal` field updates — the
    same live-click-through discipline used for Task Tracking, which is
    what caught several of that feature's real bugs that unit tests alone
    missed.

--------------------------------------------------------------------------------

<!-- Provenance: Indicates initial structural drafting via EGM. -->

*Drafted with EGM*
