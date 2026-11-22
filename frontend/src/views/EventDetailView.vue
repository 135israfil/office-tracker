<script setup>
import { computed, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";

import { api } from "@/api/client";
import { describeError, toDatetimeLocal } from "@/lib/format";
import { useAuthStore } from "@/stores/auth";

const STATUSES = ["ACTIVE", "CANCELLED"];

const route = useRoute();
const router = useRouter();
const auth = useAuthStore();

const event = ref(null);
const employees = ref([]);
const loading = ref(false);
const error = ref("");
const saveError = ref("");
const shareError = ref("");

const newGranteeId = ref("");

// datetime-local inputs need their own local-string copies — binding v-model
// straight to event.start would write the API's ISO string into the input,
// which a datetime-local field cannot parse.
const startLocal = ref("");
const endLocal = ref("");

const myEmployeeId = computed(() => auth.user?.employee?.id ?? null);
const isOwner = computed(() => event.value && myEmployeeId.value === event.value.owner.id);

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
    startLocal.value = toDatetimeLocal(loadedEvent.start);
    endLocal.value = toDatetimeLocal(loadedEvent.end);
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

function saveStart() {
  save({ start: new Date(startLocal.value).toISOString() });
}

function saveEnd() {
  save({ end: endLocal.value ? new Date(endLocal.value).toISOString() : null });
}

async function share() {
  shareError.value = "";
  if (!newGranteeId.value) return;
  try {
    event.value = await api.shareEvent(event.value.id, newGranteeId.value);
    newGranteeId.value = "";
  } catch (err) {
    shareError.value = describeError(err);
  }
}

async function revoke(employeeId) {
  shareError.value = "";
  try {
    event.value = await api.revokeEventGrant(event.value.id, employeeId);
  } catch (err) {
    shareError.value = describeError(err);
  }
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
      <p class="muted small">
        Visible to: {{ event.visible_to.join(", ") }}
      </p>
      <p
        v-if="event.last_admin_view"
        class="muted small"
      >
        Last viewed by an admin ({{ event.last_admin_view.admin }}) on
        {{ new Date(event.last_admin_view.at).toLocaleString() }}.
      </p>

      <div class="form-grid">
        <label>
          Title
          <input
            v-model="event.title"
            :disabled="!isOwner"
            @change="save({ title: event.title })"
          >
        </label>
        <label>
          Status
          <select
            v-model="event.status"
            :disabled="!isOwner"
            @change="save({ status: event.status })"
          >
            <option
              v-for="status in STATUSES"
              :key="status"
              :value="status"
            >
              {{ status }}
            </option>
          </select>
        </label>
        <label>
          Start
          <input
            v-model="startLocal"
            type="datetime-local"
            :disabled="!isOwner"
            @change="saveStart"
          >
        </label>
        <label>
          End
          <input
            v-model="endLocal"
            type="datetime-local"
            :disabled="!isOwner"
            @change="saveEnd"
          >
        </label>
        <label class="check">
          <input
            v-model="event.all_day"
            type="checkbox"
            :disabled="!isOwner"
            @change="save({ all_day: event.all_day })"
          >
          All day
        </label>
        <label>
          Location
          <input
            v-model="event.location"
            :disabled="!isOwner"
            @change="save({ location: event.location })"
          >
        </label>
        <label class="span">
          Description
          <textarea
            v-model="event.description"
            rows="3"
            :disabled="!isOwner"
            @change="save({ description: event.description })"
          />
        </label>
      </div>
      <p
        v-if="saveError"
        class="error"
      >
        {{ saveError }}
      </p>
      <p class="muted small">
        Phase: {{ event.phase }}
      </p>

      <h4>Shared with</h4>
      <ul class="bars">
        <li
          v-for="grant in event.grants"
          :key="grant.grantee.id"
        >
          <span>{{ grant.grantee.name }} ({{ grant.grantee.employee_id }})</span>
          <button
            v-if="isOwner || grant.grantee.id === myEmployeeId"
            class="link"
            @click="revoke(grant.grantee.id)"
          >
            {{ grant.grantee.id === myEmployeeId ? "Leave" : "Revoke" }}
          </button>
        </li>
        <li
          v-if="!event.grants.length"
          class="muted"
        >
          Not shared with anyone.
        </li>
      </ul>
      <form
        v-if="isOwner"
        class="row"
        @submit.prevent="share"
      >
        <select v-model="newGranteeId">
          <option value="">
            Share with…
          </option>
          <option
            v-for="employee in employees"
            :key="employee.id"
            :value="employee.id"
          >
            {{ employee.name }} ({{ employee.employee_id }})
          </option>
        </select>
        <button type="submit">
          Share
        </button>
      </form>
      <p
        v-if="shareError"
        class="error small"
      >
        {{ shareError }}
      </p>
    </template>
  </section>
</template>
