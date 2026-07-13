# CanBan

A local Kanban board. FastAPI backend, vanilla JS/HTML/CSS frontend, tasks stored in a local
SQLite database via SQLAlchemy, request/response shapes validated with Pydantic.

See [`FEATURE_IDEAS.md`](FEATURE_IDEAS.md) for the backlog of proposed/in-progress/shipped
features.

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

## Board columns

Four fixed columns: **To Do**, **In Progress**, **In Review**, **Done**. Columns aren't a
database table — a column "exists" only in the sense that some task currently has that value as
its `column`; the frontend renders all four regardless of what the API returns.

## How data is stored

Board state lives in a single SQLite database file, `.kanban_data/kanban.db`, defined via
SQLAlchemy ORM in `backend/storage.py`. There's no migration tooling; the schema is created on
first run via `Base.metadata.create_all()`.

The `tasks` table has: `id` (integer primary key), `title`, `description`, `column`, `priority`,
`blocked_by_id` (a self-referential foreign key), `deleted_at`, `archived_at`, `due_date`, and
`updated_at`. A separate `task_subtasks` table (FK `ondelete="CASCADE"`) holds each task's
subtask checklist items.

- **`id`** is exposed over the API as `"KAN-01"`, `"KAN-02"`, ... (`f"KAN-{id:02d}"`). It's never
  reused: the table uses SQLite's `AUTOINCREMENT` (`sqlite_autoincrement=True`), which guarantees
  the next inserted row's id is always higher than any id the table has ever held, even after a
  row is deleted.
- **`column`** is just a string — see "Board columns" above.
- **`blocked_by_id`** is a foreign key back onto `tasks.id`, with `ON DELETE SET NULL`: if a
  blocker task is ever permanently deleted, every task that pointed at it is automatically
  unblocked at the database level rather than being left with a dangling reference. Blocking is
  independent of `column` — a task in "To Do", "In Progress", or "In Review" can carry a blocker;
  a task in "Done" can never have one (see "Blocking rules" below).
- **`blocks`** (which tasks does this one block) is **not a column** — it's the SQLAlchemy
  `backref` of the `blocked_by` relationship, computed by the ORM on read.
- **`priority`** is one of `Low` / `Medium` / `High` / `Urgent`, defaulting to `Medium`.
- **`due_date`** is optional. Cards past their due date show an "Overdue" badge, suppressed once
  a task reaches Done.
- **`deleted_at`** is `NULL` for an active task. Setting it is the entire "soft delete"
  mechanism — the row never moves or changes shape, so restoring is just clearing it back to
  `NULL`. There's no separate `deleted_from` field like an older file-based version of this app
  had; the trash API exposes the task's own `column` value under that name instead.
- **`archived_at`** is `NULL` unless the task has been manually archived (see "Archive" below).
  Independent of `deleted_at` — a task can be trashed or archived, never both at once.
- **`updated_at`** is set on creation and touched on every content mutation (edits, priority,
  blocking, due date, moving columns) — including on a *dependent* task when finishing another
  task clears its `blocked_by`. Not touched by lifecycle-only operations (delete, restore,
  archive, unarchive). Surfaced on cards as "Updated X ago".

### Recycle bin

Deleting a task sets `deleted_at` instead of removing the row. `GET /api/tasks` and the `blocks`
computation both filter to `deleted_at IS NULL`; `GET /api/trash` filters to `deleted_at IS NOT
NULL`. Restoring just clears the timestamp. Permanently deleting (or emptying the trash) is a
real `DELETE FROM tasks WHERE ...`.

### Archive

A manual "Archive" action, available only on tasks in the Done column, hides a task from the
board without touching the trash/soft-delete path — for clearing out long-finished work that
isn't "deleted," just old. Sets `archived_at` instead of moving or deleting the row. An archive
panel (mirroring the trash panel's UX) lists archived tasks with an "Unarchive" action, plus a
bulk "Archive All" for every Done task at once.

### Subtasks

Each task can have an ordered checklist of subtask items (title + done flag), shown as a `3/5`
progress badge on the card and edited in the task detail modal. Purely manual/advisory — subtask
completion isn't wired into the Done-column invariants or blocking logic.

### Activity recency

Every card shows an "Updated X ago" line, reusing the same relative-time formatting already used
in the trash panel. Backed by the `updated_at` column described above — no separate endpoint,
just an extra field returned on `TaskOut`.

### Blocking rules

Blocking is a flag any task can carry (via `blocked_by`), not a column of its own:

- A task can be blocked while sitting in "To Do", "In Progress", or "In Review". It shows inline
  wherever it already is — no separate column, no reordering.
- A task cannot be marked Done while blocked — moving it to "Done" is rejected (`400`) until it's
  unblocked.
- A task cannot be blocked *by* something that's already Done — that would mean waiting on work
  that's already finished, so the API rejects it (`400`).
- Moving a task to "Done" automatically clears `blocked_by` on every task that pointed at it —
  finishing something can never leave a dependent blocked on a "done" task. Restoring a trashed
  task applies the same check, in case its blocker became Done (or was itself removed) while it
  sat in the trash.

### Search, filter, and WIP limits (frontend-only)

A toolbar under the header does client-side text filtering across title/description, plus quick
filters for priority and "blocked only" — pure filtering of the already-fetched board, no
additional API calls. Each column header also supports an optional WIP cap, editable inline and
persisted in the browser's `localStorage`; the count badge flags with a warning color when
exceeded. Both are purely client-side conveniences with no backend involvement.

### JSON export

A "download backup" button dumps every task (active + trashed) as JSON via `GET /api/export`,
wrapping the same data `GET /api/tasks` and `GET /api/trash` already return.

## API

| Method | Path                                     | Body                                                       | Description                                    |
|--------|-------------------------------------------|--------------------------------------------------------------|----------------------------------------------------|
| GET    | `/api/status`                             | —                                                              | Health check                                    |
| GET    | `/api/tasks`                              | —                                                              | All columns and their active tasks              |
| POST   | `/api/tasks`                               | `{column, title, description?, blocked_by?, priority?, due_date?}` | Create a task                          |
| PUT    | `/api/tasks/{task_id}/move`                | `{to_column}`                                                 | Move a task to another column                   |
| PUT    | `/api/tasks/{task_id}/blocked-by`          | `{blocked_by}`                                                | Set or clear a task's blocker (`null` clears it) |
| PUT    | `/api/tasks/{task_id}/priority`            | `{priority}`                                                  | Change a task's priority                        |
| PUT    | `/api/tasks/{task_id}/due-date`            | `{due_date}`                                                  | Set or clear a task's due date (`null` clears it)|
| DELETE | `/api/tasks/{task_id}`                     | —                                                              | Delete a task (soft — goes to trash)            |
| GET    | `/api/tasks/{task_id}/subtasks`            | —                                                              | List a task's subtasks                          |
| POST   | `/api/tasks/{task_id}/subtasks`            | `{title}`                                                     | Add a subtask                                   |
| PUT    | `/api/tasks/{task_id}/subtasks/{id}`       | `{title?, done?}`                                             | Update a subtask's title and/or done state       |
| DELETE | `/api/tasks/{task_id}/subtasks/{id}`       | —                                                              | Delete a subtask                                |
| POST   | `/api/tasks/{task_id}/archive`             | —                                                              | Archive a Done task                             |
| POST   | `/api/tasks/archive-done`                  | —                                                              | Archive every task currently in Done             |
| GET    | `/api/trash`                               | —                                                              | List trashed tasks                              |
| POST   | `/api/trash/{task_id}/restore`             | —                                                              | Restore a task to its original column           |
| DELETE | `/api/trash/{task_id}`                     | —                                                              | Permanently delete one trashed task             |
| DELETE | `/api/trash`                               | —                                                              | Permanently delete everything in trash          |
| GET    | `/api/archive`                             | —                                                              | List archived tasks                             |
| POST   | `/api/archive/{task_id}/unarchive`         | —                                                              | Unarchive a task back to Done                    |
| GET    | `/api/export`                              | —                                                              | Dump all tasks (active + trashed) as JSON        |

`task_id` is the task's own unique ID (e.g. `"KAN-05"`) — stable across moves, returned by
`GET`/`POST` and passed back as-is to the endpoints above.

`priority` must be one of `Low`, `Medium`, `High`, `Urgent` — the API returns `400` otherwise.
