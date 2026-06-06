from core import background_agents, task_queue


def test_run_one_task_completes_pending_task(monkeypatch, tmp_path):
    monkeypatch.setattr(task_queue, "DB_PATH", tmp_path / "tasks.sqlite3")
    monkeypatch.setattr(
        background_agents.agents,
        "run_task",
        lambda task: {"agent_id": task["agent_id"], "agent_name": "Research Analyst", "summary": "Done"},
    )
    monkeypatch.setattr(background_agents.knowledge_graph, "add_edge", lambda *args, **kwargs: None)
    monkeypatch.setattr(background_agents.episodic_store, "insert_event", lambda *args, **kwargs: 1)
    task_id = task_queue.create_task("Research free APIs", agent_id="research_analyst")

    result = background_agents.run_one_task()

    assert result["id"] == task_id
    assert result["status"] == "done"
    assert task_queue.get_task(task_id)["status"] == "done"


def test_run_one_task_routes_autonomous_coding_task(monkeypatch, tmp_path):
    monkeypatch.setattr(task_queue, "DB_PATH", tmp_path / "tasks.sqlite3")
    calls = []
    project_root = tmp_path / "coded-app"
    project_root.mkdir()
    changed_file = project_root / "README.md"
    changed_file.write_text("# Coded app\n", encoding="utf-8")
    coding_result = {
        "agent_id": "senior_developer",
        "agent_name": "Senior Developer",
        "task_status": "done",
        "summary": "Summary: coded. Next step: review. Risks: tests not run.",
        "changed": [str(changed_file)],
        "tested": ["verified file exists: README.md"],
        "metadata": {
            "project_root": str(project_root),
            "project_inspection": {"summary": "Project inspected."},
            "execution_plan": {"flow": ["inspect", "implement", "verify"]},
            "responsibility_boundaries": ["routes stay thin", "domain logic lives outside UI"],
            "scaffold_verification": {"status": "passed", "checks": ["verified file exists: README.md"]},
            "product_studio_gates": {
                "attempted": True,
                "technical_ready": False,
                "gates": [{"id": "install", "group": "install", "required": True, "status": "blocked"}],
            },
            "product_studio": {
                "phases": [
                    "requirements",
                    "architecture",
                    "implementation",
                    "tests",
                    "security",
                    "performance",
                    "ux",
                    "deployment",
                    "launch",
                    "proof",
                ],
                "final_proof_report": {"technical_ready": False, "market_ready": False, "gaps": ["Tests not run."]},
            },
        },
    }
    monkeypatch.setattr(background_agents.autonomous_coding, "should_handle_task", lambda task: True)
    monkeypatch.setattr(
        background_agents.autonomous_coding,
        "run_task",
        lambda task: calls.append(task["id"])
        or coding_result,
    )
    monkeypatch.setattr(background_agents.agents, "run_task", lambda task: (_ for _ in ()).throw(AssertionError("generic agent should not run")))
    monkeypatch.setattr(background_agents.knowledge_graph, "add_edge", lambda *args, **kwargs: None)
    monkeypatch.setattr(background_agents.episodic_store, "insert_event", lambda *args, **kwargs: 1)
    task_id = task_queue.create_task("Autonomous coding: build app", agent_id="senior_developer", input_data={"source": "autonomous_coding"})

    result = background_agents.run_one_task()

    assert calls == [task_id]
    assert result["status"] == "failed"
    assert task_queue.get_task(task_id)["status"] == "failed"


def test_start_and_stop_workers(monkeypatch, tmp_path):
    monkeypatch.setattr(task_queue, "DB_PATH", tmp_path / "tasks.sqlite3")
    monkeypatch.setattr(background_agents, "config_value", lambda key, default=None: True if key == "v2_background_agents_enabled" else 0.01 if key.endswith("_seconds") else default)

    count = background_agents.start_workers(count=1)
    status = background_agents.worker_status()
    background_agents.stop_workers(timeout=1)

    assert count >= 1
    assert status["workers"] >= 1


def test_senior_review_records_mentoring_edges(monkeypatch, tmp_path):
    edges = []
    task = {"id": 7, "title": "Review Junior Developer output for Parser", "agent_id": "senior_developer"}
    result = {"agent_id": "senior_developer"}
    monkeypatch.setattr(background_agents.knowledge_graph, "add_edge", lambda *args, **kwargs: edges.append((args, kwargs)))

    background_agents._record_mentoring_edge(task, result)

    assert any(edge[0][1] == "TAUGHT" for edge in edges)
    assert any(edge[0][1] == "REVIEWED" for edge in edges)


def test_cpu_guard_pauses_when_cpu_is_high(monkeypatch):
    class FakePsutil:
        @staticmethod
        def cpu_percent(interval=0.0):
            return 95.0

    monkeypatch.setattr(background_agents, "psutil", FakePsutil)
    monkeypatch.setattr(
        background_agents,
        "config_value",
        lambda key, default=None: True
        if key == "v2_cpu_guard_enabled"
        else 40.0
        if key == "v2_max_cpu_percent"
        else default,
    )

    assert background_agents._cpu_guard_active() is True
