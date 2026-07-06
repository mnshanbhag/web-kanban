# CLAUDE.md

Guidance for Claude Code when working in this repository.

## Project

Local Kanban board. FastAPI backend (`backend/`), vanilla JS/HTML/CSS frontend (`frontend/`,
served as static files by the backend — no build step, no bundler). Task data lives in a local
SQLite database (`.kanban_data/kanban.db`) via SQLAlchemy; request/response bodies are validated
with Pydantic (`backend/schemas.py`).

## Architecture

- `backend/storage.py` — the persistence layer. Defines the SQLAlchemy `Task` ORM model
  (`__tablename__ = "tasks"`) and every CRUD function: `get_all_boards`, `add_task`,
  `update_task`, `move_task`, `delete_task`, `get_trash`, `restore_task`,
  `permanent_delete_task`, `empty_trash`. Each function opens its own `Session` via `_session()`
  (which lazily creates the engine/DB file and runs `create_all` — cheap and idempotent, fine for
  a local single-user app; don't bother caching the engine).
- `backend/schemas.py` — Pydantic request/response models (`TaskCreate`, `TaskMove`,
  `TaskPriorityUpdate`, `TaskOut`, `TrashedTaskOut`, etc.), imported by `main.py` and wired up via
  FastAPI's `response_model=` on every endpoint — this is what actually validates/shapes what the
  API returns, not just what it accepts.
- `backend/main.py` — FastAPI app. REST endpoints under `/api/tasks`, CORS wide open
  (`allow_origins=["*"]`, fine for a local-only app). Mounts `frontend/` as static files at `/`
  (must stay mounted *last* so it doesn't shadow the API routes).
- Tasks have a real, stable unique ID assigned once at creation, exposed over the API as
  `"KAN-01"`, `"KAN-02"`, ... (`storage._display_id(pk)` / `storage._parse_id(task_id)` convert
  between the display string and the real integer primary key). **IDs are never reused** — this
  is enforced by SQLite's `AUTOINCREMENT` (`Task.__table_args__ = {"sqlite_autoincrement": True}`),
  not by any counter file or max-id scan. Do not remove that table arg; without it SQLite's
  default ROWID reuse behavior could hand a deleted task's id to a new one.
- Blocking: a task in the `Blocked` column (`storage.BLOCKED_COLUMN`) must carry `blocked_by_id`
  pointing at another existing, non-trashed task (validated by `storage._validate_blocker` — no
  self-blocking, blocker must exist). This is a real self-referential foreign key
  (`ForeignKey("tasks.id", ondelete="SET NULL")`) with FK enforcement turned on for every SQLite
  connection via the `Engine "connect"` event listener (`PRAGMA foreign_keys=ON` — SQLite doesn't
  enforce FKs by default). Permanently deleting a blocker therefore auto-nulls `blocked_by_id` on
  every task that referenced it — an actual improvement over the old file-based version, which
  just left a dangling string reference. The reverse `"blocks"` list is the SQLAlchemy `backref`
  of that relationship, computed by the ORM on read — still not a stored/denormalized column,
  don't add one.
- Priority: `storage.PRIORITIES = ("Low", "Medium", "High", "Urgent")`, default
  `storage.DEFAULT_PRIORITY = "Medium"`. Validated by `storage._validate_priority` on both create
  and update (`PUT /api/tasks/{task_id}/priority`) — invalid values raise `ValueError`, which
  `main.py` turns into a `400`.
- Recycle bin: `delete_task` is a **soft delete** — it just sets `Task.deleted_at`. The row's
  `column` is never touched, so restoring is only ever "clear `deleted_at` back to `NULL`"; there
  is deliberately no separate `deleted_from` field the way an earlier file-based version of this
  app needed (that field existed only because deleting used to *move a file*, which no longer
  happens). `get_all_boards`/`get_trash` filter on `deleted_at IS NULL` / `IS NOT NULL`
  respectively. `permanent_delete_task`/`empty_trash` are the only functions that actually
  `session.delete(...)` a row.
- **SQLite datetime gotcha**: SQLAlchemy's `DateTime` column silently drops tzinfo on
  SQLite round-trips (a value written as `datetime.now(timezone.utc)` comes back naive). Every
  value this app ever writes to `deleted_at` *is* UTC, so `storage._utc_isoformat()` re-attaches
  `timezone.utc` before calling `.isoformat()` — this is the only thing standing between a
  correct "deleted just now" and the frontend's `formatRelativeTime` silently being off by your
  local UTC offset. If you add another datetime column, route it through the same helper (or an
  equivalent) before it reaches the API.
- `frontend/app.js` — no build tooling, no framework. Talks to the API with `fetch`. Drag-and-drop
  calls the move endpoint; dropping onto the Blocked column opens a small modal to collect the
  blocker ID first. Each card's priority is an inline `<select class="priority-pill">` — colored
  via CSS `[data-priority="..."]` attribute selectors on both the pill and the card's left
  border. It has `draggable = false` and stops `mousedown`/`click` propagation so interacting
  with it doesn't fight the card's own HTML5 drag-and-drop. The delete button on each card calls
  the delete endpoint (soft delete). A recycle-bin icon fixed at the bottom-right (`.trash-fab`,
  with an unread-count badge) opens a panel listing trashed tasks with Restore / Delete
  Permanently actions, plus an Empty Trash button. Errors from the API surface via a toast
  (`showError`) — **never use `alert()`/`confirm()` here**: they block the JS thread, and in at
  least one automated browser context that hung the page outright (Chrome DevTools Protocol
  couldn't dispatch further events until the dialog was dismissed). Destructive trash actions
  (permanent delete, empty trash) use a custom in-page confirm modal (`confirmAction()` /
  `#confirm-modal-overlay`) instead of native `confirm()`, for the same reason.

## Running things

```
python -m uvicorn backend.main:app --reload
```
(also the "backend" config in `.claude/launch.json`, usable via the preview tool).

Tests: `python -m pytest` (needs `requirements-dev.txt` installed — adds pytest,
pytest-asyncio, httpx on top of `requirements.txt`, which itself now includes SQLAlchemy).
`pytest.ini` sets `asyncio_mode = auto` so async tests don't need `@pytest.mark.asyncio`.

## Conventions / gotchas

- Tests must not touch the real `.kanban_data/` — monkeypatch `storage.DATA_DIR` to a `tmp_path`
  (see `backend/tests/test_tasks_api.py` for the pattern); this redirects the SQLite file, not
  just markdown files, so the pattern still works unchanged. Never assert against or clean up the
  project's real `.kanban_data/` from a test.
- API tests use `httpx.AsyncClient` with `httpx.ASGITransport(app=main.app)` — no real server
  needs to be running for tests. To inspect persisted rows directly in a test, open a session
  with `storage._session()` and `session.get(storage.Task, <int pk>)` (note: the *integer* pk,
  not the `"KAN-NN"` display string).
- When manually smoke-testing endpoints against the real dev server, clean up any tasks/columns
  you create afterward so `.kanban_data/kanban.db` doesn't accumulate throwaway data (or just
  delete the file — it's recreated automatically on next run).
