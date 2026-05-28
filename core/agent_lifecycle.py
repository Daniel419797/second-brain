"""Dynamic hiring, retirement, promotion, and role rewriting for Friday agents."""

from __future__ import annotations

import datetime as dt
import json
import re
import sqlite3
import threading
from pathlib import Path
from typing import Any

from core.config import DATA_DIR, ensure_runtime_dirs

DB_PATH = DATA_DIR / "agent_lifecycle.sqlite3"
_LOCK = threading.Lock()
ACTIVE_STATUSES = {"active", "promoted"}


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
            CREATE TABLE IF NOT EXISTS dynamic_agents (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                purpose TEXT NOT NULL,
                keywords_json TEXT NOT NULL,
                status TEXT NOT NULL,
                level INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                metadata_json TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS lifecycle_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                agent_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                summary TEXT NOT NULL,
                metadata_json TEXT NOT NULL
            )
            """
        )


def hire_specialist(name: str, purpose: str, *, keywords: list[str] | str | None = None, agent_id: str = "", metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    init_db()
    normalized = _agent_id(agent_id or name)
    if not normalized:
        raise ValueError("agent name is required")
    now = _now()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute(
            """
            INSERT INTO dynamic_agents(id, name, purpose, keywords_json, status, level, created_at, updated_at, metadata_json)
            VALUES (?, ?, ?, ?, 'active', 1, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                name=excluded.name, purpose=excluded.purpose, keywords_json=excluded.keywords_json,
                status='active', updated_at=excluded.updated_at, metadata_json=excluded.metadata_json
            """,
            (normalized, _clean(name)[:200], _clean(purpose)[:1000], _json_dumps(_keywords(keywords or purpose)), now, now, _json_dumps(metadata or {})),
        )
        row = conn.execute("SELECT * FROM dynamic_agents WHERE id=?", (normalized,)).fetchone()
    item = _row(row)
    _event(item["id"], "hired", f"Hired {item['name']}: {item['purpose']}", metadata or {})
    return item


def create_specialist(name: str, purpose: str, *, keywords: list[str] | str | None = None, agent_id: str = "", metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    return hire_specialist(name, purpose, keywords=keywords, agent_id=agent_id, metadata=metadata)


def retire_agent(agent_id: str, *, reason: str = "") -> dict[str, Any]:
    return _set_status(agent_id, "retired", "retired", reason)


def promote_agent(agent_id: str, *, reason: str = "") -> dict[str, Any]:
    init_db()
    normalized = _agent_id(agent_id)
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("UPDATE dynamic_agents SET status='promoted', level=level+1, updated_at=? WHERE id=?", (_now(), normalized))
        row = conn.execute("SELECT * FROM dynamic_agents WHERE id=?", (normalized,)).fetchone()
    item = _row(row) if row else {}
    if item:
        _event(normalized, "promoted", reason or f"Promoted {normalized}.", {"level": item["level"]})
    return item or {"ok": False, "summary": "Agent not found."}


def rewrite_role(agent_id: str, *, purpose: str = "", keywords: list[str] | str | None = None, name: str = "") -> dict[str, Any]:
    init_db()
    normalized = _agent_id(agent_id)
    current = get_agent(normalized)
    if not current:
        return {"ok": False, "summary": "Agent not found."}
    next_name = _clean(name) or current["name"]
    next_purpose = _clean(purpose) or current["purpose"]
    next_keywords = _keywords(keywords or next_purpose)
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("UPDATE dynamic_agents SET name=?, purpose=?, keywords_json=?, updated_at=? WHERE id=?", (next_name, next_purpose, _json_dumps(next_keywords), _now(), normalized))
        row = conn.execute("SELECT * FROM dynamic_agents WHERE id=?", (normalized,)).fetchone()
    item = _row(row)
    _event(normalized, "rewritten", f"Updated role for {item['name']}.", {"purpose": next_purpose, "keywords": next_keywords})
    return item


def get_agent(agent_id: str) -> dict[str, Any] | None:
    init_db()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM dynamic_agents WHERE id=?", (_agent_id(agent_id),)).fetchone()
    return _row(row) if row else None


def active_agents() -> list[dict[str, Any]]:
    return list_agents(statuses=ACTIVE_STATUSES)


def list_agents(statuses: set[str] | None = None, limit: int = 100) -> list[dict[str, Any]]:
    init_db()
    params: list[Any] = []
    where = ""
    if statuses:
        placeholders = ",".join("?" for _ in statuses)
        where = f"WHERE status IN ({placeholders})"
        params.extend(sorted(statuses))
    params.append(max(1, min(300, int(limit or 100))))
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(f"SELECT * FROM dynamic_agents {where} ORDER BY level DESC, updated_at DESC LIMIT ?", params).fetchall()
    return [_row(row) for row in rows]


def status() -> dict[str, Any]:
    agents = list_agents()
    active = [item for item in agents if item["status"] in ACTIVE_STATUSES]
    return {"agents": agents, "active": active, "summary": f"{len(active)} dynamic agent(s) active, {len(agents)} total lifecycle record(s)."}


def wipe_all() -> None:
    init_db()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.execute("DELETE FROM dynamic_agents")
        conn.execute("DELETE FROM lifecycle_events")


def _set_status(agent_id: str, status: str, event: str, reason: str) -> dict[str, Any]:
    init_db()
    normalized = _agent_id(agent_id)
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("UPDATE dynamic_agents SET status=?, updated_at=? WHERE id=?", (status, _now(), normalized))
        row = conn.execute("SELECT * FROM dynamic_agents WHERE id=?", (normalized,)).fetchone()
    item = _row(row) if row else {}
    if item:
        _event(normalized, event, reason or f"{event.title()} {normalized}.", {})
    return item or {"ok": False, "summary": "Agent not found."}


def _event(agent_id: str, event_type: str, summary: str, metadata: dict[str, Any]) -> None:
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.execute(
            "INSERT INTO lifecycle_events(timestamp, agent_id, event_type, summary, metadata_json) VALUES (?, ?, ?, ?, ?)",
            (_now(), agent_id, event_type, _clean(summary)[:1000], _json_dumps(metadata)),
        )


def _row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": str(row["id"]),
        "name": str(row["name"]),
        "purpose": str(row["purpose"]),
        "keywords": _json_loads(row["keywords_json"], []),
        "status": str(row["status"]),
        "level": int(row["level"]),
        "created_at": str(row["created_at"]),
        "updated_at": str(row["updated_at"]),
        "metadata": _json_loads(row["metadata_json"], {}),
    }


def _keywords(value: list[str] | str | None) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        words = re.findall(r"[a-zA-Z][a-zA-Z0-9_+-]{2,}", value.lower())
        return sorted(set(words))[:20]
    return sorted({_clean(item).lower() for item in value if _clean(item)})[:20]


def _agent_id(value: Any) -> str:
    return re.sub(r"[^a-z0-9_]+", "_", _clean(value).lower()).strip("_")[:80]


def _clean(value: Any) -> str:
    return " ".join(str(value or "").replace("\x00", " ").strip().split())


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, default=str)


def _json_loads(value: str, default: Any) -> Any:
    try:
        return json.loads(value or "")
    except Exception:
        return default


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds")
