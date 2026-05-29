from core import autonomy_control, permissions


def isolate_permissions(monkeypatch, tmp_path):
    monkeypatch.setattr(permissions, "DB_PATH", tmp_path / "permissions.sqlite3")
    permissions.init_db()


def test_permission_defaults_and_updates(monkeypatch, tmp_path):
    isolate_permissions(monkeypatch, tmp_path)

    rules = permissions.list_rules()
    send_rule = permissions.get_rule("send_email.send_email")
    updated = permissions.set_rule("pc_control.set_volume", "block")

    assert any(rule["key"] == "pc_control.set_volume" for rule in rules)
    assert send_rule["mode"] == "ask"
    assert updated["mode"] == "block"
    assert permissions.evaluate("pc_control", {"action": "set_volume"})["blocked"] is True


def test_permission_named_policy_and_events(monkeypatch, tmp_path):
    isolate_permissions(monkeypatch, tmp_path)

    changed = permissions.set_named_policy("volume", "allow")
    decision = permissions.evaluate("pc_control", {"action": "adjust_volume", "target": "down"})
    event_id = permissions.record_decision("pc_control", {"action": "adjust_volume", "target": "down"}, decision="allowed")
    events = permissions.recent_events()

    assert len(changed) >= 3
    assert decision["mode"] == "allow"
    assert events[0]["id"] == event_id
    assert events[0]["decision"] == "allowed"


def test_permission_key_groups_mouse_and_desktop_actions(monkeypatch, tmp_path):
    isolate_permissions(monkeypatch, tmp_path)

    assert permissions.key_for_tool("pc_control", {"action": "click"}) == "pc_control.mouse_keyboard"
    assert permissions.key_for_tool("pc_control", {"action": "desktop_task"}) == "pc_control.desktop_task"


def test_full_autonomy_preapproves_trusted_project_work(monkeypatch, tmp_path):
    isolate_permissions(monkeypatch, tmp_path)
    monkeypatch.delenv("FRIDAY_AUTONOMY_MODE", raising=False)
    monkeypatch.delenv("FRIDAY_AUTONOMY_TRUSTED_ROOTS", raising=False)

    def fake_config(key, default=None):
        values = {
            "autonomy_control_enabled": True,
            "autonomy_mode": "full",
            "autonomy_trusted_roots": str(tmp_path),
            "autonomy_preapprove_local_project_work": True,
            "autonomy_hard_stop_keys": "",
        }
        return values.get(key, default)

    monkeypatch.setattr(autonomy_control, "config_value", fake_config)

    decision = permissions.evaluate("power_center", {"action": "task_autopilot", "root": str(tmp_path)})
    deploy = permissions.evaluate("power_center", {"action": "agency_project_workflow", "deploy": True, "root": str(tmp_path)})

    assert decision["allowed"] is True
    assert decision["requires_confirmation"] is False
    assert decision["autonomy_override"] is True
    assert deploy["allowed"] is True
    assert deploy["autonomy_override"] is True


def test_full_autonomy_does_not_preapprove_untrusted_scope(monkeypatch, tmp_path):
    isolate_permissions(monkeypatch, tmp_path)
    outside = tmp_path.parent / "outside"

    def fake_config(key, default=None):
        values = {
            "autonomy_control_enabled": True,
            "autonomy_mode": "full",
            "autonomy_trusted_roots": str(tmp_path),
            "autonomy_preapprove_local_project_work": True,
            "autonomy_hard_stop_keys": "",
        }
        return values.get(key, default)

    monkeypatch.setattr(autonomy_control, "config_value", fake_config)

    decision = permissions.evaluate("power_center", {"action": "task_autopilot", "root": str(outside)})

    assert decision["requires_confirmation"] is True
    assert "autonomy_override" not in decision


def test_full_autonomy_keeps_hard_stop_actions_ask_first(monkeypatch, tmp_path):
    isolate_permissions(monkeypatch, tmp_path)
    permissions.set_rule("send_email.send_email", "allow")

    def fake_config(key, default=None):
        values = {
            "autonomy_control_enabled": True,
            "autonomy_mode": "full",
            "autonomy_trusted_roots": str(tmp_path),
            "autonomy_hard_stop_keys": "send_email.send_email",
        }
        return values.get(key, default)

    monkeypatch.setattr(autonomy_control, "config_value", fake_config)

    decision = permissions.evaluate("send_email", {})

    assert decision["allowed"] is False
    assert decision["requires_confirmation"] is True
    assert decision["autonomy_hard_stop"] is True


def test_agency_outreach_approval_and_send_have_separate_permissions(monkeypatch, tmp_path):
    isolate_permissions(monkeypatch, tmp_path)
    monkeypatch.setattr(autonomy_control, "config_value", lambda key, default=None: False if key == "autonomy_control_enabled" else default)

    approve = permissions.evaluate("power_center", {"action": "agency_approve_outreach"})
    send = permissions.evaluate("power_center", {"action": "agency_send_outreach"})
    deploy = permissions.evaluate("power_center", {"action": "agency_project_workflow", "deploy": True})
    payment = permissions.evaluate("power_center", {"action": "agency_trigger_payment"})

    assert approve["allowed"] is True
    assert send["requires_confirmation"] is True
    assert deploy["requires_confirmation"] is True
    assert payment["requires_confirmation"] is True


def test_gateway_permissions_split_read_intake_config_and_stop(monkeypatch, tmp_path):
    isolate_permissions(monkeypatch, tmp_path)
    monkeypatch.setattr(autonomy_control, "config_value", lambda key, default=None: False if key == "autonomy_control_enabled" else default)

    read = permissions.evaluate("power_center", {"action": "gateway_status"})
    ingest = permissions.evaluate("power_center", {"action": "gateway_ingest_event"})
    config = permissions.evaluate("power_center", {"action": "gateway_configure_connector"})
    stop = permissions.evaluate("power_center", {"action": "gateway_emergency_stop"})

    assert read["allowed"] is True
    assert ingest["allowed"] is True
    assert config["requires_confirmation"] is True
    assert stop["allowed"] is True


def test_autonomous_agency_runtime_permissions(monkeypatch, tmp_path):
    isolate_permissions(monkeypatch, tmp_path)
    monkeypatch.setattr(autonomy_control, "config_value", lambda key, default=None: False if key == "autonomy_control_enabled" else default)

    benchmark = permissions.evaluate("power_center", {"action": "benchmark_run"})
    queue = permissions.evaluate("power_center", {"action": "connector_send"})
    dispatch = permissions.evaluate("power_center", {"action": "connector_dispatch"})
    company = permissions.evaluate("power_center", {"action": "company_handoff"})
    coding = permissions.evaluate("power_center", {"action": "production_coding_prepare"})
    memory = permissions.evaluate("power_center", {"action": "memory_governance_remember"})

    assert benchmark["allowed"] is True
    assert queue["allowed"] is True
    assert dispatch["requires_confirmation"] is True
    assert company["allowed"] is True
    assert coding["requires_confirmation"] is True
    assert memory["allowed"] is True
