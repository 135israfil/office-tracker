package com.officemanagement.events

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.SavedStateHandle
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.officemanagement.auth.AuthRepository
import com.officemanagement.core.network.ApiService
import com.officemanagement.core.network.EmployeeStub
import com.officemanagement.core.network.EventCoordinationPatchRequest
import com.officemanagement.core.network.EventFinancialsPatchRequest
import com.officemanagement.core.network.EventItem
import com.officemanagement.core.network.EventWriteRequest
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.launch
import javax.inject.Inject

data class EventDetailUiState(
    val isLoading: Boolean = true,
    val event: EventItem? = null,
    val assignableEmployees: List<EmployeeStub> = emptyList(),
    val error: String? = null,
    val saveError: String? = null,
    val isDeleted: Boolean = false,
    val isOwner: Boolean = false,
    val isAdmin: Boolean = false,
)

@HiltViewModel
class EventDetailViewModel @Inject constructor(
    private val api: ApiService,
    private val authRepository: AuthRepository,
    savedStateHandle: SavedStateHandle,
) : ViewModel() {

    private val eventId: Int = checkNotNull(savedStateHandle["eventId"])

    var uiState by mutableStateOf(EventDetailUiState())
        private set

    init {
        load()
        viewModelScope.launch {
            uiState = uiState.copy(
                assignableEmployees = try {
                    api.assignableEmployees()
                } catch (_: Exception) {
                    emptyList()
                },
            )
        }
    }

    fun load() {
        uiState = uiState.copy(isLoading = true, error = null)
        viewModelScope.launch {
            uiState = try {
                val event = api.event(eventId)
                val user = authRepository.currentUser.value
                val myId = user?.employee?.id
                uiState.copy(
                    isLoading = false,
                    event = event,
                    isOwner = myId != null && myId == event.owner.id,
                    isAdmin = user?.isAdmin == true,
                )
            } catch (e: Exception) {
                uiState.copy(isLoading = false, error = e.message ?: "Could not load this event.")
            }
        }
    }

    fun setTitle(title: String) = save(uiState.event?.copy(title = title))
    fun setAgencyName(agency: String) = save(uiState.event?.copy(agencyName = agency))
    fun setVenueName(venue: String) = save(uiState.event?.copy(venueName = venue))
    fun setAlertOn(alertOn: String?) = save(uiState.event?.copy(alertOn = alertOn))
    fun updateSetup(setup: String) = save(uiState.event?.copy(setup = setup))

    private fun save(updated: EventItem?) {
        if (updated == null) return
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
                uiState = uiState.copy(event = api.updateEvent(eventId, body), saveError = null)
            } catch (e: Exception) {
                uiState = uiState.copy(saveError = e.message ?: "That didn't save.")
            }
        }
    }

    // The owner edits assigned-lead/booking-status through the ordinary update; a
    // non-owner admin must use the dedicated coordination action instead — matches
    // EventDetailView.vue's saveCoordination().
    fun setAssignedLead(employeeId: Int?) {
        val current = uiState.event ?: return
        if (uiState.isOwner) {
            save(current.copy(assignedLead = uiState.assignableEmployees.find { it.id == employeeId }))
            return
        }
        viewModelScope.launch {
            try {
                uiState = uiState.copy(
                    event = api.updateEventCoordination(eventId, EventCoordinationPatchRequest(assignedLeadId = employeeId)),
                    saveError = null,
                )
            } catch (e: Exception) {
                uiState = uiState.copy(saveError = e.message ?: "That didn't save.")
            }
        }
    }

    fun setBookingStatus(status: String) {
        val current = uiState.event ?: return
        if (uiState.isOwner) {
            save(current.copy(bookingStatus = status))
            return
        }
        viewModelScope.launch {
            try {
                uiState = uiState.copy(
                    event = api.updateEventCoordination(eventId, EventCoordinationPatchRequest(bookingStatus = status)),
                    saveError = null,
                )
            } catch (e: Exception) {
                uiState = uiState.copy(saveError = e.message ?: "That didn't save.")
            }
        }
    }

    // Admin-only, regardless of who owns the event — matches EventDetailView.vue's
    // saveFinancials().
    fun setFinancials(budget: String?, documentStatus: String?, financialStatus: String?) {
        viewModelScope.launch {
            try {
                uiState = uiState.copy(
                    event = api.updateEventFinancials(
                        eventId,
                        EventFinancialsPatchRequest(budget = budget, documentStatus = documentStatus, financialStatus = financialStatus),
                    ),
                )
            } catch (_: Exception) {
                // Reverts to the server's view on next load().
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
