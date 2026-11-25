package com.officemanagement.nav

import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.navigation.NavGraph.Companion.findStartDestination
import androidx.navigation.NavHostController
import androidx.navigation.NavType
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.currentBackStackEntryAsState
import androidx.navigation.compose.rememberNavController
import androidx.navigation.navArgument
import com.officemanagement.activity.ActivityScreen
import com.officemanagement.attendance.AdminAttendanceScreen
import com.officemanagement.attendance.CheckInScreen
import com.officemanagement.auth.LoginScreen
import com.officemanagement.computers.ComputersScreen
import com.officemanagement.core.network.CurrentUser
import com.officemanagement.dashboard.DashboardScreen
import com.officemanagement.dashboard.MyDashboardScreen
import com.officemanagement.employees.EmployeesScreen
import com.officemanagement.events.EventDetailScreen
import com.officemanagement.events.EventsScreen
import com.officemanagement.notifications.NotificationsScreen
import com.officemanagement.reports.ReportsScreen
import com.officemanagement.settings.SettingsScreen
import com.officemanagement.tasks.TaskDetailScreen
import com.officemanagement.tasks.TasksScreen
import com.officemanagement.vault.VaultEntryDetailScreen
import com.officemanagement.vault.VaultScreen

/**
 * Role gating lives here, the same job `frontend/src/router/index.js`'s
 * `requiresAdmin` guard does for the web app: not authenticated → Login; authenticated
 * as an admin → Dashboard; authenticated as an employee → MyDashboard. Reacts to
 * [SessionViewModel]'s state rather than being told to navigate by each screen, so a
 * token that goes away for any reason (explicit logout, a 401 from any call, an admin
 * disabling the account) is reflected the same way everywhere.
 */
@Composable
fun AppNavGraph(sessionViewModel: SessionViewModel = hiltViewModel()) {
    val navController = rememberNavController()
    val token by sessionViewModel.token.collectAsStateWithLifecycle()
    val currentUser by sessionViewModel.currentUser.collectAsStateWithLifecycle()
    val backStackEntry by navController.currentBackStackEntryAsState()
    val currentRoute = backStackEntry?.destination?.route

    LaunchedEffect(token, currentUser) {
        val destination = when {
            token == null -> Destinations.Login.route
            // Still waiting on refreshCurrentUser()/login()'s own response to learn
            // the role — stay on whatever is showing rather than guess.
            currentUser == null -> null
            currentUser!!.isAdmin -> Destinations.Dashboard.route
            else -> Destinations.MyDashboard.route
        }
        if (destination != null && currentRoute != destination &&
            (currentRoute == null || currentRoute == Destinations.Login.route || destination == Destinations.Login.route)
        ) {
            navController.navigate(destination) {
                popUpTo(0) { inclusive = true }
                launchSingleTop = true
            }
        }
    }

    NavHost(navController = navController, startDestination = Destinations.Login.route) {
        composable(Destinations.Login.route) { LoginScreen() }

        authedScreen(Destinations.Dashboard, currentUser, currentRoute, navController, sessionViewModel::logout) {
            DashboardScreen()
        }
        authedScreen(Destinations.MyDashboard, currentUser, currentRoute, navController, sessionViewModel::logout) {
            MyDashboardScreen()
        }
        authedScreen(Destinations.Notifications, currentUser, currentRoute, navController, sessionViewModel::logout) {
            NotificationsScreen()
        }
        authedScreen(Destinations.Attendance, currentUser, currentRoute, navController, sessionViewModel::logout) {
            CheckInScreen()
        }
        authedScreen(Destinations.AdminAttendance, currentUser, currentRoute, navController, sessionViewModel::logout) {
            AdminAttendanceScreen()
        }
        authedScreen(Destinations.Activity, currentUser, currentRoute, navController, sessionViewModel::logout) {
            ActivityScreen()
        }
        authedScreen(Destinations.Reports, currentUser, currentRoute, navController, sessionViewModel::logout) {
            ReportsScreen()
        }
        authedScreen(Destinations.Employees, currentUser, currentRoute, navController, sessionViewModel::logout) {
            EmployeesScreen()
        }
        authedScreen(Destinations.Computers, currentUser, currentRoute, navController, sessionViewModel::logout) {
            ComputersScreen()
        }
        authedScreen(Destinations.Settings, currentUser, currentRoute, navController, sessionViewModel::logout) {
            SettingsScreen()
        }
        authedScreen(Destinations.Tasks, currentUser, currentRoute, navController, sessionViewModel::logout) {
            TasksScreen(onOpenTask = { id -> navController.navigate(DetailRoutes.taskDetail(id)) })
        }
        authedScreen(Destinations.Vault, currentUser, currentRoute, navController, sessionViewModel::logout) {
            VaultScreen(onOpenEntry = { id -> navController.navigate(DetailRoutes.vaultDetail(id)) })
        }
        authedScreen(Destinations.Events, currentUser, currentRoute, navController, sessionViewModel::logout) {
            EventsScreen(onOpenEvent = { id -> navController.navigate(DetailRoutes.eventDetail(id)) })
        }

        // Detail screens: reached only by tapping into a list, never from the drawer,
        // so they're plain composable() entries rather than authedScreen() — they
        // still render inside whichever list screen's AppShell is already on the back
        // stack, Navigation-Compose style (no shell of their own needed).
        composable(
            DetailRoutes.TASK_DETAIL,
            arguments = listOf(navArgument("taskId") { type = NavType.IntType }),
        ) {
            TaskDetailScreen(onDeleted = { navController.popBackStack() })
        }
        composable(
            DetailRoutes.VAULT_DETAIL,
            arguments = listOf(navArgument("entryId") { type = NavType.IntType }),
        ) {
            VaultEntryDetailScreen(onDeleted = { navController.popBackStack() })
        }
        composable(
            DetailRoutes.EVENT_DETAIL,
            arguments = listOf(navArgument("eventId") { type = NavType.IntType }),
        ) {
            EventDetailScreen(onDeleted = { navController.popBackStack() })
        }
    }
}

/** One NavHost `composable {}` entry wrapped in [AppShell] — the drawer/top-bar/logout
 * chrome every screen behind login shares, defined once instead of per screen. */
private fun androidx.navigation.NavGraphBuilder.authedScreen(
    destination: Destinations,
    currentUser: CurrentUser?,
    currentRoute: String?,
    navController: NavHostController,
    onLogout: () -> Unit,
    content: @Composable () -> Unit,
) {
    composable(destination.route) {
        val user = currentUser
        if (user != null) {
            AppShell(
                currentUser = user,
                currentRoute = currentRoute,
                title = destination.label,
                onNavigate = { target ->
                    if (target.route != currentRoute) {
                        navController.navigate(target.route) {
                            launchSingleTop = true
                            restoreState = true
                            popUpTo(navController.graph.findStartDestination().id) { saveState = true }
                        }
                    }
                },
                onLogout = onLogout,
                content = content,
            )
        }
    }
}
