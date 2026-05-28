from core import capability_center
from tools import capability_center as capability_tool


def test_security_scope_local_target_is_verified(monkeypatch, tmp_path):
    monkeypatch.setattr(capability_center, "DB_PATH", tmp_path / "capabilities.sqlite3")
    monkeypatch.setattr(capability_center, "REPORT_DIR", tmp_path / "reports")

    scope = capability_center.create_security_scope("127.0.0.1", kind="local")
    scopes = capability_center.list_security_scopes()

    assert scope["status"] == "verified"
    assert scopes[0]["target"] == "127.0.0.1"


def test_external_port_scan_requires_verified_scope(monkeypatch, tmp_path):
    monkeypatch.setattr(capability_center, "DB_PATH", tmp_path / "capabilities.sqlite3")
    monkeypatch.setattr(capability_center, "REPORT_DIR", tmp_path / "reports")
    monkeypatch.setattr(capability_center, "_is_local_or_private", lambda host: False)

    result = capability_center.scan_open_ports("example.com", ports=[80])

    assert result["requires_scope"] is True


def test_workspace_map_and_auto_docs(monkeypatch, tmp_path):
    monkeypatch.setattr(capability_center, "DB_PATH", tmp_path / "capabilities.sqlite3")
    monkeypatch.setattr(capability_center, "REPORT_DIR", tmp_path / "reports")
    (tmp_path / "package.json").write_text('{"name":"demo"}', encoding="utf-8")
    (tmp_path / "app.py").write_text("print('hi')", encoding="utf-8")

    mapped = capability_center.workspace_project_map(tmp_path)
    docs = capability_center.workspace_auto_docs(tmp_path)

    assert mapped["total_files_scanned"] >= 2
    assert "friday_project_map.md" in docs["path"]


def test_tool_formats_daily_brief(monkeypatch):
    monkeypatch.setattr(capability_center, "personal_brief", lambda: {"summary": "You have one thing to do."})

    assert capability_tool.execute({"action": "daily_brief"}) == "You have one thing to do."
