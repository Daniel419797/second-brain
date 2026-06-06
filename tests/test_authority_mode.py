from core import autonomy_control, friday_tool_registry, permissions


def isolate_authority(monkeypatch, tmp_path):
    monkeypatch.setattr(permissions, "DB_PATH", tmp_path / "permissions.sqlite3")
    monkeypatch.setattr(autonomy_control, "DB_PATH", tmp_path / "autonomy_control.sqlite3")
    monkeypatch.delenv("FRIDAY_AUTHORITY_MODE", raising=False)
    monkeypatch.delenv("FRIDAY_AUTONOMY_MODE", raising=False)
    monkeypatch.delenv("FRIDAY_AUTONOMY_TRUSTED_ROOTS", raising=False)
    permissions.init_db()

    def fake_config(key, default=None):
        values = {
            "autonomy_control_enabled": True,
            "autonomy_mode": "supervised",
            "autonomy_trusted_roots": str(tmp_path),
            "autonomy_hard_stop_keys": "send_email.send_email",
        }
        return values.get(key, default)

    monkeypatch.setattr(autonomy_control, "config_value", fake_config)


def test_authority_mode_switches_ask_rules_to_full_access(monkeypatch, tmp_path):
    isolate_authority(monkeypatch, tmp_path)
    permissions.set_rule("power_center.git_push", "ask")

    gated = permissions.evaluate("power_center", {"action": "git_push", "root": str(tmp_path)})
    autonomy_control.set_authority_mode("full_access", actor="test")
    full = permissions.evaluate("power_center", {"action": "git_push", "root": str(tmp_path)})

    assert gated["requires_confirmation"] is True
    assert full["allowed"] is True
    assert full["requires_confirmation"] is False
    assert full["autonomy_override"] is True


def test_full_access_bypasses_hard_stop_ask_inside_trusted_scope(monkeypatch, tmp_path):
    isolate_authority(monkeypatch, tmp_path)
    permissions.set_rule("send_email.send_email", "ask")
    autonomy_control.set_authority_mode("full_access", actor="test")

    decision = permissions.evaluate("send_email", {"root": str(tmp_path)})

    assert decision["allowed"] is True
    assert decision["requires_confirmation"] is False
    assert decision["autonomy_hard_stop_bypassed"] is True


def test_full_access_does_not_bypass_block_rules(monkeypatch, tmp_path):
    isolate_authority(monkeypatch, tmp_path)
    permissions.set_rule("send_email.send_email", "block")
    autonomy_control.set_authority_mode("full_access", actor="test")

    decision = permissions.evaluate("send_email", {"root": str(tmp_path)})

    assert decision["blocked"] is True
    assert decision["allowed"] is False


def test_tool_registry_approval_gate_respects_full_access(monkeypatch, tmp_path):
    isolate_authority(monkeypatch, tmp_path)
    autonomy_control.set_authority_mode("full_access", actor="test")

    friday_tool_registry.register_tool(
        "test.full_access_tool",
        lambda args: {"ok": True, "summary": "ran"},
        description="Test approval bypass.",
        requires_approval=True,
    )

    result = friday_tool_registry.execute_tool("test.full_access_tool", {"root": str(tmp_path)})

    assert result["ok"] is True
    assert result["status"] == "done"
    assert result["authority_override"]["authority_mode"] == "full_access"
