"""Lightweight continuous world model for Friday."""

from __future__ import annotations

import datetime as dt
import json
import re
import sqlite3
import threading
from pathlib import Path
from typing import Any

from core import cognitive_state, desktop_tasks, episodic_store, pc_awareness, task_queue, visual_monitor
from core.config import DATA_DIR, config_value, ensure_runtime_dirs

DB_PATH = DATA_DIR / "world_model.sqlite3"
_LOCK = threading.Lock()


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
            CREATE TABLE IF NOT EXISTS world_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                source TEXT NOT NULL,
                summary TEXT NOT NULL,
                active_app TEXT NOT NULL,
                active_window TEXT NOT NULL,
                visible_state_json TEXT NOT NULL,
                user_state_json TEXT NOT NULL,
                confidence REAL NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS world_entities (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                entity_type TEXT NOT NULL,
                name TEXT NOT NULL,
                last_seen_at TEXT NOT NULL,
                state_json TEXT NOT NULL,
                confidence REAL NOT NULL,
                UNIQUE(entity_type, name)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS world_expectations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                goal_id TEXT NOT NULL,
                expected_observation TEXT NOT NULL,
                actual_observation TEXT NOT NULL,
                status TEXT NOT NULL,
                confidence REAL NOT NULL
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_world_snapshots_time ON world_snapshots(timestamp)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_world_expectations_status ON world_expectations(status, expires_at)")


def capture_snapshot(source: str = "auto", *, summary: str = "", visible_state: dict[str, Any] | None = None, confidence: float = 0.6) -> dict[str, Any]:
    init_db()
    active_window = _active_window()
    latest_visual = visual_monitor.latest_event() or {}
    latest_desktop = desktop_tasks.latest_session() or {}
    pc_state = _pc_awareness_context()
    tasks = task_queue.counts()
    recent_event = _recent_event_summary()
    state = {
        "visual": _compact_dict(latest_visual),
        "desktop_task": _compact_dict(latest_desktop),
        "pc_awareness": _compact_dict(pc_state, limit=1200),
        "tasks": tasks,
    }
    if visible_state:
        state.update(visible_state)
    summary_text = summary or _build_summary(active_window, latest_visual, latest_desktop, tasks, recent_event)
    snapshot = cognitive_state.CognitiveSnapshot(
        timestamp=cognitive_state.now_iso(),
        source=_clean(source) or "auto",
        summary=summary_text,
        active_app=_infer_app(active_window),
        active_window=active_window,
        visible_state=state,
        user_state={"recent_event": recent_event},
        confidence=cognitive_state.clamp01(confidence),
    )
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        cursor = conn.execute(
            """
            INSERT INTO world_snapshots (
                timestamp, source, summary, active_app, active_window,
                visible_state_json, user_state_json, confidence
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                snapshot.timestamp,
                snapshot.source,
                snapshot.summary,
                snapshot.active_app,
                snapshot.active_window,
                cognitive_state.to_json(snapshot.visible_state),
                cognitive_state.to_json(snapshot.user_state),
                snapshot.confidence,
            ),
        )
        snapshot_id = int(cursor.lastrowid)
    if active_window:
        upsert_entity("window", active_window, {"active_app": snapshot.active_app}, confidence=0.7)
    for app in (pc_state.get("running_apps") or [])[:12]:
        if app.get("name"):
            upsert_entity("running_app", str(app["name"]), {"pid": app.get("pid"), "exe": app.get("exe")}, confidence=0.65)
    for app in (pc_state.get("desktop_apps") or [])[:12]:
        if app.get("name"):
            upsert_entity("desktop_app", str(app["name"]), {"path": app.get("path"), "source": app.get("source")}, confidence=0.7)
    item = cognitive_state.to_dict(snapshot)
    item["id"] = snapshot_id
    return item


def recent_snapshots(limit: int = 20) -> list[dict[str, Any]]:
    init_db()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM world_snapshots ORDER BY id DESC LIMIT ?",
            (max(1, min(200, int(limit))),),
        ).fetchall()
    return [_snapshot_from_row(row) for row in rows]


def latest_snapshot() -> dict[str, Any] | None:
    items = recent_snapshots(1)
    return items[0] if items else None


def current_context() -> dict[str, Any]:
    snapshot = latest_snapshot()
    if not snapshot:
        snapshot = capture_snapshot("current_context")
    open_expectations = expectations(status="open", limit=8)
    return {
        "snapshot": snapshot,
        "open_expectations": open_expectations,
        "entities": recent_entities(limit=8),
        "summary": _context_sentence(snapshot, open_expectations),
    }


def upsert_entity(entity_type: str, name: str, state: dict[str, Any] | None = None, confidence: float = 0.5) -> dict[str, Any]:
    init_db()
    now = cognitive_state.now_iso()
    normalized_type = _clean(entity_type) or "unknown"
    normalized_name = _clean(name) or "unnamed"
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        cursor = conn.execute(
            """
            INSERT INTO world_entities(entity_type, name, last_seen_at, state_json, confidence)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(entity_type, name)
            DO UPDATE SET last_seen_at=excluded.last_seen_at, state_json=excluded.state_json, confidence=excluded.confidence
            """,
            (
                normalized_type,
                normalized_name,
                now,
                cognitive_state.to_json(state or {}),
                cognitive_state.clamp01(confidence),
            ),
        )
        row_id = int(cursor.lastrowid or 0)
    return {"id": row_id, "entity_type": normalized_type, "name": normalized_name, "last_seen_at": now, "state": state or {}, "confidence": cognitive_state.clamp01(confidence)}


def recent_entities(limit: int = 20) -> list[dict[str, Any]]:
    init_db()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM world_entities ORDER BY last_seen_at DESC, id DESC LIMIT ?",
            (max(1, min(200, int(limit))),),
        ).fetchall()
    return [_entity_from_row(row) for row in rows]


def create_expectation(goal_id: str | int, expected_observation: str, ttl_seconds: float = 120.0, confidence: float = 0.6) -> int:
    init_db()
    expected = _clean(expected_observation)
    if not expected:
        raise ValueError("Expected observation is empty.")
    created = dt.datetime.now(dt.timezone.utc).astimezone()
    expires = created + dt.timedelta(seconds=max(1.0, float(ttl_seconds)))
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        cursor = conn.execute(
            """
            INSERT INTO world_expectations(created_at, expires_at, goal_id, expected_observation, actual_observation, status, confidence)
            VALUES (?, ?, ?, ?, '', 'open', ?)
            """,
            (created.isoformat(timespec="seconds"), expires.isoformat(timespec="seconds"), str(goal_id), expected, cognitive_state.clamp01(confidence)),
        )
        return int(cursor.lastrowid)


def resolve_expectations(observation_text: str) -> list[dict[str, Any]]:
    init_db()
    observed = _clean(observation_text)
    if not observed:
        return []
    now = dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds")
    resolved: list[dict[str, Any]] = []
    for item in expectations(status="open", limit=50):
        status = "met" if _matches(item["expected_observation"], observed) else "expired" if item["expires_at"] < now else "open"
        if status == "open":
            continue
        with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
            conn.execute(
                "UPDATE world_expectations SET status=?, actual_observation=? WHERE id=?",
                (status, observed, int(item["id"])),
            )
        item["status"] = status
        item["actual_observation"] = observed
        resolved.append(item)
    return resolved


def expectations(status: str = "", limit: int = 20) -> list[dict[str, Any]]:
    init_db()
    where = ""
    params: list[Any] = []
    if status:
        where = "WHERE status=?"
        params.append(status)
    params.append(max(1, min(200, int(limit))))
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            f"SELECT * FROM world_expectations {where} ORDER BY id DESC LIMIT ?",
            params,
        ).fetchall()
    return [_expectation_from_row(row) for row in rows]


def planner_context() -> str:
    context = current_context()
    snapshot = context.get("snapshot") or {}
    expectations_text = "; ".join(item["expected_observation"] for item in context.get("open_expectations", [])[:3])
    pc_summary = ((snapshot.get("visible_state") or {}).get("pc_awareness") or {}).get("summary") or ""
    pc_clause = f" PC awareness: {pc_summary}" if pc_summary else ""
    return f"World context: {snapshot.get('summary', 'No current snapshot.')}{pc_clause} Open expectations: {expectations_text or 'none'}."


def wipe_all() -> None:
    init_db()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.execute("DELETE FROM world_expectations")
        conn.execute("DELETE FROM world_entities")
        conn.execute("DELETE FROM world_snapshots")


def _active_window() -> str:
    try:
        from tools import pc_control

        result = pc_control.execute({"action": "active_window"})
        return _clean(str(result or ""))[:300]
    except Exception:
        return ""


def _recent_event_summary() -> str:
    try:
        events = episodic_store.query_events(agent_id="jarvis", limit=1)
        if not events:
            return ""
        event = events[0]
        return f"{event.get('action_type')}: {_short(event.get('outputs'))}"
    except Exception:
        return ""


def _build_summary(active_window: str, latest_visual: dict[str, Any], latest_desktop: dict[str, Any], tasks: dict[str, int], recent_event: str) -> str:
    parts = []
    if active_window:
        parts.append(f"active window is {active_window}")
    if latest_visual:
        parts.append(f"latest visual event: {latest_visual.get('summary') or latest_visual.get('event_type')}")
    if latest_desktop:
        parts.append(f"desktop session #{latest_desktop.get('id')} is {latest_desktop.get('status')}")
    parts.append(f"tasks: {tasks.get('active', 0)} active, {tasks.get('pending', 0)} pending")
    if recent_event:
        parts.append(f"recent event: {recent_event}")
    try:
        pc_state = pc_awareness.snapshot()
        stats = pc_state.get("stats") or {}
        parts.append(
            f"PC awareness sees {stats.get('running_apps', 0)} running app entries and {stats.get('desktop_apps', 0)} Desktop/Home-screen shortcuts"
        )
    except Exception:
        pass
    return "; ".join(parts)


def _context_sentence(snapshot: dict[str, Any], open_expectations: list[dict[str, Any]]) -> str:
    if not snapshot:
        return "I do not have a current world snapshot yet."
    extra = f" I am watching for {len(open_expectations)} expected outcome{'s' if len(open_expectations) != 1 else ''}." if open_expectations else ""
    return f"{snapshot.get('summary') or 'I have a basic current context.'}{extra}"


def _snapshot_from_row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "timestamp": str(row["timestamp"]),
        "source": str(row["source"]),
        "summary": str(row["summary"]),
        "active_app": str(row["active_app"]),
        "active_window": str(row["active_window"]),
        "visible_state": cognitive_state.from_json(row["visible_state_json"]),
        "user_state": cognitive_state.from_json(row["user_state_json"]),
        "confidence": float(row["confidence"]),
    }


def _entity_from_row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "entity_type": str(row["entity_type"]),
        "name": str(row["name"]),
        "last_seen_at": str(row["last_seen_at"]),
        "state": cognitive_state.from_json(row["state_json"]),
        "confidence": float(row["confidence"]),
    }


def _expectation_from_row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "created_at": str(row["created_at"]),
        "expires_at": str(row["expires_at"]),
        "goal_id": str(row["goal_id"]),
        "expected_observation": str(row["expected_observation"]),
        "actual_observation": str(row["actual_observation"]),
        "status": str(row["status"]),
        "confidence": float(row["confidence"]),
    }


def _matches(expected: str, observed: str) -> bool:
    expected_terms = {word for word in _words(expected) if len(word) >= 4}
    observed_terms = set(_words(observed))
    if not expected_terms:
        return False
    overlap = len(expected_terms & observed_terms)
    return overlap >= max(1, min(3, len(expected_terms)))


def _infer_app(active_window: str) -> str:
    text = active_window.lower()
    known = ["chrome", "gmail", "calculator", "notepad", "visual studio code", "code", "camera", "explorer", "discord", "whatsapp", "figma", "photoshop", "excel", "word", "powerpoint"]
    for item in known:
        if item in text:
            return "vscode" if item in {"code", "visual studio code"} else item
    return ""


def _pc_awareness_context() -> dict[str, Any]:
    if not bool(config_value("world_model_pc_awareness_enabled", True)):
        return {}
    try:
        return pc_awareness.planner_context()
    except Exception:
        return {}


def _compact_dict(value: dict[str, Any], limit: int = 600) -> dict[str, Any]:
    text = json.dumps(value or {}, ensure_ascii=True, default=str)
    if len(text) <= limit:
        return value or {}
    return {"summary": text[:limit]}


def _short(value: Any, limit: int = 160) -> str:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=True, default=str)
    text = _clean(text)
    return text if len(text) <= limit else text[: limit - 3] + "..."


def _words(text: str) -> list[str]:
    return [part for part in re.split(r"[^a-z0-9]+", str(text).lower()) if part]


def _clean(value: Any) -> str:
    return " ".join(str(value or "").strip().split())
