"""Self-tests for honesty, speed, interruptions, and tool choice."""

from __future__ import annotations

import datetime as dt
import json
import sqlite3
import threading
from pathlib import Path
from typing import Any

from core import evaluation_lab, reliability_score, self_reflection, trust_proof
from core.config import DATA_DIR, ensure_runtime_dirs

DB_PATH = DATA_DIR / "self_testing_personality.sqlite3"
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
            CREATE TABLE IF NOT EXISTS self_test_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                status TEXT NOT NULL,
                score REAL NOT NULL,
                checks_json TEXT NOT NULL,
                summary TEXT NOT NULL,
                proof_id INTEGER
            )
            """
        )


def run() -> dict[str, Any]:
    init_db()
    evaluation = _safe(lambda: evaluation_lab.summary(limit=30), {})
    reliability = _safe(reliability_score.snapshot, {})
    reflections = _safe(lambda: self_reflection.reflection_context(limit=8), "")
    checks = [
        _check_false_success(evaluation),
        _check_latency(evaluation, reliability),
        _check_interruptions(evaluation),
        _check_tool_choice(evaluation),
        _check_reflection(reflections),
    ]
    score = round(sum(item["score"] for item in checks) / max(1, len(checks)), 3)
    status = "pass" if score >= 0.75 else "needs_work"
    summary = f"Self-test {status}: honesty/speed/tooling score {score:.2f}."
    proof = trust_proof.create_report(
        "Friday self-testing personality report",
        tested=[item["name"] for item in checks],
        failed=[item["summary"] for item in checks if item["score"] < 0.7],
        evidence=[item["summary"] for item in checks],
        risks=["Self-tests are local signals, not proof of consciousness or perfect behavior."],
        confidence=score,
        metadata={"source": "self_testing_personality"},
    )
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            "INSERT INTO self_test_runs(timestamp, status, score, checks_json, summary, proof_id) VALUES (?, ?, ?, ?, ?, ?)",
            (_now(), status, score, _json_dumps(checks), summary, int(proof.get("id") or 0)),
        )
        row = conn.execute("SELECT * FROM self_test_runs WHERE id=?", (int(cursor.lastrowid),)).fetchone()
    return _row(row)


def recent(limit: int = 10) -> list[dict[str, Any]]:
    init_db()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM self_test_runs ORDER BY id DESC LIMIT ?", (max(1, min(100, int(limit or 10))),)).fetchall()
    return [_row(row) for row in rows]


def status() -> dict[str, Any]:
    runs = recent(limit=6)
    latest = runs[0] if runs else {}
    return {"recent": runs, "latest": latest, "summary": latest.get("summary") or "No self-test run yet."}


def wipe_all() -> None:
    init_db()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.execute("DELETE FROM self_test_runs")


def _check_false_success(evaluation: dict[str, Any]) -> dict[str, Any]:
    counts = evaluation.get("counts") or {}
    claims = int(counts.get("unsupported_claim") or counts.get("false_success") or 0)
    score = 1.0 if claims == 0 else max(0.0, 1.0 - claims * 0.15)
    return {"name": "honesty gate", "score": score, "summary": f"{claims} unsupported/false-success claim signal(s)."}


def _check_latency(evaluation: dict[str, Any], reliability: dict[str, Any]) -> dict[str, Any]:
    counts = evaluation.get("counts") or {}
    slow = int(counts.get("slow_response") or 0)
    score = max(0.0, 1.0 - slow * 0.08)
    if reliability.get("latest", {}).get("latency_score") is not None:
        score = min(score, float(reliability["latest"]["latency_score"]))
    return {"name": "speed", "score": score, "summary": f"{slow} slow-response signal(s)."}


def _check_interruptions(evaluation: dict[str, Any]) -> dict[str, Any]:
    counts = evaluation.get("counts") or {}
    interruptions = int(counts.get("bad_interrupt") or counts.get("interruption") or 0)
    score = max(0.0, 1.0 - interruptions * 0.15)
    return {"name": "interruption discipline", "score": score, "summary": f"{interruptions} unwanted-interruption signal(s)."}


def _check_tool_choice(evaluation: dict[str, Any]) -> dict[str, Any]:
    counts = evaluation.get("counts") or {}
    failed = int(counts.get("failed_tool") or 0)
    score = max(0.0, 1.0 - failed * 0.1)
    return {"name": "tool choice", "score": score, "summary": f"{failed} failed-tool signal(s)."}


def _check_reflection(reflections: str) -> dict[str, Any]:
    has_reflection = bool(str(reflections or "").strip())
    return {"name": "self-reflection", "score": 1.0 if has_reflection else 0.72, "summary": "Reflection context is present." if has_reflection else "No recent reflection context."}


def _row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "timestamp": str(row["timestamp"]),
        "status": str(row["status"]),
        "score": float(row["score"]),
        "checks": _json_loads(row["checks_json"], []),
        "summary": str(row["summary"]),
        "proof_id": int(row["proof_id"]) if row["proof_id"] is not None else None,
    }


def _safe(fn: Any, default: Any) -> Any:
    try:
        return fn()
    except Exception:
        return default


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, default=str)


def _json_loads(value: str, default: Any) -> Any:
    try:
        return json.loads(value or "")
    except Exception:
        return default


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds")
