package com.officemanagement.vault

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.SavedStateHandle
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.officemanagement.auth.AuthRepository
import com.officemanagement.core.network.ApiService
import com.officemanagement.core.network.AssigneeRequest
import com.officemanagement.core.network.EmployeeStub
import com.officemanagement.core.network.VaultEntryItem
import com.officemanagement.core.network.VaultEntryWriteRequest
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.launch
import javax.inject.Inject

data class VaultEntryDetailUiState(
    val isLoading: Boolean = true,
    val entry: VaultEntryItem? = null,
    val assignableEmployees: List<EmployeeStub> = emptyList(),
    val revealedPassword: String? = null,
    val error: String? = null,
    val isDeleted: Boolean = false,
    val isOwner: Boolean = false,
)

@HiltViewModel
class VaultEntryDetailViewModel @Inject constructor(
    private val api: ApiService,
    private val authRepository: AuthRepository,
    savedStateHandle: SavedStateHandle,
) : ViewModel() {

    private val entryId: Int = checkNotNull(savedStateHandle["entryId"])

    var uiState by mutableStateOf(VaultEntryDetailUiState())
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
                val entry = api.vaultEntry(entryId)
                val myId = authRepository.currentUser.value?.employee?.id
                uiState.copy(isLoading = false, entry = entry, isOwner = myId != null && myId == entry.owner.id)
            } catch (e: Exception) {
                uiState.copy(isLoading = false, error = e.message ?: "Could not load this entry.")
            }
        }
    }

    fun setTitle(title: String) = save { it.copy(title = title) }
    fun setUsername(username: String) = save { it.copy(username = username) }
    fun setUrl(url: String) = save { it.copy(url = url) }
    fun setNotes(notes: String) = save { it.copy(notes = notes) }

    private fun save(mutate: (VaultEntryItem) -> VaultEntryItem) {
        val current = uiState.entry ?: return
        val updated = mutate(current)
        viewModelScope.launch {
            try {
                val body = VaultEntryWriteRequest(
                    title = updated.title,
                    username = updated.username,
                    url = updated.url,
                    notes = updated.notes,
                )
                uiState = uiState.copy(entry = api.updateVaultEntry(entryId, body))
            } catch (_: Exception) {
                // Reverts to the server's view on next load(); not worth a toast here.
            }
        }
    }

    fun updatePassword(newPassword: String, onDone: (success: Boolean) -> Unit) {
        val current = uiState.entry ?: return
        if (newPassword.isBlank()) return
        viewModelScope.launch {
            try {
                uiState = uiState.copy(
                    entry = api.updateVaultEntry(
                        entryId,
                        VaultEntryWriteRequest(
                            title = current.title,
                            username = current.username,
                            password = newPassword,
                            url = current.url,
                            notes = current.notes,
                        ),
                    ),
                    // The just-replaced password is stale the moment it's set — never
                    // leave it sitting on screen looking current.
                    revealedPassword = null,
                )
                onDone(true)
            } catch (_: Exception) {
                onDone(false)
            }
        }
    }

    fun share(employeeId: Int) {
        viewModelScope.launch {
            try {
                uiState = uiState.copy(entry = api.shareVaultEntry(entryId, AssigneeRequest(employeeId)))
            } catch (_: Exception) {
                // See save().
            }
        }
    }

    fun revoke(employeeId: Int) {
        viewModelScope.launch {
            try {
                uiState = uiState.copy(entry = api.revokeVaultGrant(entryId, employeeId))
            } catch (_: Exception) {
                // See save().
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
