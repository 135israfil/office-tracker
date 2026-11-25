package com.officemanagement.vault

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.officemanagement.core.network.ApiService
import com.officemanagement.core.network.VaultEntryItem
import com.officemanagement.core.network.VaultEntryWriteRequest
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.launch
import javax.inject.Inject

data class VaultUiState(
    val isLoading: Boolean = true,
    val entries: List<VaultEntryItem> = emptyList(),
    val error: String? = null,
)

@HiltViewModel
class VaultViewModel @Inject constructor(private val api: ApiService) : ViewModel() {

    var uiState by mutableStateOf(VaultUiState())
        private set

    init {
        load()
    }

    fun load() {
        uiState = uiState.copy(isLoading = true, error = null)
        viewModelScope.launch {
            uiState = try {
                VaultUiState(isLoading = false, entries = api.vaultEntries().results)
            } catch (e: Exception) {
                VaultUiState(isLoading = false, error = e.message ?: "Could not load the vault.")
            }
        }
    }

    fun createEntry(title: String, username: String, password: String, url: String, notes: String, onDone: (Int) -> Unit) {
        viewModelScope.launch {
            try {
                val entry = api.createVaultEntry(
                    VaultEntryWriteRequest(title = title, username = username, password = password, url = url, notes = notes),
                )
                load()
                onDone(entry.id)
            } catch (_: Exception) {
                // The create dialog stays open on failure.
            }
        }
    }
}
