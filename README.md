# CanBan

A local Kanban board. FastAPI backend, vanilla JS/HTML/CSS frontend, tasks stored as plain
Markdown files on disk — no database.

## Setup

Requires Python 3.13+.

```
python -m pip install -r requirements.txt
```

For running tests, install dev dependencies instead (this also installs `requirements.txt`):

```
python -m pip install -r requirements-dev.txt
```

## Running the app

```
python -m uvicorn backend.main:app --reload
```

Open http://127.0.0.1:8000 — the backend serves both the API and the static frontend.

## Running tests

```
python -m pytest
```

## How data is stored

Board state lives under `.kanban_data/`, not a database:

```
.kanban_data/
  To Do/
    Write tests.md       <- filename = task title, frontmatter + body = metadata + description
  In Progress/
  Blocked/
  Done/
```

Each column is a folder; each task is a `.md` file. Columns and tasks are created on demand —
an empty `.kanban_data/` is a valid, empty board. There are 4 columns: To Do, In Progress,
Blocked, Done.

Each task file has a small frontmatter block for metadata, followed by the description as plain
text:

```
---
id: KAN-05
blocked_by: KAN-02
priority: High
---
Task description goes here.
```

- `id` — a unique, auto-assigned identifier (`KAN-01`, `KAN-02`, ...). Assigned once at creation
  and never changes, even when the task moves between columns. IDs are **never reused**, even
  across a permanent delete or an emptied trash — see "Recycle bin" below.
- `blocked_by` — set only while the task sits in the **Blocked** column; it names the task ID
  that must complete first. Cleared automatically if the task moves out of Blocked.
- `priority` — one of `Low` / `Medium` / `High` / `Urgent`, defaulting to `Medium` if omitted at
  creation. Carried through unchanged across moves, blocking, and the recycle bin.
- The reverse link ("which tasks does this one block") is **not stored** — it's computed on
  every read by scanning for tasks whose `blocked_by` points at this task's ID. That keeps the
  two directions from ever going out of sync.

### Recycle bin

Deleting a task doesn't remove it — it's a soft delete. The task's file moves to
`.kanban_data/.trash/<id>.md`, gaining `title` and `deleted_from` frontmatter fields (so it can
be restored to the column it came from) plus a `deleted_at` timestamp. `.trash/` is excluded from
the normal board view.

Task IDs are tracked by a persistent counter file (`.kanban_data/.id_counter`) rather than by
scanning for the current max ID on disk — scanning would let a deleted task's ID get handed to a
new task once the old file was gone.

## API

| Method | Path                            | Body                                          | Description                            |
|--------|----------------------------------|------------------------------------------------|-------------------------------------------|
| GET    | `/api/status`                   | —                                                | Health check                            |
| GET    | `/api/tasks`                     | —                                                | All columns and their tasks             |
| POST   | `/api/tasks`                      | `{column, title, description?, blocked_by?, priority?}` | Create a task                  |
| PUT    | `/api/tasks/{task_id}/move`       | `{to_column, blocked_by?}`                      | Move a task to another column           |
| PUT    | `/api/tasks/{task_id}/priority`   | `{priority}`                                    | Change a task's priority                |
| DELETE | `/api/tasks/{task_id}`            | —                                                | Delete a task (soft — goes to trash)    |
| GET    | `/api/trash`                      | —                                                | List trashed tasks                      |
| POST   | `/api/trash/{task_id}/restore`    | —                                                | Restore a task to its original column   |
| DELETE | `/api/trash/{task_id}`            | —                                                | Permanently delete one trashed task     |
| DELETE | `/api/trash`                      | —                                                | Permanently delete everything in trash  |

`task_id` is the task's own unique ID (e.g. `"KAN-05"`) — stable across moves, returned by
`GET`/`POST` and passed back as-is to `move`/`priority`/`delete`/`restore`.

`blocked_by` is **required** when `column`/`to_column` is `"Blocked"` and must reference an
existing task ID (not itself); the API returns `400` otherwise. Each task in the response also
carries a computed `"blocks"` array — the IDs of tasks currently blocked by it.

`priority` must be one of `Low`, `Medium`, `High`, `Urgent` — the API returns `400` otherwise.
