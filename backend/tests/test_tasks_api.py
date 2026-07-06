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
    assert task_id == "To Do::Write tests"

    task_file = tmp_path / "To Do" / "Write tests.md"
    assert task_file.is_file()
    content = task_file.read_text(encoding="utf-8")
    assert "priority: Medium" in content
    assert content.endswith("Cover the API with pytest and httpx.")

    get_response = await client.get("/api/tasks")

    assert get_response.status_code == 200
    board = get_response.json()
    assert board["To Do"] == [
        {
            "title": "Write tests",
            "description": "Cover the API with pytest and httpx.",
            "priority": "Medium",
            "id": task_id,
        }
    ]


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
