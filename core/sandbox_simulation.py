"""Dry-run planning for risky PC, browser, phone, and code actions."""

from __future__ import annotations

import datetime as dt
import json
import sqlite3
import threading
from pathlib import Path
from typing import Any

from core.config import DATA_DIR, ensure_runtime_dirs

DB_PATH = DATA_DIR / "sandbox_simulation.sqlite3"
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
            CREATE TABLE IF NOT EXISTS simulations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                kind TEXT NOT NULL,
                instruction TEXT NOT NULL,
                risk_level TEXT NOT NULL,
                confidence REAL NOT NULL,
                summary TEXT NOT NULL,
                payload_json TEXT NOT NULL
            )
            """
        )


def simulate_action(kind: str, instruction: str, *, context: dict[str, Any] | None = None) -> dict[str, Any]:
    init_db()
    kind = _clean(kind) or _infer_kind(instruction)
    instruction = _clean(instruction)
    payload = _plan(kind, instruction, context or {})
    simulation = _persist(kind, instruction, payload)
    return simulation | payload


def simulate_desktop_task(instruction: str) -> dict[str, Any]:
    return simulate_action("desktop", instruction)


def simulate_code_change(instruction: str, *, root: str = "") -> dict[str, Any]:
    return simulate_action("code", instruction, context={"root": root})


def simulate_tool_call(tool_name: str, inputs: dict[str, Any]) -> dict[str, Any]:
    return simulate_action("tool", f"{tool_name}: {json.dumps(inputs, ensure_ascii=True, sort_keys=True, default=str)}", context={"tool": tool_name, "inputs": inputs})


def list_simulations(limit: int = 20) -> list[dict[str, Any]]:
    init_db()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM simulations ORDER BY id DESC LIMIT ?", (max(1, min(100, int(limit))),)).fetchall()
    return [_row(row) for row in rows]


def wipe_all() -> None:
    init_db()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.execute("DELETE FROM simulations")


def _plan(kind: str, instruction: str, context: dict[str, Any]) -> dict[str, Any]:
    lowered = instruction.lower()
    risks = []
    steps = []
    rollback = []
    if kind in {"desktop", "browser", "app"}:
        steps = ["Capture current app state.", "Identify target controls through DOM/UIA/screen context.", "Take one reversible action at a time.", "Verify the visible result after each step.", "Pause for approval on login, payment, deletion, or message-sending screens."]
        rollback = ["Stop the session.", "Use Back/Escape where safe.", "Report the last confirmed screen state."]
    elif kind == "code":
        steps = ["Inspect relevant files.", "Create a small change set.", "Run focused tests.", "Summarize diff and verification.", "Wait for approval before applying risky changes."]
        rollback = ["Keep original file backups or rely on git diff.", "Revert only Friday's own change set if verification fails."]
    elif kind == "phone":
        steps = ["Check phone bridge status.", "Prefer draft/open actions over direct sending/calling.", "Verify ADB or ntfy result.", "Ask before calls, SMS, or file transfer."]
        rollback = ["Cancel drafts manually if opened.", "Do not send unless approved."]
    else:
        steps = ["Classify the requested action.", "Check permissions.", "Run the least risky available tool.", "Verify evidence before claiming success."]
        rollback = ["Stop and report uncertainty if no verification is available."]
    if any(term in lowered for term in ["delete", "send", "call", "pay", "password", "secret", "credential", "format", "shutdown"]):
        risks.append("High-risk wording detected; ask-first permission should apply.")
    if any(term in lowered for term in ["login", "captcha", "2fa", "bank"]):
        risks.append("Human handoff likely required.")
    risk_level = "high" if risks else ("medium" if kind in {"desktop", "code", "phone"} else "low")
    confidence = 0.62 if risks else 0.78
    summary = f"Simulation for {kind}: {len(steps)} planned step(s), risk {risk_level}, confidence {confidence:.2f}."
    return {
        "kind": kind,
        "risk_level": risk_level,
        "confidence": confidence,
        "requires_approval": risk_level in {"medium", "high"},
        "expected_steps": steps,
        "risks": risks,
        "rollback_plan": rollback,
        "verification_method": "Tool result, screenshot/DOM/UIA observation, test output, or audit log evidence.",
        "context": context,
        "summary": summary,
    }


def _persist(kind: str, instruction: str, payload: dict[str, Any]) -> dict[str, Any]:
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            "INSERT INTO simulations(timestamp, kind, instruction, risk_level, confidence, summary, payload_json) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (_now(), kind, instruction, payload["risk_level"], float(payload["confidence"]), payload["summary"], _json_dumps(payload)),
        )
        row = conn.execute("SELECT * FROM simulations WHERE id=?", (int(cursor.lastrowid),)).fetchone()
    return _row(row)


def _row(row: sqlite3.Row) -> dict[str, Any]:
    payload = _json_loads(row["payload_json"], {})
    return {
        "id": int(row["id"]),
        "timestamp": str(row["timestamp"]),
        "kind": str(row["kind"]),
        "instruction": str(row["instruction"]),
        "risk_level": str(row["risk_level"]),
        "confidence": float(row["confidence"]),
        "summary": str(row["summary"]),
        "payload": payload,
    }


def _infer_kind(instruction: str) -> str:
    lowered = instruction.lower()
    if any(term in lowered for term in ["browser", "website", "chrome", "form"]):
        return "browser"
    if any(term in lowered for term in ["file", "code", "test", "repo"]):
        return "code"
    if any(term in lowered for term in ["phone", "android", "sms", "call"]):
        return "phone"
    return "desktop"


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
