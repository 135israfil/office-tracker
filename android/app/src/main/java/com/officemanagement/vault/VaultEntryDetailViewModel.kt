package com.officemanagement.vault

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.SavedStateHandle
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.officemanagement.core.network.ApiService
import com.officemanagement.core.network.VaultEntryItem
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.launch
import javax.inject.Inject

data class VaultEntryDetailUiState(
    val isLoading: Boolean = true,
    val entry: VaultEntryItem? = null,
    val revealedPassword: String? = null,
    val error: String? = null,
    val isDeleted: Boolean = false,
)

@HiltViewModel
class VaultEntryDetailViewModel @Inject constructor(
    private val api: ApiService,
    savedStateHandle: SavedStateHandle,
) : ViewModel() {

    private val entryId: Int = checkNotNull(savedStateHandle["entryId"])

    var uiState by mutableStateOf(VaultEntryDetailUiState())
        private set

    init {
        load()
    }

    fun load() {
        uiState = uiState.copy(isLoading = true, error = null)
        viewModelScope.launch {
            uiState = try {
                uiState.copy(isLoading = false, entry = api.vaultEntry(entryId))
            } catch (e: Exception) {
                uiState.copy(isLoading = false, error = e.message ?: "Could not load this entry.")
            }
        }
    }

    fun reveal() {
        viewModelScope.launch {
            try {
                uiState = uiState.copy(revealedPassword = api.revealVaultEntry(entryId).password)
            } catch (_: Exception) {
                // No visible error for a failed reveal in this phase — the button
                // staying clickable to retry is feedback enough.
            }
        }
    }

    fun hide() {
        uiState = uiState.copy(revealedPassword = null)
    }

    fun delete() {
        viewModelScope.launch {
            try {
                api.deleteVaultEntry(entryId)
                uiState = uiState.copy(isDeleted = true)
            } catch (_: Exception) {
                // Stays on the detail screen if deletion failed.
            }
        }
    }
}
