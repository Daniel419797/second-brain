"""Offline Survival Mode for reduced but reliable local operation."""

from __future__ import annotations

import datetime as dt
import socket
import sqlite3
import threading
from pathlib import Path
from typing import Any

from core.config import DATA_DIR, config_value, ensure_runtime_dirs

DB_PATH = DATA_DIR / "offline_survival.sqlite3"
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
            CREATE TABLE IF NOT EXISTS mode_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                mode TEXT NOT NULL,
                reason TEXT NOT NULL
            )
            """
        )


def status() -> dict[str, Any]:
    connectivity = _connectivity()
    online = bool(connectivity["online"])
    providers = {
        "local_llm": str(config_value("ollama_model", "")),
        "local_stt": str(config_value("stt_fallback_model", "")),
        "local_memory": True,
        "local_actions": True,
    }
    mode = current_mode()
    recommended = "offline_survival" if not online else "normal_online"
    return {
        "online": online,
        "mode": mode,
        "recommended": recommended,
        "connectivity": connectivity,
        "providers": providers,
        "summary": f"{'Online' if online else 'Offline'}; recommended mode is {recommended}.",
    }


def activate(reason: str = "manual") -> dict[str, Any]:
    return _record_mode("offline_survival", reason)


def deactivate(reason: str = "manual") -> dict[str, Any]:
    return _record_mode("normal_online", reason)


def current_mode() -> str:
    init_db()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        row = conn.execute("SELECT mode FROM mode_events ORDER BY id DESC LIMIT 1").fetchone()
    return str(row[0]) if row else "auto"


def recent(limit: int = 20) -> list[dict[str, Any]]:
    init_db()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM mode_events ORDER BY id DESC LIMIT ?", (max(1, min(100, int(limit))),)).fetchall()
    return [{key: row[key] for key in row.keys()} for row in rows]


def wipe_all() -> None:
    init_db()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.execute("DELETE FROM mode_events")


def _record_mode(mode: str, reason: str) -> dict[str, Any]:
    init_db()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.execute("INSERT INTO mode_events(timestamp, mode, reason) VALUES (?, ?, ?)", (_now(), mode, str(reason or "")))
    return status() | {"summary": f"Mode set to {mode}."}


def _connectivity() -> dict[str, Any]:
    timeout = float(config_value("offline_survival_check_timeout_seconds", 1.0))
    hosts = _hosts()
    errors = []
    for host, port in hosts:
        try:
            with socket.create_connection((host, port), timeout=timeout):
                return {"online": True, "checked_at": _now(), "host": host, "port": port, "errors": errors}
        except OSError as exc:
            errors.append({"host": host, "port": port, "error": str(exc)})
    return {"online": False, "checked_at": _now(), "host": "", "port": 0, "errors": errors}


def _hosts() -> list[tuple[str, int]]:
    raw = str(config_value("offline_survival_check_hosts", "1.1.1.1:53,8.8.8.8:53,google.com:443") or "")
    hosts: list[tuple[str, int]] = []
    for part in raw.split(","):
        text = part.strip()
        if not text:
            continue
        if ":" in text:
            host, port_text = text.rsplit(":", 1)
            try:
                hosts.append((host.strip(), int(port_text)))
            except ValueError:
                continue
        else:
            hosts.append((text, 443))
    return hosts or [("1.1.1.1", 53), ("8.8.8.8", 53)]


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds")
