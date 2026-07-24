// =============================================================================
// Constants (single source of truth)
// =============================================================================
const API_BASE = "/api";
const COLUMNS = ["To Do", "In Progress", "In Review", "Done"];
const DONE_COLUMN = "Done";

const DEFAULT_PRIORITY = "Medium";
const PRIORITIES = ["Low", "Medium", "High", "Urgent"];

const WIP_LIMITS_STORAGE_KEY = "canban-wip-limits";
const THEME_STORAGE_KEY = "canban-theme";

// Default matches the `selected` <option> for both sprint-duration <select>s in
// index.html (Start Sprint and Plan Next Sprint) -- keep them in sync.
const DEFAULT_SPRINT_DURATION = "2";

// Archive/Unarchive is disabled pending a redesign. UI entry points are
// hidden in index.html; this also stops the frontend from creating the
// per-card archive button or polling the archive badge.
const ARCHIVE_ENABLED = false;

// =============================================================================
// DOM element lookups
// =============================================================================
const $ = (id) => document.getElementById(id);

const dom = {
  // Task-create modal
  modalOverlay: $("modal-overlay"),
  modalCancelBtn: $("modal-cancel"),
  taskForm: $("task-form"),
  titleInput: $("task-title"),
  descriptionInput: $("task-description"),
  columnSelect: $("task-column"),
  priorityInput: $("task-priority"),
  blockedByField: $("task-blocked-by-field"),
  blockedByInput: $("task-blocked-by"),
  dueDateInput: $("task-due-date"),

  // Task-detail modal
  taskDetailModalOverlay: $("task-detail-modal-overlay"),
  taskDetailForm: $("task-detail-form"),
  detailId: $("detail-id"),
  detailTitle: $("detail-title"),
  detailDescription: $("detail-description"),
  detailTags: $("detail-tags"),
  detailBlockedByField: $("detail-blocked-by-field"),
  detailBlockedByInput: $("detail-blocked-by"),
  detailDueDateInput: $("detail-due-date"),
  detailSaveBtn: $("detail-save-btn"),
  taskDetailCloseBtn: $("task-detail-close"),
  detailSubtaskList: $("detail-subtask-list"),
  detailSubtaskInput: $("detail-subtask-input"),
  detailSubtaskAddBtn: $("detail-subtask-add-btn"),
  detailSubtaskProgress: $("detail-subtask-progress"),
  detailNotesList: $("detail-notes-list"),
  detailNotesEmptyMessage: $("detail-notes-empty-message"),
  detailNoteInput: $("detail-note-input"),
  detailNoteAddBtn: $("detail-note-add-btn"),

  // Toast / theme / backup FABs
  errorToast: $("error-toast"),
  themeToggle: $("theme-toggle"),
  exportFab: $("export-fab"),
  importFab: $("import-fab"),
  importFileInput: $("import-file-input"),

  // Trash (recycle bin)
  trashFab: $("trash-fab"),
  trashBadge: $("trash-badge"),
  trashModalOverlay: $("trash-modal-overlay"),
  trashList: $("trash-list"),
  trashEmptyMessage: $("trash-empty-message"),
  emptyTrashBtn: $("empty-trash-btn"),
  trashModalClose: $("trash-modal-close"),

  // Archive
  archiveFab: $("archive-fab"),
  archiveBadge: $("archive-badge"),
  archiveModalOverlay: $("archive-modal-overlay"),
  archiveList: $("archive-list"),
  archiveEmptyMessage: $("archive-empty-message"),
  archiveModalClose: $("archive-modal-close"),
  archiveAllBtn: $("archive-all-btn"),

  // Confirm modal
  confirmModalOverlay: $("confirm-modal-overlay"),
  confirmMessage: $("confirm-message"),
  confirmCancelBtn: $("confirm-cancel"),
  confirmConfirmBtn: $("confirm-confirm"),

  // Filters
  filterSearchInput: $("filter-search"),
  filterPrioritySelect: $("filter-priority"),
  filterBlockedOnlyInput: $("filter-blocked-only"),
  filterClearBtn: $("filter-clear"),

  // Sprint banner + start/end modal
  sprintBannerActive: $("sprint-banner-active"),
  sprintBannerInactive: $("sprint-banner-inactive"),
  sprintBannerName: $("sprint-banner-name"),
  sprintBannerDates: $("sprint-banner-dates"),
  sprintBannerDays: $("sprint-banner-days"),
  startSprintBtn: $("start-sprint-btn"),
  endSprintBtn: $("end-sprint-btn"),
  sprintModalOverlay: $("sprint-modal-overlay"),
  sprintModalTitle: $("sprint-modal-title"),
  sprintModalHint: $("sprint-modal-hint"),
  sprintModalSubmitBtn: $("sprint-modal-submit"),
  sprintForm: $("sprint-form"),
  sprintNameInput: $("sprint-name"),
  sprintDurationSelect: $("sprint-duration"),
  sprintModalCancelBtn: $("sprint-modal-cancel"),

  // Past ("Older") sprints modal
  pastSprintsFab: $("past-sprints-fab"),
  pastSprintsModalOverlay: $("past-sprints-modal-overlay"),
  pastSprintsList: $("past-sprints-list"),
  pastSprintsEmptyMessage: $("past-sprints-empty-message"),
  pastSprintsModalClose: $("past-sprints-modal-close"),

  // Last sprint panel
  lastSprintSummaryInfo: $("last-sprint-summary-info"),
  lastSprintBody: $("last-sprint-body"),

  // Next (planned) sprint panel
  nextSprintSummaryInfo: $("next-sprint-summary-info"),
  nextSprintPlanned: $("next-sprint-planned"),
  nextSprintName: $("next-sprint-name"),
  nextSprintDuration: $("next-sprint-duration"),
  nextSprintAnticipated: $("next-sprint-anticipated"),
  nextSprintEmptyMessage: $("next-sprint-empty-message"),
  planSprintForm: $("plan-sprint-form"),
  planSprintNameInput: $("plan-sprint-name"),
  planSprintDurationSelect: $("plan-sprint-duration"),
};

// =============================================================================
// Module state
// =============================================================================
let toastTimer = null;
let pendingConfirmAction = null;
let currentDetailTask = null;
let sprintModalMode = "start";

// Sprint state manager: single holder for the active/planned sprint data that
// several render/refresh functions read and write. `activeId` is what the Done
// column's sprint filtering (see tasksForColumn) keys off of.
const sprintState = {
  activeId: null,
  active: null,
  planned: null,
  setActive(sprint) {
    this.active = sprint;
    this.activeId = sprint ? sprint.id : null;
  },
  setPlanned(sprint) {
    this.planned = sprint;
  },
};

// =============================================================================
// CSS class helpers
// =============================================================================
function addClass(el, cls) {
  el.classList.add(cls);
}

function removeClass(el, cls) {
  el.classList.remove(cls);
}

function toggleClass(el, cls, force) {
  return arguments.length > 2 ? el.classList.toggle(cls, force) : el.classList.toggle(cls);
}

// =============================================================================
// Modal / overlay helpers
// =============================================================================
function openOverlay(overlay) {
  addClass(overlay, "open");
}

function closeOverlay(overlay) {
  removeClass(overlay, "open");
}

function isOverlayOpen(overlay) {
  return overlay.classList.contains("open");
}

// Wire an overlay's shared dismiss triggers: its close/cancel button (if any)
// and a click on the backdrop itself.
function wireOverlayDismiss(overlay, close, closeBtn) {
  if (closeBtn) closeBtn.addEventListener("click", close);
  overlay.addEventListener("click", (event) => {
    if (event.target === overlay) close();
  });
}

// =============================================================================
// Fetch API wrapper
// =============================================================================
// Low-level: builds `${API_BASE}${path}`, sets JSON headers + stringifies the
// body when one is given, and returns the raw Response. Callers keep doing their
// own encodeURIComponent on ids in `path`.
function apiFetch(path, { method, body } = {}) {
  const options = {};
  if (method) options.method = method;
  if (body !== undefined) {
    options.headers = { "Content-Type": "application/json" };
    options.body = JSON.stringify(body);
  }
  return fetch(`${API_BASE}${path}`, options);
}

const api = {
  get: (path) => apiFetch(path),
  post: (path, body) => apiFetch(path, { method: "POST", body }),
  put: (path, body) => apiFetch(path, { method: "PUT", body }),
  del: (path) => apiFetch(path, { method: "DELETE" }),
};

// Shared "did the request succeed?" gate: on failure surfaces the API's error
// message via the toast and returns false, so callers can `if (!(await
// ensureOk(res))) return ...`.
async function ensureOk(res) {
  if (res.ok) return true;
  await handleApiError(res);
  return false;
}

async function handleApiError(res) {
  const body = await res.json().catch(() => ({}));
  showError(body.detail || "Something went wrong.");
}

function showError(message) {
  dom.errorToast.textContent = message;
  addClass(dom.errorToast, "visible");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => removeClass(dom.errorToast, "visible"), 4000);
}

// =============================================================================
// Utilities (date formatting + task filtering)
// =============================================================================
function formatRelativeTime(isoString) {
  const then = new Date(isoString).getTime();
  const seconds = Math.max(0, Math.floor((Date.now() - then) / 1000));

  if (seconds < 60) return "just now";
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

function formatDueDate(dueDate) {
  return new Date(dueDate).toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

function isOverdue(dueDate, column) {
  if (column === DONE_COLUMN) return false;
  return new Date(dueDate).getTime() < Date.now();
}

function formatSprintDate(dateString) {
  return new Date(`${dateString}T00:00:00`).toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
  });
}

function formatDaysRemaining(endDateString) {
  const end = new Date(`${endDateString}T00:00:00`);
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const days = Math.round((end.getTime() - today.getTime()) / (1000 * 60 * 60 * 24));

  if (days > 1) return { label: `${days} days left`, overdue: false };
  if (days === 1) return { label: "1 day left", overdue: false };
  if (days === 0) return { label: "Ends today", overdue: false };
  return { label: `${Math.abs(days)}d overdue`, overdue: true };
}

function tasksForColumn(column, board) {
  const tasks = board[column] || [];
  if (column !== DONE_COLUMN || sprintState.activeId === null) return tasks;

  // Done is the one column that isn't inherently sprint-scoped (it holds
  // every completion ever, not just this sprint's) -- filter it down to the
  // active sprint's completions, but keep legacy tasks that predate sprints
  // entirely (sprint_id null) since they'd otherwise vanish from view with
  // nowhere else to surface them.
  return tasks.filter(
    (task) => task.sprint_id === sprintState.activeId || task.sprint_id == null
  );
}

// =============================================================================
// Board rendering
// =============================================================================
async function loadBoard() {
  const res = await api.get("/tasks");
  const board = await res.json();
  renderBoard(board);
}

function renderBoard(board) {
  for (const column of COLUMNS) {
    const list = document.querySelector(`.task-list[data-column="${column}"]`);
    const countEl = document.getElementById(`count-${column}`);
    const tasks = tasksForColumn(column, board);

    list.replaceChildren();
    for (const task of tasks) {
      list.appendChild(createCardElement(column, task));
    }
    countEl.textContent = tasks.length;
    syncWipLimitInput(column);
    updateWipLimitIndicator(column, tasks.length);
    if (column === DONE_COLUMN) dom.archiveAllBtn.disabled = tasks.length === 0;
  }
  applyFilters();
}

function loadWipLimits() {
  try {
    const stored = JSON.parse(localStorage.getItem(WIP_LIMITS_STORAGE_KEY));
    return stored && typeof stored === "object" ? stored : {};
  } catch {
    return {};
  }
}

function getWipLimit(column) {
  const limits = loadWipLimits();
  const limit = limits[column];
  return typeof limit === "number" && limit > 0 ? limit : null;
}

function setWipLimit(column, limit) {
  const limits = loadWipLimits();
  if (limit === null) {
    delete limits[column];
  } else {
    limits[column] = limit;
  }
  localStorage.setItem(WIP_LIMITS_STORAGE_KEY, JSON.stringify(limits));
}

function syncWipLimitInput(column) {
  const input = document.getElementById(`wip-limit-${column}`);
  if (!input || document.activeElement === input) return;
  const limit = getWipLimit(column);
  input.value = limit === null ? "" : String(limit);
}

function updateWipLimitIndicator(column, count) {
  const countEl = document.getElementById(`count-${column}`);
  const input = document.getElementById(`wip-limit-${column}`);
  const limit = getWipLimit(column);
  const overLimit = limit !== null && count > limit;
  toggleClass(countEl, "over-limit", overLimit);
  countEl.title = overLimit ? `${count} of ${limit} WIP limit exceeded` : "";
  if (input) toggleClass(input, "over-limit", overLimit);
}

function commitWipLimitInput(input) {
  const column = input.dataset.column;
  const raw = input.value.trim();
  let limit = null;
  if (raw !== "") {
    const parsed = parseInt(raw, 10);
    limit = Number.isNaN(parsed) || parsed <= 0 ? null : parsed;
  }
  setWipLimit(column, limit);
  input.value = limit === null ? "" : String(limit);
  const countEl = document.getElementById(`count-${column}`);
  const count = parseInt(countEl.textContent, 10) || 0;
  updateWipLimitIndicator(column, count);
}

function createCardElement(column, task) {
  const card = document.createElement("div");
  card.className = "card";
  card.draggable = true;
  card.dataset.id = task.id;
  card.dataset.column = column;
  card.dataset.priority = task.priority || DEFAULT_PRIORITY;
  card.dataset.blocked = task.blocked_by ? "true" : "false";
  card.dataset.searchText = `${task.title} ${task.description || ""}`.toLowerCase();

  const idTag = document.createElement("span");
  idTag.className = "card-id";
  idTag.textContent = task.id;
  card.appendChild(idTag);

  const title = document.createElement("p");
  title.className = "card-title";
  title.textContent = task.title;
  card.appendChild(title);

  if (task.description) {
    const description = document.createElement("p");
    description.className = "card-description";
    description.textContent = task.description;
    card.appendChild(description);
  }

  const prioritySelect = document.createElement("select");
  prioritySelect.className = "priority-pill";
  prioritySelect.draggable = false;
  const priority = task.priority || DEFAULT_PRIORITY;
  prioritySelect.dataset.priority = priority;
  for (const level of PRIORITIES) {
    const option = document.createElement("option");
    option.value = level;
    option.textContent = level;
    option.selected = level === priority;
    prioritySelect.appendChild(option);
  }
  prioritySelect.addEventListener("mousedown", (event) => event.stopPropagation());
  prioritySelect.addEventListener("click", (event) => event.stopPropagation());
  prioritySelect.addEventListener("change", () => {
    prioritySelect.dataset.priority = prioritySelect.value;
    card.dataset.priority = prioritySelect.value;
    setPriority(task.id, prioritySelect.value);
  });

  const tags = document.createElement("div");
  tags.className = "card-tags";
  tags.appendChild(prioritySelect);

  if (task.blocked_by) {
    const tag = document.createElement("span");
    tag.className = "card-tag blocked-by";
    tag.textContent = `Blocked by ${task.blocked_by}`;
    tags.appendChild(tag);
  }

  if (task.blocks && task.blocks.length) {
    const tag = document.createElement("span");
    tag.className = "card-tag blocks";
    tag.textContent = `Blocks ${task.blocks.join(", ")}`;
    tags.appendChild(tag);
  }

  if (task.due_date) {
    const tag = document.createElement("span");
    if (isOverdue(task.due_date, column)) {
      tag.className = "card-tag overdue";
      tag.textContent = "Overdue";
    } else {
      tag.className = "card-tag due-date";
      tag.textContent = `Due ${formatDueDate(task.due_date)}`;
    }
    tags.appendChild(tag);
  }

  if (task.subtask_total) {
    const tag = document.createElement("span");
    tag.className = "card-tag subtask-progress";
    tag.textContent = `${task.subtask_done} / ${task.subtask_total}`;
    tags.appendChild(tag);
  }

  card.appendChild(tags);

  if (task.updated_at) {
    const updated = document.createElement("p");
    updated.className = "card-updated";
    updated.textContent = `Updated ${formatRelativeTime(task.updated_at)}`;
    card.appendChild(updated);
  }

  if (ARCHIVE_ENABLED && column === DONE_COLUMN) {
    const archiveBtn = document.createElement("button");
    archiveBtn.className = "card-archive";
    archiveBtn.draggable = false;
    archiveBtn.title = "Archive task";
    archiveBtn.setAttribute("aria-label", "Archive task");
    archiveBtn.innerHTML =
      '<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="3" width="20" height="5" rx="1"></rect><path d="M4 8v11a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8"></path><path d="M10 12h4"></path></svg>';
    archiveBtn.addEventListener("mousedown", (event) => event.stopPropagation());
    archiveBtn.addEventListener("click", (event) => {
      event.stopPropagation();
      archiveTask(task.id);
    });
    card.appendChild(archiveBtn);
  }

  if (column !== DONE_COLUMN) {
    const deleteBtn = document.createElement("button");
    deleteBtn.className = "card-delete";
    deleteBtn.textContent = "×";
    deleteBtn.title = "Delete task";
    deleteBtn.addEventListener("click", (event) => {
      event.stopPropagation();
      deleteTask(task.id);
    });
    card.appendChild(deleteBtn);
  }

  card.addEventListener("click", () => openTaskDetail(column, task));

  card.addEventListener("dragstart", () => {
    addClass(card, "dragging");
  });
  card.addEventListener("dragend", () => {
    removeClass(card, "dragging");
  });

  return card;
}

// =============================================================================
// Task CRUD
// =============================================================================
async function createTask(column, title, description, blockedBy, priority, dueDate) {
  const res = await api.post("/tasks", {
    column,
    title,
    description,
    blocked_by: blockedBy || null,
    priority: priority || DEFAULT_PRIORITY,
    due_date: dueDate || null,
  });
  if (!(await ensureOk(res))) return false;
  await loadBoard();
  return true;
}

async function setPriority(taskId, priority) {
  await api.put(`/tasks/${encodeURIComponent(taskId)}/priority`, { priority });
  await loadBoard();
}

async function moveTask(taskId, toColumn) {
  const res = await api.put(`/tasks/${encodeURIComponent(taskId)}/move`, { to_column: toColumn });
  if (!(await ensureOk(res))) return false;
  await loadBoard();
  return true;
}

async function setBlockedBy(taskId, blockedBy) {
  const res = await api.put(`/tasks/${encodeURIComponent(taskId)}/blocked-by`, {
    blocked_by: blockedBy || null,
  });
  if (!(await ensureOk(res))) return false;
  await loadBoard();
  return true;
}

async function setDueDate(taskId, dueDate) {
  const res = await api.put(`/tasks/${encodeURIComponent(taskId)}/due-date`, {
    due_date: dueDate || null,
  });
  if (!(await ensureOk(res))) return false;
  await loadBoard();
  return true;
}

async function deleteTask(taskId) {
  const res = await api.del(`/tasks/${encodeURIComponent(taskId)}`);
  if (!(await ensureOk(res))) return;
  await loadBoard();
  await refreshTrashBadge();
}

// =============================================================================
// Subtasks
// =============================================================================
async function fetchSubtasks(taskId) {
  const res = await api.get(`/tasks/${encodeURIComponent(taskId)}/subtasks`);
  if (!res.ok) return [];
  return res.json();
}

async function addSubtask(taskId, title) {
  const res = await api.post(`/tasks/${encodeURIComponent(taskId)}/subtasks`, { title });
  if (!(await ensureOk(res))) return false;
  await renderDetailSubtasks(taskId);
  await loadBoard();
  return true;
}

async function toggleSubtask(taskId, subtaskId, done) {
  const res = await api.put(
    `/tasks/${encodeURIComponent(taskId)}/subtasks/${encodeURIComponent(subtaskId)}`,
    { done }
  );
  if (!(await ensureOk(res))) return false;
  await renderDetailSubtasks(taskId);
  await loadBoard();
  return true;
}

async function deleteSubtask(taskId, subtaskId) {
  const res = await api.del(
    `/tasks/${encodeURIComponent(taskId)}/subtasks/${encodeURIComponent(subtaskId)}`
  );
  if (!(await ensureOk(res))) return false;
  await renderDetailSubtasks(taskId);
  await loadBoard();
  return true;
}

function createSubtaskItemElement(taskId, subtask) {
  const item = document.createElement("div");
  item.className = "subtask-item";

  const checkbox = document.createElement("input");
  checkbox.type = "checkbox";
  checkbox.checked = subtask.done;
  checkbox.addEventListener("change", () => {
    toggleSubtask(taskId, subtask.id, checkbox.checked);
  });
  item.appendChild(checkbox);

  const title = document.createElement("span");
  title.className = "subtask-item-title";
  title.textContent = subtask.title;
  if (subtask.done) addClass(title, "done");
  item.appendChild(title);

  const deleteBtn = document.createElement("button");
  deleteBtn.type = "button";
  deleteBtn.className = "subtask-item-delete";
  deleteBtn.textContent = "×";
  deleteBtn.title = "Delete subtask";
  deleteBtn.addEventListener("click", () => deleteSubtask(taskId, subtask.id));
  item.appendChild(deleteBtn);

  return item;
}

async function renderDetailSubtasks(taskId) {
  const subtasks = await fetchSubtasks(taskId);
  dom.detailSubtaskList.replaceChildren();
  for (const subtask of subtasks) {
    dom.detailSubtaskList.appendChild(createSubtaskItemElement(taskId, subtask));
  }
  const done = subtasks.filter((s) => s.done).length;
  dom.detailSubtaskProgress.textContent = subtasks.length ? `${done} / ${subtasks.length}` : "";
}

// =============================================================================
// Notes
// =============================================================================
async function fetchNotes(taskId) {
  const res = await api.get(`/tasks/${encodeURIComponent(taskId)}/notes`);
  if (!res.ok) return [];
  return res.json();
}

async function addNote(taskId, body) {
  const res = await api.post(`/tasks/${encodeURIComponent(taskId)}/notes`, { body });
  if (!(await ensureOk(res))) return false;
  await renderDetailNotes(taskId);
  return true;
}

function createNoteItemElement(note) {
  const item = document.createElement("div");
  item.className = "note-item";

  const body = document.createElement("p");
  body.className = "note-item-body";
  body.textContent = note.body;
  item.appendChild(body);

  const meta = document.createElement("span");
  meta.className = "note-item-meta";
  meta.textContent = formatRelativeTime(note.created_at);
  item.appendChild(meta);

  return item;
}

async function renderDetailNotes(taskId) {
  const notes = await fetchNotes(taskId);
  dom.detailNotesList.replaceChildren();
  for (const note of notes) {
    dom.detailNotesList.appendChild(createNoteItemElement(note));
  }
  toggleClass(dom.detailNotesEmptyMessage, "hidden", notes.length > 0);
}

// =============================================================================
// Archive
// =============================================================================
async function archiveTask(taskId) {
  const res = await api.post(`/tasks/${encodeURIComponent(taskId)}/archive`);
  if (!(await ensureOk(res))) return;
  await loadBoard();
  await refreshArchiveBadge();
}

async function archiveAllDone() {
  const res = await api.post("/tasks/archive-done");
  if (!(await ensureOk(res))) return;
  await loadBoard();
  await refreshArchiveBadge();
}

async function fetchArchive() {
  const res = await api.get("/archive");
  return res.json();
}

async function refreshArchiveBadge() {
  const archived = await fetchArchive();
  dom.archiveBadge.textContent = archived.length;
  toggleClass(dom.archiveBadge, "hidden", archived.length === 0);
}

function createArchiveItemElement(item) {
  const el = document.createElement("div");
  el.className = "trash-item";

  const header = document.createElement("div");
  header.className = "trash-item-header";

  const title = document.createElement("span");
  title.className = "trash-item-title";
  title.textContent = item.title;
  header.appendChild(title);

  const idTag = document.createElement("span");
  idTag.className = "trash-item-id";
  idTag.textContent = item.id;
  header.appendChild(idTag);

  el.appendChild(header);

  const meta = document.createElement("p");
  meta.className = "trash-item-meta";
  meta.textContent = `Archived ${formatRelativeTime(item.archived_at)}`;
  el.appendChild(meta);

  const actions = document.createElement("div");
  actions.className = "trash-item-actions";

  const unarchiveBtn = document.createElement("button");
  unarchiveBtn.className = "unarchive-btn";
  unarchiveBtn.textContent = "Unarchive";
  unarchiveBtn.addEventListener("click", () => unarchiveTask(item.id));
  actions.appendChild(unarchiveBtn);

  el.appendChild(actions);
  return el;
}

async function renderArchive() {
  const archived = await fetchArchive();
  dom.archiveList.replaceChildren();
  for (const item of archived) {
    dom.archiveList.appendChild(createArchiveItemElement(item));
  }
  toggleClass(dom.archiveEmptyMessage, "hidden", archived.length > 0);
  dom.archiveBadge.textContent = archived.length;
  toggleClass(dom.archiveBadge, "hidden", archived.length === 0);
}

async function unarchiveTask(taskId) {
  const res = await api.post(`/archive/${encodeURIComponent(taskId)}/unarchive`);
  if (!(await ensureOk(res))) return;
  await renderArchive();
  await loadBoard();
}

// =============================================================================
// Trash (recycle bin)
// =============================================================================
async function fetchTrash() {
  const res = await api.get("/trash");
  return res.json();
}

async function refreshTrashBadge() {
  const trashed = await fetchTrash();
  dom.trashBadge.textContent = trashed.length;
  toggleClass(dom.trashBadge, "hidden", trashed.length === 0);
}

function createTrashItemElement(item) {
  const el = document.createElement("div");
  el.className = "trash-item";

  const header = document.createElement("div");
  header.className = "trash-item-header";

  const title = document.createElement("span");
  title.className = "trash-item-title";
  title.textContent = item.title;
  header.appendChild(title);

  const idTag = document.createElement("span");
  idTag.className = "trash-item-id";
  idTag.textContent = item.id;
  header.appendChild(idTag);

  el.appendChild(header);

  const meta = document.createElement("p");
  meta.className = "trash-item-meta";
  meta.textContent = `Deleted from ${item.deleted_from} • ${formatRelativeTime(item.deleted_at)}`;
  el.appendChild(meta);

  const actions = document.createElement("div");
  actions.className = "trash-item-actions";

  const restoreBtn = document.createElement("button");
  restoreBtn.className = "restore-btn";
  restoreBtn.textContent = "Restore";
  restoreBtn.addEventListener("click", () => restoreTask(item.id));
  actions.appendChild(restoreBtn);

  const permanentDeleteBtn = document.createElement("button");
  permanentDeleteBtn.className = "permanent-delete-btn";
  permanentDeleteBtn.textContent = "Delete Permanently";
  permanentDeleteBtn.addEventListener("click", () => {
    confirmAction(`Permanently delete "${item.title}" (${item.id})? This can't be undone.`, () =>
      permanentDeleteTask(item.id)
    );
  });
  actions.appendChild(permanentDeleteBtn);

  el.appendChild(actions);
  return el;
}

async function renderTrash() {
  const trashed = await fetchTrash();
  dom.trashList.replaceChildren();
  for (const item of trashed) {
    dom.trashList.appendChild(createTrashItemElement(item));
  }
  toggleClass(dom.trashEmptyMessage, "hidden", trashed.length > 0);
  dom.trashBadge.textContent = trashed.length;
  toggleClass(dom.trashBadge, "hidden", trashed.length === 0);
}

async function restoreTask(taskId) {
  const res = await api.post(`/trash/${encodeURIComponent(taskId)}/restore`);
  if (!(await ensureOk(res))) return;
  await renderTrash();
  await loadBoard();
}

async function permanentDeleteTask(taskId) {
  await api.del(`/trash/${encodeURIComponent(taskId)}`);
  await renderTrash();
}

async function emptyTrash() {
  await api.del("/trash");
  await renderTrash();
}

// =============================================================================
// JSON export / import (backup / restore)
// =============================================================================
async function downloadExport() {
  const res = await api.get("/export");
  if (!(await ensureOk(res))) return;
  const data = await res.json();
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  const timestamp = new Date().toISOString().slice(0, 10);
  link.download = `canban-backup-${timestamp}.json`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

function triggerImportPicker() {
  dom.importFileInput.value = "";
  dom.importFileInput.click();
}

async function importBackupFile(file) {
  let data;
  try {
    data = JSON.parse(await file.text());
  } catch (err) {
    showError("That file isn't valid JSON.");
    return;
  }

  const res = await api.post("/import", data);
  if (!(await ensureOk(res))) return;

  await refreshSprintBanner();
  await refreshLastSprintPanel();
  await refreshNextSprintPanel();
  await loadBoard();
}

// =============================================================================
// Sprints
// =============================================================================
async function fetchActiveSprint() {
  const res = await api.get("/sprints/active");
  if (!res.ok) return null;
  return res.json();
}

function renderSprintBanner(sprint) {
  sprintState.setActive(sprint);

  if (!sprint) {
    addClass(dom.sprintBannerActive, "hidden");
    removeClass(dom.sprintBannerInactive, "hidden");
    return;
  }

  addClass(dom.sprintBannerInactive, "hidden");
  removeClass(dom.sprintBannerActive, "hidden");

  dom.sprintBannerName.textContent = sprint.name;
  dom.sprintBannerDates.textContent = `${formatSprintDate(sprint.start_date)} – ${formatSprintDate(sprint.end_date)}`;

  const { label, overdue } = formatDaysRemaining(sprint.end_date);
  dom.sprintBannerDays.textContent = label;
  toggleClass(dom.sprintBannerDays, "overdue", overdue);
}

async function refreshSprintBanner() {
  const sprint = await fetchActiveSprint();
  renderSprintBanner(sprint);
}

async function startSprint(name, durationWeeks) {
  const res = await api.post("/sprints/start", { name, duration_weeks: durationWeeks });
  if (!(await ensureOk(res))) return false;
  await refreshSprintBanner();
  await refreshNextSprintPanel();
  await loadBoard();
  return true;
}

async function endSprint(nextName, nextDurationWeeks) {
  const res = await api.post("/sprints/end", { name: nextName, duration_weeks: nextDurationWeeks });
  if (!(await ensureOk(res))) return false;
  await refreshSprintBanner();
  await refreshLastSprintPanel();
  await refreshNextSprintPanel();
  await loadBoard();
  return true;
}

function openSprintModal(mode) {
  sprintModalMode = mode;
  const ending = mode === "end";
  dom.sprintModalTitle.textContent = ending ? "End Sprint & Start Next" : "Start Sprint";
  dom.sprintModalSubmitBtn.textContent = ending ? "End & Start Next" : "Start Sprint";
  toggleClass(dom.sprintModalHint, "hidden", !ending);
  dom.sprintNameInput.value = "";
  dom.sprintDurationSelect.value = DEFAULT_SPRINT_DURATION;
  openOverlay(dom.sprintModalOverlay);
  dom.sprintNameInput.focus();
}

function closeSprintModal() {
  closeOverlay(dom.sprintModalOverlay);
}

async function fetchPastSprints() {
  const res = await api.get("/sprints");
  if (!res.ok) return [];
  return res.json();
}

function createPastSprintItemElement(sprint, { showHeader = true } = {}) {
  const el = document.createElement("div");
  el.className = "trash-item";

  if (showHeader) {
    const header = document.createElement("div");
    header.className = "trash-item-header";

    const title = document.createElement("span");
    title.className = "trash-item-title";
    title.textContent = sprint.name;
    header.appendChild(title);

    const dates = document.createElement("span");
    dates.className = "trash-item-id";
    dates.textContent = `${formatSprintDate(sprint.start_date)} – ${formatSprintDate(sprint.end_date)}`;
    header.appendChild(dates);

    el.appendChild(header);
  }

  const tasksWrap = document.createElement("div");
  tasksWrap.className = "past-sprint-tasks";
  if (sprint.completed_tasks.length) {
    for (const task of sprint.completed_tasks) {
      const chip = document.createElement("span");
      chip.className = "card-tag completed";
      chip.textContent = `${task.id} ${task.title}`;
      tasksWrap.appendChild(chip);
    }
  } else {
    const empty = document.createElement("span");
    empty.className = "past-sprint-tasks-empty";
    empty.textContent = "No tasks completed.";
    tasksWrap.appendChild(empty);
  }
  el.appendChild(tasksWrap);

  return el;
}

async function renderPastSprints() {
  const pastSprints = await fetchPastSprints();
  // The most-recently-closed sprint already has its own dedicated "Last Sprint" panel on
  // the board -- this modal is for everything older than that, so skip it here.
  const olderSprints = pastSprints.slice(1);
  dom.pastSprintsList.replaceChildren();
  for (const sprint of olderSprints) {
    dom.pastSprintsList.appendChild(createPastSprintItemElement(sprint));
  }
  toggleClass(dom.pastSprintsEmptyMessage, "hidden", olderSprints.length > 0);
}

function openPastSprintsModal() {
  openOverlay(dom.pastSprintsModalOverlay);
  renderPastSprints();
}

function closePastSprintsModal() {
  closeOverlay(dom.pastSprintsModalOverlay);
}

function renderLastSprintPanel(sprint) {
  dom.lastSprintBody.replaceChildren();

  if (!sprint) {
    const empty = document.createElement("p");
    empty.className = "sprint-panel-empty-message";
    empty.textContent = "No closed sprints yet.";
    dom.lastSprintBody.appendChild(empty);
    dom.lastSprintSummaryInfo.textContent = "No closed sprints yet";
    return;
  }

  dom.lastSprintBody.appendChild(createPastSprintItemElement(sprint, { showHeader: false }));

  dom.lastSprintSummaryInfo.replaceChildren();
  const name = document.createElement("span");
  name.className = "sprint-panel-summary-name";
  name.textContent = sprint.name;
  const dates = document.createElement("span");
  dates.className = "sprint-panel-summary-dates";
  dates.textContent = `${formatSprintDate(sprint.start_date)} – ${formatSprintDate(sprint.end_date)}`;
  dom.lastSprintSummaryInfo.append(name, dates);
}

async function refreshLastSprintPanel() {
  // Last sprint is a size-1 read of the past-sprints list, which the API already sorts
  // most-recently-closed first.
  const pastSprints = await fetchPastSprints();
  renderLastSprintPanel(pastSprints[0] || null);
}

async function fetchPlannedSprint() {
  const res = await api.get("/sprints/planned");
  if (!res.ok) return null;
  return res.json();
}

function renderNextSprintPanel(sprint) {
  sprintState.setPlanned(sprint);

  if (sprint) {
    removeClass(dom.nextSprintPlanned, "hidden");
    addClass(dom.nextSprintEmptyMessage, "hidden");
    addClass(dom.planSprintForm, "hidden");
    dom.nextSprintName.textContent = sprint.name;
    dom.nextSprintDuration.textContent =
      sprint.duration_weeks === 1 ? "1 week" : `${sprint.duration_weeks} weeks`;
    // A planned sprint has no real start_date yet (see storage.plan_next_sprint) -- it's only
    // computed at promotion time, from whatever day End Sprint actually gets clicked. This is
    // just a preview based on the current sprint's end_date, not a stored commitment: if the
    // current sprint ends earlier or later than its own end_date, the real promoted start_date
    // will differ from this estimate accordingly.
    dom.nextSprintAnticipated.textContent =
      sprintState.active && sprintState.active.end_date
        ? `Starts ~${formatSprintDate(sprintState.active.end_date)} (estimated)`
        : "";
    dom.nextSprintSummaryInfo.textContent = sprint.name;
    return;
  }

  addClass(dom.nextSprintPlanned, "hidden");
  removeClass(dom.nextSprintEmptyMessage, "hidden");
  dom.nextSprintSummaryInfo.textContent = "Nothing planned yet";
  // The plan control only makes sense while a sprint is active -- there's no "next" to queue
  // up otherwise.
  toggleClass(dom.planSprintForm, "hidden", sprintState.activeId === null);
}

async function refreshNextSprintPanel() {
  const sprint = await fetchPlannedSprint();
  renderNextSprintPanel(sprint);
}

async function planNextSprint(name, durationWeeks) {
  const res = await api.post("/sprints/plan", { name, duration_weeks: durationWeeks });
  if (!(await ensureOk(res))) return false;
  await refreshNextSprintPanel();
  return true;
}

// =============================================================================
// Filters
// =============================================================================
function applyFilters() {
  const query = dom.filterSearchInput.value.trim().toLowerCase();
  const priority = dom.filterPrioritySelect.value;
  const blockedOnly = dom.filterBlockedOnlyInput.checked;
  const active = Boolean(query || priority || blockedOnly);

  for (const column of COLUMNS) {
    const list = document.querySelector(`.task-list[data-column="${column}"]`);
    const countEl = document.getElementById(`count-${column}`);
    const cards = list.querySelectorAll(".card");
    let visibleCount = 0;

    cards.forEach((card) => {
      const matchesQuery = !query || card.dataset.searchText.includes(query);
      const matchesPriority = !priority || card.dataset.priority === priority;
      const matchesBlocked = !blockedOnly || card.dataset.blocked === "true";
      const matches = matchesQuery && matchesPriority && matchesBlocked;
      toggleClass(card, "filtered-out", !matches);
      if (matches) visibleCount += 1;
    });

    countEl.textContent = active ? `${visibleCount}/${cards.length}` : `${cards.length}`;
  }

  toggleClass(dom.filterClearBtn, "hidden", !active);
}

function clearFilters() {
  dom.filterSearchInput.value = "";
  dom.filterPrioritySelect.value = "";
  dom.filterBlockedOnlyInput.checked = false;
  applyFilters();
}

// =============================================================================
// Modal open/close (task-create, task-detail, trash, archive, confirm)
// =============================================================================
function openTrashModal() {
  openOverlay(dom.trashModalOverlay);
  renderTrash();
}

function closeTrashModal() {
  closeOverlay(dom.trashModalOverlay);
}

function openArchiveModal() {
  openOverlay(dom.archiveModalOverlay);
  renderArchive();
}

function closeArchiveModal() {
  closeOverlay(dom.archiveModalOverlay);
}

function confirmAction(message, onConfirm) {
  dom.confirmMessage.textContent = message;
  pendingConfirmAction = onConfirm;
  openOverlay(dom.confirmModalOverlay);
}

function closeConfirmModal() {
  closeOverlay(dom.confirmModalOverlay);
  pendingConfirmAction = null;
}

function updateBlockedByVisibility() {
  const canBlock = dom.columnSelect.value !== DONE_COLUMN;
  toggleClass(dom.blockedByField, "hidden", !canBlock);
}

function openModal(column) {
  dom.columnSelect.value = column;
  dom.titleInput.value = "";
  dom.descriptionInput.value = "";
  dom.priorityInput.value = DEFAULT_PRIORITY;
  dom.blockedByInput.value = "";
  dom.dueDateInput.value = "";
  updateBlockedByVisibility();
  openOverlay(dom.modalOverlay);
  dom.titleInput.focus();
}

function closeModal() {
  closeOverlay(dom.modalOverlay);
}

function openTaskDetail(column, task) {
  currentDetailTask = { id: task.id, column };

  dom.detailId.textContent = task.id;
  dom.detailTitle.textContent = task.title;
  dom.detailDescription.textContent = task.description || "No description.";

  dom.detailTags.replaceChildren();
  if (task.blocks && task.blocks.length) {
    const tag = document.createElement("span");
    tag.className = "card-tag blocks";
    tag.textContent = `Blocks ${task.blocks.join(", ")}`;
    dom.detailTags.appendChild(tag);
  }

  const canBlock = column !== DONE_COLUMN;
  toggleClass(dom.detailBlockedByField, "hidden", !canBlock);
  toggleClass(dom.detailSaveBtn, "hidden", !canBlock);
  dom.detailBlockedByInput.value = task.blocked_by || "";
  dom.detailDueDateInput.value = task.due_date ? task.due_date.slice(0, 10) : "";

  dom.detailSubtaskInput.value = "";
  renderDetailSubtasks(task.id);

  dom.detailNoteInput.value = "";
  renderDetailNotes(task.id);

  openOverlay(dom.taskDetailModalOverlay);
}

function closeTaskDetail() {
  closeOverlay(dom.taskDetailModalOverlay);
  currentDetailTask = null;
}

// =============================================================================
// Event wiring
// =============================================================================
document.querySelectorAll(".add-task-btn").forEach((btn) => {
  btn.addEventListener("click", () => openModal(btn.dataset.column));
});

document.querySelectorAll(".wip-limit-input").forEach((input) => {
  input.addEventListener("change", () => commitWipLimitInput(input));
  input.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      input.blur();
    } else if (event.key === "Escape") {
      event.preventDefault();
      const limit = getWipLimit(input.dataset.column);
      input.value = limit === null ? "" : String(limit);
      input.blur();
    }
  });
});

wireOverlayDismiss(dom.modalOverlay, closeModal, dom.modalCancelBtn);
dom.columnSelect.addEventListener("change", updateBlockedByVisibility);

wireOverlayDismiss(dom.taskDetailModalOverlay, closeTaskDetail, dom.taskDetailCloseBtn);

dom.themeToggle.addEventListener("click", () => {
  const root = document.documentElement;
  const next = root.dataset.theme === "dark" ? "light" : "dark";
  root.dataset.theme = next;
  localStorage.setItem(THEME_STORAGE_KEY, next);
});

dom.exportFab.addEventListener("click", downloadExport);

dom.importFab.addEventListener("click", triggerImportPicker);
dom.importFileInput.addEventListener("change", () => {
  const file = dom.importFileInput.files[0];
  if (!file) return;
  confirmAction(`Import "${file.name}"? This adds its tasks/sprints to the current board.`, () =>
    importBackupFile(file)
  );
});

wireOverlayDismiss(dom.trashModalOverlay, closeTrashModal, dom.trashModalClose);
dom.trashFab.addEventListener("click", openTrashModal);

dom.emptyTrashBtn.addEventListener("click", () => {
  confirmAction("Permanently delete every task in the recycle bin? This can't be undone.", emptyTrash);
});

dom.archiveAllBtn.addEventListener("click", archiveAllDone);

wireOverlayDismiss(dom.archiveModalOverlay, closeArchiveModal, dom.archiveModalClose);
dom.archiveFab.addEventListener("click", openArchiveModal);

wireOverlayDismiss(dom.confirmModalOverlay, closeConfirmModal, dom.confirmCancelBtn);

dom.confirmConfirmBtn.addEventListener("click", async () => {
  const action = pendingConfirmAction;
  closeConfirmModal();
  if (action) await action();
});

dom.startSprintBtn.addEventListener("click", () => openSprintModal("start"));
dom.endSprintBtn.addEventListener("click", async () => {
  // If a sprint has already been explicitly planned via the "Plan Next Sprint" control, end
  // it straight away -- the name/duration prompt is only the fallback for when nothing is
  // queued up yet.
  if (sprintState.planned) {
    await endSprint(null, null);
    return;
  }
  openSprintModal("end");
});
wireOverlayDismiss(dom.sprintModalOverlay, closeSprintModal, dom.sprintModalCancelBtn);

wireOverlayDismiss(dom.pastSprintsModalOverlay, closePastSprintsModal, dom.pastSprintsModalClose);
dom.pastSprintsFab.addEventListener("click", openPastSprintsModal);

dom.sprintForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const name = dom.sprintNameInput.value.trim();
  if (!name) return;
  const durationWeeks = parseInt(dom.sprintDurationSelect.value, 10);
  const ok =
    sprintModalMode === "end"
      ? await endSprint(name, durationWeeks)
      : await startSprint(name, durationWeeks);
  if (ok) closeSprintModal();
});

dom.planSprintForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const name = dom.planSprintNameInput.value.trim();
  if (!name) return;
  const durationWeeks = parseInt(dom.planSprintDurationSelect.value, 10);
  const ok = await planNextSprint(name, durationWeeks);
  if (ok) {
    dom.planSprintForm.reset();
    dom.planSprintDurationSelect.value = DEFAULT_SPRINT_DURATION;
  }
});

document.addEventListener("keydown", (event) => {
  if (event.key !== "Escape") return;
  if (isOverlayOpen(dom.confirmModalOverlay)) closeConfirmModal();
  else if (isOverlayOpen(dom.taskDetailModalOverlay)) closeTaskDetail();
  else if (isOverlayOpen(dom.trashModalOverlay)) closeTrashModal();
  else if (isOverlayOpen(dom.archiveModalOverlay)) closeArchiveModal();
  else if (isOverlayOpen(dom.sprintModalOverlay)) closeSprintModal();
  else if (isOverlayOpen(dom.pastSprintsModalOverlay)) closePastSprintsModal();
  else if (isOverlayOpen(dom.modalOverlay)) closeModal();
});

dom.taskForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const title = dom.titleInput.value.trim();
  if (!title) return;
  const ok = await createTask(
    dom.columnSelect.value,
    title,
    dom.descriptionInput.value.trim(),
    dom.blockedByInput.value.trim(),
    dom.priorityInput.value,
    dom.dueDateInput.value
  );
  if (ok) closeModal();
});

async function submitDetailSubtask() {
  if (!currentDetailTask) return;
  const title = dom.detailSubtaskInput.value.trim();
  if (!title) return;
  const ok = await addSubtask(currentDetailTask.id, title);
  if (ok) dom.detailSubtaskInput.value = "";
}

dom.detailSubtaskAddBtn.addEventListener("click", submitDetailSubtask);
dom.detailSubtaskInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter") {
    event.preventDefault();
    submitDetailSubtask();
  }
});

async function submitDetailNote() {
  if (!currentDetailTask) return;
  const body = dom.detailNoteInput.value.trim();
  if (!body) return;
  const ok = await addNote(currentDetailTask.id, body);
  if (ok) dom.detailNoteInput.value = "";
}

dom.detailNoteAddBtn.addEventListener("click", submitDetailNote);

dom.taskDetailForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!currentDetailTask) return;
  const blockedBy = dom.detailBlockedByInput.value.trim();
  const blockedByOk = await setBlockedBy(currentDetailTask.id, blockedBy || null);
  if (!blockedByOk) return;
  const dueDateOk = await setDueDate(currentDetailTask.id, dom.detailDueDateInput.value || null);
  if (dueDateOk) closeTaskDetail();
});

dom.filterSearchInput.addEventListener("input", applyFilters);
dom.filterPrioritySelect.addEventListener("change", applyFilters);
dom.filterBlockedOnlyInput.addEventListener("change", applyFilters);
dom.filterClearBtn.addEventListener("click", clearFilters);

document.querySelectorAll(".task-list").forEach((list) => {
  list.addEventListener("dragover", (event) => {
    event.preventDefault();
    addClass(list, "drag-over");
  });
  list.addEventListener("dragleave", () => {
    removeClass(list, "drag-over");
  });
  list.addEventListener("drop", (event) => {
    event.preventDefault();
    removeClass(list, "drag-over");
    const dragging = document.querySelector(".card.dragging");
    if (!dragging) return;

    const taskId = dragging.dataset.id;
    const sourceColumn = dragging.dataset.column;
    const targetColumn = list.dataset.column;
    if (targetColumn === sourceColumn) return;

    moveTask(taskId, targetColumn);
  });
});

// =============================================================================
// Initial load
// =============================================================================
refreshSprintBanner().then(() => {
  refreshNextSprintPanel();
  loadBoard();
});
refreshLastSprintPanel();
refreshTrashBadge();
if (ARCHIVE_ENABLED) refreshArchiveBadge();
