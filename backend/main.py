from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from backend import storage

BASE_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = BASE_DIR / "frontend"

app = FastAPI(title="Kanban App")

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


class TaskMove(BaseModel):
    to_column: str


def _make_task_id(column: str, title: str) -> str:
    return f"{storage.sanitize_name(column)}::{storage.sanitize_name(title)}"


def _parse_task_id(task_id: str) -> tuple[str, str]:
    column, sep, title = task_id.partition("::")
    if not sep:
        raise HTTPException(status_code=400, detail="Invalid task_id")
    return column, title


@app.get("/api/status")
def get_status():
    return {"status": "ok"}


@app.get("/api/tasks")
def list_tasks():
    board = storage.get_all_boards()
    return {
        column: [{**task, "id": _make_task_id(column, task["title"])} for task in tasks]
        for column, tasks in board.items()
    }


@app.post("/api/tasks", status_code=201)
def create_task(task: TaskCreate):
    try:
        storage.add_task(task.column, task.title, task.description)
    except FileExistsError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"id": _make_task_id(task.column, task.title)}


@app.put("/api/tasks/{task_id}/move")
def move_task(task_id: str, move: TaskMove):
    column, title = _parse_task_id(task_id)
    try:
        storage.move_task(title, column, move.to_column)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except FileExistsError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"id": _make_task_id(move.to_column, title)}


@app.delete("/api/tasks/{task_id}", status_code=204)
def delete_task(task_id: str):
    column, title = _parse_task_id(task_id)
    try:
        storage.delete_task(column, title)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
