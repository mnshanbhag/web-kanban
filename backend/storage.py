import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / ".kanban_data"

BLOCKED_COLUMN = "Blocked"
TRASH_DIRNAME = ".trash"
ID_COUNTER_FILENAME = ".id_counter"

_INVALID_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n?(.*)$", re.DOTALL)
_ID_RE = re.compile(r"^KAN-(\d+)$")


def sanitize_name(name: str) -> str:
    cleaned = _INVALID_CHARS.sub("_", name).strip()
    if not cleaned:
        raise ValueError("Name cannot be empty")
    return cleaned


def _column_dir(column: str) -> Path:
    return DATA_DIR / sanitize_name(column)


def _task_path(column: str, title: str) -> Path:
    return _column_dir(column) / f"{sanitize_name(title)}.md"


def _trash_dir() -> Path:
    trash = DATA_DIR / TRASH_DIRNAME
    trash.mkdir(parents=True, exist_ok=True)
    return trash


def _parse_task_content(content: str) -> tuple[dict[str, str], str]:
    match = _FRONTMATTER_RE.match(content)
    if not match:
        return {}, content

    raw_meta, body = match.groups()
    meta: dict[str, str] = {}
    for line in raw_meta.splitlines():
        key, sep, value = line.partition(":")
        if sep:
            meta[key.strip()] = value.strip()
    return meta, body


def _render_task_content(meta: dict[str, str], description: str) -> str:
    lines = ["---"]
    for key, value in meta.items():
        if value:
            lines.append(f"{key}: {value}")
    lines.append("---")
    return "\n".join(lines) + "\n" + description


def _iter_task_files():
    """Active (non-trashed) tasks only, grouped by column."""
    if not DATA_DIR.exists():
        return
    for column_dir in sorted(p for p in DATA_DIR.iterdir() if p.is_dir() and p.name != TRASH_DIRNAME):
        for task_file in sorted(column_dir.glob("*.md")):
            yield column_dir.name, task_file


def _iter_trash_files():
    trash = DATA_DIR / TRASH_DIRNAME
    if not trash.exists():
        return
    for task_file in sorted(trash.glob("*.md")):
        yield task_file


def _next_id() -> str:
    """Monotonic counter persisted on disk, so IDs are never reused even after a
    permanent delete removes the previous highest ID from disk entirely."""
    DATA_DIR.mkdir(exist_ok=True)
    counter_file = DATA_DIR / ID_COUNTER_FILENAME

    if counter_file.exists():
        next_num = int(counter_file.read_text(encoding="utf-8").strip())
    else:
        next_num = 1
        for _, path in _iter_task_files():
            meta, _ = _parse_task_content(path.read_text(encoding="utf-8"))
            match = _ID_RE.match(meta.get("id", ""))
            if match:
                next_num = max(next_num, int(match.group(1)) + 1)
        for path in _iter_trash_files():
            meta, _ = _parse_task_content(path.read_text(encoding="utf-8"))
            match = _ID_RE.match(meta.get("id", ""))
            if match:
                next_num = max(next_num, int(match.group(1)) + 1)

    counter_file.write_text(str(next_num + 1), encoding="utf-8")
    return f"KAN-{next_num:02d}"


def _find_task(task_id: str) -> tuple[str, Path, dict[str, str], str]:
    for column, path in _iter_task_files():
        meta, description = _parse_task_content(path.read_text(encoding="utf-8"))
        if meta.get("id") == task_id:
            return column, path, meta, description
    raise FileNotFoundError(f"Task '{task_id}' not found")


def _find_trashed_task(task_id: str) -> tuple[Path, dict[str, str], str]:
    for path in _iter_trash_files():
        meta, description = _parse_task_content(path.read_text(encoding="utf-8"))
        if meta.get("id") == task_id:
            return path, meta, description
    raise FileNotFoundError(f"Task '{task_id}' not found in trash")


def _validate_blocker(blocked_by: Optional[str], own_id: Optional[str]) -> str:
    if not blocked_by:
        raise ValueError(f"blocked_by is required when column is '{BLOCKED_COLUMN}'")
    if blocked_by == own_id:
        raise ValueError("A task cannot block itself")
    try:
        _find_task(blocked_by)
    except FileNotFoundError:
        raise ValueError(f"Blocker task '{blocked_by}' does not exist") from None
    return blocked_by


def get_all_boards() -> dict[str, list[dict]]:
    """Return every column and its tasks, including computed reverse 'blocks' links."""
    DATA_DIR.mkdir(exist_ok=True)

    board: dict[str, list[dict]] = {}
    all_tasks: list[dict] = []

    for column_dir in sorted(p for p in DATA_DIR.iterdir() if p.is_dir() and p.name != TRASH_DIRNAME):
        tasks = []
        for task_file in sorted(column_dir.glob("*.md")):
            meta, description = _parse_task_content(task_file.read_text(encoding="utf-8"))
            task = {
                "id": meta.get("id", ""),
                "title": task_file.stem,
                "description": description,
                "blocked_by": meta.get("blocked_by") or None,
            }
            tasks.append(task)
            all_tasks.append(task)
        board[column_dir.name] = tasks

    blocks_map: dict[str, list[str]] = {}
    for task in all_tasks:
        if task["blocked_by"]:
            blocks_map.setdefault(task["blocked_by"], []).append(task["id"])
    for task in all_tasks:
        task["blocks"] = blocks_map.get(task["id"], [])

    return board


def add_task(
    column: str,
    title: str,
    description: str = "",
    blocked_by: Optional[str] = None,
) -> str:
    column_dir = _column_dir(column)
    column_dir.mkdir(parents=True, exist_ok=True)

    task_path = _task_path(column, title)
    if task_path.exists():
        raise FileExistsError(f"Task '{title}' already exists in column '{column}'")

    if column == BLOCKED_COLUMN:
        blocked_by = _validate_blocker(blocked_by, own_id=None)
    else:
        blocked_by = None

    task_id = _next_id()
    content = _render_task_content({"id": task_id, "blocked_by": blocked_by or ""}, description)
    task_path.write_text(content, encoding="utf-8")
    return task_id


def update_task(
    task_id: str,
    new_title: Optional[str] = None,
    new_description: Optional[str] = None,
) -> None:
    column, path, meta, description = _find_task(task_id)

    if new_description is not None:
        description = new_description

    dest_path = path
    if new_title and new_title != path.stem:
        dest_path = _task_path(column, new_title)
        if dest_path.exists():
            raise FileExistsError(f"Task '{new_title}' already exists in column '{column}'")

    path.write_text(_render_task_content(meta, description), encoding="utf-8")
    if dest_path != path:
        path.rename(dest_path)


def move_task(task_id: str, to_column: str, blocked_by: Optional[str] = None) -> None:
    column, path, meta, description = _find_task(task_id)

    if to_column == BLOCKED_COLUMN:
        blocked_by = _validate_blocker(blocked_by, own_id=task_id)
    else:
        blocked_by = None

    dest_dir = _column_dir(to_column)
    dest_dir.mkdir(parents=True, exist_ok=True)

    dest_path = dest_dir / f"{sanitize_name(path.stem)}.md"
    if dest_path.exists() and dest_path != path:
        raise FileExistsError(f"Task '{path.stem}' already exists in column '{to_column}'")

    meta["blocked_by"] = blocked_by or ""
    path.write_text(_render_task_content(meta, description), encoding="utf-8")
    if dest_path != path:
        path.rename(dest_path)


def delete_task(task_id: str) -> None:
    """Soft delete: move the task's file into the trash, remembering where it came from."""
    column, path, meta, description = _find_task(task_id)

    meta["title"] = path.stem
    meta["deleted_from"] = column
    meta["deleted_at"] = datetime.now(timezone.utc).isoformat()

    trash_path = _trash_dir() / f"{task_id}.md"
    trash_path.write_text(_render_task_content(meta, description), encoding="utf-8")
    path.unlink()


def get_trash() -> list[dict]:
    trashed = []
    for path in _iter_trash_files():
        meta, description = _parse_task_content(path.read_text(encoding="utf-8"))
        trashed.append(
            {
                "id": meta.get("id", ""),
                "title": meta.get("title", ""),
                "description": description,
                "deleted_from": meta.get("deleted_from") or "To Do",
                "deleted_at": meta.get("deleted_at", ""),
            }
        )
    trashed.sort(key=lambda t: t["deleted_at"], reverse=True)
    return trashed


def restore_task(task_id: str) -> str:
    """Restore a trashed task back to the column it was deleted from. Returns that column."""
    path, meta, description = _find_trashed_task(task_id)

    title = meta.get("title") or task_id
    target_column = meta.get("deleted_from") or "To Do"

    dest_dir = _column_dir(target_column)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path = _task_path(target_column, title)
    if dest_path.exists():
        raise FileExistsError(f"Task '{title}' already exists in column '{target_column}'")

    restored_meta = {k: v for k, v in meta.items() if k not in ("title", "deleted_from", "deleted_at")}
    dest_path.write_text(_render_task_content(restored_meta, description), encoding="utf-8")
    path.unlink()
    return target_column


def permanent_delete_task(task_id: str) -> None:
    path, _, _ = _find_trashed_task(task_id)
    path.unlink()


def empty_trash() -> int:
    count = 0
    for path in list(_iter_trash_files()):
        path.unlink()
        count += 1
    return count
