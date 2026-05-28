"""Failure reports, probable causes, test plans, and self-update proposals."""

from __future__ import annotations

import datetime as dt
import json
import sqlite3
import threading
from pathlib import Path
from typing import Any

from core import notification_center
from core.config import DATA_DIR, config_value, ensure_runtime_dirs

DB_PATH = DATA_DIR / "self_debugger.sqlite3"
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
            CREATE TABLE IF NOT EXISTS self_debug_reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                source TEXT NOT NULL,
                summary TEXT NOT NULL,
                probable_cause TEXT NOT NULL,
                proposed_fix TEXT NOT NULL,
                test_plan TEXT NOT NULL,
                status TEXT NOT NULL,
                metadata_json TEXT NOT NULL
            )
            """
        )


def record_failure(source: str, summary: str, *, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    init_db()
    analysis = _analyze(source, summary, metadata or {})
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            """
            INSERT INTO self_debug_reports(timestamp, source, summary, probable_cause, proposed_fix, test_plan, status, metadata_json)
            VALUES (?, ?, ?, ?, ?, ?, 'open', ?)
            """,
            (_now(), _clean(source), _clean(summary)[:2000], analysis["probable_cause"], analysis["proposed_fix"], analysis["test_plan"], _json_dumps(metadata or {})),
        )
        row = conn.execute("SELECT * FROM self_debug_reports WHERE id=?", (int(cursor.lastrowid),)).fetchone()
    report = _row(row)
    notification_center.add(source="self_debugger", category="failure", severity=3, title="Friday created a failure report", message=report["summary"], dedupe_key=f"self-debug:{report['source']}:{report['probable_cause']}", metadata={"report_id": report["id"]})
    return report


def analyze_recent(limit: int = 10) -> dict[str, Any]:
    reports = recent_reports(limit=limit)
    open_reports = [item for item in reports if item["status"] == "open"]
    causes: dict[str, int] = {}
    for item in open_reports:
        causes[item["probable_cause"]] = causes.get(item["probable_cause"], 0) + 1
    return {
        "open_count": len(open_reports),
        "causes": causes,
        "reports": reports,
        "summary": f"{len(open_reports)} open self-debug report(s).",
    }


def create_fix_proposal(report_id: int = 0) -> dict[str, Any]:
    reports = [get_report(report_id)] if report_id else recent_reports(limit=5)
    reports = [item for item in reports if item]
    if not reports:
        return {"ok": False, "summary": "No self-debug report found."}
    request = "Fix Friday self-debug reports: " + "; ".join(f"#{item['id']} {item['summary']} probable cause: {item['probable_cause']}" for item in reports[:5])
    if not bool(config_value("self_debugger_self_update_enabled", True)):
        return {"ok": False, "summary": request}
    from core import self_update

    proposal = self_update.create_proposal(request)
    return {"ok": True, "proposal": proposal, "summary": f"Created self-update proposal #{proposal.get('id')} from self-debug reports."}


def get_report(report_id: int) -> dict[str, Any] | None:
    init_db()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM self_debug_reports WHERE id=?", (int(report_id),)).fetchone()
    return _row(row) if row else None


def recent_reports(limit: int = 20) -> list[dict[str, Any]]:
    init_db()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM self_debug_reports ORDER BY id DESC LIMIT ?", (max(1, min(100, int(limit))),)).fetchall()
    return [_row(row) for row in rows]


def wipe_all() -> None:
    init_db()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.execute("DELETE FROM self_debug_reports")


def _analyze(source: str, summary: str, metadata: dict[str, Any]) -> dict[str, str]:
    text = f"{source} {summary} {json.dumps(metadata, ensure_ascii=True, default=str)}".lower()
    if "timeout" in text or "slow" in text or "latency" in text:
        return {
            "probable_cause": "timeout_or_latency",
            "proposed_fix": "Add shorter timeouts, background execution, or cached/local fallback.",
            "test_plan": "Run the relevant unit test and one timeout-path test.",
        }
    if "permission" in text or "blocked" in text:
        return {
            "probable_cause": "permission_policy",
            "proposed_fix": "Review permission mapping and surface a clearer approval prompt.",
            "test_plan": "Test allow, ask, and block decisions for the action.",
        }
    if "stt" in text or "transcript" in text or "heard" in text:
        return {
            "probable_cause": "voice_transcription",
            "proposed_fix": "Add a voice repair alias or reduce hallucinated transcript acceptance.",
            "test_plan": "Record a voice reliability sample and verify repair matching.",
        }
    return {
        "probable_cause": "unknown",
        "proposed_fix": "Inspect recent logs, reproduce the failure, and add a focused regression test.",
        "test_plan": "Run the focused test, then the full test suite if code changes are made.",
    }


def _row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "timestamp": str(row["timestamp"]),
        "source": str(row["source"]),
        "summary": str(row["summary"]),
        "probable_cause": str(row["probable_cause"]),
        "proposed_fix": str(row["proposed_fix"]),
        "test_plan": str(row["test_plan"]),
        "status": str(row["status"]),
        "metadata": _json_loads(row["metadata_json"], {}),
    }


def _clean(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, default=str)


def _json_loads(value: str, default: Any) -> Any:
    try:
        return json.loads(value or "")
    except Exception:
        return default


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds")
