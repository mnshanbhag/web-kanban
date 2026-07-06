# Web Kanban

A local Kanban board. FastAPI backend, vanilla JS/HTML/CSS frontend, tasks stored as plain
Markdown files on disk — no database.

## Setup

Requires Python 3.13+.

```
python -m pip install -r requirements.txt
```

For running tests, install dev dependencies instead (this also installs `requirements.txt`):

```
python -m pip install -r requirements-dev.txt
```

## Running the app

```
python -m uvicorn backend.main:app --reload
```

Open http://127.0.0.1:8000 — the backend serves both the API and the static frontend.

## Running tests

```
python -m pytest
```

## How data is stored

Board state lives under `.kanban_data/`, not a database:

```
.kanban_data/
  To Do/
    Write tests.md       <- filename = task title, frontmatter + body = metadata + description
  In Progress/
  Done/
```

Each column is a folder; each task is a `.md` file. Columns and tasks are created on demand —
an empty `.kanban_data/` is a valid, empty board.

Each task file has a small frontmatter block for metadata, followed by the description as plain
text:

```
---
priority: High
---
Task description goes here.
```

`priority` is one of `Low` / `Medium` / `High` / `Urgent`, defaulting to `Medium` if omitted at
creation.

## API

| Method | Path                          | Body                                       | Description                       |
|--------|-------------------------------|-----------------------------------------------|------------------------------------|
| GET    | `/api/status`                 | —                                               | Health check                       |
| GET    | `/api/tasks`                   | —                                               | All columns and their tasks        |
| POST   | `/api/tasks`                    | `{column, title, description?, priority?}`     | Create a task                     |
| PUT    | `/api/tasks/{task_id}/move`     | `{to_column}`                                   | Move a task to another column      |
| PUT    | `/api/tasks/{task_id}/priority` | `{priority}`                                     | Change a task's priority           |
| DELETE | `/api/tasks/{task_id}`          | —                                               | Delete a task                      |

`task_id` is `"<column>::<title>"` (e.g. `"To Do::Write tests"`), returned by `GET`/`POST` and
passed back as-is to `move`/`priority`/`delete`.

`priority` must be one of `Low`, `Medium`, `High`, `Urgent` — the API returns `400` otherwise.
