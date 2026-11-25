package com.officemanagement.dashboard

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

/** Admin home — §20's "today's attendance + PC status" panels, in brief. Richer detail
 * (the employee roster, search) lives on the Employees screen instead. */
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
                OutlinedButton(onClick = viewModel::load, modifier = Modifier.padding(top = 12.dp)) {
                    Text("Retry")
                }
            }
            state.dashboard != null -> Column(modifier = Modifier.fillMaxWidth().padding(24.dp)) {
                val attendance = state.dashboard.attendance
                val computers = state.dashboard.computers
                Text("Today's attendance", style = MaterialTheme.typography.titleMedium)
                Text("${attendance.present} present · ${attendance.late} late · ${attendance.absent} absent · ${attendance.leave} on leave")
                Text(
                    "PC status",
                    style = MaterialTheme.typography.titleMedium,
                    modifier = Modifier.padding(top = 16.dp),
                )
                Text("${computers.online} online (${computers.active} active, ${computers.idle} idle) · ${computers.offline} offline")
            }
        }
    }
}
