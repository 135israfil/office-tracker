<script setup>
import { computed, onMounted, ref } from "vue";

import { api } from "@/api/client";

const WEEKDAYS = [
  { value: 0, label: "Monday" },
  { value: 1, label: "Tuesday" },
  { value: 2, label: "Wednesday" },
  { value: 3, label: "Thursday" },
  { value: 4, label: "Friday" },
  { value: 5, label: "Saturday" },
  { value: 6, label: "Sunday" },
];

const settings = ref(null);

// Spelled out on the screen rather than left to the label, because turning this on can
// lock genuine staff out of their own attendance and the admin should read why before
// they save it.
const radiusRuleNote = computed(() =>
  settings.value?.require_check_in_inside_radius
    ? "Check-in from outside the radius is refused. Phone GPS is regularly wrong by more than the radius, so staff who really are at the office can be turned away on a bad fix."
    : "Check-in outside the radius is recorded and flagged, never blocked.",
);
const holidays = ref([]);
const message = ref("");
const error = ref("");
const saving = ref(false);
const newHoliday = ref({ date: "", name: "" });
const originalRetention = ref(null);

function describe(err) {
  const payload = err.payload;
  if (!payload) return err.message;
  if (typeof payload === "string") return payload;
  return Object.entries(payload)
    .map(([field, messages]) => `${field}: ${[].concat(messages).join(", ")}`)
    .join(" · ");
}

async function load() {
  error.value = "";
  try {
    const [config, holidayList] = await Promise.all([api.getSettings(), api.listHolidays()]);
    settings.value = config;
    originalRetention.value = config.activity_retention_days;
    holidays.value = holidayList.results ?? holidayList;
  } catch (err) {
    error.value = describe(err);
  }
}

function toggleWeekend(day) {
  const days = new Set(settings.value.weekend_days);
  if (days.has(day)) days.delete(day);
  else days.add(day);
  settings.value.weekend_days = [...days].sort((a, b) => a - b);
}

async function save() {
  saving.value = true;
  message.value = "";
  error.value = "";

  const body = { ...settings.value };
  delete body.updated_at;

  // Shortening retention permanently destroys activity, so confirm in the UI as well
  // as at the API. The server refuses without this flag either way.
  if (body.activity_retention_days < originalRetention.value) {
    const ok = window.confirm(
      `Reducing retention from ${originalRetention.value} to ${body.activity_retention_days} days ` +
        "permanently deletes activity older than the new window. Continue?",
    );
    if (!ok) {
      saving.value = false;
      return;
    }
    body.confirm_shorter_retention = true;
  }

  try {
    settings.value = await api.updateSettings(body);
    originalRetention.value = settings.value.activity_retention_days;
    message.value = "Settings saved.";
  } catch (err) {
    error.value = describe(err);
  } finally {
    saving.value = false;
  }
}

async function addHoliday() {
  error.value = "";
  try {
    await api.createHoliday(newHoliday.value);
    newHoliday.value = { date: "", name: "" };
    await load();
  } catch (err) {
    error.value = describe(err);
  }
}

async function removeHoliday(id) {
  error.value = "";
  try {
    await api.deleteHoliday(id);
    await load();
  } catch (err) {
    error.value = describe(err);
  }
}

onMounted(load);
</script>

<template>
  <section
    v-if="settings"
    class="card"
  >
    <h2>Settings</h2>

    <form @submit.prevent="save">
      <fieldset>
        <legend>Office</legend>
        <div class="form-grid">
          <label>Office name<input
            v-model="settings.office_name"
            required
          ></label>
          <label>
            Allowed radius (m)
            <input
              v-model.number="settings.radius_meters"
              type="number"
              min="10"
            >
          </label>
          <label>
            Latitude
            <input
              v-model="settings.latitude"
              type="number"
              step="0.000001"
            >
          </label>
          <label>
            Longitude
            <input
              v-model="settings.longitude"
              type="number"
              step="0.000001"
            >
          </label>
        </div>
        <label class="check">
          <input
            v-model="settings.require_check_in_inside_radius"
            type="checkbox"
          >
          Only allow check-in from inside the radius
        </label>
        <p class="muted small">
          {{ radiusRuleNote }} Check-out is never blocked either way.
        </p>
      </fieldset>

      <fieldset>
        <legend>Work schedule</legend>
        <div class="form-grid">
          <label>Timezone<input
            v-model="settings.timezone"
            required
          ></label>
          <label>
            Default start
            <input
              v-model="settings.default_start_time"
              type="time"
              required
            >
          </label>
          <label>
            Default end
            <input
              v-model="settings.default_end_time"
              type="time"
              required
            >
          </label>
        </div>

        <p class="label">
          Weekend days
        </p>
        <div class="chips">
          <button
            v-for="day in WEEKDAYS"
            :key="day.value"
            type="button"
            :class="['chip', 'toggle', { on: settings.weekend_days.includes(day.value) }]"
            @click="toggleWeekend(day.value)"
          >
            {{ day.label }}
          </button>
        </div>
        <p class="muted small">
          Non-working days. Used to decide who counts as absent. At least one day must
          remain a working day.
        </p>

        <label class="check">
          <input
            v-model="settings.allow_split_shift"
            type="checkbox"
          >
          Allow split shifts (two work windows per day)
        </label>
      </fieldset>

      <fieldset>
        <legend>Leave</legend>
        <label class="check">
          <input
            v-model="settings.allow_half_day_leave"
            type="checkbox"
          >
          Allow half-day leave (0.5 increments)
        </label>
      </fieldset>

      <fieldset>
        <legend>Activity</legend>
        <div class="form-grid">
          <label>
            Idle threshold (s)
            <input
              v-model.number="settings.idle_threshold_seconds"
              type="number"
              min="60"
            >
          </label>
          <label>
            Heartbeat (s)
            <input
              v-model.number="settings.heartbeat_interval_seconds"
              type="number"
              min="15"
            >
          </label>
          <label>
            Sync interval (s)
            <input
              v-model.number="settings.sync_interval_seconds"
              type="number"
              min="15"
            >
          </label>
          <label>
            Activity retention (days)
            <input
              v-model.number="settings.activity_retention_days"
              type="number"
              min="7"
            >
          </label>
        </div>
        <label class="check">
          <input
            v-model="settings.agent_enabled"
            type="checkbox"
          >
          Desktop agents collect activity
        </label>
        <p class="muted small">
          Unchecking this stops every agent from collecting at its next config poll.
          Agents keep reporting whether the PC is on, so the fleet can be switched back
          on from here without visiting a single machine.
        </p>
        <p class="muted small">
          Retention applies to PC activity only. Attendance, leave and audit records are
          never deleted automatically.
        </p>
      </fieldset>

      <p
        v-if="message"
        class="ok"
      >
        {{ message }}
      </p>
      <p
        v-if="error"
        class="error"
      >
        {{ error }}
      </p>
      <button
        type="submit"
        :disabled="saving"
      >
        {{ saving ? "Saving…" : "Save settings" }}
      </button>
    </form>

    <hr>

    <h3>Holidays</h3>
    <form
      class="row"
      @submit.prevent="addHoliday"
    >
      <input
        v-model="newHoliday.date"
        type="date"
        required
      >
      <input
        v-model="newHoliday.name"
        placeholder="Holiday name"
        required
      >
      <button type="submit">
        Add
      </button>
    </form>

    <ul class="holidays">
      <li
        v-for="holiday in holidays"
        :key="holiday.id"
      >
        <span>{{ holiday.date }} — {{ holiday.name }}</span>
        <button
          class="link"
          @click="removeHoliday(holiday.id)"
        >
          Remove
        </button>
      </li>
      <li
        v-if="!holidays.length"
        class="muted"
      >
        No holidays configured.
      </li>
    </ul>
  </section>
</template>
