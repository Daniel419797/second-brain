"""Personal command graph connecting user phrases to multi-step workflows."""

from __future__ import annotations

import datetime as dt
import json
import re
import sqlite3
import threading
from pathlib import Path
from typing import Any

from core.config import DATA_DIR, ensure_runtime_dirs

DB_PATH = DATA_DIR / "command_graph.sqlite3"
_LOCK = threading.Lock()

DEFAULTS = {
    "start work": {"intent": "start_coding_workspace", "steps": ["open VS Code", "start API", "open dashboard", "show project status"]},
    "check friday": {"intent": "friday_health_check", "steps": ["check API", "check pending tasks", "check voice latency", "check approvals"]},
    "ship it": {"intent": "release_preflight", "steps": ["build", "test", "prepare release report", "ask for deploy approval"]},
    "fix this": {"intent": "debug_current_problem", "steps": ["collect error", "simulate change", "prepare patch", "run tests"]},
    "deep check": {"intent": "full_quality_scan", "steps": ["run QA lab", "security scan", "dependency check", "proof report"]},
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
            CREATE TABLE IF NOT EXISTS command_nodes (
                phrase TEXT PRIMARY KEY,
                intent TEXT NOT NULL,
                steps_json TEXT NOT NULL,
                confidence REAL NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                metadata_json TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS command_edges (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                from_phrase TEXT NOT NULL,
                to_phrase TEXT NOT NULL,
                relation TEXT NOT NULL,
                metadata_json TEXT NOT NULL
            )
            """
        )


def install_defaults() -> dict[str, Any]:
    created = []
    for phrase, spec in DEFAULTS.items():
        created.append(learn_phrase(phrase, spec["intent"], steps=spec["steps"], confidence=0.8, metadata={"source": "default"}))
    return {"created": created, "summary": f"Installed {len(created)} command graph defaults."}


def learn_phrase(phrase: str, intent: str, *, steps: list[str] | str | None = None, confidence: float = 0.72, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    init_db()
    normalized = _phrase(phrase)
    now = _now()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute(
            """
            INSERT INTO command_nodes(phrase, intent, steps_json, confidence, created_at, updated_at, metadata_json)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(phrase) DO UPDATE SET intent=excluded.intent, steps_json=excluded.steps_json, confidence=excluded.confidence, updated_at=excluded.updated_at, metadata_json=excluded.metadata_json
            """,
            (normalized, _clean(intent) or normalized, _json_dumps(_list(steps)), _confidence(confidence), now, now, _json_dumps(metadata or {})),
        )
        row = conn.execute("SELECT * FROM command_nodes WHERE phrase=?", (normalized,)).fetchone()
    item = _row(row)
    item["summary"] = f"Learned command graph phrase '{item['phrase']}' -> {item['intent']}."
    return item


def connect(from_phrase: str, to_phrase: str, *, relation: str = "related", metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    init_db()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        cursor = conn.execute(
            "INSERT INTO command_edges(from_phrase, to_phrase, relation, metadata_json) VALUES (?, ?, ?, ?)",
            (_phrase(from_phrase), _phrase(to_phrase), _clean(relation) or "related", _json_dumps(metadata or {})),
        )
    return {"id": int(cursor.lastrowid), "summary": f"Connected {from_phrase} -> {to_phrase}."}


def resolve(phrase: str) -> dict[str, Any]:
    init_db()
    normalized = _phrase(phrase)
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM command_nodes WHERE phrase=?", (normalized,)).fetchone()
        if not row:
            like = f"%{normalized}%"
            row = conn.execute("SELECT * FROM command_nodes WHERE phrase LIKE ? OR intent LIKE ? ORDER BY confidence DESC LIMIT 1", (like, like)).fetchone()
    if not row:
        return {"found": False, "phrase": normalized, "summary": "No command graph match yet."}
    item = _row(row)
    item["found"] = True
    item["summary"] = f"{item['phrase']} means {item['intent']}."
    return item


def list_nodes(limit: int = 50) -> list[dict[str, Any]]:
    init_db()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM command_nodes ORDER BY updated_at DESC LIMIT ?", (max(1, min(200, int(limit or 50))),)).fetchall()
    return [_row(row) for row in rows]


def status() -> dict[str, Any]:
    nodes = list_nodes(limit=20)
    return {"nodes": nodes, "summary": f"{len(nodes)} command graph node(s) loaded."}


def wipe_all() -> None:
    init_db()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.execute("DELETE FROM command_nodes")
        conn.execute("DELETE FROM command_edges")


def _row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "phrase": str(row["phrase"]),
        "intent": str(row["intent"]),
        "steps": _json_loads(row["steps_json"], []),
        "confidence": float(row["confidence"]),
        "created_at": str(row["created_at"]),
        "updated_at": str(row["updated_at"]),
        "metadata": _json_loads(row["metadata_json"], {}),
    }


def _phrase(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower())[:160]


def _list(value: list[str] | str | None) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [part.strip() for part in re.split(r"[;\n]+", value) if part.strip()]
    return [_clean(item) for item in value if _clean(item)]


def _confidence(value: Any) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except Exception:
        return 0.5


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
