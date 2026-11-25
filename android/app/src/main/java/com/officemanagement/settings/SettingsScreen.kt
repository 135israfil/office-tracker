package com.officemanagement.settings

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.rememberScrollState
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.FilterChip
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel

private val DAY_LABELS = listOf("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")

@Composable
fun SettingsScreen(viewModel: SettingsViewModel = hiltViewModel()) {
    val state = viewModel.uiState
    var showAddHoliday by remember { mutableStateOf(false) }

    Box(modifier = Modifier.fillMaxSize()) {
        when {
            state.isLoading -> CircularProgressIndicator(modifier = Modifier.align(Alignment.Center))
            state.settings != null -> {
                val settings = state.settings
                Column(modifier = Modifier.fillMaxSize().padding(16.dp)) {
                    if (state.error != null) {
                        Text(state.error, color = MaterialTheme.colorScheme.error, modifier = Modifier.padding(bottom = 8.dp))
                    }

                    Text("Weekend days", style = MaterialTheme.typography.titleMedium)
                    Row(
                        modifier = Modifier.padding(top = 8.dp, bottom = 16.dp).horizontalScroll(rememberScrollState()),
                        horizontalArrangement = Arrangement.spacedBy(6.dp),
                    ) {
                        DAY_LABELS.forEachIndexed { index, label ->
                            FilterChip(
                                selected = index in settings.weekendDays,
                                onClick = { viewModel.toggleWeekendDay(index) },
                                label = { Text(label) },
                            )
                        }
                    }

                    Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.fillMaxWidth()) {
                        Text("Require check-in inside radius", modifier = Modifier.weight(1f))
                        Switch(
                            checked = settings.requireCheckInInsideRadius,
                            onCheckedChange = viewModel::setRequireInsideRadius,
                        )
                    }
                    NumberField(
                        label = "Geofence radius (metres)",
                        value = settings.radiusMeters,
                        onCommit = viewModel::setRadius,
                    )
                    NumberField(
                        label = "Activity retention (days)",
                        value = settings.activityRetentionDays,
                        onCommit = viewModel::setRetentionDays,
                    )

                    Row(
                        verticalAlignment = Alignment.CenterVertically,
                        modifier = Modifier.fillMaxWidth().padding(top = 24.dp, bottom = 8.dp),
                    ) {
                        Text("Holidays", style = MaterialTheme.typography.titleMedium, modifier = Modifier.weight(1f))
                        OutlinedButton(onClick = { showAddHoliday = true }) { Text("Add") }
                    }
                    state.holidays.forEach { holiday ->
                        Row(
                            modifier = Modifier.fillMaxWidth().padding(vertical = 4.dp),
                            verticalAlignment = Alignment.CenterVertically,
                        ) {
                            Text("${holiday.date} — ${holiday.name}", modifier = Modifier.weight(1f))
                            OutlinedButton(onClick = { viewModel.deleteHoliday(holiday.id) }) { Text("Delete") }
                        }
                        HorizontalDivider()
                    }
                }
            }
        }
    }

    if (showAddHoliday) {
        AddHolidayDialog(
            onDismiss = { showAddHoliday = false },
            onAdd = { date, name ->
                showAddHoliday = false
                viewModel.addHoliday(date, name)
            },
        )
    }
}

@Composable
private fun NumberField(label: String, value: Int, onCommit: (Int) -> Unit) {
    var text by remember(value) { mutableStateOf(value.toString()) }
    OutlinedTextField(
        value = text,
        onValueChange = { text = it },
        label = { Text(label) },
        singleLine = true,
        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
        modifier = Modifier.fillMaxWidth().padding(top = 12.dp),
        trailingIcon = {
            OutlinedButton(onClick = { text.toIntOrNull()?.let(onCommit) }) { Text("Save") }
        },
    )
}

@Composable
private fun AddHolidayDialog(onDismiss: () -> Unit, onAdd: (String, String) -> Unit) {
    var date by remember { mutableStateOf("") }
    var name by remember { mutableStateOf("") }

    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Add holiday") },
        text = {
            Column {
                OutlinedTextField(value = date, onValueChange = { date = it }, label = { Text("Date (YYYY-MM-DD)") }, singleLine = true)
                OutlinedTextField(
                    value = name,
                    onValueChange = { name = it },
                    label = { Text("Name") },
                    singleLine = true,
                    modifier = Modifier.padding(top = 8.dp),
                )
            }
        },
        confirmButton = {
            OutlinedButton(onClick = { if (date.isNotBlank() && name.isNotBlank()) onAdd(date, name) }) { Text("Add") }
        },
        dismissButton = { OutlinedButton(onClick = onDismiss) { Text("Cancel") } },
    )
}
