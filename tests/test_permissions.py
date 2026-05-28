from core import permissions


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
