from pathlib import Path

from core import autobiographical_memory, evidence_gate, self_model


def test_evidence_gate_blocks_unsupported_action_claim():
    reply = evidence_gate.guard_reply("open chrome", "Chrome opened successfully.", evidence=None)

    assert "not claim" in reply


def test_evidence_gate_allows_supported_tool_result():
    reply = evidence_gate.guard_reply("open chrome", "Chrome opened successfully.", evidence="Chrome opened successfully.")

    assert reply == "Chrome opened successfully."


def test_autobiographical_memory_records_timeline(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(autobiographical_memory, "DB_PATH", tmp_path / "auto.sqlite3")

    event_id = autobiographical_memory.record_event("successful_fix", "Fixed volume control", "Verified with Windows audio API.", importance=0.9)
    events = autobiographical_memory.recent_events(limit=3)

    assert event_id > 0
    assert events[0]["event_type"] == "successful_fix"
    assert "volume" in autobiographical_memory.timeline_summary().lower()


def test_self_model_status_contains_identity_tools_and_limits(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(autobiographical_memory, "DB_PATH", tmp_path / "auto.sqlite3")
    monkeypatch.setattr(self_model.world_model, "current_context", lambda: {"open_expectations": [], "summary": "idle"})
    monkeypatch.setattr(self_model.background_agents, "worker_status", lambda: {"running": False, "workers": 0})
    monkeypatch.setattr(self_model.task_queue, "counts", lambda: {"active": 0, "pending": 0})

    payload = self_model.status()

    assert payload["identity"]["name"] == "Friday"
    assert payload["tools"]
    assert any("pretend" in item.lower() for item in payload["limitations"])
