# Feature ideas backlog

Maintained by the `feature-ideator` subagent. Each entry is a proposed idea, not a commitment —
pick one and hand it to `feature-implementer` to actually build it.

**Status key:** 🆕 proposed · 🚧 in progress · ✅ shipped · ❌ shelved

---

## ✅ Shipped

### Due dates with overdue indication
Nullable `due_date` on tasks with an "Overdue" badge on cards past due (suppressed for Done).
Shipped on `feature_due_dates` (2026-07-08).

### Search / filter bar
Client-side text filter across title/description, plus quick filters (priority, blocked-only), in
a new toolbar under the header. Pure frontend filtering of the already-fetched board (no new
endpoint) — hides non-matching cards via a CSS class and shows a `visible/total` count per column
while a filter is active. Shipped on `feature_search_filter` (2026-07-09).

### WIP limit warning per column
Optional per-column WIP cap, editable inline in the column header and persisted in
`localStorage`; the count badge flags with the existing warning color when exceeded. Purely
advisory — no backend change. Shipped on `feature_wip_limits` (2026-07-09).

### JSON export (manual backup)
A "download backup" button dumping all tasks (active + trashed) as JSON — the export half of the
originally-proposed export/import pair (see remaining import scope under Proposed #6). New
`GET /api/export` wraps the existing `get_all_boards`/`get_trash`, no new table. Shipped on
`feature_json_export` (2026-07-13) — also served as a live test that `feature-implementer` can
use the new `new-endpoint` skill.

### Scrum sprints
A lightweight, optional time-boxing layer over the existing continuous board: start a named
sprint with a fixed duration (1/2/3/4 weeks, picked from today), and a banner above the board
shows its name/date range/days-remaining with Start/End Sprint controls. No backlog view, no
story points, no burndown/velocity chart — deliberately scoped down from "full Scrum" to just
sprints. New `Sprint` table (`sprints`: name, start_date, end_date, status, closed_at) plus a
nullable `Task.sprint_id` FK (`ondelete="SET NULL"`, same shape as the existing `blocked_by_id`
self-FK); `start_sprint`/`end_sprint`/`get_active_sprint` storage functions;
`POST /api/sprints/start`, `POST /api/sprints/end`, `GET /api/sprints/active`; a banner + small
"Start Sprint" modal in the frontend (no per-card badge — keeps the existing card-density
decision intact). Tasks auto-join the active sprint on creation; ending a sprint clears the
sprint tag from any non-Done task in it, and starting the next sprint sweeps up every
currently-untagged, non-Done task (the "incomplete work rolls forward" mechanism). Done tasks
keep their `sprint_id` permanently as a historical record. Shipped on `feature_scrum_sprints`
(2026-07-13).

---

## 🚧 In Progress

### Subtask checklists
A small ordered checklist of items within a task (e.g. "Write tests", "Update docs"), shown as a
`3/5` progress badge on the card and edited in the detail modal.
- **Why:** priority/blocking/due-dates all operate at the whole-task level; there's no way to
  break a task into steps without splintering it into multiple cards.
- **Scope:** medium — a new `TaskSubtask` table (FK `ondelete="CASCADE"` on `Task.id`, plus an
  ordering column), a couple of endpoints, and detail-modal UI; the card itself only needs the
  count badge, keeping the existing card-density decision intact (see `feedback_card_density` in
  memory).
- **Tension:** subtask completion should be purely manual/advisory (same spirit as WIP limits) —
  don't wire it into the Done-column invariants or blocking logic, to avoid new edge cases.
- Handed to `feature-implementer` (2026-07-13).

### Archive Done tasks separately from trash
A manual "Archive" action on Done cards (alongside the existing delete button), hiding the task
from the board without touching the trash/soft-delete path. An archive panel — mirroring the
existing trash panel's UX — lists archived tasks with an "Unarchive" action.
- **Why:** long-lived boards accumulate Done clutter that isn't "deleted," just old; manual
  archiving (chosen over an automatic age-based sweep) keeps behavior predictable for a
  single-user local tool and reuses most of the existing trash-panel plumbing.
- **Scope:** medium — a third state (`archived_at`) alongside active/trashed, an archive panel
  UI component closely mirroring the trash panel, one new endpoint pair
  (archive/unarchive) plus a list endpoint.
- **Tension:** must not get confused with the existing `deleted_at IS NULL` filtering or the
  `blocks` backref computation — read `storage.py`'s trash/soft-delete section carefully before
  implementing, since archived and trashed are two independent, non-overlapping states (a task
  can't be both). Only Done tasks should be archivable — enforce it server-side, not just by
  hiding the button.
- Handed to `feature-implementer` (2026-07-13).

---

## 🆕 Proposed

### 1. Tags / labels
Free-form labels per task (e.g. "bug", "chore"), shown as chips, filterable.
- **Why:** priority + column cover urgency/status but not categorization by kind of work.
- **Scope:** small if a single comma-separated string column on `Task`; medium-large if a proper
  many-to-many (`tags` + `task_tags` tables).
- **Tension:** tag *editing* should live in the detail modal only, matching the deliberate
  card-density decision already made for blocking (see `feedback_card_density` in memory).

### 2. Per-task activity log (append-only notes)
A timestamped list of freeform notes on a task, separate from the single mutable `description`.
- **Why:** `description` gets overwritten on every edit — no way to keep a running history of
  what happened on a long-lived task.
- **Scope:** medium-large — new `TaskNote` table (FK `ondelete="CASCADE"`), new endpoints, UI
  inside the existing detail modal.
- **Tension:** `created_at` needs the same `_utc_isoformat()` tzinfo treatment as `deleted_at`/
  `due_date`. Decide whether notes survive soft-delete/restore (they should, same as the task row).

### 3. "Updated X ago" / activity recency
An `updated_at` column touched on every mutation, surfaced on cards via the existing
`formatRelativeTime` (already used for the trash panel).
- **Why:** at-a-glance staleness signal — e.g. "this In Progress card hasn't moved in 9 days."
- **Scope:** small-medium — touch it in every mutating storage function (`update_task`,
  `set_blocked_by`, `move_task`, `set_due_date`, ...).
- **Tension:** same tzinfo gotcha as above. Easy to miss a mutation path (e.g. the Done-cascade's
  dependent-clearing loop in `move_task`) — decide upfront whether that counts as "updating."

### 4. Past sprints view
A way to see closed sprints after the fact — a `GET /api/sprints` list endpoint (most-recent-
first) plus a small "past sprints" panel in the UI (name, date range, which tasks completed
during it).
- **Why:** the Scrum sprints feature (shipped) closes a sprint by flipping its `status` to
  `"closed"` and clearing `sprint_id` off any non-Done task in it, but never exposes closed
  sprints anywhere — the data sits inert in the `sprints` table with no way to look back at it.
- **Scope:** small, and purely additive on top of Scrum sprints' schema — no new columns, just a
  list endpoint (mirrors `get_trash()`/`get_archive()`'s pattern) and a read-only view. Done
  tasks already retain their `sprint_id` after a sprint closes, so "which tasks completed in
  Sprint N" falls out of a simple query once this exists.

### 5. JSON import (manual backup, remainder)
Import side of the export/import pair — the export half was split off and handed to
`feature-implementer` (see In Progress) as a live test of the `new-endpoint` skill.
- **Why:** export alone only covers backup, not restore.
- **Scope:** the harder half — must mint *new* IDs and remap `blocked_by` references rather than
  reusing exported IDs, since reusing them risks colliding with or resurrecting IDs the
  `AUTOINCREMENT` guarantee has already retired.
- **Tension:** don't start this until export has shipped and been used at least once.

### 6. Sprint timeline view (last / current / next)
On startup, show three sprint panels at once — last, current, and next — instead of just a
current-sprint banner. Last and next are collapsed by default to save space; current stays
expanded. Explicitly kept as its own later increment, not folded into the Scrum sprints feature's
first pass (2026-07-13).
- **Why:** Scrum sprints only ever surfaces the current sprint; #4 (Past sprints view) exposes
  history but only via a separate panel a user has to open. This idea instead puts the immediate
  before/after context of the current sprint on the board by default.
- **Scope:** medium-to-large, and depends on both Scrum sprints (shipped) and #4. It also adds a
  capability neither of those has: a **pre-planned "next" sprint** — sprints today only come into
  existence when started, so surfacing a real "next sprint" (name + dates, not just a placeholder)
  requires a new `"planned"` `Sprint` status creatable ahead of the current sprint ending, plus
  whatever start-time behavior reconciles a planned sprint with the existing
  auto-start/rollover-sweep logic.
- **Tension:** don't build this until #4 too (the "last sprint" panel is essentially a size-1
  version of #4's list). The "planned" status is new surface area on top of the existing `status`
  column (`"active"`/`"closed"` today) — needs its own design pass on how a planned sprint
  transitions to active and what happens if the current sprint is ended early or extended
  relative to a planned sprint's start date.
- **Status:** idea only, not scoped in detail yet, not handed to `feature-implementer`.

---

### 7. PostgreSQL support (for Vercel deployment)
Make the storage layer able to run against Postgres instead of (or alongside) SQLite, so the app
can be deployed to Vercel — Vercel's serverless functions have an ephemeral/read-only-ish
filesystem, so the current `.kanban_data/kanban.db` file won't reliably persist writes across
requests once deployed there.
- **Why:** the whole point is unblocking a Vercel deploy of this project; SQLite-on-serverless is
  the specific thing standing in the way.
- **Scope:** medium — likely a `DATABASE_URL`-style env var read in `storage._session()`/engine
  setup, defaulting to today's SQLite file when unset (keeps local dev/tests zero-config) and
  switching to Postgres when set (as Vercel Postgres/Neon would provide). Needs a Postgres driver
  added to `requirements.txt`.
- **Tension:** several bits of `storage.py` are SQLite-specific and need dialect-aware handling,
  not a blind swap:
  - `Task.__table_args__ = {"sqlite_autoincrement": True}` — this flag is meaningless (and per
    SQLAlchemy docs, silently ignored) on Postgres, which never reuses serial/identity values by
    default anyway; need to confirm the "IDs never reused" invariant still holds without it.
  - The `Engine "connect"` listener that issues `PRAGMA foreign_keys=ON` is SQLite-only syntax —
    Postgres enforces FKs by default and doesn't understand that pragma, so this needs to become
    conditional on dialect rather than running unconditionally.
  - `storage._utc_isoformat()` exists specifically because SQLite drops tzinfo on `DateTime`
    round-trips; Postgres's `TIMESTAMP WITH TIME ZONE` doesn't have that problem, so the helper
    may need to become a no-op (or conditional) on Postgres rather than being removed outright —
    removing it would break the SQLite path if dual support is kept.
  - No schema-migration tool exists today (`create_all`-only, a tension the Scrum sprints feature
    already hit and worked around with a one-time manual DB-file deletion) — decide whether this
    is finally the moment to introduce Alembic, or whether `create_all` is still good enough for a
    fresh Postgres database.
  - Existing tests monkeypatch `storage.DATA_DIR` to point SQLite at a `tmp_path`
    (`backend/tests/test_tasks_api.py`) — if dual support is kept, tests can keep doing exactly
    this against SQLite; only a manual/CI smoke test would exercise the Postgres path.
  - Moving *existing* local data into a new Postgres instance isn't really "migration" so much as
    export/import — ties into the JSON export (shipped) and JSON import (#5, not yet built) ideas.
- **Status:** idea only, not scoped down or handed to `feature-implementer` yet — open questions
  above (dual support vs. Postgres-only, Alembic vs. not) need a decision first.

---

## ❌ Shelved

### Manual card ordering within a column
Let a card be dragged to a specific position within a column, not just between columns —
persisted across reloads.
- **Why shelved:** doesn't add any value.
- **Shelved:** 2026-07-08.

### Keyboard shortcuts / quick-add
A shortcut to open "new task," `/` to focus search (pairs with the already-shipped search bar),
arrow-key card navigation.
- **Why shelved:** no tangible benefit.
- **Shelved:** 2026-07-13.
