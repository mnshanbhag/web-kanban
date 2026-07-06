# CLAUDE.md

Guidance for Claude Code when working in this repository.

## Project

Local Kanban board. FastAPI backend (`backend/`), vanilla JS/HTML/CSS frontend (`frontend/`,
served as static files by the backend — no build step, no bundler). No database: task data is
plain Markdown files under `.kanban_data/`.

## Architecture

- `backend/storage.py` — filesystem data layer. Each column is a directory under
  `.kanban_data/`; each task is a `<title>.md` file with a small frontmatter block (`id`,
  `blocked_by`) followed by the description as the body. Functions: `get_all_boards`, `add_task`,
  `update_task`, `move_task`, `delete_task`, `sanitize_name`. Column/task names are sanitized for
  filesystem-unsafe characters (`sanitize_name`) before touching disk.
- `backend/main.py` — FastAPI app. REST endpoints under `/api/tasks`, CORS wide open
  (`allow_origins=["*"]`, fine for a local-only app). Mounts `frontend/` as static files at `/`
  (must stay mounted *last* so it doesn't shadow the API routes).
- Tasks have a real, stable unique ID (`KAN-01`, `KAN-02`, ...) assigned once at creation by
  `storage._next_id`, which scans all existing task files and takes `max(id) + 1` — there's no
  separate counter file, the files themselves are the source of truth. `task_id` throughout the
  API *is* this ID, not a synthetic composite, so it stays valid across moves/renames.
- Blocking: a task in the `Blocked` column (`storage.BLOCKED_COLUMN`) must carry `blocked_by`
  pointing at another existing task's ID (validated by `storage._validate_blocker` — no
  self-blocking, blocker must exist). The reverse `"blocks"` list is **computed on every read**
  in `get_all_boards`, not stored — don't add a stored/denormalized version of it, that would let
  the two directions drift out of sync.
- `frontend/app.js` — no build tooling, no framework. Talks to the API with `fetch`. Drag-and-drop
  calls the move endpoint; dropping onto the Blocked column opens a small modal to collect the
  blocker ID first. The delete button on each card calls the delete endpoint. Errors from the API
  surface via a toast (`showError`) — **never use `alert()`/`confirm()` here**: they block the JS
  thread, and in at least one automated browser context that hung the page outright (Chrome
  DevTools Protocol couldn't dispatch further events until the dialog was dismissed).

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
