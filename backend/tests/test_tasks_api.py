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
