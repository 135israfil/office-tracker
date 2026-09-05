<script setup>
import { onMounted, ref } from "vue";

import { api } from "@/api/client";
import { clockTime } from "@/lib/format";

const rows = ref([]);
const timezone = ref(null);
const loading = ref(false);
const error = ref("");
const filters = ref({
  date_from: "",
  date_to: "",
  status: "",
  location: "",
  needs_review: false,
});

// Correction UI: one row's punches can be expanded, and within that at most one
// punch can be under edit at a time.
const expandedRowId = ref(null);
const editingPunch = ref(null); // { attendanceId, punchId }
const correctionForm = ref({ check_in_at: "", check_out_at: "", note: "" });
const correctionError = ref("");
const savingCorrection = ref(false);

function describe(err) {
  const payload = err.payload;
  if (!payload) return err.message;
  if (typeof payload === "string") return payload;
  if (payload.detail) return payload.detail;
  return JSON.stringify(payload);
}

async function load() {
  loading.value = true;
  error.value = "";
  try {
    const params = { ...filters.value };
    if (!params.needs_review) delete params.needs_review;
    const data = await api.listAttendance(params);
    rows.value = data.results ?? data;
  } catch (err) {
    error.value = describe(err);
  } finally {
    loading.value = false;
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

function duration(seconds) {
  if (!seconds) return "—";
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  return `${hours}h ${String(minutes).padStart(2, "0")}m`;
}

function firstLocation(row) {
  return row.punches?.[0]?.check_in_location_status || "—";
}

function toggleExpand(row) {
  expandedRowId.value = expandedRowId.value === row.id ? null : row.id;
  editingPunch.value = null;
  correctionError.value = "";
}

// datetime-local inputs only speak the browser's own local time, so a punch's
// UTC instant is converted for editing and converted back on save.
function toLocalInputValue(value) {
  if (!value) return "";
  const d = new Date(value);
  const pad = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function openCorrection(attendanceId, punch) {
  correctionError.value = "";
  if (editingPunch.value?.punchId === punch.id) {
    editingPunch.value = null;
    return;
  }
  correctionForm.value = {
    check_in_at: toLocalInputValue(punch.check_in_at),
    check_out_at: toLocalInputValue(punch.check_out_at),
    note: "",
  };
  editingPunch.value = { attendanceId, punchId: punch.id };
}

async function saveCorrection() {
  if (!editingPunch.value) return;
  correctionError.value = "";
  if (!correctionForm.value.note.trim()) {
    correctionError.value = "A reason is required to correct a punch.";
    return;
  }
  savingCorrection.value = true;
  try {
    const body = {
      check_in_at: new Date(correctionForm.value.check_in_at).toISOString(),
      check_out_at: correctionForm.value.check_out_at
        ? new Date(correctionForm.value.check_out_at).toISOString()
        : null,
      note: correctionForm.value.note,
    };
    await api.correctPunch(editingPunch.value.attendanceId, editingPunch.value.punchId, body);
    editingPunch.value = null;
    await load();
  } catch (err) {
    correctionError.value = describe(err);
  } finally {
    savingCorrection.value = false;
  }
}

onMounted(() => {
  loadTimezone();
  load();
});
</script>

<template>
  <section class="card">
    <h2>All attendance</h2>

    <div class="row filters">
      <label>From<input
        v-model="filters.date_from"
        type="date"
      ></label>
      <label>To<input
        v-model="filters.date_to"
        type="date"
      ></label>
      <label>
        Status
        <select v-model="filters.status">
          <option value="">
            Any
          </option>
          <option value="PRESENT">
            Present
          </option>
          <option value="LATE">
            Late
          </option>
          <option value="ABSENT">
            Absent
          </option>
          <option value="LEAVE">
            Leave
          </option>
        </select>
      </label>
      <label>
        Location
        <select v-model="filters.location">
          <option value="">
            Any
          </option>
          <option value="INSIDE">
            Inside
          </option>
          <option value="OUTSIDE">
            Outside
          </option>
        </select>
      </label>
      <label class="check">
        <input
          v-model="filters.needs_review"
          type="checkbox"
        >
        Needs review
      </label>
      <button
        :disabled="loading"
        @click="load"
      >
        {{ loading ? "Loading…" : "Apply" }}
      </button>
    </div>

    <p
      v-if="error"
      class="error"
    >
      {{ error }}
    </p>

    <div class="table-scroll">
      <table>
        <thead>
          <tr>
            <th>Date</th>
            <th>Employee</th>
            <th>Department</th>
            <th>In</th>
            <th>Out</th>
            <th>Punches</th>
            <th>Worked</th>
            <th>Late</th>
            <th>Status</th>
            <th>Location</th>
            <th />
          </tr>
        </thead>
        <tbody>
          <template
            v-for="row in rows"
            :key="row.id"
          >
            <tr>
              <td>{{ row.date }}</td>
              <td>
                {{ row.employee_name }}<br>
                <span class="muted small">{{ row.employee_code }}</span>
              </td>
              <td>{{ row.department || "—" }}</td>
              <td>{{ clockTime(row.first_check_in_at, timezone) }}</td>
              <td>{{ clockTime(row.last_check_out_at, timezone) }}</td>
              <td>
                {{ row.punches.length }}
                <span
                  v-if="row.needs_review"
                  class="chip split"
                >review</span>
                <span
                  v-if="row.is_manually_adjusted"
                  class="chip"
                >edited</span>
              </td>
              <td>{{ duration(row.worked_seconds) }}</td>
              <td>{{ row.late_minutes || 0 }} min</td>
              <td>
                <span class="badge">{{ row.status }}</span>
                <span
                  v-if="Number(row.leave_fraction) > 0"
                  class="chip"
                >
                  leave {{ row.leave_fraction }}
                </span>
              </td>
              <td>{{ firstLocation(row) }}</td>
              <td>
                <button
                  class="link"
                  @click="toggleExpand(row)"
                >
                  {{ expandedRowId === row.id ? "Close" : "Correct" }}
                </button>
              </td>
            </tr>
            <tr v-if="expandedRowId === row.id">
              <td colspan="11">
                <table>
                  <thead>
                    <tr>
                      <th>#</th>
                      <th>In</th>
                      <th>Out</th>
                      <th />
                    </tr>
                  </thead>
                  <tbody>
                    <tr
                      v-for="punch in row.punches"
                      :key="punch.id"
                    >
                      <td>{{ punch.sequence }}</td>
                      <td>{{ clockTime(punch.check_in_at, timezone) }}</td>
                      <td>{{ clockTime(punch.check_out_at, timezone) }}</td>
                      <td>
                        <button
                          class="link"
                          @click="openCorrection(row.id, punch)"
                        >
                          {{ editingPunch?.punchId === punch.id ? "Cancel" : "Edit" }}
                        </button>
                      </td>
                    </tr>
                    <tr v-if="editingPunch && row.punches.some((p) => p.id === editingPunch.punchId)">
                      <td colspan="4">
                        <form
                          class="form-grid"
                          @submit.prevent="saveCorrection"
                        >
                          <label>
                            Check-in
                            <input
                              v-model="correctionForm.check_in_at"
                              type="datetime-local"
                              required
                            >
                          </label>
                          <label>
                            Check-out
                            <input
                              v-model="correctionForm.check_out_at"
                              type="datetime-local"
                            >
                          </label>
                          <label class="span">
                            Reason for correction
                            <input
                              v-model="correctionForm.note"
                              required
                              placeholder="Why is this being corrected?"
                            >
                          </label>
                          <p
                            v-if="correctionError"
                            class="error span"
                          >
                            {{ correctionError }}
                          </p>
                          <button
                            class="span"
                            type="submit"
                            :disabled="savingCorrection"
                          >
                            {{ savingCorrection ? "Saving…" : "Save correction" }}
                          </button>
                        </form>
                      </td>
                    </tr>
                  </tbody>
                </table>
              </td>
            </tr>
          </template>
          <tr v-if="!rows.length && !loading">
            <td
              colspan="11"
              class="muted"
            >
              No attendance records match these filters.
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>
</template>
