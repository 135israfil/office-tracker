package com.officemanagement.tracking.onboarding

import android.content.Context
import android.os.Build
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.officemanagement.BuildConfig
import com.officemanagement.core.network.ApiService
import com.officemanagement.core.network.MobileDeviceRequest
import com.officemanagement.tracking.TrackingPrefs
import com.officemanagement.tracking.TrackingScheduler
import com.officemanagement.tracking.collector.UsageAccess
import dagger.hilt.android.lifecycle.HiltViewModel
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.coroutines.launch
import javax.inject.Inject

data class TrackingOnboardingUiState(
    val usageAccessGranted: Boolean = false,
    val isSubmitting: Boolean = false,
    val error: String? = null,
    val done: Boolean = false,
)

@HiltViewModel
class TrackingOnboardingViewModel @Inject constructor(
    @ApplicationContext private val context: Context,
    private val api: ApiService,
    private val prefs: TrackingPrefs,
    private val scheduler: TrackingScheduler,
) : ViewModel() {

    var uiState by mutableStateOf(TrackingOnboardingUiState(usageAccessGranted = UsageAccess.isGranted(context)))
        private set

    /** Called whenever the screen resumes (including returning from the Settings deep
     * link) — there is no callback for a Settings-granted permission, only a status to
     * re-check. */
    fun refreshPermissionStatus() {
        uiState = uiState.copy(usageAccessGranted = UsageAccess.isGranted(context))
    }

    /** Registers this phone and starts the two periodic jobs. Usage Access does not
     * need to be granted first — the collector worker already checks it on every run
     * (see CollectorWorker) and simply produces nothing until it is, so someone who
     * enables it a day later is picked up without reinstalling anything. */
    fun completeOnboarding() {
        uiState = uiState.copy(isSubmitting = true, error = null)
        viewModelScope.launch {
            try {
                api.registerMobileDevice(
                    MobileDeviceRequest(
                        computerName = "${Build.MANUFACTURER} ${Build.MODEL}".trim(),
                        operatingSystem = "Android ${Build.VERSION.RELEASE}",
                        agentVersion = BuildConfig.VERSION_NAME,
                    ),
                )
                scheduler.ensureScheduled()
                prefs.onboardingCompleted = true
                uiState = uiState.copy(isSubmitting = false, done = true)
            } catch (exc: Exception) {
                uiState = uiState.copy(isSubmitting = false, error = exc.message ?: "Could not register this phone.")
            }
        }
    }

    /** "Not now": tracking is an add-on to the rest of the app, not a gate in front of
     * it — a phone whose owner declines still gets Tasks/Vault/Events/etc. normally,
     * it just is not tracked. Not shown again this install. */
    fun skip() {
        prefs.onboardingCompleted = true
        uiState = uiState.copy(done = true)
    }
}
