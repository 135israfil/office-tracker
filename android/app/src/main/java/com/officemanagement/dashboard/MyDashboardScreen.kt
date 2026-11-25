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

/** Employee home — §24's own-data-only summary, in brief (name, department, leave
 * balance). The activity breakdown and own computers list are a later phase. */
@Composable
fun MyDashboardScreen(viewModel: MyDashboardViewModel = hiltViewModel()) {
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
            state.summary != null -> Column(modifier = Modifier.fillMaxWidth().padding(24.dp)) {
                val employee = state.summary.employee
                val leave = state.summary.leave
                Text(employee.name, style = MaterialTheme.typography.titleLarge)
                Text("${employee.designation} · ${employee.department}")
                Text(
                    "Leave: ${leave.remaining} of ${leave.total} remaining",
                    modifier = Modifier.padding(top = 16.dp),
                )
            }
        }
    }
}
