from pathlib import Path

from core import friday_memory, project_ideation, task_files


def _isolate(monkeypatch, tmp_path):
    monkeypatch.setattr(project_ideation, "DB_PATH", tmp_path / "project_ideation.sqlite3")
    monkeypatch.setattr(friday_memory, "DB_PATH", tmp_path / "friday_memory.sqlite3")


def test_project_ideas_require_source_backed_demand(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)

    def fake_search(query, *, limit=3):
        return [
            {
                "title": "Small business support pain point",
                "url": f"https://example.com/support-{limit}",
                "snippet": "Founders need help with customer support replies, inbox workflow, and manual follow up.",
            },
            {
                "title": "Invoice spreadsheet problem",
                "url": f"https://example.com/invoice-{limit}",
                "snippet": "Small business owners struggle with invoice payment tracking and spreadsheet admin.",
            },
            {
                "title": "Client onboarding checklist need",
                "url": f"https://example.com/onboarding-{limit}",
                "snippet": "Agencies need better client onboarding, requirements intake, and handoff workflow.",
            },
        ]

    monkeypatch.setattr(project_ideation.research, "search_web", fake_search)

    result = project_ideation.research_project_ideas("AI tools for SMB operators", root=tmp_path, limit=3, max_sources=6)

    assert result["research_sufficient"] is True
    assert result["ideas"]
    assert result["sources"]
    assert any(path.endswith("research-brief.md") for path in result["artifacts"])
    assert Path(result["artifacts"][0]).exists()


def test_project_ideas_refuse_to_guess_without_sources(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    monkeypatch.setattr(project_ideation.research, "search_web", lambda *args, **kwargs: [])

    result = project_ideation.research_project_ideas("AI products", root=tmp_path)

    assert result["research_sufficient"] is False
    assert result["ideas"] == []
    assert "cannot recommend" in result["summary"].lower()


def test_task_files_write_readable_packet(tmp_path):
    result = task_files.write_task_files(
        tmp_path,
        "Build a web-app for client intake",
        run_id=7,
        intent={"user_intent": "implement", "recommended_action": "edit_or_build_with_verification"},
        architecture={"framework": "nextjs", "package_manager": "npm", "style_profile_id": "nexus_forge_nextjs"},
        execution_plan={"flow": ["inspect", "build", "verify"]},
    )

    assert len(result["files"]) >= 13
    assert (Path(result["root"]) / "requirements.md").exists()
    assert (Path(result["root"]) / "requirements.docx").exists()
    assert (Path(result["root"]) / "requirements.pdf").read_bytes().startswith(b"%PDF-1.4")
    assert "Build a web-app" in (Path(result["root"]) / "requirements.md").read_text(encoding="utf-8")
    assert (Path(result["root"]) / "system-design.md").exists()
    assert (Path(result["root"]) / "implementation-plan.md").exists()
    assert (Path(result["root"]) / "features.md").exists()
