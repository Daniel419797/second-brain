import json
from pathlib import Path

from core import document_knowledge, task_files


def test_task_files_generate_and_index_readable_docs(monkeypatch, tmp_path):
    monkeypatch.setattr(document_knowledge, "_load_llama_index", lambda: {"available": False, "error": "missing"})

    result = task_files.write_task_files(
        tmp_path,
        "Build a production-ready web-app for support triage",
        run_id="42",
        intent={"user_intent": "implement this", "recommended_action": "build_project"},
        architecture={"framework": "Next.js", "package_manager": "npm", "style_profile_id": "nexus_forge_nextjs"},
        formats=["md"],
    )

    manifest = json.loads(Path(result["root"], "manifest.json").read_text(encoding="utf-8"))

    assert result["knowledge_index"]["ok"] is True
    assert result["knowledge_index"]["backend"] == "native"
    assert Path(result["knowledge_index"]["artifact"]).exists()
    assert manifest["knowledge_index"]["artifact"] == result["knowledge_index"]["artifact"]
    assert any(path.endswith("requirements.md") for path in result["files"])
