from core import agent_blackboard, agent_memory, approval_inbox, evaluation_lab, task_contracts, task_queue, voice_reliability


def test_agent_blackboard_posts_and_resolves_items(monkeypatch, tmp_path):
    monkeypatch.setattr(agent_blackboard, "DB_PATH", tmp_path / "blackboard.sqlite3")

    item = agent_blackboard.post_item("research_analyst", "finding", "Source found", "Official docs are relevant.", confidence=0.8)
    summary = agent_blackboard.summary()
    resolved = agent_blackboard.resolve_item(item["id"], note="Used by developer.")

    assert item["item_type"] == "finding"
    assert summary["open_count"] == 1
    assert resolved["status"] == "resolved"


def test_task_contract_verifies_agent_result(monkeypatch, tmp_path):
    monkeypatch.setattr(task_queue, "DB_PATH", tmp_path / "tasks.sqlite3")
    monkeypatch.setattr(task_contracts, "DB_PATH", tmp_path / "contracts.sqlite3")
    task_id = task_queue.create_task("Implement contract tests", agent_id="qa_engineer")
    task = task_queue.get_task(task_id)

    contract = task_contracts.ensure_contract(task)
    verified = task_contracts.verify_contract(task, {"agent_id": "qa_engineer", "summary": "Summary: ok"})

    assert contract["status"] == "active"
    assert verified["status"] == "verified"
    assert verified["satisfied"] is True


def test_agent_memory_retrieves_specialist_notes(monkeypatch, tmp_path):
    monkeypatch.setattr(agent_memory, "DB_PATH", tmp_path / "agent_memory.sqlite3")

    agent_memory.remember("qa_engineer", "recurring_bug", "Volume verification", "Verify device state after tool calls.", tags=["pc_control"])
    context = agent_memory.context_for_agent("qa_engineer", "volume")

    assert "Volume verification" in context
    assert "Verify device state" in context


def test_evaluation_lab_and_voice_reliability(monkeypatch, tmp_path):
    monkeypatch.setattr(evaluation_lab, "DB_PATH", tmp_path / "evaluation.sqlite3")
    monkeypatch.setattr(voice_reliability, "DB_PATH", tmp_path / "voice.sqlite3")

    evaluation_lab.record_event("slow_response", "e2e over target", metric_value=9000)
    voice_reliability.record_sample("Freddie", expected_text="Friday", backend="test", accepted=False, correction_applied=True)

    assert evaluation_lab.summary()["counts"]["slow_response"] == 1
    assert "freddie" in voice_reliability.learned_aliases()


def test_approval_inbox_aggregates_blocked_tasks_and_blackboard(monkeypatch, tmp_path):
    monkeypatch.setattr(task_queue, "DB_PATH", tmp_path / "tasks.sqlite3")
    monkeypatch.setattr(agent_blackboard, "DB_PATH", tmp_path / "blackboard.sqlite3")
    task_id = task_queue.create_task("Guarded task", agent_id="ethical_hacker")
    task_queue.update_status(task_id, "blocked")
    agent_blackboard.post_item("qa_engineer", "question", "Need answer", "Should we test this?", target_agent_id="senior_developer")

    payload = approval_inbox.summary()

    assert payload["count"] >= 2
    assert payload["by_kind"]["blocked_task"] == 1
