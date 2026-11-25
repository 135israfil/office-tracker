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
import com.officemanagement.core.network.TaskWriteRequest
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.launch
import javax.inject.Inject

data class TaskDetailUiState(
    val isLoading: Boolean = true,
    val task: TaskItem? = null,
    val assignableEmployees: List<EmployeeStub> = emptyList(),
    val subtasks: List<TaskItem> = emptyList(),
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
                val task = api.task(taskId)
                // A sub-task cannot itself have sub-tasks (the backend enforces one
                // level), so that section only ever applies to a root task.
                val subtasks = if (task.parentStub == null) {
                    try {
                        api.tasks(parent = taskId).results
                    } catch (_: Exception) {
                        emptyList()
                    }
                } else {
                    emptyList()
                }
                uiState.copy(isLoading = false, task = task, subtasks = subtasks)
            } catch (e: Exception) {
                uiState.copy(isLoading = false, error = e.message ?: "Could not load the task.")
            }
        }
    }

    fun setStatus(status: String) = patch(TaskPatchRequest(status = status))
    fun setTitle(title: String) = patch(TaskPatchRequest(title = title))
    fun setDescription(description: String) = patch(TaskPatchRequest(description = description))
    fun setDeadline(deadline: String?) = patch(TaskPatchRequest(deadline = deadline))

    private fun patch(body: TaskPatchRequest) {
        viewModelScope.launch {
            try {
                uiState = uiState.copy(task = api.updateTask(taskId, body))
            } catch (_: Exception) {
                // Reverts on next load() if this failed silently; a toast is a small
                // follow-up, not worth a new UI pattern for one field.
            }
        }
    }

    fun createSubtask(
        title: String,
        description: String,
        status: String,
        deadline: String?,
        assigneeIds: List<Int>,
    ) {
        viewModelScope.launch {
            try {
                api.createTask(
                    TaskWriteRequest(
                        title = title,
                        description = description,
                        status = status,
                        deadline = deadline,
                        parent = taskId,
                        assignees = assigneeIds,
                    ),
                )
                uiState = uiState.copy(subtasks = api.tasks(parent = taskId).results)
            } catch (_: Exception) {
                // The sub-task form stays open with what was typed on failure.
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
