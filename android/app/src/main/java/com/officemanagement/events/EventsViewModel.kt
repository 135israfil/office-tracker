package com.officemanagement.events

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.officemanagement.core.network.ApiService
import com.officemanagement.core.network.EmployeeStub
import com.officemanagement.core.network.EventItem
import com.officemanagement.core.network.EventWriteRequest
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.launch
import javax.inject.Inject

data class EventsUiState(
    val isLoading: Boolean = true,
    val events: List<EventItem> = emptyList(),
    val employees: List<EmployeeStub> = emptyList(),
    val error: String? = null,
)

@HiltViewModel
class EventsViewModel @Inject constructor(private val api: ApiService) : ViewModel() {

    var uiState by mutableStateOf(EventsUiState())
        private set

    init {
        load()
        viewModelScope.launch {
            val employees = try {
                api.assignableEmployees()
            } catch (_: Exception) {
                emptyList()
            }
            uiState = uiState.copy(employees = employees)
        }
    }

    fun load() {
        uiState = uiState.copy(isLoading = true, error = null)
        viewModelScope.launch {
            uiState = try {
                uiState.copy(isLoading = false, events = api.events().results)
            } catch (e: Exception) {
                uiState.copy(isLoading = false, error = e.message ?: "Could not load events.")
            }
        }
    }

    fun createEvent(
        title: String,
        agency: String,
        venue: String,
        assignedLeadId: Int?,
        bookingStatus: String,
        alertOn: String?,
        onDone: (Int) -> Unit,
    ) {
        viewModelScope.launch {
            try {
                val event = api.createEvent(
                    EventWriteRequest(
                        title = title,
                        agencyName = agency,
                        venueName = venue,
                        assignedLeadId = assignedLeadId,
                        bookingStatus = bookingStatus,
                        alertOn = alertOn,
                    ),
                )
                load()
                onDone(event.id)
            } catch (_: Exception) {
                // The create dialog stays open on failure.
            }
        }
    }
}
