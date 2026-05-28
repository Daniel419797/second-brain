from pathlib import Path

from core import adaptive_attention, cognitive_cycle, cognitive_state, desktop_tasks, goal_regulation, long_term_learning, self_reflection, self_update, world_model


def _isolate(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(world_model, "DB_PATH", tmp_path / "world.sqlite3")
    monkeypatch.setattr(self_reflection, "DB_PATH", tmp_path / "reflection.sqlite3")
    monkeypatch.setattr(long_term_learning, "DB_PATH", tmp_path / "learning.sqlite3")
    monkeypatch.setattr(self_update, "DB_PATH", tmp_path / "self_updates.sqlite3")
    monkeypatch.setattr(desktop_tasks, "DB_PATH", tmp_path / "desktop_tasks.sqlite3")
    monkeypatch.setattr(goal_regulation, "DB_PATH", tmp_path / "goals.sqlite3")
    monkeypatch.setattr(adaptive_attention, "DB_PATH", tmp_path / "attention.sqlite3")
    monkeypatch.setattr(cognitive_cycle, "config_value", lambda key, default=None: {
        "cognitive_cycle_enabled": True,
        "cognitive_cycle_interval_seconds": 60,
        "self_reflection_interval_minutes": 30,
    }.get(key, default))


def test_cognitive_state_serializes_dataclass():
    snapshot = cognitive_state.CognitiveSnapshot(
        timestamp=cognitive_state.now_iso(),
        source="test",
        summary="Screen changed.",
        visible_state={"x": 1},
    )

    data = cognitive_state.to_dict(snapshot)

    assert data["source"] == "test"
    assert data["visible_state"]["x"] == 1


def test_world_model_snapshot_and_expectation(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    monkeypatch.setattr(world_model, "_active_window", lambda: "Calculator")
    monkeypatch.setattr(world_model.visual_monitor, "latest_event", lambda: {"summary": "Calculator opened", "event_type": "change"})

    snapshot = world_model.capture_snapshot("test")
    expectation_id = world_model.create_expectation("goal-1", "Calculator opened", ttl_seconds=60)
    resolved = world_model.resolve_expectations(snapshot["summary"])

    assert snapshot["active_app"] == "calculator"
    assert expectation_id > 0
    assert resolved[0]["status"] == "met"


def test_reflection_creates_learning_from_user_correction(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)

    finding = self_reflection.reflect_on_command("you lied, the volume did not change", "Volume set.", success_score=1.0)
    items = long_term_learning.recent_items(limit=5)

    assert finding["category"] == "unverified_claim"
    assert items
    assert "Verify" in items[0]["content"] or "reported" in items[0]["content"]


def test_llm_reflection_adds_structured_finding(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    original_config = self_reflection.config_value

    monkeypatch.setattr(
        self_reflection,
        "config_value",
        lambda key, default=None: True if key == "self_reflection_use_llm" else original_config(key, default),
    )
    monkeypatch.setattr(
        self_reflection.llm,
        "ask_simple",
        lambda prompt, retries=1: '{"category":"slow_response","finding":"Use deterministic routes for simple questions.","severity":2,"recommended_change":"Answer simple factual commands before calling the LLM."}',
    )

    result = self_reflection.run_reflection(trigger="test", minutes=1)

    assert any(item["category"] == "slow_response" for item in result["findings"])


def test_long_term_learning_reinforces_item(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)

    item_id = long_term_learning.record_learning("lesson", "volume", "Verify volume after setting it.", confidence=0.5)
    updated = long_term_learning.reinforce_learning(item_id, "Second successful verification.")

    assert updated["evidence_count"] == 2
    assert updated["confidence"] > 0.5


def test_long_term_learning_can_propose_guarded_self_update(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    monkeypatch.setattr(self_update, "_build_plan", lambda request: {"risk_level": "medium", "request": request, "candidate_files": []})

    item_id = long_term_learning.record_learning("reflection", "volume", "Verify volume after setting it.", confidence=0.8)
    long_term_learning.reinforce_learning(item_id, "The same verification issue happened again.")
    proposal = long_term_learning.reinforce_learning(item_id, "The same verification issue happened a third time.")
    updates = self_update.list_updates(limit=3)

    assert proposal["evidence_count"] >= 3
    assert updates
    assert "Long-term learning" in updates[0]["request"]


def test_goal_regulation_tracks_goal_and_state(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)

    goal_id = goal_regulation.create_goal("Improve Friday attention", priority=2)
    goal_regulation.update_goal(goal_id, progress=0.4)
    state = goal_regulation.set_affective_state("focused", "working on attention")
    current = goal_regulation.current_regulation()

    assert state["state"] == "focused"
    assert current["active_goals"][0]["progress"] == 0.4


def test_adaptive_attention_updates_profile(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)

    for _ in range(8):
        adaptive_attention.record_attention_event("thank you for watching", "ignored", "name_required", accepted=False)
    profile = adaptive_attention.current_profile()

    assert profile["false_positive_rate"] > 0
    assert profile["name_strictness"] > 0.5


def test_desktop_task_updates_world_expectations(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    monkeypatch.setattr(world_model, "_active_window", lambda: "Calculator")
    monkeypatch.setattr(world_model.visual_monitor, "latest_event", lambda: None)

    session_id = desktop_tasks.create_session("open calculator", max_steps=3)
    desktop_tasks.append_step(
        session_id,
        step_number=1,
        status="completed",
        progress="calculator opened",
        action={"action": "open_app", "target": "calculator"},
        result="ok",
    )
    context = world_model.current_context()

    assert session_id > 0
    assert context["snapshot"]["visible_state"]["desktop_task_step"]["session_id"] == session_id
    assert any(item["status"] == "met" for item in world_model.expectations(limit=5))


def test_cognitive_cycle_run_once(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    monkeypatch.setattr(world_model, "_active_window", lambda: "Friday Command Center")
    monkeypatch.setattr(world_model.visual_monitor, "latest_event", lambda: None)

    result = cognitive_cycle.run_once("test", light_mode=True)

    assert result["trigger"] == "test"
    assert result["world_snapshot"]["summary"]
