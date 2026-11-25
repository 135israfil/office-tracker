package com.officemanagement.tasks

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Checkbox
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.ExposedDropdownMenuBox
import androidx.compose.material3.ExposedDropdownMenuDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.MenuAnchorType
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.officemanagement.core.network.EmployeeStub

val TASK_STATUSES = listOf("TODO", "IN_PROGRESS", "BLOCKED", "DONE", "CANCELLED")

/** The field set frontend/src/views/TasksView.vue's "New task" form and
 * TaskDetailView.vue's "Add sub-task" form both use — title/status/deadline/
 * description/assignees — pulled out once so a task and a sub-task never drift apart. */
class TaskFormState {
    var title by mutableStateOf("")
    var description by mutableStateOf("")
    var status by mutableStateOf("TODO")
    var deadline by mutableStateOf("")
    val selectedAssignees = mutableStateOf(setOf<Int>())
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun TaskFormFields(state: TaskFormState, employees: List<EmployeeStub>) {
    var statusExpanded by remember { mutableStateOf(false) }

    Column {
        OutlinedTextField(
            value = state.title,
            onValueChange = { state.title = it },
            label = { Text("Title") },
            singleLine = true,
            modifier = Modifier.fillMaxWidth(),
        )
        OutlinedTextField(
            value = state.description,
            onValueChange = { state.description = it },
            label = { Text("Description") },
            modifier = Modifier.fillMaxWidth().padding(top = 8.dp),
        )
        ExposedDropdownMenuBox(
            expanded = statusExpanded,
            onExpandedChange = { statusExpanded = it },
            modifier = Modifier.padding(top = 8.dp),
        ) {
            OutlinedTextField(
                value = state.status,
                onValueChange = {},
                readOnly = true,
                label = { Text("Status") },
                trailingIcon = { ExposedDropdownMenuDefaults.TrailingIcon(expanded = statusExpanded) },
                modifier = Modifier.fillMaxWidth().menuAnchor(MenuAnchorType.PrimaryNotEditable),
            )
            DropdownMenu(expanded = statusExpanded, onDismissRequest = { statusExpanded = false }) {
                TASK_STATUSES.forEach { status ->
                    DropdownMenuItem(text = { Text(status) }, onClick = { state.status = status; statusExpanded = false })
                }
            }
        }
        OutlinedTextField(
            value = state.deadline,
            onValueChange = { state.deadline = it },
            label = { Text("Deadline (YYYY-MM-DD)") },
            singleLine = true,
            modifier = Modifier.fillMaxWidth().padding(top = 8.dp),
        )
        if (employees.isNotEmpty()) {
            Text("Assignees", style = MaterialTheme.typography.labelMedium, modifier = Modifier.padding(top = 12.dp))
            employees.forEach { employee ->
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Checkbox(
                        checked = employee.id in state.selectedAssignees.value,
                        onCheckedChange = { checked ->
                            state.selectedAssignees.value =
                                if (checked) state.selectedAssignees.value + employee.id else state.selectedAssignees.value - employee.id
                        },
                    )
                    Text(employee.name)
                }
            }
        }
    }
}
