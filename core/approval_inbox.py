"""Unified inbox for human decisions Friday should not make alone."""

from __future__ import annotations

import datetime as dt
import json
import sqlite3
import threading
from pathlib import Path
from typing import Any

from core.config import DATA_DIR, ensure_runtime_dirs

DB_PATH = DATA_DIR / "approval_inbox.sqlite3"
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
            CREATE TABLE IF NOT EXISTS generic_approvals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                kind TEXT NOT NULL,
                title TEXT NOT NULL,
                summary TEXT NOT NULL,
                source TEXT NOT NULL,
                status TEXT NOT NULL,
                payload_json TEXT NOT NULL
            )
            """
        )


def create(
    *,
    kind: str,
    title: str,
    summary: str,
    source: str = "friday",
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create a simple approval item for modules without their own approval table."""

    init_db()
    now = _now()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            """
            INSERT INTO generic_approvals(timestamp, updated_at, kind, title, summary, source, status, payload_json)
            VALUES (?, ?, ?, ?, ?, ?, 'pending', ?)
            """,
            (now, now, _clean(kind) or "approval", _clean(title)[:300] or "Approval needed", _clean(summary)[:2000], _clean(source) or "friday", _json_dumps(payload or {})),
        )
        row = conn.execute("SELECT * FROM generic_approvals WHERE id=?", (int(cursor.lastrowid),)).fetchone()
    return _generic_row(row)


def items(limit: int = 50) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    results.extend(_generic_waiting(limit))
    results.extend(_blocked_tasks(limit))
    results.extend(_blackboard_waiting(limit))
    results.extend(_permission_waiting(limit))
    results.extend(_self_update_waiting(limit))
    results.extend(_desktop_waiting(limit))
    results.extend(_mission_waiting(limit))
    results.sort(key=lambda item: str(item.get("updated_at") or item.get("timestamp") or ""), reverse=True)
    return results[: max(1, min(200, int(limit)))]


def summary(limit: int = 12) -> dict[str, Any]:
    pending = items(limit=max(limit, 50))
    by_kind: dict[str, int] = {}
    for item in pending:
        by_kind[str(item["kind"])] = by_kind.get(str(item["kind"]), 0) + 1
    return {
        "count": len(pending),
        "by_kind": by_kind,
        "items": pending[:limit],
        "voice_summary": voice_summary(pending),
    }


def voice_summary(pending: list[dict[str, Any]] | None = None) -> str:
    pending = pending if pending is not None else items(limit=50)
    if not pending:
        return "You have no decisions waiting."
    by_kind: dict[str, int] = {}
    for item in pending:
        by_kind[str(item["kind"])] = by_kind.get(str(item["kind"]), 0) + 1
    parts = ", ".join(f"{count} {kind.replace('_', ' ')}" for kind, count in sorted(by_kind.items()))
    return f"You have {len(pending)} decision{'s' if len(pending) != 1 else ''} waiting: {parts}."


def resolve(kind: str, item_id: int, note: str = "") -> dict[str, Any]:
    normalized = str(kind or "").strip().lower().replace(" ", "_")
    if normalized in {"blackboard", "agent_question", "blocker"}:
        from core import agent_blackboard

        item = agent_blackboard.resolve_item(item_id, note=note)
        return {"resolved": bool(item), "item": item}
    if normalized == "task":
        from core import task_queue

        task = task_queue.get_task(item_id)
        if task and task.get("status") == "blocked":
            task_queue.update_status(item_id, "pending")
            task_queue.post_message(item_id, "approval", note or "User released blocked task.")
            return {"resolved": True, "item": task_queue.get_task(item_id)}
    if normalized in {"privacy", "autonomy_blocker", "approval", "generic", "gateway_event"}:
        init_db()
        with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
            conn.row_factory = sqlite3.Row
            conn.execute("UPDATE generic_approvals SET status='resolved', updated_at=?, summary=summary || ? WHERE id=?", (_now(), f" Resolved: {_clean(note)}" if note else " Resolved.", int(item_id)))
            row = conn.execute("SELECT * FROM generic_approvals WHERE id=?", (int(item_id),)).fetchone()
        return {"resolved": bool(row), "item": _generic_row(row) if row else None}
    return {"resolved": False, "item": None}


def _generic_waiting(limit: int) -> list[dict[str, Any]]:
    try:
        init_db()
        with sqlite3.connect(DB_PATH, timeout=10) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("SELECT * FROM generic_approvals WHERE status='pending' ORDER BY id DESC LIMIT ?", (max(1, min(200, int(limit))),)).fetchall()
    except Exception:
        return []
    return [_generic_row(row) for row in rows]


def _generic_row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "kind": str(row["kind"]),
        "id": int(row["id"]),
        "title": str(row["title"]),
        "summary": str(row["summary"]),
        "status": str(row["status"]),
        "agent_id": "friday",
        "task_id": None,
        "updated_at": str(row["updated_at"]),
        "timestamp": str(row["timestamp"]),
        "action_hint": "Approve, resolve, or change permissions in the dashboard.",
        "metadata": {"source": str(row["source"]), "payload": _json_loads(row["payload_json"], {})},
    }


def _blocked_tasks(limit: int) -> list[dict[str, Any]]:
    try:
        from core import task_queue

        tasks = task_queue.list_tasks(status="blocked", limit=limit)
    except Exception:
        return []
    return [
        {
            "kind": "blocked_task",
            "id": int(task["id"]),
            "title": task["title"],
            "summary": f"{task['agent_id']} is blocked on {task['title']}.",
            "status": task["status"],
            "agent_id": task["agent_id"],
            "task_id": task["id"],
            "updated_at": task.get("updated_at", ""),
            "action_hint": f"Review task #{task['id']} and approve, reassign, or cancel it.",
            "metadata": {"task": task},
        }
        for task in tasks
    ]


def _blackboard_waiting(limit: int) -> list[dict[str, Any]]:
    try:
        from core import agent_blackboard

        blackboard = agent_blackboard.summary(limit=limit)
    except Exception:
        return []
    waiting = [*(blackboard.get("questions") or []), *(blackboard.get("blockers") or [])]
    items: list[dict[str, Any]] = []
    seen: set[int] = set()
    for entry in waiting:
        entry_id = int(entry.get("id") or 0)
        if entry_id in seen:
            continue
        seen.add(entry_id)
        items.append(
            {
                "kind": "agent_question" if entry.get("item_type") == "question" else "blocker",
                "id": entry_id,
                "title": entry.get("title", ""),
                "summary": entry.get("content", ""),
                "status": entry.get("status", ""),
                "agent_id": entry.get("agent_id", ""),
                "task_id": entry.get("task_id"),
                "updated_at": entry.get("updated_at", ""),
                "action_hint": "Answer, route, or resolve this blackboard item.",
                "metadata": {"blackboard": entry},
            }
        )
    return items


def _permission_waiting(limit: int) -> list[dict[str, Any]]:
    try:
        from core import permissions

        events = permissions.recent_events(limit=limit)
    except Exception:
        return []
    return [
        {
            "kind": "permission_decision",
            "id": int(event["id"]),
            "title": event["key"],
            "summary": f"{event['decision']} - {event['target'] or event['action']}",
            "status": event["decision"],
            "agent_id": "friday",
            "task_id": None,
            "updated_at": event["timestamp"],
            "action_hint": "Change this rule in Safety Center if Friday should behave differently next time.",
            "metadata": {"permission_event": event},
        }
        for event in events
        if event.get("decision") in {"cancelled", "blocked"}
    ]


def _self_update_waiting(limit: int) -> list[dict[str, Any]]:
    try:
        from core import self_update

        updates = self_update.list_updates(limit=limit)
    except Exception:
        return []
    return [
        {
            "kind": "self_update_proposal",
            "id": int(update["id"]),
            "title": f"Self-update #{update['id']}",
            "summary": update["request"],
            "status": update["status"],
            "agent_id": "friday",
            "task_id": update.get("task_id"),
            "updated_at": update.get("updated_at", ""),
            "action_hint": update.get("approval_phrase") or "Review and approve/cancel this self-update.",
            "metadata": {"self_update": update},
        }
        for update in updates
        if update.get("status") in {"proposed", "approved", "failed"}
    ]


def _desktop_waiting(limit: int) -> list[dict[str, Any]]:
    try:
        from core import desktop_tasks

        sessions = desktop_tasks.list_sessions(limit=limit)
    except Exception:
        return []
    return [
        {
            "kind": "desktop_confirmation",
            "id": int(session["id"]),
            "title": f"Desktop session #{session['id']}",
            "summary": session.get("pending_reason") or session.get("goal") or "",
            "status": session.get("status", ""),
            "agent_id": "friday",
            "task_id": None,
            "updated_at": session.get("updated_at", ""),
            "action_hint": "Confirm, pause, resume, or cancel this desktop session.",
            "metadata": {"desktop_session": session},
        }
        for session in sessions
        if session.get("status") == "waiting_confirmation"
    ]


def _mission_waiting(limit: int) -> list[dict[str, Any]]:
    try:
        from core import mission_control

        approvals = mission_control.approvals(status="pending", limit=limit)
        blockers = mission_control.blockers(status="open", limit=limit)
    except Exception:
        return []
    items = [
        {
            "kind": "mission_approval",
            "id": int(item["id"]),
            "title": item.get("title", ""),
            "summary": item.get("summary", ""),
            "status": item.get("status", ""),
            "agent_id": "friday",
            "task_id": None,
            "updated_at": item.get("timestamp", ""),
            "action_hint": f"Approve mission #{item.get('mission_id')} {item.get('kind')}.",
            "metadata": {"mission_approval": item},
        }
        for item in approvals
    ]
    items.extend(
        {
            "kind": "mission_blocker",
            "id": int(item["id"]),
            "title": item.get("title", ""),
            "summary": item.get("summary", ""),
            "status": item.get("status", ""),
            "agent_id": "friday",
            "task_id": None,
            "updated_at": item.get("timestamp", ""),
            "action_hint": f"Resolve mission #{item.get('mission_id')} blocker before final proof.",
            "metadata": {"mission_blocker": item},
        }
        for item in blockers
    )
    return items


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
