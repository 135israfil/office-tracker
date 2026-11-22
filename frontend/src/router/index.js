import { createRouter, createWebHistory } from "vue-router";

import { useAuthStore } from "@/stores/auth";

const routes = [
  { path: "/login", name: "login", component: () => import("@/views/LoginView.vue") },
  {
    path: "/",
    name: "home",
    component: () => import("@/views/HomeView.vue"),
    meta: { requiresAuth: true },
  },
  {
    // The landing page differs by role, so the route resolves the component rather
    // than the guard redirecting: an employee never sees an admin URL flash past.
    path: "/dashboard",
    name: "dashboard",
    component: () => import("@/views/DashboardView.vue"),
    meta: { requiresAuth: true, requiresAdmin: true },
  },
  {
    path: "/my",
    name: "my-dashboard",
    component: () => import("@/views/MyDashboardView.vue"),
    meta: { requiresAuth: true },
  },
  {
    path: "/activity",
    name: "activity",
    component: () => import("@/views/ActivityView.vue"),
    meta: { requiresAuth: true, requiresAdmin: true },
  },
  {
    // Both roles use this, unlike most routes below: any employee can create and
    // be assigned tasks, not just admins.
    path: "/tasks",
    name: "tasks",
    component: () => import("@/views/TasksView.vue"),
    meta: { requiresAuth: true },
  },
  {
    path: "/tasks/:id",
    name: "task-detail",
    component: () => import("@/views/TaskDetailView.vue"),
    meta: { requiresAuth: true },
  },
  {
    // Both roles use this, like /tasks: any employee has their own credential
    // entries, not just admins.
    path: "/vault",
    name: "vault",
    component: () => import("@/views/VaultView.vue"),
    meta: { requiresAuth: true },
  },
  {
    path: "/vault/:id",
    name: "vault-entry-detail",
    component: () => import("@/views/VaultEntryDetailView.vue"),
    meta: { requiresAuth: true },
  },
  {
    // Both roles use this, like /tasks and /vault: any employee has their own
    // calendar, not just admins.
    path: "/events",
    name: "events",
    component: () => import("@/views/EventsView.vue"),
    meta: { requiresAuth: true },
  },
  {
    path: "/events/:id",
    name: "event-detail",
    component: () => import("@/views/EventDetailView.vue"),
    meta: { requiresAuth: true },
  },
  {
    // Admin-only, like /activity, which is the only place a link to this
    // route exists now — screenshots are browsed per employee/day from the
    // activity grid, not from their own nav entry.
    path: "/screenshots/:id",
    name: "screenshot-detail",
    component: () => import("@/views/ScreenshotDetailView.vue"),
    meta: { requiresAuth: true, requiresAdmin: true },
  },
  {
    path: "/attendance",
    name: "attendance",
    component: () => import("@/views/CheckInView.vue"),
    meta: { requiresAuth: true },
  },
  {
    path: "/admin/attendance",
    name: "admin-attendance",
    component: () => import("@/views/AttendanceAdminView.vue"),
    meta: { requiresAuth: true, requiresAdmin: true },
  },
  {
    path: "/reports",
    name: "reports",
    component: () => import("@/views/ReportsView.vue"),
    meta: { requiresAuth: true, requiresAdmin: true },
  },
  {
    path: "/employees",
    name: "employees",
    component: () => import("@/views/EmployeesView.vue"),
    meta: { requiresAuth: true, requiresAdmin: true },
  },
  {
    path: "/computers",
    name: "computers",
    component: () => import("@/views/ComputersView.vue"),
    meta: { requiresAuth: true, requiresAdmin: true },
  },
  {
    path: "/settings",
    name: "settings",
    component: () => import("@/views/SettingsView.vue"),
    meta: { requiresAuth: true, requiresAdmin: true },
  },
];

const router = createRouter({ history: createWebHistory(), routes });

router.beforeEach(async (to) => {
  const auth = useAuthStore();
  if (!auth.checked) await auth.bootstrap();

  if (to.meta.requiresAuth && !auth.isAuthenticated) {
    return { name: "login", query: { next: to.fullPath } };
  }
  // Client-side guards are for navigation only; the server enforces the real rule.
  if (to.meta.requiresAdmin && !auth.isAdmin) {
    return { name: "home" };
  }
  if (to.name === "login" && auth.isAuthenticated) {
    return { name: "home" };
  }
  return true;
});

export default router;
