package com.officemanagement.tracking.sync

import android.content.Context
import android.util.Log
import androidx.hilt.work.HiltWorker
import androidx.work.CoroutineWorker
import androidx.work.WorkerParameters
import com.officemanagement.core.network.ApiService
import com.officemanagement.core.network.MobileSessionPayload
import com.officemanagement.core.network.MobileSyncRequest
import com.officemanagement.tracking.storage.TrackingQueueRepository
import dagger.assisted.Assisted
import dagger.assisted.AssistedInject

private const val TAG = "SyncWorker"

/** Periodic job that drains the local queue to the server — the mobile analogue of
 * desktop-agent/agent/sync/client.py's SyncService, with one simplification: instead of
 * SyncService's own hand-rolled exponential backoff, this returns [Result.retry] and
 * lets WorkManager's own backoff policy (set where the work is enqueued, see
 * TrackingScheduler.kt) handle it — the platform's native retry mechanism for exactly
 * this job shape, so there is no reason to re-implement one.
 *
 * Same two behaviours as the desktop original:
 * - A dropped response means the batch is sent again. Safe by construction: ingestion
 *   upserts on `client_event_id`, so the server counts the replay as a duplicate.
 * - A session the server calls invalid is dropped locally, or one malformed row would
 *   sit at the head of the queue forever, retried every cycle.
 */
@HiltWorker
class SyncWorker @AssistedInject constructor(
    @Assisted context: Context,
    @Assisted params: WorkerParameters,
    private val api: ApiService,
    private val queueRepository: TrackingQueueRepository,
) : CoroutineWorker(context, params) {

    override suspend fun doWork(): Result {
        var batchFailed = false
        for (attempt in 0 until MAX_BATCHES_PER_RUN) {
            val batch = queueRepository.pending(BATCH_SIZE)
            if (batch.isEmpty()) break

            val rowIds = batch.map { it.rowId }
            val request = MobileSyncRequest(
                sessions = batch.map { pending ->
                    MobileSessionPayload(
                        clientEventId = pending.session.clientEventId,
                        activityType = pending.session.activityType,
                        applicationName = pending.session.applicationName,
                        executableName = pending.session.executableName,
                        websiteDomain = pending.session.websiteDomain,
                        startTime = pending.session.startTime,
                        endTime = pending.session.endTime,
                    )
                },
            )

            val response = try {
                api.mobileSync(request)
            } catch (exc: Exception) {
                Log.w(TAG, "Sync of ${batch.size} session(s) failed", exc)
                queueRepository.recordAttempt(rowIds)
                batchFailed = true
                break
            }

            // 2xx: everything in this batch is now the server's problem, including
            // the rows it counted as duplicates — those are already stored from an
            // earlier attempt.
            queueRepository.markSynced(rowIds)

            if (response.rejected.isNotEmpty()) {
                val rejectedIds = response.rejected.map { it.clientEventId }.toSet()
                val discarded = batch
                    .filter { it.session.clientEventId in rejectedIds }
                    .map { it.rowId }
                queueRepository.discard(discarded)
                Log.e(TAG, "Server rejected ${response.rejected.size} session(s); dropped locally")
            }
        }

        queueRepository.purgeSynced()
        return if (batchFailed) Result.retry() else Result.success()
    }

    companion object {
        const val UNIQUE_WORK_NAME = "tracking-sync"

        // Matches desktop-agent/agent/sync/client.py's BATCH_SIZE: big enough that a
        // long outage drains quickly, small enough to retry cheaply and stay well
        // inside the server's 500-row batch limit.
        private const val BATCH_SIZE = 100

        // Matches desktop-agent SyncService.drain()'s own cap, same reasoning: a
        // phone returning from a long outage must not monopolise this one run.
        private const val MAX_BATCHES_PER_RUN = 20
    }
}
