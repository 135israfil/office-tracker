package com.officemanagement.tasks
import com.officemanagement.ui.components.AppOutlinedButton
import com.officemanagement.ui.components.AppButton

import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.ExposedDropdownMenuBox
import androidx.compose.material3.ExposedDropdownMenuDefaults
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.MenuAnchorType
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
import com.officemanagement.core.network.EmployeeStub
import com.officemanagement.ui.components.BadgeTone
import com.officemanagement.ui.components.StatusBadge

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun TaskDetailScreen(viewModel: TaskDetailViewModel = hiltViewModel(), onDeleted: () -> Unit) {
    val state = viewModel.uiState
    var statusMenuExpanded by remember { mutableStateOf(false) }
    var addMenuExpanded by remember { mutableStateOf(false) }
    var showSubtaskForm by remember { mutableStateOf(false) }

    LaunchedEffect(state.isDeleted) { if (state.isDeleted) onDeleted() }

    Box(modifier = Modifier.fillMaxSize().safeDrawingPadding()) {
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
            state.task != null -> {
                val task = state.task
                var title by remember(task.id) { mutableStateOf(task.title) }
                var deadline by remember(task.id) { mutableStateOf(task.deadline ?: "") }
                var description by remember(task.id) { mutableStateOf(task.description) }

                Column(modifier = Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(16.dp)) {
                    task.parentStub?.let {
                        Text(
                            "Sub-task of ${it.title}",
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }

                    OutlinedTextField(
                        value = title,
                        onValueChange = { title = it },
                        label = { Text("Title") },
                        singleLine = true,
                        modifier = Modifier.fillMaxWidth().padding(top = 4.dp),
                        trailingIcon = {
                            AppOutlinedButton(onClick = { viewModel.setTitle(title) }) { Text("Save") }
                        },
                    )
                    Text(
                        "Created by ${task.createdBy.name}",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        modifier = Modifier.padding(top = 4.dp),
                    )
                    if (task.isOverdue) {
                        Text(
                            "Overdue — due ${task.deadline}",
                            color = MaterialTheme.colorScheme.error,
                            style = MaterialTheme.typography.bodySmall,
                            modifier = Modifier.padding(top = 4.dp),
                        )
                    }

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
                            TASK_STATUSES.forEach { status ->
                                DropdownMenuItem(
                                    text = { Text(status) },
                                    onClick = { statusMenuExpanded = false; viewModel.setStatus(status) },
                                )
                            }
                        }
                    }

                    OutlinedTextField(
                        value = deadline,
                        onValueChange = { deadline = it },
                        label = { Text("Deadline (YYYY-MM-DD)") },
                        singleLine = true,
                        modifier = Modifier.fillMaxWidth().padding(top = 12.dp),
                        trailingIcon = {
                            AppOutlinedButton(onClick = { viewModel.setDeadline(deadline.ifBlank { null }) }) { Text("Save") }
                        },
                    )

                    OutlinedTextField(
                        value = description,
                        onValueChange = { description = it },
                        label = { Text("Description") },
                        minLines = 3,
                        modifier = Modifier.fillMaxWidth().padding(top = 12.dp),
                    )
                    AppOutlinedButton(
                        onClick = { viewModel.setDescription(description) },
                        modifier = Modifier.padding(top = 4.dp),
                    ) { Text("Save description") }

                    Text("Assignees", style = MaterialTheme.typography.titleMedium, modifier = Modifier.padding(top = 20.dp))
                    task.assignees.forEach { assignee ->
                        Row(
                            modifier = Modifier.fillMaxWidth().padding(vertical = 4.dp),
                            verticalAlignment = Alignment.CenterVertically,
                        ) {
                            Text(assignee.employee.name, modifier = Modifier.weight(1f))
                            AppOutlinedButton(onClick = { viewModel.removeAssignee(assignee.employee.id) }) {
                                Text("Remove")
                            }
                        }
                    }

                    val assignedIds = task.assignees.map { it.employee.id }.toSet()
                    val candidates = state.assignableEmployees.filter { it.id !in assignedIds }
                    if (candidates.isNotEmpty()) {
                        Box(modifier = Modifier.padding(top = 8.dp)) {
                            AppOutlinedButton(onClick = { addMenuExpanded = true }) { Text("Add assignee") }
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

                    // A sub-task cannot itself have sub-tasks — matches the backend's
                    // one-level rule and TaskDetailView.vue's `isRootTask` gate.
                    if (task.parentStub == null) {
                        HorizontalDivider(modifier = Modifier.padding(vertical = 20.dp))
                        Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.fillMaxWidth()) {
                            Text("Sub-tasks", style = MaterialTheme.typography.titleMedium, modifier = Modifier.weight(1f))
                            AppOutlinedButton(onClick = { showSubtaskForm = !showSubtaskForm }) {
                                Text(if (showSubtaskForm) "Cancel" else "Add sub-task")
                            }
                        }

                        if (showSubtaskForm) {
                            SubtaskForm(
                                employees = state.assignableEmployees,
                                onCreate = { title2, description2, status2, deadline2, assigneeIds ->
                                    showSubtaskForm = false
                                    viewModel.createSubtask(title2, description2, status2, deadline2, assigneeIds)
                                },
                            )
                        }

                        if (state.subtasks.isEmpty()) {
                            Text(
                                "No sub-tasks yet.",
                                style = MaterialTheme.typography.bodySmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                                modifier = Modifier.padding(top = 8.dp),
                            )
                        } else {
                            state.subtasks.forEach { subtask ->
                                Row(
                                    modifier = Modifier.fillMaxWidth().padding(vertical = 6.dp),
                                    verticalAlignment = Alignment.CenterVertically,
                                ) {
                                    Text(subtask.title, modifier = Modifier.weight(1f))
                                    StatusBadge(
                                        subtask.status,
                                        tone = if (subtask.status == "DONE") BadgeTone.OK else BadgeTone.NEUTRAL,
                                    )
                                }
                            }
                        }
                    }

                    AppButton(
                        onClick = viewModel::delete,
                        colors = ButtonDefaults.buttonColors(containerColor = MaterialTheme.colorScheme.error),
                        modifier = Modifier.fillMaxWidth().padding(top = 24.dp),
                    ) { Text("Delete task") }

                    // Clears the system gesture-navigation strip so the last button on a
                    // short screen isn't swallowed by an edge swipe.
                    Spacer(Modifier.height(32.dp))
                }
            }
        }
    }
}

@Composable
private fun SubtaskForm(
    employees: List<EmployeeStub>,
    onCreate: (title: String, description: String, status: String, deadline: String?, assigneeIds: List<Int>) -> Unit,
) {
    val form = remember { TaskFormState() }
    Column(modifier = Modifier.padding(top = 12.dp)) {
        TaskFormFields(form, employees)
        AppOutlinedButton(
            onClick = {
                if (form.title.isNotBlank()) {
                    onCreate(form.title, form.description, form.status, form.deadline.ifBlank { null }, form.selectedAssignees.value.toList())
                }
            },
            modifier = Modifier.padding(top = 8.dp),
        ) { Text("Create sub-task") }
    }
}
