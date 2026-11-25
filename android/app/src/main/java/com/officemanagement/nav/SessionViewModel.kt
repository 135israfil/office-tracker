package com.officemanagement.nav

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.officemanagement.auth.AuthRepository
import com.officemanagement.core.network.CurrentUser
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch
import javax.inject.Inject

/** Held at the nav graph's root (not per-screen) so every screen sees the same auth
 * state without each one re-fetching it — the thing AppNavGraph itself watches to
 * decide whether to show Login or a role-gated home screen. */
@HiltViewModel
class SessionViewModel @Inject constructor(private val authRepository: AuthRepository) : ViewModel() {

    val token: StateFlow<String?> = authRepository.token
    val currentUser: StateFlow<CurrentUser?> = authRepository.currentUser

    init {
        // A saved token from a previous run says "logged in" but not "as whom" —
        // this is what answers that before the nav graph picks Dashboard vs MyDashboard.
        viewModelScope.launch { authRepository.refreshCurrentUser() }
    }

    fun logout() {
        viewModelScope.launch { authRepository.logout() }
    }
}
