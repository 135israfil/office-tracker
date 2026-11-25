package com.officemanagement.events
import com.officemanagement.ui.components.AppOutlinedButton
import com.officemanagement.ui.components.AppButton

import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardOptions
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
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun EventDetailScreen(viewModel: EventDetailViewModel = hiltViewModel(), onDeleted: () -> Unit) {
    val state = viewModel.uiState
    var statusMenuExpanded by remember { mutableStateOf(false) }
    var leadMenuExpanded by remember { mutableStateOf(false) }
    var documentMenuExpanded by remember { mutableStateOf(false) }
    var financialMenuExpanded by remember { mutableStateOf(false) }

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
            state.event != null -> {
                val event = state.event
                val canCoordinate = state.isOwner || state.isAdmin
                var title by remember(event.id) { mutableStateOf(event.title) }
                var agency by remember(event.id) { mutableStateOf(event.agencyName) }
                var venue by remember(event.id) { mutableStateOf(event.venueName) }
                var alertOn by remember(event.id) { mutableStateOf(event.alertOn ?: "") }
                var setupText by remember(event.id) { mutableStateOf(event.setup) }
                var budget by remember(event.id) { mutableStateOf(event.budget ?: "") }

                Column(modifier = Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(16.dp)) {
                    Text(event.title, style = MaterialTheme.typography.headlineSmall)
                    event.lastAdminView?.let {
                        Text(
                            "Last viewed by an admin (${it.admin ?: "unknown"}) on ${it.at}.",
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }

                    OutlinedTextField(
                        value = title,
                        onValueChange = { title = it },
                        label = { Text("Title") },
                        singleLine = true,
                        enabled = state.isOwner,
                        modifier = Modifier.fillMaxWidth().padding(top = 12.dp),
                        trailingIcon = if (state.isOwner) {
                            { AppOutlinedButton(onClick = { viewModel.setTitle(title) }) { Text("Save") } }
                        } else null,
                    )

                    Text("Booking", style = MaterialTheme.typography.labelLarge, modifier = Modifier.padding(top = 16.dp))
                    OutlinedTextField(
                        value = agency,
                        onValueChange = { agency = it },
                        label = { Text("Agency name") },
                        singleLine = true,
                        enabled = state.isOwner,
                        modifier = Modifier.fillMaxWidth().padding(top = 8.dp),
                        trailingIcon = if (state.isOwner) {
                            { AppOutlinedButton(onClick = { viewModel.setAgencyName(agency) }) { Text("Save") } }
                        } else null,
                    )
                    OutlinedTextField(
                        value = venue,
                        onValueChange = { venue = it },
                        label = { Text("Venue name") },
                        singleLine = true,
                        enabled = state.isOwner,
                        modifier = Modifier.fillMaxWidth().padding(top = 8.dp),
                        trailingIcon = if (state.isOwner) {
                            { AppOutlinedButton(onClick = { viewModel.setVenueName(venue) }) { Text("Save") } }
                        } else null,
                    )

                    ExposedDropdownMenuBox(
                        expanded = leadMenuExpanded,
                        onExpandedChange = { if (canCoordinate) leadMenuExpanded = it },
                        modifier = Modifier.padding(top = 8.dp),
                    ) {
                        OutlinedTextField(
                            value = event.assignedLead?.name ?: "Unassigned",
                            onValueChange = {},
                            readOnly = true,
                            enabled = canCoordinate,
                            label = { Text("Assigned lead") },
                            trailingIcon = { ExposedDropdownMenuDefaults.TrailingIcon(expanded = leadMenuExpanded) },
                            modifier = Modifier.fillMaxWidth().menuAnchor(MenuAnchorType.PrimaryNotEditable),
                        )
                        DropdownMenu(expanded = leadMenuExpanded, onDismissRequest = { leadMenuExpanded = false }) {
                            DropdownMenuItem(
                                text = { Text("Unassigned") },
                                onClick = { leadMenuExpanded = false; viewModel.setAssignedLead(null) },
                            )
                            state.assignableEmployees.forEach { employee ->
                                DropdownMenuItem(
                                    text = { Text(employee.name) },
                                    onClick = { leadMenuExpanded = false; viewModel.setAssignedLead(employee.id) },
                                )
                            }
                        }
                    }

                    ExposedDropdownMenuBox(
                        expanded = statusMenuExpanded,
                        onExpandedChange = { if (canCoordinate) statusMenuExpanded = it },
                        modifier = Modifier.padding(top = 8.dp),
                    ) {
                        OutlinedTextField(
                            value = bookingStatusLabel(event.bookingStatus),
                            onValueChange = {},
                            readOnly = true,
                            enabled = canCoordinate,
                            label = { Text("Status") },
                            trailingIcon = { ExposedDropdownMenuDefaults.TrailingIcon(expanded = statusMenuExpanded) },
                            modifier = Modifier.fillMaxWidth().menuAnchor(MenuAnchorType.PrimaryNotEditable),
                        )
                        DropdownMenu(expanded = statusMenuExpanded, onDismissRequest = { statusMenuExpanded = false }) {
                            BOOKING_STATUSES.forEach { value ->
                                DropdownMenuItem(
                                    text = { Text(bookingStatusLabel(value)) },
                                    onClick = { statusMenuExpanded = false; viewModel.setBookingStatus(value) },
                                )
                            }
                        }
                    }

                    OutlinedTextField(
                        value = alertOn,
                        onValueChange = { alertOn = it },
                        label = { Text("Alert on (YYYY-MM-DD)") },
                        singleLine = true,
                        enabled = state.isOwner,
                        modifier = Modifier.fillMaxWidth().padding(top = 8.dp),
                        trailingIcon = if (state.isOwner) {
                            { AppOutlinedButton(onClick = { viewModel.setAlertOn(alertOn.ifBlank { null }) }) { Text("Save") } }
                        } else null,
                    )

                    Text("Setup", style = MaterialTheme.typography.labelLarge, modifier = Modifier.padding(top = 16.dp))
                    // Plain text, not the web app's rich-text editor — a mobile rich-text
                    // component is disproportionate work for one field; revisit only if missed.
                    OutlinedTextField(
                        value = setupText,
                        onValueChange = { setupText = it },
                        label = { Text("Setup notes") },
                        enabled = state.isOwner,
                        modifier = Modifier.fillMaxWidth().padding(top = 8.dp),
                        minLines = 4,
                    )
                    if (state.isOwner) {
                        AppOutlinedButton(
                            onClick = { viewModel.updateSetup(setupText) },
                            modifier = Modifier.padding(top = 8.dp),
                        ) { Text("Save notes") }
                    }

                    state.saveError?.let {
                        Text(it, color = MaterialTheme.colorScheme.error, modifier = Modifier.padding(top = 8.dp))
                    }

                    if (state.isAdmin) {
                        HorizontalDivider(modifier = Modifier.padding(vertical = 20.dp))
                        Text("Financials", style = MaterialTheme.typography.titleMedium)
                        Text(
                            "Admin-only: set by any admin, regardless of who owns the event.",
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                        OutlinedTextField(
                            value = budget,
                            onValueChange = { budget = it },
                            label = { Text("Budget") },
                            singleLine = true,
                            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
                            modifier = Modifier.fillMaxWidth().padding(top = 8.dp),
                            trailingIcon = {
                                AppOutlinedButton(
                                    onClick = {
                                        viewModel.setFinancials(budget.ifBlank { null }, event.documentStatus, event.financialStatus)
                                    },
                                ) { Text("Save") }
                            },
                        )
                        ExposedDropdownMenuBox(
                            expanded = documentMenuExpanded,
                            onExpandedChange = { documentMenuExpanded = it },
                            modifier = Modifier.padding(top = 8.dp),
                        ) {
                            OutlinedTextField(
                                value = event.documentStatus?.let { documentStatusLabel(it) } ?: "Not set",
                                onValueChange = {},
                                readOnly = true,
                                label = { Text("Document status") },
                                trailingIcon = { ExposedDropdownMenuDefaults.TrailingIcon(expanded = documentMenuExpanded) },
                                modifier = Modifier.fillMaxWidth().menuAnchor(MenuAnchorType.PrimaryNotEditable),
                            )
                            DropdownMenu(expanded = documentMenuExpanded, onDismissRequest = { documentMenuExpanded = false }) {
                                DOCUMENT_STATUSES.forEach { value ->
                                    DropdownMenuItem(
                                        text = { Text(documentStatusLabel(value)) },
                                        onClick = {
                                            documentMenuExpanded = false
                                            viewModel.setFinancials(event.budget, value, event.financialStatus)
                                        },
                                    )
                                }
                            }
                        }
                        ExposedDropdownMenuBox(
                            expanded = financialMenuExpanded,
                            onExpandedChange = { financialMenuExpanded = it },
                            modifier = Modifier.padding(top = 8.dp),
                        ) {
                            OutlinedTextField(
                                value = event.financialStatus?.let { financialStatusLabel(it) } ?: "Not set",
                                onValueChange = {},
                                readOnly = true,
                                label = { Text("Financial status") },
                                trailingIcon = { ExposedDropdownMenuDefaults.TrailingIcon(expanded = financialMenuExpanded) },
                                modifier = Modifier.fillMaxWidth().menuAnchor(MenuAnchorType.PrimaryNotEditable),
                            )
                            DropdownMenu(expanded = financialMenuExpanded, onDismissRequest = { financialMenuExpanded = false }) {
                                FINANCIAL_STATUSES.forEach { value ->
                                    DropdownMenuItem(
                                        text = { Text(financialStatusLabel(value)) },
                                        onClick = {
                                            financialMenuExpanded = false
                                            viewModel.setFinancials(event.budget, event.documentStatus, value)
                                        },
                                    )
                                }
                            }
                        }
                    }

                    if (state.isOwner) {
                        AppButton(
                            onClick = viewModel::delete,
                            colors = ButtonDefaults.buttonColors(containerColor = MaterialTheme.colorScheme.error),
                            modifier = Modifier.fillMaxWidth().padding(top = 24.dp),
                        ) { Text("Delete event") }
                    }

                    // Clears the system gesture-navigation strip so the last button on a
                    // short screen isn't swallowed by an edge swipe.
                    Spacer(Modifier.height(32.dp))
                }
            }
        }
    }
}
