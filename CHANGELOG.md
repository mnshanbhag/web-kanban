# Changelog

Compact, shipped-feature history for the Kanban board. Newest first. For still-open ideas, see
`FEATURE_IDEAS.md`; for current architecture/behavior, see `CLAUDE.md`.

### JSON import (manual backup, restore) — 2026-07-20
`POST /api/import` restores a previously-exported JSON file additively (never wipe-and-replace),
remapping every id to a fresh one, importing sprints before tasks (two-pass, to resolve
`blocked_by` references), and preserving original timestamps rather than resetting them to "now".
Shipped on `feature_json_import`. Same branch revised the JSON export below to include
subtasks/notes/sprints (which had gone stale) and drop trash from the response.

### Sprint timeline view (last / current / next) — 2026-07-14
Shows last/current/next sprint panels at once instead of just a current banner: last and next are
collapsed `<details>` by default, a new `Sprint.status == "planned"` value lets you queue up the
next sprint's name/duration ahead of time, and `end_sprint` promotes a queued sprint straight to
active if one exists. Shipped on `feature_sprint_timeline_view` (branched from
`feature_past_sprints_view`, which is redundant as a result).

### Past sprints view — 2026-07-14
`GET /api/sprints` returns every closed sprint (most-recently-closed first) annotated with its
completed-task summary. A read-only "Past Sprints" panel (FAB + modal) lists them. Shipped on
`feature_past_sprints_view`, which also added the `.sprint-board-wrap` box around the current
sprint banner + board, and fixed the Done column to scope to the active sprint.

### JSON export (manual backup) — 2026-07-13
A "download backup" button dumping active tasks — each with its real `TaskSubtask`/`TaskNote`
rows — plus all sprints, as JSON. `GET /api/export`, no new table. Shipped on
`feature_json_export`.

### Scrum sprints — 2026-07-13
A lightweight, optional time-boxing layer over the continuous board: start a named sprint with a
fixed duration, with a banner showing name/date range/days-remaining and Start/End Sprint
controls. Ending a sprint always transitions directly into the next one (no gap where the board
has no active sprint). Shipped on `feature_scrum_sprints`.

### Per-task activity log (append-only notes) — 2026-07-13
A timestamped list of freeform notes on a task, separate from the single mutable `description`.
Notes survive trash/restore and are never edited or deleted once added. Shipped on
`feature_activity_log`.

### "Updated X ago" / activity recency — 2026-07-13
An `updated_at` column bumped by every content-mutating storage function, surfaced on cards via
the existing `formatRelativeTime`. Shipped on `feature_updated_at`.

### Subtask checklists — 2026-07-13
A small ordered checklist of items within a task, shown as a `3/5` progress badge on the card and
edited in the detail modal. Completion is purely manual/advisory. Shipped on
`feature_subtask_checklists`.

### Search / filter bar — 2026-07-09
Client-side text filter across title/description, plus quick filters (priority, blocked-only), in
a toolbar under the header — pure frontend filtering of the already-fetched board, no new
endpoint. Shipped on `feature_search_filter`.

### WIP limit warning per column — 2026-07-09
Optional per-column WIP cap, editable inline in the column header and persisted in
`localStorage`; purely advisory, no backend change. Shipped on `feature_wip_limits`.

### Due dates with overdue indication — 2026-07-08
Nullable `due_date` on tasks with an "Overdue" badge on cards past due (suppressed for Done).
Shipped on `feature_due_dates`.
