# CanBan

A local Kanban board. FastAPI backend, vanilla JS/HTML/CSS frontend, tasks stored in a local
SQLite database via SQLAlchemy, request/response shapes validated with Pydantic.

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

Board state lives in a single SQLite database file, `.kanban_data/kanban.db`, defined via
SQLAlchemy ORM in `backend/storage.py` (a single `tasks` table — see the `Task` model). There's
no migration tooling; the schema is created on first run via `Base.metadata.create_all()`.

Each row has: `id` (integer primary key), `title`, `description`, `column`, `priority`,
`blocked_by_id` (a self-referential foreign key), and `deleted_at`.

- **`id`** is exposed over the API as `"KAN-01"`, `"KAN-02"`, ... (`f"KAN-{id:02d}"`). It's never
  reused: the table uses SQLite's `AUTOINCREMENT` (`sqlite_autoincrement=True`), which guarantees
  the next inserted row's id is always higher than any id the table has ever held, even after a
  row is deleted.
- **`column`** is just a string (`"To Do"`, `"In Progress"`, `"Done"`) — there's no separate
  columns table. A column "exists" only in the sense that some task currently has that value; an
  empty board has no rows and therefore reports no columns at all (the frontend already renders
  its 3 fixed columns regardless of what the API returns, so this isn't user-visible).
- **`blocked_by_id`** is a foreign key back onto `tasks.id`, with `ON DELETE SET NULL`: if a
  blocker task is ever permanently deleted, every task that pointed at it is automatically
  unblocked at the database level rather than being left with a dangling reference. Blocking is
  independent of `column` — a task in "To Do" or "In Progress" can carry a blocker; a task in
  "Done" can never have one (see "Blocking rules" below).
- **`blocks`** (which tasks does this one block) is **not a column** — it's the SQLAlchemy
  `backref` of the `blocked_by` relationship, computed by the ORM on read.
- **`priority`** is one of `Low` / `Medium` / `High` / `Urgent`, defaulting to `Medium`.
- **`deleted_at`** is `NULL` for an active task. Setting it is the entire "soft delete"
  mechanism — the row never moves or changes shape, so restoring is just clearing it back to
  `NULL`. There's no separate `deleted_from` field like an older file-based version of this app
  had; the row's `column` was never touched by the delete in the first place.

### Recycle bin

Deleting a task sets `deleted_at` instead of removing the row. `GET /api/tasks` and the `blocks`
computation both filter to `deleted_at IS NULL`; `GET /api/trash` filters to `deleted_at IS NOT
NULL`. Restoring just clears the timestamp. Permanently deleting (or emptying the trash) is a
real `DELETE FROM tasks WHERE ...`.

### Blocking rules

Blocking is a flag any task can carry (via `blocked_by`), not a column of its own:

- A task can be blocked while sitting in "To Do" or "In Progress". It shows inline wherever it
  already is — no separate column, no reordering.
- A task cannot be marked Done while blocked — moving it to "Done" is rejected (`400`) until it's
  unblocked.
- A task cannot be blocked *by* something that's already Done — that would mean waiting on work
  that's already finished, so the API rejects it (`400`).
- Moving a task to "Done" automatically clears `blocked_by` on every task that pointed at it —
  finishing something can never leave a dependent blocked on a "done" task. Restoring a trashed
  task applies the same check, in case its blocker became Done (or was itself removed) while it
  sat in the trash.

## API

| Method | Path                            | Body                                          | Description                            |
|--------|----------------------------------|------------------------------------------------|-------------------------------------------|
| GET    | `/api/status`                   | —                                                | Health check                            |
| GET    | `/api/tasks`                     | —                                                | All columns and their tasks             |
| POST   | `/api/tasks`                      | `{column, title, description?, blocked_by?, priority?}` | Create a task                  |
| PUT    | `/api/tasks/{task_id}/move`       | `{to_column}`                                   | Move a task to another column           |
| PUT    | `/api/tasks/{task_id}/blocked-by` | `{blocked_by}`                                  | Set or clear a task's blocker (`null` clears it) |
| PUT    | `/api/tasks/{task_id}/priority`   | `{priority}`                                    | Change a task's priority                |
| DELETE | `/api/tasks/{task_id}`            | —                                                | Delete a task (soft — goes to trash)    |
| GET    | `/api/trash`                      | —                                                | List trashed tasks                      |
| POST   | `/api/trash/{task_id}/restore`    | —                                                | Restore a task to its original column   |
| DELETE | `/api/trash/{task_id}`            | —                                                | Permanently delete one trashed task     |
| DELETE | `/api/trash`                      | —                                                | Permanently delete everything in trash  |

`task_id` is the task's own unique ID (e.g. `"KAN-05"`) — stable across moves, returned by
`GET`/`POST` and passed back as-is to `move`/`blocked-by`/`priority`/`delete`/`restore`.

`priority` must be one of `Low`, `Medium`, `High`, `Urgent` — the API returns `400` otherwise.
