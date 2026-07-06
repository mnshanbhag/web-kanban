const API_BASE = "/api";
const COLUMNS = ["To Do", "In Progress", "Blocked", "Done"];
const BLOCKED_COLUMN = "Blocked";

const DEFAULT_PRIORITY = "Medium";
const PRIORITIES = ["Low", "Medium", "High", "Urgent"];

const modalOverlay = document.getElementById("modal-overlay");
const taskForm = document.getElementById("task-form");
const titleInput = document.getElementById("task-title");
const descriptionInput = document.getElementById("task-description");
const columnSelect = document.getElementById("task-column");
const priorityInput = document.getElementById("task-priority");
const blockedByField = document.getElementById("task-blocked-by-field");
const blockedByInput = document.getElementById("task-blocked-by");

const blockModalOverlay = document.getElementById("block-modal-overlay");
const blockForm = document.getElementById("block-form");
const blockBlockerIdInput = document.getElementById("block-blocker-id");

const errorToast = document.getElementById("error-toast");

const trashFab = document.getElementById("trash-fab");
const trashBadge = document.getElementById("trash-badge");
const trashModalOverlay = document.getElementById("trash-modal-overlay");
const trashList = document.getElementById("trash-list");
const trashEmptyMessage = document.getElementById("trash-empty-message");
const emptyTrashBtn = document.getElementById("empty-trash-btn");
const trashModalClose = document.getElementById("trash-modal-close");

const confirmModalOverlay = document.getElementById("confirm-modal-overlay");
const confirmMessage = document.getElementById("confirm-message");
const confirmCancelBtn = document.getElementById("confirm-cancel");
const confirmConfirmBtn = document.getElementById("confirm-confirm");

let pendingMove = null;
let toastTimer = null;
let pendingConfirmAction = null;

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
  }
}

function createCardElement(column, task) {
  const card = document.createElement("div");
  card.className = "card";
  card.draggable = true;
  card.dataset.id = task.id;
  card.dataset.column = column;
  card.dataset.priority = task.priority || DEFAULT_PRIORITY;

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

  if (task.blocked_by || (task.blocks && task.blocks.length)) {
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

    card.appendChild(tags);
  }

  const deleteBtn = document.createElement("button");
  deleteBtn.className = "card-delete";
  deleteBtn.textContent = "×";
  deleteBtn.title = "Delete task";
  deleteBtn.addEventListener("click", () => deleteTask(task.id));
  card.appendChild(deleteBtn);

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

async function createTask(column, title, description, blockedBy, priority) {
  const res = await fetch(`${API_BASE}/tasks`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      column,
      title,
      description,
      blocked_by: blockedBy || null,
      priority: priority || DEFAULT_PRIORITY,
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

async function moveTask(taskId, toColumn, blockedBy) {
  const res = await fetch(`${API_BASE}/tasks/${encodeURIComponent(taskId)}/move`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ to_column: toColumn, blocked_by: blockedBy || null }),
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

function openTrashModal() {
  trashModalOverlay.classList.add("open");
  renderTrash();
}

function closeTrashModal() {
  trashModalOverlay.classList.remove("open");
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
  const isBlocked = columnSelect.value === BLOCKED_COLUMN;
  blockedByField.classList.toggle("hidden", !isBlocked);
  blockedByInput.required = isBlocked;
}

function openModal(column) {
  columnSelect.value = column;
  titleInput.value = "";
  descriptionInput.value = "";
  priorityInput.value = DEFAULT_PRIORITY;
  blockedByInput.value = "";
  updateBlockedByVisibility();
  modalOverlay.classList.add("open");
  titleInput.focus();
}

function closeModal() {
  modalOverlay.classList.remove("open");
}

function openBlockModal(taskId, toColumn) {
  pendingMove = { taskId, toColumn };
  blockBlockerIdInput.value = "";
  blockModalOverlay.classList.add("open");
  blockBlockerIdInput.focus();
}

function closeBlockModal() {
  blockModalOverlay.classList.remove("open");
  pendingMove = null;
}

document.querySelectorAll(".add-task-btn").forEach((btn) => {
  btn.addEventListener("click", () => openModal(btn.dataset.column));
});

document.getElementById("modal-cancel").addEventListener("click", closeModal);
columnSelect.addEventListener("change", updateBlockedByVisibility);

modalOverlay.addEventListener("click", (event) => {
  if (event.target === modalOverlay) closeModal();
});

document.getElementById("block-modal-cancel").addEventListener("click", closeBlockModal);

blockModalOverlay.addEventListener("click", (event) => {
  if (event.target === blockModalOverlay) closeBlockModal();
});

trashFab.addEventListener("click", openTrashModal);
trashModalClose.addEventListener("click", closeTrashModal);

trashModalOverlay.addEventListener("click", (event) => {
  if (event.target === trashModalOverlay) closeTrashModal();
});

emptyTrashBtn.addEventListener("click", () => {
  confirmAction("Permanently delete every task in the recycle bin? This can't be undone.", emptyTrash);
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
  else if (blockModalOverlay.classList.contains("open")) closeBlockModal();
  else if (trashModalOverlay.classList.contains("open")) closeTrashModal();
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
    priorityInput.value
  );
  if (ok) closeModal();
});

blockForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!pendingMove) return;
  const blockerId = blockBlockerIdInput.value.trim();
  const { taskId, toColumn } = pendingMove;
  const ok = await moveTask(taskId, toColumn, blockerId);
  if (ok) closeBlockModal();
});

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

    if (targetColumn === BLOCKED_COLUMN) {
      openBlockModal(taskId, targetColumn);
    } else {
      moveTask(taskId, targetColumn, null);
    }
  });
});

loadBoard();
refreshTrashBadge();
