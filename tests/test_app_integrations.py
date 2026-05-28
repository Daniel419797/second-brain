from core import app_integrations
from tools import app_integrations as app_tool


def isolate_integrations(monkeypatch, tmp_path):
    monkeypatch.setattr(app_integrations, "DB_PATH", tmp_path / "integrations.sqlite3")
    monkeypatch.setattr(app_integrations, "OFFICE_DIR", tmp_path / "office_docs")
    monkeypatch.setattr(
        app_integrations,
        "config_value",
        lambda key, default=None: {
            "office_docs_dir": str(tmp_path / "office_docs"),
            "workspace_index_extensions": ".py,.md,.txt,.json",
            "workspace_index_skip_dirs": ".git,.venv,node_modules",
            "workspace_index_snippet_chars": 1000,
            "workspace_index_max_files": 100,
        }.get(key, default),
    )
    app_integrations.init_db()


def test_contacts_reminders_and_calendar_are_persisted(monkeypatch, tmp_path):
    isolate_integrations(monkeypatch, tmp_path)

    contact = app_integrations.create_contact("Ada Lovelace", email="ada@example.com")
    reminder = app_integrations.create_reminder("call Ada", due_at="tomorrow")
    event = app_integrations.create_calendar_event("demo", start_at="today")

    assert app_integrations.search_contacts("ada")[0]["id"] == contact["id"]
    assert app_integrations.list_reminders()[0]["id"] == reminder["id"]
    assert app_integrations.complete_reminder(reminder["id"])["status"] == "done"
    assert app_integrations.list_calendar_events()[0]["id"] == event["id"]


def test_workspace_index_search_and_overview(monkeypatch, tmp_path):
    isolate_integrations(monkeypatch, tmp_path)
    (tmp_path / "main.py").write_text("def hello():\n    return 'Friday'\n", encoding="utf-8")
    (tmp_path / "README.md").write_text("# Project\nvoice assistant dashboard\n", encoding="utf-8")

    indexed = app_integrations.index_workspace(tmp_path)
    results = app_integrations.search_workspace("voice assistant")
    overview = app_integrations.workspace_overview(tmp_path)

    assert indexed["indexed"] == 2
    assert results[0]["path"] == "README.md"
    assert overview["total_files"] == 2


def test_tool_formats_deep_integration_results(monkeypatch, tmp_path):
    isolate_integrations(monkeypatch, tmp_path)

    assert "Contact saved" in app_tool.execute({"action": "create_contact", "name": "Grace", "email": "grace@example.com"})
    assert "Reminder saved" in app_tool.execute({"action": "create_reminder", "title": "review docs"})
    assert "Document created" in app_tool.execute({"action": "create_doc", "title": "Launch Notes"})
    assert "Sheet created" in app_tool.execute({"action": "create_sheet", "title": "Budget"})
