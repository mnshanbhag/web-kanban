# Feature ideas backlog

Maintained by the `feature-ideator` subagent. Each entry is a proposed idea, not a commitment —
pick one and hand it to `feature-implementer` to actually build it.

**Status key:** 🆕 proposed · 🚧 in progress · ✅ shipped · ❌ shelved

---

## ✅ Shipped

### Due dates with overdue indication
Nullable `due_date` on tasks with an "Overdue" badge on cards past due (suppressed for Done).
Shipped on `feature_due_dates` (2026-07-08).

---

## 🆕 Proposed

### 1. Manual card ordering within a column
Let a card be dragged to a specific position within a column, not just between columns —
persisted across reloads.
- **Why:** `get_all_boards` currently sorts tasks alphabetically by title within a column; there's
  no way to say "this one's next." Biggest real gap versus a usable personal Kanban tool.
- **Scope:** medium — storage (a sortable `position` column + reorder logic), API (new endpoint),
  frontend (real insertion-point detection on drop, not just target-column detection).
- **Tension:** decide what position a restored-from-trash task gets (simplest: append to end).

### 2. Search / filter bar
Client-side text filter across title/description, plus quick filters (priority, blocked-only).
- **Why:** cheap, high value — the full board is already fetched in one call, so this is pure
  frontend filtering with no new endpoint needed.
- **Scope:** small, frontend-only.
- **Tension:** none.

### 3. Tags / labels
Free-form labels per task (e.g. "bug", "chore"), shown as chips, filterable.
- **Why:** priority + column cover urgency/status but not categorization by kind of work.
- **Scope:** small if a single comma-separated string column on `Task`; medium-large if a proper
  many-to-many (`tags` + `task_tags` tables).
- **Tension:** tag *editing* should live in the detail modal only, matching the deliberate
  card-density decision already made for blocking (see `feedback_card_density` in memory).

### 4. Per-task activity log (append-only notes)
A timestamped list of freeform notes on a task, separate from the single mutable `description`.
- **Why:** `description` gets overwritten on every edit — no way to keep a running history of
  what happened on a long-lived task.
- **Scope:** medium-large — new `TaskNote` table (FK `ondelete="CASCADE"`), new endpoints, UI
  inside the existing detail modal.
- **Tension:** `created_at` needs the same `_utc_isoformat()` tzinfo treatment as `deleted_at`/
  `due_date`. Decide whether notes survive soft-delete/restore (they should, same as the task row).

### 5. "Updated X ago" / activity recency
An `updated_at` column touched on every mutation, surfaced on cards via the existing
`formatRelativeTime` (already used for the trash panel).
- **Why:** at-a-glance staleness signal — e.g. "this In Progress card hasn't moved in 9 days."
- **Scope:** small-medium — touch it in every mutating storage function (`update_task`,
  `set_blocked_by`, `move_task`, `set_due_date`, ...).
- **Tension:** same tzinfo gotcha as above. Easy to miss a mutation path (e.g. the Done-cascade's
  dependent-clearing loop in `move_task`) — decide upfront whether that counts as "updating."

### 6. WIP limit warning per column
An optional soft cap (e.g. on "In Progress") that visually flags the column header when exceeded
— a nudge, not a block.
- **Why:** WIP limits are core Kanban discipline; a *soft* warning fits a single-user tool better
  than a server-enforced rule.
- **Scope:** small — could be pure frontend/localStorage, no backend change needed.
- **Tension:** must stay advisory. Don't implement it as a server-side invariant like the
  blocking rules — this is a personal-workflow nudge, not a business rule.

### 7. Keyboard shortcuts / quick-add
A shortcut to open "new task," `/` to focus search (pairs with #2), arrow-key card navigation.
Extends the existing `Escape`-key handler pattern in `app.js`.
- **Why:** cheap ergonomics win for a tool used many times a day by one person.
- **Scope:** small, frontend-only.
- **Tension:** must not hijack keys while a modal input/textarea has focus.

### 8. JSON export / import (manual backup)
A "download backup" button dumping all tasks (active + trashed) as JSON; matching import.
- **Why:** the whole app is one local SQLite file with no sync or versioned backups.
- **Scope:** small for export (wraps existing `get_all_boards`/`get_trash`); import is the harder
  half.
- **Tension:** import must mint *new* IDs and remap `blocked_by` references rather than reusing
  exported IDs — reusing them risks colliding with or resurrecting IDs the `AUTOINCREMENT`
  guarantee has already retired. Consider shipping export first, treating import as a separate,
  carefully-scoped follow-up.

### 9. Archive Done tasks separately from trash
Auto-hide (not delete) Done tasks older than N days, with a way to view/unarchive them.
- **Why:** long-lived boards accumulate Done clutter that isn't "deleted," just old.
- **Scope:** medium — a third state (`archived_at`) alongside active/trashed.
- **Tension:** must not get confused with the existing `deleted_at IS NULL` filtering or the
  `blocks` backref computation — needs care reading how those interact before implementing.
