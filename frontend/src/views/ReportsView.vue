<script setup>
import { computed, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";

import { api } from "@/api/client";
import { clockTime, describeError, duration, today } from "@/lib/format";

const route = useRoute();
const router = useRouter();

const REPORTS = [
  { key: "attendance", label: "Attendance" },
  { key: "activity", label: "PC activity" },
];

const STATUSES = ["PRESENT", "LATE", "ABSENT", "LEAVE"];

const report = ref(REPORTS.some((r) => r.key === route.query.report) ? route.query.report : "attendance");
const employees = ref([]);
const filters = ref({
  employee: route.query.employee ?? "",
  department: route.query.department ?? "",
  date_from: route.query.date_from ?? today(),
  date_to: route.query.date_to ?? today(),
  status: route.query.status ?? "",
  group: route.query.group ?? "day",
});

const result = ref(null);
const offset = ref(0);
const loading = ref(false);
const exporting = ref("");
const error = ref("");
const notice = ref("");
// One day at a time is the common case, and expanding every split-shift day by default
// would bury the summary rows it exists to explain.
const expanded = ref(new Set());

const LIMIT = 100;

const rows = computed(() => result.value?.rows ?? []);
const timezone = computed(() => result.value?.timezone ?? null);
const isAttendance = computed(() => report.value === "attendance");
const departments = computed(() =>
  [...new Set(employees.value.map((employee) => employee.department).filter(Boolean))].sort(),
);

function queryParams(extra = {}) {
  const params = {
    date_from: filters.value.date_from,
    date_to: filters.value.date_to,
    employee: filters.value.employee,
    department: filters.value.department,
    ...extra,
  };
  if (isAttendance.value) {
    params.status = filters.value.status;
  } else {
    params.group = filters.value.group;
  }
  return params;
}

async function load() {
  loading.value = true;
  error.value = "";
  notice.value = "";
  try {
    const params = queryParams({ limit: LIMIT, offset: offset.value });
    result.value = isAttendance.value
      ? await api.attendanceReport(params)
      : await api.activityReport(params);
    expanded.value = new Set();
    router.replace({ query: { report: report.value, ...queryParams() } });
  } catch (err) {
    error.value = describeError(err);
    result.value = null;
  } finally {
    loading.value = false;
  }
}

async function runExport(format) {
  exporting.value = format;
  error.value = "";
  notice.value = "";
  try {
    // No limit or offset: an export is the whole filtered report, not the page on
    // screen. `detail=punches` splits days that have more than one punch (D7).
    const params = queryParams({ format });
    if (isAttendance.value) params.detail = "punches";
    const name = await api.exportReport(report.value, params);
    notice.value = `Downloaded ${name}`;
  } catch (err) {
    error.value = describeError(err);
  } finally {
    exporting.value = "";
  }
}

function selectReport(key) {
  if (report.value === key) return;
  report.value = key;
  offset.value = 0;
  load();
}

function applyFilters() {
  offset.value = 0;
  load();
}

function nextPage() {
  offset.value += LIMIT;
  load();
}

function previousPage() {
  offset.value = Math.max(0, offset.value - LIMIT);
  load();
}

function toggle(key) {
  const next = new Set(expanded.value);
  if (next.has(key)) next.delete(key);
  else next.add(key);
  expanded.value = next;
}

function locationLabel(value) {
  if (value === "INSIDE") return "Inside office";
  if (value === "OUTSIDE") return "Outside office";
  return "—";
}

watch(
  () => filters.value.group,
  () => {
    if (!isAttendance.value) applyFilters();
  },
);

onMounted(async () => {
  try {
    const list = await api.listEmployees({ status: "ACTIVE" });
    employees.value = list.results ?? list;
  } catch (err) {
    error.value = describeError(err);
  }
  await load();
});
</script>

<template>
  <section class="card">
    <header class="row">
      <h2>Reports</h2>
      <div class="chips">
        <button
          v-for="option in REPORTS"
          :key="option.key"
          type="button"
          class="chip toggle"
          :class="{ on: report === option.key }"
          @click="selectReport(option.key)"
        >
          {{ option.label }}
        </button>
      </div>
    </header>

    <form
      class="row filters"
      @submit.prevent="applyFilters"
    >
      <label>
        From
        <input
          v-model="filters.date_from"
          type="date"
        >
      </label>
      <label>
        To
        <input
          v-model="filters.date_to"
          type="date"
        >
      </label>
      <label>
        Employee
        <select v-model="filters.employee">
          <option value="">
            All
          </option>
          <option
            v-for="employee in employees"
            :key="employee.id"
            :value="employee.id"
          >
            {{ employee.name }} ({{ employee.employee_id }})
          </option>
        </select>
      </label>
      <label>
        Department
        <select v-model="filters.department">
          <option value="">
            All
          </option>
          <option
            v-for="department in departments"
            :key="department"
            :value="department"
          >
            {{ department }}
          </option>
        </select>
      </label>
      <label v-if="isAttendance">
        Status
        <select v-model="filters.status">
          <option value="">
            Any
          </option>
          <option
            v-for="status in STATUSES"
            :key="status"
            :value="status"
          >
            {{ status.charAt(0) + status.slice(1).toLowerCase() }}
          </option>
        </select>
      </label>
      <label v-else>
        Group by
        <select v-model="filters.group">
          <option value="day">
            Day
          </option>
          <option value="employee">
            Employee (range total)
          </option>
        </select>
      </label>
      <button
        type="submit"
        :disabled="loading"
      >
        Apply
      </button>
    </form>

    <div class="row">
      <button
        class="secondary"
        type="button"
        :disabled="!!exporting || loading"
        @click="runExport('csv')"
      >
        {{ exporting === "csv" ? "Exporting…" : "Export CSV" }}
      </button>
      <button
        class="secondary"
        type="button"
        :disabled="!!exporting || loading"
        @click="runExport('xlsx')"
      >
        {{ exporting === "xlsx" ? "Exporting…" : "Export Excel" }}
      </button>
      <span class="muted small">
        Exports cover the whole filtered range, not just the page below.
      </span>
    </div>

    <p
      v-if="error"
      class="error"
    >
      {{ error }}
    </p>
    <p
      v-if="notice"
      class="ok small"
    >
      {{ notice }}
    </p>
    <p v-if="loading">
      Loading…
    </p>

    <template v-else-if="result">
      <p
        v-if="!rows.length"
        class="muted"
      >
        Nothing recorded for these filters.
      </p>

      <div
        v-else-if="isAttendance"
        class="table-scroll"
      >
        <table>
          <thead>
            <tr>
              <th>Employee</th>
              <th>Date</th>
              <th>Check-in</th>
              <th>Check-out</th>
              <th>Worked</th>
              <th>Late</th>
              <th>Status</th>
              <th>Check-in location</th>
              <th>Punches</th>
            </tr>
          </thead>
          <tbody>
            <template
              v-for="row in rows"
              :key="`${row.employee_id}-${row.date}`"
            >
              <tr>
                <td>
                  {{ row.employee_name }}
                  <div class="muted small">
                    {{ row.employee_code }} · {{ row.department }}
                  </div>
                </td>
                <td>{{ row.date }}</td>
                <td>{{ clockTime(row.first_check_in_at, timezone) }}</td>
                <td>{{ clockTime(row.last_check_out_at, timezone) }}</td>
                <td>{{ duration(row.worked_seconds) }}</td>
                <td>{{ row.late_minutes ? `${row.late_minutes}m` : "—" }}</td>
                <td>
                  {{ row.status.charAt(0) + row.status.slice(1).toLowerCase() }}
                  <span
                    v-if="row.needs_review"
                    class="chip split"
                  >needs review</span>
                </td>
                <td>
                  {{ locationLabel(row.check_in_location) }}
                  <div
                    v-if="row.check_in_distance_m !== null"
                    class="muted small"
                  >
                    {{ Math.round(row.check_in_distance_m) }} m
                  </div>
                </td>
                <td>
                  <button
                    v-if="row.punch_count > 1"
                    type="button"
                    class="link"
                    @click="toggle(`${row.employee_id}-${row.date}`)"
                  >
                    {{ row.punch_count }} punches
                  </button>
                  <span v-else>{{ row.punch_count }}</span>
                </td>
              </tr>
              <tr
                v-for="punch in expanded.has(`${row.employee_id}-${row.date}`) ? row.punches : []"
                :key="`${row.employee_id}-${row.date}-${punch.sequence}`"
                class="detail"
              >
                <td>Punch {{ punch.sequence }}</td>
                <td />
                <td>{{ clockTime(punch.check_in_at, timezone) }}</td>
                <td>{{ clockTime(punch.check_out_at, timezone) }}</td>
                <td>{{ duration(punch.duration_seconds) }}</td>
                <td>{{ punch.late_minutes ? `${punch.late_minutes}m` : "—" }}</td>
                <td colspan="3">
                  {{ locationLabel(punch.check_in_location) }}
                </td>
              </tr>
            </template>
          </tbody>
        </table>
      </div>

      <div
        v-else
        class="table-scroll"
      >
        <table>
          <thead>
            <tr>
              <th>Employee</th>
              <th v-if="filters.group === 'day'">
                Date
              </th>
              <th>PC on</th>
              <th>Active</th>
              <th>Idle</th>
              <th>Top application</th>
              <th>Top website</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="row in rows"
              :key="`${row.employee_id}-${row.date ?? 'all'}`"
            >
              <td>
                {{ row.employee_name }}
                <div class="muted small">
                  {{ row.employee_code }} · {{ row.department }}
                </div>
              </td>
              <td v-if="filters.group === 'day'">
                {{ row.date }}
              </td>
              <td>{{ duration(row.pc_on_seconds) }}</td>
              <td>{{ duration(row.active_seconds) }}</td>
              <td>{{ duration(row.idle_seconds) }}</td>
              <td>
                {{ row.top_application.name || "—" }}
                <div
                  v-if="row.top_application.name"
                  class="muted small"
                >
                  {{ duration(row.top_application.seconds) }} of
                  {{ row.application_count }} {{ row.application_count === 1 ? "app" : "apps" }}
                </div>
              </td>
              <td>
                {{ row.top_website.name || "—" }}
                <div
                  v-if="row.top_website.name"
                  class="muted small"
                >
                  {{ duration(row.top_website.seconds) }} of
                  {{ row.website_count }} {{ row.website_count === 1 ? "site" : "sites" }}
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <div
        v-if="rows.length"
        class="row"
      >
        <button
          class="secondary"
          type="button"
          :disabled="offset === 0"
          @click="previousPage"
        >
          Previous
        </button>
        <button
          class="secondary"
          type="button"
          :disabled="!result.has_more"
          @click="nextPage"
        >
          Next
        </button>
        <span class="muted small">
          Rows {{ offset + 1 }}–{{ offset + rows.length }}
          <template v-if="timezone">· times in {{ timezone }}</template>
        </span>
      </div>
    </template>
  </section>
</template>

<style scoped>
.detail td {
  background: var(--bg);
  font-size: 0.85rem;
}
</style>
