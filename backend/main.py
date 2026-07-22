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


@app.get("/api/status")
def get_status():
    return {"status": "ok"}


@app.get("/api/tasks", response_model=dict[str, list[TaskOut]])
def list_tasks():
    return storage.get_all_boards()


@app.post("/api/tasks", status_code=201, response_model=IdResponse)
def create_task(task: TaskCreate):
    try:
        task_id = storage.add_task(
            task.column,
            task.title,
            task.description,
            task.blocked_by,
            task.priority,
            task.due_date,
        )
    except FileExistsError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"id": task_id}


@app.put("/api/tasks/{task_id}/priority", response_model=PriorityResponse)
def set_priority(task_id: str, body: TaskPriorityUpdate):
    try:
        storage.update_task(task_id, new_priority=body.priority)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"id": task_id, "priority": body.priority}


@app.put("/api/tasks/{task_id}/move", response_model=IdResponse)
def move_task(task_id: str, move: TaskMove):
    try:
        storage.move_task(task_id, move.to_column)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except FileExistsError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"id": task_id}


@app.put("/api/tasks/{task_id}/blocked-by", response_model=BlockedByResponse)
def set_blocked_by(task_id: str, body: TaskBlockedByUpdate):
    try:
        storage.set_blocked_by(task_id, body.blocked_by)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"id": task_id, "blocked_by": body.blocked_by}


@app.put("/api/tasks/{task_id}/due-date", response_model=DueDateResponse)
def set_due_date(task_id: str, body: TaskDueDateUpdate):
    try:
        storage.set_due_date(task_id, body.due_date)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"id": task_id, "due_date": body.due_date}


@app.delete("/api/tasks/{task_id}", status_code=204)
def delete_task(task_id: str):
    try:
        storage.delete_task(task_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/tasks/{task_id}/subtasks", response_model=list[SubtaskOut])
def list_subtasks(task_id: str):
    try:
        return storage.get_subtasks(task_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/tasks/{task_id}/subtasks", status_code=201, response_model=SubtaskOut)
def create_subtask(task_id: str, body: SubtaskCreate):
    try:
        return storage.add_subtask(task_id, body.title)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.put("/api/tasks/{task_id}/subtasks/{subtask_id}", response_model=SubtaskOut)
def update_subtask(task_id: str, subtask_id: int, body: SubtaskUpdate):
    try:
        return storage.update_subtask(task_id, subtask_id, body.title, body.done)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.delete("/api/tasks/{task_id}/subtasks/{subtask_id}", status_code=204)
def delete_subtask(task_id: str, subtask_id: int):
    try:
        storage.delete_subtask(task_id, subtask_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/tasks/{task_id}/notes", response_model=list[NoteOut])
def list_notes(task_id: str):
    try:
        return storage.get_notes(task_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/tasks/{task_id}/notes", status_code=201, response_model=NoteOut)
def create_note(task_id: str, body: NoteCreate):
    try:
        return storage.add_note(task_id, body.body)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/tasks/{task_id}/archive", response_model=IdResponse)
def archive_task(task_id: str):
    try:
        storage.archive_task(task_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"id": task_id}


@app.post("/api/tasks/archive-done", response_model=ArchiveAllResponse)
def archive_all_done():
    count = storage.archive_all_done()
    return {"archived": count}


@app.get("/api/trash", response_model=list[TrashedTaskOut])
def list_trash():
    return storage.get_trash()


@app.post("/api/trash/{task_id}/restore", response_model=RestoreResponse)
def restore_task(task_id: str):
    try:
        column = storage.restore_task(task_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except FileExistsError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"id": task_id, "column": column}


@app.delete("/api/trash/{task_id}", status_code=204)
def permanent_delete_task(task_id: str):
    try:
        storage.permanent_delete_task(task_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.delete("/api/trash", response_model=EmptyTrashResponse)
def empty_trash():
    count = storage.empty_trash()
    return {"deleted": count}


@app.get("/api/archive", response_model=list[ArchivedTaskOut])
def list_archive():
    return storage.get_archive()


@app.post("/api/archive/{task_id}/unarchive", response_model=IdResponse)
def unarchive_task(task_id: str):
    try:
        storage.unarchive_task(task_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except FileExistsError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
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
def import_data(body: ExportOut):
    try:
        return storage.import_data(body.model_dump())
    except FileExistsError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/sprints/start", response_model=SprintOut)
def start_sprint(body: SprintStart):
    try:
        return storage.start_sprint(body.name, body.duration_weeks)
    except FileExistsError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/sprints/end", response_model=SprintOut)
def end_sprint(body: SprintEnd):
    try:
        return storage.end_sprint(body.name, body.duration_weeks)
    except FileExistsError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/sprints/active", response_model=Optional[SprintOut])
def get_active_sprint():
    return storage.get_active_sprint()


@app.post("/api/sprints/plan", response_model=SprintOut)
def plan_next_sprint(body: SprintPlan):
    try:
        return storage.plan_next_sprint(body.name, body.duration_weeks)
    except FileExistsError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/sprints/planned", response_model=Optional[SprintOut])
def get_planned_sprint():
    return storage.get_planned_sprint()


@app.get("/api/sprints", response_model=list[PastSprintOut])
def list_past_sprints():
    return storage.get_past_sprints()


app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
