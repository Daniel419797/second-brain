"""Contextual workspace autopilot for active projects."""

from __future__ import annotations

import datetime as dt
import json
import re
import sqlite3
import threading
from pathlib import Path
from typing import Any

from core import pc_awareness, project_autopilot, workspace_brain
from core.config import DATA_DIR, ensure_runtime_dirs, resolve_coding_root

DB_PATH = DATA_DIR / "contextual_workspace.sqlite3"
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
            CREATE TABLE IF NOT EXISTS workspace_contexts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                root TEXT NOT NULL,
                active_window TEXT NOT NULL,
                summary TEXT NOT NULL,
                dev_server TEXT NOT NULL,
                next_tasks_json TEXT NOT NULL,
                metadata_json TEXT NOT NULL
            )
            """
        )


def detect_active_workspace() -> dict[str, Any]:
    active = ""
    try:
        snapshot = pc_awareness.refresh()
        active = str(snapshot.get("active_window") or "")
    except Exception:
        snapshot = {}
    root = _root_from_active_window(active) or resolve_coding_root()
    return {"root": str(root), "active_window": active, "pc": snapshot}


def prepare_context(root: str | Path = "") -> dict[str, Any]:
    detected = detect_active_workspace()
    base = _safe_root(root or detected["root"])
    analysis = _safe_dict(lambda: workspace_brain.analyze_project(base), {"summary": "Workspace analysis unavailable.", "todos": [], "error": "analysis_failed"})
    autopilot = _safe_dict(lambda: project_autopilot.inspect_project(base, run_tests=False), {"issues": [{"summary": "Project health scan unavailable."}], "error": "autopilot_failed"})
    dev_server = _dev_server_hint(base)
    next_tasks = _next_tasks(analysis, autopilot)
    summary = f"Workspace context ready for {base.name}. {analysis.get('summary', '')[:240]}"
    context = {
        "timestamp": _now(),
        "root": str(base),
        "active_window": detected.get("active_window", ""),
        "analysis": analysis,
        "autopilot": autopilot,
        "dev_server": dev_server,
        "next_tasks": next_tasks,
        "summary": summary,
    }
    _store(context)
    return context


def latest() -> dict[str, Any] | None:
    rows = recent(limit=1)
    return rows[0] if rows else None


def recent(limit: int = 10) -> list[dict[str, Any]]:
    init_db()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM workspace_contexts ORDER BY id DESC LIMIT ?", (max(1, min(50, int(limit))),)).fetchall()
    return [_row(row) for row in rows]


def summary() -> dict[str, Any]:
    item = latest()
    return {"latest": item, "summary": item["summary"] if item else "No workspace context captured yet."}


def wipe_all() -> None:
    init_db()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.execute("DELETE FROM workspace_contexts")


def _store(context: dict[str, Any]) -> None:
    init_db()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.execute(
            "INSERT INTO workspace_contexts(timestamp, root, active_window, summary, dev_server, next_tasks_json, metadata_json) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (context["timestamp"], context["root"], context["active_window"], context["summary"], context["dev_server"], _json_dumps(context["next_tasks"]), _json_dumps({"analysis": context.get("analysis"), "autopilot": context.get("autopilot")})),
        )


def _root_from_active_window(active_window: str) -> Path | None:
    text = str(active_window or "")
    match = re.search(r"\b([A-Za-z]:\\[^|]+?)\b", text)
    if match:
        path = Path(match.group(1))
        if path.exists():
            return path if path.is_dir() else path.parent
    return None


def _dev_server_hint(base: Path) -> str:
    if (base / "package.json").exists():
        return "Run npm run dev or npm run web:dev if this is the Friday workspace."
    if (base / "pyproject.toml").exists() or (base / "requirements.txt").exists():
        return "Run the configured Python test/dev command for this project."
    return "No dev-server hint detected."


def _next_tasks(analysis: dict[str, Any], autopilot: dict[str, Any]) -> list[str]:
    tasks: list[str] = []
    issues = autopilot.get("issues") or []
    if issues:
        tasks.append(str(issues[0].get("summary") or issues[0].get("title") or "Review project issue."))
    todos = analysis.get("todos") or []
    if todos:
        tasks.append(f"Review TODO: {todos[0].get('text') or todos[0].get('kind')}")
    if not tasks:
        tasks.append("Map the repo, check docs, then run focused tests before editing.")
    return tasks[:5]


def _safe_root(root: str | Path) -> Path:
    candidate = resolve_coding_root(root)
    try:
        resolved = candidate.resolve()
    except Exception:
        return resolve_coding_root()
    fallback = resolve_coding_root()
    return resolved if resolved.exists() and resolved.is_dir() else fallback


def _safe_dict(fn: Any, fallback: dict[str, Any]) -> dict[str, Any]:
    try:
        result = fn()
        return result if isinstance(result, dict) else fallback | {"raw": str(result)}
    except Exception as exc:
        return fallback | {"exception": str(exc)}


def _row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "timestamp": str(row["timestamp"]),
        "root": str(row["root"]),
        "active_window": str(row["active_window"]),
        "summary": str(row["summary"]),
        "dev_server": str(row["dev_server"]),
        "next_tasks": _json_loads(row["next_tasks_json"], []),
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
