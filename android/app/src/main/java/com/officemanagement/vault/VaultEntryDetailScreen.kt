package com.officemanagement.vault
import com.officemanagement.ui.components.AppOutlinedButton
import com.officemanagement.ui.components.AppButton

import android.app.Activity
import android.view.WindowManager
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.input.PasswordVisualTransformation
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
                AppOutlinedButton(onClick = viewModel::load, modifier = Modifier.padding(top = 12.dp)) {
                    Text("Retry")
                }
            }
            state.entry != null -> {
                val entry = state.entry
                var title by remember(entry.id) { mutableStateOf(entry.title) }
                var username by remember(entry.id) { mutableStateOf(entry.username) }
                var url by remember(entry.id) { mutableStateOf(entry.url) }
                var notes by remember(entry.id) { mutableStateOf(entry.notes) }
                var newPassword by remember(entry.id) { mutableStateOf("") }
                var passwordError by remember(entry.id) { mutableStateOf<String?>(null) }
                var shareMenuExpanded by remember { mutableStateOf(false) }

                Column(modifier = Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(16.dp)) {
                    Text(entry.title, style = MaterialTheme.typography.headlineSmall)
                    Text(
                        "Visible to: ${entry.visibleTo.joinToString()}",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        modifier = Modifier.padding(top = 4.dp),
                    )
                    entry.lastAdminReveal?.let {
                        Text(
                            "Last viewed by an admin (${it.admin ?: "unknown"}) on ${it.at}.",
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }

                    OutlinedTextField(
                        value = title,
                        onValueChange = { title = it },
                        label = { Text("Title") },
                        singleLine = true,
                        enabled = state.isOwner,
                        modifier = Modifier.fillMaxWidth().padding(top = 12.dp),
                        trailingIcon = if (state.isOwner) {
                            { AppOutlinedButton(onClick = { viewModel.setTitle(title) }) { Text("Save") } }
                        } else null,
                    )
                    OutlinedTextField(
                        value = username,
                        onValueChange = { username = it },
                        label = { Text("Username") },
                        singleLine = true,
                        enabled = state.isOwner,
                        modifier = Modifier.fillMaxWidth().padding(top = 8.dp),
                        trailingIcon = if (state.isOwner) {
                            { AppOutlinedButton(onClick = { viewModel.setUsername(username) }) { Text("Save") } }
                        } else null,
                    )
                    OutlinedTextField(
                        value = url,
                        onValueChange = { url = it },
                        label = { Text("URL") },
                        singleLine = true,
                        enabled = state.isOwner,
                        modifier = Modifier.fillMaxWidth().padding(top = 8.dp),
                        trailingIcon = if (state.isOwner) {
                            { AppOutlinedButton(onClick = { viewModel.setUrl(url) }) { Text("Save") } }
                        } else null,
                    )
                    OutlinedTextField(
                        value = notes,
                        onValueChange = { notes = it },
                        label = { Text("Notes") },
                        enabled = state.isOwner,
                        modifier = Modifier.fillMaxWidth().padding(top = 8.dp),
                    )
                    if (state.isOwner) {
                        AppOutlinedButton(onClick = { viewModel.setNotes(notes) }, modifier = Modifier.padding(top = 4.dp)) {
                            Text("Save notes")
                        }
                    }

                    Text("Password", style = MaterialTheme.typography.titleMedium, modifier = Modifier.padding(top = 20.dp))
                    Text(
                        text = state.revealedPassword ?: "••••••••",
                        style = MaterialTheme.typography.bodyLarge,
                        modifier = Modifier.padding(top = 4.dp),
                    )
                    AppOutlinedButton(
                        onClick = { if (state.revealedPassword == null) viewModel.reveal() else viewModel.hide() },
                        modifier = Modifier.padding(top = 8.dp),
                    ) {
                        Text(if (state.revealedPassword == null) "Reveal password" else "Hide")
                    }

                    if (state.isOwner) {
                        Row(modifier = Modifier.fillMaxWidth().padding(top = 12.dp), verticalAlignment = Alignment.CenterVertically) {
                            OutlinedTextField(
                                value = newPassword,
                                onValueChange = { newPassword = it; passwordError = null },
                                label = { Text("New password") },
                                singleLine = true,
                                visualTransformation = PasswordVisualTransformation(),
                                modifier = Modifier.weight(1f),
                            )
                            AppOutlinedButton(
                                onClick = {
                                    viewModel.updatePassword(newPassword) { success ->
                                        if (success) newPassword = "" else passwordError = "That didn't go through."
                                    }
                                },
                                modifier = Modifier.padding(start = 8.dp),
                            ) { Text("Update") }
                        }
                        passwordError?.let {
                            Text(it, color = MaterialTheme.colorScheme.error, style = MaterialTheme.typography.bodySmall)
                        }
                    }

                    Text("Shared with", style = MaterialTheme.typography.titleMedium, modifier = Modifier.padding(top = 20.dp))
                    if (entry.grants.isEmpty()) {
                        Text(
                            "Not shared with anyone.",
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                            modifier = Modifier.padding(top = 4.dp),
                        )
                    } else {
                        entry.grants.forEach { grant ->
                            Row(
                                modifier = Modifier.fillMaxWidth().padding(vertical = 4.dp),
                                verticalAlignment = Alignment.CenterVertically,
                            ) {
                                Text(grant.grantee.name, modifier = Modifier.weight(1f))
                                AppOutlinedButton(onClick = { viewModel.revoke(grant.grantee.id) }) { Text("Revoke") }
                            }
                        }
                    }
                    if (state.isOwner) {
                        val alreadyShared = entry.grants.map { it.grantee.id }.toSet()
                        val candidates = state.assignableEmployees.filter { it.id !in alreadyShared }
                        if (candidates.isNotEmpty()) {
                            Box(modifier = Modifier.padding(top = 8.dp)) {
                                AppOutlinedButton(onClick = { shareMenuExpanded = true }) { Text("Share with…") }
                                DropdownMenu(expanded = shareMenuExpanded, onDismissRequest = { shareMenuExpanded = false }) {
                                    candidates.forEach { employee ->
                                        DropdownMenuItem(
                                            text = { Text(employee.name) },
                                            onClick = { shareMenuExpanded = false; viewModel.share(employee.id) },
                                        )
                                    }
                                }
                            }
                        }
                    }

                    if (state.isOwner) {
                        HorizontalDivider(modifier = Modifier.padding(top = 20.dp, bottom = 4.dp))
                        AppButton(
                            onClick = viewModel::delete,
                            colors = ButtonDefaults.buttonColors(containerColor = MaterialTheme.colorScheme.error),
                            modifier = Modifier.fillMaxWidth().padding(top = 8.dp),
                        ) { Text("Delete credential") }
                    }

                    // Clears the system gesture-navigation strip so the last button on a
                    // short screen isn't swallowed by an edge swipe.
                    Spacer(Modifier.height(32.dp))
                }
            }
        }
    }
}
