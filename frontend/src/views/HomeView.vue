<script setup>
import { onMounted } from "vue";
import { useRouter } from "vue-router";

import { useAuthStore } from "@/stores/auth";

// The home route is a signpost, not a page: admins want the fleet, employees want their
// own day, and putting both on one screen would mean an employee's landing page was
// mostly things they are not allowed to see.
const auth = useAuthStore();
const router = useRouter();

onMounted(() => {
  router.replace({ name: auth.isAdmin ? "dashboard" : "my-dashboard" });
});
</script>

<template>
  <section class="card">
    <p class="muted">
      Loading…
    </p>
  </section>
</template>
