<script setup>
import { ref } from "vue";
import { useRoute, useRouter } from "vue-router";

import { useAuthStore } from "@/stores/auth";

const auth = useAuthStore();
const router = useRouter();
const route = useRoute();

const email = ref("");
const password = ref("");
const error = ref("");

async function submit() {
  error.value = "";
  try {
    await auth.login(email.value, password.value);
    router.push(route.query.next || { name: "home" });
  } catch (err) {
    error.value = err.payload?.detail?.[0] || err.payload?.detail || "Sign in failed.";
  }
}
</script>

<template>
  <section class="card narrow">
    <h2>Sign in</h2>
    <form @submit.prevent="submit">
      <label>
        Email
        <input
          v-model="email"
          type="email"
          required
          autocomplete="username"
        >
      </label>
      <label>
        Password
        <input
          v-model="password"
          type="password"
          required
          autocomplete="current-password"
        >
      </label>
      <p
        v-if="error"
        class="error"
      >
        {{ error }}
      </p>
      <button
        type="submit"
        :disabled="auth.loading"
      >
        {{ auth.loading ? "Signing in…" : "Sign in" }}
      </button>
    </form>
  </section>
</template>
