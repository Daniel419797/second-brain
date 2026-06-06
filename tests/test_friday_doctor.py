from __future__ import annotations

from core import agent_blackboard, agent_thought_bus, doctor_agent, notification_center, task_contracts, task_queue
from scripts import friday_doctor
from tools import agent_team


def test_friday_doctor_runner_returns_structured_report(monkeypatch, tmp_path):
    calls = []

    def fake_check(name, root, *, command_timeout=None):
        calls.append((name, root))
        return {"name": name, "status": "pass", "summary": f"{name} ok", "duration_seconds": 0.01}

    monkeypatch.setattr(friday_doctor, "_run_named_check", fake_check)

    report = friday_doctor.run_diagnostics(profile="quick", root=tmp_path, write_report=False)

    assert report["overall_status"] == "pass"
    assert report["profile"] == "quick"
    assert [name for name, _ in calls] == list(friday_doctor.PROFILE_CHECKS["quick"])
    assert "Summary:" in report["summary"]
    assert "Next step:" in report["summary"]
    assert "Risks:" in report["summary"]
    assert "Friday Doctor Report" in report["markdown"]


def test_doctor_agent_posts_progress_notification_and_compact_report(monkeypatch, tmp_path):
    monkeypatch.setattr(task_queue, "DB_PATH", tmp_path / "tasks.sqlite3")
    monkeypatch.setattr(agent_blackboard, "DB_PATH", tmp_path / "blackboard.sqlite3")
    monkeypatch.setattr(agent_thought_bus, "DB_PATH", tmp_path / "thoughts.sqlite3")
    monkeypatch.setattr(notification_center, "DB_PATH", tmp_path / "notifications.sqlite3")

    def fake_run_diagnostics(**kwargs):
        kwargs["reporter"]("decision", "Doctor chose quick checks.", 25)
        kwargs["reporter"]("progress", "environment passed.", 60)
        kwargs["reporter"]("result", "diagnostics finished.", 95)
        return {
            "overall_status": "warn",
            "profile": kwargs["profile"],
            "root": str(kwargs["root"]),
            "started_at": "start",
            "completed_at": "done",
            "duration_seconds": 1.2,
            "summary": "Summary: diagnostics finished. Next step: review provider setup. Risks: provider warning.",
            "next_step": "review provider setup",
            "risks": ["provider warning"],
            "checks": [{"name": "provider_readiness", "status": "warn", "summary": "provider setup missing"}],
            "artifacts": [str(tmp_path / "doctor.md")],
        }

    monkeypatch.setattr(doctor_agent.friday_doctor, "run_diagnostics", fake_run_diagnostics)
    task_id = task_queue.create_task(
        "Run quick diagnostics",
        agent_id="doctor",
        input_data={"source": "diagnostics_request", "diagnostic_profile": "quick"},
    )
    task = task_queue.get_task(task_id)

    result = doctor_agent.run_task(task)

    assert result["agent_id"] == "doctor"
    assert result["diagnostic_status"] == "warn"
    assert result["diagnostic_report"]["checks"][0]["name"] == "provider_readiness"
    assert any("Doctor decision" in message["message"] for message in task_queue.get_messages(task_id, limit=20))
    assert agent_blackboard.list_items(task_id=task_id, limit=20)
    assert agent_thought_bus.list_thoughts(task_id=task_id, limit=20)
    assert notification_center.list_notifications("unread", limit=5)[0]["source"] == "doctor"


def test_agent_team_hands_diagnostics_to_doctor_and_starts_worker(monkeypatch, tmp_path):
    monkeypatch.setattr(task_queue, "DB_PATH", tmp_path / "tasks.sqlite3")
    monkeypatch.setattr(task_contracts, "DB_PATH", tmp_path / "contracts.sqlite3")
    monkeypatch.setattr(agent_thought_bus, "DB_PATH", tmp_path / "thoughts.sqlite3")
    started = []
    monkeypatch.setattr(agent_team.background_agents, "start_workers", lambda count=None: started.append(count) or 1)

    reply = agent_team.execute({"action": "run_diagnostics", "profile": "quick"})
    task = task_queue.list_tasks(agent_id="doctor", limit=1)[0]

    assert "Diagnostics handed to Doctor agent as task #" in reply
    assert started == [1]
    assert task["agent_id"] == "doctor"
    assert task["input"]["source"] == "diagnostics_request"
    assert task["input"]["diagnostic_profile"] == "quick"
    assert any("handed this diagnostic request" in message["message"] for message in task_queue.get_messages(task["id"], limit=10))


def test_agent_team_monitor_diagnostics_reports_decisions(monkeypatch, tmp_path):
    monkeypatch.setattr(task_queue, "DB_PATH", tmp_path / "tasks.sqlite3")
    monkeypatch.setattr(agent_blackboard, "DB_PATH", tmp_path / "blackboard.sqlite3")
    monkeypatch.setattr(agent_thought_bus, "DB_PATH", tmp_path / "thoughts.sqlite3")
    task_id = task_queue.create_task("Run diagnostics", agent_id="doctor")
    task_queue.update_status(
        task_id,
        "done",
        output={
            "diagnostic_report": {
                "overall_status": "pass",
                "summary": "Summary: ok. Next step: none. Risks: none.",
                "checks": [{"name": "environment", "status": "pass"}],
            }
        },
    )
    agent_thought_bus.post_thought("doctor", "decision", "Doctor selected quick profile.", task_id=task_id)
    agent_blackboard.post_item("doctor", "evidence", "Diagnostics complete", "All checks passed.", task_id=task_id, status="resolved")

    result = agent_team.execute({"action": "monitor_diagnostics", "task_id": task_id})

    assert "Diagnostic status: pass" in result
    assert "Decisions: Doctor selected quick profile." in result
    assert "Blackboard:" in result
