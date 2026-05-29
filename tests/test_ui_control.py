from core import app_operators, desktop_tasks, pc_awareness, ui_control, visual_monitor


def _isolate(monkeypatch, tmp_path):
    monkeypatch.setattr(desktop_tasks, "DB_PATH", tmp_path / "desktop_tasks.sqlite3")
    monkeypatch.setattr(pc_awareness, "DB_PATH", tmp_path / "pc_awareness.sqlite3")
    monkeypatch.setattr(visual_monitor, "DB_PATH", tmp_path / "visual_monitor.sqlite3")
    monkeypatch.setattr(visual_monitor, "FRAME_ROOT", tmp_path / "frames")
    monkeypatch.setattr(
        pc_awareness,
        "snapshot",
        lambda force_refresh=False: {
            "available": True,
            "active_window": "Invoices - Browser",
            "running_apps": [{"name": "Invoices", "source": "running", "launch_target": "invoices.exe"}],
            "desktop_apps": [{"name": "Ledger", "source": "desktop", "launch_target": "ledger.exe"}],
            "shortcuts": [],
            "installed_apps": [],
            "stats": {"running_apps": 1, "desktop_apps": 1},
            "summary": "PC ready.",
        },
    )
    monkeypatch.setattr(pc_awareness, "find_app", lambda query: {"found": True, "name": query, "source": "test", "launch_target": f"{query}.exe"})


def test_ui_control_status_exposes_dynamic_actions(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)

    status = ui_control.status("invoices")

    assert status["active_window"] == "Invoices - Browser"
    assert any(item["id"] == "screen_step" for item in status["actions"])
    assert status["discovered_apps"][0]["name"] == "Invoices"


def test_unknown_app_gets_dynamic_operator(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)

    context = app_operators.operator_context("InvoiceDesk")

    assert context["available"] is True
    assert context["source"] == "dynamic"
    assert context["operator"]["open_target"] == "InvoiceDesk.exe"


def test_ui_control_action_wraps_pc_control(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    calls = []

    from tools import pc_control

    monkeypatch.setattr(pc_control, "execute", lambda inputs: calls.append(inputs) or "Clicked at 10, 20.")

    result = ui_control.execute("click", x=10, y=20)

    assert result["ok"] is True
    assert calls == [{"action": "click", "x": 10.0, "y": 20.0}]
