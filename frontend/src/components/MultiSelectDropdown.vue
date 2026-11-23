<script setup>
// A closed-by-default dropdown, not a native <select multiple>: the native
// control shows every option at once with no clear way to tell "nothing is
// selected" from "something is", and looks like a leftover HTML widget next
// to the rest of this app's styled inputs.
import { computed, onBeforeUnmount, onMounted, ref } from "vue";

const props = defineProps({
  modelValue: { type: Array, default: () => [] },
  options: { type: Array, required: true }, // [{ value, label }]
  placeholder: { type: String, default: "Select…" },
});
const emit = defineEmits(["update:modelValue"]);

const open = ref(false);
const root = ref(null);

const summary = computed(() => {
  if (!props.modelValue.length) return props.placeholder;
  return props.options
    .filter((option) => props.modelValue.includes(option.value))
    .map((option) => option.label)
    .join(", ");
});

function toggle(value) {
  const next = props.modelValue.includes(value)
    ? props.modelValue.filter((v) => v !== value)
    : [...props.modelValue, value];
  emit("update:modelValue", next);
}

function onClickOutside(event) {
  if (root.value && !root.value.contains(event.target)) open.value = false;
}

onMounted(() => document.addEventListener("click", onClickOutside));
onBeforeUnmount(() => document.removeEventListener("click", onClickOutside));
</script>

<template>
  <div
    ref="root"
    class="ms"
  >
    <button
      type="button"
      class="ms__control"
      :class="{ 'ms__control--placeholder': !modelValue.length }"
      @click="open = !open"
    >
      <span class="ms__value">{{ summary }}</span>
      <svg
        class="ms__caret"
        :class="{ 'ms__caret--open': open }"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        stroke-width="2"
        stroke-linecap="round"
        stroke-linejoin="round"
      ><path d="M6 9l6 6 6-6" /></svg>
    </button>
    <div
      v-if="open"
      class="ms__menu"
    >
      <label
        v-for="option in options"
        :key="option.value"
        class="ms__option"
      >
        <input
          type="checkbox"
          :checked="modelValue.includes(option.value)"
          @change="toggle(option.value)"
        >
        {{ option.label }}
      </label>
      <p
        v-if="!options.length"
        class="muted small ms__empty"
      >
        No one to choose from.
      </p>
    </div>
  </div>
</template>

<style scoped>
.ms {
  position: relative;
  /* In a flex `.row` (not a grid column that already fills its own width),
     a bare div sizes to its content and would otherwise squeeze to nearly
     nothing next to a sibling button. */
  min-width: 14rem;
}
.ms__control {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  width: 100%;
  padding: 0.52rem 0.7rem;
  border: 1px solid var(--border-strong);
  border-radius: var(--radius-sm);
  background: var(--surface);
  color: var(--text);
  font: inherit;
  font-size: 0.9rem;
  text-align: left;
  cursor: pointer;
}
.ms__control:hover:not(:disabled) {
  /* Overrides the app-wide `button:hover` accent fill: this control reads
     as an input, not an action button, and must not turn solid blue. */
  background: var(--surface);
  border-color: var(--accent);
}
.ms__control--placeholder .ms__value {
  color: var(--muted);
}
.ms__value {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.ms__caret {
  width: 1rem;
  height: 1rem;
  flex: none;
  color: var(--muted);
  transition: transform 0.15s;
}
.ms__caret--open {
  transform: rotate(180deg);
}
.ms__menu {
  position: absolute;
  z-index: 20;
  top: calc(100% + 0.3rem);
  left: 0;
  right: 0;
  max-height: 14rem;
  overflow-y: auto;
  padding: 0.35rem;
  background: var(--surface);
  border: 1px solid var(--border-strong);
  border-radius: var(--radius-sm);
  box-shadow: var(--shadow-lifted);
}
.ms__option {
  /* `form label` (global) sets flex-direction/margin-bottom too, and CSS
     cascades per property, not per rule — a property this block leaves
     unset still falls through to that rule regardless of specificity
     elsewhere in this block, so both are spelled out here even though
     "row" and "0" sound like they need no explicit value. */
  display: flex;
  flex-direction: row;
  align-items: center;
  gap: 0.55rem;
  margin-bottom: 0;
  padding: 0.4rem 0.5rem;
  border-radius: var(--radius-sm);
  font-size: 0.88rem;
  font-weight: 500;
  color: var(--text);
  cursor: pointer;
}
.ms__option:hover {
  background: var(--surface-sunken);
}
.ms__empty {
  padding: 0.4rem 0.5rem;
}
</style>
