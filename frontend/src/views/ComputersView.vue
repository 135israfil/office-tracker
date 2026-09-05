<script setup>
import { computed, onMounted, ref } from "vue";

import { api } from "@/api/client";

const computers = ref([]);
const employees = ref([]);
const search = ref("");
const statusFilter = ref("");
const loading = ref(false);
const error = ref("");
const formError = ref("");
const showForm = ref(false);
// The code is shown once, right after enrolment, because that is when someone is
// standing at the machine waiting to type it.
const issuedCode = ref(null);

const blankForm = () => ({ employee: "", computer_name: "" });
const form = ref(blankForm());

const online = computed(() => computers.value.filter((pc) => pc.status === "ONLINE").length);
const offline = computed(() => computers.value.filter((pc) => pc.status === "OFFLINE").length);
const pending = computed(() => computers.value.filter((pc) => !pc.is_registered).length);

function describe(err) {
  const payload = err.payload;
  if (!payload) return err.message;
  if (typeof payload === "string") return payload;
  if (payload.detail) return payload.detail;
  return Object.entries(payload)
    .map(([field, messages]) => `${field}: ${[].concat(messages).join(", ")}`)
    .join(" · ");
}

function lastSeen(value) {
  if (!value) return "never";
  return new Date(value).toLocaleString();
}

async function load() {
  loading.value = true;
  error.value = "";
  try {
    const params = { search: search.value, status: statusFilter.value };
    const [list, staff] = await Promise.all([
      api.listComputers(params),
      api.listEmployees({ status: "ACTIVE" }),
    ]);
    computers.value = list.results ?? list;
    employees.value = staff.results ?? staff;
  } catch (err) {
    error.value = describe(err);
  } finally {
    loading.value = false;
  }
}

async function enrolComputer() {
  formError.value = "";
  try {
    const created = await api.createComputer(form.value);
    issuedCode.value = { name: created.computer_name, code: created.enrollment_code };
    form.value = blankForm();
    showForm.value = false;
    await load();
  } catch (err) {
    formError.value = describe(err);
  }
}

async function reissue(computer) {
  error.value = "";
  try {
    const updated = await api.issueEnrollmentCode(computer.id);
    issuedCode.value = { name: updated.computer_name, code: updated.enrollment_code };
    await load();
  } catch (err) {
    error.value = describe(err);
  }
}

async function toggleStatus(computer) {
  error.value = "";
  try {
    if (computer.status === "DISABLED") {
      const updated = await api.enableComputer(computer.id);
      issuedCode.value = { name: updated.computer_name, code: updated.enrollment_code };
    } else {
      await api.disableComputer(computer.id);
    }
    await load();
  } catch (err) {
    error.value = describe(err);
  }
}

onMounted(load);
</script>

<template>
  <section class="card">
    <header class="row">
      <h2>Computers</h2>
      <button @click="showForm = !showForm">
        {{ showForm ? "Cancel" : "Enrol computer" }}
      </button>
    </header>

    <div class="grid">
      <div class="stat">
        <span class="label">Online</span>
        <span class="value">{{ online }}</span>
      </div>
      <div class="stat">
        <span class="label">Offline</span>
        <span class="value">{{ offline }}</span>
      </div>
      <div class="stat">
        <span class="label">Awaiting enrolment</span>
        <span class="value">{{ pending }}</span>
      </div>
    </div>

    <div
      v-if="issuedCode"
      class="card code-panel"
    >
      <p class="label">
        Enrollment code for {{ issuedCode.name }}
      </p>
      <p class="code">
        {{ issuedCode.code }}
      </p>
      <p class="muted small">
        Give this to whoever installs the agent. It works once, expires in seven days,
        and is the only thing standing between the API and an unknown device — so send
        it the way you would send a password, not in a group chat.
      </p>
      <button
        class="link"
        @click="issuedCode = null"
      >
        Done
      </button>
    </div>

    <form
      v-if="showForm"
      @submit.prevent="enrolComputer"
    >
      <div class="form-grid">
        <label>
          Employee
          <select
            v-model="form.employee"
            required
          >
            <option value="">
              Select…
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
          Computer name
          <input
            v-model="form.computer_name"
            required
            placeholder="DEV-PC-01"
          >
        </label>
      </div>
      <p
        v-if="formError"
        class="error"
      >
        {{ formError }}
      </p>
      <button type="submit">
        Create and issue code
      </button>
    </form>

    <div class="row filters">
      <label>
        Search
        <input
          v-model="search"
          placeholder="Search computer name"
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
          <option value="ONLINE">
            Online
          </option>
          <option value="IDLE">
            Idle
          </option>
          <option value="OFFLINE">
            Offline
          </option>
          <option value="DISABLED">
            Disabled
          </option>
        </select>
      </label>
      <button @click="load">
        Apply
      </button>
    </div>

    <p
      v-if="error"
      class="error"
    >
      {{ error }}
    </p>
    <p v-if="loading">
      Loading…
    </p>

    <div class="table-scroll">
      <table>
        <thead>
          <tr>
            <th>Computer</th>
            <th>Employee</th>
            <th>OS</th>
            <th>Agent</th>
            <th>Status</th>
            <th>Last heartbeat</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="computer in computers"
            :key="computer.id"
          >
            <td>{{ computer.computer_name }}</td>
            <td>{{ computer.employee_name }}</td>
            <td>{{ computer.operating_system || "—" }}</td>
            <td>{{ computer.agent_version || "—" }}</td>
            <td>
              <span
                class="badge"
                :class="computer.status === 'ONLINE' || computer.status === 'IDLE'
                  ? 'active'
                  : 'inactive'"
              >
                {{ computer.status }}
              </span>
              <span
                v-if="!computer.is_registered && computer.status !== 'DISABLED'"
                class="chip"
              >
                awaiting agent
              </span>
            </td>
            <td>{{ lastSeen(computer.last_seen_at) }}</td>
            <td class="row">
              <button
                v-if="computer.status !== 'DISABLED'"
                class="link"
                @click="reissue(computer)"
              >
                New code
              </button>
              <button
                class="link"
                @click="toggleStatus(computer)"
              >
                {{ computer.status === "DISABLED" ? "Enable" : "Disable" }}
              </button>
            </td>
          </tr>
          <tr v-if="!loading && computers.length === 0">
            <td
              colspan="7"
              class="muted"
            >
              No computers enrolled yet.
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>
</template>

<style scoped>
.code-panel {
  margin: 1rem 0;
  border-color: var(--accent);
}
.code {
  font-family: ui-monospace, "Cascadia Mono", Consolas, monospace;
  font-size: 1.6rem;
  letter-spacing: 0.15em;
  margin: 0.25rem 0 0.5rem;
}
</style>
