"""Friday Gateway: connector registry, event intake, routing, and control room."""

from __future__ import annotations

import datetime as dt
import json
import os
import re
import sqlite3
import threading
from pathlib import Path
from typing import Any

from core import (
    agency_mode,
    approval_inbox,
    audit_log,
    background_agents,
    barge_in,
    cloud_worker_mode,
    model_router_brain,
    notification_center,
    personal_knowledge_vault,
    project_memory,
    reliability_score,
    skill_library,
    task_queue,
    trust_proof,
)
from core.config import DATA_DIR, config_value, ensure_runtime_dirs

DB_PATH = DATA_DIR / "friday_gateway.sqlite3"
_LOCK = threading.Lock()
SECRET_RE = re.compile(r"(api[_-]?key|token|secret|password|authorization|cookie|credential)", re.IGNORECASE)

CONNECTORS: dict[str, dict[str, Any]] = {
    "web": {"name": "Web dashboard", "category": "first_party", "env": [], "inbound": True, "outbound": True, "risk": "low"},
    "desktop": {"name": "Desktop app", "category": "first_party", "env": [], "inbound": True, "outbound": True, "risk": "medium"},
    "android": {"name": "Android app", "category": "mobile", "env": [], "inbound": True, "outbound": True, "risk": "medium"},
    "browser_extension": {"name": "Browser extension", "category": "browser", "env": [], "inbound": True, "outbound": True, "risk": "medium"},
    "whatsapp": {"name": "WhatsApp", "category": "messages", "env": ["WHATSAPP_ACCESS_TOKEN", "WHATSAPP_PHONE_NUMBER_ID"], "inbound": True, "outbound": True, "risk": "high"},
    "telegram": {"name": "Telegram", "category": "messages", "env": ["TELEGRAM_BOT_TOKEN"], "inbound": True, "outbound": True, "risk": "high"},
    "discord": {"name": "Discord", "category": "messages", "env": ["DISCORD_BOT_TOKEN"], "inbound": True, "outbound": True, "risk": "medium"},
    "slack": {"name": "Slack", "category": "messages", "env": ["SLACK_BOT_TOKEN", "SLACK_SIGNING_SECRET"], "inbound": True, "outbound": True, "risk": "medium"},
    "gmail": {"name": "Gmail", "category": "workspace", "env": ["GMAIL_ADDRESS", "GMAIL_APP_PASSWORD"], "inbound": True, "outbound": True, "risk": "high"},
    "google_calendar": {"name": "Google Calendar", "category": "workspace", "env": ["GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET"], "inbound": True, "outbound": True, "risk": "medium"},
    "github": {"name": "GitHub", "category": "developer", "env": ["GITHUB_TOKEN"], "inbound": True, "outbound": True, "risk": "medium"},
    "render": {"name": "Render", "category": "deployment", "env": ["RENDER_API_KEY"], "inbound": True, "outbound": True, "risk": "high"},
    "vercel": {"name": "Vercel", "category": "deployment", "env": ["VERCEL_TOKEN"], "inbound": True, "outbound": True, "risk": "high"},
    "stripe": {"name": "Stripe", "category": "payments", "env": ["STRIPE_SECRET_KEY", "STRIPE_WEBHOOK_SECRET"], "inbound": True, "outbound": True, "risk": "high"},
    "paystack": {"name": "Paystack", "category": "payments", "env": ["PAYSTACK_SECRET_KEY"], "inbound": True, "outbound": True, "risk": "high"},
    "notion": {"name": "Notion", "category": "office", "env": ["NOTION_TOKEN"], "inbound": True, "outbound": True, "risk": "medium"},
    "trello": {"name": "Trello", "category": "office", "env": ["TRELLO_KEY", "TRELLO_TOKEN"], "inbound": True, "outbound": True, "risk": "medium"},
    "sheets": {"name": "Google Sheets", "category": "office", "env": ["GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET"], "inbound": True, "outbound": True, "risk": "medium"},
    "local_apps": {"name": "Local apps", "category": "desktop", "env": [], "inbound": True, "outbound": True, "risk": "medium"},
}

EVENT_TYPES = {
    "message",
    "task_request",
    "client_message",
    "lead",
    "approval",
    "deploy_signal",
    "payment_signal",
    "browser_event",
    "mobile_event",
    "github_event",
    "calendar_event",
    "error",
    "cost",
    "proof",
}

HIGH_RISK_EVENT_TYPES = {"approval", "deploy_signal", "payment_signal", "client_message"}


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
            CREATE TABLE IF NOT EXISTS gateway_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                source TEXT NOT NULL,
                connector TEXT NOT NULL,
                event_type TEXT NOT NULL,
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                actor TEXT NOT NULL,
                status TEXT NOT NULL,
                risk TEXT NOT NULL,
                task_id INTEGER,
                approval_id INTEGER,
                payload_json TEXT NOT NULL
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_gateway_events_connector ON gateway_events(connector, event_type, id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_gateway_events_status ON gateway_events(status, risk, id)")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS connector_states (
                connector TEXT PRIMARY KEY,
                enabled INTEGER NOT NULL,
                mode TEXT NOT NULL,
                trust_level TEXT NOT NULL,
                last_seen_at TEXT NOT NULL,
                metadata_json TEXT NOT NULL
            )
            """
        )


def status() -> dict[str, Any]:
    init_db()
    connectors = connector_status()
    recent = list_events(limit=10)
    configured = [item for item in connectors if item["configured"]]
    enabled = [item for item in connectors if item["enabled"]]
    pending_high_risk = [item for item in recent if item["risk"] == "high" and item["status"] in {"pending_approval", "queued"}]
    return {
        "enabled": bool(config_value("friday_gateway_enabled", True)),
        "connector_count": len(connectors),
        "configured_count": len(configured),
        "enabled_count": len(enabled),
        "pending_high_risk": len(pending_high_risk),
        "connectors": connectors,
        "recent_events": recent,
        "summary": f"Friday Gateway has {len(enabled)} enabled connector(s), {len(configured)} configured connector(s), and {len(pending_high_risk)} high-risk event(s) waiting.",
    }


def connector_status() -> list[dict[str, Any]]:
    init_db()
    states = _states()
    rows = []
    for key, spec in CONNECTORS.items():
        state = states.get(key, {})
        env_names = list(spec.get("env") or [])
        configured = all(_env_configured(name) for name in env_names) if env_names else True
        enabled = bool(state.get("enabled", _default_enabled(key)))
        mode = str(state.get("mode") or "webhook")
        trust_level = str(state.get("trust_level") or ("verified" if key in {"web", "desktop", "android", "browser_extension"} else "unverified"))
        rows.append(
            {
                "key": key,
                "name": spec["name"],
                "category": spec["category"],
                "configured": configured,
                "enabled": enabled,
                "mode": mode,
                "trust_level": trust_level,
                "risk": spec["risk"],
                "inbound": bool(spec.get("inbound")),
                "outbound": bool(spec.get("outbound")),
                "required_env": env_names,
                "last_seen_at": str(state.get("last_seen_at") or ""),
                "metadata": state.get("metadata") or {},
            }
        )
    return rows


def configure_connector(connector: str, *, enabled: bool | None = None, mode: str = "", trust_level: str = "", metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    key = _connector_key(connector)
    if key not in CONNECTORS:
        raise ValueError("unknown connector")
    current = {item["key"]: item for item in connector_status()}.get(key, {})
    next_enabled = current.get("enabled", True) if enabled is None else bool(enabled)
    next_mode = _clean(mode) or str(current.get("mode") or "webhook")
    next_trust = _trust(trust_level or str(current.get("trust_level") or "unverified"))
    safe_metadata = _redact(metadata or {})
    now = _now()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.execute(
            """
            INSERT INTO connector_states(connector, enabled, mode, trust_level, last_seen_at, metadata_json)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(connector) DO UPDATE SET enabled=excluded.enabled, mode=excluded.mode, trust_level=excluded.trust_level, last_seen_at=excluded.last_seen_at, metadata_json=excluded.metadata_json
            """,
            (key, 1 if next_enabled else 0, next_mode, next_trust, now, _json_dumps(safe_metadata)),
        )
    audit_log.record(category="gateway", action="configure_connector", target=key, success=True, details={"enabled": next_enabled, "mode": next_mode, "trust_level": next_trust})
    return {item["key"]: item for item in connector_status()}[key]


def ingest_event(
    connector: str,
    event_type: str,
    title: str,
    content: str = "",
    *,
    actor: str = "",
    source: str = "gateway",
    payload: dict[str, Any] | None = None,
    route: bool = True,
) -> dict[str, Any]:
    init_db()
    if not bool(config_value("friday_gateway_enabled", True)):
        return {"ok": False, "summary": "Friday Gateway is disabled."}
    key = _connector_key(connector)
    if key not in CONNECTORS:
        raise ValueError("unknown connector")
    connector_info = {item["key"]: item for item in connector_status()}[key]
    if not connector_info["enabled"]:
        return {"ok": False, "summary": f"Connector {key} is disabled."}
    normalized_type = _event_type(event_type)
    risk = _event_risk(key, normalized_type)
    status = "received"
    safe_payload = _redact(payload or {})
    now = _now()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            """
            INSERT INTO gateway_events(timestamp, updated_at, source, connector, event_type, title, content, actor, status, risk, task_id, approval_id, payload_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, ?)
            """,
            (now, now, _clean(source) or "gateway", key, normalized_type, _clean(title)[:300] or "Gateway event", _clean(content)[:10000], _clean(actor)[:200], status, risk, _json_dumps(safe_payload)),
        )
        event_id = int(cursor.lastrowid)
        conn.execute(
            """
            INSERT INTO connector_states(connector, enabled, mode, trust_level, last_seen_at, metadata_json)
            VALUES (?, 1, 'webhook', ?, ?, '{}')
            ON CONFLICT(connector) DO UPDATE SET last_seen_at=excluded.last_seen_at
            """,
            (key, connector_info.get("trust_level") or "unverified", now),
        )
        row = conn.execute("SELECT * FROM gateway_events WHERE id=?", (event_id,)).fetchone()
    event = _event_row(row)
    routed = route_event(event["id"]) if route else event
    audit_log.record(category="gateway", action="ingest_event", target=f"{key}:{normalized_type}", success=True, details={"event_id": event_id, "risk": risk})
    return routed | {"ok": True, "summary": _event_summary(routed)}


def route_event(event_id: int) -> dict[str, Any]:
    event = get_event(event_id)
    if not event:
        raise ValueError("event not found")
    task_id = int(event.get("task_id") or 0)
    approval_id = int(event.get("approval_id") or 0)
    status_value = event["status"]
    if event["risk"] == "high" or event["event_type"] in HIGH_RISK_EVENT_TYPES:
        if not approval_id:
            approval = approval_inbox.create(
                kind="gateway_event",
                title=f"Review {event['connector']} {event['event_type']}",
                summary=f"{event['title']}: {event['content'][:500]}",
                source="friday_gateway",
                payload={"event_id": event["id"], "connector": event["connector"], "event_type": event["event_type"], "risk": event["risk"]},
            )
            approval_id = int(approval.get("id") or 0)
        status_value = "pending_approval"
    elif not task_id and bool(config_value("gateway_auto_task_events", True)):
        agent_id = _agent_for_event(event)
        task_id = task_queue.create_task(
            f"Gateway {event['event_type']}: {event['title']}",
            description=f"Connector: {event['connector']}\nActor: {event['actor']}\n\n{event['content']}",
            agent_id=agent_id,
            priority=_priority_for_event(event),
            input_data={"source": "friday_gateway", "gateway_event_id": event["id"], "connector": event["connector"], "event_type": event["event_type"], "payload": event["payload"]},
        )
        status_value = "queued"
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("UPDATE gateway_events SET status=?, task_id=?, approval_id=?, updated_at=? WHERE id=?", (status_value, task_id or None, approval_id or None, _now(), int(event_id)))
        row = conn.execute("SELECT * FROM gateway_events WHERE id=?", (int(event_id),)).fetchone()
    routed = _event_row(row)
    notification_center.add(
        source="friday_gateway",
        category="gateway",
        severity=3 if routed["risk"] == "high" else 1,
        title=f"Gateway {routed['event_type']}",
        message=_event_summary(routed),
        dedupe_key=f"gateway:{routed['id']}",
        metadata={"event_id": routed["id"], "connector": routed["connector"], "status": routed["status"]},
    )
    return routed


def list_events(connector: str = "", event_type: str = "", status: str = "", limit: int = 50) -> list[dict[str, Any]]:
    init_db()
    where: list[str] = []
    params: list[Any] = []
    if _clean(connector):
        where.append("connector=?")
        params.append(_connector_key(connector))
    if _clean(event_type):
        where.append("event_type=?")
        params.append(_event_type(event_type))
    if _clean(status):
        where.append("status=?")
        params.append(_clean(status))
    params.append(_limit(limit, 300))
    clause = "WHERE " + " AND ".join(where) if where else ""
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(f"SELECT * FROM gateway_events {clause} ORDER BY id DESC LIMIT ?", params).fetchall()
    return [_event_row(row) for row in rows]


def get_event(event_id: int) -> dict[str, Any] | None:
    init_db()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM gateway_events WHERE id=?", (int(event_id),)).fetchone()
    return _event_row(row) if row else None


def remember_business_context(kind: str, title: str, content: str = "", *, confidence: float = 0.8, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    normalized = _business_kind(kind)
    item = personal_knowledge_vault.remember(
        "project" if normalized in {"project", "business", "lead"} else "fact",
        title,
        content,
        confidence=confidence,
        tags=["friday_business", normalized],
        metadata={"business_kind": normalized, **(metadata or {})},
    )
    return item | {"business_kind": normalized, "summary": f"Remembered {normalized}: {item['title']}."}


def business_memory(limit: int = 30) -> dict[str, Any]:
    items = personal_knowledge_vault.search("friday_business", limit=limit)
    grouped: dict[str, int] = {}
    for item in items:
        kind = str((item.get("metadata") or {}).get("business_kind") or "fact")
        grouped[kind] = grouped.get(kind, 0) + 1
    return {"items": items, "counts": grouped, "summary": f"{len(items)} Friday business memory item(s) available for review."}


def control_room() -> dict[str, Any]:
    gateway = status()
    tasks = task_queue.counts()
    approvals = approval_inbox.summary(limit=8)
    agency = agency_mode.status()
    skills = skill_library.skill_summary()
    router = model_router_brain.summary()
    cloud = cloud_worker_mode.status()
    reliability = reliability_score.status()
    proof = trust_proof.summary()
    audit = audit_log.recent(limit=10)
    recent_errors = [item for item in audit if not item.get("success")]
    return {
        "gateway": gateway,
        "workers": background_agents.worker_status(),
        "tasks": tasks,
        "approvals": approvals,
        "agency": agency,
        "skills": skills,
        "model_router": router,
        "cloud_worker": cloud,
        "reliability": reliability,
        "proof": proof,
        "audit": audit,
        "errors": recent_errors,
        "business_memory": business_memory(limit=12),
        "project_memory": _safe(project_memory.status, {}),
        "summary": f"Control room: {tasks.get('active', 0)} active task(s), {approvals.get('count', 0)} approval(s), {gateway.get('pending_high_risk', 0)} gateway high-risk event(s), {agency.get('finance', {}).get('profit', 0):.2f} tracked agency profit.",
    }


def emergency_stop(reason: str = "") -> dict[str, Any]:
    barge = _safe(lambda: barge_in.request_stop(_clean(reason) or "gateway emergency stop"), {})
    _safe(background_agents.stop_workers, None)
    audit_id = audit_log.record(category="gateway", action="emergency_stop", target="all_workers", success=True, details={"reason": reason, "barge_in": barge})
    notice = notification_center.add(source="friday_gateway", category="safety", severity=4, title="Emergency stop", message=_clean(reason) or "Friday emergency stop requested.", dedupe_key=f"gateway:stop:{audit_id}")
    return {"ok": True, "audit_id": audit_id, "notification": notice, "barge_in": barge, "summary": "Emergency stop requested; live speech/workers were asked to stop."}


def wipe_all() -> None:
    init_db()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.execute("DELETE FROM gateway_events")
        conn.execute("DELETE FROM connector_states")


def _states() -> dict[str, dict[str, Any]]:
    init_db()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM connector_states").fetchall()
    return {
        str(row["connector"]): {
            "enabled": bool(row["enabled"]),
            "mode": str(row["mode"]),
            "trust_level": str(row["trust_level"]),
            "last_seen_at": str(row["last_seen_at"]),
            "metadata": _json_loads(row["metadata_json"], {}),
        }
        for row in rows
    }


def _event_row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "timestamp": str(row["timestamp"]),
        "updated_at": str(row["updated_at"]),
        "source": str(row["source"]),
        "connector": str(row["connector"]),
        "event_type": str(row["event_type"]),
        "title": str(row["title"]),
        "content": str(row["content"]),
        "actor": str(row["actor"]),
        "status": str(row["status"]),
        "risk": str(row["risk"]),
        "task_id": int(row["task_id"] or 0),
        "approval_id": int(row["approval_id"] or 0),
        "payload": _json_loads(row["payload_json"], {}),
    }


def _agent_for_event(event: dict[str, Any]) -> str:
    text = f"{event.get('event_type')} {event.get('title')} {event.get('content')}".lower()
    if any(term in text for term in ("lead", "prospect", "client", "proposal")):
        return "sales_agent"
    if any(term in text for term in ("invoice", "payment", "cost", "profit", "subscription")):
        return "finance_admin"
    if any(term in text for term in ("deploy", "vercel", "render", "github", "ci")):
        return "devops"
    if any(term in text for term in ("bug", "error", "test", "qa")):
        return "qa_engineer"
    if any(term in text for term in ("design", "figma", "ui", "ux")):
        return "ui_ux_designer"
    if any(term in text for term in ("research", "find", "source")):
        return "lead_researcher"
    if any(term in text for term in ("support", "question", "customer")):
        return "customer_support"
    return "project_manager"


def _priority_for_event(event: dict[str, Any]) -> int:
    if event.get("risk") == "high":
        return 1
    if event.get("event_type") in {"error", "approval"}:
        return 2
    return 5


def _event_risk(connector: str, event_type: str) -> str:
    if event_type in HIGH_RISK_EVENT_TYPES:
        return "high"
    risk = str(CONNECTORS.get(connector, {}).get("risk") or "medium")
    if risk == "high" and event_type in {"message", "lead", "browser_event", "mobile_event", "github_event", "calendar_event"}:
        return "medium"
    return risk


def _event_summary(event: dict[str, Any]) -> str:
    route = f" task #{event['task_id']}" if event.get("task_id") else f" approval #{event['approval_id']}" if event.get("approval_id") else ""
    return f"{event['connector']} {event['event_type']} event #{event['id']} is {event['status']}{route}."


def _redact(value: Any) -> Any:
    if isinstance(value, dict):
        clean: dict[str, Any] = {}
        for key, item in value.items():
            text_key = str(key)
            if SECRET_RE.search(text_key):
                clean[text_key] = "[redacted]"
            else:
                clean[text_key] = _redact(item)
        return clean
    if isinstance(value, list):
        return [_redact(item) for item in value[:100]]
    if isinstance(value, str):
        return value[:10000]
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return _clean(value)[:1000]


def _connector_key(value: str) -> str:
    return re.sub(r"[^a-z0-9_]+", "_", str(value or "").strip().lower()).strip("_")


def _event_type(value: str) -> str:
    normalized = _connector_key(value)
    return normalized if normalized in EVENT_TYPES else "message"


def _trust(value: str) -> str:
    normalized = _connector_key(value)
    return normalized if normalized in {"verified", "unverified", "sandboxed", "blocked"} else "unverified"


def _business_kind(value: str) -> str:
    normalized = _connector_key(value)
    allowed = {"person", "project", "business", "lead", "coding_style", "deployment_step", "client_preference", "past_failure", "successful_workflow", "reusable_decision"}
    return normalized if normalized in allowed else "reusable_decision"


def _default_enabled(key: str) -> bool:
    raw = str(config_value("friday_gateway_enabled_connectors", "web,desktop,android,browser_extension,github,gmail") or "")
    return key in {_connector_key(item) for item in raw.split(",") if item.strip()}


def _env_configured(name: str) -> bool:
    value = os.getenv(name, "")
    return bool(value and not value.lower().startswith(("your_", "replace_", "changeme", "sk-your", "placeholder")))


def _safe(fn: Any, default: Any) -> Any:
    try:
        return fn()
    except Exception:
        return default


def _clean(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _limit(value: int, maximum: int) -> int:
    return max(1, min(maximum, int(value or 50)))


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, default=str)


def _json_loads(value: str, default: Any) -> Any:
    try:
        return json.loads(value or "")
    except Exception:
        return default


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds")
