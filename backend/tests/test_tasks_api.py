import threading

import httpx
import pytest

from backend import main, storage


@pytest.fixture(autouse=True)
def isolated_data_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DATA_DIR", tmp_path)


@pytest.fixture
async def client():
    transport = httpx.ASGITransport(app=main.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def test_post_persists_task_to_sqlite_and_get_reads_it_back(client, tmp_path):
    response = await client.post(
        "/api/tasks",
        json={
            "column": "To Do",
            "title": "Write tests",
            "description": "Cover the API with pytest and httpx.",
        },
    )

    assert response.status_code == 201
    task_id = response.json()["id"]
    assert task_id == "KAN-01"

    assert (tmp_path / "kanban.db").is_file()
    with storage._session() as session:
        row = session.get(storage.Task, 1)
        assert row is not None
        assert row.title == "Write tests"
        assert row.description == "Cover the API with pytest and httpx."
        assert row.column == "To Do"
        assert row.priority == "Medium"
        assert row.deleted_at is None

    get_response = await client.get("/api/tasks")

    assert get_response.status_code == 200
    board = get_response.json()
    assert board["To Do"] == [
        {
            "id": task_id,
            "title": "Write tests",
            "description": "Cover the API with pytest and httpx.",
            "priority": "Medium",
            "blocked_by": None,
            "blocks": [],
            "due_date": None,
            "subtask_total": 0,
            "subtask_done": 0,
        }
    ]


async def test_set_blocked_by_links_blocker_and_backlinks(client):
    kan_1 = (
        await client.post("/api/tasks", json={"column": "To Do", "title": "Design schema"})
    ).json()["id"]
    kan_2 = (
        await client.post("/api/tasks", json={"column": "To Do", "title": "Build endpoint"})
    ).json()["id"]

    block_response = await client.put(
        f"/api/tasks/{kan_2}/blocked-by", json={"blocked_by": kan_1}
    )
    assert block_response.status_code == 200

    board = (await client.get("/api/tasks")).json()

    dependent = next(t for t in board["To Do"] if t["id"] == kan_2)
    assert dependent["blocked_by"] == kan_1

    blocker = next(t for t in board["To Do"] if t["id"] == kan_1)
    assert blocker["blocks"] == [kan_2]


async def test_blocked_task_can_stay_in_any_non_done_column(client):
    kan_1 = (
        await client.post("/api/tasks", json={"column": "To Do", "title": "Blocker"})
    ).json()["id"]
    kan_2 = (
        await client.post("/api/tasks", json={"column": "In Progress", "title": "Dependent"})
    ).json()["id"]

    response = await client.put(f"/api/tasks/{kan_2}/blocked-by", json={"blocked_by": kan_1})
    assert response.status_code == 200

    board = (await client.get("/api/tasks")).json()
    assert board["In Progress"][0]["blocked_by"] == kan_1


async def test_clearing_blocked_by_unblocks_the_task(client):
    kan_1 = (await client.post("/api/tasks", json={"column": "To Do", "title": "A"})).json()["id"]
    kan_2 = (await client.post("/api/tasks", json={"column": "To Do", "title": "B"})).json()["id"]
    await client.put(f"/api/tasks/{kan_2}/blocked-by", json={"blocked_by": kan_1})

    response = await client.put(f"/api/tasks/{kan_2}/blocked-by", json={"blocked_by": None})
    assert response.status_code == 200

    board = (await client.get("/api/tasks")).json()
    dependent = next(t for t in board["To Do"] if t["id"] == kan_2)
    assert dependent["blocked_by"] is None


async def test_set_blocked_by_with_nonexistent_blocker_fails(client):
    kan_1 = (
        await client.post("/api/tasks", json={"column": "To Do", "title": "Solo task"})
    ).json()["id"]

    response = await client.put(f"/api/tasks/{kan_1}/blocked-by", json={"blocked_by": "KAN-99"})

    assert response.status_code == 400


async def test_cannot_move_a_blocked_task_to_done(client):
    kan_1 = (await client.post("/api/tasks", json={"column": "To Do", "title": "Blocker"})).json()[
        "id"
    ]
    kan_2 = (
        await client.post("/api/tasks", json={"column": "To Do", "title": "Dependent"})
    ).json()["id"]
    await client.put(f"/api/tasks/{kan_2}/blocked-by", json={"blocked_by": kan_1})

    response = await client.put(f"/api/tasks/{kan_2}/move", json={"to_column": "Done"})

    assert response.status_code == 400
    board = (await client.get("/api/tasks")).json()
    assert any(t["id"] == kan_2 for t in board["To Do"])


async def test_completing_a_task_clears_blocked_by_on_its_dependents(client):
    kan_1 = (await client.post("/api/tasks", json={"column": "To Do", "title": "Blocker"})).json()[
        "id"
    ]
    kan_2 = (
        await client.post("/api/tasks", json={"column": "To Do", "title": "Dependent"})
    ).json()["id"]
    await client.put(f"/api/tasks/{kan_2}/blocked-by", json={"blocked_by": kan_1})

    move_response = await client.put(f"/api/tasks/{kan_1}/move", json={"to_column": "Done"})
    assert move_response.status_code == 200

    board = (await client.get("/api/tasks")).json()
    dependent = next(t for t in board["To Do"] if t["id"] == kan_2)
    assert dependent["blocked_by"] is None


async def test_cannot_block_on_a_task_that_is_already_done(client):
    kan_1 = (await client.post("/api/tasks", json={"column": "To Do", "title": "Finished"})).json()[
        "id"
    ]
    await client.put(f"/api/tasks/{kan_1}/move", json={"to_column": "Done"})
    kan_2 = (
        await client.post("/api/tasks", json={"column": "To Do", "title": "Waiting"})
    ).json()["id"]

    response = await client.put(f"/api/tasks/{kan_2}/blocked-by", json={"blocked_by": kan_1})

    assert response.status_code == 400


async def test_cannot_create_task_as_done_while_blocked(client):
    kan_1 = (await client.post("/api/tasks", json={"column": "To Do", "title": "Blocker"})).json()[
        "id"
    ]

    response = await client.post(
        "/api/tasks", json={"column": "Done", "title": "Impossible", "blocked_by": kan_1}
    )

    assert response.status_code == 400


async def test_create_task_with_explicit_priority(client):
    response = await client.post(
        "/api/tasks",
        json={"column": "To Do", "title": "Fix outage", "priority": "Urgent"},
    )

    assert response.status_code == 201
    board = (await client.get("/api/tasks")).json()
    assert board["To Do"][0]["priority"] == "Urgent"


async def test_create_task_with_invalid_priority_is_rejected(client):
    response = await client.post(
        "/api/tasks",
        json={"column": "To Do", "title": "Bad priority", "priority": "Not A Priority"},
    )

    assert response.status_code == 400


async def test_update_priority_endpoint_changes_priority(client):
    create_response = await client.post(
        "/api/tasks", json={"column": "To Do", "title": "Escalate me"}
    )
    task_id = create_response.json()["id"]

    update_response = await client.put(
        f"/api/tasks/{task_id}/priority", json={"priority": "High"}
    )
    assert update_response.status_code == 200

    board = (await client.get("/api/tasks")).json()
    assert board["To Do"][0]["priority"] == "High"


async def test_update_priority_with_invalid_value_is_rejected(client):
    create_response = await client.post(
        "/api/tasks", json={"column": "To Do", "title": "Task"}
    )
    task_id = create_response.json()["id"]

    response = await client.put(f"/api/tasks/{task_id}/priority", json={"priority": "Nope"})

    assert response.status_code == 400


async def test_delete_soft_deletes_instead_of_removing_the_row(client):
    kan_1 = (
        await client.post(
            "/api/tasks",
            json={"column": "To Do", "title": "Doomed task", "description": "bye"},
        )
    ).json()["id"]

    delete_response = await client.delete(f"/api/tasks/{kan_1}")
    assert delete_response.status_code == 204

    with storage._session() as session:
        row = session.get(storage.Task, 1)
        assert row is not None
        assert row.deleted_at is not None

    board = (await client.get("/api/tasks")).json()
    assert board.get("To Do", []) == []

    trash = (await client.get("/api/trash")).json()
    assert trash == [
        {
            "id": kan_1,
            "title": "Doomed task",
            "description": "bye",
            "priority": "Medium",
            "deleted_from": "To Do",
            "deleted_at": trash[0]["deleted_at"],
        }
    ]


async def test_trash_deleted_at_is_timezone_aware(client):
    kan_1 = (await client.post("/api/tasks", json={"column": "To Do", "title": "X"})).json()["id"]
    await client.delete(f"/api/tasks/{kan_1}")

    trash = (await client.get("/api/trash")).json()
    deleted_at = trash[0]["deleted_at"]

    from datetime import datetime

    parsed = datetime.fromisoformat(deleted_at)
    assert parsed.tzinfo is not None


async def test_restore_puts_task_back_in_its_original_column(client):
    kan_1 = (
        await client.post("/api/tasks", json={"column": "In Progress", "title": "Restore me"})
    ).json()["id"]
    await client.delete(f"/api/tasks/{kan_1}")

    restore_response = await client.post(f"/api/trash/{kan_1}/restore")
    assert restore_response.status_code == 200
    assert restore_response.json() == {"id": kan_1, "column": "In Progress"}

    board = (await client.get("/api/tasks")).json()
    assert board["In Progress"][0]["id"] == kan_1
    assert (await client.get("/api/trash")).json() == []


async def test_restored_task_keeps_its_priority(client):
    kan_1 = (
        await client.post(
            "/api/tasks", json={"column": "To Do", "title": "Urgent restore", "priority": "Urgent"}
        )
    ).json()["id"]
    await client.delete(f"/api/tasks/{kan_1}")
    await client.post(f"/api/trash/{kan_1}/restore")

    board = (await client.get("/api/tasks")).json()
    assert board["To Do"][0]["priority"] == "Urgent"


async def test_permanent_delete_removes_the_row_entirely(client):
    kan_1 = (
        await client.post("/api/tasks", json={"column": "To Do", "title": "Gone forever"})
    ).json()["id"]
    await client.delete(f"/api/tasks/{kan_1}")

    response = await client.delete(f"/api/trash/{kan_1}")
    assert response.status_code == 204

    assert (await client.get("/api/trash")).json() == []
    with storage._session() as session:
        assert session.get(storage.Task, 1) is None


async def test_empty_trash_removes_all_trashed_tasks(client):
    kan_1 = (await client.post("/api/tasks", json={"column": "To Do", "title": "A"})).json()["id"]
    kan_2 = (await client.post("/api/tasks", json={"column": "To Do", "title": "B"})).json()["id"]
    await client.delete(f"/api/tasks/{kan_1}")
    await client.delete(f"/api/tasks/{kan_2}")

    response = await client.delete("/api/trash")
    assert response.status_code == 200
    assert response.json() == {"deleted": 2}

    assert (await client.get("/api/trash")).json() == []


async def test_permanently_deleted_id_is_never_reused(client):
    kan_1 = (
        await client.post("/api/tasks", json={"column": "To Do", "title": "First"})
    ).json()["id"]
    assert kan_1 == "KAN-01"

    await client.delete(f"/api/tasks/{kan_1}")
    await client.delete(f"/api/trash/{kan_1}")

    kan_2 = (
        await client.post("/api/tasks", json={"column": "To Do", "title": "Second"})
    ).json()["id"]

    assert kan_2 == "KAN-02"
    assert kan_2 != kan_1


async def test_permanently_deleting_a_blocker_nulls_out_dependents(client):
    kan_1 = (
        await client.post("/api/tasks", json={"column": "To Do", "title": "Blocker"})
    ).json()["id"]
    kan_2 = (
        await client.post("/api/tasks", json={"column": "To Do", "title": "Dependent"})
    ).json()["id"]
    await client.put(f"/api/tasks/{kan_2}/blocked-by", json={"blocked_by": kan_1})

    await client.delete(f"/api/tasks/{kan_1}")
    await client.delete(f"/api/trash/{kan_1}")

    board = (await client.get("/api/tasks")).json()
    dependent = next(t for t in board["To Do"] if t["id"] == kan_2)
    assert dependent["blocked_by"] is None


async def test_restoring_a_task_clears_a_now_done_blocker(client):
    kan_1 = (await client.post("/api/tasks", json={"column": "To Do", "title": "Blocker"})).json()[
        "id"
    ]
    kan_2 = (
        await client.post("/api/tasks", json={"column": "To Do", "title": "Dependent"})
    ).json()["id"]
    await client.put(f"/api/tasks/{kan_2}/blocked-by", json={"blocked_by": kan_1})
    await client.delete(f"/api/tasks/{kan_2}")

    await client.put(f"/api/tasks/{kan_1}/move", json={"to_column": "Done"})

    restore_response = await client.post(f"/api/trash/{kan_2}/restore")
    assert restore_response.status_code == 200

    board = (await client.get("/api/tasks")).json()
    restored = next(t for t in board["To Do"] if t["id"] == kan_2)
    assert restored["blocked_by"] is None


async def test_create_task_with_due_date_round_trips(client):
    response = await client.post(
        "/api/tasks",
        json={"column": "To Do", "title": "Ship it", "due_date": "2026-07-15"},
    )

    assert response.status_code == 201
    board = (await client.get("/api/tasks")).json()
    task = board["To Do"][0]
    assert task["due_date"] is not None
    assert task["due_date"].startswith("2026-07-15")


async def test_create_task_without_due_date_leaves_it_null(client):
    response = await client.post(
        "/api/tasks", json={"column": "To Do", "title": "No deadline"}
    )

    assert response.status_code == 201
    board = (await client.get("/api/tasks")).json()
    assert board["To Do"][0]["due_date"] is None


async def test_set_due_date_endpoint_sets_and_clears(client):
    task_id = (
        await client.post("/api/tasks", json={"column": "To Do", "title": "Deadline task"})
    ).json()["id"]

    set_response = await client.put(
        f"/api/tasks/{task_id}/due-date", json={"due_date": "2026-08-01"}
    )
    assert set_response.status_code == 200

    board = (await client.get("/api/tasks")).json()
    task = next(t for t in board["To Do"] if t["id"] == task_id)
    assert task["due_date"].startswith("2026-08-01")

    clear_response = await client.put(
        f"/api/tasks/{task_id}/due-date", json={"due_date": None}
    )
    assert clear_response.status_code == 200

    board = (await client.get("/api/tasks")).json()
    task = next(t for t in board["To Do"] if t["id"] == task_id)
    assert task["due_date"] is None


async def test_due_date_can_be_set_and_cleared_on_a_done_task(client):
    """Unlike blocking, due dates have no column restriction: a Done task can
    still carry or clear a due date."""
    task_id = (
        await client.post("/api/tasks", json={"column": "To Do", "title": "Finish me"})
    ).json()["id"]
    await client.put(f"/api/tasks/{task_id}/move", json={"to_column": "Done"})

    set_response = await client.put(
        f"/api/tasks/{task_id}/due-date", json={"due_date": "2026-07-01"}
    )
    assert set_response.status_code == 200

    board = (await client.get("/api/tasks")).json()
    task = next(t for t in board["Done"] if t["id"] == task_id)
    assert task["due_date"].startswith("2026-07-01")

    clear_response = await client.put(
        f"/api/tasks/{task_id}/due-date", json={"due_date": None}
    )
    assert clear_response.status_code == 200

    board = (await client.get("/api/tasks")).json()
    task = next(t for t in board["Done"] if t["id"] == task_id)
    assert task["due_date"] is None


async def test_set_due_date_on_nonexistent_task_returns_404(client):
    response = await client.put(
        "/api/tasks/KAN-99/due-date", json={"due_date": "2026-07-01"}
    )

    assert response.status_code == 404


async def test_due_date_is_timezone_aware(client):
    task_id = (
        await client.post(
            "/api/tasks",
            json={"column": "To Do", "title": "Timezone check", "due_date": "2026-07-15"},
        )
    ).json()["id"]

    board = (await client.get("/api/tasks")).json()
    task = next(t for t in board["To Do"] if t["id"] == task_id)

    from datetime import datetime

    parsed = datetime.fromisoformat(task["due_date"])
    assert parsed.tzinfo is not None


async def test_task_can_be_created_and_moved_into_in_review(client):
    kan_1 = (
        await client.post("/api/tasks", json={"column": "In Progress", "title": "Ship feature"})
    ).json()["id"]

    move_response = await client.put(f"/api/tasks/{kan_1}/move", json={"to_column": "In Review"})
    assert move_response.status_code == 200

    board = (await client.get("/api/tasks")).json()
    assert board["In Review"][0]["id"] == kan_1
    assert board.get("In Progress", []) == []


async def test_blocked_task_can_stay_in_in_review(client):
    kan_1 = (
        await client.post("/api/tasks", json={"column": "To Do", "title": "Blocker"})
    ).json()["id"]
    kan_2 = (
        await client.post("/api/tasks", json={"column": "In Review", "title": "Dependent"})
    ).json()["id"]

    response = await client.put(f"/api/tasks/{kan_2}/blocked-by", json={"blocked_by": kan_1})
    assert response.status_code == 200

    board = (await client.get("/api/tasks")).json()
    assert board["In Review"][0]["blocked_by"] == kan_1


async def test_cannot_move_a_blocked_task_from_in_review_to_done(client):
    kan_1 = (
        await client.post("/api/tasks", json={"column": "To Do", "title": "Blocker"})
    ).json()["id"]
    kan_2 = (
        await client.post("/api/tasks", json={"column": "In Review", "title": "Dependent"})
    ).json()["id"]
    await client.put(f"/api/tasks/{kan_2}/blocked-by", json={"blocked_by": kan_1})

    response = await client.put(f"/api/tasks/{kan_2}/move", json={"to_column": "Done"})

    assert response.status_code == 400
    board = (await client.get("/api/tasks")).json()
    assert any(t["id"] == kan_2 for t in board["In Review"])


async def test_completing_a_blocker_from_in_review_clears_dependents(client):
    kan_1 = (
        await client.post("/api/tasks", json={"column": "In Review", "title": "Blocker"})
    ).json()["id"]
    kan_2 = (
        await client.post("/api/tasks", json={"column": "To Do", "title": "Dependent"})
    ).json()["id"]
    await client.put(f"/api/tasks/{kan_2}/blocked-by", json={"blocked_by": kan_1})

    move_response = await client.put(f"/api/tasks/{kan_1}/move", json={"to_column": "Done"})
    assert move_response.status_code == 200

    board = (await client.get("/api/tasks")).json()
    dependent = next(t for t in board["To Do"] if t["id"] == kan_2)
    assert dependent["blocked_by"] is None


async def test_engine_creation_is_thread_safe_under_concurrent_first_access(tmp_path):
    """Regression test: the frontend fires GET /api/tasks and GET /api/trash
    concurrently on page load, and FastAPI runs sync handlers in a thread
    pool. Without a lock around schema creation, two threads racing through
    _engine() for the same never-before-seen DATA_DIR both try to
    CREATE TABLE and SQLite raises 'table tasks already exists'."""
    errors = []

    def touch():
        try:
            storage._engine()
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=touch) for _ in range(16)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert errors == []


async def test_create_subtask_returns_it_and_lists_it(client):
    task_id = (
        await client.post("/api/tasks", json={"column": "To Do", "title": "Ship feature"})
    ).json()["id"]

    response = await client.post(
        f"/api/tasks/{task_id}/subtasks", json={"title": "Write tests"}
    )
    assert response.status_code == 201
    subtask = response.json()
    assert subtask["title"] == "Write tests"
    assert subtask["done"] is False
    assert subtask["position"] == 0

    list_response = await client.get(f"/api/tasks/{task_id}/subtasks")
    assert list_response.status_code == 200
    assert list_response.json() == [subtask]


async def test_subtasks_are_ordered_by_creation(client):
    task_id = (
        await client.post("/api/tasks", json={"column": "To Do", "title": "Ship feature"})
    ).json()["id"]

    await client.post(f"/api/tasks/{task_id}/subtasks", json={"title": "First"})
    await client.post(f"/api/tasks/{task_id}/subtasks", json={"title": "Second"})

    subtasks = (await client.get(f"/api/tasks/{task_id}/subtasks")).json()
    assert [s["title"] for s in subtasks] == ["First", "Second"]
    assert [s["position"] for s in subtasks] == [0, 1]


async def test_toggle_subtask_done_updates_board_counts(client):
    task_id = (
        await client.post("/api/tasks", json={"column": "To Do", "title": "Ship feature"})
    ).json()["id"]
    sub_1 = (
        await client.post(f"/api/tasks/{task_id}/subtasks", json={"title": "First"})
    ).json()
    await client.post(f"/api/tasks/{task_id}/subtasks", json={"title": "Second"})

    board = (await client.get("/api/tasks")).json()
    task = next(t for t in board["To Do"] if t["id"] == task_id)
    assert task["subtask_total"] == 2
    assert task["subtask_done"] == 0

    toggle_response = await client.put(
        f"/api/tasks/{task_id}/subtasks/{sub_1['id']}", json={"done": True}
    )
    assert toggle_response.status_code == 200
    assert toggle_response.json()["done"] is True

    board = (await client.get("/api/tasks")).json()
    task = next(t for t in board["To Do"] if t["id"] == task_id)
    assert task["subtask_total"] == 2
    assert task["subtask_done"] == 1


async def test_delete_subtask_removes_it_and_updates_counts(client):
    task_id = (
        await client.post("/api/tasks", json={"column": "To Do", "title": "Ship feature"})
    ).json()["id"]
    subtask = (
        await client.post(f"/api/tasks/{task_id}/subtasks", json={"title": "First"})
    ).json()

    delete_response = await client.delete(f"/api/tasks/{task_id}/subtasks/{subtask['id']}")
    assert delete_response.status_code == 204

    assert (await client.get(f"/api/tasks/{task_id}/subtasks")).json() == []

    board = (await client.get("/api/tasks")).json()
    task = next(t for t in board["To Do"] if t["id"] == task_id)
    assert task["subtask_total"] == 0
    assert task["subtask_done"] == 0


async def test_permanently_deleting_task_cascades_to_its_subtasks(client):
    task_id = (
        await client.post("/api/tasks", json={"column": "To Do", "title": "Ship feature"})
    ).json()["id"]
    subtask = (
        await client.post(f"/api/tasks/{task_id}/subtasks", json={"title": "First"})
    ).json()

    await client.delete(f"/api/tasks/{task_id}")
    await client.delete(f"/api/trash/{task_id}")

    with storage._session() as session:
        assert session.get(storage.Task, storage._parse_id(task_id)) is None
        assert session.get(storage.TaskSubtask, subtask["id"]) is None


async def test_subtask_completion_never_affects_blocking_or_done_eligibility(client):
    kan_1 = (
        await client.post("/api/tasks", json={"column": "To Do", "title": "Blocker"})
    ).json()["id"]
    kan_2 = (
        await client.post("/api/tasks", json={"column": "To Do", "title": "Dependent"})
    ).json()["id"]
    await client.put(f"/api/tasks/{kan_2}/blocked-by", json={"blocked_by": kan_1})

    subtask = (
        await client.post(f"/api/tasks/{kan_2}/subtasks", json={"title": "Checklist item"})
    ).json()
    toggle_response = await client.put(
        f"/api/tasks/{kan_2}/subtasks/{subtask['id']}", json={"done": True}
    )
    assert toggle_response.status_code == 200

    board = (await client.get("/api/tasks")).json()
    dependent = next(t for t in board["To Do"] if t["id"] == kan_2)
    assert dependent["blocked_by"] == kan_1

    move_response = await client.put(f"/api/tasks/{kan_2}/move", json={"to_column": "Done"})
    assert move_response.status_code == 400


async def test_task_with_unchecked_subtasks_can_still_move_to_done(client):
    task_id = (
        await client.post("/api/tasks", json={"column": "To Do", "title": "Ship feature"})
    ).json()["id"]
    await client.post(f"/api/tasks/{task_id}/subtasks", json={"title": "Not done yet"})

    move_response = await client.put(f"/api/tasks/{task_id}/move", json={"to_column": "Done"})
    assert move_response.status_code == 200

    board = (await client.get("/api/tasks")).json()
    task = next(t for t in board["Done"] if t["id"] == task_id)
    assert task["subtask_total"] == 1
    assert task["subtask_done"] == 0


async def test_subtask_endpoints_404_for_nonexistent_task(client):
    response = await client.post("/api/tasks/KAN-99/subtasks", json={"title": "X"})
    assert response.status_code == 404

    response = await client.get("/api/tasks/KAN-99/subtasks")
    assert response.status_code == 404


async def test_subtask_id_mismatched_with_task_returns_404(client):
    kan_1 = (
        await client.post("/api/tasks", json={"column": "To Do", "title": "A"})
    ).json()["id"]
    kan_2 = (
        await client.post("/api/tasks", json={"column": "To Do", "title": "B"})
    ).json()["id"]
    subtask = (
        await client.post(f"/api/tasks/{kan_1}/subtasks", json={"title": "Belongs to A"})
    ).json()

    response = await client.put(
        f"/api/tasks/{kan_2}/subtasks/{subtask['id']}", json={"done": True}
    )
    assert response.status_code == 404

    response = await client.delete(f"/api/tasks/{kan_2}/subtasks/{subtask['id']}")
    assert response.status_code == 404


async def test_create_subtask_with_empty_title_is_rejected(client):
    task_id = (
        await client.post("/api/tasks", json={"column": "To Do", "title": "Ship feature"})
    ).json()["id"]

    response = await client.post(f"/api/tasks/{task_id}/subtasks", json={"title": "   "})
    assert response.status_code == 400
