package com.officemanagement

import android.app.Application
import androidx.hilt.work.HiltWorkerFactory
import androidx.work.Configuration
import dagger.hilt.android.HiltAndroidApp
import javax.inject.Inject

@HiltAndroidApp
class OfficeManagementApp : Application(), Configuration.Provider {

    // Lets WorkManager construct CollectorWorker/SyncWorker through Hilt (they take
    // injected dependencies in their constructors, not a no-arg one WorkManager's
    // default factory could call) — paired with AndroidManifest.xml removing the
    // library's own auto-initializer, which would otherwise build workers the plain
    // way and crash the moment one of these ran.
    @Inject lateinit var workerFactory: HiltWorkerFactory

    override val workManagerConfiguration: Configuration
        get() = Configuration.Builder().setWorkerFactory(workerFactory).build()
}
