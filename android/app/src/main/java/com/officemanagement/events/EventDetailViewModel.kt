package com.officemanagement.events

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.SavedStateHandle
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.officemanagement.core.network.ApiService
import com.officemanagement.core.network.EventItem
import com.officemanagement.core.network.EventWriteRequest
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.launch
import javax.inject.Inject

data class EventDetailUiState(
    val isLoading: Boolean = true,
    val event: EventItem? = null,
    val error: String? = null,
    val isDeleted: Boolean = false,
)

@HiltViewModel
class EventDetailViewModel @Inject constructor(
    private val api: ApiService,
    savedStateHandle: SavedStateHandle,
) : ViewModel() {

    private val eventId: Int = checkNotNull(savedStateHandle["eventId"])

    var uiState by mutableStateOf(EventDetailUiState())
        private set

    init {
        load()
    }

    fun load() {
        uiState = uiState.copy(isLoading = true, error = null)
        viewModelScope.launch {
            uiState = try {
                uiState.copy(isLoading = false, event = api.event(eventId))
            } catch (e: Exception) {
                uiState.copy(isLoading = false, error = e.message ?: "Could not load this event.")
            }
        }
    }

    fun setBookingStatus(status: String) {
        val current = uiState.event ?: return
        save(current.copy(bookingStatus = status))
    }

    fun updateSetup(setup: String) {
        val current = uiState.event ?: return
        save(current.copy(setup = setup))
    }

    private fun save(updated: EventItem) {
        viewModelScope.launch {
            try {
                val body = EventWriteRequest(
                    title = updated.title,
                    agencyName = updated.agencyName,
                    venueName = updated.venueName,
                    setup = updated.setup,
                    assignedLeadId = updated.assignedLead?.id,
                    bookingStatus = updated.bookingStatus,
                    alertOn = updated.alertOn,
                )
                uiState = uiState.copy(event = api.updateEvent(eventId, body))
            } catch (_: Exception) {
                // Reverts to the server's view on next load(); not worth a toast here.
            }
        }
    }

    fun delete() {
        viewModelScope.launch {
            try {
                api.deleteEvent(eventId)
                uiState = uiState.copy(isDeleted = true)
            } catch (_: Exception) {
                // Stays on the detail screen if deletion failed.
            }
        }
    }
}
