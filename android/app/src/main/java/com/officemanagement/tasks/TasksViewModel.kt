package com.officemanagement.tasks

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.officemanagement.core.network.ApiService
import com.officemanagement.core.network.TaskItem
import com.officemanagement.core.network.TaskWriteRequest
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.launch
import javax.inject.Inject

data class TasksUiState(
    val isLoading: Boolean = true,
    val tasks: List<TaskItem> = emptyList(),
    val error: String? = null,
)

@HiltViewModel
class TasksViewModel @Inject constructor(private val api: ApiService) : ViewModel() {

    var uiState by mutableStateOf(TasksUiState())
        private set

    init {
        load()
    }

    fun load() {
        uiState = uiState.copy(isLoading = true, error = null)
        viewModelScope.launch {
            uiState = try {
                // Overdue-first sort (the web app's own default) is a small client-side
                // pass over what the API already returns, not a separate query param.
                val tasks = api.tasks().results.sortedByDescending { it.isOverdue }
                TasksUiState(isLoading = false, tasks = tasks)
            } catch (e: Exception) {
                TasksUiState(isLoading = false, error = e.message ?: "Could not load tasks.")
            }
        }
    }

    fun createTask(
        title: String,
        description: String,
        status: String,
        deadline: String?,
        assigneeIds: List<Int>,
        onDone: (Int) -> Unit,
    ) {
        viewModelScope.launch {
            try {
                val task = api.createTask(
                    TaskWriteRequest(
                        title = title,
                        description = description,
                        status = status,
                        deadline = deadline,
                        assignees = assigneeIds,
                    ),
                )
                load()
                onDone(task.id)
            } catch (_: Exception) {
                // The create screen stays open on failure; nothing to reconcile here.
            }
        }
    }
}
