package com.officemanagement.tasks

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
import androidx.compose.material3.Checkbox
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.FloatingActionButton
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
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
import com.officemanagement.core.network.EmployeeStub
import com.officemanagement.core.network.TaskItem

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
                    OutlinedButton(onClick = viewModel::load, modifier = Modifier.padding(top = 12.dp)) {
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
            onCreate = { title, description, assigneeIds ->
                showCreate = false
                viewModel.createTask(title, description, assigneeIds) {}
            },
        )
    }
}

@Composable
private fun TaskRow(task: TaskItem, onClick: () -> Unit) {
    Column(modifier = Modifier.fillMaxWidth().clickable(onClick = onClick).padding(16.dp)) {
        Row {
            Text(task.title, style = MaterialTheme.typography.titleMedium, modifier = Modifier.weight(1f))
            if (task.isOverdue) Text("OVERDUE", color = MaterialTheme.colorScheme.error, style = MaterialTheme.typography.labelSmall)
        }
        Text("${task.status} · ${task.deadline ?: "no deadline"}", style = MaterialTheme.typography.bodySmall)
    }
}

@Composable
private fun NewTaskDialog(
    viewModel: NewTaskViewModel = hiltViewModel(),
    onDismiss: () -> Unit,
    onCreate: (String, String, List<Int>) -> Unit,
) {
    var title by remember { mutableStateOf("") }
    var description by remember { mutableStateOf("") }
    val selected = remember { mutableStateOf(setOf<Int>()) }
    val employees = viewModel.employees

    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("New task") },
        text = {
            Column {
                OutlinedTextField(value = title, onValueChange = { title = it }, label = { Text("Title") }, singleLine = true)
                OutlinedTextField(
                    value = description,
                    onValueChange = { description = it },
                    label = { Text("Description") },
                    modifier = Modifier.padding(top = 8.dp),
                )
                if (employees.isNotEmpty()) {
                    Text("Assign to", style = MaterialTheme.typography.labelMedium, modifier = Modifier.padding(top = 12.dp))
                    employees.forEach { employee: EmployeeStub ->
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Checkbox(
                                checked = employee.id in selected.value,
                                onCheckedChange = { checked ->
                                    selected.value = if (checked) selected.value + employee.id else selected.value - employee.id
                                },
                            )
                            Text(employee.name)
                        }
                    }
                }
            }
        },
        confirmButton = {
            OutlinedButton(
                onClick = { if (title.isNotBlank()) onCreate(title, description, selected.value.toList()) },
            ) { Text("Create") }
        },
        dismissButton = { OutlinedButton(onClick = onDismiss) { Text("Cancel") } },
    )
}
