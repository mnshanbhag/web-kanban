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
    assert content.endswith("Cover the API with pytest and httpx.")

    get_response = await client.get("/api/tasks")

    assert get_response.status_code == 200
    board = get_response.json()
    assert board["To Do"] == [
        {
            "id": task_id,
            "title": "Write tests",
            "description": "Cover the API with pytest and httpx.",
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
