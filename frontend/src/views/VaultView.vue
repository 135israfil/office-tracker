<script setup>
import { onMounted, ref } from "vue";

import { api } from "@/api/client";
import { describeError } from "@/lib/format";

const entries = ref([]);
const loading = ref(false);
const error = ref("");
const formError = ref("");
const showForm = ref(false);

const blankForm = () => ({ title: "", username: "", password: "", url: "", notes: "" });
const form = ref(blankForm());

async function load() {
  loading.value = true;
  error.value = "";
  try {
    const list = await api.listVaultEntries();
    entries.value = list.results ?? list;
  } catch (err) {
    error.value = describeError(err);
  } finally {
    loading.value = false;
  }
}

async function createEntry() {
  formError.value = "";
  try {
    await api.createVaultEntry(form.value);
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
      <h2>Credentials</h2>
      <button @click="showForm = !showForm">
        {{ showForm ? "Cancel" : "New credential" }}
      </button>
    </header>
    <p class="muted small">
      For work logins — shared tools, vendor portals, service accounts. Not for
      personal banking or email passwords.
    </p>

    <form
      v-if="showForm"
      class="form-grid"
      @submit.prevent="createEntry"
    >
      <label>Title<input
        v-model="form.title"
        required
      ></label>
      <label>Username<input v-model="form.username"></label>
      <label>Password<input
        v-model="form.password"
        type="password"
        required
      ></label>
      <label>URL<input
        v-model="form.url"
        type="url"
      ></label>
      <label class="span">
        Notes
        <textarea
          v-model="form.notes"
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
        Save credential
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
            <th>Username</th>
            <th>Owner</th>
            <th>Visible to</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="entry in entries"
            :key="entry.id"
            class="task-row"
            @click="$router.push(`/vault/${entry.id}`)"
          >
            <td>{{ entry.title }}</td>
            <td>{{ entry.username || "—" }}</td>
            <td>{{ entry.owner.name }}</td>
            <td>{{ entry.visible_to.join(", ") }}</td>
          </tr>
          <tr v-if="!entries.length && !loading">
            <td
              colspan="4"
              class="muted"
            >
              No credentials yet.
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>
</template>

<style scoped>
.task-row {
  cursor: pointer;
}
</style>
