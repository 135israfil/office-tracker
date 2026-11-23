<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";

import { api } from "@/api/client";
import { clockTime, describeError, duration, today } from "@/lib/format";

const route = useRoute();
const router = useRouter();

const employees = ref([]);
const employeeId = ref(route.query.employee ?? "");
const date = ref(route.query.date ?? today());
const summary = ref(null);
const screenshots = ref([]);
// Keyed by screenshot id rather than held on each screenshot object, so a thumbnail
// that is still loading (or failed) doesn't need a placeholder value threaded through
// `screenshots` itself — the template just checks whether this map has an entry yet.
const thumbnails = ref({});
const loading = ref(false);
const error = ref("");

function revokeThumbnails() {
  for (const url of Object.values(thumbnails.value)) URL.revokeObjectURL(url);
  thumbnails.value = {};
}

async function loadThumbnails(shots) {
  // One blob fetch per screenshot, in parallel — there is no audit log or special
  // rate limit on the view action to economise against (see client.js), only the
  // ordinary per-user API throttle every other endpoint already gets.
  await Promise.all(
    shots.map(async (shot) => {
      try {
        thumbnails.value[shot.id] = await api.viewScreenshotImage(shot.id);
      } catch {
        // A single broken thumbnail (e.g. purged by retention between the list
        // call and this one) just stays absent — the tile falls back to its
        // time/computer caption rather than losing the whole grid.
      }
    }),
  );
}

const activity = computed(() => summary.value?.activity ?? null);
const attendance = computed(() => summary.value?.attendance ?? null);
const timezone = computed(() => summary.value?.timezone ?? null);

// Matches the agent's own gray/green/amber vocabulary (desktop-agent/agent/tray.py's
// COLOURS) so "off/active/idle" reads the same way in the tray icon and the web report.
const STRIP_COLOR = { O: "var(--border-strong)", A: "var(--ok)", I: "var(--warn)" };
const HOUR_LABELS = Array.from({ length: 13 }, (_, i) => `${String(i * 2).padStart(2, "0")}:00`);

// 1440 per-minute states compress to a handful of colour stops — a CSS gradient draws a
// crisp full-width strip without creating 1440 DOM nodes.
const timelineGradient = computed(() => {
  const buckets = activity.value?.minute_buckets;
  if (!buckets?.length) return null;
  const total = buckets.length;
  const stops = [];
  let i = 0;
  while (i < total) {
    const code = buckets[i];
    let j = i;
    while (j < total && buckets[j] === code) j++;
    const color = STRIP_COLOR[code] ?? STRIP_COLOR.O;
    stops.push(`${color} ${(i / total) * 100}%`, `${color} ${(j / total) * 100}%`);
    i = j;
  }
  return `linear-gradient(to right, ${stops.join(", ")})`;
});

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
  revokeThumbnails();
  try {
    const [daySummary, shots] = await Promise.all([
      api.activitySummary({ employee: employeeId.value, date: date.value }),
      api.listScreenshots({ employee: employeeId.value, date: date.value }),
    ]);
    summary.value = daySummary;
    screenshots.value = shots.results ?? shots;
    // Keep the URL in step so the page can be linked to and reloaded.
    router.replace({ query: { employee: employeeId.value, date: date.value } });
    loadThumbnails(screenshots.value);
  } catch (err) {
    error.value = describeError(err);
    summary.value = null;
    screenshots.value = [];
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

onBeforeUnmount(revokeThumbnails);
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

      <h4>24-hour activity</h4>
      <div class="legend">
        <span><i class="swatch off" />Off</span>
        <span><i class="swatch active" />Active</span>
        <span><i class="swatch idle" />Idle</span>
      </div>
      <div
        v-if="timelineGradient"
        class="timeline-strip"
        :style="{ background: timelineGradient }"
      />
      <p
        v-else
        class="muted"
      >
        Nothing recorded for this day.
      </p>
      <div class="timeline-ticks">
        <span
          v-for="label in HOUR_LABELS"
          :key="label"
        >{{ label }}</span>
      </div>

      <div class="two-up">
        <div>
          <h4>Applications</h4>
          <table class="activity-table">
            <thead>
              <tr>
                <th>Application</th>
                <th>Time</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="app in activity.top_applications"
                :key="app.name"
              >
                <td>{{ app.name }}</td>
                <td>{{ duration(app.seconds) }}</td>
              </tr>
              <tr v-if="activity.other_application_seconds">
                <td class="muted">
                  Other
                </td>
                <td>{{ duration(activity.other_application_seconds) }}</td>
              </tr>
              <tr v-if="!activity.top_applications.length && !activity.other_application_seconds">
                <td
                  colspan="2"
                  class="muted"
                >
                  No application activity.
                </td>
              </tr>
            </tbody>
          </table>
        </div>

        <div>
          <h4>Websites</h4>
          <table class="activity-table">
            <thead>
              <tr>
                <th>Website</th>
                <th>Time</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="site in activity.top_websites"
                :key="site.name"
              >
                <td>{{ site.name }}</td>
                <td>{{ duration(site.seconds) }}</td>
              </tr>
              <tr v-if="activity.other_website_seconds">
                <td class="muted">
                  Other
                </td>
                <td>{{ duration(activity.other_website_seconds) }}</td>
              </tr>
              <tr v-if="!activity.top_websites.length && !activity.other_website_seconds">
                <td
                  colspan="2"
                  class="muted"
                >
                  No website activity.
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <h4>Screenshots</h4>
      <div
        v-if="screenshots.length"
        class="screenshot-grid"
      >
        <RouterLink
          v-for="shot in screenshots"
          :key="shot.id"
          :to="`/screenshots/${shot.id}`"
          class="screenshot-tile"
        >
          <img
            v-if="thumbnails[shot.id]"
            :src="thumbnails[shot.id]"
            alt=""
            class="screenshot-thumb"
          >
          <div
            v-else
            class="screenshot-thumb screenshot-thumb--placeholder"
          />
          <span class="time">{{ clockTime(shot.captured_at, timezone) }}</span>
          <span class="muted small">{{ shot.computer_name }}</span>
        </RouterLink>
      </div>
      <p
        v-else
        class="muted"
      >
        No screenshots captured for this day.
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
.legend {
  display: flex;
  gap: 1.25rem;
  align-items: center;
  margin: 0.5rem 0;
  font-size: 0.85rem;
  color: var(--muted);
}
.swatch {
  display: inline-block;
  width: 0.7rem;
  height: 0.7rem;
  border-radius: 2px;
  margin-right: 0.35rem;
  vertical-align: middle;
}
.swatch.off {
  background: var(--border-strong);
}
.swatch.active {
  background: var(--ok);
}
.swatch.idle {
  background: var(--warn);
}
.timeline-strip {
  height: 28px;
  border-radius: 6px;
  border: 1px solid var(--border);
}
.timeline-ticks {
  display: flex;
  justify-content: space-between;
  font-size: 0.75rem;
  font-variant-numeric: tabular-nums;
  color: var(--muted);
  margin-top: 0.25rem;
}
.activity-table {
  width: 100%;
  border-collapse: collapse;
}
.activity-table th,
.activity-table td {
  text-align: left;
  padding: 0.4rem 0.2rem;
  border-bottom: 1px solid var(--border);
}
.activity-table th {
  font-size: 0.75rem;
  font-weight: 600;
  color: var(--muted);
  text-transform: uppercase;
  letter-spacing: 0.02em;
}
.activity-table th:last-child,
.activity-table td:last-child {
  text-align: right;
  font-variant-numeric: tabular-nums;
}
.screenshot-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(9rem, 1fr));
  gap: 0.75rem;
  margin: 0.5rem 0 1rem;
}
.screenshot-tile {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.3rem;
  padding: 0.5rem;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  text-decoration: none;
  color: inherit;
}
.screenshot-thumb {
  width: 100%;
  aspect-ratio: 16 / 9;
  object-fit: cover;
  border-radius: var(--radius-sm);
  background: var(--surface-sunken);
}
.screenshot-thumb--placeholder {
  animation: screenshot-thumb-pulse 1.2s ease-in-out infinite;
}
@keyframes screenshot-thumb-pulse {
  0%,
  100% {
    opacity: 0.5;
  }
  50% {
    opacity: 0.9;
  }
}
.screenshot-tile .time {
  font-variant-numeric: tabular-nums;
  font-weight: 600;
}
</style>
