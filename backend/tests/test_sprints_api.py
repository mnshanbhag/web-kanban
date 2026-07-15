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


async def test_ending_a_sprint_sets_its_end_date_to_today_not_its_original_target(client):
    """A sprint's end_date at start time is only a target -- ending it early or late than that
    should overwrite it with the real closing date, not leave the original target in place."""
    sprint_1 = (
        await client.post("/api/sprints/start", json={"name": "Sprint 1", "duration_weeks": 4})
    ).json()
    assert sprint_1["end_date"] == (date.today() + timedelta(weeks=4)).isoformat()

    await client.post("/api/sprints/end", json={"name": "Sprint 2", "duration_weeks": 1})

    with storage._session() as session:
        closed_sprint = session.get(storage.Sprint, sprint_1["id"])
        assert closed_sprint.end_date == date.today()


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


async def test_start_sprint_rejects_a_name_already_used_by_a_previous_sprint(client):
    """end_sprint never leaves the board without an active sprint, so start_sprint can't
    normally be reached again after the first-ever call -- exercise its own name check
    directly at the storage layer regardless, as a defensive backstop."""
    await client.post("/api/sprints/start", json={"name": "Sprint X", "duration_weeks": 1})
    with storage._session() as session:
        active = (
            session.query(storage.Sprint)
            .filter(storage.Sprint.status == storage.SPRINT_STATUS_ACTIVE)
            .first()
        )
        active.status = storage.SPRINT_STATUS_CLOSED
        session.commit()

    with pytest.raises(FileExistsError):
        storage.start_sprint("Sprint X", 1)


async def test_plan_next_sprint_rejects_a_name_already_used_by_a_closed_sprint(client):
    await client.post("/api/sprints/start", json={"name": "Sprint X", "duration_weeks": 1})
    await client.post("/api/sprints/end", json={"name": "Sprint Y", "duration_weeks": 1})

    response = await client.post(
        "/api/sprints/plan", json={"name": "Sprint X", "duration_weeks": 1}
    )

    assert response.status_code == 409
    assert (await client.get("/api/sprints/planned")).json() is None


async def test_end_sprint_rejects_a_next_name_already_used_by_a_closed_sprint(client):
    await client.post("/api/sprints/start", json={"name": "Sprint X", "duration_weeks": 1})
    await client.post("/api/sprints/end", json={"name": "Sprint Y", "duration_weeks": 1})

    response = await client.post(
        "/api/sprints/end", json={"name": "Sprint X", "duration_weeks": 1}
    )

    assert response.status_code == 409
    active = (await client.get("/api/sprints/active")).json()
    assert active["name"] == "Sprint Y"


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


async def test_get_planned_sprint_with_none_planned_returns_null(client):
    response = await client.get("/api/sprints/planned")

    assert response.status_code == 200
    assert response.json() is None


async def test_planning_a_sprint_requires_an_active_sprint(client):
    response = await client.post(
        "/api/sprints/plan", json={"name": "Sprint 2", "duration_weeks": 2}
    )

    assert response.status_code == 400


async def test_plan_next_sprint_creates_a_planned_sprint_with_no_dates_yet(client):
    await client.post("/api/sprints/start", json={"name": "Sprint 1", "duration_weeks": 1})

    response = await client.post(
        "/api/sprints/plan", json={"name": "Sprint 2", "duration_weeks": 3}
    )

    assert response.status_code == 200
    planned = response.json()
    assert planned["name"] == "Sprint 2"
    assert planned["status"] == "planned"
    assert planned["duration_weeks"] == 3
    assert planned["start_date"] is None
    assert planned["end_date"] is None

    fetched = (await client.get("/api/sprints/planned")).json()
    assert fetched == planned


async def test_only_one_sprint_can_be_planned_at_a_time(client):
    await client.post("/api/sprints/start", json={"name": "Sprint 1", "duration_weeks": 1})
    await client.post("/api/sprints/plan", json={"name": "Sprint 2", "duration_weeks": 2})

    response = await client.post(
        "/api/sprints/plan", json={"name": "Sprint 2 (again)", "duration_weeks": 1}
    )

    assert response.status_code == 400


async def test_plan_next_sprint_with_empty_name_is_rejected(client):
    await client.post("/api/sprints/start", json={"name": "Sprint 1", "duration_weeks": 1})

    response = await client.post("/api/sprints/plan", json={"name": "  ", "duration_weeks": 1})

    assert response.status_code == 400


async def test_plan_next_sprint_with_invalid_duration_is_rejected(client):
    await client.post("/api/sprints/start", json={"name": "Sprint 1", "duration_weeks": 1})

    response = await client.post(
        "/api/sprints/plan", json={"name": "Sprint 2", "duration_weeks": 5}
    )

    assert response.status_code == 400


async def test_end_sprint_promotes_the_planned_sprint_instead_of_opening_the_prompt_flow(client):
    sprint_1 = (
        await client.post("/api/sprints/start", json={"name": "Sprint 1", "duration_weeks": 1})
    ).json()
    planned = (
        await client.post("/api/sprints/plan", json={"name": "Sprint 2", "duration_weeks": 3})
    ).json()

    response = await client.post("/api/sprints/end", json={})

    assert response.status_code == 200
    promoted = response.json()
    assert promoted["id"] == planned["id"]
    assert promoted["name"] == "Sprint 2"
    assert promoted["status"] == "active"

    today = date.today()
    assert promoted["start_date"] == today.isoformat()
    assert promoted["end_date"] == (today + timedelta(weeks=3)).isoformat()

    active = (await client.get("/api/sprints/active")).json()
    assert active == promoted

    # The promoted sprint is no longer "planned".
    assert (await client.get("/api/sprints/planned")).json() is None

    # Sprint 1's own end_date reflects when it actually closed (today), not its original
    # 1-week target -- same end_date fix as the fallback (non-promoted) path, just exercised
    # via promotion here.
    with storage._session() as session:
        closed_sprint = session.get(storage.Sprint, sprint_1["id"])
        assert closed_sprint.end_date == today


async def test_end_sprint_ignores_a_supplied_name_and_duration_when_a_sprint_is_planned(client):
    await client.post("/api/sprints/start", json={"name": "Sprint 1", "duration_weeks": 1})
    await client.post("/api/sprints/plan", json={"name": "Planned Sprint", "duration_weeks": 4})

    response = await client.post(
        "/api/sprints/end", json={"name": "Ignored Name", "duration_weeks": 1}
    )

    assert response.status_code == 200
    promoted = response.json()
    assert promoted["name"] == "Planned Sprint"
    today = date.today()
    assert promoted["end_date"] == (today + timedelta(weeks=4)).isoformat()


async def test_end_sprint_promotion_rolls_over_incomplete_tasks_and_sweeps_untagged(client):
    sprint_1 = (
        await client.post("/api/sprints/start", json={"name": "Sprint 1", "duration_weeks": 1})
    ).json()
    await client.post("/api/sprints/plan", json={"name": "Sprint 2", "duration_weeks": 2})

    todo_id = (
        await client.post("/api/tasks", json={"column": "To Do", "title": "Still open"})
    ).json()["id"]
    done_id = (
        await client.post("/api/tasks", json={"column": "To Do", "title": "Completed"})
    ).json()["id"]
    await client.put(f"/api/tasks/{done_id}/move", json={"to_column": "Done"})

    promoted = (await client.post("/api/sprints/end", json={})).json()

    with storage._session() as session:
        todo_task = session.get(storage.Task, storage._parse_id(todo_id))
        assert todo_task.sprint_id == promoted["id"]

        done_task = session.get(storage.Task, storage._parse_id(done_id))
        assert done_task.sprint_id == sprint_1["id"]


async def test_end_sprint_without_a_planned_sprint_still_requires_name_and_duration(client):
    await client.post("/api/sprints/start", json={"name": "Sprint 1", "duration_weeks": 1})

    response = await client.post("/api/sprints/end", json={})

    assert response.status_code == 400
    active = (await client.get("/api/sprints/active")).json()
    assert active["name"] == "Sprint 1"


async def test_active_and_closed_sprints_have_no_duration_weeks_in_the_response(client):
    started = (
        await client.post("/api/sprints/start", json={"name": "Sprint 1", "duration_weeks": 1})
    ).json()
    assert started["duration_weeks"] is None

    ended = (
        await client.post("/api/sprints/end", json={"name": "Sprint 2", "duration_weeks": 1})
    ).json()
    assert ended["duration_weeks"] is None

    past = (await client.get("/api/sprints")).json()
    assert past[0]["duration_weeks"] is None
