from types import SimpleNamespace

from core import autobiographical_memory, memory, orchestrator


def _response(*blocks):
    return SimpleNamespace(content=list(blocks))


def _allow_permissions(monkeypatch):
    monkeypatch.setattr(
        orchestrator.permissions,
        "evaluate",
        lambda tool_name, tool_input: {
            "blocked": False,
            "requires_confirmation": False,
            "mode": "allow",
            "key": f"{tool_name}.test",
            "label": tool_name,
        },
    )
    monkeypatch.setattr(orchestrator.permissions, "record_decision", lambda *args, **kwargs: None)


def test_handle_command_dispatches_tool(monkeypatch):
    memory.wipe_all()
    calls = []
    first = _response(SimpleNamespace(type="tool_use", name="pc_control", input={"action": "open_app", "target": "chrome"}, id="1"))
    monkeypatch.setattr(orchestrator.llm, "ask", lambda *args, **kwargs: first)
    monkeypatch.setitem(orchestrator.TOOLS, "pc_control", lambda inputs: calls.append(inputs) or "Chrome opened successfully.")
    monkeypatch.setattr(orchestrator, "config_value", lambda key, default=None: False if key == "pc_trusted_mode_enabled" else default)

    assert orchestrator.handle_command("open calculator") == "Chrome opened successfully."
    assert calls == [{"action": "open_app", "target": "chrome"}]


def test_handle_command_text_response_skips_tools(monkeypatch):
    memory.wipe_all()
    captured = {}

    def fake_ask(*args, **kwargs):
        captured["tools"] = kwargs.get("tools")
        return _response(SimpleNamespace(type="text", text="4"))

    monkeypatch.setattr(orchestrator.llm, "ask", fake_ask)

    assert orchestrator.handle_command("what is 2+2") == "4"
    assert captured["tools"] == []


def test_transcription_artifact_does_not_reach_llm_or_tools(monkeypatch):
    memory.wipe_all()
    llm_calls = []
    tool_calls = []
    monkeypatch.setattr(orchestrator.llm, "ask", lambda *args, **kwargs: llm_calls.append(True))
    monkeypatch.setitem(orchestrator.TOOLS, "pc_control", lambda inputs: tool_calls.append(inputs) or "opened")

    reply = orchestrator.handle_command(
        "Audio is a short command for an AI assistant named Friday, Chrome, Gmail, VS Code, camera, file"
    )

    assert "ignored" in reply.lower()
    assert llm_calls == []
    assert tool_calls == []


def test_handle_command_includes_recent_conversation(monkeypatch):
    memory.wipe_all()
    memory.add_user("old question")
    memory.add_assistant("old answer")
    captured = {}

    def fake_ask(messages, *args, **kwargs):
        captured["messages"] = messages
        return _response(SimpleNamespace(type="text", text="Fresh answer."))

    monkeypatch.setattr(orchestrator.llm, "ask", fake_ask)

    assert orchestrator.handle_command("new question") == "Fresh answer."
    assert captured["messages"] == [
        {"role": "user", "content": "old question"},
        {"role": "assistant", "content": "old answer"},
        {"role": "user", "content": "new question"},
    ]


def test_handle_command_action_keeps_tools_available(monkeypatch):
    memory.wipe_all()
    captured = {}

    def fake_ask(*args, **kwargs):
        captured["tools"] = kwargs.get("tools")
        return _response(SimpleNamespace(type="text", text="Opening Chrome."))

    monkeypatch.setattr(orchestrator.llm, "ask", fake_ask)
    monkeypatch.setattr(orchestrator, "config_value", lambda key, default=None: False if key == "pc_trusted_mode_enabled" else default)

    assert orchestrator.handle_command("open calculator") == "Opening Chrome."
    assert captured["tools"] is None


def test_tool_exception_is_caught(monkeypatch):
    memory.wipe_all()
    monkeypatch.setattr(
        orchestrator.llm,
        "ask",
        lambda *args, **kwargs: _response(SimpleNamespace(type="tool_use", name="pc_control", input={}, id="1")),
    )
    monkeypatch.setitem(orchestrator.TOOLS, "pc_control", lambda inputs: (_ for _ in ()).throw(RuntimeError("bad")))
    monkeypatch.setattr(orchestrator, "config_value", lambda key, default=None: False if key == "pc_trusted_mode_enabled" else default)

    assert "problem" in orchestrator.handle_command("open calculator")


def test_llm_none_returns_fallback(monkeypatch):
    memory.wipe_all()
    monkeypatch.setattr(orchestrator.llm, "ask", lambda *args, **kwargs: None)

    assert "trouble connecting" in orchestrator.handle_command("tell me a poem")


def test_profile_name_is_stored_without_llm(monkeypatch):
    memory.wipe_all()
    called = []
    monkeypatch.setattr(orchestrator.llm, "ask", lambda *args, **kwargs: called.append(True))

    assert orchestrator.handle_command("my name is daniel") == "Nice to meet you, Daniel."
    assert called == []
    assert "user's name is Daniel" in memory.recall("name")


def test_direct_open_app_bypasses_llm(monkeypatch):
    memory.wipe_all()
    called = []
    monkeypatch.setattr(orchestrator.llm, "ask", lambda *args, **kwargs: called.append(True))
    monkeypatch.setattr(orchestrator.pc_control, "execute", lambda inputs: "Chrome opened successfully.")

    assert orchestrator.handle_command("open chrome") == "Chrome opened successfully."
    assert called == []


def test_direct_open_arbitrary_app_in_trusted_mode_bypasses_llm(monkeypatch):
    memory.wipe_all()
    called = []
    tool_inputs = []

    def fake_config(key, default=None):
        values = {
            "pc_trusted_mode_enabled": True,
            "pc_allow_arbitrary_apps": True,
        }
        return values.get(key, default)

    monkeypatch.setattr(orchestrator.llm, "ask", lambda *args, **kwargs: called.append(True))
    monkeypatch.setattr(orchestrator, "config_value", fake_config)
    monkeypatch.setattr(orchestrator.pc_control, "execute", lambda inputs: tool_inputs.append(inputs) or "Calculator opened successfully.")

    assert orchestrator.handle_command("open calculator") == "Calculator opened successfully."
    assert tool_inputs == [{"action": "open_app", "target": "calculator"}]
    assert called == []


def test_direct_open_path_bypasses_llm(monkeypatch):
    memory.wipe_all()
    called = []
    tool_inputs = []
    monkeypatch.setattr(orchestrator.llm, "ask", lambda *args, **kwargs: called.append(True))
    monkeypatch.setattr(orchestrator.pc_control, "execute", lambda inputs: tool_inputs.append(inputs) or "Opened Downloads.")

    assert orchestrator.handle_command("open downloads") == "Opened Downloads."
    assert tool_inputs[0]["action"] == "open_path"
    assert called == []


def test_direct_open_gmail_mishearing_bypasses_llm(monkeypatch):
    memory.wipe_all()
    called = []
    monkeypatch.setattr(orchestrator.llm, "ask", lambda *args, **kwargs: called.append(True))
    monkeypatch.setattr(orchestrator.pc_control, "execute", lambda inputs: "Gmail opened successfully.")

    assert orchestrator.handle_command("open gym") == "Gmail opened successfully."
    assert called == []


def test_direct_open_camera_bypasses_llm(monkeypatch):
    memory.wipe_all()
    called = []
    tool_inputs = []
    monkeypatch.setattr(orchestrator.llm, "ask", lambda *args, **kwargs: called.append(True))
    monkeypatch.setattr(orchestrator.pc_control, "execute", lambda inputs: tool_inputs.append(inputs) or "Camera opened successfully.")

    assert orchestrator.handle_command("open camera") == "Camera opened successfully."
    assert tool_inputs == [{"action": "open_app", "target": "camera"}]
    assert called == []


def test_direct_thanks_bypasses_llm(monkeypatch):
    memory.wipe_all()
    called = []
    monkeypatch.setattr(orchestrator.llm, "ask", lambda *args, **kwargs: called.append(True))
    monkeypatch.setattr(orchestrator, "config_value", lambda key, default=None: "friday,computer,jarvis" if key == "attention_names" else default)

    assert orchestrator.handle_command("Thank you Friday") == "You're welcome."
    assert called == []


def test_direct_time_bypasses_llm(monkeypatch):
    memory.wipe_all()
    called = []
    monkeypatch.setattr(orchestrator.llm, "ask", lambda *args, **kwargs: called.append(True))
    monkeypatch.setattr(orchestrator, "_format_time", lambda value: "11:21 PM")

    assert orchestrator.handle_command("can you tell me what the time is") == "It is 11:21 PM."
    assert called == []


def test_direct_what_are_you_doing_bypasses_llm_and_tools(monkeypatch):
    memory.wipe_all()
    llm_calls = []
    tool_calls = []
    monkeypatch.setattr(orchestrator.llm, "ask", lambda *args, **kwargs: llm_calls.append(True))
    monkeypatch.setitem(orchestrator.TOOLS, "pc_control", lambda inputs: tool_calls.append(inputs) or "Running pc_control.")

    reply = orchestrator.handle_command("what are you doing")

    assert "listening for your next command" in reply
    assert llm_calls == []
    assert tool_calls == []


def test_direct_what_are_you_working_on_bypasses_llm_and_tools(monkeypatch):
    memory.wipe_all()
    llm_calls = []
    tool_calls = []
    monkeypatch.setattr(orchestrator.llm, "ask", lambda *args, **kwargs: llm_calls.append(True))
    monkeypatch.setitem(orchestrator.TOOLS, "pc_control", lambda inputs: tool_calls.append(inputs) or "Running pc_control.")

    reply = orchestrator.handle_command("Friday what are you working on")

    assert "team status" in reply
    assert llm_calls == []
    assert tool_calls == []


def test_direct_list_functions_bypasses_llm_and_tools(monkeypatch):
    memory.wipe_all()
    llm_calls = []
    tool_calls = []
    monkeypatch.setattr(orchestrator.llm, "ask", lambda *args, **kwargs: llm_calls.append(True))
    monkeypatch.setitem(orchestrator.TOOLS, "pc_control", lambda inputs: tool_calls.append(inputs) or "Notepad opened.")

    reply = orchestrator.handle_command("list all the functions you have")

    assert "open apps" in reply
    assert "manage the background agent team" in reply
    assert llm_calls == []
    assert tool_calls == []


def test_direct_show_capabilities_bypasses_llm(monkeypatch):
    memory.wipe_all()
    llm_calls = []
    monkeypatch.setattr(orchestrator.llm, "ask", lambda *args, **kwargs: llm_calls.append(True))

    reply = orchestrator.handle_command("Friday show me your capabilities")

    assert "adjust volume" in reply
    assert llm_calls == []


def test_direct_list_your_capabilities_bypasses_llm(monkeypatch):
    memory.wipe_all()
    llm_calls = []
    monkeypatch.setattr(orchestrator.llm, "ask", lambda *args, **kwargs: llm_calls.append(True))

    reply = orchestrator.handle_command("list your capabilities")

    assert "open apps" in reply
    assert llm_calls == []


def test_direct_self_model_introspection_bypasses_llm(monkeypatch):
    memory.wipe_all()
    llm_calls = []
    monkeypatch.setattr(orchestrator.llm, "ask", lambda *args, **kwargs: llm_calls.append(True))
    monkeypatch.setattr(orchestrator.self_model, "tools_summary", lambda: "My tool groups are: pc_control, self_update.")
    monkeypatch.setattr(orchestrator.self_model, "uncertainty_summary", lambda: "I am unsure about: open expectations.")
    monkeypatch.setattr(orchestrator.self_model, "access_summary", lambda: "I can access safe local files.")
    monkeypatch.setattr(orchestrator.self_model, "failure_summary", lambda: "Recent failures: volume verification.")
    monkeypatch.setattr(orchestrator.self_model, "why_last_action_summary", lambda: "My latest notable event was tool_failure.")

    assert orchestrator.handle_command("what tools do you have") == "My tool groups are: pc_control, self_update."
    assert orchestrator.handle_command("what are you unsure about") == "I am unsure about: open expectations."
    assert orchestrator.handle_command("what can you currently access") == "I can access safe local files."
    assert orchestrator.handle_command("what failed recently") == "Recent failures: volume verification."
    assert orchestrator.handle_command("why did you say that") == "My latest notable event was tool_failure."
    assert llm_calls == []


def test_direct_autobiography_bypasses_llm(monkeypatch, tmp_path):
    memory.wipe_all()
    monkeypatch.setattr(autobiographical_memory, "DB_PATH", tmp_path / "auto.sqlite3")
    autobiographical_memory.record_event("user_correction", "Corrected volume", "Volume did not change.")
    monkeypatch.setattr(orchestrator.llm, "ask", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("LLM called")))

    reply = orchestrator.handle_command("show your autobiography")

    assert "Corrected volume" in reply


def test_direct_self_update_proposal_bypasses_llm(monkeypatch):
    memory.wipe_all()
    llm_calls = []
    tool_calls = []
    monkeypatch.setattr(orchestrator.llm, "ask", lambda *args, **kwargs: llm_calls.append(True))
    monkeypatch.setattr(orchestrator, "_self_update", lambda inputs: tool_calls.append(inputs) or "Self-update 1 proposed.")

    reply = orchestrator.handle_command("update your codebase to add safer retries")

    assert reply == "Self-update 1 proposed."
    assert tool_calls == [{"action": "propose", "request": "add safer retries"}]
    assert llm_calls == []


def test_direct_self_update_approval_marks_permission_confirmed(monkeypatch):
    memory.wipe_all()
    tool_calls = []
    monkeypatch.setattr(orchestrator.llm, "ask", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("LLM called")))
    monkeypatch.setattr(orchestrator, "_self_update", lambda inputs: tool_calls.append(inputs) or "Self-update 7 approved.")

    reply = orchestrator.handle_command("I authorize self update 7")

    assert reply == "Self-update 7 approved."
    assert tool_calls[0]["action"] == "approve"
    assert tool_calls[0]["update_id"] == "7"
    assert tool_calls[0]["_permission_confirmed"] is True


def test_direct_brain_explanation_bypasses_llm(monkeypatch):
    memory.wipe_all()
    llm_calls = []
    monkeypatch.setattr(orchestrator.llm, "ask", lambda *args, **kwargs: llm_calls.append(True))

    reply = orchestrator.handle_command("what is your brain like")

    assert "brain-inspired" in reply
    assert llm_calls == []


def test_direct_world_model_bypasses_llm(monkeypatch):
    memory.wipe_all()
    llm_calls = []
    monkeypatch.setattr(orchestrator.llm, "ask", lambda *args, **kwargs: llm_calls.append(True))
    monkeypatch.setattr(orchestrator.world_model, "current_context", lambda: {"summary": "Active window is Calculator."})

    reply = orchestrator.handle_command("what is going on right now")

    assert reply == "Active window is Calculator."
    assert llm_calls == []


def test_direct_attention_status_bypasses_llm(monkeypatch):
    memory.wipe_all()
    llm_calls = []
    monkeypatch.setattr(orchestrator.llm, "ask", lambda *args, **kwargs: llm_calls.append(True))
    monkeypatch.setattr(
        orchestrator.adaptive_attention,
        "current_profile",
        lambda: {"name_strictness": 0.7, "false_positive_rate": 0.1, "false_negative_rate": 0.2},
    )

    reply = orchestrator.handle_command("attention status")

    assert "0.70" in reply
    assert llm_calls == []


def test_direct_router_build_bypasses_llm(monkeypatch):
    memory.wipe_all()
    llm_calls = []
    monkeypatch.setattr(orchestrator.llm, "ask", lambda *args, **kwargs: llm_calls.append(True))

    reply = orchestrator.handle_command("what build are you running")

    assert orchestrator.ROUTER_BUILD in reply
    assert "orchestrator.py" in reply
    assert llm_calls == []


def test_direct_date_bypasses_llm(monkeypatch):
    memory.wipe_all()
    called = []
    monkeypatch.setattr(orchestrator.llm, "ask", lambda *args, **kwargs: called.append(True))
    monkeypatch.setattr(orchestrator, "_format_date", lambda value: "Friday, May 15, 2026")

    assert orchestrator.handle_command("Friday what is the date") == "Today is Friday, May 15, 2026."
    assert called == []


def test_direct_battery_percentage_bypasses_llm(monkeypatch):
    memory.wipe_all()
    called = []
    battery = SimpleNamespace(percent=87.4, power_plugged=True)
    monkeypatch.setattr(orchestrator.llm, "ask", lambda *args, **kwargs: called.append(True))
    monkeypatch.setattr(orchestrator, "psutil", SimpleNamespace(sensors_battery=lambda: battery))

    assert orchestrator.handle_command("check the percentage of my laptop") == "Battery is at 87% and charging."
    assert called == []


def test_direct_battery_percentage_handles_unavailable_sensor(monkeypatch):
    memory.wipe_all()
    called = []
    monkeypatch.setattr(orchestrator.llm, "ask", lambda *args, **kwargs: called.append(True))
    monkeypatch.setattr(orchestrator, "psutil", SimpleNamespace(sensors_battery=lambda: None))

    assert orchestrator.handle_command("what is my battery percentage") == "I cannot read the battery percentage on this PC."
    assert called == []


def test_direct_common_definition_bypasses_llm(monkeypatch):
    memory.wipe_all()
    called = []
    monkeypatch.setattr(orchestrator.llm, "ask", lambda *args, **kwargs: called.append(True))

    assert orchestrator.handle_command("what is an adjective") == "An adjective is a word that describes a noun, like blue, tall, or careful."
    assert called == []


def test_direct_ambiguous_file_question_asks_for_filename(monkeypatch):
    memory.wipe_all()
    called = []
    monkeypatch.setattr(orchestrator.llm, "ask", lambda *args, **kwargs: called.append(True))

    assert orchestrator.handle_command("what does the file say") == "Which file should I read?"
    assert called == []


def test_direct_workspace_visibility_does_not_bluff(monkeypatch):
    memory.wipe_all()
    called = []
    monkeypatch.setattr(orchestrator, "config_value", lambda key, default=None: False if key == "pc_trusted_mode_enabled" else default)
    monkeypatch.setattr(orchestrator.llm, "ask", lambda *args, **kwargs: called.append(True))

    assert (
        orchestrator.handle_command("can you see my workspace")
        == "I can access files in this project folder, but broad desktop access is disabled."
    )
    assert called == []


def test_direct_workspace_visibility_reflects_trusted_mode(monkeypatch):
    memory.wipe_all()
    called = []

    def fake_config(key, default=None):
        values = {
            "pc_trusted_mode_enabled": True,
            "pc_allow_arbitrary_paths": True,
        }
        return values.get(key, default)

    monkeypatch.setattr(orchestrator, "config_value", fake_config)
    monkeypatch.setattr(orchestrator.llm, "ask", lambda *args, **kwargs: called.append(True))

    assert (
        orchestrator.handle_command("can you see my workspace")
        == "I can access files and folders on this laptop, and I can control the visible desktop when you ask."
    )
    assert called == []


def test_direct_click_bypasses_llm(monkeypatch):
    memory.wipe_all()
    called = []
    tool_inputs = []
    monkeypatch.setattr(orchestrator.llm, "ask", lambda *args, **kwargs: called.append(True))
    monkeypatch.setattr(orchestrator.pc_control, "execute", lambda inputs: tool_inputs.append(inputs) or "Clicked at 100, 200.")

    assert orchestrator.handle_command("click at 100 200") == "Clicked at 100, 200."
    assert tool_inputs == [{"action": "click", "x": 100, "y": 200}]
    assert called == []


def test_direct_type_text_bypasses_llm(monkeypatch):
    memory.wipe_all()
    called = []
    tool_inputs = []
    monkeypatch.setattr(orchestrator.llm, "ask", lambda *args, **kwargs: called.append(True))
    monkeypatch.setattr(orchestrator.pc_control, "execute", lambda inputs: tool_inputs.append(inputs) or "Typed the text.")

    assert orchestrator.handle_command("type Hello Friday") == "Typed the text."
    assert tool_inputs == [{"action": "type_text", "text": "Hello Friday"}]
    assert called == []


def test_direct_press_hotkey_bypasses_llm(monkeypatch):
    memory.wipe_all()
    called = []
    tool_inputs = []
    monkeypatch.setattr(orchestrator.llm, "ask", lambda *args, **kwargs: called.append(True))
    monkeypatch.setattr(orchestrator.pc_control, "execute", lambda inputs: tool_inputs.append(inputs) or "Pressed ctrl+l.")

    assert orchestrator.handle_command("press control l") == "Pressed ctrl+l."
    assert tool_inputs == [{"action": "hotkey", "target": "control l"}]
    assert called == []


def test_direct_screenshot_bypasses_llm(monkeypatch):
    memory.wipe_all()
    called = []
    tool_inputs = []
    monkeypatch.setattr(orchestrator.llm, "ask", lambda *args, **kwargs: called.append(True))
    monkeypatch.setattr(orchestrator.pc_control, "execute", lambda inputs: tool_inputs.append(inputs) or "Screenshot saved.")

    assert orchestrator.handle_command("take a screenshot") == "Screenshot saved."
    assert tool_inputs == [{"action": "screenshot", "target": ""}]
    assert called == []


def test_direct_desktop_task_bypasses_llm(monkeypatch):
    memory.wipe_all()
    called = []
    tool_inputs = []
    monkeypatch.setattr(orchestrator.llm, "ask", lambda *args, **kwargs: called.append(True))
    monkeypatch.setattr(orchestrator.pc_control, "execute", lambda inputs: tool_inputs.append(inputs) or "Desktop task completed.")

    assert orchestrator.handle_command("use the desktop to open the first email") == "Desktop task completed."
    assert tool_inputs == [{"action": "desktop_task", "instruction": "open the first email"}]
    assert called == []


def test_direct_deep_app_integrations_bypass_llm(monkeypatch):
    memory.wipe_all()
    called = []
    tool_inputs = []
    monkeypatch.setattr(orchestrator.llm, "ask", lambda *args, **kwargs: called.append(True))
    monkeypatch.setattr(orchestrator.app_integrations, "execute", lambda inputs: tool_inputs.append(inputs) or "ok")

    assert orchestrator.handle_command("open calendar") == "ok"
    assert orchestrator.handle_command("add contact Ada email ada@example.com") == "ok"
    assert orchestrator.handle_command("remind me to call Ada tomorrow") == "ok"
    assert orchestrator.handle_command("search workspace for visual monitor") == "ok"

    assert tool_inputs == [
        {"action": "open_app", "target": "calendar"},
        {"action": "create_contact", "name": "Ada", "email": "ada@example.com", "phone": ""},
        {"action": "create_reminder", "title": "call Ada", "due_at": "tomorrow"},
        {"action": "search_workspace", "query": "visual monitor"},
    ]
    assert called == []


def test_direct_permission_settings_bypass_llm(monkeypatch, tmp_path):
    memory.wipe_all()
    called = []
    monkeypatch.setattr(orchestrator.permissions, "DB_PATH", tmp_path / "permissions.sqlite3")
    monkeypatch.setattr(orchestrator.llm, "ask", lambda *args, **kwargs: called.append(True))

    reply = orchestrator.handle_command("Friday may control volume")
    ask_reply = orchestrator.handle_command("must ask before deleting files or sending messages")

    assert "set to allow" in reply
    assert "set to ask" in ask_reply
    assert orchestrator.permissions.get_rule("send_email.send_email")["mode"] == "ask"
    assert called == []


def test_permission_policy_blocks_direct_tool(monkeypatch, tmp_path):
    memory.wipe_all()
    monkeypatch.setattr(orchestrator.permissions, "DB_PATH", tmp_path / "permissions.sqlite3")
    orchestrator.permissions.set_rule("pc_control.set_volume", "block")

    assert orchestrator.handle_command("set volume to 50%").startswith("Permission blocked")


def test_direct_desktop_task_controls_bypass_llm(monkeypatch):
    memory.wipe_all()
    called = []
    tool_inputs = []
    monkeypatch.setattr(orchestrator.llm, "ask", lambda *args, **kwargs: called.append(True))
    monkeypatch.setattr(orchestrator.pc_control, "execute", lambda inputs: tool_inputs.append(inputs) or "ok")

    assert orchestrator.handle_command("pause desktop task #4") == "ok"
    assert orchestrator.handle_command("resume desktop task 4") == "ok"
    assert orchestrator.handle_command("confirm desktop task 4") == "ok"
    assert orchestrator.handle_command("cancel desktop task 4") == "ok"
    assert tool_inputs == [
        {"action": "desktop_task_pause", "session_id": 4},
        {"action": "desktop_task_resume", "session_id": 4},
        {"action": "desktop_task_confirm", "session_id": 4},
        {"action": "desktop_task_cancel", "session_id": 4},
    ]
    assert called == []


def test_direct_focus_window_bypasses_llm(monkeypatch):
    memory.wipe_all()
    called = []
    tool_inputs = []
    monkeypatch.setattr(orchestrator.llm, "ask", lambda *args, **kwargs: called.append(True))
    monkeypatch.setattr(orchestrator.pc_control, "execute", lambda inputs: tool_inputs.append(inputs) or "Focused Chrome.")

    assert orchestrator.handle_command("focus Chrome window") == "Focused Chrome."
    assert tool_inputs == [{"action": "focus_window", "target": "Chrome"}]
    assert called == []


def test_direct_volume_to_max_bypasses_llm(monkeypatch):
    memory.wipe_all()
    called = []
    tool_inputs = []
    monkeypatch.setattr(orchestrator.llm, "ask", lambda *args, **kwargs: called.append(True))
    monkeypatch.setattr(orchestrator.pc_control, "execute", lambda inputs: tool_inputs.append(inputs) or "Volume set to 100%.")

    assert orchestrator.handle_command("increase my volume to the max") == "Volume set to 100%."
    assert tool_inputs == [{"action": "set_volume", "target": "100"}]
    assert called == []


def test_direct_pc_volume_to_max_bypasses_llm(monkeypatch):
    memory.wipe_all()
    called = []
    tool_inputs = []
    monkeypatch.setattr(orchestrator.llm, "ask", lambda *args, **kwargs: called.append(True))
    monkeypatch.setattr(orchestrator.pc_control, "execute", lambda inputs: tool_inputs.append(inputs) or "Volume set to 100%.")

    assert orchestrator.handle_command("increase PC volume to the max") == "Volume set to 100%."
    assert tool_inputs == [{"action": "set_volume", "target": "100"}]
    assert called == []


def test_direct_volume_adjust_bypasses_llm(monkeypatch):
    memory.wipe_all()
    called = []
    tool_inputs = []
    monkeypatch.setattr(orchestrator.llm, "ask", lambda *args, **kwargs: called.append(True))
    monkeypatch.setattr(orchestrator.pc_control, "execute", lambda inputs: tool_inputs.append(inputs) or "Volume decreased.")

    assert orchestrator.handle_command("turn the volume down") == "Volume decreased."
    assert orchestrator.handle_command("reduce my volume") == "Volume decreased."
    assert tool_inputs == [
        {"action": "adjust_volume", "direction": "down", "presses": 5},
        {"action": "adjust_volume", "direction": "down", "presses": 5},
    ]
    assert called == []


def test_direct_volume_percent_target_wins_over_direction(monkeypatch):
    memory.wipe_all()
    called = []
    tool_inputs = []
    monkeypatch.setattr(orchestrator.llm, "ask", lambda *args, **kwargs: called.append(True))
    monkeypatch.setattr(orchestrator.pc_control, "execute", lambda inputs: tool_inputs.append(inputs) or "Volume set to 40%.")

    assert orchestrator.handle_command("reduced my volume to 40%") == "Volume set to 40%."
    assert tool_inputs == [{"action": "set_volume", "target": "40"}]
    assert called == []


def test_unverified_volume_claim_is_repaired_with_real_tool(monkeypatch):
    tool_inputs = []
    monkeypatch.setattr(orchestrator.pc_control, "execute", lambda inputs: tool_inputs.append(inputs) or "Volume set to 90%.")

    reply = orchestrator._guard_unverified_pc_claim("reduced my volume", "Volume set to 30%.")

    assert reply == "Volume set to 90%."
    assert tool_inputs == [{"action": "adjust_volume", "direction": "down", "presses": 5}]


def test_direct_pc_volume_query_bypasses_llm(monkeypatch):
    memory.wipe_all()
    called = []
    tool_inputs = []
    monkeypatch.setattr(orchestrator.llm, "ask", lambda *args, **kwargs: called.append(True))
    monkeypatch.setattr(orchestrator.pc_control, "execute", lambda inputs: tool_inputs.append(inputs) or "Current volume: 42%.")

    assert orchestrator.handle_command("what is PC volume") == "Current volume: 42%."
    assert orchestrator.handle_command("meets PC volume") == "Current volume: 42%."
    assert tool_inputs == [{"action": "get_volume"}, {"action": "get_volume"}]
    assert called == []


def test_direct_mute_pc_volume_bypasses_llm(monkeypatch):
    memory.wipe_all()
    called = []
    tool_inputs = []
    monkeypatch.setattr(orchestrator.llm, "ask", lambda *args, **kwargs: called.append(True))
    monkeypatch.setattr(orchestrator.pc_control, "execute", lambda inputs: tool_inputs.append(inputs) or "Volume muted.")

    assert orchestrator.handle_command("mute PC volume") == "Volume muted."
    assert tool_inputs == [{"action": "mute_volume", "target": "mute"}]
    assert called == []


def test_direct_brightness_commands_bypass_llm(monkeypatch):
    memory.wipe_all()
    called = []
    tool_inputs = []
    monkeypatch.setattr(orchestrator.llm, "ask", lambda *args, **kwargs: called.append(True))
    monkeypatch.setattr(orchestrator.pc_control, "execute", lambda inputs: tool_inputs.append(inputs) or "Screen brightness set to 45%.")

    assert orchestrator.handle_command("reduced the brightness of my screen") == "Screen brightness set to 45%."
    assert orchestrator.handle_command("set screen brightness to 80") == "Screen brightness set to 45%."
    assert tool_inputs == [
        {"action": "adjust_brightness", "direction": "down"},
        {"action": "set_brightness", "target": "80"},
    ]
    assert called == []


def test_direct_brightness_percent_target_wins_over_direction(monkeypatch):
    memory.wipe_all()
    called = []
    tool_inputs = []
    monkeypatch.setattr(orchestrator.llm, "ask", lambda *args, **kwargs: called.append(True))
    monkeypatch.setattr(orchestrator.pc_control, "execute", lambda inputs: tool_inputs.append(inputs) or "Screen brightness set to 40%.")

    assert orchestrator.handle_command("reduce screen brightness to 40%") == "Screen brightness set to 40%."
    assert tool_inputs == [{"action": "set_brightness", "target": "40"}]
    assert called == []


def test_direct_open_editor_file_visibility_does_not_bluff(monkeypatch):
    memory.wipe_all()
    called = []
    monkeypatch.setattr(orchestrator.llm, "ask", lambda *args, **kwargs: called.append(True))

    assert (
        orchestrator.handle_command("can you see the file opened on my VS")
        == "I cannot see your open editor tab directly. Tell me the file name or path, and I can read it."
    )
    assert called == []


def test_direct_agent_team_status_bypasses_llm(monkeypatch):
    memory.wipe_all()
    called = []
    tool_inputs = []
    monkeypatch.setattr(orchestrator.llm, "ask", lambda *args, **kwargs: called.append(True))
    monkeypatch.setattr(orchestrator.agent_team, "execute", lambda inputs: tool_inputs.append(inputs) or "Agent workers are running.")

    assert orchestrator.handle_command("team status") == "Agent workers are running."
    assert tool_inputs == [{"action": "status"}]
    assert called == []


def test_direct_active_tasks_bypasses_llm(monkeypatch):
    memory.wipe_all()
    called = []
    tool_inputs = []
    monkeypatch.setattr(orchestrator.llm, "ask", lambda *args, **kwargs: called.append(True))
    monkeypatch.setattr(orchestrator.agent_team, "execute", lambda inputs: tool_inputs.append(inputs) or "#82 [active] senior_developer: Read docs")

    assert orchestrator.handle_command("what tasks are currently active") == "#82 [active] senior_developer: Read docs"
    assert tool_inputs == [{"action": "list_tasks", "status": "active", "limit": 8}]
    assert called == []


def test_direct_pending_task_question_bypasses_llm(monkeypatch):
    memory.wipe_all()
    called = []
    tool_inputs = []
    monkeypatch.setattr(orchestrator.llm, "ask", lambda *args, **kwargs: called.append(True))
    monkeypatch.setattr(orchestrator.agent_team, "execute", lambda inputs: tool_inputs.append(inputs) or "#12 [pending] research_analyst: Read docs")

    assert orchestrator.handle_command("do you have any pending task") == "#12 [pending] research_analyst: Read docs"
    assert tool_inputs == [{"action": "list_tasks", "status": "pending", "limit": 8}]
    assert called == []


def test_direct_reassign_task_bypasses_llm(monkeypatch):
    memory.wipe_all()
    called = []
    tool_inputs = []
    monkeypatch.setattr(orchestrator.llm, "ask", lambda *args, **kwargs: called.append(True))
    monkeypatch.setattr(orchestrator.agent_team, "execute", lambda inputs: tool_inputs.append(inputs) or "#82 [pending] research_analyst: Read docs")

    assert orchestrator.handle_command("assign task 82 to the research agent") == "#82 [pending] research_analyst: Read docs"
    assert tool_inputs == [{"action": "reassign_task", "task_id": "82", "agent_id": "research", "status": "pending"}]
    assert called == []


def test_direct_agent_questions_bypasses_llm(monkeypatch):
    memory.wipe_all()
    called = []
    tool_inputs = []
    monkeypatch.setattr(orchestrator.llm, "ask", lambda *args, **kwargs: called.append(True))
    monkeypatch.setattr(orchestrator.agent_team, "execute", lambda inputs: tool_inputs.append(inputs) or "No agent-to-agent questions are waiting right now.")

    assert orchestrator.handle_command("what are agents asking each other") == "No agent-to-agent questions are waiting right now."
    assert tool_inputs == [{"action": "list_questions", "limit": 8}]
    assert called == []


def test_direct_agent_team_create_task_bypasses_llm(monkeypatch):
    memory.wipe_all()
    called = []
    tool_inputs = []
    monkeypatch.setattr(orchestrator.llm, "ask", lambda *args, **kwargs: called.append(True))
    monkeypatch.setattr(orchestrator.agent_team, "execute", lambda inputs: tool_inputs.append(inputs) or "Task 1 queued.")

    assert orchestrator.handle_command("create task research free APIs") == "Task 1 queued."
    assert tool_inputs == [{"action": "create_task", "title": "research free APIs"}]
    assert called == []


def test_direct_remember_bypasses_llm(monkeypatch):
    memory.wipe_all()
    called = []
    monkeypatch.setattr(orchestrator.llm, "ask", lambda *args, **kwargs: called.append(True))

    assert orchestrator.handle_command("remember that my favorite IDE is VS Code") == "Remembered."
    assert called == []
    assert "my favorite IDE is VS Code" in memory.recall("favorite IDE")


def test_direct_draft_uses_short_llm_prompt(monkeypatch):
    memory.wipe_all()
    prompts = []
    monkeypatch.setattr(orchestrator.llm, "ask_simple", lambda prompt, retries=1: prompts.append(prompt) or "Running five minutes late.")

    assert orchestrator.handle_command("draft message to Sam saying I am running five minutes late") == "Running five minutes late."
    assert len(prompts) == 1
    assert "ready to send" in prompts[0]


def test_direct_coding_uses_coding_tool(monkeypatch):
    memory.wipe_all()
    calls = []
    monkeypatch.setattr(orchestrator.coding_tool, "execute", lambda inputs: calls.append(inputs) or "Use pathlib.")

    assert orchestrator.handle_command("write code to list files in Python") == "Use pathlib."
    assert calls == [{"action": "qa", "question": "write code to list files in Python"}]


def test_direct_build_uses_configured_coding_root(monkeypatch, tmp_path):
    memory.wipe_all()
    _allow_permissions(monkeypatch)
    calls = []
    monkeypatch.setattr(orchestrator.llm, "ask", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("LLM called")))
    monkeypatch.setattr(orchestrator.intent_engine, "resolve_coding_root", lambda root="": tmp_path)
    monkeypatch.setattr(orchestrator.power_center, "execute", lambda inputs: calls.append(inputs) or "Coding task queued.")

    assert orchestrator.handle_command("build me a dashboard app for invoices") == "Coding task queued."
    assert calls == [
        {
            "action": "autonomous_coding",
            "request": "a dashboard app for invoices",
            "root": str(tmp_path),
            "risk_level": "medium",
        }
    ]


def test_intent_router_handles_semantic_build_request(monkeypatch, tmp_path):
    memory.wipe_all()
    _allow_permissions(monkeypatch)
    calls = []
    monkeypatch.setattr(orchestrator.intent_engine, "_RULE_CLASSIFIERS", ())
    monkeypatch.setattr(orchestrator.intent_engine, "resolve_coding_root", lambda root="": tmp_path)
    monkeypatch.setattr(
        orchestrator.intent_engine.llm,
        "ask_simple",
        lambda prompt, retries=1: '{"intent":"start_coding_project","confidence":0.91,"slots":{"request":"invoice portal for my shop"},"reason":"software build request"}',
    )
    monkeypatch.setattr(orchestrator.llm, "ask", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("generic LLM should not run")))
    monkeypatch.setattr(orchestrator.power_center, "execute", lambda inputs: calls.append(inputs) or "Coding task queued.")

    assert orchestrator.handle_command("I need something that can manage invoices for my shop") == "Coding task queued."
    assert calls == [
        {
            "action": "autonomous_coding",
            "request": "invoice portal for my shop",
            "root": str(tmp_path),
            "risk_level": "medium",
        }
    ]


def test_intent_router_delegates_agent_task_without_llm(monkeypatch):
    memory.wipe_all()
    _allow_permissions(monkeypatch)
    calls = []
    monkeypatch.setattr(orchestrator.llm, "ask", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("LLM called")))
    monkeypatch.setattr(orchestrator.agent_team, "execute", lambda inputs: calls.append(inputs) or "Task queued.")

    assert orchestrator.handle_command("get the research agent to compare OCR libraries") == "Task queued."
    assert calls == [{"action": "create_task", "title": "compare OCR libraries", "agent_id": "research_analyst"}]


def test_intent_router_routes_academic_project_with_exports(monkeypatch):
    memory.wipe_all()
    _allow_permissions(monkeypatch)
    calls = []
    monkeypatch.setattr(orchestrator.llm, "ask", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("LLM called")))
    monkeypatch.setattr(orchestrator.power_center, "execute", lambda inputs: calls.append(inputs) or "Academic final year project draft ready. DOCX: project.docx. PDF: project.pdf.")

    reply = orchestrator.handle_command("write a final year project on blockchain based voting system")

    assert reply.startswith("Academic final year project draft ready")
    assert calls == [
        {
            "action": "academic_project",
            "topic": "blockchain based voting system",
            "kind": "final_year_project",
            "citation_style": "APA",
            "formats": ["md", "docx", "pdf"],
        }
    ]


def test_intent_router_routes_git_status_without_llm(monkeypatch):
    memory.wipe_all()
    _allow_permissions(monkeypatch)
    calls = []
    monkeypatch.setattr(orchestrator.llm, "ask", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("LLM called")))
    monkeypatch.setattr(orchestrator.power_center, "execute", lambda inputs: calls.append(inputs) or "Git status ready.\n## main")

    assert orchestrator.handle_command("git status").startswith("Git status ready.")
    assert calls == [{"action": "git_status"}]


def test_intent_router_routes_3d_model_without_coding_project(monkeypatch):
    memory.wipe_all()
    _allow_permissions(monkeypatch)
    calls = []
    monkeypatch.setattr(orchestrator.llm, "ask", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("LLM called")))
    monkeypatch.setattr(orchestrator.power_center, "execute", lambda inputs: calls.append(inputs) or "3D model created as spaceship. GLB: model.glb")

    assert orchestrator.handle_command("build a 3d model of a spaceship as glb").startswith("3D model created")
    assert calls == [{"action": "model3d_create", "prompt": "a spaceship", "formats": ["glb"]}]


def test_direct_image_generation_does_not_open_paint(monkeypatch):
    memory.wipe_all()
    image_inputs = []
    pc_inputs = []
    monkeypatch.setattr(orchestrator.llm, "ask", lambda *args, **kwargs: None)
    monkeypatch.setattr(orchestrator.image_generation_tool, "execute", lambda inputs: image_inputs.append(inputs) or "Image generation unavailable: configure a provider.")
    monkeypatch.setattr(orchestrator, "_pc", lambda inputs: pc_inputs.append(inputs) or "Paint opened successfully.")

    assert orchestrator.handle_command("generate an image of a cat") == "Image generation unavailable: configure a provider."
    assert image_inputs == [{"action": "generate", "prompt": "a cat"}]
    assert pc_inputs == []


def test_logo_generation_uses_image_generation(monkeypatch):
    memory.wipe_all()
    image_inputs = []
    pc_inputs = []
    monkeypatch.setattr(orchestrator.llm, "ask", lambda *args, **kwargs: None)
    monkeypatch.setattr(orchestrator.image_generation_tool, "execute", lambda inputs: image_inputs.append(inputs) or "Image generated: logo.png")
    monkeypatch.setattr(orchestrator, "_pc", lambda inputs: pc_inputs.append(inputs) or "Adobe Illustrator opened.")

    assert orchestrator.handle_command("generate a logo for a printing business, name Print Kulture") == "Image generated: logo.png"
    assert image_inputs == [{"action": "generate", "prompt": "a logo for a printing business, name Print Kulture"}]
    assert pc_inputs == []


def test_logo_reference_image_generation_uses_image_generation(monkeypatch):
    memory.wipe_all()
    image_inputs = []
    pc_inputs = []
    monkeypatch.setattr(orchestrator.llm, "ask", lambda *args, **kwargs: None)
    monkeypatch.setattr(orchestrator.image_generation_tool, "execute", lambda inputs: image_inputs.append(inputs) or "Image generated: logo-reference.png")
    monkeypatch.setattr(orchestrator, "_pc", lambda inputs: pc_inputs.append(inputs) or "Adobe Illustrator opened.")

    assert orchestrator.handle_command("generate an image i can use for a logo for a brand name Print Kulture") == "Image generated: logo-reference.png"
    assert image_inputs == [{"action": "generate", "prompt": "a logo for a brand name Print Kulture"}]
    assert pc_inputs == []


def test_destructive_action_can_be_cancelled(monkeypatch):
    memory.wipe_all()
    orchestrator._clear_pending_confirmation()
    called = []
    monkeypatch.setattr(
        orchestrator.llm,
        "ask",
        lambda *args, **kwargs: _response(SimpleNamespace(type="tool_use", name="send_email", input={}, id="1")),
    )
    monkeypatch.setitem(orchestrator.TOOLS, "send_email", lambda inputs: called.append(inputs) or "sent")

    reply = orchestrator.handle_command("send email")

    assert reply.startswith("Are you sure you want to run")
    assert orchestrator.handle_command("no") == "Action cancelled."
    assert called == []


def test_pc_shell_command_requires_confirmation(monkeypatch):
    memory.wipe_all()
    orchestrator._clear_pending_confirmation()
    called = []
    block = SimpleNamespace(type="tool_use", name="pc_control", input={"action": "run_command", "target": "Get-Date"}, id="1")
    monkeypatch.setattr(orchestrator.llm, "ask", lambda *args, **kwargs: _response(block))
    monkeypatch.setitem(orchestrator.TOOLS, "pc_control", lambda inputs: called.append(inputs) or "ran")

    reply = orchestrator.handle_command("run command get date")

    assert reply.startswith("Are you sure you want to run")
    assert orchestrator.handle_command("no") == "Action cancelled."
    assert called == []


def test_direct_phone_ring_bypasses_llm(monkeypatch):
    memory.wipe_all()
    called = []
    phone_inputs = []
    monkeypatch.setattr(orchestrator.llm, "ask", lambda *args, **kwargs: called.append(True))
    monkeypatch.setattr(orchestrator, "_phone", lambda inputs: phone_inputs.append(inputs) or "Phone ring alert sent.")

    assert orchestrator.handle_command("ring my phone") == "Phone ring alert sent."
    assert phone_inputs == [{"action": "ring", "message": "Friday is trying to reach you."}]
    assert called == []


def test_direct_phone_open_url_bypasses_llm(monkeypatch):
    memory.wipe_all()
    called = []
    phone_inputs = []
    monkeypatch.setattr(orchestrator.llm, "ask", lambda *args, **kwargs: called.append(True))
    monkeypatch.setattr(orchestrator, "_phone", lambda inputs: phone_inputs.append(inputs) or "Opened URL on Android phone.")

    assert orchestrator.handle_command("open example.com on my phone") == "Opened URL on Android phone."
    assert phone_inputs == [{"action": "open_url", "url": "example.com"}]
    assert called == []


def test_direct_phone_battery_bypasses_llm(monkeypatch):
    memory.wipe_all()
    called = []
    phone_inputs = []
    monkeypatch.setattr(orchestrator.llm, "ask", lambda *args, **kwargs: called.append(True))
    monkeypatch.setattr(orchestrator, "_phone", lambda inputs: phone_inputs.append(inputs) or "Phone battery is 87%.")

    assert orchestrator.handle_command("what is my phone battery") == "Phone battery is 87%."
    assert phone_inputs == [{"action": "battery"}]
    assert called == []


def test_direct_capability_daily_brief_bypasses_llm(monkeypatch):
    memory.wipe_all()
    called = []
    inputs = []
    monkeypatch.setattr(orchestrator.llm, "ask", lambda *args, **kwargs: called.append(True))
    monkeypatch.setattr(orchestrator, "_capability", lambda payload: inputs.append(payload) or "You have one reminder.")

    assert orchestrator.handle_command("daily brief") == "You have one reminder."
    assert inputs == [{"action": "daily_brief"}]
    assert called == []


def test_direct_hack_request_stays_scope_locked(monkeypatch):
    memory.wipe_all()
    called = []
    monkeypatch.setattr(orchestrator.llm, "ask", lambda *args, **kwargs: called.append(True))

    reply = orchestrator.handle_command("hack example.com")

    assert "verify ownership" in reply
    assert called == []
