from django.contrib import admin
from django.urls import include, path
from rest_framework.routers import DefaultRouter

from activities.views import ActivitySummaryView, ActivityViewSet
from attendance.attendance_views import (
    AttendanceViewSet,
    CheckInView,
    CheckOutView,
    MarkLeaveView,
    MyAttendanceView,
    MyTodayView,
)
from attendance.views import AppSettingsView, HolidayViewSet
from computers.agent_views import (
    AgentConfigView,
    AgentHeartbeatView,
    AgentRegisterView,
    AgentScreenshotUploadView,
    AgentSyncView,
)
from computers.views import ComputerViewSet
from employees.views import EmployeeViewSet, LeaveAdjustmentViewSet
from events.views import EventViewSet
from screenshots.views import ScreenshotCaptureViewSet
from tasks.views import AssignableEmployeesView, TaskViewSet
from vault.views import VaultEntryViewSet

router = DefaultRouter()
router.register("employees", EmployeeViewSet, basename="employee")
router.register("leave-adjustments", LeaveAdjustmentViewSet, basename="leave-adjustment")
router.register("holidays", HolidayViewSet, basename="holiday")
router.register("attendance", AttendanceViewSet, basename="attendance")
router.register("computers", ComputerViewSet, basename="computer")
router.register("activity", ActivityViewSet, basename="activity")
router.register("tasks", TaskViewSet, basename="task")
router.register("vault-entries", VaultEntryViewSet, basename="vault-entry")
router.register("events", EventViewSet, basename="event")
router.register("screenshots", ScreenshotCaptureViewSet, basename="screenshot")

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include("core.urls")),
    path("api/auth/", include("accounts.urls")),
    path("api/settings/", AppSettingsView.as_view(), name="app-settings"),
    path("api/attendance/check-in/", CheckInView.as_view(), name="check-in"),
    path("api/attendance/check-out/", CheckOutView.as_view(), name="check-out"),
    path("api/attendance/my/", MyAttendanceView.as_view(), name="my-attendance"),
    path("api/attendance/today/", MyTodayView.as_view(), name="my-today"),
    path("api/attendance/mark-leave/", MarkLeaveView.as_view(), name="mark-leave"),
    # Agent endpoints use device-token auth, never sessions (§29).
    path("api/agent/register/", AgentRegisterView.as_view(), name="agent-register"),
    path("api/agent/heartbeat/", AgentHeartbeatView.as_view(), name="agent-heartbeat"),
    path("api/agent/sync/", AgentSyncView.as_view(), name="agent-sync"),
    path("api/agent/config/", AgentConfigView.as_view(), name="agent-config"),
    path("api/agent/screenshot/", AgentScreenshotUploadView.as_view(), name="agent-screenshot"),
    path("api/activity/summary/", ActivitySummaryView.as_view(), name="activity-summary"),
    path("api/reports/", include("reports.urls")),
    # Listed before the router include: "tasks/<pk>/" would otherwise swallow this
    # path first, since DRF's default pk pattern matches any non-slash segment.
    path(
        "api/tasks/assignable-employees/",
        AssignableEmployeesView.as_view(),
        name="assignable-employees",
    ),
    path("api/", include(router.urls)),
]
