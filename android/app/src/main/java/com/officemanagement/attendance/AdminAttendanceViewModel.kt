package com.officemanagement.attendance

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.officemanagement.core.network.ApiService
import com.officemanagement.core.network.AttendanceItem
import com.officemanagement.core.network.PunchCorrectionRequest
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.launch
import javax.inject.Inject

data class AdminAttendanceUiState(
    val isLoading: Boolean = true,
    val rows: List<AttendanceItem> = emptyList(),
    val error: String? = null,
)

/** §9's admin attendance log. Filters (department/status/date-range) are a later
 * phase — this lists the most recent 50 records, which is enough to reach "today's
 * needs-review rows," the thing a correction is actually for. */
@HiltViewModel
class AdminAttendanceViewModel @Inject constructor(private val api: ApiService) : ViewModel() {

    var uiState by mutableStateOf(AdminAttendanceUiState())
        private set

    init {
        load()
    }

    fun load() {
        uiState = uiState.copy(isLoading = true, error = null)
        viewModelScope.launch {
            uiState = try {
                AdminAttendanceUiState(isLoading = false, rows = api.adminAttendance(emptyMap()).results)
            } catch (e: Exception) {
                AdminAttendanceUiState(isLoading = false, error = e.message ?: "Could not load attendance.")
            }
        }
    }

    fun correctPunch(attendanceId: Int, punchId: Int, checkInAt: String?, checkOutAt: String?, note: String) {
        viewModelScope.launch {
            try {
                api.correctPunch(
                    attendanceId,
                    punchId,
                    PunchCorrectionRequest(checkInAt = checkInAt?.ifBlank { null }, checkOutAt = checkOutAt?.ifBlank { null }, note = note),
                )
                load()
            } catch (_: Exception) {
                // The correction dialog's caller keeps whatever was typed; retrying is
                // just re-submitting the same dialog.
            }
        }
    }
}
