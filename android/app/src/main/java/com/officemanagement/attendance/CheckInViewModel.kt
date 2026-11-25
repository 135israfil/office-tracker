package com.officemanagement.attendance

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.officemanagement.core.network.ApiService
import com.officemanagement.core.network.MyTodayResponse
import com.officemanagement.core.network.PunchLocationRequest
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.launch
import javax.inject.Inject

data class CheckInUiState(
    val isLoading: Boolean = true,
    val today: MyTodayResponse? = null,
    val isSubmitting: Boolean = false,
    val error: String? = null,
)

/** §6-§9's employee attendance kiosk. Poor-accuracy GPS is flagged, not blocked — the
 * same "flag, don't block" rule the web app's own check-in page follows — this screen
 * just sends whatever fix it got and lets the backend's own distance/accuracy checks
 * decide needs_review, same as CheckInView.vue does. */
@HiltViewModel
class CheckInViewModel @Inject constructor(
    private val api: ApiService,
    private val locationProvider: LocationProvider,
) : ViewModel() {

    var uiState by mutableStateOf(CheckInUiState())
        private set

    init {
        load()
    }

    fun load() {
        uiState = uiState.copy(isLoading = true, error = null)
        viewModelScope.launch {
            uiState = try {
                uiState.copy(isLoading = false, today = api.attendanceToday())
            } catch (e: Exception) {
                uiState.copy(isLoading = false, error = e.message ?: "Could not load attendance.")
            }
        }
    }

    fun checkIn() = punch { request -> api.checkIn(request) }

    fun checkOut() = punch { request -> api.checkOut(request) }

    private fun punch(call: suspend (PunchLocationRequest) -> Unit) {
        uiState = uiState.copy(isSubmitting = true, error = null)
        viewModelScope.launch {
            val location = locationProvider.currentLocation()
            if (location == null) {
                uiState = uiState.copy(
                    isSubmitting = false,
                    error = "Could not get your location. Check location permission and try again.",
                )
                return@launch
            }
            try {
                call(PunchLocationRequest(location.latitude, location.longitude, location.accuracy))
                load()
            } catch (e: Exception) {
                uiState = uiState.copy(isSubmitting = false, error = e.message ?: "That didn't go through.")
            }
        }
    }
}
