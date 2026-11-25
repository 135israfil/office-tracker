package com.officemanagement.nav

/** One object per drawer-visible screen, plus the label the drawer shows for it —
 * matches `App.vue`'s nav list. Detail/create screens reached by tapping into a list
 * (task/vault-entry/event detail) are plain route-string templates in [DetailRoutes]
 * instead, since they don't appear in the drawer themselves. */
sealed class Destinations(val route: String, val label: String) {
    data object Login : Destinations("login", "Login")
    data object TrackingOnboarding : Destinations("tracking_onboarding", "Activity tracking")
    data object Dashboard : Destinations("dashboard", "Dashboard")
    data object MyDashboard : Destinations("my_dashboard", "My Dashboard")
    data object Notifications : Destinations("notifications", "Notifications")
    data object Attendance : Destinations("attendance", "Attendance")
    data object AdminAttendance : Destinations("admin_attendance", "All attendance")
    data object Activity : Destinations("activity", "Activity")
    data object Tasks : Destinations("tasks", "Tasks")
    data object Vault : Destinations("vault", "Credentials")
    data object Events : Destinations("events", "Events")
    data object Reports : Destinations("reports", "Reports")
    data object Employees : Destinations("employees", "Employees")
    data object Computers : Destinations("computers", "Computers")
    data object Settings : Destinations("settings", "Settings")
}

/** Route templates for screens reached by tapping into a list, not from the drawer. */
object DetailRoutes {
    const val TASK_DETAIL = "task_detail/{taskId}"
    const val VAULT_DETAIL = "vault_detail/{entryId}"
    const val EVENT_DETAIL = "event_detail/{eventId}"

    fun taskDetail(id: Int) = "task_detail/$id"
    fun vaultDetail(id: Int) = "vault_detail/$id"
    fun eventDetail(id: Int) = "event_detail/$id"
}
