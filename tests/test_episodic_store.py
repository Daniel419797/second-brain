import datetime as dt

from core import episodic_store


def test_episodic_store_insert_query_and_summary(monkeypatch, tmp_path):
    monkeypatch.setattr(episodic_store, "DB_PATH", tmp_path / "events.sqlite3")

    event_id = episodic_store.insert_event(
        agent_id="jarvis",
        action_type="tool_use",
        inputs={"tool": "pc_control"},
        outputs={"result": "ok"},
        success_score=0.9,
        timestamp=dt.datetime(2026, 5, 16, 10, 0, tzinfo=dt.timezone.utc),
    )

    assert event_id == 1
    events = episodic_store.query_events(agent_id="jarvis")
    assert events[0]["action_type"] == "tool_use"
    assert events[0]["inputs"] == {"tool": "pc_control"}
    assert events[0]["success_score"] == 0.9
    assert "tool_use" in episodic_store.summarize_recent()


def test_episodic_store_wipe_all(monkeypatch, tmp_path):
    monkeypatch.setattr(episodic_store, "DB_PATH", tmp_path / "events.sqlite3")
    episodic_store.insert_event(inputs="x", outputs="y")

    episodic_store.wipe_all()

    assert episodic_store.count_events() == 0
