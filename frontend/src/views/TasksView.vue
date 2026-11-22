<script setup>
import { computed, onMounted, ref } from "vue";

import { api } from "@/api/client";
import { dateOnly, describeError } from "@/lib/format";

const tasks = ref([]);
const employees = ref([]);
const loading = ref(false);
const error = ref("");
const formError = ref("");
const showForm = ref(false);

const blankForm = () => ({ title: "", description: "", deadline: "", assignees: [] });
const form = ref(blankForm());

// Reuses this app's existing semantic badge colours (active/inactive/warn) rather than
// inventing one colour per status, so a 5-value status field still reads at a glance.
const STATUS_BADGE = {
  TODO: "",
  IN_PROGRESS: "warn",
  BLOCKED: "warn",
  DONE: "active",
  CANCELLED: "inactive",
};

// Overdue tasks first, then soonest deadline, then everything else in the order the
// API returned it (newest created first) — computed here rather than in the backend
// query, since is_overdue is a read-time Python rule, not a database column.
const sortedTasks = computed(() =>
  [...tasks.value].sort((a, b) => {
    if (a.is_overdue !== b.is_overdue) return a.is_overdue ? -1 : 1;
    if (a.deadline && b.deadline) return a.deadline < b.deadline ? -1 : 1;
    if (a.deadline) return -1;
    if (b.deadline) return 1;
    return 0;
  }),
);

async function load() {
  loading.value = true;
  error.value = "";
  try {
    const [list, employeeList] = await Promise.all([
      api.listTasks(),
      api.listAssignableEmployees(),
    ]);
    tasks.value = list.results ?? list;
    employees.value = employeeList;
  } catch (err) {
    error.value = describeError(err);
  } finally {
    loading.value = false;
  }
}

async function createTask() {
  formError.value = "";
  try {
    // An empty date input is "", not null — DRF's DateField rejects "" outright,
    // so a task created with no deadline would otherwise fail validation.
    await api.createTask({ ...form.value, deadline: form.value.deadline || null });
    form.value = blankForm();
    showForm.value = false;
    await load();
  } catch (err) {
    formError.value = describeError(err);
  }
}

onMounted(load);
</script>

<template>
  <section class="card">
    <header class="row">
      <h2>Tasks</h2>
      <button @click="showForm = !showForm">
        {{ showForm ? "Cancel" : "New task" }}
      </button>
    </header>

    <form
      v-if="showForm"
      class="form-grid"
      @submit.prevent="createTask"
    >
      <label>Title<input
        v-model="form.title"
        required
      ></label>
      <label>Deadline<input
        v-model="form.deadline"
        type="date"
      ></label>
      <label class="span">
        Description
        <textarea
          v-model="form.description"
          rows="2"
        />
      </label>
      <label class="span">
        Assignees
        <select
          v-model="form.assignees"
          multiple
          size="5"
        >
          <option
            v-for="employee in employees"
            :key="employee.id"
            :value="employee.id"
          >
            {{ employee.name }} ({{ employee.employee_id }})
          </option>
        </select>
      </label>
      <p
        v-if="formError"
        class="error span"
      >
        {{ formError }}
      </p>
      <button
        class="span"
        type="submit"
      >
        Create task
      </button>
    </form>

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
            <th>Title</th>
            <th>Status</th>
            <th>Deadline</th>
            <th>Assignees</th>
            <th>Created by</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="task in sortedTasks"
            :key="task.id"
            class="task-row"
            @click="$router.push(`/tasks/${task.id}`)"
          >
            <td>{{ task.title }}</td>
            <td>
              <span :class="['badge', STATUS_BADGE[task.status]]">{{ task.status }}</span>
            </td>
            <td :class="{ overdue: task.is_overdue }">
              {{ dateOnly(task.deadline) }}
              <span
                v-if="task.is_overdue"
                class="overdue-tag"
              >Overdue</span>
            </td>
            <td>
              <span
                v-for="assignee in task.assignees"
                :key="assignee.employee.id"
                class="chip"
              >{{ assignee.employee.name }}</span>
              <span
                v-if="!task.assignees.length"
                class="muted"
              >Unassigned</span>
            </td>
            <td>{{ task.created_by.name }}</td>
          </tr>
          <tr v-if="!sortedTasks.length && !loading">
            <td
              colspan="5"
              class="muted"
            >
              No tasks yet.
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>
</template>

<style scoped>
.task-row {
  cursor: pointer;
}
.overdue {
  color: var(--danger);
}
.overdue-tag {
  margin-left: 0.4rem;
  font-size: 0.75rem;
  font-weight: 600;
  text-transform: uppercase;
}
</style>
