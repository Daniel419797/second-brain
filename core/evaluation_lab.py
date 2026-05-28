"""Evaluation telemetry for Friday's reliability and latency."""

from __future__ import annotations

import datetime as dt
import json
import re
import sqlite3
import threading
from pathlib import Path
from typing import Any

from core.config import DATA_DIR, LOG_DIR, ensure_runtime_dirs

DB_PATH = DATA_DIR / "evaluation_lab.sqlite3"
_LOCK = threading.Lock()

CATEGORIES = {
    "stt_mistake",
    "slow_response",
    "failed_tool",
    "task_completed",
    "task_stuck",
    "unsupported_claim",
    "latency",
    "agent_failure",
}


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
            CREATE TABLE IF NOT EXISTS evaluation_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                category TEXT NOT NULL,
                source TEXT NOT NULL,
                summary TEXT NOT NULL,
                severity INTEGER NOT NULL,
                metric_value REAL,
                metadata_json TEXT NOT NULL
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_eval_category ON evaluation_events(category, timestamp)")


def record_event(
    category: str,
    summary: str,
    *,
    source: str = "friday",
    severity: int = 1,
    metric_value: float | None = None,
    metadata: dict[str, Any] | None = None,
) -> int:
    init_db()
    normalized = _normalize_category(category)
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        cursor = conn.execute(
            """
            INSERT INTO evaluation_events(timestamp, category, source, summary, severity, metric_value, metadata_json)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                _now(),
                normalized,
                _clean(source) or "friday",
                _clean(summary)[:1000],
                max(1, min(5, int(severity or 1))),
                float(metric_value) if metric_value is not None else None,
                _json_dumps(metadata or {}),
            ),
        )
        return int(cursor.lastrowid)


def recent_events(category: str = "", limit: int = 80) -> list[dict[str, Any]]:
    init_db()
    where = ""
    params: list[Any] = []
    if category:
        where = "WHERE category = ?"
        params.append(_normalize_category(category))
    params.append(max(1, min(500, int(limit))))
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(f"SELECT * FROM evaluation_events {where} ORDER BY id DESC LIMIT ?", params).fetchall()
    return [_row_to_event(row) for row in rows]


def summary(limit: int = 12) -> dict[str, Any]:
    init_db()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        rows = conn.execute("SELECT category, COUNT(*), AVG(metric_value) FROM evaluation_events GROUP BY category").fetchall()
    counts = {category: 0 for category in sorted(CATEGORIES)}
    averages: dict[str, float] = {}
    for category, count, average in rows:
        counts[str(category)] = int(count)
        if average is not None:
            averages[str(category)] = round(float(average), 2)
    log_latency = _latency_from_logs()
    stuck = _task_stuck_count()
    if stuck:
        counts["task_stuck"] = max(counts.get("task_stuck", 0), stuck)
    return {
        "counts": counts,
        "averages": averages | ({"e2e_latency_ms_from_logs": log_latency} if log_latency else {}),
        "stt": _stt_summary(),
        "tasks": _task_summary(),
        "recent": recent_events(limit=limit),
    }


def record_latency(source: str, milliseconds: float, *, threshold_ms: float = 5000.0, metadata: dict[str, Any] | None = None) -> int:
    category = "slow_response" if milliseconds > threshold_ms else "latency"
    severity = 3 if milliseconds > threshold_ms else 1
    return record_event(
        category,
        f"{source} latency {milliseconds:.0f}ms",
        source=source,
        severity=severity,
        metric_value=float(milliseconds),
        metadata=metadata or {},
    )


def wipe_all() -> None:
    init_db()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.execute("DELETE FROM evaluation_events")


def _stt_summary() -> dict[str, Any]:
    try:
        from core import adaptive_attention

        corrections = [event for event in adaptive_attention.recent_events(limit=100) if event.get("user_corrected")]
        return {"corrections": len(corrections), "recent_corrections": corrections[:5]}
    except Exception:
        return {"corrections": 0, "recent_corrections": []}


def _task_summary() -> dict[str, int]:
    try:
        from core import task_queue

        counts = task_queue.counts()
        return {
            "completed": int(counts.get("done", 0)),
            "failed": int(counts.get("failed", 0)),
            "active": int(counts.get("active", 0)),
            "pending": int(counts.get("pending", 0)),
            "blocked": int(counts.get("blocked", 0)),
        }
    except Exception:
        return {"completed": 0, "failed": 0, "active": 0, "pending": 0, "blocked": 0}


def _task_stuck_count() -> int:
    try:
        from core import task_queue

        active = task_queue.list_tasks(status="active", limit=200)
    except Exception:
        return 0
    cutoff = dt.datetime.now(dt.timezone.utc).astimezone() - dt.timedelta(minutes=30)
    stuck = 0
    for task in active:
        try:
            updated = dt.datetime.fromisoformat(str(task.get("updated_at") or task.get("started_at") or ""))
        except ValueError:
            continue
        if updated < cutoff:
            stuck += 1
    return stuck


def _latency_from_logs() -> float:
    try:
        files = sorted(LOG_DIR.glob("*.log"), key=lambda path: path.stat().st_mtime, reverse=True)[:3]
    except Exception:
        return 0.0
    values: list[int] = []
    for path in files:
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        values.extend(int(match) for match in re.findall(r"\be2e=(\d+)ms\b", text)[-100:])
    if not values:
        return 0.0
    return round(sum(values) / len(values), 2)


def _normalize_category(value: str) -> str:
    category = _clean(value).lower().replace(" ", "_").replace("-", "_")
    return category if category in CATEGORIES else "latency"


def _row_to_event(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "timestamp": str(row["timestamp"]),
        "category": str(row["category"]),
        "source": str(row["source"]),
        "summary": str(row["summary"]),
        "severity": int(row["severity"]),
        "metric_value": row["metric_value"],
        "metadata": _json_loads(row["metadata_json"]),
    }


def _json_dumps(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=True, sort_keys=True, default=str)
    except TypeError:
        return json.dumps(str(value), ensure_ascii=True)


def _json_loads(value: str) -> Any:
    try:
        return json.loads(value or "{}")
    except Exception:
        return {}


def _clean(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds")
