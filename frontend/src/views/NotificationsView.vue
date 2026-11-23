<script setup>
import { onMounted, ref } from "vue";
import { useRouter } from "vue-router";

import { api } from "@/api/client";
import { dateTime, describeError } from "@/lib/format";

const router = useRouter();

const notifications = ref([]);
const loading = ref(false);
const error = ref("");

async function load() {
  loading.value = true;
  error.value = "";
  try {
    const list = await api.listNotifications();
    notifications.value = list.results ?? list;
  } catch (err) {
    error.value = describeError(err);
  } finally {
    loading.value = false;
  }
}

async function open(notification) {
  if (!notification.read_at) {
    try {
      notification.read_at = (await api.markNotificationRead(notification.id)).read_at;
    } catch (err) {
      error.value = describeError(err);
      return;
    }
  }
  if (notification.url) router.push(notification.url);
}

async function markAllRead() {
  error.value = "";
  try {
    await api.markAllNotificationsRead();
    await load();
  } catch (err) {
    error.value = describeError(err);
  }
}

onMounted(load);
</script>

<template>
  <section class="card">
    <header class="row">
      <h2>Notifications</h2>
      <button
        v-if="notifications.some((n) => !n.read_at)"
        @click="markAllRead"
      >
        Mark all read
      </button>
    </header>

    <p
      v-if="error"
      class="error"
    >
      {{ error }}
    </p>
    <p v-if="loading">
      Loading…
    </p>

    <ul class="bars">
      <li
        v-for="notification in notifications"
        :key="notification.id"
        :class="{ unread: !notification.read_at, clickable: notification.url }"
        @click="open(notification)"
      >
        <span>
          <span
            v-if="!notification.read_at"
            class="dot"
          />
          {{ notification.message }}
        </span>
        <span class="muted small">{{ dateTime(notification.created_at) }}</span>
      </li>
      <li
        v-if="!notifications.length && !loading"
        class="muted"
      >
        No notifications yet.
      </li>
    </ul>
  </section>
</template>

<style scoped>
.bars li.clickable {
  cursor: pointer;
}
.bars li.unread {
  font-weight: 600;
}
.dot {
  display: inline-block;
  width: 0.45rem;
  height: 0.45rem;
  border-radius: 50%;
  background: var(--danger);
  margin-right: 0.4rem;
}
</style>
