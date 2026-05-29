from core import ad_campaigns, notification_center, trust_proof


def _isolate(monkeypatch, tmp_path):
    monkeypatch.setattr(ad_campaigns, "DB_PATH", tmp_path / "ad_campaigns.sqlite3")
    monkeypatch.setattr(notification_center, "DB_PATH", tmp_path / "notifications.sqlite3")
    monkeypatch.setattr(trust_proof, "DB_PATH", tmp_path / "proof.sqlite3")


def test_ad_campaign_draft_creates_variants(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)

    draft = ad_campaigns.draft("InvoicePilot", audience="small shop owners", offer="get paid faster")

    assert draft["status"] == "draft"
    assert draft["product"] == "InvoicePilot"
    assert len(draft["variants"]) == 3
    assert draft["variants"][0]["headline"]
    assert draft["variants"][0]["image_prompt"]


def test_ad_campaign_post_queues_approval_gated_connector_message(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    calls = []

    def fake_queue_message(connector, target, body, **kwargs):
        calls.append((connector, target, body, kwargs))
        return {"id": 42, "summary": "Connector outbox #42 pending approval.", "status": "pending_approval"}

    monkeypatch.setattr(ad_campaigns.connector_runtime, "queue_message", fake_queue_message)
    draft = ad_campaigns.draft("InvoicePilot", audience="small shop owners")

    queued = ad_campaigns.queue_post(draft["id"], connector="discord", target="channel-123")

    assert queued["status"] == "queued_for_approval"
    assert queued["outbox_id"] == 42
    assert calls[0][0] == "discord"
    assert calls[0][1] == "channel-123"
    assert calls[0][3]["action"] == "ad_post"
    assert calls[0][3]["require_approval"] is True
