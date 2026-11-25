package com.officemanagement.tracking.onboarding
import com.officemanagement.ui.components.AppButton
import com.officemanagement.ui.components.AppOutlinedButton

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.widthIn
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Visibility
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.lifecycle.compose.LocalLifecycleOwner

/** Shown once, right after login, if this phone has never been through it (see
 * TrackingPrefs.onboardingCompleted and the nav graph's redirect). Explains *why*
 * before asking for anything, matching §31's "people know tracking is on" principle —
 * and asks rather than demands: "Not now" moves on to the rest of the app with
 * tracking simply left off for this phone, the same choice a desktop user has by never
 * running the enrollment command. */
@Composable
fun TrackingOnboardingScreen(viewModel: TrackingOnboardingViewModel = hiltViewModel(), onDone: () -> Unit) {
    val state = viewModel.uiState
    val context = LocalContext.current
    val lifecycleOwner = LocalLifecycleOwner.current

    LaunchedEffect(state.done) { if (state.done) onDone() }

    // Usage Access can only be granted from Settings, with no callback back into the
    // app — re-checking on every resume is how this screen notices it happened.
    DisposableEffect(lifecycleOwner) {
        val observer = LifecycleEventObserver { _, event ->
            if (event == Lifecycle.Event.ON_RESUME) viewModel.refreshPermissionStatus()
        }
        lifecycleOwner.lifecycle.addObserver(observer)
        onDispose { lifecycleOwner.lifecycle.removeObserver(observer) }
    }

    Box(modifier = Modifier.fillMaxSize().padding(24.dp), contentAlignment = Alignment.Center) {
        Surface(
            shape = MaterialTheme.shapes.medium,
            color = MaterialTheme.colorScheme.surface,
            shadowElevation = 8.dp,
            modifier = Modifier.widthIn(max = 420.dp).fillMaxWidth(),
        ) {
            Column(modifier = Modifier.padding(32.dp), verticalArrangement = Arrangement.Center) {
                Icon(
                    imageVector = Icons.Filled.Visibility,
                    contentDescription = null,
                    tint = MaterialTheme.colorScheme.primary,
                    modifier = Modifier.size(40.dp),
                )
                Text(
                    "Activity tracking on this phone",
                    style = MaterialTheme.typography.headlineSmall,
                    modifier = Modifier.padding(top = 16.dp),
                )
                Text(
                    "Your employer uses this app to track which apps are used on " +
                        "company devices, the same way the desktop app does on a PC. " +
                        "This needs Usage Access, which only Android Settings can grant.",
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    modifier = Modifier.padding(top = 12.dp),
                )

                Text(
                    if (state.usageAccessGranted) "Usage Access: granted" else "Usage Access: not granted yet",
                    style = MaterialTheme.typography.labelLarge,
                    color = if (state.usageAccessGranted) {
                        MaterialTheme.colorScheme.primary
                    } else {
                        MaterialTheme.colorScheme.error
                    },
                    modifier = Modifier.padding(top = 20.dp),
                )

                if (!state.usageAccessGranted) {
                    AppOutlinedButton(
                        onClick = { context.startActivity(com.officemanagement.tracking.collector.UsageAccess.settingsIntent()) },
                        modifier = Modifier.fillMaxWidth().padding(top = 8.dp),
                    ) { Text("Open Settings") }
                }

                if (state.error != null) {
                    Text(
                        state.error,
                        color = MaterialTheme.colorScheme.error,
                        style = MaterialTheme.typography.bodySmall,
                        modifier = Modifier.padding(top = 12.dp),
                    )
                }

                AppButton(
                    onClick = viewModel::completeOnboarding,
                    enabled = !state.isSubmitting,
                    modifier = Modifier.fillMaxWidth().padding(top = 20.dp),
                ) {
                    if (state.isSubmitting) {
                        CircularProgressIndicator(
                            modifier = Modifier.padding(end = 8.dp).size(16.dp),
                            color = MaterialTheme.colorScheme.onPrimary,
                        )
                    }
                    Text("Continue")
                }
                AppOutlinedButton(
                    onClick = viewModel::skip,
                    enabled = !state.isSubmitting,
                    modifier = Modifier.fillMaxWidth().padding(top = 8.dp),
                ) { Text("Not now") }
            }
        }
    }
}
