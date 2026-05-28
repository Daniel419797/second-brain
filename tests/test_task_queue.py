from core import task_queue
import datetime as dt


def test_task_queue_create_claim_complete(monkeypatch, tmp_path):
    monkeypatch.setattr(task_queue, "DB_PATH", tmp_path / "tasks.sqlite3")

    task_id = task_queue.create_task("Research free APIs", agent_id="research_analyst", priority=1)
    task = task_queue.claim_next_task()

    assert task["id"] == task_id
    assert task["status"] == "active"
    task_queue.complete_task(task_id, {"summary": "Done"})
    done = task_queue.get_task(task_id)
    assert done["status"] == "done"
    assert done["output"] == {"summary": "Done"}


def test_task_queue_messages_counts_and_cancel(monkeypatch, tmp_path):
    monkeypatch.setattr(task_queue, "DB_PATH", tmp_path / "tasks.sqlite3")
    task_id = task_queue.create_task("Write tests")

    task_queue.post_message(task_id, "qa", "Starting")

    assert task_queue.counts()["pending"] == 1
    assert task_queue.get_messages(task_id)[0]["message"] == "Starting"
    assert task_queue.cancel_task(task_id) is True
    assert task_queue.counts()["cancelled"] == 1


def test_task_queue_reassigns_and_requeues_active_task(monkeypatch, tmp_path):
    monkeypatch.setattr(task_queue, "DB_PATH", tmp_path / "tasks.sqlite3")
    task_id = task_queue.create_task("Read docs", agent_id="senior_developer")
    task_queue.claim_next_task()

    assert task_queue.reassign_task(task_id, "research_analyst", status="pending") is True

    task = task_queue.get_task(task_id)
    assert task["agent_id"] == "research_analyst"
    assert task["status"] == "pending"
    assert task["started_at"] == ""


def test_task_queue_skips_future_scheduled_tasks(monkeypatch, tmp_path):
    monkeypatch.setattr(task_queue, "DB_PATH", tmp_path / "tasks.sqlite3")
    future = dt.datetime.now(dt.timezone.utc).astimezone() + dt.timedelta(days=1)
    task_queue.create_task("Future research", scheduled_at=future)

    assert task_queue.claim_next_task() is None
