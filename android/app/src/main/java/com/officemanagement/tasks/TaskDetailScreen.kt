package com.officemanagement.tasks

import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.ExposedDropdownMenuBox
import androidx.compose.material3.ExposedDropdownMenuDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.MenuAnchorType
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel

private val STATUSES = listOf("TODO", "IN_PROGRESS", "BLOCKED", "DONE", "CANCELLED")

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun TaskDetailScreen(viewModel: TaskDetailViewModel = hiltViewModel(), onDeleted: () -> Unit) {
    val state = viewModel.uiState
    var statusMenuExpanded by remember { mutableStateOf(false) }
    var addMenuExpanded by remember { mutableStateOf(false) }

    LaunchedEffect(state.isDeleted) { if (state.isDeleted) onDeleted() }

    Box(modifier = Modifier.fillMaxSize().safeDrawingPadding()) {
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
            state.task != null -> {
                val task = state.task
                Column(modifier = Modifier.fillMaxSize().padding(16.dp)) {
                    Text(task.title, style = MaterialTheme.typography.headlineSmall)
                    if (task.description.isNotBlank()) {
                        Text(task.description, modifier = Modifier.padding(top = 8.dp))
                    }
                    Text(
                        "Created by ${task.createdBy.name}" + (task.deadline?.let { " · due $it" } ?: ""),
                        style = MaterialTheme.typography.bodySmall,
                        modifier = Modifier.padding(top = 8.dp),
                    )

                    ExposedDropdownMenuBox(
                        expanded = statusMenuExpanded,
                        onExpandedChange = { statusMenuExpanded = it },
                        modifier = Modifier.padding(top = 16.dp),
                    ) {
                        OutlinedTextField(
                            value = task.status,
                            onValueChange = {},
                            readOnly = true,
                            label = { Text("Status") },
                            trailingIcon = { ExposedDropdownMenuDefaults.TrailingIcon(expanded = statusMenuExpanded) },
                            modifier = Modifier.fillMaxWidth().menuAnchor(MenuAnchorType.PrimaryNotEditable),
                        )
                        DropdownMenu(expanded = statusMenuExpanded, onDismissRequest = { statusMenuExpanded = false }) {
                            STATUSES.forEach { status ->
                                DropdownMenuItem(
                                    text = { Text(status) },
                                    onClick = { statusMenuExpanded = false; viewModel.setStatus(status) },
                                )
                            }
                        }
                    }

                    Text("Assignees", style = MaterialTheme.typography.titleMedium, modifier = Modifier.padding(top = 20.dp))
                    task.assignees.forEach { assignee ->
                        Row(
                            modifier = Modifier.fillMaxWidth().padding(vertical = 4.dp),
                            verticalAlignment = Alignment.CenterVertically,
                        ) {
                            Text(assignee.employee.name, modifier = Modifier.weight(1f))
                            OutlinedButton(onClick = { viewModel.removeAssignee(assignee.employee.id) }) {
                                Text("Remove")
                            }
                        }
                    }

                    val assignedIds = task.assignees.map { it.employee.id }.toSet()
                    val candidates = state.assignableEmployees.filter { it.id !in assignedIds }
                    if (candidates.isNotEmpty()) {
                        Box(modifier = Modifier.padding(top = 8.dp)) {
                            OutlinedButton(onClick = { addMenuExpanded = true }) { Text("Add assignee") }
                            DropdownMenu(expanded = addMenuExpanded, onDismissRequest = { addMenuExpanded = false }) {
                                candidates.forEach { employee ->
                                    DropdownMenuItem(
                                        text = { Text(employee.name) },
                                        onClick = { addMenuExpanded = false; viewModel.addAssignee(employee.id) },
                                    )
                                }
                            }
                        }
                    }

                    Button(
                        onClick = viewModel::delete,
                        colors = androidx.compose.material3.ButtonDefaults.buttonColors(containerColor = MaterialTheme.colorScheme.error),
                        modifier = Modifier.fillMaxWidth().padding(top = 24.dp),
                    ) { Text("Delete task") }
                }
            }
        }
    }
}
