"""Measure agent output quality so Friday can route work to the right specialist."""

from __future__ import annotations

import datetime as dt
import json
import sqlite3
import threading
from pathlib import Path
from typing import Any

from core.config import DATA_DIR, ensure_runtime_dirs

DB_PATH = DATA_DIR / "agent_quality_manager.sqlite3"
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
            CREATE TABLE IF NOT EXISTS agent_quality_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                agent_id TEXT NOT NULL,
                task_id INTEGER,
                task_type TEXT NOT NULL,
                accuracy REAL NOT NULL,
                usefulness REAL NOT NULL,
                speed REAL NOT NULL,
                evidence REAL NOT NULL,
                mistakes REAL NOT NULL,
                fixed_by_agent TEXT NOT NULL,
                score REAL NOT NULL,
                notes TEXT NOT NULL,
                metadata_json TEXT NOT NULL
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_agent_quality_agent ON agent_quality_events(agent_id, task_type, timestamp)")


def record_evaluation(
    agent_id: str,
    *,
    task_id: int | None = None,
    task_type: str = "",
    accuracy: float = 0.7,
    usefulness: float = 0.7,
    speed: float = 0.7,
    evidence: float = 0.7,
    mistakes: float = 0.0,
    fixed_by_agent: str = "",
    notes: str = "",
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    init_db()
    score = _score(accuracy, usefulness, speed, evidence, mistakes, fixed_by_agent)
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            """
            INSERT INTO agent_quality_events(timestamp, agent_id, task_id, task_type, accuracy, usefulness, speed, evidence, mistakes, fixed_by_agent, score, notes, metadata_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                _now(),
                _agent(agent_id),
                int(task_id) if task_id else None,
                _clean(task_type)[:120] or "general",
                _clamp(accuracy),
                _clamp(usefulness),
                _clamp(speed),
                _clamp(evidence),
                _clamp(mistakes),
                _agent(fixed_by_agent),
                score,
                _clean(notes)[:2000],
                _json_dumps(metadata or {}),
            ),
        )
        row = conn.execute("SELECT * FROM agent_quality_events WHERE id=?", (int(cursor.lastrowid),)).fetchone()
    return _row(row)


def record_task_result(task: dict[str, Any], result: dict[str, Any], *, duration_ms: float = 0.0, contract_satisfied: bool = True) -> dict[str, Any]:
    summary = _clean(result.get("summary") or result.get("output") or "")
    evidence_score = 0.8 if result.get("contract", {}).get("satisfied") or contract_satisfied else 0.35
    if any(term in summary.lower() for term in ("could not", "failed", "blocked", "unverified")):
        evidence_score = min(evidence_score, 0.45)
    speed_score = _speed_score(duration_ms)
    task_type = _infer_task_type(f"{task.get('title', '')} {task.get('description', '')}")
    return record_evaluation(
        str(result.get("agent_id") or task.get("agent_id") or ""),
        task_id=int(task.get("id") or 0) or None,
        task_type=task_type,
        accuracy=0.85 if contract_satisfied else 0.35,
        usefulness=0.8 if summary else 0.25,
        speed=speed_score,
        evidence=evidence_score,
        mistakes=0.0 if contract_satisfied else 0.65,
        notes=summary[:1000],
        metadata={"duration_ms": duration_ms, "contract_satisfied": contract_satisfied, "topics": result.get("topics") or []},
    )


def record_fix(agent_id: str, fixed_by_agent: str, *, task_id: int | None = None, reason: str = "") -> dict[str, Any]:
    return record_evaluation(agent_id, task_id=task_id, task_type="repair", accuracy=0.35, usefulness=0.4, speed=0.5, evidence=0.4, mistakes=0.7, fixed_by_agent=fixed_by_agent, notes=reason)


def leaderboard(task_type: str = "", limit: int = 20) -> list[dict[str, Any]]:
    init_db()
    where = ""
    params: list[Any] = []
    if task_type:
        where = "WHERE task_type=?"
        params.append(_clean(task_type)[:120])
    params.append(max(1, min(100, int(limit or 20))))
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            f"""
            SELECT agent_id, task_type, COUNT(*) AS samples, AVG(score) AS avg_score, AVG(accuracy) AS accuracy,
                   AVG(usefulness) AS usefulness, AVG(speed) AS speed, AVG(evidence) AS evidence,
                   AVG(mistakes) AS mistakes, SUM(CASE WHEN fixed_by_agent!='' THEN 1 ELSE 0 END) AS fixed_count
            FROM agent_quality_events {where}
            GROUP BY agent_id, task_type
            ORDER BY avg_score DESC, samples DESC
            LIMIT ?
            """,
            params,
        ).fetchall()
    return [_summary_row(row) for row in rows]


def best_agent(task_type: str = "") -> dict[str, Any] | None:
    rows = leaderboard(task_type=task_type, limit=1)
    return rows[0] if rows else None


def recent(limit: int = 20) -> list[dict[str, Any]]:
    init_db()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM agent_quality_events ORDER BY id DESC LIMIT ?", (max(1, min(100, int(limit or 20))),)).fetchall()
    return [_row(row) for row in rows]


def status() -> dict[str, Any]:
    leaders = leaderboard(limit=10)
    return {"leaderboard": leaders, "recent": recent(limit=8), "summary": f"{len(leaders)} agent quality profile(s) learned."}


def wipe_all() -> None:
    init_db()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.execute("DELETE FROM agent_quality_events")


def _score(accuracy: float, usefulness: float, speed: float, evidence: float, mistakes: float, fixed_by_agent: str) -> float:
    value = _clamp(accuracy) * 0.32 + _clamp(usefulness) * 0.25 + _clamp(speed) * 0.15 + _clamp(evidence) * 0.22 - _clamp(mistakes) * 0.22
    if fixed_by_agent:
        value -= 0.12
    return round(max(0.0, min(1.0, value)), 4)


def _speed_score(duration_ms: float) -> float:
    try:
        value = float(duration_ms)
    except Exception:
        return 0.65
    if value <= 0:
        return 0.65
    if value < 5000:
        return 0.95
    if value < 30000:
        return 0.75
    if value < 120000:
        return 0.55
    return 0.35


def _infer_task_type(text: str) -> str:
    lowered = text.lower()
    for name, words in {
        "coding": ("code", "implement", "bug", "test", "refactor"),
        "research": ("research", "find", "summarize", "source"),
        "design": ("design", "ui", "ux", "figma"),
        "security": ("security", "vulnerability", "scan", "harden"),
        "deployment": ("deploy", "release", "server", "render", "vercel"),
    }.items():
        if any(word in lowered for word in words):
            return name
    return "general"


def _row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "timestamp": str(row["timestamp"]),
        "agent_id": str(row["agent_id"]),
        "task_id": int(row["task_id"]) if row["task_id"] is not None else None,
        "task_type": str(row["task_type"]),
        "accuracy": float(row["accuracy"]),
        "usefulness": float(row["usefulness"]),
        "speed": float(row["speed"]),
        "evidence": float(row["evidence"]),
        "mistakes": float(row["mistakes"]),
        "fixed_by_agent": str(row["fixed_by_agent"]),
        "score": float(row["score"]),
        "notes": str(row["notes"]),
        "metadata": _json_loads(row["metadata_json"], {}),
    }


def _summary_row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "agent_id": str(row["agent_id"]),
        "task_type": str(row["task_type"]),
        "samples": int(row["samples"]),
        "avg_score": round(float(row["avg_score"] or 0.0), 4),
        "accuracy": round(float(row["accuracy"] or 0.0), 4),
        "usefulness": round(float(row["usefulness"] or 0.0), 4),
        "speed": round(float(row["speed"] or 0.0), 4),
        "evidence": round(float(row["evidence"] or 0.0), 4),
        "mistakes": round(float(row["mistakes"] or 0.0), 4),
        "fixed_count": int(row["fixed_count"] or 0),
    }


def _agent(value: Any) -> str:
    return _clean(value).lower().replace("-", "_").replace(" ", "_")[:120]


def _clamp(value: Any) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except Exception:
        return 0.0


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
