<script setup>
import { computed, onBeforeUnmount, ref, watch } from "vue";
import { useRouter } from "vue-router";

import { api } from "@/api/client";
import NavIcon from "@/components/NavIcon.vue";
import { useAuthStore } from "@/stores/auth";

const auth = useAuthStore();
const router = useRouter();

// Built as data rather than nine hand-written links, so the admin and employee views of
// the app differ in one place instead of behind eight separate v-ifs.
const links = computed(() =>
  auth.isAdmin
    ? [
        { to: "/dashboard", label: "Dashboard", icon: "grid" },
        { to: "/notifications", label: "Notifications", icon: "bell" },
        { to: "/attendance", label: "Attendance", icon: "clock" },
        { to: "/admin/attendance", label: "All attendance", icon: "calendar" },
        { to: "/activity", label: "Activity", icon: "pulse" },
        { to: "/tasks", label: "Tasks", icon: "check-square" },
        { to: "/vault", label: "Credentials", icon: "key" },
        { to: "/events", label: "Events", icon: "calendar-event" },
        { to: "/reports", label: "Reports", icon: "chart" },
        { to: "/employees", label: "Employees", icon: "users" },
        { to: "/computers", label: "Computers", icon: "monitor" },
        { to: "/settings", label: "Settings", icon: "sliders" },
      ]
    : [
        { to: "/my", label: "My dashboard", icon: "home" },
        { to: "/notifications", label: "Notifications", icon: "bell" },
        { to: "/attendance", label: "Attendance", icon: "clock" },
        { to: "/tasks", label: "Tasks", icon: "check-square" },
        { to: "/vault", label: "Credentials", icon: "key" },
        { to: "/events", label: "Events", icon: "calendar-event" },
      ],
);

// Polling, not a push subscription: this app has no service worker or push
// infrastructure (see backend/notifications). While signed in, check for new
// notifications every 30s; anything unread that wasn't there last poll fires
// a real browser notification, not just the in-app badge below.
const unreadCount = ref(0);
const seenIds = new Set();
let pollTimer = null;
let seeded = false;

async function pollNotifications() {
  let unread;
  try {
    unread = await api.listNotifications({ unread: "true" });
  } catch {
    return;
  }
  const rows = unread.results ?? unread;
  unreadCount.value = rows.length;

  if (!seeded) {
    // The baseline: notifications already unread before this tab started
    // polling are shown in the badge, not popped as a toast.
    rows.forEach((row) => seenIds.add(row.id));
    seeded = true;
    return;
  }
  for (const row of rows) {
    if (seenIds.has(row.id)) continue;
    seenIds.add(row.id);
    if (window.Notification?.permission === "granted") {
      new Notification("Office Management", { body: row.message });
    }
  }
}

watch(
  () => auth.isAuthenticated,
  (authenticated) => {
    clearInterval(pollTimer);
    pollTimer = null;
    seenIds.clear();
    seeded = false;
    unreadCount.value = 0;
    if (!authenticated) return;

    if (window.Notification && Notification.permission === "default") {
      Notification.requestPermission();
    }
    pollNotifications();
    pollTimer = setInterval(pollNotifications, 30000);
  },
  { immediate: true },
);
onBeforeUnmount(() => clearInterval(pollTimer));

const displayName = computed(
  () => auth.user?.employee?.name || auth.user?.email || "Signed in",
);
const roleLabel = computed(() => (auth.isAdmin ? "Administrator" : "Employee"));
const initials = computed(() =>
  displayName.value
    .split(/[\s@.]+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0].toUpperCase())
    .join(""),
);

async function signOut() {
  await auth.logout();
  router.push({ name: "login" });
}
</script>

<template>
  <div :class="['shell', { 'shell--anon': !auth.isAuthenticated }]">
    <aside
      v-if="auth.isAuthenticated"
      class="sidebar"
    >
      <div class="brand">
        <span class="brand__mark">OM</span>
        <span class="brand__text">Office</span>
      </div>

      <nav class="sidebar__nav">
        <RouterLink
          v-for="link in links"
          :key="link.to"
          :to="link.to"
          class="navlink"
        >
          <NavIcon :name="link.icon" />
          <span>{{ link.label }}</span>
          <span
            v-if="link.to === '/notifications' && unreadCount"
            class="navlink__badge"
          >{{ unreadCount }}</span>
        </RouterLink>
      </nav>

      <div class="sidebar__foot">
        <div class="who">
          <span class="who__avatar">{{ initials }}</span>
          <span class="who__text">
            <span class="who__name">{{ displayName }}</span>
            <span class="who__role">{{ roleLabel }}</span>
          </span>
        </div>
        <button
          class="signout"
          @click="signOut"
        >
          Sign out
        </button>
      </div>
    </aside>

    <main class="app">
      <RouterView />
    </main>
  </div>
</template>

<style>
/* ---------------------------------------------------------------------------
   One sheet for the whole app, plus a few scoped blocks that only ever reach
   for the variables declared here. A change to the palette or the spacing
   rhythm therefore lands on every screen at once, and no view can quietly
   drift into a look of its own.

   Everything a view needs is a semantic class (.card, .stat, .badge) rather
   than a utility, so the markup says what a thing *is* and this file decides
   how it looks.
--------------------------------------------------------------------------- */

@import "@fontsource-variable/inter";

:root {
  /* Neutrals are very slightly cool. Large flat panels in a pure grey look
     muddy beside white; a few points of blue keeps them deliberate. */
  --bg: #f6f7f9;
  --surface: #ffffff;
  --surface-sunken: #f8f9fb;
  --border: #e8eaef;
  --border-strong: #d3d8e0;

  --text: #14161a;
  --text-soft: #454b56;
  --muted: #767d8b;

  --accent: #3b5bdb;
  --accent-hover: #304ec2;
  --accent-soft: #eef2ff;

  --ok: #0b7a4b;
  --ok-soft: #e9f9f1;
  --ok-border: #a9e5c8;
  --danger: #b5241c;
  --danger-soft: #fdf1f0;
  --danger-border: #f5c4c0;
  --warn: #a55a06;
  --warn-soft: #fdf6e8;
  --warn-border: #f3d9a4;

  --radius: 14px;
  --radius-sm: 9px;
  --radius-pill: 999px;

  --sidebar-w: 15.5rem;

  /* Two elevations, no more. One for surfaces at rest, one for what genuinely
     sits above the page. A third tier is how shadow systems turn to soup. */
  --shadow: 0 1px 2px rgba(20, 22, 26, 0.04), 0 1px 3px rgba(20, 22, 26, 0.05);
  --shadow-lifted: 0 12px 32px -12px rgba(20, 22, 26, 0.18), 0 3px 8px -4px rgba(20, 22, 26, 0.08);

  font-family: "Inter Variable", "Inter", system-ui, -apple-system, "Segoe UI", sans-serif;
  line-height: 1.55;
  color: var(--text);
  /* A screen full of durations, counts and clock times. Proportional digits make
     a column of them jitter; tabular figures line them up. */
  font-variant-numeric: tabular-nums;
  -webkit-font-smoothing: antialiased;
}

* {
  box-sizing: border-box;
}

body {
  margin: 0;
  background: var(--bg);
  min-height: 100vh;
}

/* --- Shell -------------------------------------------------------------- */

.shell {
  display: grid;
  grid-template-columns: var(--sidebar-w) minmax(0, 1fr);
  min-height: 100vh;
}
.shell--anon {
  grid-template-columns: minmax(0, 1fr);
}

.sidebar {
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
  padding: 1.15rem 0.85rem;
  background: var(--surface);
  border-right: 1px solid var(--border);
  /* Sticky rather than scrolling with the page: the tables are long, and the way
     out of a screen should not depend on scrolling back up. */
  position: sticky;
  top: 0;
  height: 100vh;
}

.brand {
  display: flex;
  align-items: center;
  gap: 0.6rem;
  padding: 0.25rem 0.55rem 1.15rem;
}
.brand__mark {
  display: grid;
  place-items: center;
  width: 1.85rem;
  height: 1.85rem;
  border-radius: 8px;
  background: var(--accent);
  color: #fff;
  font-size: 0.72rem;
  font-weight: 700;
  letter-spacing: 0.02em;
}
.brand__text {
  font-size: 1rem;
  font-weight: 650;
  letter-spacing: -0.02em;
}

.sidebar__nav {
  display: flex;
  flex-direction: column;
  gap: 0.1rem;
  overflow-y: auto;
}

.navlink {
  display: flex;
  align-items: center;
  gap: 0.7rem;
  padding: 0.55rem 0.6rem;
  border-radius: var(--radius-sm);
  color: var(--text-soft);
  text-decoration: none;
  font-size: 0.885rem;
  font-weight: 500;
  white-space: nowrap;
  transition: background-color 0.15s, color 0.15s;
}
.navlink:hover {
  background: var(--surface-sunken);
  color: var(--text);
}
.navlink.router-link-active {
  background: var(--accent-soft);
  color: var(--accent);
  font-weight: 600;
}
.navlink__badge {
  margin-left: auto;
  background: var(--danger);
  color: #fff;
  font-size: 0.72rem;
  font-weight: 700;
  line-height: 1;
  padding: 0.2rem 0.45rem;
  border-radius: 999px;
}

.sidebar__foot {
  margin-top: auto;
  padding-top: 0.9rem;
  border-top: 1px solid var(--border);
}
.who {
  display: flex;
  align-items: center;
  gap: 0.6rem;
  padding: 0.35rem 0.55rem 0.65rem;
  min-width: 0;
}
.who__avatar {
  display: grid;
  place-items: center;
  width: 1.9rem;
  height: 1.9rem;
  flex: none;
  border-radius: 50%;
  background: var(--surface-sunken);
  border: 1px solid var(--border-strong);
  color: var(--text-soft);
  font-size: 0.7rem;
  font-weight: 650;
}
.who__text {
  display: flex;
  flex-direction: column;
  min-width: 0;
}
.who__name {
  font-size: 0.845rem;
  font-weight: 550;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.who__role {
  font-size: 0.74rem;
  color: var(--muted);
}
.signout {
  width: 100%;
  padding: 0.42rem 0.6rem;
  background: none;
  border: 1px solid var(--border-strong);
  border-radius: var(--radius-sm);
  color: var(--text-soft);
  font: inherit;
  font-size: 0.83rem;
  font-weight: 500;
  cursor: pointer;
  transition: background-color 0.15s, border-color 0.15s, color 0.15s;
}
.signout:hover {
  background: var(--surface-sunken);
  border-color: var(--muted);
  color: var(--text);
}

.app {
  min-width: 0;
  padding: 2.25rem 2rem 5rem;
  margin: 0 auto;
  width: 100%;
  max-width: 82rem;
}

/* --- Surfaces ----------------------------------------------------------- */

.card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 1.6rem;
  box-shadow: var(--shadow);
}
.card + .card {
  margin-top: 1.25rem;
}
.card.narrow {
  max-width: 25rem;
  margin: 5rem auto;
  padding: 2.25rem;
  box-shadow: var(--shadow-lifted);
}

h2 {
  margin-top: 0;
  margin-bottom: 0.3rem;
  font-size: 1.4rem;
  font-weight: 650;
  letter-spacing: -0.025em;
}
h3 {
  font-size: 0.75rem;
  font-weight: 650;
  text-transform: uppercase;
  letter-spacing: 0.07em;
  color: var(--muted);
  margin: 1.9rem 0 0.8rem;
}
/* h3 is a section label almost everywhere, which is why it is set in small caps.
   The exception is the line naming whose day you are looking at — a person's
   name in capitals reads as shouting, not as a label. */
h3.subtitle {
  font-size: 1.02rem;
  font-weight: 600;
  text-transform: none;
  letter-spacing: -0.015em;
  color: var(--text);
  margin: 0.2rem 0 1.35rem;
}
h4 {
  font-size: 0.925rem;
  font-weight: 600;
  letter-spacing: -0.012em;
  margin: 1.6rem 0 0.65rem;
}

/* --- Forms -------------------------------------------------------------- */

/* Not just `form label`: several "detail view" pages lay fields out in a plain
   `<div class="form-grid">` (each field autosaves on change, so there is no
   single submit to wrap in a real <form>) — this must style those labels too,
   or they fall back to default, unstyled, inline browser rendering. */
form label,
.form-grid label,
.event-form label {
  display: flex;
  flex-direction: column;
  gap: 0.32rem;
  margin-bottom: 0.95rem;
  font-size: 0.84rem;
  font-weight: 550;
  color: var(--text-soft);
}
label.check {
  flex-direction: row;
  align-items: center;
  gap: 0.55rem;
}

input,
select {
  padding: 0.52rem 0.7rem;
  border: 1px solid var(--border-strong);
  border-radius: var(--radius-sm);
  font: inherit;
  font-size: 0.9rem;
  background: var(--surface);
  color: var(--text);
  transition: border-color 0.15s, box-shadow 0.15s;
}
input:hover,
select:hover {
  border-color: var(--muted);
}
input:focus-visible,
select:focus-visible,
button:focus-visible,
a:focus-visible {
  outline: none;
  border-color: var(--accent);
  /* A ring rather than a heavier border, so focus never nudges the layout. */
  box-shadow: 0 0 0 3px var(--accent-soft);
}
input[type="checkbox"] {
  width: 1.02rem;
  height: 1.02rem;
  accent-color: var(--accent);
  padding: 0;
}

button {
  padding: 0.52rem 1.05rem;
  border: 1px solid var(--accent);
  background: var(--accent);
  color: #fff;
  border-radius: var(--radius-sm);
  font: inherit;
  font-size: 0.885rem;
  font-weight: 600;
  cursor: pointer;
  transition: background-color 0.15s, border-color 0.15s, transform 0.05s;
}
button:hover:not(:disabled) {
  background: var(--accent-hover);
  border-color: var(--accent-hover);
}
button:active:not(:disabled) {
  transform: translateY(1px);
}
button:disabled {
  opacity: 0.45;
  cursor: default;
}

/* Secondary: the action sharing a row with a more important one. Exporting a
   report and paging through it are both real actions, but neither is the one
   the screen is for, and three saturated buttons read as three equal urgencies. */
button.secondary {
  background: var(--surface);
  border-color: var(--border-strong);
  color: var(--text-soft);
}
button.secondary:hover:not(:disabled) {
  background: var(--surface-sunken);
  border-color: var(--muted);
  color: var(--text);
}

button.link {
  background: none;
  border: none;
  color: var(--accent);
  padding: 0.2rem 0.1rem;
  font-weight: 550;
  text-decoration: none;
  border-bottom: 1px solid transparent;
  border-radius: 0;
}
button.link:hover:not(:disabled) {
  background: none;
  color: var(--accent-hover);
  border-bottom-color: currentColor;
}

fieldset {
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  margin: 0 0 1.35rem;
  padding: 1.35rem;
  background: var(--surface-sunken);
}
legend {
  font-weight: 650;
  font-size: 0.775rem;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--muted);
  padding: 0 0.45rem;
}

.form-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(12rem, 1fr));
  gap: 0 1.3rem;
}
.form-grid .span {
  grid-column: 1 / -1;
}

.row {
  display: flex;
  gap: 0.8rem;
  align-items: center;
  flex-wrap: wrap;
}
.row.filters {
  margin: 1.3rem 0;
  padding: 1rem 1.1rem;
  background: var(--surface-sunken);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
}
/* Inside a filter bar the labels belong beside their controls; a stack of
   floating labels there reads as a form to fill in rather than a set of knobs
   on the table below. */
.row.filters label {
  margin-bottom: 0;
}

/* --- Stat tiles --------------------------------------------------------- */

.grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(9.5rem, 1fr));
  gap: 0.85rem;
  margin: 1rem 0 1.6rem;
}

.stat {
  display: flex;
  flex-direction: column;
  gap: 0.12rem;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  padding: 0.95rem 1.05rem;
  background: var(--surface);
  box-shadow: var(--shadow);
}
.stat .label {
  font-size: 0.705rem;
  font-weight: 650;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--muted);
  margin-bottom: 0;
}
.stat .value {
  font-size: 1.7rem;
  font-weight: 650;
  line-height: 1.15;
  letter-spacing: -0.03em;
  color: var(--text);
}
/* Tiles in a row stretch to the tallest and only some carry a hint. The hint
   sits on the floor of the tile so the extra height reads as deliberate rather
   than as a gap under the number. */
.stat .small {
  margin-top: auto;
  padding-top: 0.35rem;
}

/* --- Tables ------------------------------------------------------------- */

/* Wide tables scroll inside their own container so the page never scrolls
   sideways. The border and radius live here rather than on the table, so the
   rounded corners survive the overflow clip. */
.table-scroll {
  overflow-x: auto;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--surface);
}
table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.89rem;
}
th,
td {
  text-align: left;
  padding: 0.72rem 0.9rem;
  border-bottom: 1px solid var(--border);
  vertical-align: middle;
}
thead th {
  font-size: 0.705rem;
  font-weight: 650;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--muted);
  background: var(--surface-sunken);
  white-space: nowrap;
}
tbody tr:last-child td {
  border-bottom: none;
}
tbody tr {
  transition: background-color 0.12s;
}
tbody tr:hover {
  background: var(--surface-sunken);
}

/* --- Chips and badges --------------------------------------------------- */

.chips {
  display: flex;
  flex-wrap: wrap;
  gap: 0.4rem;
  margin-bottom: 0.6rem;
}
.chip {
  display: inline-block;
  padding: 0.24rem 0.72rem;
  border: 1px solid var(--border-strong);
  border-radius: var(--radius-pill);
  font-size: 0.805rem;
  font-weight: 500;
  background: var(--surface);
  color: var(--text-soft);
  transition: background-color 0.15s, border-color 0.15s, color 0.15s;
}
.chip.toggle {
  cursor: pointer;
}
.chip.toggle:hover {
  border-color: var(--accent);
  color: var(--accent);
}
.chip.toggle.on {
  background: var(--accent);
  border-color: var(--accent);
  color: #fff;
}
.chip.split {
  border-color: var(--accent);
  color: var(--accent);
  background: var(--accent-soft);
}

.badge {
  display: inline-block;
  padding: 0.14rem 0.6rem;
  border-radius: var(--radius-pill);
  font-size: 0.725rem;
  font-weight: 650;
  letter-spacing: 0.02em;
  border: 1px solid transparent;
  white-space: nowrap;
}
.badge.active {
  background: var(--ok-soft);
  color: var(--ok);
  border-color: var(--ok-border);
}
.badge.inactive {
  background: var(--danger-soft);
  color: var(--danger);
  border-color: var(--danger-border);
}
/* Late is neither fine nor a failure, and colouring it the same green as
   Present makes a roomful of late arrivals scan as a good day. */
.badge.warn {
  background: var(--warn-soft);
  color: var(--warn);
  border-color: var(--warn-border);
}

/* --- Odds and ends ------------------------------------------------------ */

.holidays {
  list-style: none;
  padding: 0;
  margin: 0;
}
.holidays li {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0.65rem 0;
  border-bottom: 1px solid var(--border);
}
.holidays li:last-child {
  border-bottom: none;
}

.muted {
  color: var(--muted);
}
.small {
  font-size: 0.82rem;
}
.label {
  font-size: 0.84rem;
  color: var(--muted);
  margin-bottom: 0.25rem;
}
.error {
  color: var(--danger);
  background: var(--danger-soft);
  border: 1px solid var(--danger-border);
  border-radius: var(--radius-sm);
  padding: 0.62rem 0.85rem;
  font-size: 0.87rem;
}
/* An error that is only ever a few words inside a table cell or beside a field
   should not become a full-width banner. */
td .error,
.row .error {
  background: none;
  border: none;
  padding: 0;
}
.ok {
  color: var(--ok);
}

@media (prefers-reduced-motion: reduce) {
  * {
    transition: none !important;
  }
}

/* Below this width the sidebar becomes a bar across the top. The nav itself
   wraps onto as many rows as it needs: an admin has 12 links, which a
   horizontal scroller left almost entirely hidden with no visible scrollbar
   to hint more existed (confirmed: ~1.5 links visible out of 12, same on
   every page). Wrapping costs vertical space but needs no gesture nobody is
   told about and no drawer state/scrim to build instead. */
@media (max-width: 60rem) {
  .shell {
    grid-template-columns: minmax(0, 1fr);
  }
  .sidebar {
    position: sticky;
    top: 0;
    z-index: 20;
    height: auto;
    flex-direction: row;
    flex-wrap: wrap;
    align-items: center;
    gap: 0.4rem 0.9rem;
    padding: 0.6rem 0.9rem;
    border-right: none;
    border-bottom: 1px solid var(--border);
  }
  .brand {
    padding: 0;
  }
  .brand__text {
    display: none;
  }
  .sidebar__nav {
    flex-direction: row;
    flex-wrap: wrap;
    flex: 1 1 100%;
    order: 3;
    gap: 0.25rem;
  }
  .sidebar__foot {
    margin-top: 0;
    padding-top: 0;
    border-top: none;
    display: flex;
    align-items: center;
  }
  .who__text {
    display: none;
  }
  .who {
    padding: 0 0.5rem 0 0;
  }
  .signout {
    width: auto;
    white-space: nowrap;
  }
  .app {
    padding: 1.35rem 1rem 4rem;
  }
  .card {
    padding: 1.15rem;
  }
}
</style>
