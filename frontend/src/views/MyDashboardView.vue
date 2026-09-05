<script setup>
import { computed, onMounted, ref } from "vue";

import { api } from "@/api/client";
import { clockTime, describeError, duration, today } from "@/lib/format";

// §24. Everything on this page comes from /api/me/summary/, which takes no employee
// parameter at all — there is nothing here that could be pointed at somebody else.
const date = ref(today());
const summary = ref(null);
const loading = ref(false);
const error = ref("");

const activity = computed(() => summary.value?.activity ?? null);
const attendance = computed(() => summary.value?.attendance ?? null);
const timezone = computed(() => summary.value?.timezone ?? null);

async function load() {
  loading.value = true;
  error.value = "";
  try {
    summary.value = await api.mySummary({ date: date.value });
  } catch (err) {
    error.value = describeError(err);
  } finally {
    loading.value = false;
  }
}

onMounted(load);
</script>

<template>
  <section class="card">
    <header class="row">
      <h2>My dashboard</h2>
      <input
        v-model="date"
        type="date"
        @change="load"
      >
      <RouterLink to="/attendance">
        Check in / out
      </RouterLink>
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
      <p class="muted">
        {{ summary.employee.name }} · {{ summary.employee.designation || "—" }} ·
        {{ summary.employee.department || "—" }}
      </p>

      <h3>{{ summary.is_today ? "Today's attendance" : "Attendance" }}</h3>
      <div class="grid">
        <div class="stat">
          <span class="label">Status</span>
          <span class="value">{{ attendance ? attendance.status : "No record" }}</span>
        </div>
        <div class="stat">
          <span class="label">Check-in</span>
          <span class="value">{{ clockTime(attendance?.first_check_in_at, timezone) }}</span>
        </div>
        <div class="stat">
          <span class="label">Check-out</span>
          <span class="value">{{ clockTime(attendance?.last_check_out_at, timezone) }}</span>
        </div>
        <div class="stat">
          <span class="label">Leave remaining</span>
          <span class="value">{{ summary.leave.remaining }} days</span>
          <span class="muted small">
            {{ summary.leave.used }} used of {{ summary.leave.total }}
          </span>
        </div>
      </div>

      <h3>PC activity</h3>
      <div class="grid">
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

      <div
        v-if="summary.computers.length"
        class="chips"
      >
        <span
          v-for="pc in summary.computers"
          :key="pc.id"
          class="chip"
        >
          {{ pc.computer_name }} · {{ pc.status }}
        </span>
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
            <li
              v-if="!activity.top_applications.length"
              class="muted"
            >
              Nothing recorded.
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
            <li
              v-if="!activity.top_websites.length"
              class="muted"
            >
              Nothing recorded.
            </li>
          </ul>
        </div>
      </div>
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
</style>
