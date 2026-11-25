package com.officemanagement.tracking.collector

import android.app.usage.UsageEvents
import android.app.usage.UsageStatsManager
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.util.Log
import com.officemanagement.tracking.sessions.Sample
import java.time.Instant
import javax.inject.Inject
import javax.inject.Singleton

private const val TAG = "UsageEventReader"

/** Reads foreground-app transitions out of `UsageStatsManager` and turns them into
 * [Sample]s — the mobile analogue of desktop-agent's `collectors/application.py`.
 *
 * Unlike the desktop collector, which polls a live foreground window every couple of
 * seconds, this reads a *history* of MOVE_TO_FOREGROUND events since the last
 * checkpoint in one batch (see tracking/collector/CollectorWorker.kt) — each event
 * already carries its own real timestamp, so feeding them through SessionBuilder in
 * order produces the same kind of closed intervals either way.
 *
 * There is no idle signal on this platform (see Sample's own docstring): every Sample
 * here is ONLINE, and a phone nobody touched simply produced no MOVE_TO_FOREGROUND
 * events in the window, which the builder's gap rule already treats as unobserved
 * time.
 */
@Singleton
class UsageEventReader @Inject constructor(@dagger.hilt.android.qualifiers.ApplicationContext private val context: Context) {

    // Friendly-name lookups hit PackageManager, which is not free; a foreground app
    // seen repeatedly across many events in the same batch should not pay for it twice.
    private val nameCache = mutableMapOf<String, String>()

    /** Foreground-app samples between [sinceMillis] and [untilMillis], oldest first. */
    @Suppress("DEPRECATION") // MOVE_TO_FOREGROUND's replacement (ACTIVITY_RESUMED) needs
    // API 29; this needs to keep working down to minSdk 26.
    fun readSince(sinceMillis: Long, untilMillis: Long): List<Sample> {
        val manager = context.getSystemService(Context.USAGE_STATS_SERVICE) as? UsageStatsManager
            ?: return emptyList()

        val events = try {
            manager.queryEvents(sinceMillis, untilMillis)
        } catch (exc: Exception) {
            // A failure here must never take the collector worker down with it — the
            // same "return the honest empty answer" convention idle.py's
            // GetLastInputInfo failure uses on desktop.
            Log.w(TAG, "queryEvents failed", exc)
            return emptyList()
        }

        val samples = mutableListOf<Sample>()
        val event = UsageEvents.Event()
        while (events.hasNextEvent()) {
            events.getNextEvent(event)
            if (event.eventType != UsageEvents.Event.MOVE_TO_FOREGROUND) continue
            val packageName = event.packageName ?: continue
            if (isLauncherOrSystemUi(packageName)) continue

            samples += Sample(
                at = Instant.ofEpochMilli(event.timeStamp),
                applicationName = friendlyName(packageName),
                executableName = packageName,
            )
        }
        return samples
    }

    private fun friendlyName(packageName: String): String =
        nameCache.getOrPut(packageName) {
            try {
                val pm = context.packageManager
                val info = pm.getApplicationInfo(packageName, 0)
                pm.getApplicationLabel(info).toString()
            } catch (_: PackageManager.NameNotFoundException) {
                // Plenty of short-lived system packages never show up in a launcher at
                // all; the bare package name is the best name available.
                packageName
            }
        }

    /** The home launcher and system UI own the desktop and task switcher, not
     * something anyone "used" — recording them turns every Home-button press and
     * notification-shade pull into a session, the same reason
     * desktop-agent/collectors/application.py excludes explorer.exe et al. The
     * launcher's package name is resolved rather than hardcoded, since it varies by
     * device and launcher app. */
    private fun isLauncherOrSystemUi(packageName: String): Boolean {
        if (packageName in SYSTEM_UI_PACKAGES) return true
        return packageName == defaultLauncherPackage()
    }

    private var cachedLauncherPackage: String? = null
    private fun defaultLauncherPackage(): String? {
        cachedLauncherPackage?.let { return it }
        val intent = Intent(Intent.ACTION_MAIN).addCategory(Intent.CATEGORY_HOME)
        val resolved = context.packageManager.resolveActivity(intent, 0)?.activityInfo?.packageName
        cachedLauncherPackage = resolved
        return resolved
    }

    private companion object {
        val SYSTEM_UI_PACKAGES = setOf("com.android.systemui")
    }
}
