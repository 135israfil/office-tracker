package com.officemanagement.employees

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.officemanagement.core.network.ApiService
import com.officemanagement.core.network.EmployeeListItem
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.launch
import javax.inject.Inject

data class EmployeesUiState(
    val isLoading: Boolean = true,
    val query: String = "",
    val employees: List<EmployeeListItem> = emptyList(),
    val error: String? = null,
)

/** The employee directory (admin-only, §4) — search only in this phase; create,
 * disable/enable and the shift editor are a later phase (see the plan's
 * screen-mapping notes). */
@HiltViewModel
class EmployeesViewModel @Inject constructor(private val api: ApiService) : ViewModel() {

    var uiState by mutableStateOf(EmployeesUiState())
        private set

    init {
        load()
    }

    fun onQueryChange(value: String) {
        uiState = uiState.copy(query = value)
    }

    fun load() {
        uiState = uiState.copy(isLoading = true, error = null)
        viewModelScope.launch {
            uiState = try {
                val results = api.employees(search = uiState.query.ifBlank { null }).results
                uiState.copy(isLoading = false, employees = results)
            } catch (e: Exception) {
                uiState.copy(isLoading = false, error = e.message ?: "Could not load employees.")
            }
        }
    }
}
