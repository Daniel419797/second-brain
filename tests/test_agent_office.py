from core import agent_office, task_queue


def test_agent_office_tracks_current_task_progress_and_messages(monkeypatch, tmp_path):
    monkeypatch.setattr(task_queue, "DB_PATH", tmp_path / "tasks.sqlite3")
    monkeypatch.setattr(agent_office, "config_value", lambda key, default=None: 120 if key == "agent_office_task_limit" else default)
    monkeypatch.setattr(agent_office.competence, "get_agent_map", lambda agent_id: {"python": 0.8, "general": 0.6})
    monkeypatch.setattr(agent_office.agents, "agent_provider_chain", lambda agent_id: ["nvidia", "ollama"])
    task_id = task_queue.create_task("Review API routing", agent_id="senior_developer", priority=2)

    task = task_queue.claim_next_task()
    task_queue.post_message(task_id, "office", "Progress 55%: specialist work is in progress.")

    office = agent_office.office("senior_developer")

    assert office["agent_id"] == "senior_developer"
    assert office["room_name"] == "Architecture Studio"
    assert office["status"] == "working"
    assert office["current_task"]["id"] == task["id"]
    assert office["progress_percent"] >= 35
    assert office["task_counts"]["active"] == 1
    assert office["recent_messages"][0]["message"].startswith("Progress")
    assert office["provider_chain"] == ["nvidia", "ollama"]


def test_office_summary_reports_active_agents(monkeypatch, tmp_path):
    monkeypatch.setattr(task_queue, "DB_PATH", tmp_path / "tasks.sqlite3")
    monkeypatch.setattr(agent_office, "config_value", lambda key, default=None: 120 if key == "agent_office_task_limit" else default)
    monkeypatch.setattr(agent_office.competence, "get_agent_map", lambda agent_id: {"general": 0.6})
    monkeypatch.setattr(agent_office.agents, "agent_provider_chain", lambda agent_id: ["ollama"])
    task_queue.create_task("Write tests", agent_id="qa_engineer", priority=1)

    summary = agent_office.office_summary(limit=2)

    assert "QA Engineer" in summary
    assert "queued" in summary
