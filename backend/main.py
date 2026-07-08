from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend import storage
from backend.schemas import (
    BlockedByResponse,
    EmptyTrashResponse,
    IdResponse,
    PriorityResponse,
    RestoreResponse,
    TaskBlockedByUpdate,
    TaskCreate,
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
            task.column, task.title, task.description, task.blocked_by, task.priority
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


@app.delete("/api/tasks/{task_id}", status_code=204)
def delete_task(task_id: str):
    try:
        storage.delete_task(task_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


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


app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
