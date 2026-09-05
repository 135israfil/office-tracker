<script setup>
import { onMounted, ref } from "vue";

import { api } from "@/api/client";
import { clockTime, describeError, duration, today } from "@/lib/format";

const date = ref(today());
const dashboard = ref(null);
const timezone = ref(null);
const roster = ref([]);
const search = ref("");
const loading = ref(false);
const error = ref("");

async function load() {
  loading.value = true;
  error.value = "";
  try {
    const [counts, employees] = await Promise.all([
      api.dashboard({ date: date.value }),
      api.roster({ date: date.value, search: search.value }),
    ]);
    dashboard.value = counts;
    timezone.value = counts.timezone;
    roster.value = employees.employees;
  } catch (err) {
    error.value = describeError(err);
  } finally {
    loading.value = false;
  }
}

// Present and Late are both "they turned up", but colouring them alike makes a
// roomful of late arrivals scan as a good day. Absent is the only red state:
// Leave is a planned, approved absence and should not read as a problem.
function attendanceBadge(status) {
  if (status === "ABSENT") return "inactive";
  if (status === "LATE") return "warn";
  return "active";
}

onMounted(load);
</script>

<template>
  <section class="card">
    <header class="row">
      <h2>Dashboard</h2>
      <input
        v-model="date"
        type="date"
        @change="load"
      >
      <button
        :disabled="loading"
        @click="load"
      >
        Refresh
      </button>
    </header>

    <p
      v-if="error"
      class="error"
    >
      {{ error }}
    </p>

    <template v-if="dashboard">
      <h3>Attendance</h3>
      <p
        v-if="!dashboard.attendance.is_working_day"
        class="muted small"
      >
        Not a working day — weekend or holiday.
      </p>
      <div class="grid">
        <div class="stat">
          <span class="label">Employees</span>
          <span class="value">{{ dashboard.attendance.employees }}</span>
        </div>
        <div class="stat">
          <span class="label">Present</span>
          <span class="value">{{ dashboard.attendance.present }}</span>
        </div>
        <div class="stat">
          <span class="label">Late</span>
          <span class="value">{{ dashboard.attendance.late }}</span>
        </div>
        <div class="stat">
          <span class="label">Absent</span>
          <span class="value">{{ dashboard.attendance.absent }}</span>
        </div>
        <div class="stat">
          <span class="label">Leave</span>
          <span class="value">{{ dashboard.attendance.leave }}</span>
        </div>
        <div class="stat">
          <span class="label">Not recorded</span>
          <span class="value">{{ dashboard.attendance.not_recorded }}</span>
          <span class="muted small">not arrived yet</span>
        </div>
      </div>

      <h3>PC status</h3>
      <div class="grid">
        <div class="stat">
          <span class="label">Online</span>
          <span class="value">{{ dashboard.computers.online }}</span>
          <span class="muted small">active + idle</span>
        </div>
        <div class="stat">
          <span class="label">Active</span>
          <span class="value">{{ dashboard.computers.active }}</span>
        </div>
        <div class="stat">
          <span class="label">Idle</span>
          <span class="value">{{ dashboard.computers.idle }}</span>
        </div>
        <div class="stat">
          <span class="label">Offline</span>
          <span class="value">{{ dashboard.computers.offline }}</span>
        </div>
        <div
          v-if="dashboard.computers.unregistered"
          class="stat"
        >
          <span class="label">Awaiting enrolment</span>
          <span class="value">{{ dashboard.computers.unregistered }}</span>
        </div>
      </div>
    </template>

    <h3>Employees</h3>
    <div class="row filters">
      <input
        v-model="search"
        placeholder="Search name"
        @keyup.enter="load"
      >
      <button @click="load">
        Apply
      </button>
    </div>

    <div class="table-scroll">
      <table>
        <thead>
          <tr>
            <th>Employee</th>
            <th>Department</th>
            <th>Attendance</th>
            <th>Check-in</th>
            <th>Check-out</th>
            <th>PC</th>
            <th>Active</th>
            <th>Idle</th>
            <th />
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="row in roster"
            :key="row.employee_id"
          >
            <td>
              {{ row.name }}
              <span class="muted small">{{ row.employee_code }}</span>
            </td>
            <td>{{ row.department || "—" }}</td>
            <td>
              <span
                v-if="row.attendance_status"
                class="badge"
                :class="attendanceBadge(row.attendance_status)"
              >
                {{ row.attendance_status }}
              </span>
              <span
                v-else
                class="muted"
              >—</span>
              <span
                v-if="row.late_minutes"
                class="muted small"
              >{{ row.late_minutes }}m late</span>
            </td>
            <td>{{ clockTime(row.first_check_in_at, timezone) }}</td>
            <td>{{ clockTime(row.last_check_out_at, timezone) }}</td>
            <td>
              <span
                v-if="row.pc_status"
                class="badge"
                :class="['ONLINE', 'IDLE'].includes(row.pc_status) ? 'active' : 'inactive'"
              >
                {{ row.pc_status }}
              </span>
              <span
                v-else
                class="muted"
              >no PC</span>
            </td>
            <td>{{ duration(row.active_seconds) }}</td>
            <td>{{ duration(row.idle_seconds) }}</td>
            <td>
              <RouterLink :to="{ name: 'activity', query: { employee: row.employee_id, date } }">
                Activity
              </RouterLink>
            </td>
          </tr>
          <tr v-if="!loading && roster.length === 0">
            <td
              colspan="9"
              class="muted"
            >
              No employees match.
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>
</template>
