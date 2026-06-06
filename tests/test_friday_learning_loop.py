from pathlib import Path

from core import design_providers, friday_learning_loop, friday_memory, project_memory, style_profiles


def _config(overrides):
    def lookup(key, default=None):
        return overrides.get(key, default)

    return lookup


def _isolated_memory(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(friday_memory, "DB_PATH", tmp_path / "friday_memory.sqlite3")
    monkeypatch.setattr(project_memory, "DB_PATH", tmp_path / "project_memory.sqlite3")
    monkeypatch.setattr(style_profiles, "DB_PATH", tmp_path / "style_profiles.sqlite3")
    monkeypatch.setattr(friday_learning_loop.taste_memory, "learn", lambda *args, **kwargs: {"summary": "taste learned"})


def test_user_feedback_becomes_actionable_learning_context(monkeypatch, tmp_path):
    _isolated_memory(monkeypatch, tmp_path)

    result = friday_learning_loop.learn_from_user_feedback(
        "I hate the generic split hero. Do not default to text-left image-right SaaS layouts for design work.",
        root=tmp_path,
        domain="design",
        evidence=["manual_browser_review"],
    )

    assert result["ok"] is True
    assert result["memory"]["memory_type"] == "design_failure"
    assert "rejected_pattern" in result["memory"]["tags"]

    context = friday_learning_loop.learning_context_for_request(
        "Build a Nexus Forge developer-tools landing page",
        root=tmp_path,
        domain="design",
    )

    assert context["available"] is True
    assert any("split heroes" in line or "split hero" in line for line in context["prompt_lines"])
    assert any(item["memory_type"] == "design_failure" for item in context["rules"])


def test_run_outcome_writes_failure_and_learning_report(monkeypatch, tmp_path):
    _isolated_memory(monkeypatch, tmp_path)

    result = friday_learning_loop.learn_from_run_outcome(
        "Build a production landing page",
        root=tmp_path,
        gate_results={
            "status": "attention",
            "technical_ready": False,
            "failed_required": ["Rendered UI visual review: failed - H1 overlaps the next section"],
            "gates": [
                {
                    "id": "browser_visual_review",
                    "label": "Rendered UI visual review",
                    "group": "browser",
                    "status": "failed",
                    "required": True,
                    "summary": "H1 overlaps the next section",
                }
            ],
        },
        quality_reviews=[
            {
                "ok": False,
                "issues": [
                    {
                        "id": "visual_incoherent_copy",
                        "severity": 5,
                        "summary": "Hero copy is generic and incoherent.",
                    }
                ],
            }
        ],
        fix_attempts=[{"ok": True, "status": "css_fix", "summary": "Added responsive type and overflow guards."}],
        source="test",
    )

    assert result["status"] == "learned"
    assert result["lesson_count"] >= 3
    assert any("learning-report.json" in item for item in result["artifacts"])
    assert (tmp_path / ".friday" / "product-studio" / "learning" / "learning-report.md").exists()

    context = friday_learning_loop.learning_context_for_request("Build a polished landing page", root=tmp_path, domain="design")
    assert any("Hero copy is generic" in line for line in context["prompt_lines"])


def test_design_brief_includes_learned_rules_in_stitch_prompt(monkeypatch, tmp_path):
    _isolated_memory(monkeypatch, tmp_path)
    monkeypatch.setattr(design_providers, "config_value", _config({"design_stitch_prompt_budget_chars": 12000}))
    monkeypatch.delenv("STITCH_API_KEY", raising=False)
    monkeypatch.setattr(design_providers, "_node_package_available", lambda package, probe: False)

    friday_learning_loop.learn_from_user_feedback(
        "Never use Home 1, Home 2, Service 1, Service 2 labels or generic split hero scaffolds in websites.",
        root=tmp_path,
        domain="design",
    )

    brief = design_providers.design_brief(
        "Build a polished four-page website for a construction company with project photography and inquiry flow.",
        root=tmp_path,
        product_name="Northline Builders",
        stack={"stack": "nextjs", "label": "Next.js web app"},
    )

    prompt = brief["stitch_prompt"]
    assert brief["design_context"]["learned_rules"]["available"] is True
    assert "Learned Friday memory rules:" in prompt
    assert "Home 1" in prompt
    assert "generic split hero" in prompt or "generic left-text/right-card" in prompt
    design_doc = (tmp_path / ".friday" / "design" / "DESIGN.md").read_text(encoding="utf-8")
    assert "## Learned Friday Memory Rules" in design_doc
