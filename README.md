# CanBan

A local Kanban board. FastAPI backend, vanilla JS/HTML/CSS frontend, tasks stored in a local
SQLite database via SQLAlchemy, request/response shapes validated with Pydantic.

See [`FEATURE_IDEAS.md`](FEATURE_IDEAS.md) for the backlog of proposed/in-progress/shipped
features.

## Setup

Requires Python 3.13+.

```
uv pip install -r requirements.txt
```

For running tests, install dev dependencies instead (this also installs `requirements.txt`):

```
uv pip install -r requirements-dev.txt
```

## Running the app

```
uv run uvicorn backend.main:app --reload
```

Open http://127.0.0.1:8000 — the backend serves both the API and the static frontend.

## Running tests

```
uv run pytest
```

## Seeding sample data

`scripts/seed_sample_data.py` populates the board with a fixed set of ~16 varied sample tasks
(all priorities, all columns, blocking relationships, subtasks, notes, due dates, and a few tasks
with a deliberately backdated `updated_at`) — useful for demoing or manually testing the UI
against a non-empty board. Start the dev server first, then run:

```
uv run -m scripts.seed_sample_data
```

It talks to the running API for everything except backdating `updated_at`, which has no API
surface and goes through `backend/storage` directly. It also starts the first sprint if none is
active yet. Not idempotent — re-running against a board that already has these task titles fails
on the first duplicate-title request (`409`); point it at an empty `.kanban_data/kanban.db` (or
delete that file, it's recreated on next run) to start fresh.

## Board columns

Four fixed columns: **To Do**, **In Progress**, **In Review**, **Done**. Columns aren't a
database table — a column "exists" only in the sense that some task currently has that value as
its `column`; the frontend renders all four regardless of what the API returns.

## How data is stored

Board state lives in a single SQLite database file, `.kanban_data/kanban.db`, defined via
SQLAlchemy ORM in `backend/storage.py`. There's no migration tooling; the schema is created on
first run via `Base.metadata.create_all()`.

The `tasks` table has: `id` (integer primary key), `title`, `description`, `column`, `priority`,
`blocked_by_id` (a self-referential foreign key), `deleted_at`, `archived_at`, `due_date`,
`updated_at`, and `sprint_id` (a nullable foreign key into `sprints`). A separate `task_subtasks`
table (FK `ondelete="CASCADE"`) holds each task's subtask checklist items, a `task_notes` table
(same FK shape) holds each task's activity log entries, and a `sprints` table (`id`, `name`,
`start_date`, `end_date`, `duration_weeks`, `status`, `closed_at`) holds sprint records —
`start_date`/`end_date` are nullable to support a `"planned"` sprint, which has only a name and
`duration_weeks` until it's promoted to active.

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

**Disabled pending a redesign (2026-07-13):** the UI entry points (Archive FAB, archive panel,
per-card archive button, Archive All) are hidden behind `ARCHIVE_ENABLED = false` in
`frontend/app.js`. The backend endpoints below and any already-archived data are untouched.

### Subtasks

Each task can have an ordered checklist of subtask items (title + done flag), shown as a `3/5`
progress badge on the card and edited in the task detail modal. Purely manual/advisory — subtask
completion isn't wired into the Done-column invariants or blocking logic.

### Activity log

A timestamped, append-only list of freeform notes per task, separate from the single mutable
`description` — a running history of what happened on a long-lived task, edited in the task
detail modal, newest note first. Backed by a `task_notes` table (FK `ondelete="CASCADE"`); notes
survive their parent task being trashed and restored, and are only removed if the task is
permanently deleted. There's no edit or delete for an individual note — once added, a note stays.

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

### Sprints

A lightweight, optional time-boxing layer over the otherwise-continuous board. Rather than just a
current-sprint banner, the board shows three sprint panels at once: **Last Sprint** and **Next
Sprint** are collapsed-by-default disclosures above/below the current sprint, which keeps its own
bordered box (visually "owning" the board) with a banner showing its name, date range, and
days-remaining (or "Ends today" / "Nd overdue" once the end date has passed) plus Start/End
controls — no per-card sprint badge, no backlog view, no story points or burndown chart.

- **Starting the very first sprint** (`POST /api/sprints/start`, `{name, duration_weeks}`,
  1/2/3/4 weeks from today) sweeps up every currently-untagged, non-Done task into it. New tasks
  auto-join the active sprint on creation. Only one sprint can be active at a time.
- **Planning the next sprint ahead of time** (`POST /api/sprints/plan`, `{name, duration_weeks}`)
  queues up a name/duration without committing to a start date — shown in the "Next Sprint" panel
  with a computed, self-correcting "Starts ~&lt;date&gt; (estimated)" hint. At most one sprint can
  be planned at a time. `GET /api/sprints/planned` returns it, or `null`.
- **Ending a sprint** (`POST /api/sprints/end`, `{name, duration_weeks}` — both optional) does
  *not* leave the board without an active sprint — it atomically closes the current sprint and
  activates the next one in a single step, rolling every non-Done task from the closed sprint
  straight into the new one. If a sprint was already planned, it's promoted straight to active
  (computing real dates from its stored duration) and any `name`/`duration_weeks` in the request
  body is ignored; otherwise the "End Sprint" button opens a form for the next sprint's
  name/duration (defaulting to 2 weeks, editable), which is why the body fields are optional.
  A closed sprint's `end_date` is always overwritten with the real closing date. Done tasks keep
  their `sprint_id` pointing at the now-closed sprint permanently, as a historical record —
  they're the only way to later answer "what shipped in Sprint N."
- **Sprint names are unique** across every sprint regardless of status — starting, planning, or
  ending into a name already used by another sprint (active, planned, or long-closed) returns
  `409`.
- `GET /api/sprints/active` returns the current active sprint, or `null` if none has ever been
  started.
- `GET /api/sprints` returns every *closed* sprint, most-recently-closed first, each with a
  `completed_tasks` summary. The frontend splits this into two views: the single most-recently-
  closed sprint gets its own "Last Sprint" panel, and everything older lives behind an "Older
  Sprints" FAB + modal.

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
| GET    | `/api/tasks/{task_id}/notes`               | —                                                              | List a task's activity log notes, newest first   |
| POST   | `/api/tasks/{task_id}/notes`               | `{body}`                                                       | Append a note to a task's activity log           |
| POST   | `/api/tasks/{task_id}/archive`             | —                                                              | Archive a Done task                             |
| POST   | `/api/tasks/archive-done`                  | —                                                              | Archive every task currently in Done             |
| GET    | `/api/trash`                               | —                                                              | List trashed tasks                              |
| POST   | `/api/trash/{task_id}/restore`             | —                                                              | Restore a task to its original column           |
| DELETE | `/api/trash/{task_id}`                     | —                                                              | Permanently delete one trashed task             |
| DELETE | `/api/trash`                               | —                                                              | Permanently delete everything in trash          |
| GET    | `/api/archive`                             | —                                                              | List archived tasks                             |
| POST   | `/api/archive/{task_id}/unarchive`         | —                                                              | Unarchive a task back to Done                    |
| GET    | `/api/export`                              | —                                                              | Dump all tasks (active + trashed) as JSON        |
| POST   | `/api/sprints/start`                       | `{name, duration_weeks}`                                       | Start the first sprint (1/2/3/4 weeks)           |
| POST   | `/api/sprints/end`                         | `{name?, duration_weeks?}`                                      | End the active sprint and start/promote the next |
| GET    | `/api/sprints/active`                      | —                                                              | The active sprint, or `null` if none              |
| POST   | `/api/sprints/plan`                        | `{name, duration_weeks}`                                       | Queue up the next sprint ahead of time            |
| GET    | `/api/sprints/planned`                     | —                                                              | The planned sprint, or `null` if none              |
| GET    | `/api/sprints`                             | —                                                              | Every closed sprint, most-recently-closed first    |

`task_id` is the task's own unique ID (e.g. `"KAN-05"`) — stable across moves, returned by
`GET`/`POST` and passed back as-is to the endpoints above.

`priority` must be one of `Low`, `Medium`, `High`, `Urgent` — the API returns `400` otherwise.

`duration_weeks` must be one of `1`, `2`, `3`, `4` — the API returns `400` otherwise.
