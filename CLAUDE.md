# CLAUDE.md

Guidance for Claude Code when working in this repository.

## Project

Local Kanban board. FastAPI backend (`backend/`), vanilla JS/HTML/CSS frontend (`frontend/`,
served as static files by the backend — no build step, no bundler). Task data lives in a local
SQLite database (`.kanban_data/kanban.db`) via SQLAlchemy; request/response bodies are validated
with Pydantic (`backend/schemas.py`).

`FEATURE_IDEAS.md` is a backlog of proposed features, maintained by the `feature-ideator`
subagent and built by handing an entry to `feature-implementer`. Not a spec — see its own status
key for what's proposed/in-progress/shipped/shelved.

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
- Blocking is a **flag** (`blocked_by_id`), not a column — `storage.DONE_COLUMN = "Done"` is the
  only column with special meaning now. A task in any non-Done column can carry `blocked_by_id`
  pointing at another existing, non-trashed, non-Done task (validated by
  `storage._validate_blocker` — no self-blocking, blocker must exist, blocker can't already be
  Done). This is a real self-referential foreign key (`ForeignKey("tasks.id", ondelete="SET
  NULL")`) with FK enforcement turned on for every SQLite connection via the `Engine "connect"`
  event listener (`PRAGMA foreign_keys=ON` — SQLite doesn't enforce FKs by default). Permanently
  deleting a blocker auto-nulls `blocked_by_id` on every task that referenced it via that FK. The
  reverse `"blocks"` list is the SQLAlchemy `backref` of that relationship, computed by the ORM on
  read — still not a stored/denormalized column, don't add one.
  - `storage.set_blocked_by(task_id, blocked_by)` is the only way to set/clear a block — pass
    `None` to clear it. It's independent of `move_task`; moving a task no longer touches
    `blocked_by_id` at all except in the two cases below.
  - `move_task` rejects (`ValueError` → `400`) moving a blocked task to Done.
  - `move_task` cascades: when a task's *target* column is Done, every active task whose
    `blocked_by_id` points at it gets cleared. This is the "finishing something can't leave a
    dependent blocked" rule — don't remove it, and don't be tempted to move it into
    `set_blocked_by` instead, since it needs to fire on every path that can result in a task
    becoming Done, not just explicit blocking calls.
  - `restore_task` re-checks the blocker on restore (was it deleted or did it become Done while
    this task sat in the trash?) and clears `blocked_by_id` if so — the same invariant enforced a
    second time, because trashed tasks are invisible to the `move_task` cascade above.
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
  equivalent) before it reaches the API. `Task.updated_at` and `TaskNote.created_at` both go
  through it too.
- `Task.updated_at` is bumped by every *content*-mutating storage function (`update_task`,
  `set_blocked_by`, `set_due_date`, and `move_task` — including on a *dependent* task when the
  Done-cascade clears its `blocked_by_id`, which counts as an update to that dependent even though
  the mutating call was against the blocker). It is deliberately **not** touched by lifecycle-only
  operations (delete, restore, archive, unarchive) — if you add a new mutating storage function,
  decide explicitly whether it should bump `updated_at` rather than assuming it does.
- Archive/Unarchive is fully implemented server-side (`archive_task`, `unarchive_task`,
  `get_archive`, the `archived_at` column) but its frontend entry points are currently **disabled
  pending a redesign** via `ARCHIVE_ENABLED = false` in `frontend/app.js` — the Archive FAB,
  archive modal, per-card archive button, and Archive All button are all gated behind that one
  flag (plus matching `hidden` classes in `index.html`). Don't "fix" the missing UI without
  checking this flag first; don't build new features against the assumption that Archive is
  reachable from the UI.
- Scrum sprints: only one `Sprint` can have `status == "active"` at a time — `start_sprint`
  raises if one already exists. Sprint names are also globally unique across every sprint
  regardless of status (active, planned, or long-closed) — `storage._assert_sprint_name_available`
  (mirrors the per-column `_assert_title_available` used for task titles) is checked in
  `start_sprint`, `plan_next_sprint`, and `end_sprint`'s fallback (prompt-driven) branch, raising
  `FileExistsError` → `409`. This matters because the Last/Older Sprints panels render by name —
  two same-named closed sprints would otherwise be indistinguishable there. `end_sprint`'s
  promotion branch doesn't re-check: a planned sprint's name was already validated once at
  `plan_next_sprint` time and sprint records are never renamed afterward, so it can't have gone
  stale by promotion time. `end_sprint` never leaves the board without an active sprint: it
  atomically closes the current sprint and creates+activates the next one in the same call (or
  promotes an already-`"planned"` sprint if one is queued — see below), rolling every non-Done
  task from the closed sprint into the new one (plus sweeping up any still-untagged non-Done
  task, the only way that happens being a task created before the very first sprint). Done tasks
  keep their `sprint_id` pointing at the now-closed sprint permanently as a historical record —
  don't null it out or reassign it. A sprint's `end_date` is a target, not a promise: `end_sprint`
  overwrites the *closing* sprint's `end_date` with the real closing date (today) every time,
  regardless of whether it closed early, on time, or late relative to whatever `end_date` was
  computed at start/promotion time — don't assume a closed sprint's stored `end_date` still
  matches what `start_sprint`/promotion originally set. The sprint banner and the board are
  wrapped together in a single bordered `.sprint-board-wrap` box (`frontend/index.html`/
  `style.css`) so the board visually reads as belonging to the active sprint — this replaced an
  earlier "banner-only" thin-bar treatment that didn't make that ownership legible on its own.
  That redesign surfaced a real gap: Done is the one column that was never sprint-scoped (it
  showed every completion ever, from every sprint). `TaskOut` now exposes `sprint_id`, and
  `frontend/app.js`'s `tasksForColumn()` filters the Done column client-side down to the active
  sprint's own completions (legacy tasks with `sprint_id == null`, predating any sprint ever
  starting, are still shown there since there's nowhere else to surface them) — don't remove this
  filtering on the assumption Done should always show every task; that assumption is what caused
  the bug in the first place.
- Past sprints: `storage.get_past_sprints()` (mirrors the `get_trash()`/`get_archive()` pattern)
  returns every closed sprint, most-recently-closed first, each annotated with a
  `completed_tasks` summary — the Done tasks whose `sprint_id` matches, which falls straight out
  of the invariant above with no new column needed. `GET /api/sprints` exposes it. The frontend
  splits this into two surfaces rather than one: the single most-recently-closed sprint gets its
  own "Last Sprint" panel (a `<details>` disclosure, collapsed by default, directly above the
  current-sprint box — see below), and everything *older* than that lives in a separate
  "Older Sprints" panel (FAB + modal, mirroring the trash/archive panel UX; despite the id/JS
  names still saying `past-sprints-*` internally) — `renderPastSprints()` explicitly
  `.slice(1)`s the list to exclude the last sprint, since that one already has its own panel and
  showing it twice would be redundant. Don't render the full unsliced list in that modal again.
  Both panels share `createPastSprintItemElement()` to render a sprint's date range + completed-
  task chips, but it takes a `showHeader` option (default `true`): the Older Sprints *list* needs
  each item's own name/date header since it shows several sprints at once, but the Last Sprint
  *panel* already shows the name and date range in its own summary row (`renderLastSprintPanel()`
  builds that row itself, name + dates as separate spans) — call it with `showHeader: false` there
  so the name isn't rendered a second time in the body.
- Sprint timeline (last / current / next): alongside `"active"`/`"closed"`, a `Sprint.status` can
  be `"planned"` — a queued-up next sprint with only a `name`/`duration_weeks`, no `start_date`/
  `end_date` yet (both nullable; only computed at promotion time, so there's no fixed planned
  start date to drift from if the current sprint ends earlier or later than expected).
  `storage.plan_next_sprint()` requires an active sprint and enforces at most one `"planned"`
  sprint at a time, mirroring `start_sprint`'s at-most-one-`"active"` check;
  `storage.get_planned_sprint()` reads it back. `end_sprint` checks for a queued planned sprint
  first and promotes it straight to active if one exists (computing real dates from its stored
  `duration_weeks` as of the promotion moment, ignoring any name/duration passed to the call),
  falling back to the original prompt-driven flow otherwise — which is why `POST /api/sprints/end`
  body fields are optional now, validated at call time instead of via required Pydantic fields.
  New endpoints: `POST /api/sprints/plan`, `GET /api/sprints/planned`. Frontend: a "Next Sprint"
  `<details>` panel (collapsed by default, below the current-sprint box) shows the planned
  sprint's name/duration once one exists, plus a computed-not-stored "Starts ~&lt;date&gt;
  (estimated)" hint derived from the *current* active sprint's own `end_date` (never a placeholder
  guess before something's actually been planned) — this is why the estimate self-corrects if the
  current sprint ends earlier/later than expected, without needing any extra logic: the real
  `start_date` is computed fresh at promotion time regardless of what this preview showed.
- `frontend/app.js` — no build tooling, no framework. 4 columns (`COLUMNS` = To Do, In Progress,
  In Review, Done — no separate "Blocked" column).
  Talks to the API with `fetch`. Drag-and-drop just calls the move endpoint directly now; there's
  no special-cased drop target anymore. Each card shows an inline "Blocked by KAN-XX" /
  "Blocks KAN-YY" badge when applicable (rendered in-place, cards never move or group by blocked
  state — this was a deliberate choice over grouping/sorting variants, see project history if you
  need the rationale), but the card itself carries **no editing controls** — clicking anywhere on
  a card (other than the priority pill or delete button, which stop propagation) opens
  `#task-detail-modal-overlay` via `openTaskDetail(column, task)`. That's deliberate: an earlier
  version put a "Block"/"Unblock" button directly on the card and the user asked for it to move
  behind a click-in detail view instead, to keep the board itself lean — see
  `feedback_card_density` in memory if this pattern gets challenged again. The detail view has a
  plain `#detail-blocked-by` text input (not a separate modal) — empty means unblocked, a task ID
  means blocked by that task; submitting the form calls `setBlockedBy(id, value || null)`. That
  field (and its Save button) is hidden entirely for cards in Done, since a Done task can never be
  blocked (an invariant enforced server-side too — don't rely on the frontend hiding it as the
  only guard). Each card's priority is an inline `<select class="priority-pill">` — colored via CSS
  `[data-priority="..."]` attribute selectors on both the pill and the card's left border. It has
  `draggable = false` and stops `mousedown`/`click` propagation so interacting with it doesn't
  fight the card's own HTML5 drag-and-drop. The delete button on each card calls the delete
  endpoint (soft delete). A recycle-bin icon fixed at the bottom-right (`.trash-fab`,
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
