package com.officemanagement.attendance

import android.Manifest
import android.content.pm.PackageManager
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.core.content.ContextCompat
import androidx.hilt.navigation.compose.hiltViewModel

@Composable
fun CheckInScreen(viewModel: CheckInViewModel = hiltViewModel()) {
    val context = LocalContext.current
    var hasLocationPermission by remember {
        mutableStateOf(
            ContextCompat.checkSelfPermission(context, Manifest.permission.ACCESS_COARSE_LOCATION) ==
                PackageManager.PERMISSION_GRANTED,
        )
    }
    val permissionLauncher = rememberLauncherForActivityResult(ActivityResultContracts.RequestMultiplePermissions()) { result ->
        hasLocationPermission = result.values.any { it }
    }

    val state = viewModel.uiState

    Box(modifier = Modifier.fillMaxSize().padding(24.dp)) {
        when {
            !hasLocationPermission -> Column(
                modifier = Modifier.align(Alignment.Center),
                horizontalAlignment = Alignment.CenterHorizontally,
            ) {
                Text("Check-in needs your location to confirm you're at the office.")
                Button(
                    onClick = {
                        permissionLauncher.launch(
                            arrayOf(Manifest.permission.ACCESS_FINE_LOCATION, Manifest.permission.ACCESS_COARSE_LOCATION),
                        )
                    },
                    modifier = Modifier.padding(top = 12.dp),
                ) { Text("Grant location access") }
            }
            state.isLoading -> CircularProgressIndicator(modifier = Modifier.align(Alignment.Center))
            state.today == null -> Column(
                modifier = Modifier.align(Alignment.Center),
                horizontalAlignment = Alignment.CenterHorizontally,
            ) {
                Text(state.error ?: "Could not load attendance.", color = MaterialTheme.colorScheme.error)
                OutlinedButton(onClick = viewModel::load, modifier = Modifier.padding(top = 12.dp)) {
                    Text("Retry")
                }
            }
            else -> Column(modifier = Modifier.fillMaxWidth().align(Alignment.Center)) {
                val today = state.today
                Text(
                    if (today.checkedIn) "You're checked in" else "You're not checked in",
                    style = MaterialTheme.typography.headlineSmall,
                )
                today.attendance?.let {
                    Text("Worked so far: ${it.workedSeconds / 60}m · ${it.status}", modifier = Modifier.padding(top = 8.dp))
                }
                if (state.error != null) {
                    Text(state.error, color = MaterialTheme.colorScheme.error, modifier = Modifier.padding(top = 12.dp))
                }
                Button(
                    onClick = { if (today.checkedIn) viewModel.checkOut() else viewModel.checkIn() },
                    enabled = !state.isSubmitting,
                    modifier = Modifier.fillMaxWidth().padding(top = 24.dp),
                ) {
                    Text(if (state.isSubmitting) "Submitting…" else if (today.checkedIn) "Check out" else "Check in")
                }
                OutlinedButton(onClick = viewModel::load, modifier = Modifier.fillMaxWidth().padding(top = 8.dp)) {
                    Text("Refresh")
                }
            }
        }
    }
}
