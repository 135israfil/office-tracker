package com.officemanagement.nav

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.officemanagement.auth.AuthRepository
import com.officemanagement.core.network.CurrentUser
import com.officemanagement.tracking.TrackingPrefs
import com.officemanagement.tracking.TrackingScheduler
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch
import javax.inject.Inject

/** Held at the nav graph's root (not per-screen) so every screen sees the same auth
 * state without each one re-fetching it — the thing AppNavGraph itself watches to
 * decide whether to show Login or a role-gated home screen. */
@HiltViewModel
class SessionViewModel @Inject constructor(
    private val authRepository: AuthRepository,
    private val trackingPrefs: TrackingPrefs,
    private val trackingScheduler: TrackingScheduler,
) : ViewModel() {

    val token: StateFlow<String?> = authRepository.token
    val currentUser: StateFlow<CurrentUser?> = authRepository.currentUser

    init {
        // A saved token from a previous run says "logged in" but not "as whom" —
        // this is what answers that before the nav graph picks Dashboard vs MyDashboard.
        viewModelScope.launch { authRepository.refreshCurrentUser() }
        // Re-asserts the periodic jobs at every app start (see TrackingScheduler's own
        // docstring on why) — a no-op via ExistingPeriodicWorkPolicy.KEEP for a phone
        // that already went through onboarding, and nothing at all for one that hasn't.
        if (trackingPrefs.onboardingCompleted) trackingScheduler.ensureScheduled()
    }

    /** Whether this phone still needs to see the tracking-onboarding screen — checked
     * once per redirect decision in AppNavGraph's LaunchedEffect, not observed
     * reactively: the onboarding screen's own onDone callback is what moves past it. */
    fun needsTrackingOnboarding(): Boolean = !trackingPrefs.onboardingCompleted

    fun logout() {
        viewModelScope.launch { authRepository.logout() }
        // A token that is gone must stop everything that depends on it — the same
        // "logged out and tracking paused are the same state" guarantee
        // AuthInterceptor's own docstring describes.
        trackingScheduler.cancel()
    }
}
