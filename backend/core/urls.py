"""Cross-cutting endpoints: health and the dashboards (§20, §21, §24)."""

from django.urls import path

from . import views

urlpatterns = [
    path("health/", views.health, name="health"),
    path("dashboard/", views.AdminDashboardView.as_view(), name="admin-dashboard"),
    path("dashboard/employees/", views.EmployeeRosterView.as_view(), name="employee-roster"),
    path("me/summary/", views.MySummaryView.as_view(), name="my-summary"),
]
