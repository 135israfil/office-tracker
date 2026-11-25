package com.officemanagement.activity

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.officemanagement.core.network.ActivitySummaryResponse
import com.officemanagement.core.network.ApiService
import com.officemanagement.core.network.EmployeeListItem
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.launch
import javax.inject.Inject

data class ActivityUiState(
    val isLoading: Boolean = true,
    val employees: List<EmployeeListItem> = emptyList(),
    val selectedEmployeeId: Int? = null,
    val summary: ActivitySummaryResponse? = null,
    val error: String? = null,
)

/** §22's per-employee activity viewer (admin-only) — today's PC activity, plus the
 * separate Phone block when the employee has a tracked phone (backend/activities/
 * views.py's ActivitySummaryView). The minute-by-minute timeline and the screenshot
 * grid are a later phase (see the plan's screen-mapping notes) — this is the stat
 * cards, which is the part the phone-activity work this session actually added. */
@HiltViewModel
class ActivityViewModel @Inject constructor(private val api: ApiService) : ViewModel() {

    var uiState by mutableStateOf(ActivityUiState())
        private set

    init {
        viewModelScope.launch {
            val employees = try {
                api.employees().results
            } catch (e: Exception) {
                uiState = uiState.copy(isLoading = false, error = e.message ?: "Could not load employees.")
                return@launch
            }
            uiState = uiState.copy(employees = employees, selectedEmployeeId = employees.firstOrNull()?.id)
            uiState.selectedEmployeeId?.let { loadSummary(it) }
        }
    }

    fun selectEmployee(employeeId: Int) {
        uiState = uiState.copy(selectedEmployeeId = employeeId)
        loadSummary(employeeId)
    }

    fun retry() {
        uiState.selectedEmployeeId?.let { loadSummary(it) }
    }

    private fun loadSummary(employeeId: Int) {
        uiState = uiState.copy(isLoading = true, error = null)
        viewModelScope.launch {
            uiState = try {
                uiState.copy(isLoading = false, summary = api.activitySummary(employeeId))
            } catch (e: Exception) {
                uiState.copy(isLoading = false, error = e.message ?: "Could not load activity.")
            }
        }
    }
}
