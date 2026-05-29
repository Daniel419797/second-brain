"""Provider connector runtime with approval-gated outbox and webhook intake."""

from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import json
import os
import sqlite3
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from core import approval_inbox, audit_log, friday_gateway, notification_center, trust_proof
from core.config import DATA_DIR, config_value, ensure_runtime_dirs

DB_PATH = DATA_DIR / "connector_runtime.sqlite3"
_LOCK = threading.Lock()
SECRET_KEYS = ("token", "secret", "password", "authorization", "cookie", "api_key", "access_token")


def init_db(path: Path | None = None) -> None:
    ensure_runtime_dirs()
    db_path = path or DB_PATH
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path, timeout=10) as conn:
        try:
            conn.execute("PRAGMA journal_mode=WAL")
        except sqlite3.OperationalError:
            pass
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS connector_outbox (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                connector TEXT NOT NULL,
                target TEXT NOT NULL,
                action TEXT NOT NULL,
                subject TEXT NOT NULL,
                body TEXT NOT NULL,
                status TEXT NOT NULL,
                approval_id INTEGER,
                attempts INTEGER NOT NULL,
                next_attempt_at TEXT NOT NULL,
                last_error TEXT NOT NULL,
                dedupe_key TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                result_json TEXT NOT NULL
            )
            """
        )
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_connector_outbox_dedupe ON connector_outbox(dedupe_key)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_connector_outbox_status ON connector_outbox(status, next_attempt_at)")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS connector_webhook_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                connector TEXT NOT NULL,
                external_id TEXT NOT NULL,
                signature_ok INTEGER NOT NULL,
                processed INTEGER NOT NULL,
                event_id INTEGER,
                payload_json TEXT NOT NULL
            )
            """
        )
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_connector_webhook_dedupe ON connector_webhook_events(connector, external_id)")


def status() -> dict[str, Any]:
    outbox = list_outbox(limit=12)
    counts = _counts("connector_outbox", "status")
    webhook_counts = _counts("connector_webhook_events", "connector")
    return {
        "outbox_counts": counts,
        "webhook_counts": webhook_counts,
        "ready_adapters": ready_adapters(),
        "recent_outbox": outbox,
        "summary": f"Connector runtime has {counts.get('queued', 0)} queued item(s), {counts.get('pending_approval', 0)} approval item(s), and {counts.get('retry', 0)} retry item(s).",
    }


def ready_adapters() -> list[dict[str, Any]]:
    rows = []
    for connector in friday_gateway.connector_status():
        key = str(connector["key"])
        rows.append(
            {
                "key": key,
                "configured": bool(connector["configured"]),
                "enabled": bool(connector["enabled"]),
                "can_send": key in _ADAPTERS,
                "webhook_verification": key in _WEBHOOK_VERIFIERS,
                "required_env": connector.get("required_env") or [],
                "risk": connector.get("risk"),
            }
        )
    return rows


def queue_message(
    connector: str,
    target: str,
    body: str,
    *,
    subject: str = "",
    action: str = "message",
    payload: dict[str, Any] | None = None,
    require_approval: bool | None = None,
) -> dict[str, Any]:
    init_db()
    key = _connector(connector)
    if key not in friday_gateway.CONNECTORS:
        raise ValueError("unknown connector")
    target = _clean(target)[:1000]
    if not target:
        raise ValueError("target is required")
    body = str(body or "").strip()
    if not body and action == "message":
        raise ValueError("body is required")
    metadata = _redact(payload or {})
    approval_required = _approval_required(key, action) if require_approval is None else bool(require_approval)
    now = _now()
    dedupe = _dedupe_key(key, target, action, subject, body, metadata)
    approval_id = None
    outbox_status = "pending_approval" if approval_required else "queued"
    if approval_required:
        approval = approval_inbox.create(
            kind="connector_outbound",
            title=f"Approve {key} {action}",
            summary=f"Target: {target}. Subject: {subject or action}. Body: {body[:500]}",
            source="connector_runtime",
            payload={"connector": key, "target": target, "action": action, "subject": subject, "body": body[:2000], "payload": metadata},
        )
        approval_id = int(approval.get("id") or 0) or None
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        try:
            cursor = conn.execute(
                """
                INSERT INTO connector_outbox(created_at, updated_at, connector, target, action, subject, body, status, approval_id, attempts, next_attempt_at, last_error, dedupe_key, payload_json, result_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, '', ?, ?, '{}')
                """,
                (now, now, key, target, _connector(action), _clean(subject)[:500], body[:12000], outbox_status, approval_id, now, dedupe, _json_dumps(metadata)),
            )
            row = conn.execute("SELECT * FROM connector_outbox WHERE id=?", (int(cursor.lastrowid),)).fetchone()
        except sqlite3.IntegrityError:
            row = conn.execute("SELECT * FROM connector_outbox WHERE dedupe_key=?", (dedupe,)).fetchone()
    item = _outbox_row(row)
    notification_center.add(source="connector_runtime", category="connector", severity=3 if approval_required else 1, title=f"Connector {key} queued", message=item["summary"], metadata={"outbox_id": item["id"]})
    audit_log.record(category="connector_runtime", action="queue_message", target=f"{key}:{target}", success=True, details={"outbox_id": item["id"], "status": item["status"]})
    return item


def approve_outbox(outbox_id: int, *, note: str = "", dispatch: bool = False) -> dict[str, Any]:
    item = get_outbox(outbox_id)
    if not item:
        raise ValueError("outbox item not found")
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.execute("UPDATE connector_outbox SET status='queued', updated_at=?, next_attempt_at=? WHERE id=?", (_now(), _now(), int(outbox_id)))
    if item.get("approval_id"):
        try:
            approval_inbox.resolve("connector_outbound", int(item["approval_id"]), note=note or "Approved for connector dispatch.")
        except Exception:
            pass
    updated = get_outbox(outbox_id) or item
    return dispatch_outbox(outbox_id, approved=True) if dispatch else updated | {"summary": f"Connector outbox #{outbox_id} approved and queued."}


def dispatch_outbox(outbox_id: int, *, approved: bool = False) -> dict[str, Any]:
    item = get_outbox(outbox_id)
    if not item:
        raise ValueError("outbox item not found")
    if item["status"] == "pending_approval" and not approved:
        return item | {"ok": False, "summary": "Connector outbox item is waiting for approval."}
    if item["connector"] not in _ADAPTERS:
        return _mark_failed(item, "No outbound adapter is implemented for this connector.", retry=False)
    limited = _rate_limit_message(item["connector"])
    if limited:
        return _mark_failed(item, limited, retry=True)
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.execute("UPDATE connector_outbox SET status='sending', attempts=attempts + 1, updated_at=? WHERE id=?", (_now(), int(outbox_id)))
    started = time.perf_counter()
    try:
        result = _ADAPTERS[item["connector"]](item)
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        return _mark_sent(item, result | {"latency_ms": elapsed_ms})
    except Exception as exc:
        return _mark_failed(item, str(exc), retry=item["attempts"] < _max_attempts())


def retry_due(limit: int = 10) -> dict[str, Any]:
    init_db()
    now = _now()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM connector_outbox WHERE status='retry' AND (next_attempt_at='' OR next_attempt_at<=?) ORDER BY id LIMIT ?",
            (now, max(1, min(50, int(limit or 10)))),
        ).fetchall()
    results = [dispatch_outbox(int(row["id"])) for row in rows]
    return {"processed": len(results), "results": results, "summary": f"Retried {len(results)} connector outbox item(s)."}


def list_outbox(limit: int = 50, status: str = "", connector: str = "") -> list[dict[str, Any]]:
    init_db()
    where: list[str] = []
    params: list[Any] = []
    if status:
        where.append("status=?")
        params.append(_connector(status))
    if connector:
        where.append("connector=?")
        params.append(_connector(connector))
    params.append(max(1, min(200, int(limit or 50))))
    clause = "WHERE " + " AND ".join(where) if where else ""
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(f"SELECT * FROM connector_outbox {clause} ORDER BY id DESC LIMIT ?", params).fetchall()
    return [_outbox_row(row) for row in rows]


def get_outbox(outbox_id: int) -> dict[str, Any] | None:
    init_db()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM connector_outbox WHERE id=?", (int(outbox_id),)).fetchone()
    return _outbox_row(row) if row else None


def receive_webhook(connector: str, *, headers: dict[str, Any] | None = None, body: bytes | str = b"", query: dict[str, Any] | None = None) -> dict[str, Any]:
    init_db()
    key = _connector(connector)
    if key not in friday_gateway.CONNECTORS:
        raise ValueError("unknown connector")
    raw = body if isinstance(body, bytes) else str(body or "").encode("utf-8")
    header_map = {str(k).lower(): str(v) for k, v in (headers or {}).items()}
    query_map = {str(k): str(v) for k, v in (query or {}).items()}
    verified = verify_webhook(key, header_map, raw, query_map)
    if not verified["ok"]:
        _record_webhook(key, verified.get("external_id") or _hash(raw), False, False, 0, {"error": verified.get("summary"), "query": query_map})
        audit_log.record(category="connector_runtime", action="webhook_rejected", target=key, success=False, details=verified)
        return verified | {"processed": False}
    if "challenge" in verified:
        _record_webhook(key, verified.get("external_id") or "verification", True, False, 0, {"query": query_map, "challenge": "[provider_verification]"})
        audit_log.record(category="connector_runtime", action="webhook_verified", target=key, success=True, details={"verification": True})
        return verified | {"processed": False}
    payload = _json_loads(raw.decode("utf-8", errors="replace"), {})
    external_id = verified.get("external_id") or _external_id(key, payload, raw)
    if _webhook_seen(key, external_id):
        return {"ok": True, "deduped": True, "processed": False, "summary": f"Duplicate {key} webhook ignored."}
    event = _webhook_to_gateway_event(key, payload, header_map)
    routed = friday_gateway.ingest_event(key, event["event_type"], event["title"], event["content"], actor=event["actor"], source=f"{key}_webhook", payload=event["payload"], route=True)
    _record_webhook(key, external_id, True, True, int(routed.get("id") or 0), payload)
    return {"ok": True, "processed": True, "event": routed, "summary": f"{key} webhook accepted and routed."}


def verify_webhook(connector: str, headers: dict[str, str] | None = None, body: bytes | str = b"", query: dict[str, str] | None = None) -> dict[str, Any]:
    key = _connector(connector)
    raw = body if isinstance(body, bytes) else str(body or "").encode("utf-8")
    verifier = _WEBHOOK_VERIFIERS.get(key)
    if not verifier:
        return {"ok": True, "external_id": _hash(raw), "summary": "No signature verifier configured; accepted as local/test connector."}
    return verifier({str(k).lower(): str(v) for k, v in (headers or {}).items()}, raw, query or {})


def wipe_all() -> None:
    init_db()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.execute("DELETE FROM connector_outbox")
        conn.execute("DELETE FROM connector_webhook_events")


def _send_telegram(item: dict[str, Any]) -> dict[str, Any]:
    token = _required_env("TELEGRAM_BOT_TOKEN")
    return _post_json(f"https://api.telegram.org/bot{token}/sendMessage", {"chat_id": item["target"], "text": item["body"]})


def _send_slack(item: dict[str, Any]) -> dict[str, Any]:
    token = _required_env("SLACK_BOT_TOKEN")
    return _post_json("https://slack.com/api/chat.postMessage", {"channel": item["target"], "text": item["body"]}, headers={"Authorization": f"Bearer {token}"})


def _send_discord(item: dict[str, Any]) -> dict[str, Any]:
    if item["target"].startswith("https://"):
        return _post_json(item["target"], {"content": item["body"]})
    token = _required_env("DISCORD_BOT_TOKEN")
    return _post_json(f"https://discord.com/api/v10/channels/{urllib.parse.quote(item['target'])}/messages", {"content": item["body"]}, headers={"Authorization": f"Bot {token}"})


def _send_whatsapp(item: dict[str, Any]) -> dict[str, Any]:
    token = _required_env("WHATSAPP_ACCESS_TOKEN")
    phone_number_id = _required_env("WHATSAPP_PHONE_NUMBER_ID")
    version = str(config_value("connector_whatsapp_graph_version", os.getenv("WHATSAPP_GRAPH_VERSION", "v20.0")) or "v20.0").strip()
    payload = {"messaging_product": "whatsapp", "to": item["target"], "type": "text", "text": {"body": item["body"]}}
    return _post_json(f"https://graph.facebook.com/{version}/{urllib.parse.quote(phone_number_id)}/messages", payload, headers={"Authorization": f"Bearer {token}"})


def _send_gmail(item: dict[str, Any]) -> dict[str, Any]:
    from tools import email_tool

    result = email_tool._send(item["target"], item["subject"] or "Friday message", item["body"], sender=os.getenv("GMAIL_ADDRESS"), password=os.getenv("GMAIL_APP_PASSWORD"))
    if not result.lower().startswith("email sent"):
        raise RuntimeError(result)
    return {"ok": True, "summary": result}


def _send_google_calendar(item: dict[str, Any]) -> dict[str, Any]:
    from core import google_workspace

    payload = item["payload"]
    event = google_workspace.create_calendar_event(item["subject"] or item["body"][:80] or "Friday event", start_at=str(payload.get("start_at") or ""), end_at=str(payload.get("end_at") or ""), location=str(payload.get("location") or ""), notes=item["body"])
    return {"ok": True, "event": event, "summary": f"Google Calendar event created: {event.get('title') or event.get('id')}"}


def _send_sheets(item: dict[str, Any]) -> dict[str, Any]:
    from core import google_workspace

    payload = item["payload"]
    sheet = google_workspace.create_sheet(item["subject"] or "Friday sheet", headers=payload.get("headers") if isinstance(payload.get("headers"), list) else [])
    return {"ok": True, "sheet": sheet, "summary": f"Google Sheet created: {sheet.get('title') or sheet.get('id')}"}


def _send_github(item: dict[str, Any]) -> dict[str, Any]:
    token = _required_env("GITHUB_TOKEN")
    repo = item["payload"].get("repo") or item["target"]
    title = item["subject"] or item["body"][:80] or "Friday issue"
    return _post_json(f"https://api.github.com/repos/{repo}/issues", {"title": title, "body": item["body"]}, headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"})


def _send_render(item: dict[str, Any]) -> dict[str, Any]:
    token = _required_env("RENDER_API_KEY")
    service_id = item["payload"].get("service_id") or item["target"]
    return _post_json(f"https://api.render.com/v1/services/{urllib.parse.quote(str(service_id))}/deploys", {"clearCache": bool(item["payload"].get("clear_cache", False))}, headers={"Authorization": f"Bearer {token}"})


def _send_vercel(item: dict[str, Any]) -> dict[str, Any]:
    if item["target"].startswith("https://"):
        return _post_json(item["target"], item["payload"] or {})
    raise RuntimeError("Vercel outbound requires a deploy hook URL as target.")


def _send_notion(item: dict[str, Any]) -> dict[str, Any]:
    token = _required_env("NOTION_TOKEN")
    database_id = item["payload"].get("database_id") or item["target"]
    title = item["subject"] or item["body"][:80] or "Friday note"
    payload = {
        "parent": {"database_id": database_id},
        "properties": {"Name": {"title": [{"text": {"content": title}}]}},
        "children": [{"object": "block", "type": "paragraph", "paragraph": {"rich_text": [{"type": "text", "text": {"content": item["body"][:1800]}}]}}],
    }
    return _post_json("https://api.notion.com/v1/pages", payload, headers={"Authorization": f"Bearer {token}", "Notion-Version": "2022-06-28"})


def _send_trello(item: dict[str, Any]) -> dict[str, Any]:
    key = _required_env("TRELLO_KEY")
    token = _required_env("TRELLO_TOKEN")
    query = urllib.parse.urlencode({"idList": item["target"], "key": key, "token": token, "name": item["subject"] or item["body"][:80], "desc": item["body"]})
    return _post_json(f"https://api.trello.com/1/cards?{query}", {})


_ADAPTERS = {
    "discord": _send_discord,
    "github": _send_github,
    "gmail": _send_gmail,
    "google_calendar": _send_google_calendar,
    "notion": _send_notion,
    "render": _send_render,
    "sheets": _send_sheets,
    "slack": _send_slack,
    "telegram": _send_telegram,
    "trello": _send_trello,
    "vercel": _send_vercel,
    "whatsapp": _send_whatsapp,
}


def _verify_slack(headers: dict[str, str], body: bytes, _query: dict[str, str]) -> dict[str, Any]:
    secret = os.getenv("SLACK_SIGNING_SECRET", "")
    signature = headers.get("x-slack-signature", "")
    timestamp = headers.get("x-slack-request-timestamp", "")
    if not secret or not signature or not timestamp:
        return {"ok": False, "summary": "Missing Slack signing data."}
    try:
        if abs(time.time() - int(timestamp)) > 60 * 5:
            return {"ok": False, "summary": "Slack webhook timestamp is too old."}
    except Exception:
        return {"ok": False, "summary": "Invalid Slack timestamp."}
    expected = "v0=" + hmac.new(secret.encode("utf-8"), b"v0:" + timestamp.encode("utf-8") + b":" + body, hashlib.sha256).hexdigest()
    return {"ok": hmac.compare_digest(expected, signature), "external_id": _hash(body), "summary": "Slack signature accepted." if hmac.compare_digest(expected, signature) else "Slack signature rejected."}


def _verify_hmac_header(env_name: str, header_name: str, digest: str = "sha256", prefix: str = "") -> Any:
    def verify(headers: dict[str, str], body: bytes, _query: dict[str, str]) -> dict[str, Any]:
        secret = os.getenv(env_name, "")
        signature = headers.get(header_name.lower(), "")
        if not secret or not signature:
            return {"ok": False, "summary": f"Missing {header_name} signature."}
        algorithm = getattr(hashlib, digest)
        expected = prefix + hmac.new(secret.encode("utf-8"), body, algorithm).hexdigest()
        return {"ok": hmac.compare_digest(expected, signature), "external_id": _hash(body), "summary": "Webhook signature accepted." if hmac.compare_digest(expected, signature) else "Webhook signature rejected."}

    return verify


def _verify_telegram(headers: dict[str, str], body: bytes, _query: dict[str, str]) -> dict[str, Any]:
    token = os.getenv("TELEGRAM_WEBHOOK_SECRET", "")
    if token and not hmac.compare_digest(headers.get("x-telegram-bot-api-secret-token", ""), token):
        return {"ok": False, "summary": "Telegram webhook secret rejected."}
    return {"ok": True, "external_id": _hash(body), "summary": "Telegram webhook accepted."}


def _verify_whatsapp(_headers: dict[str, str], body: bytes, query: dict[str, str]) -> dict[str, Any]:
    verify_token = os.getenv("WHATSAPP_VERIFY_TOKEN", "")
    if query.get("hub.mode") == "subscribe":
        return {"ok": bool(verify_token and hmac.compare_digest(query.get("hub.verify_token", ""), verify_token)), "challenge": query.get("hub.challenge", ""), "external_id": "whatsapp_verify", "summary": "WhatsApp verification checked."}
    app_secret = os.getenv("WHATSAPP_APP_SECRET", "")
    signature = _headers.get("x-hub-signature-256", "")
    if app_secret:
        expected = "sha256=" + hmac.new(app_secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, signature):
            return {"ok": False, "external_id": _hash(body), "summary": "WhatsApp webhook signature rejected."}
    return {"ok": True, "external_id": _hash(body), "summary": "WhatsApp webhook accepted."}


def _verify_stripe(headers: dict[str, str], body: bytes, _query: dict[str, str]) -> dict[str, Any]:
    secret = os.getenv("STRIPE_WEBHOOK_SECRET", "")
    header = headers.get("stripe-signature", "")
    if not secret or not header:
        return {"ok": False, "summary": "Missing Stripe webhook signature."}
    pieces = {}
    for item in header.split(","):
        key, _, value = item.partition("=")
        if key and value:
            pieces.setdefault(key, []).append(value)
    timestamp = (pieces.get("t") or [""])[0]
    signatures = pieces.get("v1") or []
    if not timestamp or not signatures:
        return {"ok": False, "summary": "Invalid Stripe webhook signature header."}
    expected = hmac.new(secret.encode("utf-8"), timestamp.encode("utf-8") + b"." + body, hashlib.sha256).hexdigest()
    return {"ok": any(hmac.compare_digest(expected, signature) for signature in signatures), "external_id": _hash(body), "summary": "Stripe signature accepted." if any(hmac.compare_digest(expected, signature) for signature in signatures) else "Stripe signature rejected."}


_WEBHOOK_VERIFIERS = {
    "github": _verify_hmac_header("GITHUB_WEBHOOK_SECRET", "x-hub-signature-256", prefix="sha256="),
    "paystack": _verify_hmac_header("PAYSTACK_SECRET_KEY", "x-paystack-signature", digest="sha512"),
    "slack": _verify_slack,
    "stripe": _verify_stripe,
    "telegram": _verify_telegram,
    "whatsapp": _verify_whatsapp,
}


def _post_json(url: str, payload: dict[str, Any], *, headers: dict[str, str] | None = None, timeout: float | None = None) -> dict[str, Any]:
    data = json.dumps(payload, ensure_ascii=True, default=str).encode("utf-8")
    request = urllib.request.Request(url, data=data, method="POST")
    request.add_header("Content-Type", "application/json")
    for key, value in (headers or {}).items():
        request.add_header(key, value)
    try:
        with urllib.request.urlopen(request, timeout=float(timeout or config_value("connector_request_timeout_seconds", 20.0))) as response:
            text = response.read().decode("utf-8", errors="replace")
            parsed = _json_loads(text, {"raw": text})
            ok = 200 <= int(response.status) < 300
            if isinstance(parsed, dict) and parsed.get("ok") is False:
                ok = False
            if not ok:
                raise RuntimeError(str(parsed)[:1000])
            return {"ok": True, "status": int(response.status), "response": _redact(parsed), "summary": f"Connector API call succeeded with HTTP {response.status}."}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:1000]
        raise RuntimeError(f"HTTP {exc.code}: {detail}") from exc


def _mark_sent(item: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("UPDATE connector_outbox SET status='sent', result_json=?, last_error='', updated_at=? WHERE id=?", (_json_dumps(_redact(result)), _now(), int(item["id"])))
        row = conn.execute("SELECT * FROM connector_outbox WHERE id=?", (int(item["id"]),)).fetchone()
    updated = _outbox_row(row)
    audit_log.record(category="connector_runtime", action="dispatch", target=f"{item['connector']}:{item['target']}", success=True, details={"outbox_id": item["id"], "result": _redact(result)})
    trust_proof.create_report(
        f"Connector dispatch #{item['id']}",
        changed=[f"{item['connector']} {item['action']} sent to {item['target']}"],
        tested=[result.get("summary") or "Provider returned success."],
        evidence=[_json_dumps(_redact(result))[:1000]],
        risks=["Provider-side delivery/read status may still require separate verification."],
        confidence=0.82,
        metadata={"source": "connector_runtime", "outbox_id": item["id"]},
    )
    return updated | {"ok": True, "summary": f"Connector outbox #{item['id']} sent via {item['connector']}."}


def _mark_failed(item: dict[str, Any], error: str, *, retry: bool) -> dict[str, Any]:
    status_value = "retry" if retry else "failed"
    next_attempt = _next_attempt(item["attempts"]) if retry else ""
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute(
            "UPDATE connector_outbox SET status=?, last_error=?, next_attempt_at=?, updated_at=? WHERE id=?",
            (status_value, _clean(error)[:2000], next_attempt, _now(), int(item["id"])),
        )
        row = conn.execute("SELECT * FROM connector_outbox WHERE id=?", (int(item["id"]),)).fetchone()
    audit_log.record(category="connector_runtime", action="dispatch", target=f"{item['connector']}:{item['target']}", success=False, details={"outbox_id": item["id"], "error": error, "retry": retry})
    return _outbox_row(row) | {"ok": False, "summary": f"Connector outbox #{item['id']} {status_value}: {_clean(error)[:180]}"}


def _record_webhook(connector: str, external_id: str, signature_ok: bool, processed: bool, event_id: int, payload: dict[str, Any]) -> None:
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.execute(
            "INSERT OR IGNORE INTO connector_webhook_events(timestamp, connector, external_id, signature_ok, processed, event_id, payload_json) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (_now(), connector, external_id[:300], 1 if signature_ok else 0, 1 if processed else 0, event_id or None, _json_dumps(_redact(payload))),
        )


def _webhook_seen(connector: str, external_id: str) -> bool:
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        return bool(conn.execute("SELECT 1 FROM connector_webhook_events WHERE connector=? AND external_id=?", (connector, external_id[:300])).fetchone())


def _webhook_to_gateway_event(connector: str, payload: dict[str, Any], headers: dict[str, str]) -> dict[str, Any]:
    title = f"{connector} webhook"
    actor = headers.get("x-github-sender") or ""
    content = ""
    event_type = "message"
    if connector == "github":
        action = str(payload.get("action") or "")
        issue = payload.get("issue") or payload.get("pull_request") or {}
        title = f"GitHub {action}: {issue.get('title') or payload.get('repository', {}).get('full_name') or 'event'}"
        content = str(issue.get("body") or payload.get("zen") or "")
        actor = str((payload.get("sender") or {}).get("login") or actor)
        event_type = "github_event"
    elif connector in {"slack", "telegram", "whatsapp", "discord"}:
        message = payload.get("message") or payload.get("event") or payload
        content = str(message.get("text") or message.get("body") or payload.get("text") or "") if isinstance(message, dict) else str(message)
        actor = str((message.get("from") or message.get("user") or actor) if isinstance(message, dict) else actor)
        title = f"{connector} message"
        event_type = "client_message" if connector in {"whatsapp", "telegram"} else "message"
    else:
        content = _json_dumps(_redact(payload))[:2000]
    return {"event_type": event_type, "title": title, "content": content, "actor": actor, "payload": _redact(payload)}


def _approval_required(connector: str, action: str) -> bool:
    if bool(config_value("connector_runtime_default_approval_required", True)):
        return True
    if action in {"deploy", "payment", "delete", "credential"}:
        return True
    spec = friday_gateway.CONNECTORS.get(connector, {})
    if spec.get("risk") == "high":
        return True
    return connector in {"slack", "discord", "telegram", "gmail", "whatsapp"}


def _rate_limit_message(connector: str) -> str:
    daily_limit = int(config_value(f"connector_{connector}_daily_limit", config_value("connector_default_daily_limit", 100)))
    if daily_limit <= 0:
        return ""
    today = _now()[:10]
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        count = int(conn.execute("SELECT COUNT(*) FROM connector_outbox WHERE connector=? AND status='sent' AND updated_at LIKE ?", (connector, f"{today}%")).fetchone()[0])
    return f"{connector} daily outbound limit {daily_limit} reached." if count >= daily_limit else ""


def _counts(table: str, column: str) -> dict[str, int]:
    init_db()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        rows = conn.execute(f"SELECT {column}, COUNT(*) FROM {table} GROUP BY {column}").fetchall()
    return {str(key): int(count) for key, count in rows}


def _outbox_row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "created_at": str(row["created_at"]),
        "updated_at": str(row["updated_at"]),
        "connector": str(row["connector"]),
        "target": str(row["target"]),
        "action": str(row["action"]),
        "subject": str(row["subject"]),
        "body": str(row["body"]),
        "status": str(row["status"]),
        "approval_id": int(row["approval_id"] or 0),
        "attempts": int(row["attempts"] or 0),
        "next_attempt_at": str(row["next_attempt_at"]),
        "last_error": str(row["last_error"]),
        "payload": _json_loads(row["payload_json"], {}),
        "result": _json_loads(row["result_json"], {}),
        "summary": f"{row['connector']} {row['action']} to {row['target']} is {row['status']}.",
    }


def _external_id(connector: str, payload: dict[str, Any], raw: bytes) -> str:
    for key in ("id", "event_id", "webhook_id"):
        if payload.get(key):
            return str(payload[key])
    if connector == "github" and payload.get("delivery"):
        return str(payload["delivery"])
    return _hash(raw)


def _required_env(name: str) -> str:
    value = os.getenv(name, "")
    if not value or value.lower().startswith(("your_", "replace_", "changeme")):
        raise RuntimeError(f"Missing required environment variable {name}.")
    return value


def _next_attempt(attempts: int) -> str:
    seconds = min(3600, 30 * max(1, int(attempts or 1)))
    return (dt.datetime.now(dt.timezone.utc).astimezone() + dt.timedelta(seconds=seconds)).isoformat(timespec="seconds")


def _max_attempts() -> int:
    return max(1, min(10, int(config_value("connector_max_retry_attempts", 3))))


def _dedupe_key(*parts: Any) -> str:
    return hashlib.sha256(_json_dumps(parts).encode("utf-8")).hexdigest()


def _hash(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _connector(value: Any) -> str:
    text = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    return "".join(ch for ch in text if ch.isalnum() or ch == "_").strip("_") or "message"


def _redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): "[redacted]" if any(term in str(key).lower() for term in SECRET_KEYS) else _redact(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_redact(item) for item in value[:100]]
    if isinstance(value, str):
        return value[:12000]
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return _clean(value)[:1000]


def _clean(value: Any) -> str:
    return " ".join(str(value or "").replace("\x00", " ").strip().split())


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, default=str)


def _json_loads(value: str | bytes, default: Any) -> Any:
    try:
        if isinstance(value, bytes):
            value = value.decode("utf-8", errors="replace")
        parsed = json.loads(value or "")
        return parsed if parsed is not None else default
    except Exception:
        return default


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds")
