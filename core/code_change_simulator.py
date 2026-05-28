"""Predict code-change impact, tests, risk, and rollback before editing."""

from __future__ import annotations

import datetime as dt
import json
import re
import sqlite3
import threading
from pathlib import Path
from typing import Any

from core.config import DATA_DIR, ensure_runtime_dirs

DB_PATH = DATA_DIR / "code_change_simulator.sqlite3"
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
            CREATE TABLE IF NOT EXISTS code_simulations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                root TEXT NOT NULL,
                instruction TEXT NOT NULL,
                affected_files_json TEXT NOT NULL,
                risks_json TEXT NOT NULL,
                tests_json TEXT NOT NULL,
                rollback_plan TEXT NOT NULL,
                confidence REAL NOT NULL,
                metadata_json TEXT NOT NULL
            )
            """
        )


def simulate(instruction: str, *, root: str = "", metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    init_db()
    clean = _clean(instruction)
    base = Path(root or ".").resolve()
    files = _predict_files(clean, base)
    tests = _tests_for(clean, base)
    risks = _risks(clean)
    rollback = "Snapshot touched files first, keep a focused diff, and revert only this change set if tests fail."
    confidence = 0.72 if files else 0.48
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            """
            INSERT INTO code_simulations(timestamp, root, instruction, affected_files_json, risks_json, tests_json, rollback_plan, confidence, metadata_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (_now(), str(base), clean[:4000], _json_dumps(files), _json_dumps(risks), _json_dumps(tests), rollback, confidence, _json_dumps(metadata or {})),
        )
        row = conn.execute("SELECT * FROM code_simulations WHERE id=?", (int(cursor.lastrowid),)).fetchone()
    item = _row(row)
    item["summary"] = f"Predicted {len(files)} affected file(s), {len(risks)} risk(s), and {len(tests)} verification step(s)."
    return item


def recent(limit: int = 20) -> list[dict[str, Any]]:
    init_db()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM code_simulations ORDER BY id DESC LIMIT ?", (max(1, min(100, int(limit or 20))),)).fetchall()
    return [_row(row) for row in rows]


def status() -> dict[str, Any]:
    items = recent(limit=8)
    return {"recent": items, "summary": f"{len(items)} recent code change simulation(s)."}


def wipe_all() -> None:
    init_db()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.execute("DELETE FROM code_simulations")


def _predict_files(instruction: str, root: Path) -> list[str]:
    files: list[str] = []
    for match in re.findall(r"[\w./\\-]+\.(?:py|js|jsx|ts|tsx|css|json|md)", instruction):
        files.append(match)
    keywords = {
        "api": ("api/server.py", "core/orchestrator.py"),
        "dashboard": ("apps/web/app/page.jsx", "apps/web/app/globals.css"),
        "electron": ("apps/desktop/main.js", "package.json"),
        "agent": ("core/agents.py", "core/background_agents.py"),
        "voice": ("jarvis.py", "core/orchestrator.py"),
        "permission": ("core/permissions.py", "api/server.py"),
        "test": ("tests/",),
    }
    lowered = instruction.lower()
    for key, paths in keywords.items():
        if key in lowered:
            files.extend(paths)
    if root.exists():
        for name in ("package.json", "requirements.txt", "pyproject.toml"):
            path = root / name
            if path.exists():
                files.append(str(path))
    return sorted(dict.fromkeys(files))[:20]


def _tests_for(instruction: str, root: Path) -> list[str]:
    tests = [".venv\\Scripts\\python.exe -m compileall core api tools tests"]
    lowered = instruction.lower()
    if "api" in lowered or "endpoint" in lowered:
        tests.append(".venv\\Scripts\\python.exe -m pytest tests/test_api_server.py -q")
    if "agent" in lowered:
        tests.append(".venv\\Scripts\\python.exe -m pytest tests/test_background_agents.py tests/test_agent_office.py -q")
    if "dashboard" in lowered or "web" in lowered:
        tests.append("npm run web:build")
    if (root / "package.json").exists() and "web" not in lowered:
        tests.append("npm run web:build")
    return list(dict.fromkeys(tests))


def _risks(instruction: str) -> list[str]:
    lowered = instruction.lower()
    risks = ["Scope creep if the change touches shared orchestration paths."]
    if any(term in lowered for term in ("delete", "remove", "credential", ".env", "secret")):
        risks.append("Sensitive or destructive operation needs explicit permission and backup.")
    if any(term in lowered for term in ("agent", "background", "thread", "worker")):
        risks.append("Background concurrency can hide failures; verify task queue and worker status.")
    if any(term in lowered for term in ("ui", "dashboard", "css")):
        risks.append("Responsive layout can regress; run the web build and inspect compact views.")
    return risks


def _row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "timestamp": str(row["timestamp"]),
        "root": str(row["root"]),
        "instruction": str(row["instruction"]),
        "affected_files": _json_loads(row["affected_files_json"], []),
        "risks": _json_loads(row["risks_json"], []),
        "tests": _json_loads(row["tests_json"], []),
        "rollback_plan": str(row["rollback_plan"]),
        "confidence": float(row["confidence"]),
        "metadata": _json_loads(row["metadata_json"], {}),
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
