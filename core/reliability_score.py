"""Reliability scoring across STT, tools, tasks, latency, and honesty."""

from __future__ import annotations

import datetime as dt
import json
import sqlite3
import threading
from pathlib import Path
from typing import Any

from core import evaluation_lab, task_queue, trust_proof, voice_reliability
from core.config import DATA_DIR, ensure_runtime_dirs

DB_PATH = DATA_DIR / "reliability_score.sqlite3"
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
            CREATE TABLE IF NOT EXISTS reliability_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                overall INTEGER NOT NULL,
                summary TEXT NOT NULL,
                scores_json TEXT NOT NULL,
                inputs_json TEXT NOT NULL
            )
            """
        )


def snapshot() -> dict[str, Any]:
    init_db()
    evaluation = evaluation_lab.summary(limit=50)
    voice = voice_reliability.summary() if hasattr(voice_reliability, "summary") else {}
    counts = task_queue.counts()
    proofs = trust_proof.summary()
    scores = _scores(evaluation, voice, counts, proofs)
    overall = round(sum(scores.values()) / max(1, len(scores)))
    summary = f"Friday reliability score: {overall}/100. Tool success {scores['tool_success']}/100, STT {scores['stt_accuracy']}/100, honesty {scores['honesty']}/100."
    payload = {"evaluation": evaluation, "voice": voice, "task_counts": counts, "proof_reports": proofs}
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            "INSERT INTO reliability_snapshots(timestamp, overall, summary, scores_json, inputs_json) VALUES (?, ?, ?, ?, ?)",
            (_now(), int(overall), summary, _json_dumps(scores), _json_dumps(payload)),
        )
        row = conn.execute("SELECT * FROM reliability_snapshots WHERE id=?", (int(cursor.lastrowid),)).fetchone()
    return _row(row)


def status() -> dict[str, Any]:
    recent = recent_snapshots(limit=8)
    latest = recent[0] if recent else snapshot()
    return {"latest": latest, "recent": recent, "summary": latest["summary"]}


def recent_snapshots(limit: int = 20) -> list[dict[str, Any]]:
    init_db()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM reliability_snapshots ORDER BY id DESC LIMIT ?", (max(1, min(100, int(limit or 20))),)).fetchall()
    return [_row(row) for row in rows]


def wipe_all() -> None:
    init_db()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.execute("DELETE FROM reliability_snapshots")


def _scores(evaluation: dict[str, Any], voice: dict[str, Any], counts: dict[str, Any], proofs: dict[str, Any]) -> dict[str, int]:
    categories = evaluation.get("counts") or evaluation.get("by_category") or evaluation.get("categories") or {}
    recent = evaluation.get("events") or evaluation.get("recent") or []
    stt_mistakes = _count(categories, "stt_mistake") + _count(categories, "voice_repair")
    failed_tool = _count(categories, "failed_tool") + _count(categories, "agent_failure")
    false_success = _count(categories, "unsupported_claim")
    slow = _count(categories, "slow_response") + _count(categories, "latency")
    total_done = int(counts.get("done") or 0)
    total_failed = int(counts.get("failed") or 0)
    tool_success = _clamp(100 - failed_tool * 8 - total_failed * 2 + min(8, total_done // 20))
    task_completion = _clamp(80 + min(15, total_done // 10) - total_failed * 3)
    stt_accuracy = _clamp(95 - stt_mistakes * 10)
    latency = _clamp(92 - slow * 6)
    honesty = _clamp(96 - false_success * 18 + min(4, len(proofs.get("reports") or [])))
    return {
        "stt_accuracy": stt_accuracy,
        "tool_success": tool_success,
        "honesty": honesty,
        "latency": latency,
        "task_completion": task_completion,
        "sample_count": _clamp(len(recent) * 5),
    }


def _count(categories: dict[str, Any], name: str) -> int:
    value = categories.get(name, 0) if isinstance(categories, dict) else 0
    if isinstance(value, dict):
        return int(value.get("count") or 0)
    try:
        return int(value or 0)
    except Exception:
        return 0


def _clamp(value: int | float) -> int:
    return max(0, min(100, int(round(float(value)))))


def _row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "timestamp": str(row["timestamp"]),
        "overall": int(row["overall"]),
        "summary": str(row["summary"]),
        "scores": _json_loads(row["scores_json"], {}),
        "inputs": _json_loads(row["inputs_json"], {}),
    }


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, default=str)


def _json_loads(value: str, default: Any) -> Any:
    try:
        return json.loads(value or "")
    except Exception:
        return default


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds")
