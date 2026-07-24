from functools import wraps
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from typing import Optional

from backend import storage
from backend.schemas import (
    ArchivedTaskOut,
    ArchiveAllResponse,
    BlockedByResponse,
    DueDateResponse,
    EmptyTrashResponse,
    ExportOut,
    IdResponse,
    ImportResult,
    NoteCreate,
    NoteOut,
    PastSprintOut,
    PriorityResponse,
    RestoreResponse,
    SprintEnd,
    SprintOut,
    SprintPlan,
    SprintStart,
    SubtaskCreate,
    SubtaskOut,
    SubtaskUpdate,
    TaskBlockedByUpdate,
    TaskCreate,
    TaskDueDateUpdate,
    TaskMove,
    TaskOut,
    TaskPriorityUpdate,
    TrashedTaskOut,
)

BASE_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = BASE_DIR / "frontend"

app = FastAPI(title="CanBan")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Storage functions raise plain exception types; every endpoint that calls them
# maps the same three to HTTP status codes. This decorator centralizes that
# mapping so handlers can call storage directly and just return. Ordered
# most-specific first so an isinstance match picks the right code (the three
# types are unrelated in practice, so order only guards against subclasses).
_EXC_STATUS = (
    (FileNotFoundError, 404),
    (FileExistsError, 409),
    (ValueError, 400),
)


def storage_errors(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except tuple(exc_type for exc_type, _ in _EXC_STATUS) as exc:
            status = next(code for exc_type, code in _EXC_STATUS if isinstance(exc, exc_type))
            raise HTTPException(status_code=status, detail=str(exc)) from exc

    return wrapper


@app.get("/api/status")
def get_status():
    return {"status": "ok"}


@app.get("/api/tasks", response_model=dict[str, list[TaskOut]])
def list_tasks():
    return storage.get_all_boards()


@app.post("/api/tasks", status_code=201, response_model=IdResponse)
@storage_errors
def create_task(task: TaskCreate):
    task_id = storage.add_task(
        task.column,
        task.title,
        task.description,
        task.blocked_by,
        task.priority,
        task.due_date,
    )
    return {"id": task_id}


@app.put("/api/tasks/{task_id}/priority", response_model=PriorityResponse)
@storage_errors
def set_priority(task_id: str, body: TaskPriorityUpdate):
    storage.update_task(task_id, new_priority=body.priority)
    return {"id": task_id, "priority": body.priority}


@app.put("/api/tasks/{task_id}/move", response_model=IdResponse)
@storage_errors
def move_task(task_id: str, move: TaskMove):
    storage.move_task(task_id, move.to_column)
    return {"id": task_id}


@app.put("/api/tasks/{task_id}/blocked-by", response_model=BlockedByResponse)
@storage_errors
def set_blocked_by(task_id: str, body: TaskBlockedByUpdate):
    storage.set_blocked_by(task_id, body.blocked_by)
    return {"id": task_id, "blocked_by": body.blocked_by}


@app.put("/api/tasks/{task_id}/due-date", response_model=DueDateResponse)
@storage_errors
def set_due_date(task_id: str, body: TaskDueDateUpdate):
    storage.set_due_date(task_id, body.due_date)
    return {"id": task_id, "due_date": body.due_date}


@app.delete("/api/tasks/{task_id}", status_code=204)
@storage_errors
def delete_task(task_id: str):
    storage.delete_task(task_id)


@app.get("/api/tasks/{task_id}/subtasks", response_model=list[SubtaskOut])
@storage_errors
def list_subtasks(task_id: str):
    return storage.get_subtasks(task_id)


@app.post("/api/tasks/{task_id}/subtasks", status_code=201, response_model=SubtaskOut)
@storage_errors
def create_subtask(task_id: str, body: SubtaskCreate):
    return storage.add_subtask(task_id, body.title)


@app.put("/api/tasks/{task_id}/subtasks/{subtask_id}", response_model=SubtaskOut)
@storage_errors
def update_subtask(task_id: str, subtask_id: int, body: SubtaskUpdate):
    return storage.update_subtask(task_id, subtask_id, body.title, body.done)


@app.delete("/api/tasks/{task_id}/subtasks/{subtask_id}", status_code=204)
@storage_errors
def delete_subtask(task_id: str, subtask_id: int):
    storage.delete_subtask(task_id, subtask_id)


@app.get("/api/tasks/{task_id}/notes", response_model=list[NoteOut])
@storage_errors
def list_notes(task_id: str):
    return storage.get_notes(task_id)


@app.post("/api/tasks/{task_id}/notes", status_code=201, response_model=NoteOut)
@storage_errors
def create_note(task_id: str, body: NoteCreate):
    return storage.add_note(task_id, body.body)


@app.post("/api/tasks/{task_id}/archive", response_model=IdResponse)
@storage_errors
def archive_task(task_id: str):
    storage.archive_task(task_id)
    return {"id": task_id}


@app.post("/api/tasks/archive-done", response_model=ArchiveAllResponse)
def archive_all_done():
    count = storage.archive_all_done()
    return {"archived": count}


@app.get("/api/trash", response_model=list[TrashedTaskOut])
def list_trash():
    return storage.get_trash()


@app.post("/api/trash/{task_id}/restore", response_model=RestoreResponse)
@storage_errors
def restore_task(task_id: str):
    column = storage.restore_task(task_id)
    return {"id": task_id, "column": column}


@app.delete("/api/trash/{task_id}", status_code=204)
@storage_errors
def permanent_delete_task(task_id: str):
    storage.permanent_delete_task(task_id)


@app.delete("/api/trash", response_model=EmptyTrashResponse)
def empty_trash():
    count = storage.empty_trash()
    return {"deleted": count}


@app.get("/api/archive", response_model=list[ArchivedTaskOut])
def list_archive():
    return storage.get_archive()


@app.post("/api/archive/{task_id}/unarchive", response_model=IdResponse)
@storage_errors
def unarchive_task(task_id: str):
    storage.unarchive_task(task_id)
    return {"id": task_id}


@app.get("/api/export", response_model=ExportOut)
def export_data():
    boards = storage.get_all_boards()
    tasks = {
        column: [
            {
                **task,
                "subtasks": storage.get_subtasks(task["id"]),
                "notes": storage.get_notes(task["id"]),
            }
            for task in column_tasks
        ]
        for column, column_tasks in boards.items()
    }
    return {"tasks": tasks, "sprints": storage.get_all_sprints()}


@app.post("/api/import", response_model=ImportResult)
@storage_errors
def import_data(body: ExportOut):
    return storage.import_data(body.model_dump())


@app.post("/api/sprints/start", response_model=SprintOut)
@storage_errors
def start_sprint(body: SprintStart):
    return storage.start_sprint(body.name, body.duration_weeks)


@app.post("/api/sprints/end", response_model=SprintOut)
@storage_errors
def end_sprint(body: SprintEnd):
    return storage.end_sprint(body.name, body.duration_weeks)


@app.get("/api/sprints/active", response_model=Optional[SprintOut])
def get_active_sprint():
    return storage.get_active_sprint()


@app.post("/api/sprints/plan", response_model=SprintOut)
@storage_errors
def plan_next_sprint(body: SprintPlan):
    return storage.plan_next_sprint(body.name, body.duration_weeks)


@app.get("/api/sprints/planned", response_model=Optional[SprintOut])
def get_planned_sprint():
    return storage.get_planned_sprint()


@app.get("/api/sprints", response_model=list[PastSprintOut])
def list_past_sprints():
    return storage.get_past_sprints()


app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
