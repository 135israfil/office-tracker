// Single place that knows how to talk to the backend.
// Session cookies are used for the web app, so every request sends credentials
// and carries the CSRF token Django expects on unsafe methods.

const BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000/api";

function getCookie(name) {
  // Split rather than build a regex: cookie names would need escaping, and a
  // backslash class in a template literal silently loses its meaning.
  const prefix = `${name}=`;
  for (const part of document.cookie.split(";")) {
    const cookie = part.trim();
    if (cookie.startsWith(prefix)) {
      return decodeURIComponent(cookie.slice(prefix.length));
    }
  }
  return null;
}

async function fetchJson(url, { method = "GET", headers, body } = {}) {
  const response = await fetch(url, { method, credentials: "include", headers, body });

  const payload = response.status === 204 ? null : await response.json().catch(() => null);

  if (!response.ok) {
    const error = new Error(`Request failed with status ${response.status}`);
    error.status = response.status;
    error.payload = payload;
    throw error;
  }
  return payload;
}

export async function request(path, { method = "GET", body, ...options } = {}) {
  const headers = { Accept: "application/json", ...options.headers };

  if (body !== undefined) {
    headers["Content-Type"] = "application/json";
  }
  if (!["GET", "HEAD", "OPTIONS"].includes(method)) {
    const csrf = getCookie("csrftoken");
    if (csrf) headers["X-CSRFToken"] = csrf;
  }

  const payload = await fetchJson(`${BASE_URL}${path}`, {
    method,
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
  });

  // DRF's PageNumberPagination caps every list response at PAGE_SIZE (25, see
  // backend/config/settings.py) and links the rest through `next`. Every list view in
  // this app expects `.results` to be the whole collection, so pagination is followed
  // here, once, rather than in each view that lists something.
  if (payload && Array.isArray(payload.results) && "next" in payload) {
    let results = payload.results;
    let next = payload.next;
    while (next) {
      const page = await fetchJson(next, { headers });
      results = results.concat(page.results);
      next = page.next;
    }
    return { ...payload, results, next: null };
  }

  return payload;
}

// Exports are files, not JSON, so they cannot go through `request()`. The download is
// still a credentialed fetch rather than a plain link: a link would send the request
// without the session cookie rules the rest of the app relies on, and would give no way
// to show the server's error message when the range is refused.
export async function download(path) {
  const response = await fetch(`${BASE_URL}${path}`, {
    method: "GET",
    credentials: "include",
    headers: { Accept: "*/*" },
  });

  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    const error = new Error(`Request failed with status ${response.status}`);
    error.status = response.status;
    error.payload = payload;
    throw error;
  }

  // The server names the file; guessing here would produce "download" or a name that
  // disagreed with the range actually exported.
  const disposition = response.headers.get("Content-Disposition") ?? "";
  const match = /filename="([^"]+)"/.exec(disposition);
  const name = match ? match[1] : "report";

  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = name;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  // Revoking immediately can cancel the download in some browsers; a tick is enough.
  setTimeout(() => URL.revokeObjectURL(url), 1000);
  return name;
}

// A screenshot's image is served only by the admin-only, audit-logged `view`
// action — never a plain <img src>, which would bypass the session cookie
// rules `request()` relies on and leave no way to surface a 403/404. Returns
// an object URL the caller is responsible for revoking once the <img> using
// it unmounts.
export async function fetchImageObjectUrl(path) {
  const response = await fetch(`${BASE_URL}${path}`, {
    method: "GET",
    credentials: "include",
    headers: { Accept: "image/*" },
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    const error = new Error(`Request failed with status ${response.status}`);
    error.status = response.status;
    error.payload = payload;
    throw error;
  }
  const blob = await response.blob();
  return URL.createObjectURL(blob);
}

function query(params = {}) {
  const search = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "") search.append(key, value);
  });
  const qs = search.toString();
  return qs ? `?${qs}` : "";
}

export const api = {
  health: () => request("/health/"),

  // Auth
  csrf: () => request("/auth/csrf/"),
  login: (email, password) =>
    request("/auth/login/", { method: "POST", body: { email, password } }),
  logout: () => request("/auth/logout/", { method: "POST" }),
  me: () => request("/auth/me/"),

  // Employees
  listEmployees: (params) => request(`/employees/${query(params)}`),
  getEmployee: (id) => request(`/employees/${id}/`),
  createEmployee: (body) => request("/employees/", { method: "POST", body }),
  updateEmployee: (id, body) => request(`/employees/${id}/`, { method: "PATCH", body }),
  disableEmployee: (id) => request(`/employees/${id}/disable/`, { method: "POST" }),
  enableEmployee: (id) => request(`/employees/${id}/enable/`, { method: "POST" }),
  setShifts: (id, shifts) =>
    request(`/employees/${id}/shifts/`, { method: "PUT", body: { shifts } }),

  // Leave
  listLeaveAdjustments: (params) => request(`/leave-adjustments/${query(params)}`),
  adjustLeave: (body) => request("/leave-adjustments/", { method: "POST", body }),

  // Attendance
  today: () => request("/attendance/today/"),
  checkIn: (position) => request("/attendance/check-in/", { method: "POST", body: position }),
  checkOut: (position) => request("/attendance/check-out/", { method: "POST", body: position }),
  myAttendance: (params) => request(`/attendance/my/${query(params)}`),
  listAttendance: (params) => request(`/attendance/${query(params)}`),
  markLeave: (body) => request("/attendance/mark-leave/", { method: "POST", body }),
  correctPunch: (attendanceId, punchId, body) =>
    request(`/attendance/${attendanceId}/punches/${punchId}/`, { method: "PATCH", body }),

  // Dashboards and activity (§20-§24)
  dashboard: (params) => request(`/dashboard/${query(params)}`),
  roster: (params) => request(`/dashboard/employees/${query(params)}`),
  mySummary: (params) => request(`/me/summary/${query(params)}`),
  activitySummary: (params) => request(`/activity/summary/${query(params)}`),
  listActivity: (params) => request(`/activity/${query(params)}`),

  // Reports and export (§25, §26)
  attendanceReport: (params) => request(`/reports/attendance/${query(params)}`),
  activityReport: (params) => request(`/reports/activity/${query(params)}`),
  exportReport: (report, params) => download(`/reports/${report}/export/${query(params)}`),

  // Computers (§12)
  listComputers: (params) => request(`/computers/${query(params)}`),
  createComputer: (body) => request("/computers/", { method: "POST", body }),
  issueEnrollmentCode: (id) => request(`/computers/${id}/issue-code/`, { method: "POST" }),
  disableComputer: (id) => request(`/computers/${id}/disable/`, { method: "POST" }),
  enableComputer: (id) => request(`/computers/${id}/enable/`, { method: "POST" }),

  // Tasks
  // Minimal, non-admin-safe employee directory for the assignee picker — not
  // listEmployees, which is admin-only and exposes full HR fields.
  listAssignableEmployees: () => request("/tasks/assignable-employees/"),
  listTasks: (params) => request(`/tasks/${query(params)}`),
  getTask: (id) => request(`/tasks/${id}/`),
  createTask: (body) => request("/tasks/", { method: "POST", body }),
  updateTask: (id, body) => request(`/tasks/${id}/`, { method: "PATCH", body }),
  deleteTask: (id) => request(`/tasks/${id}/`, { method: "DELETE" }),
  addTaskAssignee: (id, employeeId) =>
    request(`/tasks/${id}/add_assignee/`, { method: "POST", body: { employee: employeeId } }),
  removeTaskAssignee: (id, employeeId) =>
    request(`/tasks/${id}/assignees/${employeeId}/`, { method: "DELETE" }),

  // Vault (work credential store)
  listVaultEntries: (params) => request(`/vault-entries/${query(params)}`),
  getVaultEntry: (id) => request(`/vault-entries/${id}/`),
  createVaultEntry: (body) => request("/vault-entries/", { method: "POST", body }),
  updateVaultEntry: (id, body) => request(`/vault-entries/${id}/`, { method: "PATCH", body }),
  deleteVaultEntry: (id) => request(`/vault-entries/${id}/`, { method: "DELETE" }),
  revealVaultEntry: (id) => request(`/vault-entries/${id}/reveal/`, { method: "POST" }),
  shareVaultEntry: (id, employeeId) =>
    request(`/vault-entries/${id}/share/`, { method: "POST", body: { employee: employeeId } }),
  revokeVaultEntryGrant: (id, employeeId) =>
    request(`/vault-entries/${id}/grants/${employeeId}/`, { method: "DELETE" }),

  // Calendar events
  listEvents: (params) => request(`/events/${query(params)}`),
  getEvent: (id) => request(`/events/${id}/`),
  createEvent: (body) => request("/events/", { method: "POST", body }),
  updateEvent: (id, body) => request(`/events/${id}/`, { method: "PATCH", body }),
  updateEventFinancials: (id, body) =>
    request(`/events/${id}/financials/`, { method: "PATCH", body }),
  updateEventCoordination: (id, body) =>
    request(`/events/${id}/coordination/`, { method: "PATCH", body }),
  deleteEvent: (id) => request(`/events/${id}/`, { method: "DELETE" }),

  // Screenshots (admin-only; the captured employee never gets API access)
  listScreenshots: (params) => request(`/screenshots/${query(params)}`),
  getScreenshot: (id) => request(`/screenshots/${id}/`),
  viewScreenshotImage: (id) => fetchImageObjectUrl(`/screenshots/${id}/view/`),

  // Settings and holidays
  getSettings: () => request("/settings/"),
  updateSettings: (body) => request("/settings/", { method: "PATCH", body }),
  listHolidays: (params) => request(`/holidays/${query(params)}`),
  createHoliday: (body) => request("/holidays/", { method: "POST", body }),
  deleteHoliday: (id) => request(`/holidays/${id}/`, { method: "DELETE" }),
};
