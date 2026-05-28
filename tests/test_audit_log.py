from core import audit_log


def test_audit_log_records_and_filters(monkeypatch, tmp_path):
    monkeypatch.setattr(audit_log, "DB_PATH", tmp_path / "audit.sqlite3")

    audit_log.record(category="pc_control", action="open_app", target="chrome", success=True)
    audit_log.record(category="web", action="open_url", target="https://example.com", success=True)

    all_events = audit_log.recent()
    pc_events = audit_log.recent(category="pc_control")

    assert len(all_events) == 2
    assert len(pc_events) == 1
    assert pc_events[0]["action"] == "open_app"
    assert pc_events[0]["success"] is True
