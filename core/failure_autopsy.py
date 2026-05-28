"""Write short autopsies whenever Friday fails badly."""

from __future__ import annotations

import datetime as dt
import json
import re
import sqlite3
import threading
from pathlib import Path
from typing import Any

from core import skill_improvement
from core.config import DATA_DIR, ensure_runtime_dirs

DB_PATH = DATA_DIR / "failure_autopsy.sqlite3"
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
            CREATE TABLE IF NOT EXISTS failure_autopsies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                title TEXT NOT NULL,
                what_happened TEXT NOT NULL,
                root_cause TEXT NOT NULL,
                next_time TEXT NOT NULL,
                code_change_needed INTEGER NOT NULL,
                evidence_json TEXT NOT NULL,
                source TEXT NOT NULL,
                metadata_json TEXT NOT NULL
            )
            """
        )


def create(
    title: str,
    what_happened: str,
    *,
    root_cause: str = "",
    next_time: str = "",
    evidence: list[Any] | str | None = None,
    code_change_needed: bool = False,
    source: str = "friday",
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    init_db()
    clean_happened = _clean(what_happened)
    cause = _clean(root_cause) or _infer_root_cause(clean_happened)
    next_action = _clean(next_time) or _next_time(cause)
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            """
            INSERT INTO failure_autopsies(timestamp, title, what_happened, root_cause, next_time, code_change_needed, evidence_json, source, metadata_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (_now(), _clean(title)[:300], clean_happened[:3000], cause[:1500], next_action[:1500], 1 if code_change_needed else 0, _json_dumps(_list(evidence)), _clean(source)[:120], _json_dumps(metadata or {})),
        )
        row = conn.execute("SELECT * FROM failure_autopsies WHERE id=?", (int(cursor.lastrowid),)).fetchone()
    item = _row(row)
    try:
        skill_improvement.record_failure(source or "friday", clean_happened, evidence=item["evidence"], context={"autopsy_id": item["id"], "root_cause": cause})
    except Exception:
        pass
    item["summary"] = f"Autopsy #{item['id']}: {item['root_cause']}"
    return item


def recent(limit: int = 20) -> list[dict[str, Any]]:
    init_db()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM failure_autopsies ORDER BY id DESC LIMIT ?", (max(1, min(100, int(limit or 20))),)).fetchall()
    return [_row(row) for row in rows]


def status() -> dict[str, Any]:
    items = recent(limit=8)
    return {"recent": items, "summary": f"{len(items)} recent failure autopsy/autopsies."}


def wipe_all() -> None:
    init_db()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.execute("DELETE FROM failure_autopsies")


def _infer_root_cause(text: str) -> str:
    lowered = text.lower()
    if "contract" in lowered and "not satisfied" in lowered:
        return "The agent output did not satisfy the task contract."
    if "permission" in lowered:
        return "A permission gate blocked the action."
    if "timeout" in lowered:
        return "The operation timed out or waited on a slow dependency."
    if "not found" in lowered:
        return "Friday targeted something that could not be found."
    if "no evidence" in lowered or "without verified evidence" in lowered or "unsupported" in lowered:
        return "Friday lacked verified evidence for the claim."
    return "Unknown root cause; needs inspection."


def _next_time(cause: str) -> str:
    lowered = cause.lower()
    if "contract" in lowered:
        return "Ask for missing evidence or revise the output before marking the task done."
    if "permission" in lowered:
        return "Surface the approval request clearly and wait for user confirmation."
    if "evidence" in lowered:
        return "Run or inspect a verifying tool before using success language."
    return "Create a small reproducible check, then update the relevant skill if the failure repeats."


def _row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "timestamp": str(row["timestamp"]),
        "title": str(row["title"]),
        "what_happened": str(row["what_happened"]),
        "root_cause": str(row["root_cause"]),
        "next_time": str(row["next_time"]),
        "code_change_needed": bool(row["code_change_needed"]),
        "evidence": _json_loads(row["evidence_json"], []),
        "source": str(row["source"]),
        "metadata": _json_loads(row["metadata_json"], {}),
    }


def _list(value: list[Any] | str | None) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [_clean(item) for item in value if _clean(item)]
    return [_clean(value)] if _clean(value) else []


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").replace("\x00", " ")).strip()


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, default=str)


def _json_loads(value: str, default: Any) -> Any:
    try:
        return json.loads(value or "")
    except Exception:
        return default


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds")
