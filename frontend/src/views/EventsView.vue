<script setup>
import { computed, onMounted, ref } from "vue";

import { api } from "@/api/client";
import RichTextEditor from "@/components/RichTextEditor.vue";
import { dateOnly, describeError } from "@/lib/format";

const events = ref([]);
const employees = ref([]);
const loading = ref(false);
const error = ref("");
const formError = ref("");
const showForm = ref(false);

const blankForm = () => ({
  title: "",
  agency_name: "",
  venue_name: "",
  setup: "",
  assigned_lead_id: "",
  booking_status: "ON_COMMUNICATION",
  alert_on: "",
});
const form = ref(blankForm());

const BOOKING_STATUSES = ["ON_COMMUNICATION", "LOCKED", "DONE"];
const BOOKING_STATUS_LABEL = {
  ON_COMMUNICATION: "On communication",
  LOCKED: "Locked",
  DONE: "Done",
};
const BOOKING_STATUS_BADGE = { ON_COMMUNICATION: "warn", LOCKED: "inactive", DONE: "active" };

// Soonest alert first, same ordering the backend's own default returns —
// sorted again here only because the list can also include events with no
// alert date at all, which the API already puts last.
const sortedEvents = computed(() =>
  [...events.value].sort((a, b) => (a.alert_on ?? "9999") < (b.alert_on ?? "9999") ? -1 : 1),
);

async function load() {
  loading.value = true;
  error.value = "";
  try {
    const [list, assignable] = await Promise.all([
      api.listEvents(),
      api.listAssignableEmployees(),
    ]);
    events.value = list.results ?? list;
    employees.value = assignable;
  } catch (err) {
    error.value = describeError(err);
  } finally {
    loading.value = false;
  }
}

async function createEvent() {
  formError.value = "";
  try {
    await api.createEvent({
      ...form.value,
      assigned_lead_id: form.value.assigned_lead_id || null,
      alert_on: form.value.alert_on || null,
    });
    form.value = blankForm();
    showForm.value = false;
    await load();
  } catch (err) {
    formError.value = describeError(err);
  }
}

onMounted(load);
</script>

<template>
  <section class="card">
    <header class="row">
      <h2>Events</h2>
      <button @click="showForm = !showForm">
        {{ showForm ? "Cancel" : "New event" }}
      </button>
    </header>

    <form
      v-if="showForm"
      class="event-form"
      @submit.prevent="createEvent"
    >
      <label class="span">Title<input
        v-model="form.title"
        required
        placeholder="e.g. Annual Gala"
      ></label>

      <h4 class="span section-heading">
        Booking
      </h4>
      <label>Agency name<input v-model="form.agency_name"></label>
      <label>Venue name<input v-model="form.venue_name"></label>
      <label>
        Assigned lead
        <select v-model="form.assigned_lead_id">
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
        <select v-model="form.booking_status">
          <option
            v-for="status in BOOKING_STATUSES"
            :key="status"
            :value="status"
          >
            {{ BOOKING_STATUS_LABEL[status] }}
          </option>
        </select>
      </label>
      <label class="span">Alert on<input
        v-model="form.alert_on"
        type="date"
      ></label>

      <h4 class="span section-heading">
        Setup
      </h4>
      <div class="span">
        <RichTextEditor v-model="form.setup" />
      </div>

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
        Create event
      </button>
    </form>

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
            <th>Title</th>
            <th>Venue</th>
            <th>Assigned lead</th>
            <th>Status</th>
            <th>Alert on</th>
            <th>Owner</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="event in sortedEvents"
            :key="event.id"
            class="event-row"
            @click="$router.push(`/events/${event.id}`)"
          >
            <td>{{ event.title }}</td>
            <td>{{ event.venue_name || "—" }}</td>
            <td>{{ event.assigned_lead?.name ?? "—" }}</td>
            <td>
              <span :class="['badge', BOOKING_STATUS_BADGE[event.booking_status]]">
                {{ BOOKING_STATUS_LABEL[event.booking_status] }}
              </span>
            </td>
            <td>{{ event.alert_on ? dateOnly(event.alert_on) : "—" }}</td>
            <td>{{ event.owner.name }}</td>
          </tr>
          <tr v-if="!sortedEvents.length && !loading">
            <td
              colspan="6"
              class="muted"
            >
              No events yet.
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>
</template>

<style scoped>
.event-row {
  cursor: pointer;
}
.event-form {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0 1.3rem;
  margin-bottom: 1.5rem;
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
</style>
