<script setup>
import { computed, onMounted, ref } from "vue";

import { api } from "@/api/client";
import { describeError, toDatetimeLocal } from "@/lib/format";

const events = ref([]);
const loading = ref(false);
const error = ref("");
const formError = ref("");
const showForm = ref(false);

const blankForm = () => ({
  title: "",
  description: "",
  start: "",
  end: "",
  all_day: false,
  location: "",
});
const form = ref(blankForm());

const PHASE_BADGE = { UPCOMING: "", IN_PROGRESS: "active", PAST: "inactive" };
const PHASE_LABEL = { UPCOMING: "Upcoming", IN_PROGRESS: "In progress", PAST: "Past" };
const PHASE_ORDER = { UPCOMING: 0, IN_PROGRESS: 1, PAST: 2 };

// Upcoming and in-progress events first (soonest start first), past events
// last — computed here rather than in the backend query, since phase is a
// read-time Python rule, not a database column.
const sortedEvents = computed(() =>
  [...events.value].sort((a, b) => {
    if (PHASE_ORDER[a.phase] !== PHASE_ORDER[b.phase]) {
      return PHASE_ORDER[a.phase] - PHASE_ORDER[b.phase];
    }
    return a.start < b.start ? -1 : 1;
  }),
);

async function load() {
  loading.value = true;
  error.value = "";
  try {
    const list = await api.listEvents();
    events.value = list.results ?? list;
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
      start: new Date(form.value.start).toISOString(),
      end: form.value.end ? new Date(form.value.end).toISOString() : null,
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
      class="form-grid"
      @submit.prevent="createEvent"
    >
      <label>Title<input
        v-model="form.title"
        required
      ></label>
      <label>Location<input v-model="form.location"></label>
      <label>Start<input
        v-model="form.start"
        type="datetime-local"
        required
      ></label>
      <label>End<input
        v-model="form.end"
        type="datetime-local"
      ></label>
      <label class="check">
        <input
          v-model="form.all_day"
          type="checkbox"
        >
        All day
      </label>
      <label class="span">
        Description
        <textarea
          v-model="form.description"
          rows="2"
        />
      </label>
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
            <th>Phase</th>
            <th>Start</th>
            <th>Shared with</th>
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
            <td>
              <span :class="['badge', PHASE_BADGE[event.phase]]">{{ PHASE_LABEL[event.phase] }}</span>
              <span
                v-if="event.status === 'CANCELLED'"
                class="badge inactive"
              >Cancelled</span>
            </td>
            <td>{{ toDatetimeLocal(event.start).replace("T", " ") }}</td>
            <td>
              <span
                v-for="grant in event.grants"
                :key="grant.grantee.id"
                class="chip"
              >{{ grant.grantee.name }}</span>
              <span
                v-if="!event.grants.length"
                class="muted"
              >Not shared</span>
            </td>
            <td>{{ event.owner.name }}</td>
          </tr>
          <tr v-if="!sortedEvents.length && !loading">
            <td
              colspan="5"
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
</style>
