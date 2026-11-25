package com.officemanagement.tracking

import android.content.Context
import android.content.SharedPreferences
import dagger.hilt.android.qualifiers.ApplicationContext
import javax.inject.Inject
import javax.inject.Singleton

/** Small, non-secret tracking state — nothing here is a credential (that's TokenStore),
 * just bookkeeping for the collector and the one-time onboarding screen. Plain
 * SharedPreferences rather than DataStore: this is a couple of scalars, not a schema
 * worth a serializer for. */
@Singleton
class TrackingPrefs @Inject constructor(@ApplicationContext context: Context) {
    private val prefs: SharedPreferences = context.getSharedPreferences("tracking_prefs", Context.MODE_PRIVATE)

    /** Where the collector last stopped reading UsageEvents from. Null means "never
     * run yet" — the collector starts from (now - one interval) rather than querying
     * the device's entire usage history on first run. */
    var lastCheckpointMillis: Long?
        get() = prefs.getLong(KEY_CHECKPOINT, -1L).takeIf { it >= 0 }
        set(value) {
            if (value == null) prefs.edit().remove(KEY_CHECKPOINT).apply()
            else prefs.edit().putLong(KEY_CHECKPOINT, value).apply()
        }

    /** Set once the user has been through the tracking-onboarding screen (granted or
     * explicitly skipped Usage Access) — the app does not show it again. */
    var onboardingCompleted: Boolean
        get() = prefs.getBoolean(KEY_ONBOARDED, false)
        set(value) = prefs.edit().putBoolean(KEY_ONBOARDED, value).apply()

    private companion object {
        const val KEY_CHECKPOINT = "last_checkpoint_millis"
        const val KEY_ONBOARDED = "onboarding_completed"
    }
}
