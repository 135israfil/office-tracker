package com.officemanagement.tracking.collector

import android.app.AppOpsManager
import android.content.Context
import android.content.Intent
import android.os.Process
import android.provider.Settings

/** Usage Access (`PACKAGE_USAGE_STATS`) is a special app-op permission with no runtime
 * dialog — Android only lets a user grant it from Settings, never from an in-app
 * prompt, so this is a status check plus a deep link rather than a request call. */
object UsageAccess {

    @Suppress("DEPRECATION") // No non-deprecated replacement exists at minSdk 26; "unsafe"
    // refers to skipping a calling-UID trust check, which does not apply to checking our
    // own process's own op (Process.myUid()/context.packageName, both ours already).
    fun isGranted(context: Context): Boolean {
        val appOps = context.getSystemService(Context.APP_OPS_SERVICE) as AppOpsManager
        val mode = appOps.unsafeCheckOpNoThrow(
            AppOpsManager.OPSTR_GET_USAGE_STATS,
            Process.myUid(),
            context.packageName,
        )
        return mode == AppOpsManager.MODE_ALLOWED
    }

    /** The one way to grant this permission — Settings > Apps > Special app access >
     * Usage access, landing directly on the right screen rather than the top of
     * Settings. */
    fun settingsIntent(): Intent = Intent(Settings.ACTION_USAGE_ACCESS_SETTINGS)
}
