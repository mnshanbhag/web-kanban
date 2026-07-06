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


async def test_post_writes_markdown_file_and_get_reads_it_back(client, tmp_path):
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

    task_file = tmp_path / "To Do" / "Write tests.md"
    assert task_file.is_file()
    content = task_file.read_text(encoding="utf-8")
    assert "id: KAN-01" in content
    assert "priority: Medium" in content
    assert content.endswith("Cover the API with pytest and httpx.")

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


async def test_move_to_blocked_links_blocker_and_backlinks(client):
    kan_1 = (
        await client.post("/api/tasks", json={"column": "To Do", "title": "Design schema"})
    ).json()["id"]
    kan_2 = (
        await client.post("/api/tasks", json={"column": "To Do", "title": "Build endpoint"})
    ).json()["id"]

    move_response = await client.put(
        f"/api/tasks/{kan_2}/move",
        json={"to_column": "Blocked", "blocked_by": kan_1},
    )
    assert move_response.status_code == 200

    board = (await client.get("/api/tasks")).json()

    blocked_task = board["Blocked"][0]
    assert blocked_task["id"] == kan_2
    assert blocked_task["blocked_by"] == kan_1

    blocker_task = board["To Do"][0]
    assert blocker_task["id"] == kan_1
    assert blocker_task["blocks"] == [kan_2]


async def test_move_to_blocked_without_blocker_fails(client):
    kan_1 = (
        await client.post("/api/tasks", json={"column": "To Do", "title": "Solo task"})
    ).json()["id"]

    response = await client.put(f"/api/tasks/{kan_1}/move", json={"to_column": "Blocked"})

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


async def test_delete_moves_task_to_trash_instead_of_removing_it(client, tmp_path):
    kan_1 = (
        await client.post(
            "/api/tasks",
            json={"column": "To Do", "title": "Doomed task", "description": "bye"},
        )
    ).json()["id"]

    delete_response = await client.delete(f"/api/tasks/{kan_1}")
    assert delete_response.status_code == 204

    assert not (tmp_path / "To Do" / "Doomed task.md").exists()
    assert (tmp_path / ".trash" / f"{kan_1}.md").is_file()

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


async def test_permanent_delete_removes_task_from_trash(client, tmp_path):
    kan_1 = (
        await client.post("/api/tasks", json={"column": "To Do", "title": "Gone forever"})
    ).json()["id"]
    await client.delete(f"/api/tasks/{kan_1}")

    response = await client.delete(f"/api/trash/{kan_1}")
    assert response.status_code == 204

    assert (await client.get("/api/trash")).json() == []
    assert not (tmp_path / ".trash" / f"{kan_1}.md").exists()


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
