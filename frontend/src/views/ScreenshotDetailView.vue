<script setup>
import { onMounted, onUnmounted, ref, watch } from "vue";
import { useRoute } from "vue-router";

import { api } from "@/api/client";
import { dateTime, describeError } from "@/lib/format";

const route = useRoute();

const shot = ref(null);
const loading = ref(false);
const error = ref("");

const imageUrl = ref("");
const viewing = ref(false);
const viewError = ref("");

async function load() {
  loading.value = true;
  error.value = "";
  revokeImage();
  try {
    shot.value = await api.getScreenshot(route.params.id);
  } catch (err) {
    error.value = describeError(err);
  } finally {
    loading.value = false;
  }
}

async function viewImage() {
  viewError.value = "";
  viewing.value = true;
  try {
    imageUrl.value = await api.viewScreenshotImage(shot.value.id);
    // Viewing just logged an admin reveal against this capture — refresh the
    // metadata so the view count/last-viewed line on screen isn't stale.
    shot.value = await api.getScreenshot(shot.value.id);
  } catch (err) {
    viewError.value = describeError(err);
  } finally {
    viewing.value = false;
  }
}

function revokeImage() {
  if (imageUrl.value) URL.revokeObjectURL(imageUrl.value);
  imageUrl.value = "";
}

watch(() => route.params.id, load);
onMounted(load);
onUnmounted(revokeImage);
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

    <template v-if="shot">
      <header class="row">
        <h2>Screenshot of {{ shot.employee.name }}</h2>
      </header>
      <p class="muted small">
        Computer: {{ shot.computer_name }} &middot; Captured
        {{ dateTime(shot.captured_at) }}
      </p>
      <p class="muted small">
        Viewed {{ shot.view_count }} time(s){{
          shot.last_viewed_by ? ` — last by ${shot.last_viewed_by.admin} (${dateTime(shot.last_viewed_by.at)})` : ""
        }}.
        {{ shot.employee.name }} cannot see this image, but can see that it was viewed.
      </p>

      <img
        v-if="imageUrl"
        :src="imageUrl"
        alt="Captured screenshot"
        class="screenshot-image"
      >
      <button
        v-else
        :disabled="viewing"
        @click="viewImage"
      >
        {{ viewing ? "Loading…" : "View screenshot" }}
      </button>
      <p
        v-if="viewError"
        class="error small"
      >
        {{ viewError }}
      </p>
    </template>
  </section>
</template>

<style scoped>
.screenshot-image {
  max-width: 100%;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
}
</style>
