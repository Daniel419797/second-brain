from core import agent_thought_bus


def test_thought_bus_posts_and_retrieves_relevant_context(monkeypatch, tmp_path):
    monkeypatch.setattr(agent_thought_bus, "DB_PATH", tmp_path / "thoughts.sqlite3")

    packet = agent_thought_bus.post_thought(
        "research_analyst",
        "research_handoff",
        "FastAPI docs recommend dependency injection for auth",
        {"notes": "Use Depends for protected dashboard routes."},
        target_agent_id="senior_developer",
        task_id=42,
        confidence=0.8,
        priority=2,
    )
    context = agent_thought_bus.context_for_agent("senior_developer", "implement FastAPI auth dependency", task_id=42)

    assert packet["id"] > 0
    assert packet["target_agent_id"] == "senior_developer"
    assert "Silent thought bus context" in context
    assert "FastAPI docs" in context


def test_thought_bus_filters_target_agent(monkeypatch, tmp_path):
    monkeypatch.setattr(agent_thought_bus, "DB_PATH", tmp_path / "thoughts.sqlite3")

    agent_thought_bus.post_thought("product_manager", "risk", "Regression tests missing", target_agent_id="senior_developer")
    qa_context = agent_thought_bus.context_for_agent("qa_engineer", "regression tests")
    dev_context = agent_thought_bus.context_for_agent("senior_developer", "regression tests")

    assert "Regression tests missing" not in qa_context
    assert "Regression tests missing" in dev_context


def test_thought_bus_summary_and_resolve(monkeypatch, tmp_path):
    monkeypatch.setattr(agent_thought_bus, "DB_PATH", tmp_path / "thoughts.sqlite3")

    packet = agent_thought_bus.post_thought("ceo", "need", "Need user approval", priority=1)
    summary = agent_thought_bus.summary()
    resolved = agent_thought_bus.resolve_thought(packet["id"], note="Handled")

    assert summary["open_count"] == 1
    assert summary["urgent"][0]["summary"] == "Need user approval"
    assert resolved["status"] == "resolved"
    assert resolved["metadata"]["resolution_note"] == "Handled"
