package com.officemanagement.core.network

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

/** Mirrors backend/accounts/serializers.py's CurrentUserSerializer.get_employee(). */
@Serializable
data class EmployeeSummary(
    val id: Int,
    @SerialName("employee_id") val employeeId: String,
    val name: String,
    val department: String,
    val designation: String,
    val status: String,
    @SerialName("leave_total") val leaveTotal: String,
    @SerialName("leave_used") val leaveUsed: String,
    @SerialName("leave_remaining") val leaveRemaining: String,
)

/** Mirrors backend/accounts/serializers.py's CurrentUserSerializer. */
@Serializable
data class CurrentUser(
    val id: Int,
    val email: String,
    val role: String,
    @SerialName("is_active") val isActive: Boolean,
    val employee: EmployeeSummary? = null,
) {
    val isAdmin: Boolean get() = role == "ADMIN"
}

@Serializable
data class TokenLoginRequest(val email: String, val password: String)

/** Mirrors backend/accounts/views.py's TokenLoginView response body. */
@Serializable
data class TokenLoginResponse(val token: String, val user: CurrentUser)

/** A DRF {"detail": "..."} error body — the shape every endpoint in this backend
 * uses for a 4xx, per backend/accounts/serializers.py's own convention. */
@Serializable
data class ApiErrorBody(val detail: String? = null)

/** Mirrors backend/core/dashboards.py's attendance_counts(). Partial on purpose:
 * ignoreUnknownKeys (NetworkModule) means only the fields a screen actually reads
 * need declaring here. */
@Serializable
data class AttendanceCounts(
    val employees: Int,
    val present: Int,
    val late: Int,
    val absent: Int,
    val leave: Int,
    @SerialName("not_recorded") val notRecorded: Int,
    @SerialName("is_working_day") val isWorkingDay: Boolean = true,
)

/** Mirrors backend/core/dashboards.py's computer_counts() (partial, see above). */
@Serializable
data class ComputerCounts(
    val total: Int,
    val online: Int,
    val active: Int,
    val idle: Int,
    val offline: Int,
    val unregistered: Int = 0,
)

/** Mirrors backend/core/views.py's AdminDashboardView response (partial). */
@Serializable
data class AdminDashboard(
    val attendance: AttendanceCounts,
    val computers: ComputerCounts,
)

/** Mirrors backend/core/views.py's MySummaryView response (partial — only the
 * employee identity and leave balance; the activity/computers detail belongs to the
 * Activity screen, a later phase). */
@Serializable
data class MySummary(
    val employee: MySummaryEmployee,
    val leave: MySummaryLeave,
)

@Serializable
data class MySummaryEmployee(val name: String, val department: String, val designation: String)

@Serializable
data class MySummaryLeave(val total: String, val used: String, val remaining: String)

/** DRF's PageNumberPagination envelope (config/settings.py's DEFAULT_PAGINATION_CLASS) —
 * every router-registered list endpoint (employees, computers, notifications, ...)
 * returns this shape. */
@Serializable
data class PagedResponse<T>(
    val count: Int,
    val next: String? = null,
    val previous: String? = null,
    val results: List<T>,
)

/** Mirrors backend/notifications/serializers.py's NotificationSerializer. */
@Serializable
data class NotificationItem(
    val id: Int,
    val message: String,
    val url: String = "",
    @SerialName("created_at") val createdAt: String,
    @SerialName("read_at") val readAt: String? = null,
)

/** Mirrors backend/employees/serializers.py's EmployeeSerializer (partial — list-screen
 * fields only; shift editing is a later phase). */
@Serializable
data class EmployeeListItem(
    val id: Int,
    @SerialName("employee_id") val employeeId: String,
    val name: String,
    val email: String,
    val department: String,
    val designation: String,
    val status: String,
    @SerialName("is_user_active") val isUserActive: Boolean,
    @SerialName("leave_remaining") val leaveRemaining: String,
)

/** Mirrors backend/computers/serializers.py's ComputerSerializer (partial — list-screen
 * fields only; enrolling a new one is a later phase). */
@Serializable
data class ComputerListItem(
    val id: Int,
    @SerialName("employee_name") val employeeName: String,
    @SerialName("computer_name") val computerName: String,
    @SerialName("device_type") val deviceType: String = "PC",
    val status: String,
    @SerialName("operating_system") val operatingSystem: String = "",
    @SerialName("last_seen_at") val lastSeenAt: String? = null,
)

/** Mirrors backend/activities/queries.py's summarise() output (partial — enough for
 * the Activity screen's stat cards; the minute-by-minute timeline is a later phase). */
@Serializable
data class ActivityStat(val name: String, val seconds: Int)

@Serializable
data class ActivityBlock(
    @SerialName("pc_on_seconds") val pcOnSeconds: Int = 0,
    @SerialName("active_seconds") val activeSeconds: Int = 0,
    @SerialName("idle_seconds") val idleSeconds: Int = 0,
    @SerialName("top_applications") val topApplications: List<ActivityStat> = emptyList(),
    @SerialName("top_websites") val topWebsites: List<ActivityStat> = emptyList(),
    @SerialName("session_count") val sessionCount: Int = 0,
)

@Serializable
data class ActivitySummaryEmployee(val id: Int, val name: String, val department: String)

/** Mirrors backend/activities/views.py's ActivitySummaryView response (partial — no
 * attendance/screenshots yet, see the plan's screen-mapping notes). */
@Serializable
data class ActivitySummaryResponse(
    val employee: ActivitySummaryEmployee,
    val date: String,
    val activity: ActivityBlock,
    @SerialName("phone_activity") val phoneActivity: ActivityBlock? = null,
)

/** Mirrors backend/reports/views.py's _ReportView response envelope. */
@Serializable
data class ReportResponse<T>(
    val rows: List<T>,
    @SerialName("has_more") val hasMore: Boolean = false,
)

/** Mirrors one row of backend/reports/queries.py's attendance_rows() (partial). */
@Serializable
data class AttendanceReportRow(
    @SerialName("employee_name") val employeeName: String,
    val date: String? = null,
    @SerialName("worked_seconds") val workedSeconds: Int = 0,
    val status: String = "",
)

/** Mirrors one row of backend/reports/queries.py's activity_rows()/_row() (partial). */
@Serializable
data class ActivityReportRow(
    @SerialName("employee_name") val employeeName: String,
    val date: String? = null,
    @SerialName("pc_on_seconds") val pcOnSeconds: Int = 0,
    @SerialName("active_seconds") val activeSeconds: Int = 0,
    @SerialName("idle_seconds") val idleSeconds: Int = 0,
)

// --- Tasks (mirrors backend/tasks/serializers.py) --------------------------

@Serializable
data class EmployeeStub(val id: Int, @SerialName("employee_id") val employeeId: String, val name: String)

@Serializable
data class TaskAssignee(val employee: EmployeeStub, @SerialName("assigned_by") val assignedBy: EmployeeStub)

@Serializable
data class ParentStub(val id: Int, val title: String)

@Serializable
data class TaskItem(
    val id: Int,
    val title: String,
    val description: String = "",
    val status: String,
    val deadline: String? = null,
    @SerialName("is_overdue") val isOverdue: Boolean = false,
    @SerialName("created_by") val createdBy: EmployeeStub,
    val assignees: List<TaskAssignee> = emptyList(),
    val parent: Int? = null,
    @SerialName("parent_stub") val parentStub: ParentStub? = null,
)

@Serializable
data class TaskWriteRequest(
    val title: String,
    val description: String = "",
    val status: String = "TODO",
    val deadline: String? = null,
    val parent: Int? = null,
    val assignees: List<Int> = emptyList(),
)

@Serializable
data class TaskPatchRequest(
    val title: String? = null,
    val description: String? = null,
    val status: String? = null,
    val deadline: String? = null,
)

@Serializable
data class AssigneeRequest(val employee: Int)

// --- Vault (mirrors backend/vault/serializers.py) --------------------------

@Serializable
data class VaultGrant(val grantee: EmployeeStub, @SerialName("granted_by") val grantedBy: EmployeeStub)

@Serializable
data class AdminViewRecord(val admin: String? = null, val at: String)

@Serializable
data class VaultEntryItem(
    val id: Int,
    val title: String,
    val username: String = "",
    val url: String = "",
    val notes: String = "",
    val owner: EmployeeStub,
    val grants: List<VaultGrant> = emptyList(),
    @SerialName("visible_to") val visibleTo: List<String> = emptyList(),
    @SerialName("last_admin_reveal") val lastAdminReveal: AdminViewRecord? = null,
)

@Serializable
data class VaultEntryWriteRequest(
    val title: String,
    val username: String = "",
    val password: String? = null,
    val url: String = "",
    val notes: String = "",
    // Create-only: backend/vault/views.py's perform_create() reads this straight off
    // request.data (it isn't a declared serializer field), so it's a no-op on update.
    val grantees: List<Int> = emptyList(),
)

@Serializable
data class VaultRevealResponse(val password: String)

// --- Events (mirrors backend/events/serializers.py) ------------------------

@Serializable
data class EventItem(
    val id: Int,
    val title: String,
    @SerialName("agency_name") val agencyName: String = "",
    @SerialName("venue_name") val venueName: String = "",
    val setup: String = "",
    @SerialName("assigned_lead") val assignedLead: EmployeeStub? = null,
    @SerialName("booking_status") val bookingStatus: String,
    @SerialName("alert_on") val alertOn: String? = null,
    val budget: String? = null,
    @SerialName("document_status") val documentStatus: String? = null,
    @SerialName("financial_status") val financialStatus: String? = null,
    val owner: EmployeeStub,
    @SerialName("last_admin_view") val lastAdminView: AdminViewRecord? = null,
)

@Serializable
data class EventFinancialsPatchRequest(
    val budget: String? = null,
    @SerialName("document_status") val documentStatus: String? = null,
    @SerialName("financial_status") val financialStatus: String? = null,
)

@Serializable
data class EventCoordinationPatchRequest(
    @SerialName("assigned_lead_id") val assignedLeadId: Int? = null,
    @SerialName("booking_status") val bookingStatus: String? = null,
)

@Serializable
data class EventWriteRequest(
    val title: String,
    @SerialName("agency_name") val agencyName: String = "",
    @SerialName("venue_name") val venueName: String = "",
    val setup: String = "",
    @SerialName("assigned_lead_id") val assignedLeadId: Int? = null,
    @SerialName("booking_status") val bookingStatus: String = "ON_COMMUNICATION",
    @SerialName("alert_on") val alertOn: String? = null,
)

// --- Attendance (mirrors backend/attendance/attendance_serializers.py) -----

@Serializable
data class PunchItem(
    val id: Int,
    val sequence: Int,
    @SerialName("check_in_at") val checkInAt: String,
    @SerialName("check_out_at") val checkOutAt: String? = null,
    @SerialName("late_minutes") val lateMinutes: Int = 0,
    @SerialName("duration_seconds") val durationSeconds: Int = 0,
)

@Serializable
data class AttendanceItem(
    val id: Int,
    val employee: Int,
    @SerialName("employee_name") val employeeName: String = "",
    val date: String,
    @SerialName("worked_seconds") val workedSeconds: Int = 0,
    @SerialName("late_minutes") val lateMinutes: Int = 0,
    val status: String,
    @SerialName("needs_review") val needsReview: Boolean = false,
    val punches: List<PunchItem> = emptyList(),
)

@Serializable
data class PunchLocationRequest(val latitude: Double, val longitude: Double, @SerialName("accuracy_m") val accuracyM: Float? = null)

@Serializable
data class PunchCorrectionRequest(
    @SerialName("check_in_at") val checkInAt: String? = null,
    @SerialName("check_out_at") val checkOutAt: String? = null,
    val note: String = "",
)

@Serializable
data class OfficeInfo(val name: String, val latitude: String, val longitude: String, @SerialName("radius_meters") val radiusMeters: Int)

@Serializable
data class MyTodayResponse(
    @SerialName("checked_in") val checkedIn: Boolean,
    val attendance: AttendanceItem? = null,
    val office: OfficeInfo,
)

// --- Settings (mirrors backend/attendance/serializers.py's AppSettingsSerializer,
// partial — only the fields the Settings screen's phase actually surfaces) ---

@Serializable
data class AppSettingsItem(
    @SerialName("weekend_days") val weekendDays: List<Int> = emptyList(),
    @SerialName("require_check_in_inside_radius") val requireCheckInInsideRadius: Boolean = false,
    @SerialName("radius_meters") val radiusMeters: Int = 0,
    @SerialName("activity_retention_days") val activityRetentionDays: Int = 0,
)

@Serializable
data class HolidayItem(val id: Int, val date: String, val name: String)

@Serializable
data class HolidayWriteRequest(val date: String, val name: String)

/** A partial PATCH body — every field optional so only what actually changed is sent.
 * Requires Json { explicitNulls = false } (NetworkModule) so an omitted field serializes
 * to nothing at all rather than an explicit `null`, which would otherwise null out a
 * setting nobody meant to touch (DRF's partial=True only skips fields *absent* from
 * the body, not fields present with a null value) — same requirement TaskPatchRequest
 * and every other partial-update request in this file relies on. */
@Serializable
data class SettingsPatchRequest(
    @SerialName("weekend_days") val weekendDays: List<Int>? = null,
    @SerialName("require_check_in_inside_radius") val requireCheckInInsideRadius: Boolean? = null,
    @SerialName("radius_meters") val radiusMeters: Int? = null,
    @SerialName("activity_retention_days") val activityRetentionDays: Int? = null,
)
