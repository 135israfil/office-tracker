package com.officemanagement.nav
import com.officemanagement.ui.components.AppOutlinedButton

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Menu
import androidx.compose.material3.DrawerValue
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalDrawerSheet
import androidx.compose.material3.ModalNavigationDrawer
import androidx.compose.material3.NavigationDrawerItem
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.material3.rememberDrawerState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.officemanagement.core.network.CurrentUser
import kotlinx.coroutines.launch

/** The drawer + top bar every authenticated screen shares, the same job `App.vue`'s
 * sidebar does for the web app: a brand mark, one role-based link list (admin gets more
 * than an employee does), the signed-in user's identity, and Sign out — built once here
 * rather than copied into every screen. */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun AppShell(
    currentUser: CurrentUser,
    currentRoute: String?,
    title: String,
    onNavigate: (Destinations) -> Unit,
    onLogout: () -> Unit,
    content: @Composable () -> Unit,
) {
    val drawerState = rememberDrawerState(DrawerValue.Closed)
    val scope = rememberCoroutineScope()

    // Matches App.vue's role-based link list — grows as each screen lands, not
    // meant to list screens that don't exist yet.
    val items = buildList {
        add(if (currentUser.isAdmin) Destinations.Dashboard else Destinations.MyDashboard)
        add(Destinations.Notifications)
        add(Destinations.Attendance)
        if (currentUser.isAdmin) add(Destinations.AdminAttendance)
        if (currentUser.isAdmin) add(Destinations.Activity)
        add(Destinations.Tasks)
        add(Destinations.Vault)
        add(Destinations.Events)
        if (currentUser.isAdmin) {
            add(Destinations.Reports)
            add(Destinations.Employees)
            add(Destinations.Computers)
            add(Destinations.Settings)
        }
    }

    val displayName = currentUser.employee?.name ?: currentUser.email
    val initials = displayName
        .split(Regex("[\\s@.]+"))
        .filter { it.isNotBlank() }
        .take(2)
        .joinToString("") { it.first().uppercase() }

    ModalNavigationDrawer(
        drawerState = drawerState,
        drawerContent = {
            ModalDrawerSheet {
                // --- Brand ------------------------------------------------------
                Row(
                    verticalAlignment = Alignment.CenterVertically,
                    modifier = Modifier.padding(start = 20.dp, end = 16.dp, top = 18.dp, bottom = 14.dp),
                ) {
                    Surface(
                        shape = RoundedCornerShape(8.dp),
                        color = MaterialTheme.colorScheme.primary,
                        modifier = Modifier.size(30.dp),
                    ) {
                        Box(contentAlignment = Alignment.Center) {
                            Text(
                                "OM",
                                color = MaterialTheme.colorScheme.onPrimary,
                                style = MaterialTheme.typography.labelSmall,
                                fontWeight = FontWeight.Bold,
                            )
                        }
                    }
                    Text(
                        "Office",
                        style = MaterialTheme.typography.titleMedium,
                        modifier = Modifier.padding(start = 10.dp),
                    )
                }
                HorizontalDivider()

                // --- Nav ---------------------------------------------------------
                Column(modifier = Modifier.weight(1f).padding(vertical = 4.dp)) {
                    items.forEach { destination ->
                        NavigationDrawerItem(
                            label = { Text(destination.label) },
                            selected = destination.route == currentRoute,
                            onClick = {
                                scope.launch { drawerState.close() }
                                onNavigate(destination)
                            },
                            modifier = Modifier.padding(horizontal = 12.dp),
                        )
                    }
                }

                // --- Who + sign out -----------------------------------------------
                HorizontalDivider()
                Row(
                    verticalAlignment = Alignment.CenterVertically,
                    modifier = Modifier.fillMaxWidth().padding(start = 20.dp, end = 12.dp, top = 12.dp, bottom = 4.dp),
                ) {
                    Surface(
                        shape = RoundedCornerShape(50),
                        color = MaterialTheme.colorScheme.surfaceVariant,
                        border = BorderStroke(1.dp, MaterialTheme.colorScheme.outline),
                        modifier = Modifier.size(30.dp),
                    ) {
                        Box(contentAlignment = Alignment.Center) {
                            Text(initials, style = MaterialTheme.typography.labelSmall, fontWeight = FontWeight.Bold)
                        }
                    }
                    Column(modifier = Modifier.weight(1f).padding(start = 10.dp)) {
                        Text(
                            displayName,
                            style = MaterialTheme.typography.labelLarge,
                            maxLines = 1,
                            overflow = TextOverflow.Ellipsis,
                        )
                        Text(
                            if (currentUser.isAdmin) "Administrator" else "Employee",
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }
                }
                AppOutlinedButton(
                    onClick = {
                        scope.launch { drawerState.close() }
                        onLogout()
                    },
                    colors = ButtonDefaults.outlinedButtonColors(contentColor = MaterialTheme.colorScheme.onSurface),
                    modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 10.dp),
                ) {
                    Text("Sign out")
                }
            }
        },
    ) {
        Scaffold(
            topBar = {
                TopAppBar(
                    title = { Text(title) },
                    navigationIcon = {
                        IconButton(onClick = { scope.launch { drawerState.open() } }) {
                            Icon(Icons.Default.Menu, contentDescription = "Menu")
                        }
                    },
                    colors = TopAppBarDefaults.topAppBarColors(containerColor = MaterialTheme.colorScheme.surface),
                )
            },
        ) { padding ->
            Box(modifier = Modifier.padding(padding)) { content() }
        }
    }
}
