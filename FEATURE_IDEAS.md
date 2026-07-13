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

### 4. Keyboard shortcuts / quick-add
A shortcut to open "new task," `/` to focus search (pairs with the already-shipped search bar),
arrow-key card navigation. Extends the existing `Escape`-key handler pattern in `app.js`.
- **Why:** cheap ergonomics win for a tool used many times a day by one person.
- **Scope:** small, frontend-only.
- **Tension:** must not hijack keys while a modal input/textarea has focus.

### 5. JSON export / import (manual backup)
A "download backup" button dumping all tasks (active + trashed) as JSON; matching import.
- **Why:** the whole app is one local SQLite file with no sync or versioned backups.
- **Scope:** small for export (wraps existing `get_all_boards`/`get_trash`); import is the harder
  half.
- **Tension:** import must mint *new* IDs and remap `blocked_by` references rather than reusing
  exported IDs — reusing them risks colliding with or resurrecting IDs the `AUTOINCREMENT`
  guarantee has already retired. Consider shipping export first, treating import as a separate,
  carefully-scoped follow-up.

### 6. Archive Done tasks separately from trash
Auto-hide (not delete) Done tasks older than N days, with a way to view/unarchive them.
- **Why:** long-lived boards accumulate Done clutter that isn't "deleted," just old.
- **Scope:** medium — a third state (`archived_at`) alongside active/trashed.
- **Tension:** must not get confused with the existing `deleted_at IS NULL` filtering or the
  `blocks` backref computation — needs care reading how those interact before implementing.

---

## ❌ Shelved

### Manual card ordering within a column
Let a card be dragged to a specific position within a column, not just between columns —
persisted across reloads.
- **Why shelved:** doesn't add any value.
- **Shelved:** 2026-07-08.
