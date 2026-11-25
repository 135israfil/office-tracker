package com.officemanagement.nav

import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Menu
import androidx.compose.material3.DrawerValue
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.ModalDrawerSheet
import androidx.compose.material3.ModalNavigationDrawer
import androidx.compose.material3.NavigationDrawerItem
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.rememberDrawerState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.officemanagement.core.network.CurrentUser
import kotlinx.coroutines.launch

/** The drawer + top bar every authenticated screen shares, the same job `App.vue`'s
 * sidebar does for the web app: one role-based link list (admin gets more than an
 * employee does), the signed-in user's identity, and Sign out — built once here
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

    ModalNavigationDrawer(
        drawerState = drawerState,
        drawerContent = {
            ModalDrawerSheet {
                Text(
                    currentUser.employee?.name ?: currentUser.email,
                    modifier = Modifier.padding(16.dp),
                )
                HorizontalDivider()
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
                HorizontalDivider(modifier = Modifier.padding(vertical = 8.dp))
                NavigationDrawerItem(
                    label = { Text("Sign out") },
                    selected = false,
                    onClick = {
                        scope.launch { drawerState.close() }
                        onLogout()
                    },
                    modifier = Modifier.padding(horizontal = 12.dp),
                )
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
                )
            },
        ) { padding ->
            Box(modifier = Modifier.padding(padding)) { content() }
        }
    }
}
