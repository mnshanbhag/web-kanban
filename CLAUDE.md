# CLAUDE.md

Guidance for Claude Code when working in this repository.

## Project

Local Kanban board. FastAPI backend (`backend/`), vanilla JS/HTML/CSS frontend (`frontend/`,
served as static files by the backend — no build step, no bundler). No database: task data is
plain Markdown files under `.kanban_data/`.

## Architecture

- `backend/storage.py` — filesystem data layer. Each column is a directory under
  `.kanban_data/`; each task is a `<title>.md` file with a small frontmatter block (currently
  just `priority`) followed by the description as the body. Functions: `get_all_boards`,
  `add_task`, `update_task`, `move_task`, `delete_task`, `sanitize_name`. Column/task names are
  sanitized for filesystem-unsafe characters (`sanitize_name`) before touching disk — colons are
  stripped, which the API layer relies on (see below).
- `backend/main.py` — FastAPI app. REST endpoints under `/api/tasks`, CORS wide open
  (`allow_origins=["*"]`, fine for a local-only app). Mounts `frontend/` as static files at `/`
  (must stay mounted *last* so it doesn't shadow the API routes).
- Tasks have no numeric ID. The API synthesizes `task_id` as `"<column>::<title>"`. This only
  works because `sanitize_name` strips `:` from stored names, so `::` is an unambiguous
  delimiter. If you ever change what characters are sanitized, re-check this assumption.
- Priority: `storage.PRIORITIES = ("Low", "Medium", "High", "Urgent")`, default
  `storage.DEFAULT_PRIORITY = "Medium"`. Validated by `storage._validate_priority` on both create
  and update — invalid values raise `ValueError`, which `main.py` turns into a `400`.
- `frontend/app.js` — no build tooling, no framework. Talks to the API with `fetch`. Drag-and-drop
  calls the move endpoint; the delete button on each card calls the delete endpoint. Each card's
  priority is an inline `<select class="priority-pill">` — colored via CSS
  `[data-priority="..."]` attribute selectors on both the pill and the card's left border. It has
  `draggable = false` and stops `mousedown`/`click` propagation so interacting with it doesn't
  fight the card's own HTML5 drag-and-drop.

## Branch note

This frontmatter approach (`backend/storage._parse_task_content` /
`_render_task_content`) was introduced independently on this branch (`feature_priority`) to store
`priority`. A sibling branch, `feature_blocked_col`, introduced the *same* frontmatter mechanism
independently to store a task `id` and `blocked_by`. **These will conflict when merged** — the
fix is to combine both schemes into one frontmatter block (`id`, `priority`, `blocked_by`) rather
than picking one side, and reconcile `get_all_boards()`/`add_task()`/`update_task()` to carry all
three fields.

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
