import pytest

from core import desktop_tasks, desktop_vision


@pytest.fixture(autouse=True)
def desktop_task_db(monkeypatch, tmp_path):
    monkeypatch.setattr(desktop_tasks, "DB_PATH", tmp_path / "desktop_tasks.sqlite3")
    monkeypatch.setattr(desktop_vision.browser_dom, "context_summary", lambda limit=None: {"available": False, "reason": "test"})
    monkeypatch.setattr(desktop_vision.app_accessibility, "context_summary", lambda limit=None: {"available": False, "reason": "test"})


def test_desktop_vision_uses_local_summary_without_api_key(monkeypatch, tmp_path):
    image = tmp_path / "screen.png"
    image.write_text("fake", encoding="utf-8")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setattr(desktop_vision, "_capture_screenshot", lambda: {"path": str(image)})
    monkeypatch.setattr(
        desktop_vision,
        "config_value",
        lambda key, default=None: "gemini" if key == "desktop_vision_provider" else "GEMINI_API_KEY" if key == "gemini_api_key_env" else default,
    )

    from tools import pc_control

    monkeypatch.setattr(pc_control, "execute", lambda inputs: "Active window: Chrome at 0, 0, size 800 by 600.")

    result = desktop_vision.inspect_screen("what is open")

    assert "Screenshot saved to" in result
    assert "Active window: Chrome" in result


def test_desktop_vision_executes_one_safe_action(monkeypatch):
    calls = []
    monkeypatch.setattr(desktop_vision, "config_value", lambda key, default=None: True if key == "desktop_vision_allow_actions" else default)

    from tools import pc_control

    monkeypatch.setattr(pc_control, "execute", lambda inputs: calls.append(inputs) or "Clicked at 10, 20.")

    result = desktop_vision._maybe_execute_action('The button is visible.\nACTION_JSON: {"action":"click","x":10,"y":20}', "click it")

    assert result == "Clicked at 10, 20."
    assert calls == [{"action": "click", "x": 10, "y": 20}]


def test_desktop_vision_blocks_unsafe_action(monkeypatch):
    monkeypatch.setattr(desktop_vision, "config_value", lambda key, default=None: True if key == "desktop_vision_allow_actions" else default)

    result = desktop_vision._maybe_execute_action('ACTION_JSON: {"action":"run_command","target":"format c:"}', "do it")

    assert "blocked" in result


def test_desktop_task_runs_until_complete(monkeypatch, tmp_path):
    image = tmp_path / "screen.png"
    image.write_text("fake", encoding="utf-8")
    plans = [
        {"status": "action", "progress": "Search box visible.", "action": {"action": "click", "x": 10, "y": 20}},
        {"status": "action", "progress": "Cursor is in the search box.", "action": {"action": "type_text", "text": "hello"}},
        {"status": "complete", "progress": "The text is visible.", "action": {}},
    ]
    actions = []
    monkeypatch.setattr(desktop_vision, "_capture_screenshot", lambda: {"path": str(image)})
    monkeypatch.setattr(desktop_vision, "_plan_desktop_step", lambda *args, **kwargs: plans.pop(0))
    monkeypatch.setattr(desktop_vision, "_execute_safe_action", lambda action: actions.append(action) or "ok")
    monkeypatch.setattr(
        desktop_vision,
        "config_value",
        lambda key, default=None: {
            "desktop_vision_allow_actions": True,
            "desktop_task_max_steps": 5,
            "desktop_task_no_progress_limit": 2,
            "desktop_task_step_delay_seconds": 0,
        }.get(key, default),
    )

    result = desktop_vision.run_desktop_task("search hello")

    assert result.startswith("Desktop task completed")
    assert actions == [{"action": "click", "x": 10, "y": 20}, {"action": "type_text", "text": "hello"}]


def test_desktop_task_stops_on_repeated_no_progress(monkeypatch, tmp_path):
    image = tmp_path / "screen.png"
    image.write_text("fake", encoding="utf-8")
    action = {"action": "click", "x": 10, "y": 20}
    monkeypatch.setattr(desktop_vision, "_capture_screenshot", lambda: {"path": str(image)})
    monkeypatch.setattr(
        desktop_vision,
        "_plan_desktop_step",
        lambda *args, **kwargs: {"status": "action", "progress": "Still on same dialog.", "action": action},
    )
    monkeypatch.setattr(desktop_vision, "_execute_safe_action", lambda _action: "Clicked.")
    monkeypatch.setattr(
        desktop_vision,
        "config_value",
        lambda key, default=None: {
            "desktop_vision_allow_actions": True,
            "desktop_task_max_steps": 5,
            "desktop_task_no_progress_limit": 1,
            "desktop_task_recovery_enabled": False,
            "desktop_task_step_delay_seconds": 0,
        }.get(key, default),
    )

    result = desktop_vision.run_desktop_task("close the dialog")

    assert "same action was repeating" in result


def test_desktop_task_blocks_without_vision_provider(monkeypatch, tmp_path):
    image = tmp_path / "screen.png"
    image.write_text("fake", encoding="utf-8")
    monkeypatch.setattr(desktop_vision, "_capture_screenshot", lambda: {"path": str(image)})
    monkeypatch.setattr(desktop_vision, "_ask_gemini_vision", lambda *args, **kwargs: "")
    monkeypatch.setattr(
        desktop_vision,
        "config_value",
        lambda key, default=None: {
            "desktop_vision_allow_actions": True,
            "desktop_task_max_steps": 5,
            "desktop_task_step_delay_seconds": 0,
        }.get(key, default),
    )

    result = desktop_vision.run_desktop_task("open the first result")

    assert "need a configured vision provider" in result.lower()


def test_desktop_task_waits_for_risky_confirmation(monkeypatch, tmp_path):
    image = tmp_path / "screen.png"
    image.write_text("fake", encoding="utf-8")
    action = {"action": "click", "x": 20, "y": 30}
    monkeypatch.setattr(desktop_vision, "_capture_screenshot", lambda: {"path": str(image)})
    monkeypatch.setattr(
        desktop_vision,
        "_plan_desktop_step",
        lambda *args, **kwargs: {"status": "action", "progress": "Send button is visible.", "reason": "Click Send.", "action": action},
    )
    monkeypatch.setattr(desktop_vision, "_execute_safe_action", lambda _action: "Clicked.")
    monkeypatch.setattr(
        desktop_vision,
        "config_value",
        lambda key, default=None: {
            "desktop_vision_allow_actions": True,
            "desktop_task_max_steps": 5,
            "desktop_task_step_delay_seconds": 0,
            "desktop_task_confirm_risky_actions": True,
        }.get(key, default),
    )

    result = desktop_vision.run_desktop_task("send the email")
    session = desktop_tasks.latest_session()

    assert "waiting for confirmation" in result.lower()
    assert session["status"] == "waiting_confirmation"
    assert session["pending_action"] == action


def test_desktop_task_confirm_executes_pending_action_and_continues(monkeypatch, tmp_path):
    image = tmp_path / "screen.png"
    image.write_text("fake", encoding="utf-8")
    actions = []
    session_id = desktop_tasks.create_session("send the email", max_steps=5)
    desktop_tasks.record_pending_confirmation(
        session_id,
        action={"action": "click", "x": 20, "y": 30},
        reason="Confirm before I run this risky desktop action: click.",
    )
    monkeypatch.setattr(desktop_vision, "_capture_screenshot", lambda: {"path": str(image)})
    monkeypatch.setattr(
        desktop_vision,
        "_plan_desktop_step",
        lambda *args, **kwargs: {"status": "complete", "progress": "The email was sent.", "action": {}},
    )
    monkeypatch.setattr(desktop_vision, "_execute_safe_action", lambda action: actions.append(action) or "Clicked.")
    monkeypatch.setattr(
        desktop_vision,
        "config_value",
        lambda key, default=None: {
            "desktop_vision_allow_actions": True,
            "desktop_task_step_delay_seconds": 0,
        }.get(key, default),
    )

    result = desktop_vision.confirm_desktop_task(session_id)

    assert result.startswith("Desktop task completed")
    assert actions == [{"action": "click", "x": 20, "y": 30}]
    assert desktop_tasks.get_session(session_id)["status"] == "completed"


def test_desktop_task_pause_and_resume(monkeypatch, tmp_path):
    image = tmp_path / "screen.png"
    image.write_text("fake", encoding="utf-8")
    session_id = desktop_tasks.create_session("open settings", max_steps=5)
    paused = desktop_vision.pause_desktop_task(session_id)
    monkeypatch.setattr(desktop_vision, "_capture_screenshot", lambda: {"path": str(image)})
    monkeypatch.setattr(
        desktop_vision,
        "_plan_desktop_step",
        lambda *args, **kwargs: {"status": "complete", "progress": "Settings is open.", "action": {}},
    )
    monkeypatch.setattr(
        desktop_vision,
        "config_value",
        lambda key, default=None: {
            "desktop_vision_allow_actions": True,
            "desktop_task_step_delay_seconds": 0,
        }.get(key, default),
    )

    resumed = desktop_vision.resume_desktop_task(session_id)

    assert "paused" in paused.lower()
    assert resumed.startswith("Desktop task completed")


def test_desktop_task_pauses_for_captcha_handoff(monkeypatch, tmp_path):
    image = tmp_path / "screen.png"
    image.write_text("fake", encoding="utf-8")
    monkeypatch.setattr(desktop_vision, "_capture_screenshot", lambda: {"path": str(image)})
    monkeypatch.setattr(desktop_vision.browser_dom, "context_summary", lambda limit=None: {"available": True, "detections": ["captcha"], "elements": []})
    monkeypatch.setattr(
        desktop_vision,
        "config_value",
        lambda key, default=None: {
            "desktop_vision_allow_actions": True,
            "desktop_task_max_steps": 5,
            "desktop_task_step_delay_seconds": 0,
            "browser_dom_enabled": True,
            "app_accessibility_enabled": False,
        }.get(key, default),
    )

    result = desktop_vision.run_desktop_task("open the account page")
    session = desktop_tasks.latest_session()

    assert "paused" in result.lower()
    assert "captcha" in result.lower()
    assert session["status"] == "paused"


def test_desktop_task_executes_browser_dom_action(monkeypatch, tmp_path):
    image = tmp_path / "screen.png"
    image.write_text("fake", encoding="utf-8")
    actions = []
    plans = [
        {"status": "action", "progress": "Search input is in DOM.", "action": {"action": "dom_type", "selector": "#q", "text": "hello"}},
        {"status": "complete", "progress": "Search term entered.", "action": {}},
    ]
    monkeypatch.setattr(desktop_vision, "_capture_screenshot", lambda: {"path": str(image)})
    monkeypatch.setattr(desktop_vision, "_plan_desktop_step", lambda *args, **kwargs: plans.pop(0))
    monkeypatch.setattr(desktop_vision.browser_dom, "execute_dom_action", lambda action: actions.append(action) or "Browser DOM typed the text.")
    monkeypatch.setattr(
        desktop_vision,
        "config_value",
        lambda key, default=None: {
            "desktop_vision_allow_actions": True,
            "desktop_task_max_steps": 5,
            "desktop_task_step_delay_seconds": 0,
        }.get(key, default),
    )

    result = desktop_vision.run_desktop_task("type hello in the search box")

    assert result.startswith("Desktop task completed")
    assert actions == [{"action": "dom_type", "selector": "#q", "text": "hello"}]


def test_desktop_task_auto_extends_when_progressing(monkeypatch, tmp_path):
    image = tmp_path / "screen.png"
    image.write_text("fake", encoding="utf-8")
    plans = [
        {"status": "action", "progress": "Step one progressed.", "action": {"action": "wait", "seconds": 0}},
        {"status": "complete", "progress": "Done after extension.", "action": {}},
    ]
    monkeypatch.setattr(desktop_vision, "_capture_screenshot", lambda: {"path": str(image)})
    monkeypatch.setattr(desktop_vision, "_plan_desktop_step", lambda *args, **kwargs: plans.pop(0))
    monkeypatch.setattr(desktop_vision, "_execute_safe_action", lambda action: "ok")
    monkeypatch.setattr(
        desktop_vision,
        "config_value",
        lambda key, default=None: {
            "desktop_vision_allow_actions": True,
            "desktop_task_max_steps": 1,
            "desktop_task_absolute_max_steps": 3,
            "desktop_task_auto_extend_steps": True,
            "desktop_task_extend_by_steps": 1,
            "desktop_task_step_delay_seconds": 0,
        }.get(key, default),
    )

    result = desktop_vision.run_desktop_task("wait for the page to settle")

    assert result.startswith("Desktop task completed")
