package com.officemanagement.vault
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
import androidx.compose.material3.Checkbox
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.FloatingActionButton
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
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
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import com.officemanagement.core.network.EmployeeStub
import com.officemanagement.core.network.VaultEntryItem

@Composable
fun VaultScreen(viewModel: VaultViewModel = hiltViewModel(), onOpenEntry: (Int) -> Unit) {
    val state = viewModel.uiState
    var showCreate by remember { mutableStateOf(false) }

    Scaffold(
        floatingActionButton = {
            FloatingActionButton(onClick = { showCreate = true }) {
                Icon(Icons.Default.Add, contentDescription = "New credential")
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
                state.entries.isEmpty() -> Text("No credentials yet", modifier = Modifier.align(Alignment.Center))
                else -> LazyColumn(modifier = Modifier.fillMaxSize()) {
                    items(state.entries, key = { it.id }) { entry ->
                        EntryRow(entry, onClick = { onOpenEntry(entry.id) })
                        HorizontalDivider()
                    }
                }
            }
        }
    }

    if (showCreate) {
        NewEntryDialog(
            employees = state.employees,
            onDismiss = { showCreate = false },
            onCreate = { title, username, password, url, notes, granteeIds ->
                showCreate = false
                viewModel.createEntry(title, username, password, url, notes, granteeIds) {}
            },
        )
    }
}

@Composable
private fun EntryRow(entry: VaultEntryItem, onClick: () -> Unit) {
    Column(modifier = Modifier.fillMaxWidth().clickable(onClick = onClick).padding(16.dp)) {
        Text(entry.title, style = MaterialTheme.typography.titleMedium)
        Text(
            entry.username.ifBlank { entry.owner.name },
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
    }
}

@Composable
private fun NewEntryDialog(
    employees: List<EmployeeStub>,
    onDismiss: () -> Unit,
    onCreate: (title: String, username: String, password: String, url: String, notes: String, granteeIds: List<Int>) -> Unit,
) {
    var title by remember { mutableStateOf("") }
    var username by remember { mutableStateOf("") }
    var password by remember { mutableStateOf("") }
    var url by remember { mutableStateOf("") }
    var notes by remember { mutableStateOf("") }
    val selectedGrantees = remember { mutableStateOf(setOf<Int>()) }

    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("New credential") },
        text = {
            Column {
                OutlinedTextField(value = title, onValueChange = { title = it }, label = { Text("Title") }, singleLine = true)
                OutlinedTextField(
                    value = username,
                    onValueChange = { username = it },
                    label = { Text("Username") },
                    singleLine = true,
                    modifier = Modifier.padding(top = 8.dp),
                )
                OutlinedTextField(
                    value = password,
                    onValueChange = { password = it },
                    label = { Text("Password") },
                    singleLine = true,
                    visualTransformation = PasswordVisualTransformation(),
                    modifier = Modifier.padding(top = 8.dp),
                )
                OutlinedTextField(
                    value = url,
                    onValueChange = { url = it },
                    label = { Text("URL") },
                    singleLine = true,
                    modifier = Modifier.padding(top = 8.dp),
                )
                OutlinedTextField(
                    value = notes,
                    onValueChange = { notes = it },
                    label = { Text("Notes") },
                    modifier = Modifier.fillMaxWidth().padding(top = 8.dp),
                )
                if (employees.isNotEmpty()) {
                    Text("Share with", style = MaterialTheme.typography.labelMedium, modifier = Modifier.padding(top = 12.dp))
                    employees.forEach { employee ->
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Checkbox(
                                checked = employee.id in selectedGrantees.value,
                                onCheckedChange = { checked ->
                                    selectedGrantees.value =
                                        if (checked) selectedGrantees.value + employee.id else selectedGrantees.value - employee.id
                                },
                            )
                            Text(employee.name)
                        }
                    }
                }
            }
        },
        confirmButton = {
            AppOutlinedButton(
                onClick = {
                    if (title.isNotBlank() && password.isNotBlank()) {
                        onCreate(title, username, password, url, notes, selectedGrantees.value.toList())
                    }
                },
            ) { Text("Create") }
        },
        dismissButton = { AppOutlinedButton(onClick = onDismiss) { Text("Cancel") } },
    )
}
