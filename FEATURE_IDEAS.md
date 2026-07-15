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
originally-proposed export/import pair (see remaining import scope under Proposed #2). New
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
modal in the frontend (no per-card badge — keeps the existing card-density decision intact).
Tasks auto-join the active sprint on creation.

**Revised during live testing (2026-07-13):** the first pass had "End Sprint" clear the sprint
tag off every non-Done task (back to untagged), relying on the *next* sprint's `start_sprint` to
sweep untagged tasks back up — which left the board with a "no active sprint, some tasks
untagged" gap any time you ended a sprint without immediately starting another. Ending a sprint
now always transitions directly into the next one: the End Sprint button opens a modal (name +
duration, prefilled to 2 weeks, editable) and `end_sprint(next_name, next_duration_weeks)`
atomically closes the current sprint *and* creates+activates the new one, moving every non-Done
task from the closed sprint straight into it (no untagged gap in between). It still also sweeps
up any currently-untagged non-Done task (the only way that can happen now is a task created
before the very first sprint ever started), reusing the same sweep logic `start_sprint` uses for
that initial bootstrap case — `start_sprint` itself is unchanged and still the only path to
create the very first sprint. Done tasks still keep their `sprint_id` pointing at the
now-closed sprint permanently, as a historical record. Shipped on `feature_scrum_sprints`
(2026-07-13).

**Revised again (2026-07-14):** the banner-only display wasn't enough to make it clear the board's
cards belonged to the active sprint ("cards are just dangling"), so the banner and board are now
wrapped together in a single bordered `.sprint-board-wrap` box. That redesign surfaced a real bug:
the Done column had never been sprint-scoped — it showed every completed task ever, from every
sprint, so cards finished in an earlier sprint appeared to be inside "this sprint's" box. Fixed by
exposing `sprint_id` on `TaskOut` and filtering Done client-side to the active sprint's own
completions (pre-sprint legacy Done tasks with `sprint_id == null` are still shown, since there's
nowhere else to surface them). Shipped alongside the Past sprints view entry below, on
`feature_past_sprints_view` (2026-07-14).

### Per-task activity log (append-only notes)
A timestamped list of freeform notes on a task, separate from the single mutable `description`.
New `TaskNote` table (FK `ondelete="CASCADE"`), `GET`/`POST /api/tasks/{task_id}/notes`, and UI
inside the existing detail modal, newest note first. Notes survive their parent task being
trashed and restored, and are only removed if the task is permanently deleted; there's no edit or
delete for an individual note — once added, a note stays. Shipped on `feature_activity_log`
(2026-07-13).

### "Updated X ago" / activity recency
An `updated_at` column touched on every content-mutating storage function (`update_task`,
`set_blocked_by`, `set_due_date`, `move_task` — including the Done-cascade's dependent-clearing
loop), surfaced on cards via the existing `formatRelativeTime` (already used for the trash panel).
Not touched by lifecycle-only operations (delete, restore, archive, unarchive). Shipped on
`feature_updated_at` (2026-07-13).

### Past sprints view
A way to see closed sprints after the fact. New `GET /api/sprints` returns every closed sprint
(most-recently-closed first, ordered by `closed_at` then `id` as a tiebreaker; the currently
active sprint — which has no `closed_at` — is excluded, since the primary use case is looking
back at history), each annotated with a `completed_tasks` summary (id + title) of the Done tasks
that carry its `sprint_id` — no new columns needed, since Done tasks already keep `sprint_id`
pointing at their now-closed sprint permanently. Storage-side, `get_past_sprints()` mirrors the
existing `get_trash()`/`get_archive()` pattern. A read-only "Past Sprints" panel (a FAB + modal
mirroring the trash/archive panel UX) lists each closed sprint's name, date range, and completed
tasks as chips. Shipped on `feature_past_sprints_view` (2026-07-14).

### Sprint timeline view (last / current / next)
On startup, shows three sprint panels at once — last, current, and next — instead of just a
current-sprint banner. Last and next are collapsed `<details>` disclosures by default (native,
no extra JS); current stays expanded and, together with the board, keeps the existing bordered
"box" treatment (`.sprint-board-wrap`) so the board still visually reads as belonging to the
active sprint. New `Sprint.status == "planned"` value alongside `"active"`/`"closed"` —
`start_date`/`end_date` are now nullable, since a planned sprint has only a `name` and
`duration_weeks` until it's promoted. A standalone "Plan Next Sprint" control (name + duration,
no date picker) is usable any time a sprint is active; storage enforces at most one `"planned"`
sprint at a time, mirroring the existing at-most-one-`"active"` check. `end_sprint` now checks
for a queued planned sprint first and, if one exists, promotes it straight to active (computing
real `start_date`/`end_date` from its stored `duration_weeks` as of the promotion moment),
ignoring any name/duration passed in the request; otherwise it falls back to the original
prompt-driven flow, which is why `POST /api/sprints/end`'s body fields are now optional. Two new
endpoints: `POST /api/sprints/plan` and `GET /api/sprints/planned`. The "next" panel only ever
shows a real sprint once one has been explicitly planned — until then it renders a "nothing
planned yet" empty state plus the plan form (hidden entirely when no sprint is active), never a
placeholder guess. The "last" panel is a size-1 read of the already-shipped `GET /api/sprints`
(most-recently-closed first), reusing its existing list-item rendering.

**Revised during live testing (2026-07-14):** three follow-up fixes surfaced from actually using
the timeline:
- The "last sprint" `<details>` summary showed the sprint's name in a muted, easy-to-miss style —
  bumped `.sprint-panel-summary-info` to full-contrast bold text so it's legible without expanding.
- The old "Past Sprints" panel duplicated the sprint already shown in the new "Last Sprint" panel.
  Renamed to "Older Sprints" and `renderPastSprints()` now `.slice(1)`s the list to exclude the
  most-recently-closed sprint (still fetched from the same unfiltered `GET /api/sprints`).
- A closed sprint's `end_date` was never updated at close time, so ending a sprint early (or late)
  left its stored `end_date` showing the original target instead of when it actually closed —
  also made Sprint N+1 visually overlap Sprint N's date range. `end_sprint` now overwrites the
  *closing* sprint's `end_date` with the real closing date every time, regardless of which path
  (promotion or fallback) closed it.
- Added: while a sprint is planned but not yet promoted, the "Next Sprint" panel shows a
  computed-not-stored "Starts ~&lt;date&gt; (estimated)" hint derived from the *current* active
  sprint's own `end_date` — purely a preview, so it self-corrects for free if the current sprint
  ends earlier/later than expected (the real `start_date` is still only computed at promotion
  time, unchanged from the original design).

**Revised during live testing (2026-07-15):** two more follow-ups:
- The "last sprint" `<details>` body repeated the sprint's name a second time (it's already shown
  in the summary row) via the same `createPastSprintItemElement()` used for the many-sprint
  "Older Sprints" list. That helper now takes a `showHeader` option; the Last Sprint panel passes
  `showHeader: false` and instead folds the date range into the summary row next to the name
  (new `.sprint-panel-summary-dates` style), so the body is just the completed-task chips.
- Sprint names were never checked for uniqueness, so `start_sprint`/`plan_next_sprint`/`end_sprint`
  could all create a sprint reusing a name already used by another sprint (active, planned, or
  long-closed) — surfaced by two different closed sprints both named "Sprint X" showing up
  side-by-side in "Older Sprints" with no way to tell them apart. New `_assert_sprint_name_available`
  (mirrors the existing per-column `_assert_title_available` for tasks) rejects a collision with a
  `FileExistsError` → `409`, checked at all three sprint-creation call sites.

**Shipped on `feature_sprint_timeline_view` (2026-07-14) — based on `feature_past_sprints_view`,
not `main`.** No separate merge needed: this branch already contains every commit from
`feature_past_sprints_view` up through the sprint-box redesign (`45a6fd2`) where it branched off.
The one commit `feature_past_sprints_view` has since gained on top of that (`55ca9f8`, a docs-only
commit describing that same redesign) is superseded by this branch's own docs above — merge this
branch straight into `main` and treat `feature_past_sprints_view` as redundant.

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
- **Disabled (2026-07-13):** UI entry points hidden pending a redesign — see
  `ARCHIVE_ENABLED` in `frontend/app.js`. Backend endpoints and existing archived data are
  untouched; re-enabling is a one-line flip once the redesign lands.

---

## 🆕 Proposed

### 1. Tags / labels
Free-form labels per task (e.g. "bug", "chore"), shown as chips, filterable.
- **Why:** priority + column cover urgency/status but not categorization by kind of work.
- **Scope:** small if a single comma-separated string column on `Task`; medium-large if a proper
  many-to-many (`tags` + `task_tags` tables).
- **Tension:** tag *editing* should live in the detail modal only, matching the deliberate
  card-density decision already made for blocking (see `feedback_card_density` in memory).

### 2. JSON import (manual backup, remainder)
Import side of the export/import pair — the export half was split off and handed to
`feature-implementer` (see In Progress) as a live test of the `new-endpoint` skill.
- **Why:** export alone only covers backup, not restore.
- **Scope:** the harder half — must mint *new* IDs and remap `blocked_by` references rather than
  reusing exported IDs, since reusing them risks colliding with or resurrecting IDs the
  `AUTOINCREMENT` guarantee has already retired.
- **Tension:** don't start this until export has shipped and been used at least once.

### 3. PostgreSQL support (for Vercel deployment)
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
    export/import — ties into the JSON export (shipped) and JSON import (#2, not yet built) ideas.
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
