package com.officemanagement.dashboard

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.officemanagement.core.network.ApiService
import com.officemanagement.core.network.MySummary
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.launch
import javax.inject.Inject

data class MyDashboardUiState(
    val isLoading: Boolean = true,
    val summary: MySummary? = null,
    val error: String? = null,
)

@HiltViewModel
class MyDashboardViewModel @Inject constructor(private val api: ApiService) : ViewModel() {

    var uiState by mutableStateOf(MyDashboardUiState())
        private set

    init {
        load()
    }

    fun load() {
        uiState = uiState.copy(isLoading = true, error = null)
        viewModelScope.launch {
            uiState = try {
                MyDashboardUiState(isLoading = false, summary = api.mySummary())
            } catch (e: Exception) {
                MyDashboardUiState(isLoading = false, error = e.message ?: "Could not load your dashboard.")
            }
        }
    }
}
