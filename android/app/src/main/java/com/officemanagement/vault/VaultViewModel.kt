package com.officemanagement.vault

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.officemanagement.auth.AuthRepository
import com.officemanagement.core.network.ApiService
import com.officemanagement.core.network.EmployeeStub
import com.officemanagement.core.network.VaultEntryItem
import com.officemanagement.core.network.VaultEntryWriteRequest
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.launch
import javax.inject.Inject

data class VaultUiState(
    val isLoading: Boolean = true,
    val entries: List<VaultEntryItem> = emptyList(),
    val employees: List<EmployeeStub> = emptyList(),
    val error: String? = null,
)

@HiltViewModel
class VaultViewModel @Inject constructor(
    private val api: ApiService,
    private val authRepository: AuthRepository,
) : ViewModel() {

    var uiState by mutableStateOf(VaultUiState())
        private set

    init {
        load()
        viewModelScope.launch {
            // Sharing with yourself is meaningless — you already own it — so leave
            // yourself out of the picker, matching VaultView.vue's shareableEmployees.
            val myId = authRepository.currentUser.value?.employee?.id
            val employees = try {
                api.assignableEmployees().filter { it.id != myId }
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
                uiState.copy(isLoading = false, entries = api.vaultEntries().results)
            } catch (e: Exception) {
                uiState.copy(isLoading = false, error = e.message ?: "Could not load the vault.")
            }
        }
    }

    fun createEntry(
        title: String,
        username: String,
        password: String,
        url: String,
        notes: String,
        granteeIds: List<Int>,
        onDone: (Int) -> Unit,
    ) {
        viewModelScope.launch {
            try {
                val entry = api.createVaultEntry(
                    VaultEntryWriteRequest(
                        title = title,
                        username = username,
                        password = password,
                        url = url,
                        notes = notes,
                        grantees = granteeIds,
                    ),
                )
                load()
                onDone(entry.id)
            } catch (_: Exception) {
                // The create dialog stays open on failure.
            }
        }
    }
}
