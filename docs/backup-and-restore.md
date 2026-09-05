# Backup and restore

A backup nobody has restored is a hypothesis. §5 below is the part that matters; the rest
is setup.

---

## 1. What has to be backed up

| Item | Where | If you lose it |
|---|---|---|
| **Database** | PostgreSQL | Everything: employees, attendance, leave, activity, audit log |
| **`.env`** | `/etc/office-management/.env` | The secret key. Every existing session cookie becomes invalid; the database is intact but nobody stays logged in |
| Application code | Git | Nothing, if it is pushed |
| Frontend build | `frontend/dist` | Nothing — rebuild it |

Two items, not one. The `.env` is small enough to be forgotten and cannot be regenerated:
`DJANGO_SECRET_KEY` is not derivable from anything else, and a new one invalidates every
session in the system. Back it up **separately from the database**, encrypted, somewhere
a database dump would not also be — a backup set where one stolen archive contains both
the data and the key that protects its sessions has not achieved much.

What is **not** in the database: the agents' local queues, which live on each PC. They are
a transient buffer of unsent sessions, not a system of record, and are deliberately not
backed up.

---

## 2. Taking a backup

### Docker

```bash
docker compose exec -T db pg_dump -U postgres -Fc office_management \
    > "backup-$(date +%F-%H%M).dump"
```

### Direct PostgreSQL

```bash
PGPASSWORD="$POSTGRES_PASSWORD" pg_dump \
    -h "$POSTGRES_HOST" -U "$POSTGRES_USER" -Fc "$POSTGRES_DB" \
    > "backup-$(date +%F-%H%M).dump"
```

`-Fc` (custom format) rather than plain SQL: it compresses, and it restores with
`pg_restore`, which can do a single table or a schema-only run when something has gone
wrong in a specific way.

### Nightly, with rotation

```bash
#!/usr/bin/env bash
# /usr/local/bin/office-backup.sh
set -euo pipefail

BACKUP_DIR=/var/backups/office-management
KEEP_DAYS=30
STAMP=$(date +%F-%H%M)

mkdir -p "$BACKUP_DIR"
set -a; . /etc/office-management/.env; set +a

PGPASSWORD="$POSTGRES_PASSWORD" pg_dump \
    -h "$POSTGRES_HOST" -U "$POSTGRES_USER" -Fc "$POSTGRES_DB" \
    > "$BACKUP_DIR/db-$STAMP.dump.part"

# Rename only after pg_dump exits 0, so a dump interrupted halfway is never mistaken
# for a complete one — which is how a directory full of backups turns out to contain
# nothing usable.
mv "$BACKUP_DIR/db-$STAMP.dump.part" "$BACKUP_DIR/db-$STAMP.dump"

find "$BACKUP_DIR" -name 'db-*.dump' -mtime +$KEEP_DAYS -delete
find "$BACKUP_DIR" -name '*.part' -mtime +1 -delete

echo "$(date -Is) backup ok: $(du -h "$BACKUP_DIR/db-$STAMP.dump" | cut -f1)"
```

```cron
15 1 * * * /usr/local/bin/office-backup.sh >> /var/log/office-backup.log 2>&1
```

**Copy the dumps off the host.** A backup on the same disk as the database survives a
mistaken `DELETE` and nothing else.

### Retention and the deletion promise

Employees are told PC activity is deleted after the configured window (default 90 days).
Backups older than that window still contain it. Either keep backup retention at or below
the activity window, or say so in the notice. Keeping a year of dumps while telling people
data is deleted after ninety days is a promise the system does not keep.

Attendance and leave are employment records and are not covered by that window.

---

## 3. Verifying a backup exists and is readable

Listing a dump's contents does not touch the running system and catches a truncated file:

```bash
pg_restore --list backup-2026-08-19-0115.dump | head
```

Silence or an error here means the dump is not usable. That is worth knowing on a
Tuesday rather than during an outage.

---

## 4. Restoring

> Restoring replaces data. Take a fresh dump of the current state first, even if you
> believe it is worthless — it is the only way back if the restore is the mistake.

### Full restore, over an existing database

```bash
systemctl stop office-management        # nothing should be writing during a restore

set -a; . /etc/office-management/.env; set +a

PGPASSWORD="$POSTGRES_PASSWORD" pg_restore \
    -h "$POSTGRES_HOST" -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
    --clean --if-exists --no-owner --no-privileges \
    backup-2026-08-19-0115.dump

cd /srv/office-management/backend
.venv/bin/python manage.py migrate      # in case the code is newer than the dump
systemctl start office-management
```

### Into a fresh database

```bash
createdb -h "$POSTGRES_HOST" -U "$POSTGRES_USER" office_management_restored
PGPASSWORD="$POSTGRES_PASSWORD" pg_restore \
    -h "$POSTGRES_HOST" -U "$POSTGRES_USER" -d office_management_restored \
    --no-owner --no-privileges backup-2026-08-19-0115.dump
```

This is the right shape for a restore *drill*, and for answering "what did this look like
last month" without touching production.

### Docker

```bash
docker compose stop backend
docker compose exec -T db pg_restore -U postgres -d office_management \
    --clean --if-exists --no-owner < backup-2026-08-19-0115.dump
docker compose start backend
```

### After any restore

```bash
curl -sS https://office.example.com/api/health/
```

- Sign in. If nobody can, the `.env` is not the one that goes with this data — the secret
  key differs, and every session cookie is invalid. Restore the matching `.env`.
- Spot-check a recent attendance day against what people remember.
- Agents recover on their own: they queue locally and resend anything the server did not
  confirm, so activity from the gap arrives without intervention. Duplicates are harmless
  because ingestion upserts on `client_event_id`.
- Expect a burst of agent traffic in the first minutes as queues drain.

---

## 5. The restore drill

**Do this before go-live, and every quarter.** It is the only step on this page that
proves anything.

1. Take last night's dump — the real one, not a fresh one made for the occasion.
2. Restore it into a scratch database (§4, "into a fresh database").
3. Point a *non-production* backend at it:
   ```bash
   POSTGRES_DB=office_management_restored .venv/bin/python manage.py runserver 8001
   ```
4. Check, and write down what you found:
   - [ ] `/api/health/` returns 200
   - [ ] An admin can sign in
   - [ ] Employee count matches production
   - [ ] Yesterday's attendance is present and correct
   - [ ] The audit log has entries from yesterday
   - [ ] Activity exists for a machine you know was on
5. Note **how long the restore took**. That number is the recovery time you actually
   have, as opposed to the one anybody would have guessed.
6. Drop the scratch database.

Record the date and the outcome. A drill that was never written down did not happen.

### Drill log

| Date | Dump | Restore time | Result |
|---|---|---|---|
| 2026-08-19 | 76 KB, 20 tables (seeded pre-release data) | ~3 s | Pass — row counts matched the source exactly (3 employees, 3 attendance, 11 activity, 7 audit), and a backend pointed at the restored database read them correctly |

That timing is from a near-empty database and says nothing about a year of production
data. Re-measure at the first quarterly drill, once the tables have real volume in them;
that number is the one to plan around.

---

## 6. If things have gone wrong in a specific way

**One table damaged, the rest fine.** `pg_restore -t attendance_attendance` into a scratch
database, inspect, then move the rows across. Restoring the whole dump to fix one table
throws away everything written since.

**An accidental mass delete, noticed quickly.** The audit log records admin mutations —
`AuditLog` in the Django admin, filtered by actor and time — so start by establishing what
was actually run and by whom. Retention deletions are logged as `ACTIVITY_PURGED` with the
cutoff and the row count, so it is possible to tell a misconfigured retention window from
something else entirely.

**Only the `.env` is lost.** The data is fine. Generate a new secret key, restart, and
tell everyone they need to sign in again. Nothing else is affected: passwords are hashed
with a per-password salt, not encrypted with the secret key.

**Only the database is lost.** Restore the most recent dump. Everything since the dump is
gone except PC activity, which the agents will resend from their local queues.
