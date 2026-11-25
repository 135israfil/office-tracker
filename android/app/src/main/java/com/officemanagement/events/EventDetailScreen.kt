package com.officemanagement.events

import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
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

private val BOOKING_STATUSES = listOf("ON_COMMUNICATION", "LOCKED", "DONE")

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun EventDetailScreen(viewModel: EventDetailViewModel = hiltViewModel(), onDeleted: () -> Unit) {
    val state = viewModel.uiState
    var statusMenuExpanded by remember { mutableStateOf(false) }

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
            state.event != null -> {
                val event = state.event
                var setupText by remember(event.id) { mutableStateOf(event.setup) }

                Column(modifier = Modifier.fillMaxSize().padding(16.dp)) {
                    Text(event.title, style = MaterialTheme.typography.headlineSmall)
                    Text("${event.agencyName} · ${event.venueName}", style = MaterialTheme.typography.bodyMedium)
                    Text("Owner: ${event.owner.name}", style = MaterialTheme.typography.bodySmall)

                    ExposedDropdownMenuBox(
                        expanded = statusMenuExpanded,
                        onExpandedChange = { statusMenuExpanded = it },
                        modifier = Modifier.padding(top = 16.dp),
                    ) {
                        OutlinedTextField(
                            value = event.bookingStatus,
                            onValueChange = {},
                            readOnly = true,
                            label = { Text("Booking status") },
                            trailingIcon = { ExposedDropdownMenuDefaults.TrailingIcon(expanded = statusMenuExpanded) },
                            modifier = Modifier.fillMaxWidth().menuAnchor(MenuAnchorType.PrimaryNotEditable),
                        )
                        DropdownMenu(expanded = statusMenuExpanded, onDismissRequest = { statusMenuExpanded = false }) {
                            BOOKING_STATUSES.forEach { status ->
                                DropdownMenuItem(
                                    text = { Text(status) },
                                    onClick = { statusMenuExpanded = false; viewModel.setBookingStatus(status) },
                                )
                            }
                        }
                    }

                    // Plain text, not the web app's rich-text editor — a mobile rich-text
                    // component is disproportionate work for one field (see the plan's
                    // screen-mapping notes); revisit only if this is actually missed.
                    OutlinedTextField(
                        value = setupText,
                        onValueChange = { setupText = it },
                        label = { Text("Setup notes") },
                        modifier = Modifier.fillMaxWidth().padding(top = 16.dp),
                        minLines = 4,
                    )
                    OutlinedButton(
                        onClick = { viewModel.updateSetup(setupText) },
                        modifier = Modifier.padding(top = 8.dp),
                    ) { Text("Save notes") }

                    if (event.budget != null || event.documentStatus != null || event.financialStatus != null) {
                        Text(
                            "Budget: ${event.budget ?: "—"} · ${event.documentStatus ?: ""} · ${event.financialStatus ?: ""}",
                            style = MaterialTheme.typography.bodySmall,
                            modifier = Modifier.padding(top = 16.dp),
                        )
                    }

                    Button(
                        onClick = viewModel::delete,
                        colors = ButtonDefaults.buttonColors(containerColor = MaterialTheme.colorScheme.error),
                        modifier = Modifier.fillMaxWidth().padding(top = 24.dp),
                    ) { Text("Delete event") }
                }
            }
        }
    }
}
