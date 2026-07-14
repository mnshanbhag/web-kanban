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


async def test_end_sprint_rolls_non_done_tasks_into_the_new_sprint_but_not_done_tasks(client):
    sprint_1 = (
        await client.post("/api/sprints/start", json={"name": "Sprint 1", "duration_weeks": 1})
    ).json()

    todo_id = (
        await client.post("/api/tasks", json={"column": "To Do", "title": "Still open"})
    ).json()["id"]
    done_id = (
        await client.post("/api/tasks", json={"column": "To Do", "title": "Completed"})
    ).json()["id"]
    await client.put(f"/api/tasks/{done_id}/move", json={"to_column": "Done"})

    response = await client.post(
        "/api/sprints/end", json={"name": "Sprint 2", "duration_weeks": 1}
    )
    assert response.status_code == 200
    sprint_2 = response.json()
    assert sprint_2["name"] == "Sprint 2"
    assert sprint_2["status"] == "active"

    with storage._session() as session:
        old_sprint = session.get(storage.Sprint, sprint_1["id"])
        assert old_sprint.status == "closed"
        assert old_sprint.closed_at is not None

        todo_task = session.get(storage.Task, storage._parse_id(todo_id))
        assert todo_task.sprint_id == sprint_2["id"]

        done_task = session.get(storage.Task, storage._parse_id(done_id))
        assert done_task.sprint_id == sprint_1["id"]


async def test_ending_a_sprint_leaves_the_new_sprint_as_active(client):
    await client.post("/api/sprints/start", json={"name": "Sprint 1", "duration_weeks": 1})
    ended = (
        await client.post("/api/sprints/end", json={"name": "Sprint 2", "duration_weeks": 1})
    ).json()

    active = (await client.get("/api/sprints/active")).json()
    assert active == ended
    assert active["name"] == "Sprint 2"


async def test_end_sprint_with_none_active_is_rejected(client):
    response = await client.post(
        "/api/sprints/end", json={"name": "Sprint 2", "duration_weeks": 1}
    )

    assert response.status_code == 400


async def test_end_sprint_with_empty_next_name_is_rejected(client):
    await client.post("/api/sprints/start", json={"name": "Sprint 1", "duration_weeks": 1})

    response = await client.post(
        "/api/sprints/end", json={"name": "  ", "duration_weeks": 1}
    )

    assert response.status_code == 400
    active = (await client.get("/api/sprints/active")).json()
    assert active["name"] == "Sprint 1"


async def test_end_sprint_with_invalid_next_duration_is_rejected(client):
    await client.post("/api/sprints/start", json={"name": "Sprint 1", "duration_weeks": 1})

    response = await client.post(
        "/api/sprints/end", json={"name": "Sprint 2", "duration_weeks": 5}
    )

    assert response.status_code == 400
    active = (await client.get("/api/sprints/active")).json()
    assert active["name"] == "Sprint 1"


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


async def test_ending_a_sprint_also_sweeps_up_any_untagged_non_done_task(client):
    """A task created before the very first sprint ever started has no sprint_id; ending the
    first sprint should still pick it up into the next one, same as start_sprint's sweep."""
    task_id = (
        await client.post("/api/tasks", json={"column": "To Do", "title": "Pre-dates sprints"})
    ).json()["id"]
    await client.post("/api/sprints/start", json={"name": "Sprint 1", "duration_weeks": 1})

    sprint_2 = (
        await client.post("/api/sprints/end", json={"name": "Sprint 2", "duration_weeks": 1})
    ).json()

    with storage._session() as session:
        task = session.get(storage.Task, storage._parse_id(task_id))
        assert task.sprint_id == sprint_2["id"]


async def test_ending_multiple_sprints_in_a_row_rolls_task_forward_each_time(client):
    await client.post("/api/sprints/start", json={"name": "Sprint 1", "duration_weeks": 1})
    task_id = (
        await client.post("/api/tasks", json={"column": "To Do", "title": "Carries over"})
    ).json()["id"]

    await client.post("/api/sprints/end", json={"name": "Sprint 2", "duration_weeks": 1})
    sprint_3 = (
        await client.post("/api/sprints/end", json={"name": "Sprint 3", "duration_weeks": 1})
    ).json()

    with storage._session() as session:
        task = session.get(storage.Task, storage._parse_id(task_id))
        assert task.sprint_id == sprint_3["id"]


async def test_get_past_sprints_with_no_closed_sprints_returns_empty_list(client):
    response = await client.get("/api/sprints")

    assert response.status_code == 200
    assert response.json() == []


async def test_get_past_sprints_excludes_the_currently_active_sprint(client):
    await client.post("/api/sprints/start", json={"name": "Sprint 1", "duration_weeks": 1})

    response = await client.get("/api/sprints")

    assert response.status_code == 200
    assert response.json() == []


async def test_get_past_sprints_lists_a_closed_sprint_with_its_completed_tasks(client):
    sprint_1 = (
        await client.post("/api/sprints/start", json={"name": "Sprint 1", "duration_weeks": 1})
    ).json()

    done_id = (
        await client.post("/api/tasks", json={"column": "To Do", "title": "Completed task"})
    ).json()["id"]
    await client.put(f"/api/tasks/{done_id}/move", json={"to_column": "Done"})

    still_open_id = (
        await client.post("/api/tasks", json={"column": "To Do", "title": "Still open"})
    ).json()["id"]

    await client.post("/api/sprints/end", json={"name": "Sprint 2", "duration_weeks": 1})

    response = await client.get("/api/sprints")

    assert response.status_code == 200
    past_sprints = response.json()
    assert len(past_sprints) == 1
    past_sprint = past_sprints[0]
    assert past_sprint["id"] == sprint_1["id"]
    assert past_sprint["name"] == "Sprint 1"
    assert past_sprint["status"] == "closed"
    assert past_sprint["closed_at"] is not None
    assert past_sprint["completed_tasks"] == [{"id": done_id, "title": "Completed task"}]

    completed_ids = [t["id"] for t in past_sprint["completed_tasks"]]
    assert still_open_id not in completed_ids


async def test_get_past_sprints_orders_most_recently_closed_first(client):
    sprint_1 = (
        await client.post("/api/sprints/start", json={"name": "Sprint 1", "duration_weeks": 1})
    ).json()
    sprint_2 = (
        await client.post("/api/sprints/end", json={"name": "Sprint 2", "duration_weeks": 1})
    ).json()
    sprint_3 = (
        await client.post("/api/sprints/end", json={"name": "Sprint 3", "duration_weeks": 1})
    ).json()
    await client.post("/api/sprints/end", json={"name": "Sprint 4", "duration_weeks": 1})

    response = await client.get("/api/sprints")

    assert response.status_code == 200
    past_sprint_ids = [s["id"] for s in response.json()]
    assert past_sprint_ids == [sprint_3["id"], sprint_2["id"], sprint_1["id"]]


async def test_get_past_sprints_excludes_trashed_completed_tasks(client):
    await client.post("/api/sprints/start", json={"name": "Sprint 1", "duration_weeks": 1})

    done_id = (
        await client.post("/api/tasks", json={"column": "To Do", "title": "Completed task"})
    ).json()["id"]
    await client.put(f"/api/tasks/{done_id}/move", json={"to_column": "Done"})
    await client.delete(f"/api/tasks/{done_id}")

    await client.post("/api/sprints/end", json={"name": "Sprint 2", "duration_weeks": 1})

    response = await client.get("/api/sprints")

    assert response.status_code == 200
    assert response.json()[0]["completed_tasks"] == []
