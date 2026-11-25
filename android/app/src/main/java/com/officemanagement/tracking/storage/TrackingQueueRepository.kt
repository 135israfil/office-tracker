package com.officemanagement.tracking.storage

import com.officemanagement.tracking.sessions.ClosedSession
import java.time.Duration
import java.time.Instant
import javax.inject.Inject
import javax.inject.Singleton

/** One row carrying both the queue's own id (for mark/discard calls) and the closed
 * session itself, the same shape desktop-agent/agent/storage/queue.py's `pending()`
 * returns (a dict with `id` mixed into the session fields). */
data class PendingSession(val rowId: Long, val session: ClosedSession)

/** Policy wrapper around [TrackingSessionDao] — the Room port of
 * desktop-agent/agent/storage/queue.py's SessionQueue. The dedup-by-`client_event_id`,
 * cap-at-MAX_PENDING_ROWS, and grace-period-purge rules all match the desktop original;
 * only the storage engine differs (Room/SQLite here as there, but reached through the
 * platform's own ORM rather than hand-written SQL). */
@Singleton
class TrackingQueueRepository @Inject constructor(private val dao: TrackingSessionDao) {

    /** Stores one closed session. Returns false if the queue is full or the session was
     * already stored (the same `client_event_id` arriving twice, which the unique index
     * makes harmless rather than an error). */
    suspend fun enqueue(session: ClosedSession, now: Instant = Instant.now()): Boolean {
        if (dao.totalCount() >= MAX_PENDING_ROWS) {
            // An agent offline for months must not fill the phone's disk; the drop is
            // silent to the user by design (same as desktop) but not to logs.
            return false
        }
        val id = dao.insert(
            TrackingSessionEntity(
                clientEventId = session.clientEventId,
                activityType = session.activityType,
                applicationName = session.applicationName,
                executableName = session.executableName,
                websiteDomain = session.websiteDomain,
                startTime = session.startTime,
                endTime = session.endTime,
                createdAt = now.toEpochMilli(),
            ),
        )
        return id != -1L
    }

    suspend fun pending(limit: Int = 100): List<PendingSession> =
        dao.pending(limit).map { row ->
            PendingSession(
                rowId = row.id,
                session = ClosedSession(
                    clientEventId = row.clientEventId,
                    activityType = row.activityType,
                    applicationName = row.applicationName,
                    executableName = row.executableName,
                    websiteDomain = row.websiteDomain,
                    startTime = row.startTime,
                    endTime = row.endTime,
                    durationSeconds = Duration.between(Instant.parse(row.startTime), Instant.parse(row.endTime)).seconds,
                ),
            )
        }

    suspend fun pendingCount(): Int = dao.pendingCount()

    suspend fun markSynced(ids: List<Long>, now: Instant = Instant.now()) {
        if (ids.isEmpty()) return
        dao.markSynced(ids, now.toEpochMilli())
    }

    suspend fun recordAttempt(ids: List<Long>) {
        if (ids.isEmpty()) return
        dao.recordAttempt(ids)
    }

    /** Drops rows the server named as invalid — without this, one malformed row sits at
     * the head of the queue forever, retried every cycle and blocking everything behind
     * it. */
    suspend fun discard(ids: List<Long>) {
        if (ids.isEmpty()) return
        dao.discard(ids)
    }

    /** Deletes confirmed-uploaded rows older than [keepDays] — a short grace period for
     * people, not correctness: when someone asks why a day looks wrong, the last day of
     * uploads is still on the device. */
    suspend fun purgeSynced(keepDays: Long = 1): Int =
        dao.purgeSyncedBefore(Instant.now().minus(Duration.ofDays(keepDays)).toEpochMilli())

    suspend fun stats(): TrackingQueueStats {
        val row = dao.stats()
        return TrackingQueueStats(total = row.total, pending = row.pending ?: 0, maxAttempts = row.maxAttempts)
    }

    companion object {
        // Matches desktop-agent/agent/storage/queue.py's MAX_PENDING_ROWS exactly —
        // roughly three months of buffer at typical sampling rates.
        const val MAX_PENDING_ROWS = 50_000
    }
}
