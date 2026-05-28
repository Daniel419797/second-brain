"""Autonomous refactor planning without changing files."""

from __future__ import annotations

import datetime as dt
import json
import re
import sqlite3
import threading
from collections import Counter
from pathlib import Path
from typing import Any

from core.config import DATA_DIR, config_value, ensure_runtime_dirs

DB_PATH = DATA_DIR / "refactor_planner.sqlite3"
_LOCK = threading.Lock()
CODE_EXTENSIONS = {".py", ".js", ".jsx", ".ts", ".tsx"}


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
            CREATE TABLE IF NOT EXISTS refactor_plans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                root TEXT NOT NULL,
                focus TEXT NOT NULL,
                findings_json TEXT NOT NULL,
                plan_json TEXT NOT NULL,
                risk_level TEXT NOT NULL,
                metadata_json TEXT NOT NULL
            )
            """
        )


def plan(root: str = "", *, focus: str = "", max_files: int = 80) -> dict[str, Any]:
    init_db()
    root_path = Path(root or ".").resolve()
    findings = _scan(root_path, focus=focus, max_files=max_files)
    risk = "medium" if len(findings) > 5 else "low"
    steps = _steps(findings)
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            "INSERT INTO refactor_plans(timestamp, root, focus, findings_json, plan_json, risk_level, metadata_json) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (_now(), str(root_path), _clean(focus), _json_dumps(findings), _json_dumps(steps), risk, _json_dumps({"max_files": max_files})),
        )
        row = conn.execute("SELECT * FROM refactor_plans WHERE id=?", (int(cursor.lastrowid),)).fetchone()
    item = _row(row)
    item["summary"] = f"Found {len(findings)} refactor candidate(s); risk {risk}."
    return item


def recent(limit: int = 20) -> list[dict[str, Any]]:
    init_db()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM refactor_plans ORDER BY id DESC LIMIT ?", (max(1, min(100, int(limit or 20))),)).fetchall()
    return [_row(row) for row in rows]


def status() -> dict[str, Any]:
    items = recent(limit=6)
    return {"recent": items, "summary": f"{len(items)} refactor plan(s) available."}


def wipe_all() -> None:
    init_db()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.execute("DELETE FROM refactor_plans")


def _scan(root: Path, *, focus: str, max_files: int) -> list[dict[str, Any]]:
    if not root.exists():
        return [{"kind": "missing_root", "path": str(root), "risk": "low", "reason": "Root path does not exist."}]
    findings: list[dict[str, Any]] = []
    files = [path for path in root.rglob("*") if path.is_file() and path.suffix.lower() in CODE_EXTENSIONS]
    for path in files[: max(1, min(500, max_files))]:
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        rel = str(path.relative_to(root)) if path.is_relative_to(root) else str(path)
        lines = text.splitlines()
        max_file_lines = int(config_value("codebase_standards_max_file_lines", 300))
        if len(lines) > max_file_lines:
            findings.append({"kind": "large_file", "path": rel, "risk": "medium", "reason": f"{len(lines)} lines; preferred limit is {max_file_lines}. Consider splitting responsibilities."})
        todo_count = sum(1 for line in lines if "todo" in line.lower() or "fixme" in line.lower())
        if todo_count:
            findings.append({"kind": "todo_debt", "path": rel, "risk": "low", "reason": f"{todo_count} TODO/FIXME marker(s)."})
        if re.search(r"\beval\s*\(|shell\s*=\s*True|subprocess\.[^(]+\(", text):
            findings.append({"kind": "security_review", "path": rel, "risk": "high", "reason": "Shell/eval/subprocess pattern needs defensive review."})
        duplicates = [line for line, count in Counter(line.strip() for line in lines if len(line.strip()) > 60).items() if count >= 3]
        if duplicates:
            findings.append({"kind": "duplication", "path": rel, "risk": "medium", "reason": "Repeated long lines suggest extractable helpers."})
        if focus and focus.lower() in rel.lower():
            findings.append({"kind": "focus_file", "path": rel, "risk": "low", "reason": "Matches requested refactor focus."})
    return findings[:50]


def _steps(findings: list[dict[str, Any]]) -> list[str]:
    if not findings:
        return ["No obvious refactor needed from the lightweight scan.", "Keep tests green and avoid cosmetic churn."]
    steps = ["Start with high-risk findings, one small change set at a time."]
    if any(item["kind"] == "security_review" for item in findings):
        steps.append("Review shell/eval/subprocess paths first and add focused tests before changing behavior.")
    if any(item["kind"] == "large_file" for item in findings):
        steps.append("Split large files by stable responsibilities after adding regression coverage.")
    if any(item["kind"] == "duplication" for item in findings):
        steps.append("Extract repeated logic only when it is truly the same behavior.")
    steps.append("Run compile/build and the closest affected tests before claiming completion.")
    return steps


def _row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "timestamp": str(row["timestamp"]),
        "root": str(row["root"]),
        "focus": str(row["focus"]),
        "findings": _json_loads(row["findings_json"], []),
        "plan": _json_loads(row["plan_json"], []),
        "risk_level": str(row["risk_level"]),
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
