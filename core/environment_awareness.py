"""Current PC/environment context that lets Friday notice useful moments."""

from __future__ import annotations

import datetime as dt
import json
import sqlite3
import threading
from pathlib import Path
from typing import Any

try:
    import psutil
except Exception:  # pragma: no cover - optional on some machines
    psutil = None

from core import pc_awareness
from core.config import DATA_DIR, ensure_runtime_dirs

DB_PATH = DATA_DIR / "environment_awareness.sqlite3"
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
            CREATE TABLE IF NOT EXISTS environment_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                active_window TEXT NOT NULL,
                battery_percent REAL,
                plugged INTEGER NOT NULL,
                wifi_hint TEXT NOT NULL,
                idle_hint TEXT NOT NULL,
                open_project TEXT NOT NULL,
                recommendation TEXT NOT NULL,
                payload_json TEXT NOT NULL
            )
            """
        )


def snapshot(*, force_refresh: bool = False) -> dict[str, Any]:
    init_db()
    pc = pc_awareness.snapshot(force_refresh=force_refresh)
    active = str(pc.get("active_window") or "")
    battery = _battery()
    net = _network_hint()
    project = _infer_open_project(active, pc)
    recommendation = _recommend(active, battery, project)
    payload = {
        "timestamp": _now(),
        "active_window": active,
        "battery": battery,
        "wifi_hint": net,
        "open_project": project,
        "running_apps": (pc.get("running_apps") or [])[:12],
        "recommendation": recommendation,
    }
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.execute(
            """
            INSERT INTO environment_snapshots(timestamp, active_window, battery_percent, plugged, wifi_hint, idle_hint, open_project, recommendation, payload_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload["timestamp"],
                active[:300],
                battery.get("percent"),
                1 if battery.get("plugged") else 0,
                net[:200],
                "unknown",
                project[:500],
                recommendation[:1000],
                _json_dumps(payload),
            ),
        )
    payload["summary"] = recommendation or f"Environment captured. Active window: {active or 'unknown'}."
    return payload


def latest() -> dict[str, Any] | None:
    init_db()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM environment_snapshots ORDER BY id DESC LIMIT 1").fetchone()
    return _row(row) if row else None


def recent(limit: int = 20) -> list[dict[str, Any]]:
    init_db()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM environment_snapshots ORDER BY id DESC LIMIT ?", (max(1, min(100, int(limit or 20))),)).fetchall()
    return [_row(row) for row in rows]


def status() -> dict[str, Any]:
    current = latest() or snapshot()
    return {"latest": current, "recent": recent(limit=6), "summary": current.get("recommendation") or current.get("summary", "Environment awareness ready.")}


def wipe_all() -> None:
    init_db()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.execute("DELETE FROM environment_snapshots")


def _battery() -> dict[str, Any]:
    if psutil is None or not hasattr(psutil, "sensors_battery"):
        return {"available": False, "percent": None, "plugged": False}
    try:
        battery = psutil.sensors_battery()
    except Exception:
        battery = None
    if not battery:
        return {"available": False, "percent": None, "plugged": False}
    return {"available": True, "percent": float(battery.percent), "plugged": bool(battery.power_plugged)}


def _network_hint() -> str:
    if psutil is None:
        return "network status unavailable"
    try:
        up = [name for name, stat in psutil.net_if_stats().items() if stat.isup]
    except Exception:
        up = []
    if not up:
        return "no active network interface detected"
    wifi = [name for name in up if any(term in name.lower() for term in ("wi-fi", "wifi", "wireless", "wlan"))]
    return f"active: {', '.join((wifi or up)[:4])}"


def _infer_open_project(active: str, pc: dict[str, Any]) -> str:
    if "visual studio code" in active.lower() or "vscode" in active.lower():
        title = active
        for suffix in (" - Visual Studio Code - Insiders", " - Visual Studio Code", " - VS Code"):
            if suffix.lower() in title.lower():
                title = title[: title.lower().rfind(suffix.lower())]
                break
        parts = [part.strip() for part in title.split(" - ") if part.strip()]
        return parts[-1] if parts else "VS Code project"
    for app in pc.get("running_apps") or []:
        name = str(app.get("name") or "").lower()
        if name in {"code", "code - insiders", "pycharm", "webstorm"}:
            return str(app.get("name") or "open project")
    return ""


def _recommend(active: str, battery: dict[str, Any], project: str) -> str:
    if battery.get("available") and not battery.get("plugged") and battery.get("percent") is not None and float(battery["percent"]) <= 25:
        return "Battery is low. Friday should reduce brightness, pause heavy agents, and save work."
    if project:
        return f"You appear to be in {project}. Friday can start the API/dashboard, check tests, or load project context."
    if "chrome" in active.lower() or "edge" in active.lower():
        return "Browser is active. Friday can use the extension context for page-aware help."
    return "Environment awareness is watching for useful work moments."


def _row(row: sqlite3.Row) -> dict[str, Any]:
    payload = _json_loads(row["payload_json"], {})
    return {
        "id": int(row["id"]),
        "timestamp": str(row["timestamp"]),
        "active_window": str(row["active_window"]),
        "battery_percent": row["battery_percent"],
        "plugged": bool(row["plugged"]),
        "wifi_hint": str(row["wifi_hint"]),
        "idle_hint": str(row["idle_hint"]),
        "open_project": str(row["open_project"]),
        "recommendation": str(row["recommendation"]),
        "payload": payload,
        "summary": str(row["recommendation"]) or "Environment snapshot captured.",
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
