"""Practical local safety guardian: secrets, protected files, risky deletes."""

from __future__ import annotations

import datetime as dt
import json
import re
import sqlite3
import threading
from pathlib import Path
from typing import Any

from core import backup_recovery
from core.config import DATA_DIR, ROOT_DIR, ensure_runtime_dirs

DB_PATH = DATA_DIR / "personal_safety_guardian.sqlite3"
_LOCK = threading.Lock()
SECRET_RE = re.compile(r"(?i)(api[_-]?key|secret|token|password|authorization)\s*[:=]\s*['\"]?([a-z0-9_\-.$/+=]{12,})")
IGNORE_DIRS = {".git", ".venv", "node_modules", ".next", "data", "__pycache__"}
PROTECTED_NAMES = {".env", ".env.local", ".env.production", "pyvenv.cfg"}


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
            CREATE TABLE IF NOT EXISTS safety_reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                root TEXT NOT NULL,
                status TEXT NOT NULL,
                summary TEXT NOT NULL,
                findings_json TEXT NOT NULL,
                metadata_json TEXT NOT NULL
            )
            """
        )


def scan(root: str | Path = "", *, max_files: int = 500) -> dict[str, Any]:
    init_db()
    base = _safe_root(root)
    findings: list[dict[str, Any]] = []
    for name in PROTECTED_NAMES:
        if (base / name).exists():
            findings.append({"kind": "protected_file", "severity": 3, "summary": f"{name} exists and should stay protected.", "path": str(base / name)})
    checked = 0
    for path in base.rglob("*"):
        if checked >= max(1, min(5000, int(max_files or 500))):
            break
        if not path.is_file() or any(part in IGNORE_DIRS for part in path.relative_to(base).parts):
            continue
        if path.name in PROTECTED_NAMES:
            continue
        if path.suffix.lower() not in {".py", ".js", ".jsx", ".ts", ".tsx", ".json", ".md", ".yml", ".yaml", ".env", ".txt"}:
            continue
        checked += 1
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")[:20000]
        except OSError:
            continue
        if SECRET_RE.search(text):
            findings.append({"kind": "possible_secret", "severity": 5, "summary": f"Possible secret-like value in {path.relative_to(base)}.", "path": str(path)})
    status = "attention" if any(int(item["severity"]) >= 4 for item in findings) else "ok"
    summary = f"Safety guardian scanned {checked} file(s), found {len(findings)} finding(s)."
    report = _persist(base, status, summary, findings, {"checked_files": checked})
    report["findings"] = findings
    return report


def preflight_action(instruction: str = "", *, path: str = "") -> dict[str, Any]:
    text = f"{instruction} {path}".lower()
    findings: list[dict[str, Any]] = []
    target = Path(path).name.lower() if path else ""
    if any(term in text for term in ("delete", "remove", "wipe", "overwrite", "replace")):
        findings.append({"kind": "risky_action", "severity": 4, "summary": "This looks destructive. Friday should ask first and create a backup/snapshot."})
    if target in PROTECTED_NAMES or ".env" in text:
        findings.append({"kind": "protected_env", "severity": 5, "summary": ".env or environment config is protected. Friday must not expose values and should ask before changing it."})
    backup_hint = None
    if path and findings:
        try:
            backup_hint = backup_recovery.risky_delete_guard(path)
        except Exception:
            backup_hint = {"summary": "Backup guard unavailable."}
    allowed_without_approval = not any(int(item["severity"]) >= 4 for item in findings)
    return {
        "allowed_without_approval": allowed_without_approval,
        "findings": findings,
        "backup_hint": backup_hint,
        "summary": "Safe to proceed without special approval." if allowed_without_approval else "Approval and backup are required before this action.",
    }


def recent(limit: int = 20) -> list[dict[str, Any]]:
    init_db()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM safety_reports ORDER BY id DESC LIMIT ?", (max(1, min(100, int(limit or 20))),)).fetchall()
    return [_row(row) for row in rows]


def status() -> dict[str, Any]:
    reports = recent(limit=6)
    latest = reports[0] if reports else {}
    return {"reports": reports, "latest": latest, "summary": latest.get("summary") or "Personal safety guardian is ready."}


def wipe_all() -> None:
    init_db()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.execute("DELETE FROM safety_reports")


def _persist(base: Path, status: str, summary: str, findings: list[dict[str, Any]], metadata: dict[str, Any]) -> dict[str, Any]:
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            "INSERT INTO safety_reports(timestamp, root, status, summary, findings_json, metadata_json) VALUES (?, ?, ?, ?, ?, ?)",
            (_now(), str(base), status, summary, _json_dumps(findings), _json_dumps(metadata)),
        )
        row = conn.execute("SELECT * FROM safety_reports WHERE id=?", (int(cursor.lastrowid),)).fetchone()
    return _row(row)


def _row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "timestamp": str(row["timestamp"]),
        "root": str(row["root"]),
        "status": str(row["status"]),
        "summary": str(row["summary"]),
        "findings": _json_loads(row["findings_json"], []),
        "metadata": _json_loads(row["metadata_json"], {}),
    }


def _safe_root(root: str | Path) -> Path:
    raw = Path(str(root or "").strip() or ROOT_DIR)
    if not raw.is_absolute():
        raw = ROOT_DIR / raw
    return raw.resolve()


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, default=str)


def _json_loads(value: str, default: Any) -> Any:
    try:
        return json.loads(value or "")
    except Exception:
        return default


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds")
