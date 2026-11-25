package com.officemanagement.attendance

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
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
import androidx.hilt.navigation.compose.hiltViewModel
import com.officemanagement.core.network.AttendanceItem
import com.officemanagement.core.network.PunchItem

@Composable
fun AdminAttendanceScreen(viewModel: AdminAttendanceViewModel = hiltViewModel()) {
    val state = viewModel.uiState
    var correcting by remember { mutableStateOf<Pair<AttendanceItem, PunchItem>?>(null) }

    Box(modifier = Modifier.fillMaxSize()) {
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
            state.rows.isEmpty() -> Text("No attendance records", modifier = Modifier.align(Alignment.Center))
            else -> LazyColumn(modifier = Modifier.fillMaxSize()) {
                items(state.rows, key = { it.id }) { row ->
                    Column(modifier = Modifier.fillMaxWidth().padding(16.dp)) {
                        Text(row.employeeName, style = MaterialTheme.typography.titleMedium)
                        Text(
                            "${row.date} · ${row.status} · ${row.workedSeconds / 60}m worked" +
                                if (row.needsReview) " · NEEDS REVIEW" else "",
                            style = MaterialTheme.typography.bodySmall,
                            color = if (row.needsReview) MaterialTheme.colorScheme.error else MaterialTheme.colorScheme.onSurface,
                        )
                        row.punches.forEach { punch ->
                            Text(
                                "Punch ${punch.sequence}: ${punch.checkInAt} → ${punch.checkOutAt ?: "open"}",
                                style = MaterialTheme.typography.bodySmall,
                                modifier = Modifier.fillMaxWidth().clickable { correcting = row to punch }.padding(top = 4.dp),
                            )
                        }
                    }
                    HorizontalDivider()
                }
            }
        }
    }

    correcting?.let { (attendance, punch) ->
        CorrectionDialog(
            punch = punch,
            onDismiss = { correcting = null },
            onSave = { checkIn, checkOut, note ->
                viewModel.correctPunch(attendance.id, punch.id, checkIn, checkOut, note)
                correcting = null
            },
        )
    }
}

@Composable
private fun CorrectionDialog(punch: PunchItem, onDismiss: () -> Unit, onSave: (String?, String?, String) -> Unit) {
    var checkIn by remember { mutableStateOf(punch.checkInAt) }
    var checkOut by remember { mutableStateOf(punch.checkOutAt ?: "") }
    var note by remember { mutableStateOf("") }

    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Correct punch") },
        text = {
            Column {
                OutlinedTextField(
                    value = checkIn,
                    onValueChange = { checkIn = it },
                    label = { Text("Check-in (ISO 8601)") },
                    singleLine = true,
                )
                OutlinedTextField(
                    value = checkOut,
                    onValueChange = { checkOut = it },
                    label = { Text("Check-out (ISO 8601, blank = open)") },
                    singleLine = true,
                    modifier = Modifier.padding(top = 8.dp),
                )
                OutlinedTextField(
                    value = note,
                    onValueChange = { note = it },
                    label = { Text("Note") },
                    modifier = Modifier.padding(top = 8.dp),
                )
            }
        },
        confirmButton = {
            OutlinedButton(onClick = { onSave(checkIn, checkOut, note) }) { Text("Save") }
        },
        dismissButton = { OutlinedButton(onClick = onDismiss) { Text("Cancel") } },
    )
}
