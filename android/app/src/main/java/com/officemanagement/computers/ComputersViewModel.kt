package com.officemanagement.computers

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.officemanagement.core.network.ApiService
import com.officemanagement.core.network.ComputerListItem
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.launch
import javax.inject.Inject

data class ComputersUiState(
    val isLoading: Boolean = true,
    val computers: List<ComputerListItem> = emptyList(),
    val error: String? = null,
)

/** The managed device fleet (admin-only) — PC rows from the desktop agent and
 * Android rows auto-provisioned by a phone's own login (device_type) side by side,
 * same list the web app's Computers page shows. Enrolling a new PC (the one-time code
 * flow) is a later phase; Android rows need no enrolling at all, see the plan's §5. */
@HiltViewModel
class ComputersViewModel @Inject constructor(private val api: ApiService) : ViewModel() {

    var uiState by mutableStateOf(ComputersUiState())
        private set

    init {
        load()
    }

    fun load() {
        uiState = uiState.copy(isLoading = true, error = null)
        viewModelScope.launch {
            uiState = try {
                ComputersUiState(isLoading = false, computers = api.computers().results)
            } catch (e: Exception) {
                ComputersUiState(isLoading = false, error = e.message ?: "Could not load computers.")
            }
        }
    }
}
