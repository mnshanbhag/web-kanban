const API_BASE = "/api";
const COLUMNS = ["To Do", "In Progress", "Blocked", "Done"];
const BLOCKED_COLUMN = "Blocked";

const modalOverlay = document.getElementById("modal-overlay");
const taskForm = document.getElementById("task-form");
const titleInput = document.getElementById("task-title");
const descriptionInput = document.getElementById("task-description");
const columnSelect = document.getElementById("task-column");
const blockedByField = document.getElementById("task-blocked-by-field");
const blockedByInput = document.getElementById("task-blocked-by");

const blockModalOverlay = document.getElementById("block-modal-overlay");
const blockForm = document.getElementById("block-form");
const blockBlockerIdInput = document.getElementById("block-blocker-id");

const errorToast = document.getElementById("error-toast");

let pendingMove = null;
let toastTimer = null;

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

async function createTask(column, title, description, blockedBy) {
  const res = await fetch(`${API_BASE}/tasks`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ column, title, description, blocked_by: blockedBy || null }),
  });
  if (!res.ok) {
    await handleApiError(res);
    return false;
  }
  await loadBoard();
  return true;
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

document.addEventListener("keydown", (event) => {
  if (event.key !== "Escape") return;
  if (blockModalOverlay.classList.contains("open")) closeBlockModal();
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
    blockedByInput.value.trim()
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
