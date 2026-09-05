<script setup>
import { computed, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";

import { api } from "@/api/client";
import { clockTime, describeError, duration, today } from "@/lib/format";

const route = useRoute();
const router = useRouter();

const employees = ref([]);
const employeeId = ref(route.query.employee ?? "");
const date = ref(route.query.date ?? today());
const summary = ref(null);
const loading = ref(false);
const error = ref("");

const activity = computed(() => summary.value?.activity ?? null);
const attendance = computed(() => summary.value?.attendance ?? null);
const timezone = computed(() => summary.value?.timezone ?? null);

async function loadEmployees() {
  const list = await api.listEmployees({ status: "ACTIVE" });
  employees.value = list.results ?? list;
  if (!employeeId.value && employees.value.length) {
    employeeId.value = employees.value[0].id;
  }
}

async function load() {
  if (!employeeId.value) return;
  loading.value = true;
  error.value = "";
  try {
    summary.value = await api.activitySummary({ employee: employeeId.value, date: date.value });
    // Keep the URL in step so the page can be linked to and reloaded.
    router.replace({ query: { employee: employeeId.value, date: date.value } });
  } catch (err) {
    error.value = describeError(err);
    summary.value = null;
  } finally {
    loading.value = false;
  }
}

watch([employeeId, date], load);

onMounted(async () => {
  try {
    await loadEmployees();
    await load();
  } catch (err) {
    error.value = describeError(err);
  }
});
</script>

<template>
  <section class="card">
    <header class="row">
      <h2>Employee activity</h2>
      <select v-model="employeeId">
        <option
          v-for="employee in employees"
          :key="employee.id"
          :value="employee.id"
        >
          {{ employee.name }} ({{ employee.employee_id }})
        </option>
      </select>
      <input
        v-model="date"
        type="date"
      >
    </header>

    <p
      v-if="error"
      class="error"
    >
      {{ error }}
    </p>
    <p v-if="loading">
      Loading…
    </p>

    <template v-if="summary">
      <h3 class="subtitle">
        {{ summary.employee.name }} · {{ summary.date }}
      </h3>

      <div class="grid">
        <div class="stat">
          <span class="label">Attendance</span>
          <span class="value">
            {{ attendance ? attendance.status : "No record" }}
          </span>
          <span
            v-if="attendance"
            class="muted small"
          >
            {{ clockTime(attendance.first_check_in_at, timezone) }} –
            {{ clockTime(attendance.last_check_out_at, timezone) }}
          </span>
        </div>
        <div class="stat">
          <span class="label">PC on</span>
          <span class="value">{{ duration(activity.pc_on_seconds) }}</span>
        </div>
        <div class="stat">
          <span class="label">Active</span>
          <span class="value">{{ duration(activity.active_seconds) }}</span>
        </div>
        <div class="stat">
          <span class="label">Idle</span>
          <span class="value">{{ duration(activity.idle_seconds) }}</span>
        </div>
      </div>

      <div class="two-up">
        <div>
          <h4>Top applications</h4>
          <ul class="bars">
            <li
              v-for="app in activity.top_applications"
              :key="app.name"
            >
              <span>{{ app.name }}</span>
              <strong>{{ duration(app.seconds) }}</strong>
            </li>
            <li v-if="activity.other_application_seconds">
              <span class="muted">Other</span>
              <strong>{{ duration(activity.other_application_seconds) }}</strong>
            </li>
            <li
              v-if="!activity.top_applications.length"
              class="muted"
            >
              No application activity.
            </li>
          </ul>
        </div>

        <div>
          <h4>Top websites</h4>
          <ul class="bars">
            <li
              v-for="site in activity.top_websites"
              :key="site.name"
            >
              <span>{{ site.name }}</span>
              <strong>{{ duration(site.seconds) }}</strong>
            </li>
            <li v-if="activity.other_website_seconds">
              <span class="muted">Other</span>
              <strong>{{ duration(activity.other_website_seconds) }}</strong>
            </li>
            <li
              v-if="!activity.top_websites.length"
              class="muted"
            >
              No website activity.
            </li>
          </ul>
        </div>
      </div>

      <h4>Timeline</h4>
      <ol class="timeline">
        <li
          v-for="(entry, index) in activity.timeline.entries"
          :key="index"
        >
          <span class="when">{{ clockTime(entry.at, timezone) }}</span>
          <span>
            {{ entry.label }}
            <span
              v-if="entry.detail"
              class="muted"
            >/ {{ entry.detail }}</span>
          </span>
        </li>
        <li
          v-if="!activity.timeline.entries.length"
          class="muted"
        >
          Nothing recorded for this day.
        </li>
      </ol>
      <p
        v-if="activity.timeline.truncated"
        class="muted small"
      >
        {{ activity.timeline.truncated }} further entries not shown.
      </p>
    </template>
  </section>
</template>

<style scoped>
.two-up {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(16rem, 1fr));
  gap: 1.5rem;
  margin: 1rem 0;
}
.bars {
  list-style: none;
  padding: 0;
  margin: 0;
}
.bars li {
  display: flex;
  justify-content: space-between;
  gap: 1rem;
  padding: 0.35rem 0;
  border-bottom: 1px solid var(--border);
}
.timeline {
  list-style: none;
  padding: 0;
}
.timeline li {
  display: flex;
  gap: 1rem;
  padding: 0.3rem 0;
  border-bottom: 1px solid var(--border);
}
.timeline .when {
  font-variant-numeric: tabular-nums;
  color: var(--muted);
  min-width: 4.5rem;
}
</style>
