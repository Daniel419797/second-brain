import hashlib
import hmac
import json
import time

from core import approval_inbox, audit_log, connector_runtime, friday_gateway, notification_center, task_queue, trust_proof


def _isolate(monkeypatch, tmp_path):
    monkeypatch.setattr(connector_runtime, "DB_PATH", tmp_path / "connector_runtime.sqlite3")
    monkeypatch.setattr(friday_gateway, "DB_PATH", tmp_path / "friday_gateway.sqlite3")
    monkeypatch.setattr(approval_inbox, "DB_PATH", tmp_path / "approval.sqlite3")
    monkeypatch.setattr(notification_center, "DB_PATH", tmp_path / "notifications.sqlite3")
    monkeypatch.setattr(audit_log, "DB_PATH", tmp_path / "audit.sqlite3")
    monkeypatch.setattr(task_queue, "DB_PATH", tmp_path / "tasks.sqlite3")
    monkeypatch.setattr(trust_proof, "DB_PATH", tmp_path / "proof.sqlite3")

    def fake_config(key, default=None):
        values = {
            "friday_gateway_enabled": True,
            "friday_gateway_enabled_connectors": "web,desktop,telegram,slack",
            "connector_runtime_default_approval_required": True,
            "connector_default_daily_limit": 100,
            "connector_max_retry_attempts": 2,
            "gateway_auto_task_events": True,
        }
        return values.get(key, default)

    monkeypatch.setattr(connector_runtime, "config_value", fake_config)
    monkeypatch.setattr(friday_gateway, "config_value", fake_config)


def test_connector_outbox_requires_approval_then_dispatches(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
    calls = []

    def fake_post(url, payload, **kwargs):
        calls.append({"url": url, "payload": payload, "kwargs": kwargs})
        return {"ok": True, "status": 200, "summary": "sent"}

    monkeypatch.setattr(connector_runtime, "_post_json", fake_post)

    item = connector_runtime.queue_message("telegram", "123", "Hello", payload={"api_key": "secret"})

    assert item["status"] == "pending_approval"
    assert item["approval_id"] > 0
    assert item["payload"]["api_key"] == "[redacted]"

    queued = connector_runtime.approve_outbox(item["id"], note="ok")
    sent = connector_runtime.dispatch_outbox(item["id"])

    assert queued["status"] == "queued"
    assert sent["status"] == "sent"
    assert calls[0]["payload"]["chat_id"] == "123"


def test_connector_webhook_verifies_and_dedupes(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    monkeypatch.setenv("SLACK_SIGNING_SECRET", "whsec")
    friday_gateway.configure_connector("slack", enabled=True, trust_level="verified")
    body = json.dumps({"event": {"text": "Need a dashboard", "user": "U1"}}).encode("utf-8")
    timestamp = str(int(time.time()))
    base = b"v0:" + timestamp.encode("utf-8") + b":" + body
    signature = "v0=" + hmac.new(b"whsec", base, hashlib.sha256).hexdigest()
    headers = {"x-slack-request-timestamp": timestamp, "x-slack-signature": signature}

    first = connector_runtime.receive_webhook("slack", headers=headers, body=body)
    second = connector_runtime.receive_webhook("slack", headers=headers, body=body)

    assert first["ok"] is True
    assert first["processed"] is True
    assert second["deduped"] is True


def test_whatsapp_verification_challenge_is_not_routed(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    monkeypatch.setenv("WHATSAPP_VERIFY_TOKEN", "verify-me")
    friday_gateway.configure_connector("whatsapp", enabled=True, trust_level="verified")

    result = connector_runtime.receive_webhook(
        "whatsapp",
        query={"hub.mode": "subscribe", "hub.verify_token": "verify-me", "hub.challenge": "abc123"},
    )

    assert result["ok"] is True
    assert result["processed"] is False
    assert result["challenge"] == "abc123"
