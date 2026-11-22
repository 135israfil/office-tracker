<script setup>
import { computed, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";

import { api } from "@/api/client";
import { dateOnly, describeError } from "@/lib/format";
import { useAuthStore } from "@/stores/auth";

const STATUSES = ["TODO", "IN_PROGRESS", "BLOCKED", "DONE", "CANCELLED"];

const route = useRoute();
const router = useRouter();
const auth = useAuthStore();

const task = ref(null);
const subtasks = ref([]);
const employees = ref([]);
const loading = ref(false);
const error = ref("");
const saveError = ref("");
const assigneeError = ref("");
const subtaskError = ref("");

const newAssigneeId = ref("");
const subtaskForm = ref({ title: "", deadline: "" });
const showSubtaskForm = ref(false);

const myEmployeeId = computed(() => auth.user?.employee?.id ?? null);
const isAdmin = computed(() => auth.isAdmin);
const isCreator = computed(() => task.value && myEmployeeId.value === task.value.created_by.id);
// A sub-task cannot itself have sub-tasks, so that section only makes sense for a
// root task — the same one-level rule the backend enforces.
const isRootTask = computed(() => task.value && task.value.parent_stub === null);

async function load() {
  loading.value = true;
  error.value = "";
  try {
    const [loadedTask, employeeList] = await Promise.all([
      api.getTask(route.params.id),
      api.listAssignableEmployees(),
    ]);
    task.value = loadedTask;
    employees.value = employeeList;
    subtasks.value = loadedTask.parent_stub
      ? []
      : (await api.listTasks({ parent: route.params.id })).results ?? [];
  } catch (err) {
    error.value = describeError(err);
  } finally {
    loading.value = false;
  }
}

async function save(patch) {
  saveError.value = "";
  try {
    // An empty date input is "", not null — DRF's DateField rejects "" outright.
    if ("deadline" in patch) patch = { ...patch, deadline: patch.deadline || null };
    task.value = await api.updateTask(task.value.id, patch);
  } catch (err) {
    saveError.value = describeError(err);
  }
}

async function addAssignee() {
  assigneeError.value = "";
  if (!newAssigneeId.value) return;
  try {
    task.value = await api.addTaskAssignee(task.value.id, newAssigneeId.value);
    newAssigneeId.value = "";
  } catch (err) {
    assigneeError.value = describeError(err);
  }
}

async function removeAssignee(employeeId) {
  assigneeError.value = "";
  try {
    task.value = await api.removeTaskAssignee(task.value.id, employeeId);
  } catch (err) {
    assigneeError.value = describeError(err);
  }
}

async function createSubtask() {
  subtaskError.value = "";
  try {
    await api.createTask({
      ...subtaskForm.value,
      deadline: subtaskForm.value.deadline || null,
      parent: task.value.id,
      assignees: [],
    });
    subtaskForm.value = { title: "", deadline: "" };
    showSubtaskForm.value = false;
    subtasks.value = (await api.listTasks({ parent: task.value.id })).results ?? [];
  } catch (err) {
    subtaskError.value = describeError(err);
  }
}

async function deleteTask() {
  try {
    await api.deleteTask(task.value.id);
    router.push({ name: "tasks" });
  } catch (err) {
    error.value = describeError(err);
  }
}

watch(() => route.params.id, load);
onMounted(load);
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

    <template v-if="task">
      <header class="row">
        <div>
          <p
            v-if="task.parent_stub"
            class="muted small"
          >
            Sub-task of
            <RouterLink :to="`/tasks/${task.parent_stub.id}`">
              {{ task.parent_stub.title }}
            </RouterLink>
          </p>
          <h2>{{ task.title }}</h2>
        </div>
        <button
          v-if="isCreator || isAdmin"
          class="secondary"
          @click="deleteTask"
        >
          Delete task
        </button>
      </header>

      <div class="form-grid">
        <label>
          Title
          <input
            v-model="task.title"
            @change="save({ title: task.title })"
          >
        </label>
        <label>
          Status
          <select
            v-model="task.status"
            @change="save({ status: task.status })"
          >
            <option
              v-for="status in STATUSES"
              :key="status"
              :value="status"
              :disabled="status === 'CANCELLED' && !isCreator && !isAdmin"
            >
              {{ status }}
            </option>
          </select>
        </label>
        <label>
          Deadline
          <input
            v-model="task.deadline"
            type="date"
            @change="save({ deadline: task.deadline })"
          >
        </label>
        <label class="span">
          Description
          <textarea
            v-model="task.description"
            rows="3"
            @change="save({ description: task.description })"
          />
        </label>
      </div>
      <p
        v-if="saveError"
        class="error"
      >
        {{ saveError }}
      </p>
      <p
        v-if="task.is_overdue"
        class="error small"
      >
        Overdue — due {{ dateOnly(task.deadline) }}
      </p>

      <h4>Assignees</h4>
      <ul class="bars">
        <li
          v-for="assignee in task.assignees"
          :key="assignee.employee.id"
        >
          <span>{{ assignee.employee.name }} ({{ assignee.employee.employee_id }})</span>
          <button
            v-if="isCreator || isAdmin || assignee.employee.id === myEmployeeId"
            class="link"
            @click="removeAssignee(assignee.employee.id)"
          >
            {{ assignee.employee.id === myEmployeeId ? "Leave" : "Remove" }}
          </button>
        </li>
        <li
          v-if="!task.assignees.length"
          class="muted"
        >
          Unassigned.
        </li>
      </ul>
      <form
        class="row"
        @submit.prevent="addAssignee"
      >
        <select v-model="newAssigneeId">
          <option value="">
            Add an assignee…
          </option>
          <option
            v-for="employee in employees"
            :key="employee.id"
            :value="employee.id"
          >
            {{ employee.name }} ({{ employee.employee_id }})
          </option>
        </select>
        <button type="submit">
          Add
        </button>
      </form>
      <p
        v-if="assigneeError"
        class="error small"
      >
        {{ assigneeError }}
      </p>

      <template v-if="isRootTask">
        <header class="row">
          <h4>Sub-tasks</h4>
          <button @click="showSubtaskForm = !showSubtaskForm">
            {{ showSubtaskForm ? "Cancel" : "Add sub-task" }}
          </button>
        </header>

        <form
          v-if="showSubtaskForm"
          class="form-grid"
          @submit.prevent="createSubtask"
        >
          <label>Title<input
            v-model="subtaskForm.title"
            required
          ></label>
          <label>Deadline<input
            v-model="subtaskForm.deadline"
            type="date"
          ></label>
          <p
            v-if="subtaskError"
            class="error span"
          >
            {{ subtaskError }}
          </p>
          <button
            class="span"
            type="submit"
          >
            Create sub-task
          </button>
        </form>

        <ul class="bars">
          <li
            v-for="subtask in subtasks"
            :key="subtask.id"
          >
            <RouterLink :to="`/tasks/${subtask.id}`">
              {{ subtask.title }}
            </RouterLink>
            <span :class="['badge', subtask.status === 'DONE' ? 'active' : '']">
              {{ subtask.status }}
            </span>
          </li>
          <li
            v-if="!subtasks.length"
            class="muted"
          >
            No sub-tasks yet.
          </li>
        </ul>
      </template>
    </template>
  </section>
</template>
