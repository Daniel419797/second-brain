"""Backup/version guardian for snapshots, protected paths, and rollback notes."""

from __future__ import annotations

import datetime as dt
import json
import sqlite3
import threading
from pathlib import Path
from typing import Any

from core import backup_recovery, personal_safety_guardian, trust_proof
from core.config import DATA_DIR, ROOT_DIR, ensure_runtime_dirs

DB_PATH = DATA_DIR / "version_guardian.sqlite3"
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
            CREATE TABLE IF NOT EXISTS version_guardian_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                kind TEXT NOT NULL,
                summary TEXT NOT NULL,
                payload_json TEXT NOT NULL
            )
            """
        )


def snapshot_files(paths: list[str] | str | None = None, *, label: str = "mission snapshot", mission_id: int | None = None) -> dict[str, Any]:
    init_db()
    items = paths if isinstance(paths, list) else [paths] if paths else []
    if not items:
        items = [str(ROOT_DIR / "config.json")]
    backups: list[dict[str, Any]] = []
    skipped: list[str] = []
    for raw in items:
        path = _safe_path(raw)
        if not path.exists() or not path.is_file():
            skipped.append(str(path))
            continue
        backups.append(backup_recovery.backup_file(str(path), label=label))
    summary = f"Version guardian saved {len(backups)} snapshot(s), skipped {len(skipped)} path(s)."
    payload = {"backups": backups, "skipped": skipped, "mission_id": mission_id, "label": label, "summary": summary}
    _record("snapshot", summary, payload)
    trust_proof.create_report(
        "Version guardian snapshot",
        changed=["Created rollback snapshots only."],
        tested=[summary],
        evidence=[str(item.get("backup_path") or item.get("summary") or "") for item in backups],
        risks=skipped,
        mission_id=mission_id,
        confidence=0.85 if backups else 0.45,
        metadata={"source": "version_guardian"},
    )
    return payload


def preflight(instruction: str = "", paths: list[str] | str | None = None) -> dict[str, Any]:
    items = paths if isinstance(paths, list) else [paths] if paths else []
    checks = [personal_safety_guardian.preflight_action(instruction, path=str(_safe_path(path))) for path in items] if items else [personal_safety_guardian.preflight_action(instruction)]
    protected = [str(_safe_path(path)) for path in items if _is_protected(path)]
    requires_snapshot = any("delete" in str(instruction).lower() or "overwrite" in str(instruction).lower() for _ in [0]) or bool(protected)
    summary = "Version preflight requires approval/snapshot." if requires_snapshot or protected else "Version preflight found no obvious protected path."
    payload = {"checks": checks, "protected_paths": protected, "requires_snapshot": requires_snapshot, "summary": summary}
    _record("preflight", summary, payload)
    return payload


def rollback_notes(mission_id: int | None = None, *, root: str | Path = "", notes: str = "") -> dict[str, Any]:
    payload = {
        "mission_id": mission_id,
        "root": str(_safe_path(root or ROOT_DIR)),
        "notes": _clean(notes) or "Use listed backup snapshots and proof report evidence to roll back mission changes.",
    }
    payload["summary"] = f"Rollback notes recorded for {payload['root']}."
    _record("rollback_notes", payload["summary"], payload)
    return payload


def status() -> dict[str, Any]:
    events = recent_events(limit=10)
    return {"events": events, "summary": events[0]["summary"] if events else "Version guardian is ready."}


def recent_events(limit: int = 20) -> list[dict[str, Any]]:
    init_db()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM version_guardian_events ORDER BY id DESC LIMIT ?", (max(1, min(100, int(limit or 20))),)).fetchall()
    return [_row(row) for row in rows]


def wipe_all() -> None:
    init_db()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.execute("DELETE FROM version_guardian_events")


def _record(kind: str, summary: str, payload: dict[str, Any]) -> int:
    init_db()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        cursor = conn.execute(
            "INSERT INTO version_guardian_events(timestamp, kind, summary, payload_json) VALUES (?, ?, ?, ?)",
            (_now(), _clean(kind), _clean(summary)[:1000], _json_dumps(payload)),
        )
    return int(cursor.lastrowid)


def _safe_path(path: str | Path) -> Path:
    raw = Path(path or ROOT_DIR).expanduser()
    if not raw.is_absolute():
        raw = ROOT_DIR / raw
    return raw.resolve()


def _is_protected(path: str | Path) -> bool:
    text = str(path or "").lower()
    return ".env" in text or "credential" in text or "secret" in text or "config.json" in text


def _row(row: sqlite3.Row) -> dict[str, Any]:
    return {"id": int(row["id"]), "timestamp": str(row["timestamp"]), "kind": str(row["kind"]), "summary": str(row["summary"]), "payload": _json_loads(row["payload_json"], {})}


def _clean(value: Any) -> str:
    return " ".join(str(value or "").replace("\x00", " ").strip().split())


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, default=str)


def _json_loads(value: str, default: Any) -> Any:
    try:
        return json.loads(value or "")
    except Exception:
        return default


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds")

