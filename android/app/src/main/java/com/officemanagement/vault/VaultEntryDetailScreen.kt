package com.officemanagement.vault

import android.app.Activity
import android.view.WindowManager
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel

@Composable
fun VaultEntryDetailScreen(viewModel: VaultEntryDetailViewModel = hiltViewModel(), onDeleted: () -> Unit) {
    val state = viewModel.uiState
    val activity = LocalContext.current as? Activity

    // FLAG_SECURE for the lifetime of this screen only: blocks screenshots and hides
    // this content from the recent-apps thumbnail while a real credential might be on
    // screen — a risk the web app's equivalent page doesn't have, since there's no
    // OS-level "recent apps" snapshot of a browser tab. Cleared on leaving so the rest
    // of the app (which has nothing secret to protect this way) isn't needlessly
    // blocked from being screenshotted.
    DisposableEffect(activity) {
        activity?.window?.setFlags(WindowManager.LayoutParams.FLAG_SECURE, WindowManager.LayoutParams.FLAG_SECURE)
        onDispose { activity?.window?.clearFlags(WindowManager.LayoutParams.FLAG_SECURE) }
    }

    LaunchedEffect(state.isDeleted) { if (state.isDeleted) onDeleted() }

    Box(modifier = Modifier.fillMaxSize().safeDrawingPadding()) {
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
            state.entry != null -> {
                val entry = state.entry
                Column(modifier = Modifier.fillMaxSize().padding(16.dp)) {
                    Text(entry.title, style = MaterialTheme.typography.headlineSmall)
                    if (entry.username.isNotBlank()) {
                        Text("Username: ${entry.username}", modifier = Modifier.padding(top = 8.dp))
                    }
                    if (entry.url.isNotBlank()) Text("URL: ${entry.url}")

                    Text(
                        text = state.revealedPassword?.let { "Password: $it" } ?: "Password: ••••••••",
                        modifier = Modifier.padding(top = 16.dp),
                        style = MaterialTheme.typography.titleMedium,
                    )
                    OutlinedButton(
                        onClick = { if (state.revealedPassword == null) viewModel.reveal() else viewModel.hide() },
                        modifier = Modifier.padding(top = 8.dp),
                    ) {
                        Text(if (state.revealedPassword == null) "Reveal" else "Hide")
                    }

                    Text(
                        "Visible to: ${entry.visibleTo.joinToString()}",
                        style = MaterialTheme.typography.bodySmall,
                        modifier = Modifier.padding(top = 16.dp),
                    )

                    Button(
                        onClick = viewModel::delete,
                        colors = ButtonDefaults.buttonColors(containerColor = MaterialTheme.colorScheme.error),
                        modifier = Modifier.fillMaxWidth().padding(top = 24.dp),
                    ) { Text("Delete credential") }
                }
            }
        }
    }
}
