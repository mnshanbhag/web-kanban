import re
from pathlib import Path
from typing import Optional

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / ".kanban_data"

_INVALID_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def sanitize_name(name: str) -> str:
    cleaned = _INVALID_CHARS.sub("_", name).strip()
    if not cleaned:
        raise ValueError("Name cannot be empty")
    return cleaned


def _column_dir(column: str) -> Path:
    return DATA_DIR / sanitize_name(column)


def _task_path(column: str, title: str) -> Path:
    return _column_dir(column) / f"{sanitize_name(title)}.md"


def get_all_boards() -> dict[str, list[dict[str, str]]]:
    """Return every column and its tasks: {column: [{"title", "description"}, ...]}."""
    DATA_DIR.mkdir(exist_ok=True)
    board: dict[str, list[dict[str, str]]] = {}
    for column_dir in sorted(p for p in DATA_DIR.iterdir() if p.is_dir()):
        tasks = [
            {"title": task_file.stem, "description": task_file.read_text(encoding="utf-8")}
            for task_file in sorted(column_dir.glob("*.md"))
        ]
        board[column_dir.name] = tasks
    return board


def add_task(column: str, title: str, description: str = "") -> None:
    column_dir = _column_dir(column)
    column_dir.mkdir(parents=True, exist_ok=True)

    task_path = _task_path(column, title)
    if task_path.exists():
        raise FileExistsError(f"Task '{title}' already exists in column '{column}'")

    task_path.write_text(description, encoding="utf-8")


def update_task(
    column: str,
    title: str,
    new_title: Optional[str] = None,
    new_description: Optional[str] = None,
) -> None:
    task_path = _task_path(column, title)
    if not task_path.exists():
        raise FileNotFoundError(f"Task '{title}' not found in column '{column}'")

    description = (
        new_description if new_description is not None else task_path.read_text(encoding="utf-8")
    )

    if new_title and new_title != title:
        new_path = _task_path(column, new_title)
        if new_path.exists():
            raise FileExistsError(f"Task '{new_title}' already exists in column '{column}'")
        task_path.unlink()
        task_path = new_path

    task_path.write_text(description, encoding="utf-8")


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
