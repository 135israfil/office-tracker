package com.officemanagement.tasks
import com.officemanagement.ui.components.AppOutlinedButton

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.FloatingActionButton
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import com.officemanagement.core.network.TaskItem
import com.officemanagement.ui.components.BadgeTone
import com.officemanagement.ui.components.StatusBadge

@Composable
fun TasksScreen(viewModel: TasksViewModel = hiltViewModel(), onOpenTask: (Int) -> Unit) {
    val state = viewModel.uiState
    var showCreate by remember { mutableStateOf(false) }

    Scaffold(
        floatingActionButton = {
            FloatingActionButton(onClick = { showCreate = true }) {
                Icon(Icons.Default.Add, contentDescription = "New task")
            }
        },
    ) { padding ->
        Box(modifier = Modifier.padding(padding).fillMaxSize()) {
            when {
                state.isLoading -> CircularProgressIndicator(modifier = Modifier.align(Alignment.Center))
                state.error != null -> Column(
                    modifier = Modifier.align(Alignment.Center).padding(24.dp),
                    horizontalAlignment = Alignment.CenterHorizontally,
                ) {
                    Text(state.error, color = MaterialTheme.colorScheme.error)
                    AppOutlinedButton(onClick = viewModel::load, modifier = Modifier.padding(top = 12.dp)) {
                        Text("Retry")
                    }
                }
                state.tasks.isEmpty() -> Text("No tasks", modifier = Modifier.align(Alignment.Center))
                else -> LazyColumn(modifier = Modifier.fillMaxSize()) {
                    items(state.tasks, key = { it.id }) { task ->
                        TaskRow(task, onClick = { onOpenTask(task.id) })
                        HorizontalDivider()
                    }
                }
            }
        }
    }

    if (showCreate) {
        NewTaskDialog(
            onDismiss = { showCreate = false },
            onCreate = { title, description, status, deadline, assigneeIds ->
                showCreate = false
                viewModel.createTask(title, description, status, deadline, assigneeIds) {}
            },
        )
    }
}

// Mirrors frontend/src/views/TasksView.vue's STATUS_BADGE map: TODO has no tone (plain
// pill), IN_PROGRESS/BLOCKED read as "in motion but not done" (warn), DONE is the one
// positive outcome (ok), CANCELLED is the one terminal negative (danger).
private fun taskBadgeTone(status: String): BadgeTone = when (status) {
    "DONE" -> BadgeTone.OK
    "IN_PROGRESS", "BLOCKED" -> BadgeTone.WARN
    "CANCELLED" -> BadgeTone.DANGER
    else -> BadgeTone.NEUTRAL
}

@Composable
private fun TaskRow(task: TaskItem, onClick: () -> Unit) {
    Column(modifier = Modifier.fillMaxWidth().clickable(onClick = onClick).padding(16.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(task.title, style = MaterialTheme.typography.titleMedium, modifier = Modifier.weight(1f))
            if (task.isOverdue) {
                Text(
                    "OVERDUE",
                    color = MaterialTheme.colorScheme.error,
                    style = MaterialTheme.typography.labelSmall,
                    modifier = Modifier.padding(end = 8.dp),
                )
            }
            StatusBadge(task.status, tone = taskBadgeTone(task.status))
        }
        Text(
            task.deadline ?: "no deadline",
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            modifier = Modifier.padding(top = 4.dp),
        )
    }
}

@Composable
private fun NewTaskDialog(
    viewModel: NewTaskViewModel = hiltViewModel(),
    onDismiss: () -> Unit,
    onCreate: (title: String, description: String, status: String, deadline: String?, assigneeIds: List<Int>) -> Unit,
) {
    val form = remember { TaskFormState() }
    val employees = viewModel.employees

    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("New task") },
        text = { TaskFormFields(form, employees) },
        confirmButton = {
            AppOutlinedButton(
                onClick = {
                    if (form.title.isNotBlank()) {
                        onCreate(form.title, form.description, form.status, form.deadline.ifBlank { null }, form.selectedAssignees.value.toList())
                    }
                },
            ) { Text("Create") }
        },
        dismissButton = { AppOutlinedButton(onClick = onDismiss) { Text("Cancel") } },
    )
}
