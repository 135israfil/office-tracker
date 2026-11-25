package com.officemanagement.employees

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import com.officemanagement.core.network.EmployeeListItem

@Composable
fun EmployeesScreen(viewModel: EmployeesViewModel = hiltViewModel()) {
    val state = viewModel.uiState

    Column(modifier = Modifier.fillMaxSize()) {
        OutlinedTextField(
            value = state.query,
            onValueChange = viewModel::onQueryChange,
            label = { Text("Search") },
            singleLine = true,
            keyboardOptions = KeyboardOptions(imeAction = ImeAction.Search),
            keyboardActions = KeyboardActions(onSearch = { viewModel.load() }),
            modifier = Modifier.fillMaxWidth().padding(16.dp),
        )

        when {
            state.isLoading -> CircularProgressIndicator(
                modifier = Modifier.padding(24.dp).align(Alignment.CenterHorizontally),
            )
            state.error != null -> Column(
                modifier = Modifier.padding(24.dp),
                horizontalAlignment = Alignment.CenterHorizontally,
            ) {
                Text(state.error, color = MaterialTheme.colorScheme.error)
                OutlinedButton(onClick = viewModel::load, modifier = Modifier.padding(top = 12.dp)) {
                    Text("Retry")
                }
            }
            state.employees.isEmpty() -> Text(
                "No employees found",
                modifier = Modifier.padding(24.dp),
            )
            else -> LazyColumn(modifier = Modifier.fillMaxSize()) {
                items(state.employees, key = { it.id }) { employee ->
                    EmployeeRow(employee)
                    HorizontalDivider()
                }
            }
        }
    }
}

@Composable
private fun EmployeeRow(employee: EmployeeListItem) {
    Column(modifier = Modifier.fillMaxWidth().padding(16.dp)) {
        Text(employee.name, style = MaterialTheme.typography.titleMedium)
        Text("${employee.designation} · ${employee.department}")
        Text(
            "${employee.employeeId} · ${employee.status}" +
                if (!employee.isUserActive) " · login disabled" else "",
            style = MaterialTheme.typography.bodySmall,
        )
    }
}
