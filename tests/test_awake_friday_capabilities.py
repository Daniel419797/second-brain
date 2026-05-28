from core import (
    android_companion,
    barge_in,
    daily_companion,
    event_nervous_system,
    model_router_brain,
    notification_center,
    personal_finance,
    private_embedding_memory,
    privacy_vault,
    project_watchdog,
    sandbox_simulation,
    self_debugger,
)


def _isolate(monkeypatch, tmp_path):
    modules = [
        android_companion,
        barge_in,
        daily_companion,
        event_nervous_system,
        model_router_brain,
        notification_center,
        personal_finance,
        private_embedding_memory,
        privacy_vault,
        project_watchdog,
        sandbox_simulation,
        self_debugger,
    ]
    for module in modules:
        monkeypatch.setattr(module, "DB_PATH", tmp_path / f"{module.__name__.split('.')[-1]}.sqlite3")
    monkeypatch.setattr(barge_in, "STOP_FLAG_PATH", tmp_path / "barge_in_stop.flag")


def test_event_nervous_system_emits_and_summarizes(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)

    event = event_nervous_system.emit_event("app_opened", "Chrome opened", "Chrome", severity=3, notify=True)
    summary = event_nervous_system.summary()

    assert event["event_type"] == "app_opened"
    assert summary["open_count"] == 1
    assert notification_center.summary()["unread_count"] == 1


def test_barge_in_sets_and_clears_interrupt(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)

    assert barge_in.handle_if_interrupt("Friday stop") == "Stopping."
    assert barge_in.is_requested() is True
    barge_in.clear()

    assert barge_in.is_requested() is False


def test_barge_in_queues_replacement_command(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)

    assert barge_in.handle_if_interrupt("No that's wrong reduce volume to 40") == "Stopping."
    queued = barge_in.pop_pending_command()

    assert queued is not None
    assert queued["command"] == "reduce volume to 40"
    assert barge_in.pop_pending_command() is None


def test_daily_companion_persists_brief(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)

    brief = daily_companion.morning_brief(notify=False)

    assert brief["kind"] == "morning"
    assert daily_companion.recent_briefs()[0]["id"] == brief["id"]


def test_personal_finance_tracks_budget_and_affordability(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)

    personal_finance.set_budget("food", 1000)
    personal_finance.add_expense(250, category="food", merchant="market")
    result = personal_finance.can_i_afford(500, category="food")

    assert result["ok"] is True
    assert result["remaining"] == 750


def test_private_memory_and_privacy_vault_are_searchable(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)

    private_embedding_memory.index_text("Rent note", "The rent receipt is in Downloads.", source="test")
    privacy_item = privacy_vault.store_item("credential_reference", "Hosting login", "do not store plaintext", tags=["hosting"])

    assert private_embedding_memory.search("rent receipt")[0]["title"] == "Rent note"
    assert privacy_vault.search("hosting")[0]["id"] == privacy_item["id"]
    assert privacy_item["content"] == "[not stored; hash only]"


def test_sandbox_model_router_and_self_debugger(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)

    simulation = sandbox_simulation.simulate_action("desktop", "send an email")
    route = model_router_brain.choose_provider("coding", "write python")
    report = self_debugger.record_failure("test", "STT timeout while listening")

    assert simulation["risk_level"] == "high"
    assert route["provider"]
    assert report["probable_cause"] == "timeout_or_latency"
