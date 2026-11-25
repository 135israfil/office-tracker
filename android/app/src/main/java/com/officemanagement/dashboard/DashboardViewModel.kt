package com.officemanagement.dashboard

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.officemanagement.core.network.AdminDashboard
import com.officemanagement.core.network.ApiService
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.launch
import javax.inject.Inject

data class DashboardUiState(
    val isLoading: Boolean = true,
    val dashboard: AdminDashboard? = null,
    val error: String? = null,
)

@HiltViewModel
class DashboardViewModel @Inject constructor(private val api: ApiService) : ViewModel() {

    var uiState by mutableStateOf(DashboardUiState())
        private set

    init {
        load()
    }

    fun load() {
        uiState = uiState.copy(isLoading = true, error = null)
        viewModelScope.launch {
            uiState = try {
                DashboardUiState(isLoading = false, dashboard = api.adminDashboard())
            } catch (e: Exception) {
                DashboardUiState(isLoading = false, error = e.message ?: "Could not load the dashboard.")
            }
        }
    }
}
