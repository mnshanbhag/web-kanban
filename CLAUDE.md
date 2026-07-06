# CLAUDE.md

Guidance for Claude Code when working in this repository.

## Project

Local Kanban board. FastAPI backend (`backend/`), vanilla JS/HTML/CSS frontend (`frontend/`,
served as static files by the backend — no build step, no bundler). No database: task data is
plain Markdown files under `.kanban_data/`.

## Architecture

- `backend/storage.py` — filesystem data layer. Each column is a directory under
  `.kanban_data/`; each task is a `<title>.md` file with a small frontmatter block (`id`,
  `blocked_by`, `priority`) followed by the description as the body. Functions:
  `get_all_boards`, `add_task`, `update_task`, `move_task`, `delete_task`, `sanitize_name`.
  Column/task names are sanitized for filesystem-unsafe characters (`sanitize_name`) before
  touching disk.
- `backend/main.py` — FastAPI app. REST endpoints under `/api/tasks`, CORS wide open
  (`allow_origins=["*"]`, fine for a local-only app). Mounts `frontend/` as static files at `/`
  (must stay mounted *last* so it doesn't shadow the API routes).
- Tasks have a real, stable unique ID (`KAN-01`, `KAN-02`, ...) assigned once at creation by
  `storage._next_id`. **IDs are never reused** — `_next_id` reads/writes a persistent counter
  file (`.kanban_data/.id_counter`), it does *not* scan for the current max ID on disk. Do not
  "simplify" this back to a disk scan — that would let a permanently-deleted task's ID get
  reassigned to the next new task, which is the one invariant this whole feature exists to
  protect. `task_id` throughout the API *is* this ID, not a synthetic composite, so it stays
  valid across moves/renames.
- Blocking: a task in the `Blocked` column (`storage.BLOCKED_COLUMN`) must carry `blocked_by`
  pointing at another existing task's ID (validated by `storage._validate_blocker` — no
  self-blocking, blocker must exist). The reverse `"blocks"` list is **computed on every read**
  in `get_all_boards`, not stored — don't add a stored/denormalized version of it, that would let
  the two directions drift out of sync.
- Priority: `storage.PRIORITIES = ("Low", "Medium", "High", "Urgent")`, default
  `storage.DEFAULT_PRIORITY = "Medium"`. Validated by `storage._validate_priority` on both create
  and update (`PUT /api/tasks/{task_id}/priority`) — invalid values raise `ValueError`, which
  `main.py` turns into a `400`. Priority is preserved across moves, blocking, and through the
  recycle bin (soft delete and restore) automatically, since it's just another key in the same
  frontmatter dict that every one of those operations already carries through untouched — don't
  special-case it anywhere.
- Recycle bin: `delete_task` is a **soft delete** — it moves the task's file into
  `.kanban_data/.trash/<id>.md` (filename is the ID, not the title, since trash can hold tasks
  that once shared a title with something else) and stamps `title`/`deleted_from`/`deleted_at`
  onto its frontmatter. `_iter_task_files` and `get_all_boards` explicitly exclude
  `storage.TRASH_DIRNAME` so trashed tasks never leak into the normal board view or the `blocks`
  computation. `restore_task` reads `deleted_from` to know which column to put it back in;
  `permanent_delete_task`/`empty_trash` are the only functions that actually `unlink()` a task
  file for good.
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
pytest-asyncio, httpx on top of `requirements.txt`). `pytest.ini` sets `asyncio_mode = auto` so
async tests don't need `@pytest.mark.asyncio`.

## Conventions / gotchas

- Tests must not touch the real `.kanban_data/` — monkeypatch `storage.DATA_DIR` to a `tmp_path`
  (see `backend/tests/test_tasks_api.py` for the pattern). Never assert against or clean up the
  project's real `.kanban_data/` from a test.
- API tests use `httpx.AsyncClient` with `httpx.ASGITransport(app=main.app)` — no real server
  needs to be running for tests.
- When manually smoke-testing endpoints against the real dev server, clean up any tasks/columns
  you create afterward so `.kanban_data/` doesn't accumulate throwaway data.
