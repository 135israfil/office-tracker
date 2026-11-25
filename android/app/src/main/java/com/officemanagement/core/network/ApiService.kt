package com.officemanagement.core.network

import okhttp3.ResponseBody
import retrofit2.http.Body
import retrofit2.http.DELETE
import retrofit2.http.GET
import retrofit2.http.PATCH
import retrofit2.http.POST
import retrofit2.http.Path
import retrofit2.http.Query
import retrofit2.http.QueryMap
import retrofit2.http.Streaming

/** The Android app's view of the backend's REST surface. One endpoint grows per
 * feature screen as it's built (see the plan's build order) — this file is not meant
 * to pre-declare the whole ~50-endpoint surface up front. */
interface ApiService {

    @POST("auth/token/")
    suspend fun login(@Body body: TokenLoginRequest): TokenLoginResponse

    @POST("auth/token/revoke/")
    suspend fun revokeToken()

    @GET("auth/me/")
    suspend fun me(): CurrentUser

    @GET("dashboard/")
    suspend fun adminDashboard(): AdminDashboard

    @GET("me/summary/")
    suspend fun mySummary(): MySummary

    @GET("notifications/")
    suspend fun notifications(@Query("unread") unread: Boolean? = null): PagedResponse<NotificationItem>

    @POST("notifications/{id}/read/")
    suspend fun markNotificationRead(@Path("id") id: Int)

    @POST("notifications/read_all/")
    suspend fun markAllNotificationsRead()

    @GET("employees/")
    suspend fun employees(@Query("search") search: String? = null): PagedResponse<EmployeeListItem>

    @GET("computers/")
    suspend fun computers(@Query("search") search: String? = null): PagedResponse<ComputerListItem>

    @GET("activity/summary/")
    suspend fun activitySummary(
        @Query("employee") employeeId: Int,
        @Query("date") date: String? = null,
    ): ActivitySummaryResponse

    @GET("reports/attendance/")
    suspend fun attendanceReport(@QueryMap filters: Map<String, String>): ReportResponse<AttendanceReportRow>

    @GET("reports/activity/")
    suspend fun activityReport(@QueryMap filters: Map<String, String>): ReportResponse<ActivityReportRow>

    @Streaming
    @GET("reports/{report}/export/")
    suspend fun exportReport(
        @Path("report") report: String,
        @QueryMap filters: Map<String, String>,
    ): ResponseBody

    // --- Tasks ---------------------------------------------------------------

    @GET("tasks/assignable-employees/")
    suspend fun assignableEmployees(): List<EmployeeStub>

    @GET("tasks/")
    suspend fun tasks(@Query("parent") parent: Int? = null): PagedResponse<TaskItem>

    @GET("tasks/{id}/")
    suspend fun task(@Path("id") id: Int): TaskItem

    @POST("tasks/")
    suspend fun createTask(@Body body: TaskWriteRequest): TaskItem

    @PATCH("tasks/{id}/")
    suspend fun updateTask(@Path("id") id: Int, @Body body: TaskPatchRequest): TaskItem

    @DELETE("tasks/{id}/")
    suspend fun deleteTask(@Path("id") id: Int)

    @POST("tasks/{id}/add_assignee/")
    suspend fun addTaskAssignee(@Path("id") id: Int, @Body body: AssigneeRequest): TaskItem

    @DELETE("tasks/{id}/assignees/{employeeId}/")
    suspend fun removeTaskAssignee(@Path("id") id: Int, @Path("employeeId") employeeId: Int): TaskItem

    // --- Vault -----------------------------------------------------------------

    @GET("vault-entries/")
    suspend fun vaultEntries(): PagedResponse<VaultEntryItem>

    @GET("vault-entries/{id}/")
    suspend fun vaultEntry(@Path("id") id: Int): VaultEntryItem

    @POST("vault-entries/")
    suspend fun createVaultEntry(@Body body: VaultEntryWriteRequest): VaultEntryItem

    @PATCH("vault-entries/{id}/")
    suspend fun updateVaultEntry(@Path("id") id: Int, @Body body: VaultEntryWriteRequest): VaultEntryItem

    @DELETE("vault-entries/{id}/")
    suspend fun deleteVaultEntry(@Path("id") id: Int)

    @POST("vault-entries/{id}/reveal/")
    suspend fun revealVaultEntry(@Path("id") id: Int): VaultRevealResponse

    @POST("vault-entries/{id}/share/")
    suspend fun shareVaultEntry(@Path("id") id: Int, @Body body: AssigneeRequest): VaultEntryItem

    @DELETE("vault-entries/{id}/grants/{employeeId}/")
    suspend fun revokeVaultGrant(@Path("id") id: Int, @Path("employeeId") employeeId: Int): VaultEntryItem

    // --- Events ------------------------------------------------------------------

    @GET("events/")
    suspend fun events(): PagedResponse<EventItem>

    @GET("events/{id}/")
    suspend fun event(@Path("id") id: Int): EventItem

    @POST("events/")
    suspend fun createEvent(@Body body: EventWriteRequest): EventItem

    @PATCH("events/{id}/")
    suspend fun updateEvent(@Path("id") id: Int, @Body body: EventWriteRequest): EventItem

    @PATCH("events/{id}/financials/")
    suspend fun updateEventFinancials(@Path("id") id: Int, @Body body: EventFinancialsPatchRequest): EventItem

    @PATCH("events/{id}/coordination/")
    suspend fun updateEventCoordination(@Path("id") id: Int, @Body body: EventCoordinationPatchRequest): EventItem

    @DELETE("events/{id}/")
    suspend fun deleteEvent(@Path("id") id: Int)

    // --- Attendance --------------------------------------------------------------

    @GET("attendance/today/")
    suspend fun attendanceToday(): MyTodayResponse

    @POST("attendance/check-in/")
    suspend fun checkIn(@Body body: PunchLocationRequest): AttendanceItem

    @POST("attendance/check-out/")
    suspend fun checkOut(@Body body: PunchLocationRequest): AttendanceItem

    @GET("attendance/")
    suspend fun adminAttendance(@QueryMap filters: Map<String, String>): PagedResponse<AttendanceItem>

    @PATCH("attendance/{id}/punches/{punchId}/")
    suspend fun correctPunch(
        @Path("id") attendanceId: Int,
        @Path("punchId") punchId: Int,
        @Body body: PunchCorrectionRequest,
    ): AttendanceItem

    // --- Settings ------------------------------------------------------------------

    @GET("settings/")
    suspend fun settings(): AppSettingsItem

    @PATCH("settings/")
    suspend fun updateSettings(@Body body: SettingsPatchRequest): AppSettingsItem

    @GET("holidays/")
    suspend fun holidays(): PagedResponse<HolidayItem>

    @POST("holidays/")
    suspend fun createHoliday(@Body body: HolidayWriteRequest): HolidayItem

    @DELETE("holidays/{id}/")
    suspend fun deleteHoliday(@Path("id") id: Int)
}
