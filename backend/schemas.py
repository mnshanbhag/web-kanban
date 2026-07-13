from typing import Optional

from pydantic import BaseModel

from backend import storage


class TaskCreate(BaseModel):
    column: str
    title: str
    description: str = ""
    blocked_by: Optional[str] = None
    priority: str = storage.DEFAULT_PRIORITY
    due_date: Optional[str] = None


class TaskMove(BaseModel):
    to_column: str


class TaskPriorityUpdate(BaseModel):
    priority: str


class TaskBlockedByUpdate(BaseModel):
    blocked_by: Optional[str] = None


class TaskDueDateUpdate(BaseModel):
    due_date: Optional[str] = None


class SubtaskCreate(BaseModel):
    title: str


class SubtaskUpdate(BaseModel):
    title: Optional[str] = None
    done: Optional[bool] = None


class SubtaskOut(BaseModel):
    id: int
    title: str
    done: bool
    position: int


class TaskOut(BaseModel):
    id: str
    title: str
    description: str
    priority: str
    blocked_by: Optional[str] = None
    blocks: list[str] = []
    due_date: Optional[str] = None
    subtask_total: int = 0
    subtask_done: int = 0
    updated_at: Optional[str] = None


class TrashedTaskOut(BaseModel):
    id: str
    title: str
    description: str
    priority: str
    deleted_from: str
    deleted_at: str


class ArchivedTaskOut(BaseModel):
    id: str
    title: str
    description: str
    priority: str
    archived_at: str


class IdResponse(BaseModel):
    id: str


class PriorityResponse(BaseModel):
    id: str
    priority: str


class BlockedByResponse(BaseModel):
    id: str
    blocked_by: Optional[str] = None


class DueDateResponse(BaseModel):
    id: str
    due_date: Optional[str] = None


class RestoreResponse(BaseModel):
    id: str
    column: str


class EmptyTrashResponse(BaseModel):
    deleted: int


class ArchiveAllResponse(BaseModel):
    archived: int


class ExportOut(BaseModel):
    tasks: dict[str, list[TaskOut]]
    trash: list[TrashedTaskOut]


class SprintStart(BaseModel):
    name: str
    duration_weeks: int


class SprintOut(BaseModel):
    id: int
    name: str
    start_date: str
    end_date: str
    status: str
    closed_at: Optional[str] = None
