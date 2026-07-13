from datetime import date, timedelta

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


async def test_get_active_sprint_with_none_active_returns_null(client):
    response = await client.get("/api/sprints/active")

    assert response.status_code == 200
    assert response.json() is None


async def test_start_sprint_creates_active_sprint_with_correct_date_range(client):
    response = await client.post(
        "/api/sprints/start", json={"name": "Sprint 1", "duration_weeks": 2}
    )

    assert response.status_code == 200
    sprint = response.json()
    assert sprint["name"] == "Sprint 1"
    assert sprint["status"] == "active"
    assert sprint["closed_at"] is None

    today = date.today()
    assert sprint["start_date"] == today.isoformat()
    assert sprint["end_date"] == (today + timedelta(weeks=2)).isoformat()

    active = (await client.get("/api/sprints/active")).json()
    assert active == sprint


async def test_starting_a_sprint_sweeps_up_untagged_non_done_tasks(client):
    todo_id = (
        await client.post("/api/tasks", json={"column": "To Do", "title": "Untagged task"})
    ).json()["id"]
    done_id = (
        await client.post("/api/tasks", json={"column": "To Do", "title": "Finished task"})
    ).json()["id"]
    await client.put(f"/api/tasks/{done_id}/move", json={"to_column": "Done"})

    sprint = (
        await client.post("/api/sprints/start", json={"name": "Sprint 1", "duration_weeks": 1})
    ).json()

    with storage._session() as session:
        todo_task = session.get(storage.Task, storage._parse_id(todo_id))
        assert todo_task.sprint_id == sprint["id"]

        done_task = session.get(storage.Task, storage._parse_id(done_id))
        assert done_task.sprint_id is None


async def test_new_task_auto_joins_the_active_sprint(client):
    sprint = (
        await client.post("/api/sprints/start", json={"name": "Sprint 1", "duration_weeks": 1})
    ).json()

    task_id = (
        await client.post("/api/tasks", json={"column": "To Do", "title": "Created mid-sprint"})
    ).json()["id"]

    with storage._session() as session:
        task = session.get(storage.Task, storage._parse_id(task_id))
        assert task.sprint_id == sprint["id"]


async def test_new_task_without_active_sprint_has_no_sprint_id(client):
    task_id = (
        await client.post("/api/tasks", json={"column": "To Do", "title": "No sprint"})
    ).json()["id"]

    with storage._session() as session:
        task = session.get(storage.Task, storage._parse_id(task_id))
        assert task.sprint_id is None


async def test_only_one_sprint_can_be_active_at_a_time(client):
    await client.post("/api/sprints/start", json={"name": "Sprint 1", "duration_weeks": 1})

    response = await client.post(
        "/api/sprints/start", json={"name": "Sprint 2", "duration_weeks": 2}
    )

    assert response.status_code == 400


async def test_end_sprint_clears_sprint_id_from_non_done_tasks_but_not_done_tasks(client):
    await client.post("/api/sprints/start", json={"name": "Sprint 1", "duration_weeks": 1})

    todo_id = (
        await client.post("/api/tasks", json={"column": "To Do", "title": "Still open"})
    ).json()["id"]
    done_id = (
        await client.post("/api/tasks", json={"column": "To Do", "title": "Completed"})
    ).json()["id"]
    await client.put(f"/api/tasks/{done_id}/move", json={"to_column": "Done"})

    response = await client.post("/api/sprints/end")
    assert response.status_code == 200
    ended = response.json()
    assert ended["status"] == "closed"
    assert ended["closed_at"] is not None

    with storage._session() as session:
        todo_task = session.get(storage.Task, storage._parse_id(todo_id))
        assert todo_task.sprint_id is None

        done_task = session.get(storage.Task, storage._parse_id(done_id))
        assert done_task.sprint_id is not None


async def test_ending_a_sprint_closed_at_is_timezone_aware(client):
    await client.post("/api/sprints/start", json={"name": "Sprint 1", "duration_weeks": 1})

    response = await client.post("/api/sprints/end")
    closed_at = response.json()["closed_at"]

    from datetime import datetime

    parsed = datetime.fromisoformat(closed_at)
    assert parsed.tzinfo is not None


async def test_ending_a_sprint_clears_active_sprint(client):
    await client.post("/api/sprints/start", json={"name": "Sprint 1", "duration_weeks": 1})
    await client.post("/api/sprints/end")

    active = (await client.get("/api/sprints/active")).json()
    assert active is None


async def test_end_sprint_with_none_active_is_rejected(client):
    response = await client.post("/api/sprints/end")

    assert response.status_code == 400


async def test_start_sprint_with_invalid_duration_is_rejected(client):
    response = await client.post(
        "/api/sprints/start", json={"name": "Sprint 1", "duration_weeks": 5}
    )

    assert response.status_code == 400


async def test_start_sprint_with_empty_name_is_rejected(client):
    response = await client.post(
        "/api/sprints/start", json={"name": "   ", "duration_weeks": 1}
    )

    assert response.status_code == 400


async def test_starting_a_second_sprint_after_the_first_ends_sweeps_rolled_over_task(client):
    """Incomplete work from a closed sprint (now untagged) rolls forward into the next one."""
    await client.post("/api/sprints/start", json={"name": "Sprint 1", "duration_weeks": 1})
    task_id = (
        await client.post("/api/tasks", json={"column": "To Do", "title": "Carries over"})
    ).json()["id"]
    await client.post("/api/sprints/end")

    sprint_2 = (
        await client.post("/api/sprints/start", json={"name": "Sprint 2", "duration_weeks": 1})
    ).json()

    with storage._session() as session:
        task = session.get(storage.Task, storage._parse_id(task_id))
        assert task.sprint_id == sprint_2["id"]
