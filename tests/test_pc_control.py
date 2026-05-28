from types import SimpleNamespace

from tools import pc_control


class FakeImage:
    def save(self, path):
        from pathlib import Path

        Path(path).write_text("fake image", encoding="utf-8")


class FakeWindow:
    def __init__(self):
        self.isMinimized = True
        self.restored = False
        self.activated = False
        self.title = "Chrome"
        self.left = 1
        self.top = 2
        self.width = 800
        self.height = 600

    def restore(self):
        self.restored = True
        self.isMinimized = False

    def activate(self):
        self.activated = True


class FakeGui:
    FAILSAFE = True

    def __init__(self):
        self.calls = []
        self.pos = (10, 20)
        self.window = FakeWindow()

    def position(self):
        return self.pos

    def size(self):
        return SimpleNamespace(width=1000, height=700)

    def moveTo(self, x, y, duration=0):
        self.pos = (x, y)
        self.calls.append(("moveTo", x, y, duration))

    def click(self, **kwargs):
        if "x" in kwargs and "y" in kwargs:
            self.pos = (kwargs["x"], kwargs["y"])
        self.calls.append(("click", kwargs))

    def dragTo(self, x, y, duration=0, button="left"):
        self.pos = (x, y)
        self.calls.append(("dragTo", x, y, duration, button))

    def scroll(self, amount):
        self.calls.append(("scroll", amount))

    def write(self, text, interval=0):
        self.calls.append(("write", text, interval))

    def press(self, key, presses=1):
        self.calls.append(("press", key, presses))

    def hotkey(self, *keys):
        self.calls.append(("hotkey", keys))

    def screenshot(self):
        self.calls.append(("screenshot",))
        return FakeImage()

    def getWindowsWithTitle(self, title):
        self.calls.append(("getWindowsWithTitle", title))
        return [self.window]

    def getActiveWindow(self):
        self.calls.append(("getActiveWindow",))
        return self.window


def enable_desktop(monkeypatch, extra=None):
    values = {
        "pc_trusted_mode_enabled": True,
        "pc_allow_desktop_automation": True,
        "pc_allow_arbitrary_paths": True,
        "blocked_paths": [],
        "desktop_mouse_duration_seconds": 0.12,
        "desktop_type_interval_seconds": 0.01,
        "desktop_max_type_chars": 1000,
    }
    if extra:
        values.update(extra)

    monkeypatch.setattr(pc_control, "config_value", lambda key, default=None: values.get(key, default))


def test_open_app_uses_allowed_path(monkeypatch):
    calls = []
    audit = []
    monkeypatch.setattr(pc_control, "_apps", lambda: {"chrome": "C:\\Chrome\\chrome.exe"})
    monkeypatch.setattr(pc_control, "config_value", lambda key, default=None: False if key == "browser_dom_launch_chrome_debug" else default)
    monkeypatch.setattr(pc_control.os, "startfile", lambda path: calls.append(path), raising=False)
    monkeypatch.setattr(pc_control, "_audit_pc_log", lambda level, message: audit.append((level, message)))

    assert "opened successfully" in pc_control._open_app("chrome")
    assert calls == ["C:\\Chrome\\chrome.exe"]
    assert audit and "action=open_app" in audit[0][1]


def test_open_app_denies_unknown_app(monkeypatch):
    monkeypatch.setattr(pc_control, "_apps", lambda: {"chrome": "C:\\Chrome\\chrome.exe"})
    monkeypatch.setattr(pc_control, "config_value", lambda key, default=None: False if key == "pc_trusted_mode_enabled" else default)

    assert "not in the allowed list" in pc_control._open_app("malware")


def test_open_app_can_resolve_arbitrary_app_in_trusted_mode(monkeypatch):
    calls = []

    def fake_config(key, default=None):
        values = {
            "pc_trusted_mode_enabled": True,
            "pc_allow_arbitrary_apps": True,
        }
        return values.get(key, default)

    monkeypatch.setattr(pc_control, "_apps", lambda: {})
    monkeypatch.setattr(pc_control, "config_value", fake_config)
    monkeypatch.setattr(pc_control.os, "startfile", lambda path: calls.append(path), raising=False)

    assert pc_control._open_app("calculator") == "Calculator opened successfully."
    assert calls == ["calc.exe"]


def test_open_app_supports_uri_targets(monkeypatch):
    calls = []
    monkeypatch.setattr(pc_control, "_apps", lambda: {"camera": "ms-camera:"})
    monkeypatch.setattr(pc_control, "config_value", lambda key, default=None: False if key == "browser_dom_launch_chrome_debug" else default)
    monkeypatch.setattr(pc_control.os, "startfile", lambda path: calls.append(path), raising=False)

    assert pc_control._open_app("camera") == "Camera opened successfully."
    assert calls == ["ms-camera:"]


def test_open_app_reports_launch_failure(monkeypatch):
    def fail_startfile(path):
        raise OSError("missing")

    monkeypatch.setattr(pc_control, "_apps", lambda: {"camera": "ms-camera:"})
    monkeypatch.setattr(pc_control, "config_value", lambda key, default=None: False if key == "browser_dom_launch_chrome_debug" else default)
    monkeypatch.setattr(pc_control.os, "startfile", fail_startfile, raising=False)

    assert pc_control._open_app("camera") == "I could not open Camera."


def test_open_path_opens_known_folder(monkeypatch):
    calls = []

    def fake_config(key, default=None):
        values = {
            "pc_trusted_mode_enabled": True,
            "pc_allow_arbitrary_paths": True,
            "blocked_paths": [],
        }
        return values.get(key, default)

    monkeypatch.setattr(pc_control, "config_value", fake_config)
    monkeypatch.setattr(pc_control.os, "startfile", lambda path: calls.append(path), raising=False)

    assert pc_control._open_path("home").startswith("Opened")
    assert calls


def test_read_file_allows_external_path_in_trusted_mode(monkeypatch, tmp_path):
    target = tmp_path / "note.txt"
    target.write_text("hello", encoding="utf-8")

    def fake_config(key, default=None):
        values = {
            "pc_trusted_mode_enabled": True,
            "pc_allow_arbitrary_paths": True,
            "blocked_paths": [],
        }
        return values.get(key, default)

    monkeypatch.setattr(pc_control, "config_value", fake_config)

    assert pc_control._read_file(str(target)) == "hello"


def test_run_command_requires_config_flag(monkeypatch):
    monkeypatch.setattr(pc_control, "config_value", lambda key, default=None: False if key == "pc_trusted_mode_enabled" else default)

    assert pc_control._run_command("Get-Date") == "Shell commands are disabled in config."


def test_blocked_system_path_is_not_safe():
    assert pc_control._is_safe_path("C:\\Windows\\System32\\cmd.exe") is False


def test_pyautogui_failsafe_enabled():
    assert pc_control.pyautogui.FAILSAFE is True


def test_move_mouse_uses_pyautogui(monkeypatch):
    fake = FakeGui()
    enable_desktop(monkeypatch)
    monkeypatch.setattr(pc_control, "pyautogui", fake)

    assert pc_control.execute({"action": "move_mouse", "x": 100, "y": 200}) == "Moved mouse to 100, 200."
    assert fake.calls == [("moveTo", 100, 200, 0.12)]


def test_click_can_use_current_position(monkeypatch):
    fake = FakeGui()
    enable_desktop(monkeypatch)
    monkeypatch.setattr(pc_control, "pyautogui", fake)

    assert pc_control.execute({"action": "click"}) == "Clicked at 10, 20."
    assert fake.calls == [("click", {"button": "left", "clicks": 1, "interval": 0.05})]


def test_right_click_and_drag(monkeypatch):
    fake = FakeGui()
    enable_desktop(monkeypatch)
    monkeypatch.setattr(pc_control, "pyautogui", fake)

    assert pc_control.execute({"action": "right_click", "target": "30 40"}) == "Right clicked at 30, 40."
    assert pc_control.execute({"action": "drag_mouse", "x": 50, "y": 60}) == "Dragged mouse to 50, 60."
    assert fake.calls[0] == ("click", {"x": 30, "y": 40, "button": "right", "clicks": 1, "interval": 0.05})
    assert fake.calls[1] == ("dragTo", 50, 60, 0.12, "left")


def test_type_press_hotkey_and_scroll(monkeypatch):
    fake = FakeGui()
    enable_desktop(monkeypatch)
    monkeypatch.setattr(pc_control, "pyautogui", fake)

    assert pc_control.execute({"action": "type_text", "text": "hello"}) == "Typed the text."
    assert pc_control.execute({"action": "press_key", "target": "enter"}) == "Pressed enter."
    assert pc_control.execute({"action": "hotkey", "target": "control l"}) == "Pressed ctrl+l."
    assert pc_control.execute({"action": "scroll", "target": "down 7"}) == "Scrolled down."
    assert fake.calls == [
        ("write", "hello", 0.01),
        ("press", "enter", 1),
        ("hotkey", ("ctrl", "l")),
        ("scroll", -7),
    ]


def test_volume_controls_use_media_keys(monkeypatch):
    fake = FakeGui()
    media_keys = []
    enable_desktop(monkeypatch)
    monkeypatch.setattr(pc_control, "pyautogui", fake)
    monkeypatch.setattr(pc_control, "_set_system_volume_windows", lambda percent: None)
    monkeypatch.setattr(pc_control, "_get_system_volume_windows", lambda: None)
    monkeypatch.setattr(pc_control, "_set_system_mute_windows", lambda muted: None)
    monkeypatch.setattr(pc_control, "_press_media_key", lambda key, presses=1: media_keys.append((key, presses)))

    assert pc_control.execute({"action": "set_volume", "target": "100"}) == "I sent volume-up keys, but I could not verify the exact volume."
    assert pc_control.execute({"action": "set_volume", "target": "30"}) == "I sent volume key presses, but I could not verify the exact volume."
    assert pc_control.execute({"action": "adjust_volume", "direction": "down", "presses": 3}) == "Volume decreased."
    assert pc_control.execute({"action": "mute_volume"}) == "I sent the mute key, but I could not verify the mute state."

    assert media_keys == [
        ("volumeup", 50),
        ("volumedown", 50),
        ("volumeup", 15),
        ("volumedown", 3),
        ("volumemute", 1),
    ]


def test_exact_volume_controls_use_core_audio_when_available(monkeypatch):
    calls = []
    monkeypatch.setattr(pc_control, "_set_system_volume_windows", lambda percent: calls.append(("set", percent)) or {"volume": percent, "muted": False})
    monkeypatch.setattr(pc_control, "_get_system_volume_windows", lambda: {"volume": 42, "muted": False})
    monkeypatch.setattr(pc_control, "_set_system_mute_windows", lambda muted: calls.append(("mute", muted)) or {"volume": 42, "muted": muted})

    assert pc_control.execute({"action": "set_volume", "target": "70"}) == "Volume set to 70%."
    assert pc_control.execute({"action": "get_volume"}) == "Current volume: 42%."
    assert pc_control.execute({"action": "adjust_volume", "direction": "down", "presses": 5}) == "Volume set to 32%."
    assert pc_control.execute({"action": "adjust_volume", "direction": "up", "step": 20}) == "Volume set to 62%."
    assert pc_control.execute({"action": "mute_volume", "target": "mute"}) == "Volume muted."
    assert pc_control.execute({"action": "mute_volume", "target": "unmute"}) == "Volume unmuted."
    assert calls == [("set", 70), ("set", 32), ("set", 62), ("mute", True), ("mute", False)]


def test_brightness_controls_use_wmi_when_available(monkeypatch):
    calls = []
    monkeypatch.setattr(pc_control, "_get_system_brightness_windows", lambda: {"brightness": 60, "displays": 1})
    monkeypatch.setattr(
        pc_control,
        "_set_system_brightness_windows",
        lambda percent: calls.append(percent) or {"brightness": percent, "displays": 1},
    )

    assert pc_control.execute({"action": "get_brightness"}) == "Current screen brightness: 60%."
    assert pc_control.execute({"action": "set_brightness", "target": "40"}) == "Screen brightness set to 40%."
    assert pc_control.execute({"action": "adjust_brightness", "direction": "down", "step": 15}) == "Screen brightness set to 45%."
    assert pc_control.execute({"action": "adjust_brightness", "direction": "up", "step": 20}) == "Screen brightness set to 80%."
    assert calls == [40, 45, 80]


def test_brightness_controls_report_unsupported_display(monkeypatch):
    monkeypatch.setattr(pc_control, "_get_system_brightness_windows", lambda: None)
    monkeypatch.setattr(pc_control, "_set_system_brightness_windows", lambda percent: None)

    assert pc_control.execute({"action": "get_brightness"}) == "I could not read screen brightness on this display."
    assert pc_control.execute({"action": "set_brightness", "target": "40"}) == "I could not set screen brightness on this display."
    assert pc_control.execute({"action": "adjust_brightness", "direction": "down"}) == "I could not read or adjust screen brightness on this display."


def test_media_key_falls_back_to_pyautogui(monkeypatch):
    fake = FakeGui()
    monkeypatch.setattr(pc_control, "pyautogui", fake)
    monkeypatch.setattr(pc_control, "_press_media_key_windows", lambda key, presses: False)

    pc_control._press_media_key("volumeup", presses=2)

    assert fake.calls == [("press", "volumeup", 2)]


def test_screenshot_saves_to_configured_folder(monkeypatch, tmp_path):
    fake = FakeGui()
    enable_desktop(monkeypatch, {"desktop_screenshot_dir": str(tmp_path)})
    monkeypatch.setattr(pc_control, "pyautogui", fake)

    result = pc_control.execute({"action": "screenshot"})

    assert result.startswith("Screenshot saved to")
    assert list(tmp_path.glob("screenshot_*.png"))


def test_focus_and_active_window(monkeypatch):
    fake = FakeGui()
    enable_desktop(monkeypatch)
    monkeypatch.setattr(pc_control, "pyautogui", fake)

    assert pc_control.execute({"action": "focus_window", "target": "Chrome"}) == "Focused Chrome."
    assert fake.window.restored is True
    assert fake.window.activated is True
    assert pc_control.execute({"action": "active_window"}).startswith("Active window: Chrome")


def test_inspect_screen_delegates_to_vision_module(monkeypatch):
    calls = []

    from core import desktop_vision

    monkeypatch.setattr(desktop_vision, "inspect_screen", lambda instruction, act=False: calls.append((instruction, act)) or "Screen inspected.")

    assert pc_control.execute({"action": "inspect_screen", "instruction": "find the button"}) == "Screen inspected."
    assert pc_control.execute({"action": "screen_step", "instruction": "click the button"}) == "Screen inspected."
    assert calls == [("find the button", False), ("click the button", True)]


def test_desktop_task_delegates_to_vision_loop(monkeypatch):
    calls = []

    from core import desktop_vision

    monkeypatch.setattr(desktop_vision, "run_desktop_task", lambda instruction, max_steps=None: calls.append((instruction, max_steps)) or "Desktop task completed.")

    assert pc_control.execute({"action": "desktop_task", "instruction": "fill the form", "max_steps": 4}) == "Desktop task completed."
    assert calls == [("fill the form", 4)]


def test_desktop_task_controls_delegate_to_vision_loop(monkeypatch):
    calls = []

    from core import desktop_vision

    monkeypatch.setattr(desktop_vision, "pause_desktop_task", lambda session_id=None: calls.append(("pause", session_id)) or "paused")
    monkeypatch.setattr(desktop_vision, "resume_desktop_task", lambda session_id=None: calls.append(("resume", session_id)) or "resumed")
    monkeypatch.setattr(desktop_vision, "confirm_desktop_task", lambda session_id=None: calls.append(("confirm", session_id)) or "confirmed")
    monkeypatch.setattr(desktop_vision, "cancel_desktop_task", lambda session_id=None: calls.append(("cancel", session_id)) or "cancelled")

    assert pc_control.execute({"action": "desktop_task_pause", "session_id": 4}) == "paused"
    assert pc_control.execute({"action": "desktop_task_resume", "target": "5"}) == "resumed"
    assert pc_control.execute({"action": "desktop_task_confirm"}) == "confirmed"
    assert pc_control.execute({"action": "desktop_task_cancel", "session_id": 6}) == "cancelled"
    assert calls == [("pause", 4), ("resume", 5), ("confirm", None), ("cancel", 6)]


def test_open_app_can_launch_chrome_debug(monkeypatch):
    calls = []
    monkeypatch.setattr(pc_control, "_apps", lambda: {"gmail": "https://mail.google.com/"})
    monkeypatch.setattr(pc_control, "config_value", lambda key, default=None: True if key == "browser_dom_launch_chrome_debug" else default)

    from core import browser_dom

    monkeypatch.setattr(browser_dom, "launch_debug_chrome", lambda url="": calls.append(url) or "Chrome debug mode opened at Gmail.")

    assert pc_control.execute({"action": "open_app", "target": "gmail"}) == "Chrome debug mode opened at Gmail."
    assert calls == ["https://mail.google.com/"]


def test_browser_and_accessibility_inspection(monkeypatch):
    from core import app_accessibility, browser_dom

    monkeypatch.setattr(browser_dom, "context_summary", lambda limit=40: {"available": True, "elements": [{"text": "Search"}]})
    monkeypatch.setattr(app_accessibility, "context_summary", lambda limit=40: {"available": True, "elements": [{"name": "OK"}]})

    assert '"Search"' in pc_control.execute({"action": "inspect_browser"})
    assert '"OK"' in pc_control.execute({"action": "inspect_accessibility"})


def test_visual_monitor_actions_delegate(monkeypatch):
    from core import visual_monitor

    calls = []
    monkeypatch.setattr(visual_monitor, "start_monitor", lambda source: calls.append(("start", source)) or {"running": True, "source": source, "event_count": 1})
    monkeypatch.setattr(visual_monitor, "stop_monitor", lambda: calls.append(("stop", "")) or {"running": False, "source": "screen", "event_count": 1})
    monkeypatch.setattr(visual_monitor, "status", lambda: calls.append(("status", "")) or {"running": True, "source": "screen", "event_count": 2})
    monkeypatch.setattr(
        visual_monitor,
        "capture_once",
        lambda source, analyze=None: calls.append(("capture", source, analyze)) or [{"summary": "Screen changed."}],
    )

    assert "source=camera" in pc_control.execute({"action": "visual_monitor_start", "source": "camera"})
    assert "running" in pc_control.execute({"action": "visual_monitor_status"})
    assert "Captured 1 visual frame" in pc_control.execute({"action": "visual_capture_once", "source": "screen", "analyze": True})
    assert "stopped" in pc_control.execute({"action": "visual_monitor_stop"})
    assert calls == [("start", "camera"), ("status", ""), ("capture", "screen", True), ("stop", "")]


def test_pc_control_honors_permission_block(monkeypatch, tmp_path):
    from core import permissions

    monkeypatch.setattr(permissions, "DB_PATH", tmp_path / "permissions.sqlite3")
    permissions.set_rule("pc_control.set_volume", "block")

    assert pc_control.execute({"action": "set_volume", "target": "50"}).startswith("Permission blocked")


def test_desktop_automation_requires_config(monkeypatch):
    fake = FakeGui()
    monkeypatch.setattr(pc_control, "config_value", lambda key, default=None: False if key == "pc_trusted_mode_enabled" else default)
    monkeypatch.setattr(pc_control, "pyautogui", fake)

    assert pc_control.execute({"action": "click"}) == "Desktop automation is disabled in config."


def test_mouse_coordinates_must_be_on_screen(monkeypatch):
    fake = FakeGui()
    enable_desktop(monkeypatch)
    monkeypatch.setattr(pc_control, "pyautogui", fake)

    assert "outside the screen size" in pc_control.execute({"action": "move_mouse", "x": 2000, "y": 10})
