package com.officemanagement.notifications

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.officemanagement.core.network.ApiService
import com.officemanagement.core.network.NotificationItem
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.launch
import javax.inject.Inject

data class NotificationsUiState(
    val isLoading: Boolean = true,
    val items: List<NotificationItem> = emptyList(),
    val error: String? = null,
)

/** §-whatever's in-app inbox: list, mark-read, mark-all-read. No push/FCM
 * infrastructure exists on the backend (confirmed in the research pass) — a later
 * phase could add 30-second polling to match the web app's own mechanism; this
 * screen loads once on open and on manual refresh, same floor the web app's first
 * load starts from. */
@HiltViewModel
class NotificationsViewModel @Inject constructor(private val api: ApiService) : ViewModel() {

    var uiState by mutableStateOf(NotificationsUiState())
        private set

    init {
        load()
    }

    fun load() {
        uiState = uiState.copy(isLoading = true, error = null)
        viewModelScope.launch {
            uiState = try {
                NotificationsUiState(isLoading = false, items = api.notifications().results)
            } catch (e: Exception) {
                NotificationsUiState(isLoading = false, error = e.message ?: "Could not load notifications.")
            }
        }
    }

    fun markRead(id: Int) {
        viewModelScope.launch {
            try {
                api.markNotificationRead(id)
                uiState = uiState.copy(
                    items = uiState.items.map { if (it.id == id) it.copy(readAt = "now") else it },
                )
            } catch (_: Exception) {
                // Best effort: a failed mark-read is not worth surfacing an error for;
                // the next load() will reconcile the real state anyway.
            }
        }
    }

    fun markAllRead() {
        viewModelScope.launch {
            try {
                api.markAllNotificationsRead()
                load()
            } catch (_: Exception) {
                // See markRead — best effort.
            }
        }
    }
}
