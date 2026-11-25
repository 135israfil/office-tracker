package com.officemanagement.tracking.collector

import android.content.Context
import androidx.hilt.work.HiltWorker
import androidx.work.CoroutineWorker
import androidx.work.WorkerParameters
import com.officemanagement.BuildConfig
import com.officemanagement.core.network.ApiService
import com.officemanagement.core.network.MobileDeviceRequest
import com.officemanagement.tracking.TrackingPrefs
import com.officemanagement.tracking.sessions.SessionBuilder
import com.officemanagement.tracking.storage.TrackingQueueRepository
import dagger.assisted.Assisted
import dagger.assisted.AssistedInject
import java.time.Instant

/** Periodic job (WorkManager's own 15-minute floor) that turns the UsageEvents history
 * since the last checkpoint into closed sessions and queues them for upload, and
 * carries this run's own heartbeat — there is no separate, more-frequent heartbeat
 * worker, since 15 minutes is already the shortest cadence WorkManager allows, so the
 * job that already runs on it is where the heartbeat rides along rather than a second
 * job duplicating the same schedule. Without this call the phone's Computer row would
 * stay OFFLINE forever: nothing else ever tells the server this device is alive.
 *
 * A fresh [SessionBuilder] is built for every run rather than one persisted across
 * invocations: WorkManager creates a new Worker instance each time it fires, so there is
 * no in-memory state to carry over anyway, and feeding one run's whole event history
 * through a builder that is then flushed at the end produces the same closed sessions a
 * persisted builder would — each run is a complete, self-contained batch. See
 * tracking/sessions/SessionBuilder.kt's own docstring for why this is still correct.
 */
@HiltWorker
class CollectorWorker @AssistedInject constructor(
    @Assisted context: Context,
    @Assisted params: WorkerParameters,
    private val usageEventReader: UsageEventReader,
    private val trackingPrefs: TrackingPrefs,
    private val queueRepository: TrackingQueueRepository,
    private val api: ApiService,
) : CoroutineWorker(context, params) {

    override suspend fun doWork(): Result {
        try {
            api.mobileHeartbeat(MobileDeviceRequest(agentVersion = BuildConfig.VERSION_NAME))
        } catch (_: Exception) {
            // A missed heartbeat is not fatal to this run: the collector still has work
            // to do locally, and the next run tries again — the same "liveness and
            // collection are independent" principle service.py's module docstring
            // describes for the desktop agent's own loops.
        }

        if (!UsageAccess.isGranted(applicationContext)) {
            // Not an error: the user has not (or not yet) granted Usage Access from
            // Settings. Retrying on the same schedule costs nothing and picks up the
            // moment they do.
            return Result.success()
        }

        val now = Instant.now()
        val nowMillis = now.toEpochMilli()
        // First run ever: start from one interval ago rather than querying the
        // device's entire usage history, which could be months of events on an
        // existing phone.
        val since = trackingPrefs.lastCheckpointMillis ?: (nowMillis - DEFAULT_LOOKBACK_MILLIS)

        val samples = usageEventReader.readSince(since, nowMillis)
        val builder = SessionBuilder()
        val closed = mutableListOf<com.officemanagement.tracking.sessions.ClosedSession>()
        for (sample in samples) {
            closed += builder.observe(sample)
        }
        closed += builder.flush(now)

        for (session in closed) {
            queueRepository.enqueue(session, now)
        }

        trackingPrefs.lastCheckpointMillis = nowMillis
        return Result.success()
    }

    companion object {
        const val UNIQUE_WORK_NAME = "tracking-collector"
        private const val DEFAULT_LOOKBACK_MILLIS = 15 * 60 * 1000L
    }
}
