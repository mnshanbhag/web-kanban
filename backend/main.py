from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from backend import storage

BASE_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = BASE_DIR / "frontend"

app = FastAPI(title="CanBan")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class TaskCreate(BaseModel):
    column: str
    title: str
    description: str = ""
    blocked_by: Optional[str] = None
    priority: str = storage.DEFAULT_PRIORITY


class TaskMove(BaseModel):
    to_column: str
    blocked_by: Optional[str] = None


class TaskPriorityUpdate(BaseModel):
    priority: str


@app.get("/api/status")
def get_status():
    return {"status": "ok"}


@app.get("/api/tasks")
def list_tasks():
    return storage.get_all_boards()


@app.post("/api/tasks", status_code=201)
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


@app.put("/api/tasks/{task_id}/priority")
def set_priority(task_id: str, body: TaskPriorityUpdate):
    try:
        storage.update_task(task_id, new_priority=body.priority)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"id": task_id, "priority": body.priority}


@app.put("/api/tasks/{task_id}/move")
def move_task(task_id: str, move: TaskMove):
    try:
        storage.move_task(task_id, move.to_column, move.blocked_by)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except FileExistsError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"id": task_id}


@app.delete("/api/tasks/{task_id}", status_code=204)
def delete_task(task_id: str):
    try:
        storage.delete_task(task_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/trash")
def list_trash():
    return storage.get_trash()


@app.post("/api/trash/{task_id}/restore")
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


@app.delete("/api/trash")
def empty_trash():
    count = storage.empty_trash()
    return {"deleted": count}


app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
