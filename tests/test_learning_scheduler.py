import datetime as dt

from core import learning_scheduler, task_queue


def test_learning_scheduler_seeds_low_priority_future_tasks(monkeypatch, tmp_path):
    monkeypatch.setattr(task_queue, "DB_PATH", tmp_path / "tasks.sqlite3")
    monkeypatch.setattr(
        learning_scheduler,
        "config_value",
        lambda key, default=None: True
        if key == "v2_self_learning_enabled"
        else 10
        if key == "v2_self_learning_priority"
        else 15
        if key == "v2_self_learning_delay_minutes"
        else 12
        if key == "v2_self_learning_repeat_hours"
        else default,
    )
    now = dt.datetime(2026, 5, 16, 12, 0, tzinfo=dt.timezone.utc)

    created = learning_scheduler.seed_learning_tasks(now=now)
    second = learning_scheduler.seed_learning_tasks(now=now)
    tasks = task_queue.list_tasks(limit=10)

    assert len(created) == 3
    assert second == []
    assert all(task["priority"] == 10 for task in tasks)
    assert all(task["scheduled_at"] for task in tasks)
    docs_task = next(task for task in tasks if task["input"]["key"] == "dev_official_docs_learning")
    assert docs_task["agent_id"] == "research_analyst"


def test_learning_scheduler_skips_recent_finished_tasks(monkeypatch, tmp_path):
    monkeypatch.setattr(task_queue, "DB_PATH", tmp_path / "tasks.sqlite3")
    monkeypatch.setattr(
        learning_scheduler,
        "config_value",
        lambda key, default=None: True
        if key == "v2_self_learning_enabled"
        else 10
        if key == "v2_self_learning_priority"
        else 15
        if key == "v2_self_learning_delay_minutes"
        else 12
        if key == "v2_self_learning_repeat_hours"
        else default,
    )
    now = dt.datetime(2026, 5, 16, 12, 0, tzinfo=dt.timezone.utc)
    task_id = task_queue.create_task("Read official documentation for current project stack")
    task_queue.complete_task(task_id, {"summary": "done"})

    created = learning_scheduler.seed_learning_tasks(now=now)

    titles = [task_queue.get_task(task_id)["title"] for task_id in created]
    assert "Read official documentation for current project stack" not in titles
