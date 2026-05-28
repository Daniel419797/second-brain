from core import intent_engine


def test_rule_classifier_materializes_coding_project_under_coding_root(monkeypatch, tmp_path):
    monkeypatch.setattr(intent_engine, "resolve_coding_root", lambda root="": tmp_path)

    result = intent_engine.classify("could you make a web app that tracks invoices")

    assert result.actionable
    assert result.intent == "start_coding_project"
    assert result.source == "rules"
    assert result.tool_name == "power_center"
    assert result.tool_input == {
        "action": "autonomous_coding",
        "request": "a web app that tracks invoices",
        "root": str(tmp_path),
        "risk_level": "medium",
    }


def test_rule_classifier_extracts_agent_task_slots():
    result = intent_engine.classify("get the research agent to compare OCR libraries")

    assert result.actionable
    assert result.intent == "create_agent_task"
    assert result.tool_name == "agent_team"
    assert result.tool_input == {
        "action": "create_task",
        "title": "compare OCR libraries",
        "agent_id": "research_analyst",
    }


def test_rule_classifier_extracts_academic_project_slots():
    result = intent_engine.classify("write a final year project on blockchain based voting system")

    assert result.actionable
    assert result.intent == "academic_project"
    assert result.tool_name == "power_center"
    assert result.tool_input == {
        "action": "academic_project",
        "topic": "blockchain based voting system",
        "kind": "final_year_project",
        "citation_style": "APA",
        "formats": ["md", "docx", "pdf"],
    }


def test_rule_classifier_extracts_git_status():
    result = intent_engine.classify("git status")

    assert result.actionable
    assert result.intent == "git_status"
    assert result.tool_name == "power_center"
    assert result.tool_input == {"action": "git_status"}


def test_rule_classifier_extracts_git_clone():
    result = intent_engine.classify("clone github repo octo/demo to demo-app")

    assert result.actionable
    assert result.intent == "git_clone"
    assert result.tool_input == {"action": "git_clone", "repo": "octo/demo", "destination": "demo-app"}


def test_rule_classifier_extracts_git_add_and_branches():
    add_result = intent_engine.classify("git add app.py tests/test_app.py")
    branch_result = intent_engine.classify("git branches")

    assert add_result.actionable
    assert add_result.tool_input == {"action": "git_add", "paths": ["app.py", "tests/test_app.py"]}
    assert branch_result.actionable
    assert branch_result.tool_input == {"action": "git_branches"}


def test_rule_classifier_extracts_3d_model_export():
    result = intent_engine.classify("generate a 3d model of a low poly spaceship as glb")

    assert result.actionable
    assert result.intent == "create_3d_model"
    assert result.tool_input == {
        "action": "model3d_create",
        "prompt": "a low poly spaceship",
        "formats": ["glb"],
    }


def test_rule_classifier_routes_complex_3d_models():
    result = intent_engine.classify("make a 3d model of a city with houses")

    assert result.actionable
    assert result.intent == "create_3d_model"
    assert result.tool_input == {
        "action": "model3d_create",
        "prompt": "a city with houses",
        "formats": ["obj", "stl", "gltf", "glb"],
    }


def test_rule_classifier_marks_photorealistic_3d_quality():
    result = intent_engine.classify("make a photorealistic zbrush quality 3d model of a human")

    assert result.actionable
    assert result.tool_input == {
        "action": "model3d_create",
        "prompt": "a human",
        "formats": ["obj", "stl", "gltf", "glb"],
        "quality": "studio",
    }


def test_semantic_classifier_handles_non_hardcoded_action(monkeypatch, tmp_path):
    monkeypatch.setattr(intent_engine, "_RULE_CLASSIFIERS", ())
    monkeypatch.setattr(intent_engine, "resolve_coding_root", lambda root="": tmp_path)
    monkeypatch.setattr(
        intent_engine.llm,
        "ask_simple",
        lambda prompt, retries=1: '{"intent":"start_coding_project","confidence":0.91,"slots":{"request":"invoice portal for a small shop"},"reason":"software build request"}',
    )

    result = intent_engine.classify("I need something that can manage invoices for my shop", allow_llm=True)

    assert result.actionable
    assert result.intent == "start_coding_project"
    assert result.source == "llm"
    assert result.tool_input["request"] == "invoice portal for a small shop"
    assert result.tool_input["root"] == str(tmp_path)


def test_semantic_classifier_skips_general_questions(monkeypatch):
    def fail(*args, **kwargs):
        raise AssertionError("LLM classifier should not run for non-actionable chat")

    monkeypatch.setattr(intent_engine.llm, "ask_simple", fail)

    result = intent_engine.classify("what is 2+2", allow_llm=True)

    assert result.intent == "none"


def test_classifier_requires_confidence_threshold(monkeypatch):
    monkeypatch.setattr(intent_engine, "_RULE_CLASSIFIERS", ())
    monkeypatch.setattr(
        intent_engine.llm,
        "ask_simple",
        lambda prompt, retries=1: '{"intent":"start_coding_project","confidence":0.4,"slots":{"request":"maybe build a thing"},"reason":"low confidence"}',
    )

    result = intent_engine.classify("please sort out an idea for invoices", allow_llm=True)

    assert result.intent == "start_coding_project"
    assert not result.actionable
