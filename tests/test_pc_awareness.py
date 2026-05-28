from pathlib import Path

from core import pc_awareness
from tools import pc_control


def test_pc_awareness_finds_desktop_shortcut(monkeypatch):
    monkeypatch.setattr(pc_awareness, "reload_config", lambda: {"allowed_apps": {}})
    monkeypatch.setattr(
        pc_awareness,
        "snapshot",
        lambda: {
            "desktop_apps": [
                {"source": "desktop", "name": "Figma", "path": r"C:\Users\User\Desktop\Figma.lnk", "launch_target": r"C:\Users\User\Desktop\Figma.lnk"}
            ],
            "shortcuts": [],
            "installed_apps": [],
            "running_apps": [],
        },
    )

    result = pc_awareness.find_app("figma")

    assert result["found"] is True
    assert result["name"] == "Figma"
    assert result["launch_target"].endswith("Figma.lnk")


def test_pc_awareness_collects_desktop_and_url_shortcuts(monkeypatch, tmp_path):
    desktop = tmp_path / "Desktop"
    desktop.mkdir()
    (desktop / "Figma.lnk").write_text("", encoding="utf-8")
    (desktop / "Calendar.url").write_text("[InternetShortcut]\nURL=https://calendar.google.com/\n", encoding="utf-8")
    monkeypatch.setattr(pc_awareness, "_shortcut_roots", lambda: [("desktop", desktop)])
    monkeypatch.setattr(pc_awareness, "config_value", lambda key, default=None: 20 if key == "pc_awareness_max_shortcuts" else default)

    items = pc_awareness._collect_shortcuts()

    names = {item["name"]: item for item in items}
    assert "Figma" in names
    assert names["Calendar"]["launch_target"] == "https://calendar.google.com/"


def test_pc_control_resolves_app_from_awareness(monkeypatch):
    from core import pc_awareness as awareness

    monkeypatch.setattr(
        awareness,
        "find_app",
        lambda query: {"found": True, "name": "Figma", "source": "desktop", "launch_target": r"C:\Users\User\Desktop\Figma.lnk"},
    )
    monkeypatch.setattr(pc_control, "_find_start_menu_shortcut", lambda name: None)

    assert pc_control._resolve_app_target("figma") == r"C:\Users\User\Desktop\Figma.lnk"


def test_pc_control_lists_awareness_inventory(monkeypatch):
    from core import pc_awareness as awareness

    monkeypatch.setattr(awareness, "running_apps", lambda limit=0: [{"name": "Chrome", "pid": 1}])
    monkeypatch.setattr(awareness, "installed_apps", lambda limit=0: [{"name": "Figma"}])
    monkeypatch.setattr(awareness, "desktop_apps", lambda limit=0: [{"name": "VS Code"}])

    assert "Chrome" in pc_control.execute({"action": "list_running_apps"})
    assert "Figma" in pc_control.execute({"action": "list_installed_apps"})
    assert "VS Code" in pc_control.execute({"action": "list_desktop_apps"})
