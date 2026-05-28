"""Reality checks for claims before Friday treats them as true."""

from __future__ import annotations

import datetime as dt
import json
import sqlite3
import threading
from pathlib import Path
from typing import Any

from core import certainty_brain, evaluation_lab, evidence_gate
from core.config import DATA_DIR, ensure_runtime_dirs

DB_PATH = DATA_DIR / "reality_check.sqlite3"
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
            CREATE TABLE IF NOT EXISTS reality_checks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                claim TEXT NOT NULL,
                evidence TEXT NOT NULL,
                verdict TEXT NOT NULL,
                confidence REAL NOT NULL,
                reason TEXT NOT NULL,
                metadata_json TEXT NOT NULL
            )
            """
        )


def check(claim: str, *, evidence: Any = "", tool_result: Any = None, domain: str = "general", metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    init_db()
    evidence_text = str(tool_result if tool_result is not None else evidence or "")
    claims_success = evidence_gate.claims_success(claim)
    supported = evidence_gate.evidence_supports_success(evidence_text)
    if claims_success and supported:
        verdict, confidence, reason = "verified", 0.88, "The claim says success and the evidence supports success."
    elif claims_success:
        verdict, confidence, reason = "unsupported", 0.82, "The claim sounds like success, but there is no supporting tool/result evidence."
    elif evidence_text:
        verdict, confidence, reason = "partial", 0.62, "Evidence exists, but the claim is not a direct success claim."
    else:
        verdict, confidence, reason = "guess", 0.42, "No evidence was supplied."
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            "INSERT INTO reality_checks(timestamp, claim, evidence, verdict, confidence, reason, metadata_json) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (_now(), str(claim or "")[:3000], evidence_text[:3000], verdict, confidence, reason, _json_dumps({"domain": domain, **(metadata or {})})),
        )
        row = conn.execute("SELECT * FROM reality_checks WHERE id=?", (int(cursor.lastrowid),)).fetchone()
    item = _row(row)
    _record_verdict(item, domain)
    item["summary"] = f"Reality check: {verdict}. {reason}"
    return item


def recent(limit: int = 20) -> list[dict[str, Any]]:
    init_db()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM reality_checks ORDER BY id DESC LIMIT ?", (max(1, min(100, int(limit or 20))),)).fetchall()
    return [_row(row) for row in rows]


def status() -> dict[str, Any]:
    items = recent(limit=8)
    unsupported = [item for item in items if item["verdict"] == "unsupported"]
    return {"recent": items, "unsupported": unsupported, "summary": f"{len(unsupported)} unsupported claim(s) in the recent reality-check window."}


def wipe_all() -> None:
    init_db()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.execute("DELETE FROM reality_checks")


def _record_verdict(item: dict[str, Any], domain: str) -> None:
    try:
        if item["verdict"] == "verified":
            certainty_brain.record_known(domain or "reality_check", item["claim"], evidence=[item["evidence"]], confidence=item["confidence"], source="reality_check")
        elif item["verdict"] in {"unsupported", "guess"}:
            certainty_brain.record_guess(domain or "reality_check", item["claim"], evidence=[item["reason"]], confidence=0.35, source="reality_check")
            evaluation_lab.record_event("unsupported_claim", item["reason"], source="reality_check", severity=4, metadata={"claim": item["claim"]})
    except Exception:
        pass


def _row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "timestamp": str(row["timestamp"]),
        "claim": str(row["claim"]),
        "evidence": str(row["evidence"]),
        "verdict": str(row["verdict"]),
        "confidence": float(row["confidence"]),
        "reason": str(row["reason"]),
        "metadata": _json_loads(row["metadata_json"], {}),
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
