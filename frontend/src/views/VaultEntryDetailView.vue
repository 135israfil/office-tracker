<script setup>
import { computed, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";

import { api } from "@/api/client";
import { describeError } from "@/lib/format";
import { useAuthStore } from "@/stores/auth";

const route = useRoute();
const router = useRouter();
const auth = useAuthStore();

const entry = ref(null);
const employees = ref([]);
const loading = ref(false);
const error = ref("");
const saveError = ref("");
const shareError = ref("");

const revealedPassword = ref("");
const revealing = ref(false);
const revealError = ref("");

const newGranteeId = ref("");

const myEmployeeId = computed(() => auth.user?.employee?.id ?? null);
const isOwner = computed(() => entry.value && myEmployeeId.value === entry.value.owner.id);

async function load() {
  loading.value = true;
  error.value = "";
  revealedPassword.value = "";
  try {
    const [loadedEntry, employeeList] = await Promise.all([
      api.getVaultEntry(route.params.id),
      api.listAssignableEmployees(),
    ]);
    entry.value = loadedEntry;
    employees.value = employeeList;
  } catch (err) {
    error.value = describeError(err);
  } finally {
    loading.value = false;
  }
}

async function save(patch) {
  saveError.value = "";
  try {
    entry.value = await api.updateVaultEntry(entry.value.id, patch);
  } catch (err) {
    saveError.value = describeError(err);
  }
}

async function reveal() {
  revealError.value = "";
  revealing.value = true;
  try {
    const { password } = await api.revealVaultEntry(entry.value.id);
    revealedPassword.value = password;
  } catch (err) {
    revealError.value = describeError(err);
  } finally {
    revealing.value = false;
  }
}

async function share() {
  shareError.value = "";
  if (!newGranteeId.value) return;
  try {
    entry.value = await api.shareVaultEntry(entry.value.id, newGranteeId.value);
    newGranteeId.value = "";
  } catch (err) {
    shareError.value = describeError(err);
  }
}

async function revoke(employeeId) {
  shareError.value = "";
  try {
    entry.value = await api.revokeVaultEntryGrant(entry.value.id, employeeId);
  } catch (err) {
    shareError.value = describeError(err);
  }
}

async function deleteEntry() {
  try {
    await api.deleteVaultEntry(entry.value.id);
    router.push({ name: "vault" });
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

    <template v-if="entry">
      <header class="row">
        <h2>{{ entry.title }}</h2>
        <button
          v-if="isOwner"
          class="secondary"
          @click="deleteEntry"
        >
          Delete
        </button>
      </header>
      <p class="muted small">
        Visible to: {{ entry.visible_to.join(", ") }}
      </p>
      <p
        v-if="entry.last_admin_reveal"
        class="muted small"
      >
        Last viewed by an admin ({{ entry.last_admin_reveal.admin }}) on
        {{ new Date(entry.last_admin_reveal.at).toLocaleString() }}.
      </p>

      <div class="form-grid">
        <label>
          Title
          <input
            v-model="entry.title"
            :disabled="!isOwner"
            @change="save({ title: entry.title })"
          >
        </label>
        <label>
          Username
          <input
            v-model="entry.username"
            :disabled="!isOwner"
            @change="save({ username: entry.username })"
          >
        </label>
        <label>
          URL
          <input
            v-model="entry.url"
            type="url"
            :disabled="!isOwner"
            @change="save({ url: entry.url })"
          >
        </label>
        <label class="span">
          Notes
          <textarea
            v-model="entry.notes"
            rows="2"
            :disabled="!isOwner"
            @change="save({ notes: entry.notes })"
          />
        </label>
      </div>
      <p
        v-if="saveError"
        class="error"
      >
        {{ saveError }}
      </p>

      <h4>Password</h4>
      <p
        v-if="revealedPassword"
        class="small"
      >
        <code>{{ revealedPassword }}</code>
      </p>
      <button
        v-else
        :disabled="revealing"
        @click="reveal"
      >
        {{ revealing ? "Revealing…" : "Reveal password" }}
      </button>
      <p
        v-if="revealError"
        class="error small"
      >
        {{ revealError }}
      </p>

      <h4>Shared with</h4>
      <ul class="bars">
        <li
          v-for="grant in entry.grants"
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
          v-if="!entry.grants.length"
          class="muted"
        >
          Not shared with anyone.
        </li>
      </ul>
      <p class="muted small">
        Revoking stops future access only — it does not undo anything the
        person already saw. Rotate the actual password if that's a concern.
      </p>
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
