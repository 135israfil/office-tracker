<script setup>
// Drawn inline rather than pulled from an icon package: nine glyphs do not justify a
// dependency, and an intranet deployment should not fetch anything at run time.
// All of them share one 24x24 grid and one stroke weight so they sit together evenly.
defineProps({
  name: { type: String, required: true },
});
</script>

<template>
  <svg
    class="icon"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    stroke-width="1.75"
    stroke-linecap="round"
    stroke-linejoin="round"
    aria-hidden="true"
  >
    <template v-if="name === 'grid'">
      <rect
        x="3"
        y="3"
        width="7.5"
        height="7.5"
        rx="1.6"
      />
      <rect
        x="13.5"
        y="3"
        width="7.5"
        height="7.5"
        rx="1.6"
      />
      <rect
        x="3"
        y="13.5"
        width="7.5"
        height="7.5"
        rx="1.6"
      />
      <rect
        x="13.5"
        y="13.5"
        width="7.5"
        height="7.5"
        rx="1.6"
      />
    </template>

    <template v-else-if="name === 'clock'">
      <circle
        cx="12"
        cy="12"
        r="9"
      />
      <path d="M12 7v5.2l3.2 1.9" />
    </template>

    <template v-else-if="name === 'pulse'">
      <path d="M3 12h3.5l2.5-6 4 12 2.5-6H21" />
    </template>

    <template v-else-if="name === 'calendar'">
      <rect
        x="3"
        y="5"
        width="18"
        height="16"
        rx="2.5"
      />
      <path d="M8 3v4M16 3v4M3 10.5h18" />
    </template>

    <template v-else-if="name === 'chart'">
      <path d="M3.5 20.5h17" />
      <path d="M7 20.5v-5.5M12 20.5V8M17 20.5v-8.5" />
    </template>

    <template v-else-if="name === 'users'">
      <circle
        cx="9.5"
        cy="8"
        r="3.6"
      />
      <path d="M3 20c0-3.4 2.9-5.4 6.5-5.4s6.5 2 6.5 5.4" />
      <path d="M17 5.2a3.6 3.6 0 0 1 0 6.9" />
      <path d="M18.4 15c1.7.8 2.6 2.4 2.6 5" />
    </template>

    <template v-else-if="name === 'monitor'">
      <rect
        x="2.5"
        y="4"
        width="19"
        height="12.5"
        rx="2.5"
      />
      <path d="M9 20.5h6M12 16.5v4" />
    </template>

    <template v-else-if="name === 'sliders'">
      <path d="M4 8h9M18.5 8H20M4 16h5M14.5 16H20" />
      <circle
        cx="15.75"
        cy="8"
        r="2.25"
      />
      <circle
        cx="11.75"
        cy="16"
        r="2.25"
      />
    </template>

    <template v-else-if="name === 'home'">
      <path d="M3 10.6 12 3.5l9 7.1" />
      <path d="M5.6 9.4V20.5h12.8V9.4" />
    </template>

    <template v-else-if="name === 'check-square'">
      <rect
        x="3.5"
        y="3.5"
        width="17"
        height="17"
        rx="3"
      />
      <path d="M7.5 12.3l3 3 6-6.6" />
    </template>

    <template v-else-if="name === 'key'">
      <circle
        cx="8"
        cy="15.5"
        r="4.25"
      />
      <path d="M11 12.5 19.5 4" />
      <path d="M15.5 8l2.5 2.5M18.5 5l2 2" />
    </template>

    <template v-else-if="name === 'calendar-event'">
      <rect
        x="3"
        y="5"
        width="18"
        height="16"
        rx="2.5"
      />
      <path d="M8 3v4M16 3v4M3 10.5h18" />
      <circle
        cx="12"
        cy="15.5"
        r="1.6"
        fill="currentColor"
        stroke="none"
      />
    </template>

    <template v-else-if="name === 'bell'">
      <path d="M6 10.5a6 6 0 0 1 12 0c0 4 1.5 5.5 2 6.5H4c.5-1 2-2.5 2-6.5Z" />
      <path d="M10 19.5a2 2 0 0 0 4 0" />
    </template>

    <template v-else-if="name === 'menu'">
      <path d="M4 7h16M4 12h16M4 17h16" />
    </template>

    <template v-else-if="name === 'x'">
      <path d="M6 6l12 12M18 6 6 18" />
    </template>
  </svg>
</template>

<style scoped>
.icon {
  width: 1.15rem;
  height: 1.15rem;
  flex: none;
}
</style>
