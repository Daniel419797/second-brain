"""Real-time dev-server copilot signals from logs, files, and console text."""

from __future__ import annotations

import datetime as dt
import json
import re
import sqlite3
import threading
from pathlib import Path
from typing import Any

from core.config import DATA_DIR, ensure_runtime_dirs

DB_PATH = DATA_DIR / "dev_server_copilot.sqlite3"
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
            CREATE TABLE IF NOT EXISTS dev_copilot_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                root TEXT NOT NULL,
                source TEXT NOT NULL,
                signal TEXT NOT NULL,
                likely_file TEXT NOT NULL,
                probable_cause TEXT NOT NULL,
                recommendation TEXT NOT NULL,
                confidence REAL NOT NULL,
                metadata_json TEXT NOT NULL
            )
            """
        )


def observe(root: str = "", *, log_text: str = "", current_file: str = "", source: str = "manual") -> dict[str, Any]:
    init_db()
    signal = _signal(log_text, current_file)
    likely = _likely_file(log_text) or _clean(current_file)
    cause = _cause(log_text, likely)
    recommendation = _recommendation(signal, likely)
    confidence = 0.78 if likely and signal != "healthy" else 0.45 if signal != "healthy" else 0.62
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            """
            INSERT INTO dev_copilot_events(timestamp, root, source, signal, likely_file, probable_cause, recommendation, confidence, metadata_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (_now(), _clean(root)[:1000], _clean(source)[:120], signal, likely[:1000], cause, recommendation, confidence, _json_dumps({"log_excerpt": _clean(log_text)[:2000]})),
        )
        row = conn.execute("SELECT * FROM dev_copilot_events WHERE id=?", (int(cursor.lastrowid),)).fetchone()
    item = _row(row)
    item["summary"] = f"{signal}: {recommendation}"
    return item


def recent(limit: int = 20) -> list[dict[str, Any]]:
    init_db()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM dev_copilot_events ORDER BY id DESC LIMIT ?", (max(1, min(100, int(limit or 20))),)).fetchall()
    return [_row(row) for row in rows]


def status() -> dict[str, Any]:
    items = recent(limit=8)
    latest = items[0] if items else None
    return {"recent": items, "latest": latest, "summary": latest["summary"] if latest else "Dev server copilot is watching for useful signals."}


def wipe_all() -> None:
    init_db()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.execute("DELETE FROM dev_copilot_events")


def _signal(log_text: str, current_file: str) -> str:
    text = f"{log_text}\n{current_file}".lower()
    if any(term in text for term in ("traceback", "exception", "error:", "typeerror", "referenceerror", "syntaxerror", "failed to compile")):
        return "error_detected"
    if any(term in text for term in ("warning", "warn", "deprecated")):
        return "warning_detected"
    if any(term in text for term in ("compiled successfully", "ready", "listening on", "started server")):
        return "healthy"
    return "needs_more_context"


def _likely_file(text: str) -> str:
    patterns = [
        r"File \"([^\"]+\.(?:py|js|jsx|ts|tsx|css|json))\"",
        r"([A-Za-z]:\\[^\s:]+?\.(?:py|js|jsx|ts|tsx|css|json))",
        r"([\w./\\-]+\.(?:py|js|jsx|ts|tsx|css|json))[:(]\d+",
    ]
    for pattern in patterns:
        match = re.search(pattern, text or "")
        if match:
            return _clean(match.group(1))
    return ""


def _cause(log_text: str, likely_file: str) -> str:
    lowered = (log_text or "").lower()
    if "modulenotfound" in lowered or "cannot find module" in lowered:
        return "Missing dependency or bad import path."
    if "syntaxerror" in lowered or "failed to compile" in lowered:
        return "Compile or syntax issue."
    if "typeerror" in lowered:
        return "Runtime type mismatch or undefined value."
    if likely_file:
        return f"The recent failure points at {likely_file}."
    return "Not enough evidence yet; capture terminal output or browser console."


def _recommendation(signal: str, likely_file: str) -> str:
    if signal == "healthy":
        return "No immediate dev-server issue detected."
    if likely_file:
        return f"Inspect {likely_file}, reproduce the error, then run the smallest relevant test."
    return "Paste the failing terminal/browser log so Friday can connect the error to a file."


def _row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "timestamp": str(row["timestamp"]),
        "root": str(row["root"]),
        "source": str(row["source"]),
        "signal": str(row["signal"]),
        "likely_file": str(row["likely_file"]),
        "probable_cause": str(row["probable_cause"]),
        "recommendation": str(row["recommendation"]),
        "confidence": float(row["confidence"]),
        "metadata": _json_loads(row["metadata_json"], {}),
        "summary": f"{row['signal']}: {row['recommendation']}",
    }


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
