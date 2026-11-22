<script setup>
import { onMounted, ref } from "vue";

import { api } from "@/api/client";
import { dateTime, describeError } from "@/lib/format";

const screenshots = ref([]);
const loading = ref(false);
const error = ref("");

async function load() {
  loading.value = true;
  error.value = "";
  try {
    const list = await api.listScreenshots();
    screenshots.value = list.results ?? list;
  } catch (err) {
    error.value = describeError(err);
  } finally {
    loading.value = false;
  }
}

onMounted(load);
</script>

<template>
  <section class="card">
    <header class="row">
      <h2>Screenshots</h2>
    </header>
    <p class="muted small">
      Admin-only. The employee a capture is of cannot see it — only that it was
      viewed, by whom, and when.
    </p>

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
            <th>Employee</th>
            <th>Computer</th>
            <th>Captured</th>
            <th>Views</th>
            <th>Last viewed by</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="shot in screenshots"
            :key="shot.id"
            class="screenshot-row"
            @click="$router.push(`/screenshots/${shot.id}`)"
          >
            <td>{{ shot.employee.name }}</td>
            <td>{{ shot.computer_name }}</td>
            <td>{{ dateTime(shot.captured_at) }}</td>
            <td>{{ shot.view_count }}</td>
            <td>
              <span v-if="shot.last_viewed_by">
                {{ shot.last_viewed_by.admin }} ({{ dateTime(shot.last_viewed_by.at) }})
              </span>
              <span
                v-else
                class="muted"
              >Never viewed</span>
            </td>
          </tr>
          <tr v-if="!screenshots.length && !loading">
            <td
              colspan="5"
              class="muted"
            >
              No screenshots captured yet.
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>
</template>

<style scoped>
.screenshot-row {
  cursor: pointer;
}
</style>
