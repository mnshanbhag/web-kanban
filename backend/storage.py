from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, relationship

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / ".kanban_data"

BLOCKED_COLUMN = "Blocked"
PRIORITIES = ("Low", "Medium", "High", "Urgent")
DEFAULT_PRIORITY = "Medium"


class Base(DeclarativeBase):
    pass


class Task(Base):
    __tablename__ = "tasks"
    __table_args__ = {"sqlite_autoincrement": True}

    id = Column(Integer, primary_key=True)
    title = Column(String, nullable=False)
    description = Column(String, nullable=False, default="")
    column = Column(String, nullable=False)
    priority = Column(String, nullable=False, default=DEFAULT_PRIORITY)
    blocked_by_id = Column(Integer, ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True)
    deleted_at = Column(DateTime, nullable=True)

    blocked_by = relationship(
        "Task", remote_side=[id], backref="blocks", foreign_keys=[blocked_by_id]
    )


@event.listens_for(Engine, "connect")
def _enable_foreign_keys(dbapi_connection, _connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def _engine():
    DATA_DIR.mkdir(exist_ok=True)
    engine = create_engine(f"sqlite:///{DATA_DIR / 'kanban.db'}")
    Base.metadata.create_all(engine)
    return engine


def _session() -> Session:
    return Session(_engine())


def _display_id(pk: int) -> str:
    return f"KAN-{pk:02d}"


def _parse_id(task_id: str) -> int:
    if not task_id.startswith("KAN-"):
        raise FileNotFoundError(f"Task '{task_id}' not found")
    try:
        return int(task_id[len("KAN-") :])
    except ValueError:
        raise FileNotFoundError(f"Task '{task_id}' not found") from None


def _validate_priority(priority: str) -> str:
    if priority not in PRIORITIES:
        raise ValueError(f"priority must be one of {', '.join(PRIORITIES)}")
    return priority


def _validate_blocker(session: Session, blocked_by: Optional[str], own_id: Optional[int]) -> int:
    if not blocked_by:
        raise ValueError(f"blocked_by is required when column is '{BLOCKED_COLUMN}'")
    blocker_pk = _parse_id(blocked_by)
    if blocker_pk == own_id:
        raise ValueError("A task cannot block itself")
    blocker = session.get(Task, blocker_pk)
    if blocker is None or blocker.deleted_at is not None:
        raise ValueError(f"Blocker task '{blocked_by}' does not exist")
    return blocker_pk


def _get_active_task(session: Session, task_id: str) -> Task:
    task = session.get(Task, _parse_id(task_id))
    if task is None or task.deleted_at is not None:
        raise FileNotFoundError(f"Task '{task_id}' not found")
    return task


def _get_trashed_task(session: Session, task_id: str) -> Task:
    task = session.get(Task, _parse_id(task_id))
    if task is None or task.deleted_at is None:
        raise FileNotFoundError(f"Task '{task_id}' not found in trash")
    return task


def _assert_title_available(
    session: Session, column: str, title: str, exclude_id: Optional[int] = None
) -> None:
    query = session.query(Task).filter(
        Task.column == column, Task.title == title, Task.deleted_at.is_(None)
    )
    if exclude_id is not None:
        query = query.filter(Task.id != exclude_id)
    if query.first() is not None:
        raise FileExistsError(f"Task '{title}' already exists in column '{column}'")


def _task_to_dict(task: Task) -> dict:
    return {
        "id": _display_id(task.id),
        "title": task.title,
        "description": task.description,
        "priority": task.priority,
        "blocked_by": _display_id(task.blocked_by_id) if task.blocked_by_id else None,
        "blocks": [_display_id(t.id) for t in task.blocks if t.deleted_at is None],
    }


def get_all_boards() -> dict[str, list[dict]]:
    with _session() as session:
        tasks = (
            session.query(Task)
            .filter(Task.deleted_at.is_(None))
            .order_by(Task.column, Task.title)
            .all()
        )
        board: dict[str, list[dict]] = {}
        for task in tasks:
            board.setdefault(task.column, []).append(_task_to_dict(task))
        return board


def add_task(
    column: str,
    title: str,
    description: str = "",
    blocked_by: Optional[str] = None,
    priority: str = DEFAULT_PRIORITY,
) -> str:
    with _session() as session:
        _assert_title_available(session, column, title)

        priority = _validate_priority(priority)

        blocked_by_id = None
        if column == BLOCKED_COLUMN:
            blocked_by_id = _validate_blocker(session, blocked_by, own_id=None)

        task = Task(
            title=title,
            description=description,
            column=column,
            priority=priority,
            blocked_by_id=blocked_by_id,
        )
        session.add(task)
        session.commit()
        return _display_id(task.id)


def update_task(
    task_id: str,
    new_title: Optional[str] = None,
    new_description: Optional[str] = None,
    new_priority: Optional[str] = None,
) -> None:
    with _session() as session:
        task = _get_active_task(session, task_id)

        if new_description is not None:
            task.description = new_description

        if new_priority is not None:
            task.priority = _validate_priority(new_priority)

        if new_title and new_title != task.title:
            _assert_title_available(session, task.column, new_title, exclude_id=task.id)
            task.title = new_title

        session.commit()


def move_task(task_id: str, to_column: str, blocked_by: Optional[str] = None) -> None:
    with _session() as session:
        task = _get_active_task(session, task_id)

        if to_column == BLOCKED_COLUMN:
            task.blocked_by_id = _validate_blocker(session, blocked_by, own_id=task.id)
        else:
            task.blocked_by_id = None

        if to_column != task.column:
            _assert_title_available(session, to_column, task.title)
            task.column = to_column

        session.commit()


def delete_task(task_id: str) -> None:
    """Soft delete: mark the row as trashed without removing it."""
    with _session() as session:
        task = _get_active_task(session, task_id)
        task.deleted_at = datetime.now(timezone.utc)
        session.commit()


def _utc_isoformat(dt: datetime) -> str:
    """SQLite drops tzinfo on round-trip, but every value we write is UTC —
    reattach it before formatting so the API always emits an unambiguous
    (timezone-suffixed) timestamp."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


def get_trash() -> list[dict]:
    with _session() as session:
        tasks = (
            session.query(Task)
            .filter(Task.deleted_at.isnot(None))
            .order_by(Task.deleted_at.desc())
            .all()
        )
        return [
            {
                "id": _display_id(t.id),
                "title": t.title,
                "description": t.description,
                "priority": t.priority,
                "deleted_from": t.column,
                "deleted_at": _utc_isoformat(t.deleted_at),
            }
            for t in tasks
        ]


def restore_task(task_id: str) -> str:
    """Restore a trashed task back to the column it was deleted from. Returns that column."""
    with _session() as session:
        task = _get_trashed_task(session, task_id)
        _assert_title_available(session, task.column, task.title, exclude_id=task.id)
        task.deleted_at = None
        session.commit()
        return task.column


def permanent_delete_task(task_id: str) -> None:
    with _session() as session:
        task = _get_trashed_task(session, task_id)
        session.delete(task)
        session.commit()


def empty_trash() -> int:
    with _session() as session:
        trashed = session.query(Task).filter(Task.deleted_at.isnot(None)).all()
        count = len(trashed)
        for task in trashed:
            session.delete(task)
        session.commit()
        return count
