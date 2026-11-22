<script setup>
import { computed, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";

import { api } from "@/api/client";
import RichTextEditor from "@/components/RichTextEditor.vue";
import { describeError } from "@/lib/format";
import { useAuthStore } from "@/stores/auth";

const BOOKING_STATUSES = ["ON_COMMUNICATION", "LOCKED", "DONE"];
const BOOKING_STATUS_LABEL = {
  ON_COMMUNICATION: "On communication",
  LOCKED: "Locked",
  DONE: "Done",
};
const DOCUMENT_STATUSES = [
  "VERBAL_COMMUNICATION",
  "PROPOSAL_SENT",
  "WORK_ORDER",
  "VERBAL_CONFIRMATION",
  "INVOICE_SENT",
];
const DOCUMENT_STATUS_LABEL = {
  VERBAL_COMMUNICATION: "Verbal communication",
  PROPOSAL_SENT: "Proposal sent",
  WORK_ORDER: "Work order",
  VERBAL_CONFIRMATION: "Verbal confirmation",
  INVOICE_SENT: "Invoice sent",
};
const FINANCIAL_STATUSES = ["ADVANCE", "PARTIAL_PAID", "FULL_PAID"];
const FINANCIAL_STATUS_LABEL = {
  ADVANCE: "Advance",
  PARTIAL_PAID: "Partial paid",
  FULL_PAID: "Full paid",
};

const route = useRoute();
const router = useRouter();
const auth = useAuthStore();

const event = ref(null);
const employees = ref([]);
const loading = ref(false);
const error = ref("");
const saveError = ref("");
const financialsError = ref("");

// Same reason the vault's reveal state is a separate ref from the plain record:
// the select binds to a plain id, but `event.assigned_lead` is the nested
// {id, name, employee_id} stub the API reads back.
const assignedLeadId = ref("");

const myEmployeeId = computed(() => auth.user?.employee?.id ?? null);
const isOwner = computed(() => event.value && myEmployeeId.value === event.value.owner.id);
// Assigned lead and booking status are a second, narrower admin override
// (see events/models.py): any admin may set them on any event, same as the
// owner can on their own — unlike every other field, which stays owner-only.
const canCoordinate = computed(() => isOwner.value || auth.isAdmin);

async function load() {
  loading.value = true;
  error.value = "";
  try {
    const [loadedEvent, employeeList] = await Promise.all([
      api.getEvent(route.params.id),
      api.listAssignableEmployees(),
    ]);
    event.value = loadedEvent;
    employees.value = employeeList;
    assignedLeadId.value = loadedEvent.assigned_lead?.id ?? "";
  } catch (err) {
    error.value = describeError(err);
  } finally {
    loading.value = false;
  }
}

async function save(patch) {
  saveError.value = "";
  try {
    event.value = await api.updateEvent(event.value.id, patch);
  } catch (err) {
    saveError.value = describeError(err);
  }
}

async function saveFinancials(patch) {
  financialsError.value = "";
  try {
    event.value = await api.updateEventFinancials(event.value.id, patch);
  } catch (err) {
    financialsError.value = describeError(err);
  }
}

// The owner edits these through the ordinary PATCH; a non-owner admin must
// use the dedicated coordination action instead (see events/models.py).
async function saveCoordination(patch) {
  saveError.value = "";
  try {
    event.value = isOwner.value
      ? await api.updateEvent(event.value.id, patch)
      : await api.updateEventCoordination(event.value.id, patch);
  } catch (err) {
    saveError.value = describeError(err);
  }
}

function saveAssignedLead() {
  saveCoordination({ assigned_lead_id: assignedLeadId.value || null });
}

// The editor emits on every keystroke ("change input undo redo"), so saving
// straight off that would send one PATCH per character — debounced instead,
// the same autosave pattern a rich text field needs regardless of framework.
let setupSaveTimer = null;
function updateSetup(value) {
  event.value.setup = value;
  clearTimeout(setupSaveTimer);
  setupSaveTimer = setTimeout(() => save({ setup: value }), 800);
}

async function deleteEvent() {
  try {
    await api.deleteEvent(event.value.id);
    router.push({ name: "events" });
  } catch (err) {
    error.value = describeError(err);
  }
}

watch(() => route.params.id, load);
onMounted(load);
</script>

<template>
  <section class="card">
    <p
      v-if="error"
      class="error"
    >
      {{ error }}
    </p>
    <p v-if="loading">
      Loading…
    </p>

    <template v-if="event">
      <header class="row">
        <h2>{{ event.title }}</h2>
        <button
          v-if="isOwner"
          class="secondary"
          @click="deleteEvent"
        >
          Delete
        </button>
      </header>
      <p
        v-if="event.last_admin_view"
        class="muted small"
      >
        Last viewed by an admin ({{ event.last_admin_view.admin }}) on
        {{ new Date(event.last_admin_view.at).toLocaleString() }}.
      </p>

      <div class="event-form">
        <label class="span">
          Title
          <input
            v-model="event.title"
            :disabled="!isOwner"
            @change="save({ title: event.title })"
          >
        </label>

        <h4 class="span section-heading">
          Booking
        </h4>
        <label>
          Agency name
          <input
            v-model="event.agency_name"
            :disabled="!isOwner"
            @change="save({ agency_name: event.agency_name })"
          >
        </label>
        <label>
          Venue name
          <input
            v-model="event.venue_name"
            :disabled="!isOwner"
            @change="save({ venue_name: event.venue_name })"
          >
        </label>
        <p
          v-if="auth.isAdmin && !isOwner"
          class="muted small span coordination-note"
        >
          Assigned lead and status can be set by any admin; the rest of this event is
          owner-only.
        </p>
        <label>
          Assigned lead
          <select
            v-model="assignedLeadId"
            :disabled="!canCoordinate"
            @change="saveAssignedLead"
          >
            <option value="">
              Unassigned
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
          Status
          <select
            v-model="event.booking_status"
            :disabled="!canCoordinate"
            @change="saveCoordination({ booking_status: event.booking_status })"
          >
            <option
              v-for="status in BOOKING_STATUSES"
              :key="status"
              :value="status"
            >
              {{ BOOKING_STATUS_LABEL[status] }}
            </option>
          </select>
        </label>
        <label>
          Alert on
          <input
            v-model="event.alert_on"
            type="date"
            :disabled="!isOwner"
            @change="save({ alert_on: event.alert_on || null })"
          >
        </label>

        <h4 class="span section-heading">
          Setup
        </h4>
        <div class="span">
          <RichTextEditor
            :model-value="event.setup"
            :disabled="!isOwner"
            @update:model-value="updateSetup"
          />
        </div>
      </div>
      <p
        v-if="saveError"
        class="error"
      >
        {{ saveError }}
      </p>

      <template v-if="auth.isAdmin">
        <h4>Financials</h4>
        <p class="muted small">
          Admin-only: set by any admin, regardless of who owns the event.
        </p>
        <div class="event-form">
          <label>
            Budget
            <input
              v-model="event.budget"
              type="number"
              step="0.01"
              min="0"
              @change="saveFinancials({ budget: event.budget || null })"
            >
          </label>
          <label>
            Document status
            <select
              v-model="event.document_status"
              @change="saveFinancials({ document_status: event.document_status })"
            >
              <option value="">
                Not set
              </option>
              <option
                v-for="status in DOCUMENT_STATUSES"
                :key="status"
                :value="status"
              >
                {{ DOCUMENT_STATUS_LABEL[status] }}
              </option>
            </select>
          </label>
          <label>
            Financial status
            <select
              v-model="event.financial_status"
              @change="saveFinancials({ financial_status: event.financial_status })"
            >
              <option value="">
                Not set
              </option>
              <option
                v-for="status in FINANCIAL_STATUSES"
                :key="status"
                :value="status"
              >
                {{ FINANCIAL_STATUS_LABEL[status] }}
              </option>
            </select>
          </label>
        </div>
        <p
          v-if="financialsError"
          class="error"
        >
          {{ financialsError }}
        </p>
      </template>
    </template>
  </section>
</template>

<style scoped>
.event-form {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0 1.3rem;
}
.event-form .span {
  grid-column: 1 / -1;
}
.section-heading {
  margin: 1rem 0 0.25rem;
  padding-top: 0.75rem;
  border-top: 1px solid var(--border);
  font-size: 0.85rem;
  color: var(--muted);
  text-transform: uppercase;
  letter-spacing: 0.02em;
}
.event-form > h4:first-of-type {
  padding-top: 0;
  border-top: none;
}
.coordination-note {
  margin: -0.5rem 0 0.6rem;
}
</style>
