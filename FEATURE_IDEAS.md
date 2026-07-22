# Feature ideas backlog

Maintained by the `feature-ideator` subagent. Each entry is a proposed idea, not a commitment —
pick one and hand it to `feature-implementer` to actually build it.

**Status key:** 🆕 proposed · 🚧 in progress · ✅ shipped · ❌ shelved

Shipped features are moved to `CHANGELOG.md` in compact form once they land — this file only
tracks what's still actionable.

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

### 3. Bulk actions via multi-select
Select several cards at once (a toggleable "select mode") and apply one action — move to a
column, delete, set priority — to all of them in one step.
- **Why:** growing task counts across sprints make one-at-a-time cleanup tedious — e.g. moving a
  batch of stale To Do cards into the current sprint's Done column, or clearing several stragglers
  to In Progress at once. This is still a single local user managing their own board, so it stays
  scoped to the board they already see, not a team/permissions feature.
- **Scope:** medium — frontend: a toolbar toggle for "select mode" that reveals a small checkbox
  on each card only while active (cards stay visually unchanged the rest of the time), plus a
  bulk-action bar once ≥1 card is selected. Backend: could reuse the existing single-task
  endpoints in a loop (simplest, no new endpoints) rather than adding bulk-specific ones — board
  sizes here are small enough that sequential round-trips shouldn't matter in practice.
- **Tension:**
  - The card-density decision (see `feedback_card_density` in memory) put editing controls in the
    detail modal, not the card — a select-mode checkbox is a selection control rather than an
    editing one, but it should stay strictly opt-in/hidden-until-toggled to stay consistent with
    that spirit.
  - Bulk moves into Done still need `move_task`'s per-task blocking check (a blocked task can't
    reach Done) and bulk deletes still need `delete_task`'s per-task Done-guard — a mixed selection
    can partially fail, so the UI needs to report per-task success/failure, not one all-or-nothing
    toast.
  - No bulk endpoint exists today anywhere in `main.py` — this would be a new pattern if the
    loop-of-single-calls approach ever proves insufficient and a real bulk endpoint gets added
    later.
- **Tracked as:** #14

### 4. Undo toast for the last action
After moving a card, changing its priority, or blocking/unblocking it, a toast appears for a few
seconds with an "Undo" button that reverses just that one change.
- **Why:** drag-and-drop boards are prone to misclicks/mis-drops (wrong column, fat-fingered
  priority pill), and this is a single local user with nobody else to fix it for them — right now
  the only recovery is manually redoing the opposite action by hand. Delete already has a safety
  net (the recycle bin); no other mutation does.
- **Scope:** small-medium, frontend-only — track just the single most recent mutation (task id,
  field, previous value) in memory, show a dismissible toast alongside the existing `showError`
  toast machinery, and call the same setter (`moveTask`/`setPriority`/`setBlockedBy`/`setDueDate`)
  with the prior value on click. No new backend endpoints needed: every mutation already has a
  corresponding "set to X" endpoint, so undo is just "set back to what it was."
- **Tension:**
  - Moving a task *to* Done can cascade-clear `blocked_by_id` on every task that pointed at it
    (the Done-cascade rule) — undoing that move (back out of Done) doesn't un-cascade those
    dependents' cleared blocks, so undo can't promise a full state restore in that one case.
    Either scope undo to just the moved task's own fields and say so in the toast copy, or exclude
    Done-involved moves from the undo affordance entirely if that's judged too surprising.
  - Keep this to a single last-action slot, not an undo stack/history UI, matching the "keep it
    lean" pattern already used elsewhere (e.g. WIP limits' localStorage-only persistence) — and no
    keyboard shortcut for triggering it, since keyboard shortcuts were already explicitly shelved
    for lack of tangible benefit.
  - Delete/restore already has its own safety net (the trash) — don't fold delete into this
    mechanism too, that'd be a second, confusing path to the same recovery.
- **Tracked as:** #15

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
