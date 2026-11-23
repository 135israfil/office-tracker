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
const imageError = ref("");

async function load() {
  loading.value = true;
  error.value = "";
  imageError.value = "";
  revokeImage();
  try {
    shot.value = await api.getScreenshot(route.params.id);
    imageUrl.value = await api.viewScreenshotImage(shot.value.id);
  } catch (err) {
    if (shot.value) {
      // The metadata loaded fine; only the image itself failed (e.g. purged by
      // retention a moment ago) — keep showing the metadata rather than the
      // page's generic error state.
      imageError.value = describeError(err);
    } else {
      error.value = describeError(err);
    }
  } finally {
    loading.value = false;
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
        {{ shot.employee.name }} cannot see this image.
      </p>

      <img
        v-if="imageUrl"
        :src="imageUrl"
        alt="Captured screenshot"
        class="screenshot-image"
      >
      <p
        v-else-if="imageError"
        class="error small"
      >
        {{ imageError }}
      </p>
      <p v-else>
        Loading image…
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
