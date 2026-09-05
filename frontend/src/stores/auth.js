import { defineStore } from "pinia";
import { ref, computed } from "vue";

import { api } from "@/api/client";

export const useAuthStore = defineStore("auth", () => {
  const user = ref(null);
  const loading = ref(false);
  const checked = ref(false);

  const isAuthenticated = computed(() => user.value !== null);
  const isAdmin = computed(() => user.value?.role === "ADMIN");

  async function bootstrap() {
    // Fetch the CSRF cookie first: without it the very first login POST is rejected.
    await api.csrf().catch(() => {});
    try {
      user.value = await api.me();
    } catch {
      user.value = null;
    } finally {
      checked.value = true;
    }
  }

  async function login(email, password) {
    loading.value = true;
    try {
      await api.csrf();
      user.value = await api.login(email, password);
      return user.value;
    } finally {
      loading.value = false;
    }
  }

  async function logout() {
    try {
      await api.logout();
    } finally {
      user.value = null;
    }
  }

  return { user, loading, checked, isAuthenticated, isAdmin, bootstrap, login, logout };
});
