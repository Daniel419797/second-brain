import datetime as dt

from core import app_integrations, proactive_speech, task_queue


def isolate_proactive(monkeypatch, tmp_path, values=None):
    values = values or {}
    defaults = {
        "proactive_speech_enabled": True,
        "proactive_speech_sources": "reminders,calendar,agent_tasks",
        "proactive_speech_max_per_hour": 3,
        "proactive_speech_quiet_hours_start": "00:00",
        "proactive_speech_quiet_hours_end": "00:00",
        "proactive_speech_reminder_lookahead_minutes": 2,
        "proactive_speech_calendar_lookahead_minutes": 10,
        "proactive_speech_task_priority_threshold": 3,
    } | values
    monkeypatch.setattr(proactive_speech, "DB_PATH", tmp_path / "proactive.sqlite3")
    monkeypatch.setattr(app_integrations, "DB_PATH", tmp_path / "integrations.sqlite3")
    monkeypatch.setattr(task_queue, "DB_PATH", tmp_path / "tasks.sqlite3")
    monkeypatch.setattr(
        proactive_speech,
        "config_value",
        lambda key, default=None: defaults.get(key, default),
    )
    proactive_speech.init_db()
    app_integrations.init_db()
    task_queue.init_db()


def test_due_reminder_is_spoken_once(monkeypatch, tmp_path):
    isolate_proactive(monkeypatch, tmp_path)
    now = dt.datetime(2026, 5, 19, 12, 0, tzinfo=dt.datetime.now().astimezone().tzinfo)
    reminder = app_integrations.create_reminder("drink water", due_at=(now - dt.timedelta(minutes=1)).isoformat())

    notifications = proactive_speech.collect_notifications(now)

    assert notifications[0]["key"] == f"reminder:{reminder['id']}:due"
    assert notifications[0]["message"] == "Reminder: drink water."
    proactive_speech.mark_spoken(notifications[0]["key"], notifications[0]["source"], notifications[0]["message"], now)
    assert proactive_speech.collect_notifications(now) == []


def test_quiet_hours_suppress_proactive_speech(monkeypatch, tmp_path):
    isolate_proactive(
        monkeypatch,
        tmp_path,
        {
            "proactive_speech_quiet_hours_start": "00:00",
            "proactive_speech_quiet_hours_end": "23:59",
        },
    )
    now = dt.datetime(2026, 5, 19, 12, 0, tzinfo=dt.datetime.now().astimezone().tzinfo)
    app_integrations.create_reminder("stand up", due_at=(now - dt.timedelta(minutes=1)).isoformat())

    assert proactive_speech.collect_notifications(now) == []


def test_agent_task_notifications_include_blocked_and_high_priority_done(monkeypatch, tmp_path):
    isolate_proactive(monkeypatch, tmp_path, {"proactive_speech_sources": "agent_tasks"})
    blocked_id = task_queue.create_task("Needs approval", agent_id="ethical_hacker", priority=1)
    task_queue.update_status(blocked_id, "blocked")
    done_id = task_queue.create_task("Finish plan", agent_id="project_manager", priority=2)
    task_queue.complete_task(done_id, {"summary": "done"})
    low_id = task_queue.create_task("Low priority cleanup", agent_id="qa_engineer", priority=9)
    task_queue.complete_task(low_id, {"summary": "done"})

    messages = [item["message"] for item in proactive_speech.collect_notifications()]

    assert any("needs your approval" in message for message in messages)
    assert any("Finish plan" in message for message in messages)
    assert not any("Low priority cleanup" in message for message in messages)
