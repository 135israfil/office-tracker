package com.officemanagement.activity
import com.officemanagement.ui.components.AppOutlinedButton

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.ExposedDropdownMenuBox
import androidx.compose.material3.ExposedDropdownMenuDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.MenuAnchorType
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.DropdownMenu
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
import com.officemanagement.core.network.ActivityBlock

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ActivityScreen(viewModel: ActivityViewModel = hiltViewModel()) {
    val state = viewModel.uiState
    var dropdownExpanded by remember { mutableStateOf(false) }

    Column(modifier = Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(16.dp)) {
        if (state.employees.isNotEmpty()) {
            val selectedName = state.employees.firstOrNull { it.id == state.selectedEmployeeId }?.name ?: ""
            ExposedDropdownMenuBox(
                expanded = dropdownExpanded,
                onExpandedChange = { dropdownExpanded = it },
            ) {
                OutlinedTextField(
                    value = selectedName,
                    onValueChange = {},
                    readOnly = true,
                    label = { Text("Employee") },
                    trailingIcon = { ExposedDropdownMenuDefaults.TrailingIcon(expanded = dropdownExpanded) },
                    modifier = Modifier.fillMaxWidth().menuAnchor(MenuAnchorType.PrimaryNotEditable),
                )
                DropdownMenu(expanded = dropdownExpanded, onDismissRequest = { dropdownExpanded = false }) {
                    state.employees.forEach { employee ->
                        DropdownMenuItem(
                            text = { Text(employee.name) },
                            onClick = {
                                dropdownExpanded = false
                                viewModel.selectEmployee(employee.id)
                            },
                        )
                    }
                }
            }
        }

        Box(modifier = Modifier.fillMaxWidth().padding(top = 16.dp)) {
            when {
                // A verticalScroll parent gives unbounded height, so centering inside a
                // fillMaxSize() Box here would crash — a fixed height box instead, same
                // as a loading/error state anywhere else on a scrollable screen.
                state.isLoading -> Box(modifier = Modifier.fillMaxWidth().padding(32.dp)) {
                    CircularProgressIndicator(modifier = Modifier.align(Alignment.Center))
                }
                state.error != null -> Column(horizontalAlignment = Alignment.CenterHorizontally, modifier = Modifier.fillMaxWidth()) {
                    Text(state.error, color = MaterialTheme.colorScheme.error)
                    AppOutlinedButton(onClick = viewModel::retry, modifier = Modifier.padding(top = 12.dp)) {
                        Text("Retry")
                    }
                }
                state.summary != null -> Column(modifier = Modifier.fillMaxWidth()) {
                    ActivityBlockCard(title = "PC", block = state.summary.activity)
                    state.summary.phoneActivity?.let {
                        ActivityBlockCard(title = "Phone", block = it, modifier = Modifier.padding(top = 12.dp))
                    }
                }
            }
        }
    }
}

@Composable
private fun ActivityBlockCard(title: String, block: ActivityBlock, modifier: Modifier = Modifier) {
    Card(
        modifier = modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
        border = BorderStroke(1.dp, MaterialTheme.colorScheme.outlineVariant),
        elevation = CardDefaults.cardElevation(defaultElevation = 0.dp),
    ) {
        Column(modifier = Modifier.padding(16.dp)) {
            Text(title, style = MaterialTheme.typography.titleMedium)
            Text(
                "${duration(block.activeSeconds)} active · ${duration(block.idleSeconds)} idle",
                style = MaterialTheme.typography.bodyMedium,
                modifier = Modifier.padding(top = 2.dp),
            )
            block.topApplications.firstOrNull()?.let {
                Text(
                    "Top app: ${it.name} (${duration(it.seconds)})",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    modifier = Modifier.padding(top = 8.dp),
                )
            }
            block.topWebsites.firstOrNull()?.let {
                Text(
                    "Top site: ${it.name} (${duration(it.seconds)})",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
        }
    }
}

/** Mirrors frontend/src/lib/format.js's duration() so the two clients never disagree
 * about how long an hour is. */
private fun duration(seconds: Int): String {
    val total = seconds.coerceAtLeast(0)
    val hours = total / 3600
    val minutes = (total % 3600) / 60
    return when {
        hours == 0 && minutes == 0 -> if (total > 0) "<1m" else "0m"
        hours == 0 -> "${minutes}m"
        else -> "${hours}h %02dm".format(minutes)
    }
}
