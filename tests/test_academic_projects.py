import zipfile

from core import academic_projects, document_exports
from tools import power_center


def _isolate(monkeypatch, tmp_path, *, llm_enabled=False):
    def fake_config(key, default=None):
        values = {
            "academic_projects_dir": str(tmp_path / "academic_projects"),
            "academic_project_max_sources": 2,
            "academic_project_formats": "md,docx,pdf",
            "academic_project_llm_enabled": llm_enabled,
            "academic_project_provider_chain": "test",
        }
        return values.get(key, default)

    monkeypatch.setattr(academic_projects, "config_value", fake_config)
    monkeypatch.setattr(
        academic_projects.research,
        "research_topic",
        lambda topic, limit=2: {
            "query": topic,
            "sources": [
                {"title": "Official Blockchain Voting Study", "url": "https://example.edu/voting", "snippet": "Blockchain voting can improve auditability."},
                {"title": "Election Security Guide", "url": "https://example.org/security", "snippet": "Voting systems require privacy and verification controls."},
            ],
            "notes": "Fresh research context:\n- Official Blockchain Voting Study: Blockchain voting can improve auditability.\n- Election Security Guide: Privacy controls matter.",
        },
    )


def test_document_exports_create_docx_and_pdf(tmp_path):
    markdown = "# Sample\n\nThis is a source-backed draft.\n\n- First point"

    result = document_exports.export_markdown(markdown, tmp_path / "sample", formats=["md", "docx", "pdf"])

    assert set(result["paths"]) == {"md", "docx", "pdf"}
    assert (tmp_path / "sample.md").read_text(encoding="utf-8").startswith("# Sample")
    assert (tmp_path / "sample.pdf").read_bytes().startswith(b"%PDF-1.4")
    with zipfile.ZipFile(tmp_path / "sample.docx") as archive:
        assert "word/document.xml" in archive.namelist()
        assert "Sample" in archive.read("word/document.xml").decode("utf-8")


def test_academic_project_creates_source_notes_and_exports(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path, llm_enabled=False)

    project = academic_projects.create_project("Blockchain based voting system", kind="final year project")

    assert project["source_count"] == 2
    assert project["exports"]["docx"].endswith(".docx")
    assert project["exports"]["pdf"].endswith(".pdf")
    assert "source-notes.md" in project["source_notes"]
    assert "Academic final year project draft ready" in project["summary"]
    assert "Official Blockchain Voting Study" in open(project["source_notes"], encoding="utf-8").read()
    assert open(project["exports"]["pdf"], "rb").read(8).startswith(b"%PDF")


def test_academic_project_uses_llm_without_fabricating_export(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path, llm_enabled=True)
    monkeypatch.setattr(
        academic_projects.llm,
        "ask_simple_with_provider_chain",
        lambda prompt, providers, retries=1: "# Research Paper\n\nCited discussion uses [S1].\n\n## References\n- [S1] Official Blockchain Voting Study. https://example.edu/voting",
    )

    project = academic_projects.create_project("Blockchain based voting system", kind="research paper", citation_style="IEEE")

    draft = open(project["draft"], encoding="utf-8").read()
    assert "Cited discussion uses [S1]" in draft
    assert project["kind"] == "research_paper"
    assert project["exports"]["docx"].endswith(".docx")


def test_power_center_academic_project_action(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path, llm_enabled=False)
    monkeypatch.setattr(power_center, "_permission_reply", lambda inputs: "")

    result = power_center.execute({"action": "academic_project", "topic": "AI attendance system", "kind": "proposal"})

    assert "Academic proposal draft ready" in result
    assert ".docx" in result
    assert ".pdf" in result
