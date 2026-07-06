const API_BASE = "/api";
const COLUMNS = ["To Do", "In Progress", "Done"];

const DEFAULT_PRIORITY = "Medium";
const PRIORITIES = ["Low", "Medium", "High", "Urgent"];

const modalOverlay = document.getElementById("modal-overlay");
const taskForm = document.getElementById("task-form");
const titleInput = document.getElementById("task-title");
const descriptionInput = document.getElementById("task-description");
const columnSelect = document.getElementById("task-column");
const priorityInput = document.getElementById("task-priority");

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

  const deleteBtn = document.createElement("button");
  deleteBtn.className = "card-delete";
  deleteBtn.textContent = "×";
  deleteBtn.title = "Delete task";
  deleteBtn.addEventListener("click", () => deleteTask(task.id));
  card.appendChild(deleteBtn);

  card.addEventListener("dragstart", () => {
    card.classList.add("dragging");
    card.dataset.dragging = "true";
  });
  card.addEventListener("dragend", () => {
    card.classList.remove("dragging");
  });

  return card;
}

async function createTask(column, title, description, priority) {
  await fetch(`${API_BASE}/tasks`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ column, title, description, priority }),
  });
  await loadBoard();
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
  await fetch(`${API_BASE}/tasks/${encodeURIComponent(taskId)}/move`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ to_column: toColumn }),
  });
  await loadBoard();
}

async function deleteTask(taskId) {
  await fetch(`${API_BASE}/tasks/${encodeURIComponent(taskId)}`, { method: "DELETE" });
  await loadBoard();
}

function openModal(column) {
  columnSelect.value = column;
  titleInput.value = "";
  descriptionInput.value = "";
  priorityInput.value = DEFAULT_PRIORITY;
  modalOverlay.classList.add("open");
  titleInput.focus();
}

function closeModal() {
  modalOverlay.classList.remove("open");
}

document.querySelectorAll(".add-task-btn").forEach((btn) => {
  btn.addEventListener("click", () => openModal(btn.dataset.column));
});

document.getElementById("modal-cancel").addEventListener("click", closeModal);

modalOverlay.addEventListener("click", (event) => {
  if (event.target === modalOverlay) closeModal();
});

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && modalOverlay.classList.contains("open")) closeModal();
});

taskForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const title = titleInput.value.trim();
  if (!title) return;
  await createTask(columnSelect.value, title, descriptionInput.value.trim(), priorityInput.value);
  closeModal();
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
    const targetColumn = list.dataset.column;
    if (targetColumn !== dragging.dataset.column) {
      moveTask(taskId, targetColumn);
    }
  });
});

loadBoard();
