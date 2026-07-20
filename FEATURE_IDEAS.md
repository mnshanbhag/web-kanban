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

**Revised (2026-07-20):** an audit against the live schema ahead of building JSON import found
the export had gone stale — several features shipped since (Scrum sprints, subtask checklists,
the per-task activity log) were never reflected in it. `trash` is now dropped from the response
entirely (exported trashed tasks are out of scope for round-tripping via import). Each exported
task now carries its real `TaskSubtask`/`TaskNote` rows, not just the `subtask_total`/
`subtask_done` counts `TaskOut` already exposed — a new `ExportTaskOut(TaskOut)` schema adds
`subtasks: list[SubtaskOut]`/`notes: list[NoteOut]`, built per-task in the export endpoint by
reusing `storage.get_subtasks()`/`storage.get_notes()` rather than widening the base `TaskOut`
(which every board fetch uses — that would've added N+1 queries there for no reason). The
`Sprint` table itself is now exported too: a task's `sprint_id` rode along on `TaskOut` already,
but with no sprint rows in the export it pointed at nothing on import into an empty/different
database, so a new `storage.get_all_sprints()` (the first storage function returning every sprint
regardless of status — `get_active_sprint`/`get_planned_sprint`/`get_past_sprints()` each return
only one status) is exposed as `ExportOut.sprints`. Archive stays excluded, unchanged (still
shelved behind `ARCHIVE_ENABLED = false`, see Shelved section). Revised on `feature_json_import`
(2026-07-20), ahead of building JSON import (below) against this corrected shape.

### JSON import (manual backup, restore)
Import side of the export/import pair — a "Import Backup" button (next to the existing "Download
Backup" one) uploads a previously-exported JSON file and restores it into the live board. New
`POST /api/import`, request body is the same `ExportOut` shape `GET /api/export` produces (reused
directly, no separate schema to keep in sync); `storage.import_data()` does the actual work in one
`_session()` block, mirroring `end_sprint`'s pattern of atomic multi-step work — nothing is
committed until every row validates, so a partial failure (a title collision partway through, say)
leaves nothing persisted. Import is additive (adds to whatever's already in the DB), not a
wipe-and-replace — this app has no "reset the board" operation and doesn't gain one here.

Every id in the file (sprint ids, `"KAN-NN"` task ids) is local to that file and gets remapped to
a freshly-minted id rather than reused, same reasoning as the "IDs are never reused" invariant
elsewhere in this app: reusing an id risks colliding with or resurrecting one `AUTOINCREMENT` has
already retired. Sprints import first (tasks reference them by id), enforcing the same
at-most-one-active/at-most-one-planned invariants `start_sprint`/`plan_next_sprint` already
enforce live — checked across the combination of the file and the live DB, not just within the
file — plus the existing sprint-name-uniqueness check (`_assert_sprint_name_available`). Tasks
import in two passes since a `blocked_by` reference can point at a task appearing later in the
file: pass one creates every task (skipping `add_task`, which would've auto-joined whatever sprint
happens to be active in the *target* DB right now instead of the task's real remapped
`sprint_id`), pass two wires up `blocked_by_id` through the id map built in pass one, rejecting
(400) a reference to a task not present in the import set or already Done, mirroring
`_validate_blocker`'s live rules. The file's `blocks` field is ignored entirely on import, same as
everywhere else in this app — it's a computed backref, never accepted as input. Subtasks/notes
attach to each task's newly-minted id, copying `title`/`done`/`position` and `body`/`created_at`
respectively.

Timestamps (`Task.updated_at`, `TaskNote.created_at`, `Sprint.closed_at`) are preserved from the
file rather than reset to "now" — import is a restore of prior state, not new activity, so cards
should show their real history ("updated 3 days ago"), not look freshly touched by the import
itself. Trashed and archived tasks were never in the export (see the Revised paragraph above), so
there's nothing to import for either. Shipped on `feature_json_import` (2026-07-20), same branch
as the export fix above (no separate merge needed).

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

### Subtask checklists
A small ordered checklist of items within a task (e.g. "Write tests", "Update docs"), shown as a
`3/5` progress badge on the card and edited in the detail modal. New `TaskSubtask` table (FK
`ondelete="CASCADE"` on `Task.id`, plus an ordering column), CRUD endpoints, and detail-modal UI;
`TaskOut` exposes `subtask_total`/`subtask_done` for the card's count badge — the card itself
carries no other subtask UI, keeping the existing card-density decision intact (see
`feedback_card_density` in memory). Completion is purely manual/advisory, same spirit as WIP
limits — not wired into the Done-column invariants or blocking logic. Shipped on
`feature_subtask_checklists` (2026-07-13).

---

## 🚧 In Progress

_Nothing currently in progress._

---

## 🆕 Proposed

### 1. Tags / labels
Free-form labels per task (e.g. "bug", "chore"), shown as chips, filterable.
- **Why:** priority + column cover urgency/status but not categorization by kind of work.
- **Scope:** small if a single comma-separated string column on `Task`; medium-large if a proper
  many-to-many (`tags` + `task_tags` tables).
- **Tension:** tag *editing* should live in the detail modal only, matching the deliberate
  card-density decision already made for blocking (see `feedback_card_density` in memory).

### 2. PostgreSQL support (for Vercel deployment)
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
    export/import — ties into the JSON export/import features (both shipped).
- **Status:** idea only, not scoped down or handed to `feature-implementer` yet — open questions
  above (dual support vs. Postgres-only, Alembic vs. not) need a decision first.

---

## ❌ Shelved

### Archive Done tasks separately from trash
A manual "Archive" action on Done cards (alongside the existing delete button), hiding the task
from the board without touching the trash/soft-delete path. Fully implemented: a third
independent state (`archived_at`) alongside active/trashed — a task can't be both — an archive
panel mirroring the trash panel's UX (Unarchive action), archive/unarchive endpoints, and a bulk
"archive all Done" endpoint, all on `feature_archive_done_tasks` (2026-07-13). Only Done tasks
are archivable, enforced server-side.
- **Why shelved:** the UI entry points (Archive FAB, archive modal, per-card archive button,
  Archive All button) were disabled behind `ARCHIVE_ENABLED = false` in `frontend/app.js` pending
  a redesign, and the redesign never happened — backend and existing archived data are untouched,
  so re-enabling is still a one-line flip if this gets picked back up.
- **Shelved:** 2026-07-17.

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
