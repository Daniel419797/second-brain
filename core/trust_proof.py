"""Proof reports for completed work and mission evidence."""

from __future__ import annotations

import datetime as dt
import json
import sqlite3
import threading
from pathlib import Path
from typing import Any

from core.config import DATA_DIR, ensure_runtime_dirs

DB_PATH = DATA_DIR / "trust_proof.sqlite3"
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
            CREATE TABLE IF NOT EXISTS proof_reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                title TEXT NOT NULL,
                mission_id INTEGER,
                task_id INTEGER,
                changed_json TEXT NOT NULL,
                tested_json TEXT NOT NULL,
                failed_json TEXT NOT NULL,
                evidence_json TEXT NOT NULL,
                risks_json TEXT NOT NULL,
                confidence REAL NOT NULL,
                summary TEXT NOT NULL,
                metadata_json TEXT NOT NULL
            )
            """
        )


def create_report(
    title: str,
    *,
    changed: list[Any] | str | None = None,
    tested: list[Any] | str | None = None,
    failed: list[Any] | str | None = None,
    evidence: list[Any] | str | None = None,
    risks: list[Any] | str | None = None,
    mission_id: int | None = None,
    task_id: int | None = None,
    confidence: float = 0.7,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    init_db()
    changed_list = _list(changed)
    tested_list = _list(tested)
    failed_list = _list(failed)
    evidence_list = _list(evidence)
    risks_list = _list(risks)
    summary = _summary(title, changed_list, tested_list, failed_list, evidence_list, risks_list)
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            """
            INSERT INTO proof_reports(timestamp, title, mission_id, task_id, changed_json, tested_json, failed_json, evidence_json, risks_json, confidence, summary, metadata_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                _now(),
                _clean(title)[:300] or "Proof report",
                int(mission_id) if mission_id else None,
                int(task_id) if task_id else None,
                _json_dumps(changed_list),
                _json_dumps(tested_list),
                _json_dumps(failed_list),
                _json_dumps(evidence_list),
                _json_dumps(risks_list),
                _clamp(confidence),
                summary,
                _json_dumps(metadata or {}),
            ),
        )
        row = conn.execute("SELECT * FROM proof_reports WHERE id=?", (int(cursor.lastrowid),)).fetchone()
    return _row(row)


def from_mission(mission_id: int) -> dict[str, Any]:
    from core import mission_control

    mission = mission_control.get_mission(int(mission_id))
    if not mission:
        return {"ok": False, "summary": "Mission not found."}
    evidence = [f"{item.get('phase_name')}: {item.get('title')} - {item.get('summary')}" for item in mission.get("evidence") or []]
    blockers = [f"{item.get('title')}: {item.get('summary')}" for item in mission.get("blockers") or [] if item.get("status") == "open"]
    phases = mission.get("phases") or []
    tested = [item for item in evidence if "qa" in item.lower() or "test" in item.lower()]
    report = create_report(
        f"Mission #{mission_id}: {mission.get('goal')}",
        changed=[f"{phase.get('name')}={phase.get('status')}" for phase in phases],
        tested=tested or ["No QA evidence found; report marks this as a remaining risk."],
        failed=blockers,
        evidence=evidence,
        risks=blockers or ["Review final output manually before external deployment or irreversible action."],
        mission_id=int(mission_id),
        confidence=0.85 if evidence and not blockers else 0.55,
        metadata={"source": "mission_control", "status": mission.get("status")},
    )
    report["ok"] = True
    return report


def recent(limit: int = 20) -> list[dict[str, Any]]:
    init_db()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM proof_reports ORDER BY id DESC LIMIT ?", (max(1, min(100, int(limit or 20))),)).fetchall()
    return [_row(row) for row in rows]


def summary() -> dict[str, Any]:
    reports = recent(limit=6)
    return {"reports": reports, "summary": f"{len(reports)} recent proof report(s)." if reports else "No proof reports yet."}


def wipe_all() -> None:
    init_db()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.execute("DELETE FROM proof_reports")


def _summary(title: str, changed: list[str], tested: list[str], failed: list[str], evidence: list[str], risks: list[str]) -> str:
    return (
        f"{_clean(title) or 'Proof report'}: {len(changed)} change note(s), "
        f"{len(tested)} test/check note(s), {len(failed)} failure/blocker note(s), "
        f"{len(evidence)} evidence item(s), {len(risks)} remaining risk(s)."
    )


def _row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "timestamp": str(row["timestamp"]),
        "title": str(row["title"]),
        "mission_id": row["mission_id"],
        "task_id": row["task_id"],
        "changed": _json_loads(row["changed_json"], []),
        "tested": _json_loads(row["tested_json"], []),
        "failed": _json_loads(row["failed_json"], []),
        "evidence": _json_loads(row["evidence_json"], []),
        "risks": _json_loads(row["risks_json"], []),
        "confidence": float(row["confidence"]),
        "summary": str(row["summary"]),
        "metadata": _json_loads(row["metadata_json"], {}),
    }


def _list(value: list[Any] | str | None) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [_clean(item) for item in value if _clean(item)]
    return [_clean(value)] if _clean(value) else []


def _clean(value: Any) -> str:
    return " ".join(str(value or "").replace("\x00", " ").strip().split())


def _clamp(value: Any) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except Exception:
        return 0.7


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, default=str)


def _json_loads(value: str, default: Any) -> Any:
    try:
        return json.loads(value or "")
    except Exception:
        return default


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds")
