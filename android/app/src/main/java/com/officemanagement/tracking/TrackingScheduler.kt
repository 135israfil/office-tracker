package com.officemanagement.tracking

import android.content.Context
import androidx.work.BackoffPolicy
import androidx.work.Constraints
import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.NetworkType
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.WorkRequest
import com.officemanagement.tracking.collector.CollectorWorker
import com.officemanagement.tracking.sync.SyncWorker
import java.util.concurrent.TimeUnit
import javax.inject.Inject
import javax.inject.Singleton

/** Enqueues the two periodic tracking jobs. Called once onboarding completes (see
 * tracking/onboarding/TrackingOnboardingViewModel.kt) and again at every app start (see
 * MainActivity) so the jobs survive a device reboot without needing a
 * RECEIVE_BOOT_COMPLETED receiver of this app's own — WorkManager's bundled one already
 * re-enqueues anything that was persisted, but only after something in the app process
 * asks it to again at least once; `KEEP` makes repeating that call on every launch a
 * no-op rather than a reset. */
@Singleton
class TrackingScheduler @Inject constructor(@dagger.hilt.android.qualifiers.ApplicationContext private val context: Context) {

    fun ensureScheduled() {
        val workManager = WorkManager.getInstance(context)

        // 15 minutes is WorkManager's own floor for periodic work (plan §8.2) — not a
        // choice made here, just the platform's minimum.
        val collectorRequest = PeriodicWorkRequestBuilder<CollectorWorker>(15, TimeUnit.MINUTES)
            .setBackoffCriteria(BackoffPolicy.LINEAR, WorkRequest.MIN_BACKOFF_MILLIS, TimeUnit.MILLISECONDS)
            .build()
        workManager.enqueueUniquePeriodicWork(
            CollectorWorker.UNIQUE_WORK_NAME,
            ExistingPeriodicWorkPolicy.KEEP,
            collectorRequest,
        )

        val syncRequest = PeriodicWorkRequestBuilder<SyncWorker>(15, TimeUnit.MINUTES)
            .setConstraints(Constraints.Builder().setRequiredNetworkType(NetworkType.CONNECTED).build())
            .setBackoffCriteria(BackoffPolicy.EXPONENTIAL, WorkRequest.MIN_BACKOFF_MILLIS, TimeUnit.MILLISECONDS)
            .build()
        workManager.enqueueUniquePeriodicWork(
            SyncWorker.UNIQUE_WORK_NAME,
            ExistingPeriodicWorkPolicy.KEEP,
            syncRequest,
        )
    }

    /** Called on logout: a token that is gone should stop everything that depends on
     * it, the same "logged out and tracking paused are the same state" guarantee
     * AuthInterceptor's own docstring describes. */
    fun cancel() {
        val workManager = WorkManager.getInstance(context)
        workManager.cancelUniqueWork(CollectorWorker.UNIQUE_WORK_NAME)
        workManager.cancelUniqueWork(SyncWorker.UNIQUE_WORK_NAME)
    }
}
