import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, relationship

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / ".kanban_data"

DONE_COLUMN = "Done"
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
    archived_at = Column(DateTime, nullable=True)
    due_date = Column(DateTime, nullable=True)

    blocked_by = relationship(
        "Task", remote_side=[id], backref="blocks", foreign_keys=[blocked_by_id]
    )


@event.listens_for(Engine, "connect")
def _enable_foreign_keys(dbapi_connection, _connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


_engine_cache: dict[str, Engine] = {}
_engine_lock = threading.Lock()


def _engine() -> Engine:
    """Cached per DATA_DIR (tests monkeypatch DATA_DIR to get isolated databases).

    FastAPI runs sync route handlers in a thread pool, and the frontend fires
    GET /api/tasks and GET /api/trash concurrently on page load. Without the
    lock, two threads can both see an uninitialized cache for the same
    DATA_DIR and race through create_engine()+create_all() at once, which
    SQLite reports as "table tasks already exists" — this double-checked
    lock ensures schema creation happens exactly once per DATA_DIR.
    """
    DATA_DIR.mkdir(exist_ok=True)
    key = str(DATA_DIR)
    if key in _engine_cache:
        return _engine_cache[key]
    with _engine_lock:
        if key not in _engine_cache:
            engine = create_engine(f"sqlite:///{DATA_DIR / 'kanban.db'}")
            Base.metadata.create_all(engine)
            _engine_cache[key] = engine
        return _engine_cache[key]


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


def _validate_blocker(session: Session, blocked_by: str, own_id: Optional[int]) -> int:
    """Validate a non-empty blocked_by string. Callers decide whether blocking is optional."""
    blocker_pk = _parse_id(blocked_by)
    if blocker_pk == own_id:
        raise ValueError("A task cannot block itself")
    blocker = session.get(Task, blocker_pk)
    if blocker is None or blocker.deleted_at is not None:
        raise ValueError(f"Blocker task '{blocked_by}' does not exist")
    if blocker.column == DONE_COLUMN:
        raise ValueError(f"Blocker task '{blocked_by}' is already Done")
    return blocker_pk


def _get_active_task(session: Session, task_id: str) -> Task:
    task = session.get(Task, _parse_id(task_id))
    if task is None or task.deleted_at is not None or task.archived_at is not None:
        raise FileNotFoundError(f"Task '{task_id}' not found")
    return task


def _get_trashed_task(session: Session, task_id: str) -> Task:
    task = session.get(Task, _parse_id(task_id))
    if task is None or task.deleted_at is None:
        raise FileNotFoundError(f"Task '{task_id}' not found in trash")
    return task


def _get_archived_task(session: Session, task_id: str) -> Task:
    task = session.get(Task, _parse_id(task_id))
    if task is None or task.archived_at is None:
        raise FileNotFoundError(f"Task '{task_id}' not found in archive")
    return task


def _assert_title_available(
    session: Session, column: str, title: str, exclude_id: Optional[int] = None
) -> None:
    query = session.query(Task).filter(
        Task.column == column,
        Task.title == title,
        Task.deleted_at.is_(None),
        Task.archived_at.is_(None),
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
        "due_date": _utc_isoformat(task.due_date) if task.due_date is not None else None,
    }


def get_all_boards() -> dict[str, list[dict]]:
    with _session() as session:
        tasks = (
            session.query(Task)
            .filter(Task.deleted_at.is_(None), Task.archived_at.is_(None))
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
    due_date: Optional[str] = None,
) -> str:
    with _session() as session:
        _assert_title_available(session, column, title)

        priority = _validate_priority(priority)

        blocked_by_id = None
        if blocked_by:
            if column == DONE_COLUMN:
                raise ValueError("A task cannot be created as Done while blocked")
            blocked_by_id = _validate_blocker(session, blocked_by, own_id=None)

        parsed_due_date = datetime.fromisoformat(due_date) if due_date else None

        task = Task(
            title=title,
            description=description,
            column=column,
            priority=priority,
            blocked_by_id=blocked_by_id,
            due_date=parsed_due_date,
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


def set_blocked_by(task_id: str, blocked_by: Optional[str]) -> None:
    """Set or clear a task's blocker, independent of which column it's in."""
    with _session() as session:
        task = _get_active_task(session, task_id)

        if blocked_by:
            if task.column == DONE_COLUMN:
                raise ValueError("A Done task cannot be blocked")
            task.blocked_by_id = _validate_blocker(session, blocked_by, own_id=task.id)
        else:
            task.blocked_by_id = None

        session.commit()


def set_due_date(task_id: str, due_date: Optional[str]) -> None:
    """Set or clear a task's due date, independent of which column it's in."""
    with _session() as session:
        task = _get_active_task(session, task_id)

        if due_date:
            task.due_date = datetime.fromisoformat(due_date)
        else:
            task.due_date = None

        session.commit()


def move_task(task_id: str, to_column: str) -> None:
    with _session() as session:
        task = _get_active_task(session, task_id)

        if to_column == DONE_COLUMN and task.blocked_by_id is not None:
            raise ValueError("A blocked task cannot be moved to Done")

        if to_column != task.column:
            _assert_title_available(session, to_column, task.title)
            task.column = to_column

        if to_column == DONE_COLUMN:
            dependents = (
                session.query(Task)
                .filter(Task.blocked_by_id == task.id, Task.deleted_at.is_(None))
                .all()
            )
            for dependent in dependents:
                dependent.blocked_by_id = None

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

        if task.blocked_by_id is not None:
            blocker = session.get(Task, task.blocked_by_id)
            if blocker is None or blocker.deleted_at is not None or blocker.column == DONE_COLUMN:
                task.blocked_by_id = None

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


def archive_task(task_id: str) -> None:
    """Archive a Done task: hides it from the board without touching the trash path.

    Archived and trashed are independent, non-overlapping states — a task can't be
    both. _get_active_task already excludes trashed *and* archived tasks, so this
    naturally rejects re-archiving an already-archived task or archiving a trashed
    one (both surface as 404, same as any other "not found" active task).
    """
    with _session() as session:
        task = _get_active_task(session, task_id)
        if task.column != DONE_COLUMN:
            raise ValueError("Only tasks in the Done column can be archived")
        task.archived_at = datetime.now(timezone.utc)
        session.commit()


def unarchive_task(task_id: str) -> None:
    """Unarchive a task, making it visible on the board again.

    Archived tasks are always in Done, and Done tasks can never carry a
    blocked_by_id (set_blocked_by refuses to block a Done task, and move_task
    clears it on the way in) — so unlike restore_task there's no blocker
    invariant to re-check here, only the title-uniqueness one.
    """
    with _session() as session:
        task = _get_archived_task(session, task_id)
        _assert_title_available(session, task.column, task.title, exclude_id=task.id)
        task.archived_at = None
        session.commit()


def get_archive() -> list[dict]:
    with _session() as session:
        tasks = (
            session.query(Task)
            .filter(Task.archived_at.isnot(None))
            .order_by(Task.archived_at.desc())
            .all()
        )
        return [
            {
                "id": _display_id(t.id),
                "title": t.title,
                "description": t.description,
                "priority": t.priority,
                "archived_at": _utc_isoformat(t.archived_at),
            }
            for t in tasks
        ]
