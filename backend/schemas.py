from typing import Optional

from pydantic import BaseModel

from backend import storage


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


class TaskOut(BaseModel):
    id: str
    title: str
    description: str
    priority: str
    blocked_by: Optional[str] = None
    blocks: list[str] = []


class TrashedTaskOut(BaseModel):
    id: str
    title: str
    description: str
    priority: str
    deleted_from: str
    deleted_at: str


class IdResponse(BaseModel):
    id: str


class PriorityResponse(BaseModel):
    id: str
    priority: str


class RestoreResponse(BaseModel):
    id: str
    column: str


class EmptyTrashResponse(BaseModel):
    deleted: int
