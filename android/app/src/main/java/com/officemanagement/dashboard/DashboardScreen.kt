package com.officemanagement.dashboard
import com.officemanagement.ui.components.AppOutlinedButton

import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import com.officemanagement.ui.components.StatTile

/** Admin home — §20's "today's attendance + PC status" panels. The web app also shows
 * a searchable employee-roster table here; on a phone that belongs on the dedicated
 * Employees screen instead of a cramped table, so it isn't duplicated here. */
@Composable
fun DashboardScreen(viewModel: DashboardViewModel = hiltViewModel()) {
    val state = viewModel.uiState

    Box(modifier = Modifier.fillMaxSize()) {
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
            state.dashboard != null -> Column(modifier = Modifier.fillMaxWidth().padding(20.dp)) {
                val attendance = state.dashboard.attendance
                val computers = state.dashboard.computers

                SectionLabel("Attendance")
                if (!attendance.isWorkingDay) {
                    Text(
                        "Not a working day — weekend or holiday.",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        modifier = Modifier.padding(top = 4.dp),
                    )
                }
                val tileModifier = Modifier.fillMaxWidth().padding(top = 10.dp)
                StatTile("Employees", "${attendance.employees}", modifier = tileModifier)
                StatTile("Present", "${attendance.present}", modifier = tileModifier)
                StatTile("Late", "${attendance.late}", modifier = tileModifier)
                StatTile("Absent", "${attendance.absent}", modifier = tileModifier)
                StatTile("Leave", "${attendance.leave}", modifier = tileModifier)
                StatTile(
                    "Not recorded",
                    "${attendance.notRecorded}",
                    hint = "not arrived yet",
                    modifier = tileModifier,
                )

                SectionLabel("PC status", modifier = Modifier.padding(top = 22.dp))
                StatTile("Online", "${computers.online}", hint = "active + idle", modifier = tileModifier)
                StatTile("Active", "${computers.active}", modifier = tileModifier)
                StatTile("Idle", "${computers.idle}", modifier = tileModifier)
                StatTile("Offline", "${computers.offline}", modifier = tileModifier)
                if (computers.unregistered > 0) {
                    StatTile("Awaiting enrolment", "${computers.unregistered}", modifier = tileModifier)
                }
            }
        }
    }
}

/** Matches App.vue's `h3` — a small-caps section label above a block of content. */
@Composable
fun SectionLabel(text: String, modifier: Modifier = Modifier) {
    Text(
        text.uppercase(),
        style = MaterialTheme.typography.labelSmall,
        color = MaterialTheme.colorScheme.onSurfaceVariant,
        modifier = modifier,
    )
}
