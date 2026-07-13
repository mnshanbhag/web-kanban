const API_BASE = "/api";
const COLUMNS = ["To Do", "In Progress", "In Review", "Done"];
const DONE_COLUMN = "Done";

const DEFAULT_PRIORITY = "Medium";
const PRIORITIES = ["Low", "Medium", "High", "Urgent"];

const WIP_LIMITS_STORAGE_KEY = "canban-wip-limits";

const modalOverlay = document.getElementById("modal-overlay");
const taskForm = document.getElementById("task-form");
const titleInput = document.getElementById("task-title");
const descriptionInput = document.getElementById("task-description");
const columnSelect = document.getElementById("task-column");
const priorityInput = document.getElementById("task-priority");
const blockedByField = document.getElementById("task-blocked-by-field");
const blockedByInput = document.getElementById("task-blocked-by");
const dueDateInput = document.getElementById("task-due-date");

const taskDetailModalOverlay = document.getElementById("task-detail-modal-overlay");
const taskDetailForm = document.getElementById("task-detail-form");
const detailId = document.getElementById("detail-id");
const detailTitle = document.getElementById("detail-title");
const detailDescription = document.getElementById("detail-description");
const detailTags = document.getElementById("detail-tags");
const detailBlockedByField = document.getElementById("detail-blocked-by-field");
const detailBlockedByInput = document.getElementById("detail-blocked-by");
const detailDueDateInput = document.getElementById("detail-due-date");
const detailSaveBtn = document.getElementById("detail-save-btn");
const taskDetailCloseBtn = document.getElementById("task-detail-close");

const errorToast = document.getElementById("error-toast");

const themeToggle = document.getElementById("theme-toggle");

const exportFab = document.getElementById("export-fab");

const trashFab = document.getElementById("trash-fab");
const trashBadge = document.getElementById("trash-badge");
const trashModalOverlay = document.getElementById("trash-modal-overlay");
const trashList = document.getElementById("trash-list");
const trashEmptyMessage = document.getElementById("trash-empty-message");
const emptyTrashBtn = document.getElementById("empty-trash-btn");
const trashModalClose = document.getElementById("trash-modal-close");

const archiveFab = document.getElementById("archive-fab");
const archiveBadge = document.getElementById("archive-badge");
const archiveModalOverlay = document.getElementById("archive-modal-overlay");
const archiveList = document.getElementById("archive-list");
const archiveEmptyMessage = document.getElementById("archive-empty-message");
const archiveModalClose = document.getElementById("archive-modal-close");
const archiveAllBtn = document.getElementById("archive-all-btn");

const confirmModalOverlay = document.getElementById("confirm-modal-overlay");
const confirmMessage = document.getElementById("confirm-message");
const confirmCancelBtn = document.getElementById("confirm-cancel");
const confirmConfirmBtn = document.getElementById("confirm-confirm");

const filterSearchInput = document.getElementById("filter-search");
const filterPrioritySelect = document.getElementById("filter-priority");
const filterBlockedOnlyInput = document.getElementById("filter-blocked-only");
const filterClearBtn = document.getElementById("filter-clear");

let toastTimer = null;
let pendingConfirmAction = null;
let currentDetailTask = null;

function showError(message) {
  errorToast.textContent = message;
  errorToast.classList.add("visible");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => errorToast.classList.remove("visible"), 4000);
}

async function loadBoard() {
  const res = await fetch(`${API_BASE}/tasks`);
  const board = await res.json();
  renderBoard(board);
}

function renderBoard(board) {
  for (const column of COLUMNS) {
    const list = document.querySelector(`.task-list[data-column="${column}"]`);
    const countEl = document.getElementById(`count-${column}`);
    const tasks = board[column] || [];

    list.replaceChildren();
    for (const task of tasks) {
      list.appendChild(createCardElement(column, task));
    }
    countEl.textContent = tasks.length;
    syncWipLimitInput(column);
    updateWipLimitIndicator(column, tasks.length);
    if (column === DONE_COLUMN) archiveAllBtn.disabled = tasks.length === 0;
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
  countEl.classList.toggle("over-limit", overLimit);
  countEl.title = overLimit ? `${count} of ${limit} WIP limit exceeded` : "";
  if (input) input.classList.toggle("over-limit", overLimit);
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
  card.appendChild(prioritySelect);

  if (task.blocked_by || (task.blocks && task.blocks.length) || task.due_date) {
    const tags = document.createElement("div");
    tags.className = "card-tags";

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

    card.appendChild(tags);
  }

  if (column === DONE_COLUMN) {
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

  const deleteBtn = document.createElement("button");
  deleteBtn.className = "card-delete";
  deleteBtn.textContent = "×";
  deleteBtn.title = "Delete task";
  deleteBtn.addEventListener("click", (event) => {
    event.stopPropagation();
    deleteTask(task.id);
  });
  card.appendChild(deleteBtn);

  card.addEventListener("click", () => openTaskDetail(column, task));

  card.addEventListener("dragstart", () => {
    card.classList.add("dragging");
  });
  card.addEventListener("dragend", () => {
    card.classList.remove("dragging");
  });

  return card;
}

async function handleApiError(res) {
  const body = await res.json().catch(() => ({}));
  showError(body.detail || "Something went wrong.");
}

async function createTask(column, title, description, blockedBy, priority, dueDate) {
  const res = await fetch(`${API_BASE}/tasks`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      column,
      title,
      description,
      blocked_by: blockedBy || null,
      priority: priority || DEFAULT_PRIORITY,
      due_date: dueDate || null,
    }),
  });
  if (!res.ok) {
    await handleApiError(res);
    return false;
  }
  await loadBoard();
  return true;
}

async function setPriority(taskId, priority) {
  await fetch(`${API_BASE}/tasks/${encodeURIComponent(taskId)}/priority`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ priority }),
  });
  await loadBoard();
}

async function moveTask(taskId, toColumn) {
  const res = await fetch(`${API_BASE}/tasks/${encodeURIComponent(taskId)}/move`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ to_column: toColumn }),
  });
  if (!res.ok) {
    await handleApiError(res);
    return false;
  }
  await loadBoard();
  return true;
}

async function setBlockedBy(taskId, blockedBy) {
  const res = await fetch(`${API_BASE}/tasks/${encodeURIComponent(taskId)}/blocked-by`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ blocked_by: blockedBy || null }),
  });
  if (!res.ok) {
    await handleApiError(res);
    return false;
  }
  await loadBoard();
  return true;
}

async function setDueDate(taskId, dueDate) {
  const res = await fetch(`${API_BASE}/tasks/${encodeURIComponent(taskId)}/due-date`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ due_date: dueDate || null }),
  });
  if (!res.ok) {
    await handleApiError(res);
    return false;
  }
  await loadBoard();
  return true;
}

async function deleteTask(taskId) {
  await fetch(`${API_BASE}/tasks/${encodeURIComponent(taskId)}`, { method: "DELETE" });
  await loadBoard();
  await refreshTrashBadge();
}

async function archiveTask(taskId) {
  const res = await fetch(`${API_BASE}/tasks/${encodeURIComponent(taskId)}/archive`, {
    method: "POST",
  });
  if (!res.ok) {
    await handleApiError(res);
    return;
  }
  await loadBoard();
  await refreshArchiveBadge();
}

async function archiveAllDone() {
  const res = await fetch(`${API_BASE}/tasks/archive-done`, { method: "POST" });
  if (!res.ok) {
    await handleApiError(res);
    return;
  }
  await loadBoard();
  await refreshArchiveBadge();
}

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

async function fetchTrash() {
  const res = await fetch(`${API_BASE}/trash`);
  return res.json();
}

async function refreshTrashBadge() {
  const trashed = await fetchTrash();
  trashBadge.textContent = trashed.length;
  trashBadge.classList.toggle("hidden", trashed.length === 0);
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
  trashList.replaceChildren();
  for (const item of trashed) {
    trashList.appendChild(createTrashItemElement(item));
  }
  trashEmptyMessage.classList.toggle("hidden", trashed.length > 0);
  trashBadge.textContent = trashed.length;
  trashBadge.classList.toggle("hidden", trashed.length === 0);
}

async function restoreTask(taskId) {
  const res = await fetch(`${API_BASE}/trash/${encodeURIComponent(taskId)}/restore`, {
    method: "POST",
  });
  if (!res.ok) {
    await handleApiError(res);
    return;
  }
  await renderTrash();
  await loadBoard();
}

async function permanentDeleteTask(taskId) {
  await fetch(`${API_BASE}/trash/${encodeURIComponent(taskId)}`, { method: "DELETE" });
  await renderTrash();
}

async function emptyTrash() {
  await fetch(`${API_BASE}/trash`, { method: "DELETE" });
  await renderTrash();
}

async function fetchArchive() {
  const res = await fetch(`${API_BASE}/archive`);
  return res.json();
}

async function refreshArchiveBadge() {
  const archived = await fetchArchive();
  archiveBadge.textContent = archived.length;
  archiveBadge.classList.toggle("hidden", archived.length === 0);
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
  archiveList.replaceChildren();
  for (const item of archived) {
    archiveList.appendChild(createArchiveItemElement(item));
  }
  archiveEmptyMessage.classList.toggle("hidden", archived.length > 0);
  archiveBadge.textContent = archived.length;
  archiveBadge.classList.toggle("hidden", archived.length === 0);
}

async function unarchiveTask(taskId) {
  const res = await fetch(`${API_BASE}/archive/${encodeURIComponent(taskId)}/unarchive`, {
    method: "POST",
  });
  if (!res.ok) {
    await handleApiError(res);
    return;
  }
  await renderArchive();
  await loadBoard();
}

async function downloadExport() {
  const res = await fetch(`${API_BASE}/export`);
  if (!res.ok) {
    await handleApiError(res);
    return;
  }
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

function applyFilters() {
  const query = filterSearchInput.value.trim().toLowerCase();
  const priority = filterPrioritySelect.value;
  const blockedOnly = filterBlockedOnlyInput.checked;
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
      card.classList.toggle("filtered-out", !matches);
      if (matches) visibleCount += 1;
    });

    countEl.textContent = active ? `${visibleCount}/${cards.length}` : `${cards.length}`;
  }

  filterClearBtn.classList.toggle("hidden", !active);
}

function clearFilters() {
  filterSearchInput.value = "";
  filterPrioritySelect.value = "";
  filterBlockedOnlyInput.checked = false;
  applyFilters();
}

function openTrashModal() {
  trashModalOverlay.classList.add("open");
  renderTrash();
}

function closeTrashModal() {
  trashModalOverlay.classList.remove("open");
}

function openArchiveModal() {
  archiveModalOverlay.classList.add("open");
  renderArchive();
}

function closeArchiveModal() {
  archiveModalOverlay.classList.remove("open");
}

function confirmAction(message, onConfirm) {
  confirmMessage.textContent = message;
  pendingConfirmAction = onConfirm;
  confirmModalOverlay.classList.add("open");
}

function closeConfirmModal() {
  confirmModalOverlay.classList.remove("open");
  pendingConfirmAction = null;
}

function updateBlockedByVisibility() {
  const canBlock = columnSelect.value !== DONE_COLUMN;
  blockedByField.classList.toggle("hidden", !canBlock);
}

function openModal(column) {
  columnSelect.value = column;
  titleInput.value = "";
  descriptionInput.value = "";
  priorityInput.value = DEFAULT_PRIORITY;
  blockedByInput.value = "";
  dueDateInput.value = "";
  updateBlockedByVisibility();
  modalOverlay.classList.add("open");
  titleInput.focus();
}

function closeModal() {
  modalOverlay.classList.remove("open");
}

function openTaskDetail(column, task) {
  currentDetailTask = { id: task.id, column };

  detailId.textContent = task.id;
  detailTitle.textContent = task.title;
  detailDescription.textContent = task.description || "No description.";

  detailTags.replaceChildren();
  if (task.blocks && task.blocks.length) {
    const tag = document.createElement("span");
    tag.className = "card-tag blocks";
    tag.textContent = `Blocks ${task.blocks.join(", ")}`;
    detailTags.appendChild(tag);
  }

  const canBlock = column !== DONE_COLUMN;
  detailBlockedByField.classList.toggle("hidden", !canBlock);
  detailSaveBtn.classList.toggle("hidden", !canBlock);
  detailBlockedByInput.value = task.blocked_by || "";
  detailDueDateInput.value = task.due_date ? task.due_date.slice(0, 10) : "";

  taskDetailModalOverlay.classList.add("open");
}

function closeTaskDetail() {
  taskDetailModalOverlay.classList.remove("open");
  currentDetailTask = null;
}

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

document.getElementById("modal-cancel").addEventListener("click", closeModal);
columnSelect.addEventListener("change", updateBlockedByVisibility);

modalOverlay.addEventListener("click", (event) => {
  if (event.target === modalOverlay) closeModal();
});

taskDetailCloseBtn.addEventListener("click", closeTaskDetail);

taskDetailModalOverlay.addEventListener("click", (event) => {
  if (event.target === taskDetailModalOverlay) closeTaskDetail();
});

themeToggle.addEventListener("click", () => {
  const root = document.documentElement;
  const next = root.dataset.theme === "dark" ? "light" : "dark";
  root.dataset.theme = next;
  localStorage.setItem("canban-theme", next);
});

exportFab.addEventListener("click", downloadExport);

trashFab.addEventListener("click", openTrashModal);
trashModalClose.addEventListener("click", closeTrashModal);

trashModalOverlay.addEventListener("click", (event) => {
  if (event.target === trashModalOverlay) closeTrashModal();
});

emptyTrashBtn.addEventListener("click", () => {
  confirmAction("Permanently delete every task in the recycle bin? This can't be undone.", emptyTrash);
});

archiveAllBtn.addEventListener("click", archiveAllDone);

archiveFab.addEventListener("click", openArchiveModal);
archiveModalClose.addEventListener("click", closeArchiveModal);

archiveModalOverlay.addEventListener("click", (event) => {
  if (event.target === archiveModalOverlay) closeArchiveModal();
});

confirmCancelBtn.addEventListener("click", closeConfirmModal);

confirmConfirmBtn.addEventListener("click", async () => {
  const action = pendingConfirmAction;
  closeConfirmModal();
  if (action) await action();
});

confirmModalOverlay.addEventListener("click", (event) => {
  if (event.target === confirmModalOverlay) closeConfirmModal();
});

document.addEventListener("keydown", (event) => {
  if (event.key !== "Escape") return;
  if (confirmModalOverlay.classList.contains("open")) closeConfirmModal();
  else if (taskDetailModalOverlay.classList.contains("open")) closeTaskDetail();
  else if (trashModalOverlay.classList.contains("open")) closeTrashModal();
  else if (archiveModalOverlay.classList.contains("open")) closeArchiveModal();
  else if (modalOverlay.classList.contains("open")) closeModal();
});

taskForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const title = titleInput.value.trim();
  if (!title) return;
  const ok = await createTask(
    columnSelect.value,
    title,
    descriptionInput.value.trim(),
    blockedByInput.value.trim(),
    priorityInput.value,
    dueDateInput.value
  );
  if (ok) closeModal();
});

taskDetailForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!currentDetailTask) return;
  const blockedBy = detailBlockedByInput.value.trim();
  const blockedByOk = await setBlockedBy(currentDetailTask.id, blockedBy || null);
  if (!blockedByOk) return;
  const dueDateOk = await setDueDate(currentDetailTask.id, detailDueDateInput.value || null);
  if (dueDateOk) closeTaskDetail();
});

filterSearchInput.addEventListener("input", applyFilters);
filterPrioritySelect.addEventListener("change", applyFilters);
filterBlockedOnlyInput.addEventListener("change", applyFilters);
filterClearBtn.addEventListener("click", clearFilters);

document.querySelectorAll(".task-list").forEach((list) => {
  list.addEventListener("dragover", (event) => {
    event.preventDefault();
    list.classList.add("drag-over");
  });
  list.addEventListener("dragleave", () => {
    list.classList.remove("drag-over");
  });
  list.addEventListener("drop", (event) => {
    event.preventDefault();
    list.classList.remove("drag-over");
    const dragging = document.querySelector(".card.dragging");
    if (!dragging) return;

    const taskId = dragging.dataset.id;
    const sourceColumn = dragging.dataset.column;
    const targetColumn = list.dataset.column;
    if (targetColumn === sourceColumn) return;

    moveTask(taskId, targetColumn);
  });
});

loadBoard();
refreshTrashBadge();
refreshArchiveBadge();
