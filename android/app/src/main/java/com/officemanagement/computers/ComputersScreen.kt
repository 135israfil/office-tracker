package com.officemanagement.computers
import com.officemanagement.ui.components.AppOutlinedButton

import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Computer
import androidx.compose.material.icons.filled.PhoneAndroid
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import com.officemanagement.core.network.ComputerListItem
import com.officemanagement.ui.components.BadgeTone
import com.officemanagement.ui.components.StatusBadge

@Composable
fun ComputersScreen(viewModel: ComputersViewModel = hiltViewModel()) {
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
            state.computers.isEmpty() -> Text("No computers enrolled", modifier = Modifier.align(Alignment.Center))
            else -> LazyColumn(modifier = Modifier.fillMaxSize()) {
                items(state.computers, key = { it.id }) { computer ->
                    ComputerRow(computer)
                    HorizontalDivider()
                }
            }
        }
    }
}

@Composable
private fun ComputerRow(computer: ComputerListItem) {
    Row(
        modifier = Modifier.fillMaxWidth().padding(16.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Icon(
            imageVector = if (computer.deviceType == "ANDROID") Icons.Default.PhoneAndroid else Icons.Default.Computer,
            contentDescription = null,
            modifier = Modifier.padding(end = 12.dp),
        )
        Column(modifier = Modifier.weight(1f)) {
            Text(computer.computerName, style = MaterialTheme.typography.titleMedium)
            Text(
                "${computer.employeeName} · ${computer.operatingSystem}",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
        StatusBadge(
            computer.status,
            tone = if (computer.status == "ONLINE" || computer.status == "IDLE") BadgeTone.OK else BadgeTone.DANGER,
        )
    }
}
