<script setup>
import { computed, onMounted, ref } from "vue";

import { api } from "@/api/client";
import { clockTime } from "@/lib/format";

const state = ref(null);
const timezone = ref(null);
const busy = ref(false);
const error = ref("");
const notice = ref("");
const locating = ref(false);
const lastFix = ref(null);

// Below this, a "you are 300m away" reading means very little. We still submit —
// D2 flags rather than blocks — but the employee deserves to know.
const POOR_ACCURACY_M = 100;

const checkedIn = computed(() => state.value?.checked_in === true);
const shifts = computed(() => state.value?.shifts ?? []);
const punches = computed(() => state.value?.attendance?.punches ?? []);

function describe(err) {
  const payload = err.payload;
  if (!payload) return err.message;
  if (typeof payload === "string") return payload;
  if (payload.detail) return payload.detail;
  return Object.entries(payload)
    .map(([field, messages]) => `${field}: ${[].concat(messages).join(", ")}`)
    .join(" · ");
}

async function load() {
  try {
    state.value = await api.today();
  } catch (err) {
    error.value = describe(err);
  }
}

async function loadTimezone() {
  try {
    const settings = await api.getSettings();
    timezone.value = settings.timezone;
  } catch {
    // Non-critical: clockTime() falls back to the viewer's browser timezone.
  }
}

function getPosition() {
  return new Promise((resolve, reject) => {
    if (!("geolocation" in navigator)) {
      reject(new Error("This browser does not support location services."));
      return;
    }
    locating.value = true;
    navigator.geolocation.getCurrentPosition(
      (position) => {
        locating.value = false;
        resolve({
          latitude: position.coords.latitude,
          longitude: position.coords.longitude,
          accuracy_m: position.coords.accuracy,
        });
      },
      (err) => {
        locating.value = false;
        // Distinct messages per failure: "permission denied" and "no signal" need
        // completely different actions from the employee.
        const messages = {
          1: "Location permission was denied. Enable location for this site and try again.",
          2: "Your location is unavailable. Move somewhere with a clearer signal and retry.",
          3: "Getting your location timed out. Please try again.",
        };
        reject(new Error(messages[err.code] || "Could not read your location."));
      },
      { enableHighAccuracy: true, timeout: 15000, maximumAge: 0 },
    );
  });
}

async function punch(direction) {
  error.value = "";
  notice.value = "";
  busy.value = true;
  try {
    const position = await getPosition();
    lastFix.value = position;

    if (position.accuracy_m > POOR_ACCURACY_M) {
      notice.value =
        `Your location is only accurate to about ${Math.round(position.accuracy_m)}m. ` +
        "It has been recorded along with your check-in.";
    }

    state.value = null;
    if (direction === "in") await api.checkIn(position);
    else await api.checkOut(position);

    await load();
  } catch (err) {
    error.value = describe(err);
    if (!state.value) await load();
  } finally {
    busy.value = false;
  }
}

function duration(seconds) {
  if (!seconds) return "0h 00m";
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  return `${hours}h ${String(minutes).padStart(2, "0")}m`;
}

onMounted(() => {
  loadTimezone();
  load();
});
</script>

<template>
  <section class="card checkin">
    <h2>Attendance</h2>

    <div
      v-if="state"
      class="punch-area"
    >
      <p class="muted">
        {{ state.date }} · {{ state.office.name }}
      </p>

      <button
        v-if="!checkedIn"
        class="big"
        :disabled="busy"
        @click="punch('in')"
      >
        {{ locating ? "Getting location…" : busy ? "Checking in…" : "CHECK IN" }}
      </button>
      <button
        v-else
        class="big out"
        :disabled="busy"
        @click="punch('out')"
      >
        {{ locating ? "Getting location…" : busy ? "Checking out…" : "CHECK OUT" }}
      </button>

      <p
        v-if="checkedIn"
        class="muted"
      >
        Checked in since {{ clockTime(state.open_since, timezone) }}
      </p>

      <p
        v-if="error"
        class="error"
      >
        {{ error }}
      </p>
      <p
        v-if="notice"
        class="warn"
      >
        {{ notice }}
      </p>
    </div>

    <div
      v-if="state?.attendance"
      class="summary"
    >
      <div class="grid">
        <div class="stat">
          <span class="label">Status</span>
          <span class="value">{{ state.attendance.status }}</span>
        </div>
        <div class="stat">
          <span class="label">Worked</span>
          <span class="value">{{ duration(state.attendance.worked_seconds) }}</span>
        </div>
        <div class="stat">
          <span class="label">Late</span>
          <span class="value">{{ state.attendance.late_minutes }} min</span>
        </div>
        <div class="stat">
          <span class="label">Leave left</span>
          <span class="value">{{ state.leave.remaining }}</span>
        </div>
      </div>

      <div class="table-scroll">
        <table>
          <thead>
            <tr>
              <th>#</th>
              <th>In</th>
              <th>Out</th>
              <th>Late</th>
              <th>Location</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="p in punches"
              :key="p.id"
            >
              <td>{{ p.sequence }}</td>
              <td>{{ clockTime(p.check_in_at, timezone) }}</td>
              <td>{{ clockTime(p.check_out_at, timezone) }}</td>
              <td>{{ p.late_minutes }} min</td>
              <td>
                <span :class="['badge', p.check_in_location_status === 'INSIDE' ? 'active' : 'inactive']">
                  {{ p.check_in_location_status }}
                </span>
                <span
                  v-if="p.check_in_distance_m != null"
                  class="muted small"
                >
                  {{ Math.round(p.check_in_distance_m) }}m
                </span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <p
      v-if="shifts.length"
      class="muted small"
    >
      Your schedule:
      <span
        v-for="s in shifts"
        :key="s.sequence"
        class="chip"
      >
        {{ s.start_time?.slice(0, 5) }}–{{ s.end_time?.slice(0, 5) }}
      </span>
    </p>
  </section>
</template>

<style scoped>
.checkin {
  max-width: 34rem;
  margin: 0 auto;
}
.punch-area {
  text-align: center;
  padding: 1rem 0 1.5rem;
}
button.big {
  width: 100%;
  max-width: 20rem;
  padding: 1.5rem;
  font-size: 1.3rem;
  font-weight: 700;
  letter-spacing: 0.05em;
}
button.big.out {
  background: var(--warn);
  border-color: var(--warn);
}
.warn {
  color: var(--warn);
}
.summary {
  border-top: 1px solid var(--border);
  padding-top: 1rem;
}
</style>
