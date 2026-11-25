package com.officemanagement.tasks

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.SavedStateHandle
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.officemanagement.core.network.ApiService
import com.officemanagement.core.network.AssigneeRequest
import com.officemanagement.core.network.EmployeeStub
import com.officemanagement.core.network.TaskItem
import com.officemanagement.core.network.TaskPatchRequest
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.launch
import javax.inject.Inject

data class TaskDetailUiState(
    val isLoading: Boolean = true,
    val task: TaskItem? = null,
    val assignableEmployees: List<EmployeeStub> = emptyList(),
    val error: String? = null,
    val isDeleted: Boolean = false,
)

@HiltViewModel
class TaskDetailViewModel @Inject constructor(
    private val api: ApiService,
    savedStateHandle: SavedStateHandle,
) : ViewModel() {

    private val taskId: Int = checkNotNull(savedStateHandle["taskId"])

    var uiState by mutableStateOf(TaskDetailUiState())
        private set

    init {
        load()
        viewModelScope.launch {
            val employees = try {
                api.assignableEmployees()
            } catch (_: Exception) {
                emptyList()
            }
            uiState = uiState.copy(assignableEmployees = employees)
        }
    }

    fun load() {
        uiState = uiState.copy(isLoading = true, error = null)
        viewModelScope.launch {
            uiState = try {
                uiState.copy(isLoading = false, task = api.task(taskId))
            } catch (e: Exception) {
                uiState.copy(isLoading = false, error = e.message ?: "Could not load the task.")
            }
        }
    }

    fun setStatus(status: String) {
        viewModelScope.launch {
            try {
                uiState = uiState.copy(task = api.updateTask(taskId, TaskPatchRequest(status = status)))
            } catch (_: Exception) {
                // The status reverts on next load() if this failed silently; a
                // toast is a small follow-up, not worth a new UI pattern for one field.
            }
        }
    }

    fun addAssignee(employeeId: Int) {
        viewModelScope.launch {
            try {
                uiState = uiState.copy(task = api.addTaskAssignee(taskId, AssigneeRequest(employeeId)))
            } catch (_: Exception) {
                // See setStatus.
            }
        }
    }

    fun removeAssignee(employeeId: Int) {
        viewModelScope.launch {
            try {
                uiState = uiState.copy(task = api.removeTaskAssignee(taskId, employeeId))
            } catch (_: Exception) {
                // See setStatus.
            }
        }
    }

    fun delete() {
        viewModelScope.launch {
            try {
                api.deleteTask(taskId)
                uiState = uiState.copy(isDeleted = true)
            } catch (_: Exception) {
                // Stays on the detail screen if deletion failed.
            }
        }
    }
}
