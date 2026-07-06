import re
from pathlib import Path
from typing import Optional

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / ".kanban_data"

PRIORITIES = ("Low", "Medium", "High", "Urgent")
DEFAULT_PRIORITY = "Medium"

_INVALID_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n?(.*)$", re.DOTALL)


def sanitize_name(name: str) -> str:
    cleaned = _INVALID_CHARS.sub("_", name).strip()
    if not cleaned:
        raise ValueError("Name cannot be empty")
    return cleaned


def _validate_priority(priority: str) -> str:
    if priority not in PRIORITIES:
        raise ValueError(f"priority must be one of {', '.join(PRIORITIES)}")
    return priority


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


def get_all_boards() -> dict[str, list[dict[str, str]]]:
    """Return every column and its tasks: {column: [{"title", "description", "priority"}, ...]}."""
    DATA_DIR.mkdir(exist_ok=True)
    board: dict[str, list[dict[str, str]]] = {}
    for column_dir in sorted(p for p in DATA_DIR.iterdir() if p.is_dir()):
        tasks = []
        for task_file in sorted(column_dir.glob("*.md")):
            meta, description = _parse_task_content(task_file.read_text(encoding="utf-8"))
            tasks.append(
                {
                    "title": task_file.stem,
                    "description": description,
                    "priority": meta.get("priority") or DEFAULT_PRIORITY,
                }
            )
        board[column_dir.name] = tasks
    return board


def add_task(
    column: str,
    title: str,
    description: str = "",
    priority: str = DEFAULT_PRIORITY,
) -> None:
    column_dir = _column_dir(column)
    column_dir.mkdir(parents=True, exist_ok=True)

    task_path = _task_path(column, title)
    if task_path.exists():
        raise FileExistsError(f"Task '{title}' already exists in column '{column}'")

    priority = _validate_priority(priority)
    content = _render_task_content({"priority": priority}, description)
    task_path.write_text(content, encoding="utf-8")


def update_task(
    column: str,
    title: str,
    new_title: Optional[str] = None,
    new_description: Optional[str] = None,
    new_priority: Optional[str] = None,
) -> None:
    task_path = _task_path(column, title)
    if not task_path.exists():
        raise FileNotFoundError(f"Task '{title}' not found in column '{column}'")

    meta, description = _parse_task_content(task_path.read_text(encoding="utf-8"))

    if new_description is not None:
        description = new_description

    if new_priority is not None:
        meta["priority"] = _validate_priority(new_priority)

    dest_path = task_path
    if new_title and new_title != title:
        dest_path = _task_path(column, new_title)
        if dest_path.exists():
            raise FileExistsError(f"Task '{new_title}' already exists in column '{column}'")

    task_path.write_text(_render_task_content(meta, description), encoding="utf-8")
    if dest_path != task_path:
        task_path.rename(dest_path)


def move_task(title: str, from_column: str, to_column: str) -> None:
    src = _task_path(from_column, title)
    if not src.exists():
        raise FileNotFoundError(f"Task '{title}' not found in column '{from_column}'")

    dest_dir = _column_dir(to_column)
    dest_dir.mkdir(parents=True, exist_ok=True)

    dest = _task_path(to_column, title)
    if dest.exists():
        raise FileExistsError(f"Task '{title}' already exists in column '{to_column}'")

    src.rename(dest)


def delete_task(column: str, title: str) -> None:
    task_path = _task_path(column, title)
    if not task_path.exists():
        raise FileNotFoundError(f"Task '{title}' not found in column '{column}'")

    task_path.unlink()
