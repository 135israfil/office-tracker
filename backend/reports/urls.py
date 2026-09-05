"""Report endpoints (§28: `GET /api/reports/`)."""

from django.urls import path

from . import views

urlpatterns = [
    path("attendance/", views.AttendanceReportView.as_view(), name="report-attendance"),
    path("activity/", views.ActivityReportView.as_view(), name="report-activity"),
    # One export view for both reports, so a new report gets its export for free and
    # the two can never drift apart in how they name files or audit themselves.
    path("<str:report>/export/", views.ReportExportView.as_view(), name="report-export"),
]
