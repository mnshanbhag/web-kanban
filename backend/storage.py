import re
from pathlib import Path
from typing import Optional

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / ".kanban_data"

BLOCKED_COLUMN = "Blocked"

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
    if not DATA_DIR.exists():
        return
    for column_dir in sorted(p for p in DATA_DIR.iterdir() if p.is_dir()):
        for task_file in sorted(column_dir.glob("*.md")):
            yield column_dir.name, task_file


def _next_id() -> str:
    max_num = 0
    for _, path in _iter_task_files():
        meta, _ = _parse_task_content(path.read_text(encoding="utf-8"))
        match = _ID_RE.match(meta.get("id", ""))
        if match:
            max_num = max(max_num, int(match.group(1)))
    return f"KAN-{max_num + 1:02d}"


def _find_task(task_id: str) -> tuple[str, Path, dict[str, str], str]:
    for column, path in _iter_task_files():
        meta, description = _parse_task_content(path.read_text(encoding="utf-8"))
        if meta.get("id") == task_id:
            return column, path, meta, description
    raise FileNotFoundError(f"Task '{task_id}' not found")


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

    for column_dir in sorted(p for p in DATA_DIR.iterdir() if p.is_dir()):
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
    _, path, _, _ = _find_task(task_id)
    path.unlink()
