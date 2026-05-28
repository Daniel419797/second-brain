"""Explicit privacy preflight before Friday uses sensitive local context."""

from __future__ import annotations

import datetime as dt
import json
import re
import sqlite3
import threading
from pathlib import Path
from typing import Any

from core import approval_inbox, personal_safety_guardian, privacy_vault
from core.config import DATA_DIR, ensure_runtime_dirs

DB_PATH = DATA_DIR / "privacy_firewall_pro.sqlite3"
_LOCK = threading.Lock()

SENSITIVE_TERMS = {
    ".env": "environment secrets",
    "password": "credential-like text",
    "secret": "secret reference",
    "token": "token reference",
    "api_key": "API key reference",
    "private": "private memory",
    "phone": "phone data",
    "message": "message data",
    "email": "email data",
    "location": "location data",
    "credential": "credential reference",
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
            CREATE TABLE IF NOT EXISTS privacy_checks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                instruction TEXT NOT NULL,
                context TEXT NOT NULL,
                status TEXT NOT NULL,
                risk_level TEXT NOT NULL,
                requested_data_json TEXT NOT NULL,
                reason TEXT NOT NULL,
                approval_id INTEGER,
                metadata_json TEXT NOT NULL
            )
            """
        )


def check(instruction: str, *, context: str = "", paths: list[str] | str | None = None, purpose: str = "") -> dict[str, Any]:
    init_db()
    requested = _detect(instruction, context, paths)
    risk = "high" if any(item["category"] in {"environment secrets", "credential-like text", "secret reference", "token reference", "API key reference"} for item in requested) else ("medium" if requested else "low")
    status = "approval_required" if requested else "allowed"
    reason = _reason(requested, purpose)
    approval_id: int | None = None
    if requested:
        approval = _create_approval(instruction, requested, reason)
        approval_id = int(approval.get("id") or 0) or None
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            """
            INSERT INTO privacy_checks(timestamp, instruction, context, status, risk_level, requested_data_json, reason, approval_id, metadata_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (_now(), _clean(instruction)[:3000], _clean(context)[:2000], status, risk, _json_dumps(requested), reason, approval_id, _json_dumps({"paths": _paths(paths), "purpose": purpose})),
        )
        row = conn.execute("SELECT * FROM privacy_checks WHERE id=?", (int(cursor.lastrowid),)).fetchone()
    return _row(row)


def approval_summary(limit: int = 10) -> dict[str, Any]:
    pending = [item for item in recent(limit=limit) if item["status"] == "approval_required"]
    vault = _safe(privacy_vault.summary, {})
    return {"pending": pending, "vault": vault, "summary": f"{len(pending)} privacy approval check(s) waiting."}


def recent(limit: int = 20) -> list[dict[str, Any]]:
    init_db()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM privacy_checks ORDER BY id DESC LIMIT ?", (max(1, min(200, int(limit or 20))),)).fetchall()
    return [_row(row) for row in rows]


def status() -> dict[str, Any]:
    latest = recent(limit=8)
    pending = [item for item in latest if item["status"] == "approval_required"]
    return {"recent": latest, "pending": pending, "summary": f"{len(pending)} privacy check(s) need approval."}


def wipe_all() -> None:
    init_db()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.execute("DELETE FROM privacy_checks")


def _detect(instruction: str, context: str, paths: list[str] | str | None) -> list[dict[str, str]]:
    haystack = f"{instruction} {context} {' '.join(_paths(paths))}".lower()
    requested = []
    for term, category in SENSITIVE_TERMS.items():
        if term in haystack:
            requested.append({"term": term, "category": category, "reason": f"Instruction or context mentions {term}."})
    for path in _paths(paths):
        try:
            preflight = personal_safety_guardian.preflight_action("use file", path=path)
            if not preflight.get("allowed_without_approval", True):
                requested.append({"term": Path(path).name, "category": "protected file", "reason": preflight.get("summary", "Protected file.")})
        except Exception:
            continue
    seen = set()
    out = []
    for item in requested:
        key = (item["term"], item["category"])
        if key not in seen:
            seen.add(key)
            out.append(item)
    return out


def _create_approval(instruction: str, requested: list[dict[str, str]], reason: str) -> dict[str, Any]:
    try:
        return approval_inbox.create(
            kind="privacy",
            title="Private data access approval",
            summary=reason,
            source="privacy_firewall_pro",
            payload={"instruction": instruction, "requested": requested},
        )
    except Exception:
        return {}


def _reason(requested: list[dict[str, str]], purpose: str) -> str:
    if not requested:
        return "No sensitive data trigger detected."
    categories = sorted({item["category"] for item in requested})
    suffix = f" Purpose: {_clean(purpose)}." if _clean(purpose) else ""
    return f"Friday wants to use: {', '.join(categories)}.{suffix} Approve once or adjust the permission first."


def _row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "timestamp": str(row["timestamp"]),
        "instruction": str(row["instruction"]),
        "context": str(row["context"]),
        "status": str(row["status"]),
        "risk_level": str(row["risk_level"]),
        "requested_data": _json_loads(row["requested_data_json"], []),
        "reason": str(row["reason"]),
        "approval_id": int(row["approval_id"]) if row["approval_id"] is not None else None,
        "metadata": _json_loads(row["metadata_json"], {}),
        "summary": str(row["reason"]),
    }


def _paths(paths: list[str] | str | None) -> list[str]:
    if paths is None:
        return []
    if isinstance(paths, str):
        return [paths] if paths else []
    return [str(path) for path in paths if str(path or "").strip()]


def _safe(fn: Any, default: Any) -> Any:
    try:
        return fn()
    except Exception:
        return default


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
