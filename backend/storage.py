import threading
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    create_engine,
    event,
    func,
)
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, relationship

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / ".kanban_data"

DONE_COLUMN = "Done"
PRIORITIES = ("Low", "Medium", "High", "Urgent")
DEFAULT_PRIORITY = "Medium"

SPRINT_STATUS_ACTIVE = "active"
SPRINT_STATUS_CLOSED = "closed"
SPRINT_STATUS_PLANNED = "planned"
SPRINT_DURATIONS_WEEKS = (1, 2, 3, 4)


class Base(DeclarativeBase):
    pass


class Sprint(Base):
    __tablename__ = "sprints"
    __table_args__ = {"sqlite_autoincrement": True}

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    # A "planned" sprint has a name + duration_weeks but no start_date/end_date yet -- those
    # are only computed at promotion time (see end_sprint), which sidesteps any "planned sprint
    # started early/late relative to a fixed date" problem since there's no fixed planned start
    # date to drift from. Nullable to support that state; active/closed sprints always have both.
    start_date = Column(Date, nullable=True)
    end_date = Column(Date, nullable=True)
    # Only meaningful while status == "planned" -- the duration a planned sprint will get once
    # promoted to active. Active/closed sprints don't need it since their date range is already
    # fixed on start_date/end_date.
    duration_weeks = Column(Integer, nullable=True)
    status = Column(String, nullable=False, default=SPRINT_STATUS_ACTIVE)
    closed_at = Column(DateTime, nullable=True)


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
    sprint_id = Column(Integer, ForeignKey("sprints.id", ondelete="SET NULL"), nullable=True)
    updated_at = Column(DateTime, nullable=True)

    blocked_by = relationship(
        "Task", remote_side=[id], backref="blocks", foreign_keys=[blocked_by_id]
    )


class TaskSubtask(Base):
    __tablename__ = "task_subtasks"
    __table_args__ = {"sqlite_autoincrement": True}

    id = Column(Integer, primary_key=True)
    task_id = Column(Integer, ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False)
    title = Column(String, nullable=False)
    done = Column(Boolean, nullable=False, default=False)
    position = Column(Integer, nullable=False, default=0)


class TaskNote(Base):
    __tablename__ = "task_notes"
    __table_args__ = {"sqlite_autoincrement": True}

    id = Column(Integer, primary_key=True)
    task_id = Column(Integer, ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False)
    body = Column(String, nullable=False)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))


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


def _task_to_dict(session: Session, task: Task) -> dict:
    subtask_total = (
        session.query(TaskSubtask).filter(TaskSubtask.task_id == task.id).count()
    )
    subtask_done = (
        session.query(TaskSubtask)
        .filter(TaskSubtask.task_id == task.id, TaskSubtask.done.is_(True))
        .count()
    )
    return {
        "id": _display_id(task.id),
        "title": task.title,
        "description": task.description,
        "priority": task.priority,
        "blocked_by": _display_id(task.blocked_by_id) if task.blocked_by_id else None,
        "blocks": [_display_id(t.id) for t in task.blocks if t.deleted_at is None],
        "due_date": _utc_isoformat(task.due_date) if task.due_date is not None else None,
        "subtask_total": subtask_total,
        "subtask_done": subtask_done,
        "updated_at": _utc_isoformat(task.updated_at) if task.updated_at is not None else None,
        "sprint_id": task.sprint_id,
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
            board.setdefault(task.column, []).append(_task_to_dict(session, task))
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

        active_sprint = (
            session.query(Sprint).filter(Sprint.status == SPRINT_STATUS_ACTIVE).first()
        )

        task = Task(
            title=title,
            description=description,
            column=column,
            priority=priority,
            blocked_by_id=blocked_by_id,
            due_date=parsed_due_date,
            sprint_id=active_sprint.id if active_sprint is not None else None,
            updated_at=datetime.now(timezone.utc),
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

        task.updated_at = datetime.now(timezone.utc)
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

        task.updated_at = datetime.now(timezone.utc)
        session.commit()


def set_due_date(task_id: str, due_date: Optional[str]) -> None:
    """Set or clear a task's due date, independent of which column it's in."""
    with _session() as session:
        task = _get_active_task(session, task_id)

        if due_date:
            task.due_date = datetime.fromisoformat(due_date)
        else:
            task.due_date = None

        task.updated_at = datetime.now(timezone.utc)
        session.commit()


def move_task(task_id: str, to_column: str) -> None:
    with _session() as session:
        task = _get_active_task(session, task_id)

        if to_column == DONE_COLUMN and task.blocked_by_id is not None:
            raise ValueError("A blocked task cannot be moved to Done")

        if to_column != task.column:
            _assert_title_available(session, to_column, task.title)
            task.column = to_column

        now = datetime.now(timezone.utc)

        if to_column == DONE_COLUMN:
            dependents = (
                session.query(Task)
                .filter(Task.blocked_by_id == task.id, Task.deleted_at.is_(None))
                .all()
            )
            for dependent in dependents:
                dependent.blocked_by_id = None
                dependent.updated_at = now

        task.updated_at = now
        session.commit()


def delete_task(task_id: str) -> None:
    """Soft delete: mark the row as trashed without removing it.

    Done tasks can't be deleted directly — move it to another column first.
    This mirrors the "finishing something is a real state" philosophy behind
    the Done-cascade in move_task: a completed task shouldn't quietly vanish.
    """
    with _session() as session:
        task = _get_active_task(session, task_id)
        if task.column == DONE_COLUMN:
            raise ValueError("A Done task cannot be deleted; move it to another column first")
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


def _subtask_to_dict(subtask: TaskSubtask) -> dict:
    return {
        "id": subtask.id,
        "title": subtask.title,
        "done": subtask.done,
        "position": subtask.position,
    }


def _get_subtask(session: Session, task_id: str, subtask_id: int) -> TaskSubtask:
    task = _get_active_task(session, task_id)
    subtask = session.get(TaskSubtask, subtask_id)
    if subtask is None or subtask.task_id != task.id:
        raise FileNotFoundError(f"Subtask '{subtask_id}' not found on task '{task_id}'")
    return subtask


def get_subtasks(task_id: str) -> list[dict]:
    with _session() as session:
        task = _get_active_task(session, task_id)
        subtasks = (
            session.query(TaskSubtask)
            .filter(TaskSubtask.task_id == task.id)
            .order_by(TaskSubtask.position, TaskSubtask.id)
            .all()
        )
        return [_subtask_to_dict(s) for s in subtasks]


def add_subtask(task_id: str, title: str) -> dict:
    with _session() as session:
        task = _get_active_task(session, task_id)

        title = title.strip()
        if not title:
            raise ValueError("Subtask title cannot be empty")

        max_position = (
            session.query(func.max(TaskSubtask.position))
            .filter(TaskSubtask.task_id == task.id)
            .scalar()
        )
        next_position = 0 if max_position is None else max_position + 1

        subtask = TaskSubtask(task_id=task.id, title=title, done=False, position=next_position)
        session.add(subtask)
        session.commit()
        session.refresh(subtask)
        return _subtask_to_dict(subtask)


def update_subtask(
    task_id: str,
    subtask_id: int,
    new_title: Optional[str] = None,
    new_done: Optional[bool] = None,
) -> dict:
    with _session() as session:
        subtask = _get_subtask(session, task_id, subtask_id)

        if new_title is not None:
            new_title = new_title.strip()
            if not new_title:
                raise ValueError("Subtask title cannot be empty")
            subtask.title = new_title

        if new_done is not None:
            subtask.done = new_done

        session.commit()
        session.refresh(subtask)
        return _subtask_to_dict(subtask)


def delete_subtask(task_id: str, subtask_id: int) -> None:
    with _session() as session:
        subtask = _get_subtask(session, task_id, subtask_id)
        session.delete(subtask)
        session.commit()


def _note_to_dict(note: TaskNote) -> dict:
    return {
        "id": note.id,
        "body": note.body,
        "created_at": _utc_isoformat(note.created_at),
    }


def get_notes(task_id: str) -> list[dict]:
    with _session() as session:
        task = _get_active_task(session, task_id)
        notes = (
            session.query(TaskNote)
            .filter(TaskNote.task_id == task.id)
            .order_by(TaskNote.created_at.desc(), TaskNote.id.desc())
            .all()
        )
        return [_note_to_dict(n) for n in notes]


def add_note(task_id: str, body: str) -> dict:
    with _session() as session:
        task = _get_active_task(session, task_id)

        body = body.strip()
        if not body:
            raise ValueError("Note body cannot be empty")

        note = TaskNote(task_id=task.id, body=body, created_at=datetime.now(timezone.utc))
        session.add(note)
        session.commit()
        session.refresh(note)
        return _note_to_dict(note)


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


def archive_all_done() -> int:
    """Archive every active Done task in one shot. Returns the number archived."""
    with _session() as session:
        tasks = (
            session.query(Task)
            .filter(
                Task.column == DONE_COLUMN,
                Task.deleted_at.is_(None),
                Task.archived_at.is_(None),
            )
            .all()
        )
        now = datetime.now(timezone.utc)
        for task in tasks:
            task.archived_at = now
        session.commit()
        return len(tasks)


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


def _validate_sprint_duration(duration_weeks: int) -> int:
    if duration_weeks not in SPRINT_DURATIONS_WEEKS:
        raise ValueError(
            "duration_weeks must be one of "
            f"{', '.join(str(d) for d in SPRINT_DURATIONS_WEEKS)}"
        )
    return duration_weeks


def _sprint_to_dict(sprint: Sprint) -> dict:
    return {
        "id": sprint.id,
        "name": sprint.name,
        "start_date": sprint.start_date.isoformat() if sprint.start_date is not None else None,
        "end_date": sprint.end_date.isoformat() if sprint.end_date is not None else None,
        "duration_weeks": sprint.duration_weeks,
        "status": sprint.status,
        "closed_at": _utc_isoformat(sprint.closed_at) if sprint.closed_at is not None else None,
    }


def _assert_sprint_name_available(session: Session, name: str) -> None:
    """Sprint names are never reused, even across closed sprints -- unlike task titles (unique
    only within a column), a sprint's name has no scoping concept to make a collision safe, and
    the Last/Older Sprints panels render by name, so two same-named sprints would be
    indistinguishable there."""
    if session.query(Sprint).filter(Sprint.name == name).first() is not None:
        raise FileExistsError(f"A sprint named '{name}' already exists")


def get_all_sprints() -> list[dict]:
    """Every sprint row regardless of status (active + planned + closed), for export -- unlike
    get_active_sprint/get_planned_sprint/get_past_sprints, which each return only one status
    subset. Ordered by id since there's no single recency field spanning all three statuses
    (planned sprints have no start_date/closed_at yet)."""
    with _session() as session:
        sprints = session.query(Sprint).order_by(Sprint.id).all()
        return [_sprint_to_dict(s) for s in sprints]


def get_active_sprint() -> Optional[dict]:
    with _session() as session:
        sprint = (
            session.query(Sprint).filter(Sprint.status == SPRINT_STATUS_ACTIVE).first()
        )
        return _sprint_to_dict(sprint) if sprint is not None else None


def start_sprint(name: str, duration_weeks: int) -> dict:
    """Start a new sprint. Only one sprint may be active at a time.

    Sweeps up every currently-untagged (sprint_id IS NULL), non-Done, active
    task and tags it with the new sprint's id — this is the "incomplete work
    rolls forward" mechanism, since there's no separate backlog/holding state
    in this scope.
    """
    name = name.strip()
    if not name:
        raise ValueError("Sprint name cannot be empty")
    duration_weeks = _validate_sprint_duration(duration_weeks)

    with _session() as session:
        existing = (
            session.query(Sprint).filter(Sprint.status == SPRINT_STATUS_ACTIVE).first()
        )
        if existing is not None:
            raise ValueError("A sprint is already active")
        _assert_sprint_name_available(session, name)

        start = date.today()
        end = start + timedelta(weeks=duration_weeks)
        sprint = Sprint(
            name=name, start_date=start, end_date=end, status=SPRINT_STATUS_ACTIVE
        )
        session.add(sprint)
        session.flush()

        untagged_tasks = (
            session.query(Task)
            .filter(
                Task.sprint_id.is_(None),
                Task.column != DONE_COLUMN,
                Task.deleted_at.is_(None),
                Task.archived_at.is_(None),
            )
            .all()
        )
        for task in untagged_tasks:
            task.sprint_id = sprint.id

        session.commit()
        session.refresh(sprint)
        return _sprint_to_dict(sprint)


def get_planned_sprint() -> Optional[dict]:
    with _session() as session:
        sprint = (
            session.query(Sprint).filter(Sprint.status == SPRINT_STATUS_PLANNED).first()
        )
        return _sprint_to_dict(sprint) if sprint is not None else None


def plan_next_sprint(name: str, duration_weeks: int) -> dict:
    """Queue up the next sprint's name/duration ahead of time, without committing to a start
    date yet. At most one sprint may be "planned" at a time, mirroring the at-most-one-active
    check `start_sprint` already enforces. `end_sprint` promotes this straight to active
    (computing real start_date/end_date from `duration_weeks` as of the promotion moment)
    instead of opening its name/duration prompt.
    """
    name = name.strip()
    if not name:
        raise ValueError("Sprint name cannot be empty")
    duration_weeks = _validate_sprint_duration(duration_weeks)

    with _session() as session:
        active = (
            session.query(Sprint).filter(Sprint.status == SPRINT_STATUS_ACTIVE).first()
        )
        if active is None:
            raise ValueError("Cannot plan a next sprint while no sprint is active")

        existing = (
            session.query(Sprint).filter(Sprint.status == SPRINT_STATUS_PLANNED).first()
        )
        if existing is not None:
            raise ValueError("A sprint is already planned")
        _assert_sprint_name_available(session, name)

        sprint = Sprint(
            name=name,
            start_date=None,
            end_date=None,
            duration_weeks=duration_weeks,
            status=SPRINT_STATUS_PLANNED,
        )
        session.add(sprint)
        session.commit()
        session.refresh(sprint)
        return _sprint_to_dict(sprint)


def end_sprint(next_name: Optional[str] = None, next_duration_weeks: Optional[int] = None) -> dict:
    """Close the active sprint and immediately promote the next one, so the board is never left
    without an active sprint once the first one has started.

    Checks for a queued planned sprint first: if one exists, it's promoted straight to active
    (its stored `duration_weeks` used to compute real `start_date`/`end_date` as of this
    promotion moment), and `next_name`/`next_duration_weeks` are ignored. Otherwise, falls back
    to the original prompt-driven flow -- `next_name`/`next_duration_weeks` (required in that
    case) open a brand new sprint, same as before `plan_next_sprint` existed.

    The closing sprint's own `end_date` is overwritten with today's date regardless of what it
    was set to at start/promotion time -- that original value was only ever a target, and ending
    a sprint early or late relative to it is normal, so a closed sprint's date range should
    always reflect what actually happened, not what was originally planned.

    Either way, every incomplete (non-Done) task in the closing sprint rolls straight into the
    new sprint rather than being cleared back to untagged. Done tasks keep their sprint_id
    pointing at the now-closed sprint permanently, as a historical record. Also sweeps up any
    currently-untagged non-Done task, same as `start_sprint`, since that's still the only way a
    task not previously in a sprint (e.g. created before the very first sprint ever started)
    joins.
    """
    with _session() as session:
        sprint = (
            session.query(Sprint).filter(Sprint.status == SPRINT_STATUS_ACTIVE).first()
        )
        if sprint is None:
            raise ValueError("No sprint is currently active")

        planned = (
            session.query(Sprint).filter(Sprint.status == SPRINT_STATUS_PLANNED).first()
        )

        start = date.today()

        sprint.status = SPRINT_STATUS_CLOSED
        sprint.closed_at = datetime.now(timezone.utc)
        # The sprint's end_date was set at start_sprint/plan time as a target, not a promise --
        # ending it earlier or later than that target is normal. Overwrite it with the actual
        # closing date so a closed sprint's date range always reflects what really happened.
        sprint.end_date = start

        if planned is not None:
            new_sprint = planned
            new_sprint.start_date = start
            new_sprint.end_date = start + timedelta(weeks=planned.duration_weeks)
            new_sprint.status = SPRINT_STATUS_ACTIVE
        else:
            next_name = (next_name or "").strip()
            if not next_name:
                raise ValueError(
                    "No sprint is planned; name and duration_weeks are required to end the "
                    "sprint"
                )
            next_duration_weeks = _validate_sprint_duration(next_duration_weeks)
            _assert_sprint_name_available(session, next_name)
            end = start + timedelta(weeks=next_duration_weeks)
            new_sprint = Sprint(
                name=next_name, start_date=start, end_date=end, status=SPRINT_STATUS_ACTIVE
            )
            session.add(new_sprint)
        session.flush()

        rollover_tasks = (
            session.query(Task)
            .filter(
                Task.sprint_id == sprint.id,
                Task.column != DONE_COLUMN,
                Task.deleted_at.is_(None),
            )
            .all()
        )
        for task in rollover_tasks:
            task.sprint_id = new_sprint.id

        untagged_tasks = (
            session.query(Task)
            .filter(
                Task.sprint_id.is_(None),
                Task.column != DONE_COLUMN,
                Task.deleted_at.is_(None),
                Task.archived_at.is_(None),
            )
            .all()
        )
        for task in untagged_tasks:
            task.sprint_id = new_sprint.id

        session.commit()
        session.refresh(new_sprint)
        return _sprint_to_dict(new_sprint)


def import_data(payload: dict) -> dict:
    """Restore tasks/sprints from a `GET /api/export`-shaped payload.

    Additive, not wipe-and-replace -- rows are added to whatever's already in the DB. Every id in
    the payload (sprint ids, "KAN-NN" task ids) is local to that file and gets remapped to a
    freshly minted id here rather than reused, same reasoning as the "IDs are never reused"
    invariant elsewhere: reusing an id risks colliding with or resurrecting one AUTOINCREMENT has
    already retired. Nothing is committed until every row validates, so a failure partway through
    (a title collision, an orphaned blocker reference, ...) leaves the session uncommitted and its
    `.close()` on exit discards everything -- the same one-`session.commit()`-at-the-end pattern
    `end_sprint` uses for its own multi-step atomic work.

    Timestamps (Task.updated_at, TaskNote.created_at, Sprint.closed_at) are preserved from the
    file rather than reset to "now" -- import is a restore of prior state, not new activity.
    """
    with _session() as session:
        sprints_payload = payload.get("sprints", [])
        tasks_payload = payload.get("tasks", {})

        active_in_file = [s for s in sprints_payload if s["status"] == SPRINT_STATUS_ACTIVE]
        planned_in_file = [s for s in sprints_payload if s["status"] == SPRINT_STATUS_PLANNED]
        if len(active_in_file) > 1:
            raise ValueError("Import file contains more than one active sprint")
        if len(planned_in_file) > 1:
            raise ValueError("Import file contains more than one planned sprint")
        if active_in_file and (
            session.query(Sprint).filter(Sprint.status == SPRINT_STATUS_ACTIVE).first()
            is not None
        ):
            raise ValueError("An active sprint already exists")
        if planned_in_file and (
            session.query(Sprint).filter(Sprint.status == SPRINT_STATUS_PLANNED).first()
            is not None
        ):
            raise ValueError("A sprint is already planned")

        sprint_id_map: dict[int, int] = {}
        for s in sprints_payload:
            _assert_sprint_name_available(session, s["name"])
            new_sprint = Sprint(
                name=s["name"],
                start_date=date.fromisoformat(s["start_date"]) if s.get("start_date") else None,
                end_date=date.fromisoformat(s["end_date"]) if s.get("end_date") else None,
                duration_weeks=s.get("duration_weeks"),
                status=s["status"],
                closed_at=(
                    datetime.fromisoformat(s["closed_at"]) if s.get("closed_at") else None
                ),
            )
            session.add(new_sprint)
            session.flush()
            sprint_id_map[s["id"]] = new_sprint.id

        task_id_map: dict[str, int] = {}
        pending_blocks: list[tuple[int, str]] = []
        tasks_imported = 0
        for column, column_tasks in tasks_payload.items():
            for t in column_tasks:
                priority = _validate_priority(t["priority"])
                _assert_title_available(session, column, t["title"])

                sprint_id = None
                if t.get("sprint_id") is not None:
                    if t["sprint_id"] not in sprint_id_map:
                        raise ValueError(
                            f"Task '{t['id']}' references sprint id {t['sprint_id']}, which is "
                            "not present in this import"
                        )
                    sprint_id = sprint_id_map[t["sprint_id"]]

                new_task = Task(
                    title=t["title"],
                    description=t.get("description", ""),
                    column=column,
                    priority=priority,
                    due_date=(
                        datetime.fromisoformat(t["due_date"]) if t.get("due_date") else None
                    ),
                    sprint_id=sprint_id,
                    updated_at=(
                        datetime.fromisoformat(t["updated_at"]) if t.get("updated_at") else None
                    ),
                )
                session.add(new_task)
                session.flush()
                task_id_map[t["id"]] = new_task.id
                tasks_imported += 1

                if t.get("blocked_by"):
                    pending_blocks.append((new_task.id, t["blocked_by"]))

                for st in t.get("subtasks", []):
                    session.add(
                        TaskSubtask(
                            task_id=new_task.id,
                            title=st["title"],
                            done=st["done"],
                            position=st["position"],
                        )
                    )
                for note in t.get("notes", []):
                    session.add(
                        TaskNote(
                            task_id=new_task.id,
                            body=note["body"],
                            created_at=datetime.fromisoformat(note["created_at"]),
                        )
                    )

        for new_pk, old_blocked_by in pending_blocks:
            if old_blocked_by not in task_id_map:
                raise ValueError(
                    f"Blocker task '{old_blocked_by}' is not present in this import"
                )
            blocker_pk = task_id_map[old_blocked_by]
            blocker_task = session.get(Task, blocker_pk)
            if blocker_task.column == DONE_COLUMN:
                raise ValueError(f"Blocker task '{old_blocked_by}' is already Done")
            session.get(Task, new_pk).blocked_by_id = blocker_pk

        session.commit()
        return {"sprints_imported": len(sprint_id_map), "tasks_imported": tasks_imported}


def get_past_sprints() -> list[dict]:
    """Closed sprints, most-recently-closed first, each annotated with the Done tasks that
    completed during it.

    Done tasks keep their sprint_id pointing at the now-closed sprint permanently (see
    end_sprint's docstring), so "which tasks completed in sprint N" is just a query for Done
    tasks with sprint_id == N — no new column needed.
    """
    with _session() as session:
        sprints = (
            session.query(Sprint)
            .filter(Sprint.status == SPRINT_STATUS_CLOSED)
            .order_by(Sprint.closed_at.desc(), Sprint.id.desc())
            .all()
        )
        result = []
        for sprint in sprints:
            completed_tasks = (
                session.query(Task)
                .filter(
                    Task.sprint_id == sprint.id,
                    Task.column == DONE_COLUMN,
                    Task.deleted_at.is_(None),
                )
                .order_by(Task.title)
                .all()
            )
            sprint_dict = _sprint_to_dict(sprint)
            sprint_dict["completed_tasks"] = [
                {"id": _display_id(t.id), "title": t.title} for t in completed_tasks
            ]
            result.append(sprint_dict)
        return result
