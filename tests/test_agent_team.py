from core import task_queue
from tools import agent_team


def test_agent_team_create_and_list(monkeypatch, tmp_path):
    monkeypatch.setattr(task_queue, "DB_PATH", tmp_path / "tasks.sqlite3")

    created = agent_team.execute({"action": "create_task", "title": "Research free APIs", "agent_id": "research"})
    listing = agent_team.execute({"action": "list_tasks"})

    assert "queued" in created
    assert "research_analyst" in listing


def test_agent_team_status_and_roster(monkeypatch, tmp_path):
    monkeypatch.setattr(task_queue, "DB_PATH", tmp_path / "tasks.sqlite3")

    status = agent_team.execute({"action": "status"})
    roster = agent_team.execute({"action": "roster"})

    assert "Agent workers" in status
    assert "Senior Developer" in roster


def test_agent_team_office_summary(monkeypatch, tmp_path):
    monkeypatch.setattr(task_queue, "DB_PATH", tmp_path / "tasks.sqlite3")
    monkeypatch.setattr(agent_team.agent_office.competence, "get_agent_map", lambda agent_id: {"general": 0.6})
    monkeypatch.setattr(agent_team.agent_office.agents, "agent_provider_chain", lambda agent_id: ["ollama"])
    task_queue.create_task("Write regression tests", agent_id="qa_engineer")

    offices = agent_team.execute({"action": "offices"})
    office = agent_team.execute({"action": "office", "agent_id": "qa_engineer"})

    assert "QA Engineer" in offices
    assert "QA Engineer is queued" in office


def test_agent_team_cancel_task(monkeypatch, tmp_path):
    monkeypatch.setattr(task_queue, "DB_PATH", tmp_path / "tasks.sqlite3")
    task_id = task_queue.create_task("Do something")

    result = agent_team.execute({"action": "cancel_task", "task_id": task_id})

    assert result == f"Task {task_id} cancelled."


def test_agent_team_reassign_task(monkeypatch, tmp_path):
    monkeypatch.setattr(task_queue, "DB_PATH", tmp_path / "tasks.sqlite3")
    task_id = task_queue.create_task("Read official docs", agent_id="senior_developer")

    result = agent_team.execute({"action": "reassign_task", "task_id": task_id, "agent_id": "research", "status": "pending"})

    assert f"#{task_id} [pending] research_analyst" in result


def test_agent_team_lists_agent_questions(monkeypatch, tmp_path):
    monkeypatch.setattr(task_queue, "DB_PATH", tmp_path / "tasks.sqlite3")
    task_queue.create_task(
        "Answer Design question",
        agent_id="qa_engineer",
        input_data={"source": "agent_question", "from_agent": "ui_ux_designer", "question": "Which regression tests matter?"},
    )

    result = agent_team.execute({"action": "list_questions"})

    assert "ui_ux_designer asked qa_engineer" in result


def test_agent_team_approve_guarded_task(monkeypatch, tmp_path):
    monkeypatch.setattr(task_queue, "DB_PATH", tmp_path / "tasks.sqlite3")
    task_id = agent_team.agents.create_task("Test authorized target", agent_id="ethical_hacker")

    denied = agent_team.execute({"action": "approve_task", "task_id": task_id, "confirmation": "yes"})
    approved = agent_team.execute({"action": "approve_task", "task_id": task_id, "confirmation": f"I authorize task {task_id}"})

    assert "could not approve" in denied
    assert approved == f"Task {task_id} approved and returned to pending."
