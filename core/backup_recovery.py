"""Backup and recovery guardrails for important Friday/user files."""

from __future__ import annotations

import datetime as dt
import json
import shutil
import sqlite3
import threading
from pathlib import Path
from typing import Any

from core.config import DATA_DIR, ROOT_DIR, config_value, ensure_runtime_dirs

DB_PATH = DATA_DIR / "backup_recovery.sqlite3"
BACKUP_DIR = DATA_DIR / "backups"
PROTECTED_NAMES = {".env", ".env.local", "config.json"}
_LOCK = threading.Lock()


def init_db(path: Path | None = None) -> None:
    ensure_runtime_dirs()
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    db_path = path or DB_PATH
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path, timeout=10) as conn:
        try:
            conn.execute("PRAGMA journal_mode=WAL")
        except sqlite3.OperationalError:
            pass
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS backups (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                label TEXT NOT NULL,
                source_path TEXT NOT NULL,
                backup_path TEXT NOT NULL,
                size INTEGER NOT NULL,
                metadata_json TEXT NOT NULL
            )
            """
        )


def snapshot_config(label: str = "config snapshot") -> dict[str, Any]:
    paths = [ROOT_DIR / "config.json", ROOT_DIR / ".env.example"]
    if bool(config_value("backup_allow_env_snapshot", False)):
        paths.append(ROOT_DIR / ".env")
    backed = [backup_file(path, label=label) for path in paths if path.exists()]
    return {"items": backed, "summary": f"Created {len(backed)} config backup items."}


def backup_file(path: str | Path, *, label: str = "") -> dict[str, Any]:
    init_db()
    source = _safe_source(path)
    if not source.exists() or not source.is_file():
        return {"ok": False, "summary": "File not found.", "source": str(source)}
    backup_root = BACKUP_DIR / _timestamp_slug()
    backup_root.mkdir(parents=True, exist_ok=True)
    destination = backup_root / source.name
    shutil.copy2(source, destination)
    now = _now()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            "INSERT INTO backups(timestamp, label, source_path, backup_path, size, metadata_json) VALUES (?, ?, ?, ?, ?, ?)",
            (now, label or "manual backup", str(source), str(destination), int(destination.stat().st_size), _json_dumps({"protected": is_protected_path(source)})),
        )
        row = conn.execute("SELECT * FROM backups WHERE id=?", (int(cursor.lastrowid),)).fetchone()
    return _backup_from_row(row) | {"ok": True, "summary": f"Backed up {source.name}."}


def list_backups(limit: int = 50) -> list[dict[str, Any]]:
    init_db()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM backups ORDER BY id DESC LIMIT ?", (max(1, min(200, int(limit))),)).fetchall()
    return [_backup_from_row(row) for row in rows]


def restore_backup(backup_id: int, *, confirm: bool = False) -> dict[str, Any]:
    item = get_backup(backup_id)
    if not item:
        return {"ok": False, "summary": "Backup not found."}
    source = Path(item["source_path"])
    backup = Path(item["backup_path"])
    if is_protected_path(source) and not confirm:
        return {"ok": False, "requires_confirmation": True, "summary": "Restore touches a protected file. Confirm before restoring."}
    if not backup.exists():
        return {"ok": False, "summary": "Backup file is missing."}
    shutil.copy2(backup, source)
    return {"ok": True, "summary": f"Restored {source.name}.", "source_path": str(source)}


def get_backup(backup_id: int) -> dict[str, Any] | None:
    init_db()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM backups WHERE id=?", (int(backup_id),)).fetchone()
    return _backup_from_row(row) if row else None


def risky_delete_guard(path: str | Path) -> dict[str, Any]:
    target = _safe_source(path)
    protected = is_protected_path(target)
    reason = "protected config/env file" if protected else "ordinary file"
    return {
        "path": str(target),
        "protected": protected,
        "requires_backup": protected or target.suffix.lower() in {".py", ".js", ".ts", ".tsx", ".json", ".md"},
        "summary": f"Delete guard: {reason}. Create a backup and ask for confirmation before deleting.",
    }


def is_protected_path(path: str | Path) -> bool:
    target = Path(path)
    try:
        resolved = target.resolve()
    except Exception:
        resolved = target
    return resolved.name.lower() in PROTECTED_NAMES or ".env" in resolved.name.lower()


def wipe_all() -> None:
    init_db()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.execute("DELETE FROM backups")


def _safe_source(path: str | Path) -> Path:
    candidate = Path(path).expanduser() if str(path or "").strip() else ROOT_DIR / "config.json"
    try:
        resolved = candidate.resolve()
    except Exception:
        resolved = ROOT_DIR / "config.json"
    return resolved


def _backup_from_row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "timestamp": str(row["timestamp"]),
        "label": str(row["label"]),
        "source_path": str(row["source_path"]),
        "backup_path": str(row["backup_path"]),
        "size": int(row["size"]),
        "metadata": _json_loads(row["metadata_json"], {}),
    }


def _timestamp_slug() -> str:
    return dt.datetime.now().strftime("%Y%m%d_%H%M%S_%f")


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, default=str)


def _json_loads(value: str, default: Any = None) -> Any:
    try:
        return json.loads(value or "")
    except Exception:
        return default


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds")
