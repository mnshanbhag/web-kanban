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
- **`column`** is just a string (`"To Do"`, `"In Progress"`, `"Blocked"`, `"Done"`) — there's no
  separate columns table. A column "exists" only in the sense that some task currently has that
  value; an empty board has no rows and therefore reports no columns at all (the frontend already
  renders its 4 fixed columns regardless of what the API returns, so this isn't user-visible).
- **`blocked_by_id`** is a foreign key back onto `tasks.id`, with `ON DELETE SET NULL`: if a
  blocker task is ever permanently deleted, every task that pointed at it is automatically
  unblocked at the database level rather than being left with a dangling reference.
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
