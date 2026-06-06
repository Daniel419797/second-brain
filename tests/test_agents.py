import pytest

from core import agent_thought_bus, agents, task_queue


@pytest.fixture(autouse=True)
def isolate_thought_bus(monkeypatch, tmp_path):
    monkeypatch.setattr(agent_thought_bus, "DB_PATH", tmp_path / "agent_thought_bus.sqlite3")


def test_agent_roster_contains_v2_roles():
    roster = agents.roster()

    assert len(roster) >= 14
    assert any(agent["id"] == "senior_developer" for agent in roster)
    assert any(agent["id"] == "lead_researcher" for agent in roster)
    assert any(agent["id"] == "customer_support" for agent in roster)
    assert any(agent["id"] == "doctor" for agent in roster)


def test_choose_agent_from_task_text():
    assert agents.choose_agent("review this code for bugs") == "code_reviewer"
    assert agents.choose_agent("research free APIs") == "research_analyst"
    assert agents.choose_agent("run system diagnostics") == "doctor"


def test_create_task_selects_agent(monkeypatch, tmp_path):
    monkeypatch.setattr(task_queue, "DB_PATH", tmp_path / "tasks.sqlite3")

    task_id = agents.create_task("write unit tests for memory")
    task = task_queue.get_task(task_id)

    assert task["agent_id"] in {"junior_developer", "qa_engineer"}


def test_run_task_uses_local_fallback_when_llm_unavailable(monkeypatch, tmp_path):
    monkeypatch.setattr(task_queue, "DB_PATH", tmp_path / "tasks.sqlite3")
    monkeypatch.setattr(agents.llm, "ask_simple_with_provider_chain", lambda *args, **kwargs: None)
    monkeypatch.setattr(agents.memory, "remember_fact", lambda *args, **kwargs: None)
    monkeypatch.setattr(agents.skill_library, "prompt_prefix", lambda *args, **kwargs: "")
    monkeypatch.setattr(agents.skill_library, "record_example", lambda *args, **kwargs: None)
    monkeypatch.setattr(agents.competence, "infer_topics", lambda text: ["web_research"])
    monkeypatch.setattr(agents.competence, "prompt_summary", lambda *args, **kwargs: "Competence map: web_research=0.5.")
    monkeypatch.setattr(agents.competence, "weakest_topics", lambda *args, **kwargs: [])
    monkeypatch.setattr(agents.competence, "record_result", lambda *args, **kwargs: {"web_research": 0.55})
    monkeypatch.setattr(agents, "config_value", lambda key, default=None: True if key == "v2_agent_use_llm" else False if key in {"v2_agent_delegation_enabled", "v2_agent_autonomous_research_enabled"} else default)
    task = {"id": 1, "title": "Research APIs", "description": "Find free options", "agent_id": "research_analyst"}

    result = agents.run_task(task)

    assert result["agent_id"] == "research_analyst"
    assert result["mode"] == "local"
    assert "Summary:" in result["summary"]


def test_run_task_adds_research_context_for_research_agent(monkeypatch, tmp_path):
    monkeypatch.setattr(task_queue, "DB_PATH", tmp_path / "tasks.sqlite3")
    prompts = []
    monkeypatch.setattr(agents.llm, "ask_simple_with_provider_chain", lambda prompt, *args, **kwargs: prompts.append(prompt) or "Summary: researched")
    monkeypatch.setattr(agents.memory, "remember_fact", lambda *args, **kwargs: None)
    monkeypatch.setattr(agents.skill_library, "prompt_prefix", lambda *args, **kwargs: "")
    monkeypatch.setattr(agents.skill_library, "record_example", lambda *args, **kwargs: None)
    monkeypatch.setattr(agents.competence, "infer_topics", lambda text: ["web_research"])
    monkeypatch.setattr(agents.competence, "prompt_summary", lambda *args, **kwargs: "Competence map: web_research=0.4.")
    monkeypatch.setattr(agents.competence, "weakest_topics", lambda *args, **kwargs: [{"topic": "web_research", "score": 0.4}])
    monkeypatch.setattr(agents.competence, "record_result", lambda *args, **kwargs: {"web_research": 0.45})
    monkeypatch.setattr(agents.research, "research_topic", lambda *args, **kwargs: {"notes": "Fresh research context:\n- Official docs"})
    monkeypatch.setattr(agents, "config_value", lambda key, default=None: True if key in {"v2_agent_use_llm", "v2_agent_autonomous_research_enabled"} else 1 if key == "research_max_sources" else default)
    task = {"id": 1, "title": "Research official docs", "description": "Find free options", "agent_id": "research_analyst"}

    result = agents.run_task(task)

    assert result["researched"] is True
    assert "Fresh research context" in prompts[0]


def test_research_handoff_teaches_target_agent(monkeypatch, tmp_path):
    from core import long_term_learning

    monkeypatch.setattr(task_queue, "DB_PATH", tmp_path / "tasks.sqlite3")
    monkeypatch.setattr(long_term_learning, "DB_PATH", tmp_path / "learning.sqlite3")
    prompts = []
    skills = []
    monkeypatch.setattr(agents.llm, "ask_simple_with_provider_chain", lambda prompt, *args, **kwargs: prompts.append(prompt) or "Summary: planned")
    monkeypatch.setattr(agents.memory, "remember_fact", lambda *args, **kwargs: None)
    monkeypatch.setattr(agents.skill_library, "prompt_prefix", lambda *args, **kwargs: "")
    monkeypatch.setattr(agents.skill_library, "record_example", lambda *args, **kwargs: None)
    monkeypatch.setattr(agents.skill_library, "add_skill", lambda *args, **kwargs: skills.append((args, kwargs)) or "skill")
    monkeypatch.setattr(agents.competence, "infer_topics", lambda text: ["python", "web_research"])
    monkeypatch.setattr(agents.competence, "prompt_summary", lambda *args, **kwargs: "Competence map: python=0.4.")
    monkeypatch.setattr(agents.competence, "weakest_topics", lambda *args, **kwargs: [{"topic": "python", "score": 0.4}])
    monkeypatch.setattr(agents.competence, "record_result", lambda *args, **kwargs: {"python": 0.45})
    monkeypatch.setattr(agents.research, "research_topic", lambda *args, **kwargs: {"notes": "Fresh research context:\n- Use official FastAPI docs."})
    monkeypatch.setattr(
        agents,
        "config_value",
        lambda key, default=None: True
        if key in {"v2_agent_use_llm", "v2_agent_autonomous_research_enabled"}
        else False
        if key in {"v2_agent_delegation_enabled", "v2_agent_questions_enabled"}
        else 1
        if key == "research_max_sources"
        else default,
    )
    task_id = task_queue.create_task("Plan FastAPI endpoint", agent_id="senior_developer")
    task = task_queue.get_task(task_id)

    result = agents.run_task(task)
    messages = task_queue.get_messages(task_id, limit=10)
    thoughts = agent_thought_bus.list_thoughts(target_agent_id="senior_developer", limit=5)

    assert result["researched"] is True
    assert "Fresh research context" in prompts[0]
    assert any("Research handoff to senior_developer" in message["message"] for message in messages)
    assert any(item["packet_type"] == "research_handoff" for item in thoughts)
    assert skills and skills[0][1]["agent_id"] == "senior_developer"
    assert long_term_learning.recent_items(limit=3)


def test_run_task_reads_silent_thought_bus_context(monkeypatch, tmp_path):
    monkeypatch.setattr(task_queue, "DB_PATH", tmp_path / "tasks.sqlite3")
    prompts = []
    monkeypatch.setattr(agents.llm, "ask_simple_with_provider_chain", lambda prompt, *args, **kwargs: prompts.append(prompt) or "Summary: used thought")
    monkeypatch.setattr(agents.memory, "remember_fact", lambda *args, **kwargs: None)
    monkeypatch.setattr(agents.skill_library, "prompt_prefix", lambda *args, **kwargs: "")
    monkeypatch.setattr(agents.skill_library, "record_example", lambda *args, **kwargs: None)
    monkeypatch.setattr(agents.competence, "infer_topics", lambda text: ["general"])
    monkeypatch.setattr(agents.competence, "prompt_summary", lambda *args, **kwargs: "Competence map: general=0.5.")
    monkeypatch.setattr(agents.competence, "weakest_topics", lambda *args, **kwargs: [])
    monkeypatch.setattr(agents.competence, "record_result", lambda *args, **kwargs: {"general": 0.55})
    monkeypatch.setattr(
        agents,
        "config_value",
        lambda key, default=None: True
        if key in {"v2_agent_use_llm", "agent_thought_bus_enabled"}
        else False
        if key in {"v2_agent_autonomous_research_enabled", "v2_agent_delegation_enabled", "v2_agent_questions_enabled"}
        else 6
        if key == "agent_thought_bus_prompt_limit"
        else default,
    )
    task_id = task_queue.create_task("Implement auth endpoint", agent_id="senior_developer")
    agent_thought_bus.post_thought(
        "research_analyst",
        "finding",
        "Use FastAPI Depends for bearer auth",
        target_agent_id="senior_developer",
        task_id=task_id,
        confidence=0.8,
    )
    task = task_queue.get_task(task_id)

    agents.run_task(task)

    assert "Silent thought bus context" in prompts[0]
    assert "Use FastAPI Depends" in prompts[0]


def test_agent_question_routes_to_peer_agent(monkeypatch, tmp_path):
    monkeypatch.setattr(task_queue, "DB_PATH", tmp_path / "tasks.sqlite3")
    monkeypatch.setattr(
        agents.llm,
        "ask_simple_with_provider_chain",
        lambda *args, **kwargs: "Summary: design ready\nAgent question to qa_engineer: What regression tests should cover this dashboard?",
    )
    monkeypatch.setattr(agents.memory, "remember_fact", lambda *args, **kwargs: None)
    monkeypatch.setattr(agents.skill_library, "prompt_prefix", lambda *args, **kwargs: "")
    monkeypatch.setattr(agents.skill_library, "record_example", lambda *args, **kwargs: None)
    monkeypatch.setattr(agents.competence, "infer_topics", lambda text: ["general"])
    monkeypatch.setattr(agents.competence, "prompt_summary", lambda *args, **kwargs: "Competence map: general=0.5.")
    monkeypatch.setattr(agents.competence, "weakest_topics", lambda *args, **kwargs: [])
    monkeypatch.setattr(agents.competence, "record_result", lambda *args, **kwargs: {"general": 0.55})
    monkeypatch.setattr(
        agents,
        "config_value",
        lambda key, default=None: True
        if key in {"v2_agent_use_llm", "v2_agent_delegation_enabled", "v2_agent_questions_enabled"}
        else False
        if key in {"v2_agent_autonomous_research_enabled", "v2_dynamic_decomposition_enabled"}
        else 4
        if key == "v2_max_subtasks_per_task"
        else default,
    )
    parent_id = task_queue.create_task("Design dashboard panel", agent_id="ui_ux_designer")
    task = task_queue.get_task(parent_id)

    result = agents.run_task(task)
    child = task_queue.get_task(result["spawned_subtasks"][0])

    assert child["agent_id"] == "qa_engineer"
    assert child["input"]["source"] == "agent_question"
    assert "regression tests" in child["description"]


def test_agent_provider_routes_prefer_design_and_local_cheap_agents(monkeypatch):
    def fake_config(key, default=None):
        values = {
            "v2_agent_provider_routes": {
                "default": "nvidia>ollama",
                "ui_ux_designer": "gemini>nvidia>ollama",
                "qa_engineer": "ollama>nvidia",
            },
            "llm_provider": "nvidia",
            "llm_fallback_provider": "ollama",
        }
        return values.get(key, default)

    monkeypatch.setattr(agents, "config_value", fake_config)

    assert agents._agent_provider_chain("ui_ux_designer") == ["gemini", "nvidia", "ollama"]
    assert agents._agent_provider_chain("qa_engineer") == ["ollama", "nvidia"]
    assert agents._agent_provider_chain("research_analyst") == ["nvidia", "ollama"]


def test_api_agent_mode_moves_cpu_sensitive_agents_online_first(monkeypatch):
    def fake_config(key, default=None):
        values = {
            "v2_api_agent_mode_enabled": True,
            "v2_api_background_worker_count": 10,
            "v2_api_agent_force_online_first": True,
            "v2_api_agent_online_providers": "nvidia>gemini",
            "v2_agent_provider_routes": {
                "default": "nvidia>ollama",
                "qa_engineer": "ollama>nvidia",
                "junior_developer": "ollama>nvidia",
            },
            "llm_provider": "nvidia",
            "llm_fallback_provider": "ollama",
        }
        return values.get(key, default)

    monkeypatch.setattr(agents, "config_value", fake_config)
    monkeypatch.setattr(agents.llm, "provider_has_credentials", lambda provider: provider == "nvidia" or provider == "ollama")

    assert agents.api_agent_mode_enabled() is True
    assert agents.default_worker_count() == 10
    assert agents._agent_provider_chain("qa_engineer") == ["nvidia", "ollama"]
    assert agents._agent_provider_chain("junior_developer") == ["nvidia", "ollama"]


def test_ceo_task_spawns_child_tasks(monkeypatch, tmp_path):
    monkeypatch.setattr(task_queue, "DB_PATH", tmp_path / "tasks.sqlite3")
    monkeypatch.setattr(agents.llm, "ask_simple_with_provider_chain", lambda *args, **kwargs: "Summary: delegated")
    monkeypatch.setattr(agents.memory, "remember_fact", lambda *args, **kwargs: None)
    monkeypatch.setattr(agents.skill_library, "prompt_prefix", lambda *args, **kwargs: "")
    monkeypatch.setattr(agents.skill_library, "record_example", lambda *args, **kwargs: None)
    monkeypatch.setattr(agents.competence, "infer_topics", lambda text: ["general"])
    monkeypatch.setattr(agents.competence, "prompt_summary", lambda *args, **kwargs: "Competence map: general=0.5.")
    monkeypatch.setattr(agents.competence, "weakest_topics", lambda *args, **kwargs: [])
    monkeypatch.setattr(agents.competence, "record_result", lambda *args, **kwargs: {"general": 0.55})
    monkeypatch.setattr(
        agents,
        "config_value",
        lambda key, default=None: True
        if key in {"v2_agent_use_llm", "v2_agent_delegation_enabled"}
        else False
        if key == "v2_agent_autonomous_research_enabled"
        else 4
        if key == "v2_max_subtasks_per_task"
        else default,
    )
    parent_id = task_queue.create_task("Build a dashboard", agent_id="ceo")
    task = task_queue.get_task(parent_id)

    result = agents.run_task(task)
    children = [item for item in task_queue.list_tasks(limit=10) if item["parent_id"] == parent_id]

    assert len(result["spawned_subtasks"]) == 4
    assert {child["agent_id"] for child in children} >= {"product_manager", "research_analyst", "senior_developer", "qa_engineer"}


def test_dynamic_decomposition_spawns_llm_child_tasks(monkeypatch, tmp_path):
    monkeypatch.setattr(task_queue, "DB_PATH", tmp_path / "tasks.sqlite3")
    responses = iter(
        [
            "Summary: deploy plan ready",
            '[{"agent_id":"devops","title":"Prepare Render deploy","description":"Create cloud deployment steps."}]',
        ]
    )
    monkeypatch.setattr(agents.llm, "ask_simple_with_provider_chain", lambda *args, **kwargs: next(responses))
    monkeypatch.setattr(agents.memory, "remember_fact", lambda *args, **kwargs: None)
    monkeypatch.setattr(agents.skill_library, "prompt_prefix", lambda *args, **kwargs: "")
    monkeypatch.setattr(agents.skill_library, "record_example", lambda *args, **kwargs: None)
    monkeypatch.setattr(agents.competence, "infer_topics", lambda text: ["general"])
    monkeypatch.setattr(agents.competence, "prompt_summary", lambda *args, **kwargs: "Competence map: general=0.5.")
    monkeypatch.setattr(agents.competence, "weakest_topics", lambda *args, **kwargs: [])
    monkeypatch.setattr(agents.competence, "record_result", lambda *args, **kwargs: {"general": 0.55})
    monkeypatch.setattr(
        agents,
        "config_value",
        lambda key, default=None: True
        if key in {"v2_agent_use_llm", "v2_agent_delegation_enabled", "v2_dynamic_decomposition_enabled"}
        else False
        if key == "v2_agent_autonomous_research_enabled"
        else 4
        if key == "v2_max_subtasks_per_task"
        else default,
    )
    parent_id = task_queue.create_task("Deploy Friday dashboard", agent_id="ceo")
    task = task_queue.get_task(parent_id)

    result = agents.run_task(task)
    child = task_queue.get_task(result["spawned_subtasks"][0])

    assert child["agent_id"] == "devops"
    assert child["title"] == "Prepare Render deploy"


def test_junior_task_spawns_mentoring_review(monkeypatch, tmp_path):
    monkeypatch.setattr(task_queue, "DB_PATH", tmp_path / "tasks.sqlite3")
    monkeypatch.setattr(agents.llm, "ask_simple_with_provider_chain", lambda *args, **kwargs: "Summary: implemented")
    monkeypatch.setattr(agents.memory, "remember_fact", lambda *args, **kwargs: None)
    monkeypatch.setattr(agents.skill_library, "prompt_prefix", lambda *args, **kwargs: "")
    monkeypatch.setattr(agents.skill_library, "record_example", lambda *args, **kwargs: None)
    monkeypatch.setattr(agents.competence, "infer_topics", lambda text: ["python"])
    monkeypatch.setattr(agents.competence, "prompt_summary", lambda *args, **kwargs: "Competence map: python=0.7.")
    monkeypatch.setattr(agents.competence, "weakest_topics", lambda *args, **kwargs: [])
    monkeypatch.setattr(agents.competence, "record_result", lambda *args, **kwargs: {"python": 0.75})
    monkeypatch.setattr(
        agents,
        "config_value",
        lambda key, default=None: True
        if key in {"v2_agent_use_llm", "v2_agent_delegation_enabled", "v2_mentoring_enabled"}
        else False
        if key == "v2_agent_autonomous_research_enabled"
        else 4
        if key == "v2_max_subtasks_per_task"
        else default,
    )
    parent_id = task_queue.create_task("Implement parser", agent_id="junior_developer")
    task = task_queue.get_task(parent_id)

    result = agents.run_task(task)
    child = task_queue.get_task(result["spawned_subtasks"][0])

    assert child["agent_id"] == "senior_developer"
    assert "Review Junior Developer output" in child["title"]


def test_structured_review_feedback_is_stored(monkeypatch):
    from core import knowledge_graph

    edges = []
    skills = []
    monkeypatch.setattr(knowledge_graph, "add_edge", lambda *args, **kwargs: edges.append((args, kwargs)))
    monkeypatch.setattr(agents.skill_library, "add_skill", lambda *args, **kwargs: skills.append((args, kwargs)) or "skill")

    feedback = agents._structured_review_feedback(
        agents.get_agent("senior_developer"),
        "Review Junior Developer output for parser",
        "Strengths: simple parser\nIssues: missing tests\nLesson: add regression tests before refactors\nPractice topic: tests",
    )
    agents._store_review_feedback("Review Junior Developer output for parser", feedback)

    assert feedback["practice_topic"] == "tests"
    assert any(edge[0][1] == "TAUGHT" for edge in edges)
    assert skills


def test_ethical_hacker_task_requires_explicit_approval(monkeypatch, tmp_path):
    monkeypatch.setattr(task_queue, "DB_PATH", tmp_path / "tasks.sqlite3")

    task_id = agents.create_task("Test authorized target", agent_id="ethical_hacker")
    blocked = task_queue.get_task(task_id)

    assert blocked["status"] == "blocked"
    assert agents.approve_guarded_task(task_id, "sounds good") is False
    assert agents.approve_guarded_task(task_id, f"I authorize task {task_id}") is True
    assert task_queue.get_task(task_id)["status"] == "pending"
