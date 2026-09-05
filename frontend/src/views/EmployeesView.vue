<script setup>
import { computed, onMounted, ref } from "vue";

import { api } from "@/api/client";

const employees = ref([]);
const settings = ref(null);
const search = ref("");
const statusFilter = ref("");
const loading = ref(false);
const error = ref("");
const formError = ref("");
const showForm = ref(false);

const blankForm = () => ({
  employee_id: "",
  name: "",
  email: "",
  password: "",
  phone: "",
  department: "",
  designation: "",
  joining_date: "",
  leave_total: "0.0",
});
const form = ref(blankForm());

const splitShiftEnabled = computed(() => settings.value?.allow_split_shift === true);

// Shift editing: one employee's shifts can be open for editing at a time, mirroring
// the single add-employee form above rather than inventing a modal system.
const editingShiftsId = ref(null);
const shiftForm = ref({ start_time: "", end_time: "", second: null });
const shiftFormError = ref("");
const savingShifts = ref(false);

async function load() {
  loading.value = true;
  error.value = "";
  try {
    const params = { search: search.value, status: statusFilter.value };
    const [list, config] = await Promise.all([api.listEmployees(params), api.getSettings()]);
    employees.value = list.results ?? list;
    settings.value = config;
  } catch (err) {
    error.value = describe(err);
  } finally {
    loading.value = false;
  }
}

function describe(err) {
  const payload = err.payload;
  if (!payload) return err.message;
  if (typeof payload === "string") return payload;
  return Object.entries(payload)
    .map(([field, messages]) => `${field}: ${[].concat(messages).join(", ")}`)
    .join(" · ");
}

async function createEmployee() {
  formError.value = "";
  try {
    await api.createEmployee(form.value);
    form.value = blankForm();
    showForm.value = false;
    await load();
  } catch (err) {
    formError.value = describe(err);
  }
}

async function toggleStatus(employee) {
  error.value = "";
  try {
    if (employee.status === "ACTIVE") await api.disableEmployee(employee.id);
    else await api.enableEmployee(employee.id);
    await load();
  } catch (err) {
    error.value = describe(err);
  }
}

function openShiftEditor(employee) {
  shiftFormError.value = "";
  if (editingShiftsId.value === employee.id) {
    editingShiftsId.value = null;
    return;
  }
  const sorted = [...employee.shifts].sort((a, b) => a.sequence - b.sequence);
  shiftForm.value = {
    start_time: sorted[0]?.start_time?.slice(0, 5) ?? "",
    end_time: sorted[0]?.end_time?.slice(0, 5) ?? "",
    second: sorted[1]
      ? { start_time: sorted[1].start_time.slice(0, 5), end_time: sorted[1].end_time.slice(0, 5) }
      : null,
  };
  editingShiftsId.value = employee.id;
}

function addSecondShift() {
  shiftForm.value.second = { start_time: "", end_time: "" };
}

function removeSecondShift() {
  shiftForm.value.second = null;
}

async function saveShifts(employee) {
  shiftFormError.value = "";
  savingShifts.value = true;
  try {
    const shifts = [{ start_time: shiftForm.value.start_time, end_time: shiftForm.value.end_time }];
    if (shiftForm.value.second) shifts.push(shiftForm.value.second);
    await api.setShifts(employee.id, shifts);
    editingShiftsId.value = null;
    await load();
  } catch (err) {
    shiftFormError.value = describe(err);
  } finally {
    savingShifts.value = false;
  }
}

onMounted(load);
</script>

<template>
  <section class="card">
    <header class="row">
      <h2>Employees</h2>
      <button @click="showForm = !showForm">
        {{ showForm ? "Cancel" : "Add employee" }}
      </button>
    </header>

    <form
      v-if="showForm"
      class="form-grid"
      @submit.prevent="createEmployee"
    >
      <label>Employee ID<input
        v-model="form.employee_id"
        required
      ></label>
      <label>Full name<input
        v-model="form.name"
        required
      ></label>
      <label>Email<input
        v-model="form.email"
        type="email"
        required
      ></label>
      <label>
        Initial password
        <input
          v-model="form.password"
          type="password"
          required
          minlength="8"
        >
      </label>
      <label>Department<input v-model="form.department"></label>
      <label>Designation<input v-model="form.designation"></label>
      <label>Joining date<input
        v-model="form.joining_date"
        type="date"
      ></label>
      <label>Leave total<input
        v-model="form.leave_total"
        type="number"
        step="0.5"
        min="0"
      ></label>
      <p
        v-if="formError"
        class="error span"
      >
        {{ formError }}
      </p>
      <button
        class="span"
        type="submit"
      >
        Create employee
      </button>
    </form>

    <div class="row filters">
      <label>
        Search
        <input
          v-model="search"
          placeholder="Search name, ID or email"
          @keyup.enter="load"
        >
      </label>
      <label>
        Status
        <select
          v-model="statusFilter"
          @change="load"
        >
          <option value="">
            All statuses
          </option>
          <option value="ACTIVE">
            Active
          </option>
          <option value="INACTIVE">
            Inactive
          </option>
        </select>
      </label>
      <button
        :disabled="loading"
        @click="load"
      >
        {{ loading ? "Loading…" : "Search" }}
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
            <th>ID</th>
            <th>Name</th>
            <th>Department</th>
            <th>Shifts</th>
            <th>Leave</th>
            <th>Status</th>
            <th />
          </tr>
        </thead>
        <tbody>
          <template
            v-for="employee in employees"
            :key="employee.id"
          >
            <tr>
              <td>{{ employee.employee_id }}</td>
              <td>
                {{ employee.name }}<br>
                <span class="muted small">{{ employee.email }}</span>
              </td>
              <td>{{ employee.department || "—" }}</td>
              <td>
                <span
                  v-for="shift in employee.shifts"
                  :key="shift.id"
                  class="chip"
                >
                  {{ shift.start_time?.slice(0, 5) }}–{{ shift.end_time?.slice(0, 5) }}
                </span>
                <span
                  v-if="employee.shifts.length > 1"
                  class="chip split"
                >split</span>
              </td>
              <td>{{ employee.leave_remaining }} / {{ employee.leave_total }}</td>
              <td>
                <span :class="['badge', employee.status.toLowerCase()]">
                  {{ employee.status }}
                </span>
              </td>
              <td class="row">
                <button
                  class="link"
                  @click="toggleStatus(employee)"
                >
                  {{ employee.status === "ACTIVE" ? "Disable" : "Enable" }}
                </button>
                <button
                  class="link"
                  @click="openShiftEditor(employee)"
                >
                  {{ editingShiftsId === employee.id ? "Close" : "Manage shifts" }}
                </button>
              </td>
            </tr>
            <tr v-if="editingShiftsId === employee.id">
              <td colspan="7">
                <form
                  class="form-grid"
                  @submit.prevent="saveShifts(employee)"
                >
                  <label>
                    Shift 1 start
                    <input
                      v-model="shiftForm.start_time"
                      type="time"
                      required
                    >
                  </label>
                  <label>
                    Shift 1 end
                    <input
                      v-model="shiftForm.end_time"
                      type="time"
                      required
                    >
                  </label>
                  <template v-if="shiftForm.second">
                    <label>
                      Shift 2 start
                      <input
                        v-model="shiftForm.second.start_time"
                        type="time"
                        required
                      >
                    </label>
                    <label>
                      Shift 2 end
                      <input
                        v-model="shiftForm.second.end_time"
                        type="time"
                        required
                      >
                    </label>
                  </template>
                  <p
                    v-if="shiftFormError"
                    class="error span"
                  >
                    {{ shiftFormError }}
                  </p>
                  <div class="row span">
                    <button
                      type="submit"
                      :disabled="savingShifts"
                    >
                      {{ savingShifts ? "Saving…" : "Save shifts" }}
                    </button>
                    <button
                      v-if="splitShiftEnabled && !shiftForm.second"
                      type="button"
                      class="secondary"
                      @click="addSecondShift"
                    >
                      Add second shift
                    </button>
                    <button
                      v-if="shiftForm.second"
                      type="button"
                      class="secondary"
                      @click="removeSecondShift"
                    >
                      Remove second shift
                    </button>
                  </div>
                </form>
              </td>
            </tr>
          </template>
          <tr v-if="!employees.length && !loading">
            <td
              colspan="7"
              class="muted"
            >
              No employees yet.
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <p class="muted small">
      Split shifts are
      <strong>{{ splitShiftEnabled ? "enabled" : "disabled" }}</strong> in settings.
    </p>
  </section>
</template>
