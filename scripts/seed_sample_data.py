"""Seed the local kanban board with a varied set of sample tasks for demoing/testing.

Creates tasks through the real HTTP API (so normal validation runs), then backdates a
few tasks' `updated_at` directly through the storage layer -- the only way to do that,
since no API mutates `updated_at` (it's always stamped with "now" on every write).

Also seeds a small sprint history: Sprint 1 starts, several tasks are completed, and
the sprint is closed (rolling everything still open into Sprint 2, which stays active
with one completion of its own) -- so the board demos both the Past Sprints view and
the current-sprint Done filtering out of the box.

Usage: start the dev server first (`python -m uvicorn backend.main:app --reload`),
then run `python -m scripts.seed_sample_data` from the repo root. Run it against a
blank database (delete `.kanban_data/kanban.db` first) since it always starts a fresh
Sprint 1 unconditionally.

Not idempotent: re-running against a board that already has tasks with these titles
will fail on the very first request with a 409 (duplicate title in that column).
"""

from datetime import date, datetime, timedelta, timezone

import httpx

from backend import storage

API = "http://localhost:8000/api"


def _today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def _future(days: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(days=days)).date().isoformat()


def _past(days: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).date().isoformat()


SPRINT_1 = {"name": "Sprint 1", "duration_weeks": 2}
SPRINT_2 = {"name": "Sprint 2", "duration_weeks": 2}

# (column, title, description, priority, due_date)
TASKS = [
    ("To Do", "Design login page mockups", "High-fidelity mockups for the new login flow.", "Medium", _future(10)),
    ("To Do", "Set up CI pipeline", "Add GitHub Actions workflow for lint + pytest.", "High", None),
    ("In Progress", "Fix flaky logout test", "test_logout intermittently times out in CI.", "Urgent", _today()),
    ("In Progress", "Refactor auth middleware", "Split session handling out of the auth middleware.", "High", None),
    ("To Do", "Write API docs for tasks endpoint", "Document /api/tasks request/response shapes.", "Low", None),
    ("In Progress", "Investigate memory leak in worker", "RSS grows unbounded after ~2h under load.", "Urgent", None),
    ("To Do", "Add pagination to trash view", "Trash panel loads all rows at once; paginate.", "Medium", None),
    ("To Do", "Upgrade SQLAlchemy to 2.1", "Check for deprecated Query-style usage first.", "Low", _past(5)),
    ("In Review", "Design system: button component audit", "Confirm all button variants match Figma.", "Medium", None),
    ("To Do", "Spike: websocket notifications", "Feasibility spike, not a commitment to build.", "High", None),
    ("In Review", "Fix due-date timezone bug", "Naive datetimes from SQLite need UTC reattached.", "Urgent", None),
    ("Done", "Onboard new dev environment doc", "README section for first-time setup.", "Low", None),
    ("Done", "Release v1.4.0", "Sprint scrum feature release.", "High", None),
    ("To Do", "Cleanup dead code in storage.py", "Remove helpers left over from file-based storage.", "Low", None),
    ("In Progress", "Add rate limiting to API", "Simple in-memory token bucket per IP.", "Medium", _future(14)),
    ("To Do", "Improve empty trash confirmation copy", "Current copy doesn't say how many tasks.", "Low", None),
]

# titles to block, keyed by the blocking task's title -> title of its blocker
BLOCKS = {
    "Investigate memory leak in worker": "Fix flaky logout test",
    "Cleanup dead code in storage.py": "Upgrade SQLAlchemy to 2.1",
}

# title -> list of (subtask title, done)
SUBTASKS = {
    "Set up CI pipeline": [("Add lint job", True), ("Add pytest job", False), ("Add badge to README", False)],
    "Release v1.4.0": [("Tag release", True), ("Publish changelog", True)],
}

# title -> list of note bodies
NOTES = {
    "Fix flaky logout test": ["Repros ~1 in 20 runs, only in CI not locally."],
    "Refactor auth middleware": ["Blocked on deciding session store; discuss in standup."],
}

# title -> days in the past to backdate `updated_at` to, done directly via storage
BACKDATE_DAYS = {
    "Set up CI pipeline": 21,
    "Write API docs for tasks endpoint": 35,
    "Upgrade SQLAlchemy to 2.1": 45,
    "Onboard new dev environment doc": 60,
}

# Titles moved to Done before Sprint 1 ends. "Onboard new dev environment doc" and
# "Release v1.4.0" are created directly into Done above, so they need no move -- a
# task auto-joins whichever sprint is active at creation time, regardless of column.
DONE_DURING_SPRINT_1 = [
    "Design login page mockups",
    "Design system: button component audit",
    "Fix due-date timezone bug",
    "Fix flaky logout test",
]

# Titles moved to Done after Sprint 2 starts, demonstrating this sprint's own progress
# (as opposed to the rolled-over carryover from Sprint 1).
DONE_DURING_SPRINT_2 = [
    "Add rate limiting to API",
]


def main() -> None:
    with httpx.Client(base_url=API) as client:
        resp = client.post("/sprints/start", json=SPRINT_1)
        resp.raise_for_status()
        sprint_1_id = resp.json()["id"]
        print(f"Started sprint: {resp.json()['name']}")

        title_to_id: dict[str, str] = {}
        for column, title, description, priority, due_date in TASKS:
            resp = client.post(
                "/tasks",
                json={
                    "column": column,
                    "title": title,
                    "description": description,
                    "priority": priority,
                    "due_date": due_date,
                },
            )
            resp.raise_for_status()
            task_id = resp.json()["id"]
            title_to_id[title] = task_id
            print(f"Created {task_id}: {title} [{column}/{priority}]")

        for blocked_title, blocker_title in BLOCKS.items():
            task_id = title_to_id[blocked_title]
            blocker_id = title_to_id[blocker_title]
            resp = client.put(f"/tasks/{task_id}/blocked-by", json={"blocked_by": blocker_id})
            resp.raise_for_status()
            print(f"{task_id} ({blocked_title}) now blocked by {blocker_id} ({blocker_title})")

        for title, subtasks in SUBTASKS.items():
            task_id = title_to_id[title]
            for sub_title, done in subtasks:
                resp = client.post(f"/tasks/{task_id}/subtasks", json={"title": sub_title})
                resp.raise_for_status()
                if done:
                    subtask_id = resp.json()["id"]
                    client.put(f"/tasks/{task_id}/subtasks/{subtask_id}", json={"done": True}).raise_for_status()
            print(f"{task_id} ({title}): added {len(subtasks)} subtasks")

        for title, notes in NOTES.items():
            task_id = title_to_id[title]
            for body in notes:
                client.post(f"/tasks/{task_id}/notes", json={"body": body}).raise_for_status()
            print(f"{task_id} ({title}): added {len(notes)} note(s)")

        for title in DONE_DURING_SPRINT_1:
            task_id = title_to_id[title]
            client.put(f"/tasks/{task_id}/move", json={"to_column": "Done"}).raise_for_status()
        print(f"Completed {len(DONE_DURING_SPRINT_1)} more task(s) before ending Sprint 1")

        resp = client.post("/sprints/end", json=SPRINT_2)
        resp.raise_for_status()
        print(f"Ended Sprint 1, started {resp.json()['name']}")

        for title in DONE_DURING_SPRINT_2:
            task_id = title_to_id[title]
            client.put(f"/tasks/{task_id}/move", json={"to_column": "Done"}).raise_for_status()
        print(f"Completed {len(DONE_DURING_SPRINT_2)} task(s) during Sprint 2")

    # Backdating `updated_at` has no API surface -- go straight through storage.
    with storage._session() as session:
        for title, days_ago in BACKDATE_DAYS.items():
            task_id = title_to_id[title]
            pk = storage._parse_id(task_id)
            task = session.get(storage.Task, pk)
            task.updated_at = datetime.now(timezone.utc) - timedelta(days=days_ago)
        session.commit()
    print(f"Backdated updated_at on {len(BACKDATE_DAYS)} tasks via storage layer")

    # Sprint 1 and Sprint 2 both get created "now" (seconds apart) by the flow above, which
    # would otherwise leave Sprint 1 with an end_date in the future and overlapping Sprint 2's
    # range entirely. Backdate Sprint 1 by its own duration so it reads as a real, already-
    # finished sprint that Sprint 2 picks up right where it left off (end_date == Sprint 2's
    # start_date) -- has no API surface either, same reasoning as updated_at above.
    with storage._session() as session:
        sprint_1 = session.get(storage.Sprint, sprint_1_id)
        sprint_1.start_date = date.today() - timedelta(weeks=SPRINT_1["duration_weeks"])
        sprint_1.end_date = date.today()
        session.commit()
    print("Backdated Sprint 1's start/end dates so it no longer overlaps Sprint 2")

    print(f"\nSeeded {len(TASKS)} tasks total across Sprint 1 (closed) and Sprint 2 (active).")


if __name__ == "__main__":
    main()
