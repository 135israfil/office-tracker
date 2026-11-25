package com.officemanagement.events
import com.officemanagement.ui.components.AppOutlinedButton

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.ExposedDropdownMenuBox
import androidx.compose.material3.ExposedDropdownMenuDefaults
import androidx.compose.material3.FloatingActionButton
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.MenuAnchorType
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
import com.officemanagement.core.network.EventItem
import com.officemanagement.ui.components.StatusBadge

@Composable
fun EventsScreen(viewModel: EventsViewModel = hiltViewModel(), onOpenEvent: (Int) -> Unit) {
    val state = viewModel.uiState
    var showCreate by remember { mutableStateOf(false) }

    Scaffold(
        floatingActionButton = {
            FloatingActionButton(onClick = { showCreate = true }) {
                Icon(Icons.Default.Add, contentDescription = "New event")
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
                state.events.isEmpty() -> Text("No events", modifier = Modifier.align(Alignment.Center))
                else -> LazyColumn(modifier = Modifier.fillMaxSize()) {
                    items(state.events, key = { it.id }) { event ->
                        EventRow(event, onClick = { onOpenEvent(event.id) })
                        HorizontalDivider()
                    }
                }
            }
        }
    }

    if (showCreate) {
        NewEventDialog(
            employees = state.employees,
            onDismiss = { showCreate = false },
            onCreate = { title, agency, venue, assignedLeadId, status, alertOn ->
                showCreate = false
                viewModel.createEvent(title, agency, venue, assignedLeadId, status, alertOn) {}
            },
        )
    }
}

@Composable
private fun EventRow(event: EventItem, onClick: () -> Unit) {
    Column(modifier = Modifier.fillMaxWidth().clickable(onClick = onClick).padding(16.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(event.title, style = MaterialTheme.typography.titleMedium, modifier = Modifier.weight(1f))
            StatusBadge(bookingStatusLabel(event.bookingStatus), tone = bookingStatusTone(event.bookingStatus))
        }
        Text(
            event.agencyName,
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            modifier = Modifier.padding(top = 4.dp),
        )
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun NewEventDialog(
    employees: List<EmployeeStub>,
    onDismiss: () -> Unit,
    onCreate: (title: String, agency: String, venue: String, assignedLeadId: Int?, status: String, alertOn: String?) -> Unit,
) {
    var title by remember { mutableStateOf("") }
    var agency by remember { mutableStateOf("") }
    var venue by remember { mutableStateOf("") }
    var assignedLead by remember { mutableStateOf<EmployeeStub?>(null) }
    var status by remember { mutableStateOf("ON_COMMUNICATION") }
    var alertOn by remember { mutableStateOf("") }
    var leadMenuExpanded by remember { mutableStateOf(false) }
    var statusMenuExpanded by remember { mutableStateOf(false) }

    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("New event") },
        text = {
            Column {
                OutlinedTextField(value = title, onValueChange = { title = it }, label = { Text("Title") }, singleLine = true)
                OutlinedTextField(
                    value = agency,
                    onValueChange = { agency = it },
                    label = { Text("Agency") },
                    singleLine = true,
                    modifier = Modifier.padding(top = 8.dp),
                )
                OutlinedTextField(
                    value = venue,
                    onValueChange = { venue = it },
                    label = { Text("Venue") },
                    singleLine = true,
                    modifier = Modifier.padding(top = 8.dp),
                )
                ExposedDropdownMenuBox(
                    expanded = leadMenuExpanded,
                    onExpandedChange = { leadMenuExpanded = it },
                    modifier = Modifier.padding(top = 8.dp),
                ) {
                    OutlinedTextField(
                        value = assignedLead?.name ?: "Unassigned",
                        onValueChange = {},
                        readOnly = true,
                        label = { Text("Assigned lead") },
                        trailingIcon = { ExposedDropdownMenuDefaults.TrailingIcon(expanded = leadMenuExpanded) },
                        modifier = Modifier.fillMaxWidth().menuAnchor(MenuAnchorType.PrimaryNotEditable),
                    )
                    DropdownMenu(expanded = leadMenuExpanded, onDismissRequest = { leadMenuExpanded = false }) {
                        DropdownMenuItem(text = { Text("Unassigned") }, onClick = { assignedLead = null; leadMenuExpanded = false })
                        employees.forEach { employee ->
                            DropdownMenuItem(
                                text = { Text(employee.name) },
                                onClick = { assignedLead = employee; leadMenuExpanded = false },
                            )
                        }
                    }
                }
                ExposedDropdownMenuBox(
                    expanded = statusMenuExpanded,
                    onExpandedChange = { statusMenuExpanded = it },
                    modifier = Modifier.padding(top = 8.dp),
                ) {
                    OutlinedTextField(
                        value = bookingStatusLabel(status),
                        onValueChange = {},
                        readOnly = true,
                        label = { Text("Status") },
                        trailingIcon = { ExposedDropdownMenuDefaults.TrailingIcon(expanded = statusMenuExpanded) },
                        modifier = Modifier.fillMaxWidth().menuAnchor(MenuAnchorType.PrimaryNotEditable),
                    )
                    DropdownMenu(expanded = statusMenuExpanded, onDismissRequest = { statusMenuExpanded = false }) {
                        BOOKING_STATUSES.forEach { value ->
                            DropdownMenuItem(
                                text = { Text(bookingStatusLabel(value)) },
                                onClick = { status = value; statusMenuExpanded = false },
                            )
                        }
                    }
                }
                OutlinedTextField(
                    value = alertOn,
                    onValueChange = { alertOn = it },
                    label = { Text("Alert on (YYYY-MM-DD)") },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth().padding(top = 8.dp),
                )
            }
        },
        confirmButton = {
            AppOutlinedButton(
                onClick = {
                    if (title.isNotBlank()) onCreate(title, agency, venue, assignedLead?.id, status, alertOn.ifBlank { null })
                },
            ) { Text("Create") }
        },
        dismissButton = { AppOutlinedButton(onClick = onDismiss) { Text("Cancel") } },
    )
}
