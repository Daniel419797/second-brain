"""Local PC awareness inventory for Friday.

This module keeps Friday aware of the current Windows environment without
pretending it has privileged app APIs. It observes what the OS exposes:
running processes, installed-program registry entries, Start Menu shortcuts,
Desktop shortcuts, and the active window.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import re
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

try:
    import psutil
except Exception:  # pragma: no cover - optional dependency in scaffold tests
    psutil = None

try:
    import winreg
except Exception:  # pragma: no cover - non-Windows test runners
    winreg = None

from core.config import DATA_DIR, config_value, ensure_runtime_dirs, reload_config

DB_PATH = DATA_DIR / "pc_awareness.sqlite3"
_LOCK = threading.Lock()
_CACHE: dict[str, Any] | None = None
_CACHE_TIME = 0.0


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
            CREATE TABLE IF NOT EXISTS pc_awareness_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                summary TEXT NOT NULL,
                active_window TEXT NOT NULL,
                running_json TEXT NOT NULL,
                installed_json TEXT NOT NULL,
                shortcuts_json TEXT NOT NULL,
                stats_json TEXT NOT NULL
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_pc_awareness_time ON pc_awareness_snapshots(timestamp)")


def snapshot(*, force_refresh: bool = False) -> dict[str, Any]:
    """Return a bounded inventory of the current PC state."""
    global _CACHE, _CACHE_TIME
    if not bool(config_value("pc_awareness_enabled", True)):
        return {
            "available": False,
            "summary": "PC awareness is disabled in config.",
            "running_apps": [],
            "installed_apps": [],
            "shortcuts": [],
            "desktop_apps": [],
            "home_screen_apps": [],
            "stats": {},
        }
    ttl = max(1.0, float(config_value("pc_awareness_cache_seconds", 300)))
    now = time.time()
    if _CACHE and not force_refresh and now - _CACHE_TIME <= ttl:
        return dict(_CACHE)
    payload = _build_snapshot()
    _persist_snapshot(payload)
    _CACHE = payload
    _CACHE_TIME = now
    return dict(payload)


def refresh() -> dict[str, Any]:
    return snapshot(force_refresh=True)


def running_apps(*, limit: int = 0) -> list[dict[str, Any]]:
    items = snapshot().get("running_apps") or []
    return items[: _limit(limit, "pc_awareness_max_running_apps", 80)]


def installed_apps(*, limit: int = 0) -> list[dict[str, Any]]:
    items = snapshot().get("installed_apps") or []
    return items[: _limit(limit, "pc_awareness_max_installed_apps", 400)]


def desktop_apps(*, limit: int = 0) -> list[dict[str, Any]]:
    items = snapshot().get("desktop_apps") or []
    return items[: _limit(limit, "pc_awareness_max_shortcuts", 500)]


def start_menu_apps(*, limit: int = 0) -> list[dict[str, Any]]:
    items = [
        item
        for item in snapshot().get("shortcuts") or []
        if str(item.get("source") or "").startswith("start_menu")
    ]
    return items[: _limit(limit, "pc_awareness_max_shortcuts", 500)]


def find_app(query: str) -> dict[str, Any]:
    """Find the best known local or web app launch target for a spoken name."""
    needle = _norm(query)
    if not needle:
        return {"found": False, "query": query, "reason": "empty query"}
    candidates: list[dict[str, Any]] = []
    cfg_apps = reload_config().get("allowed_apps", {})
    if isinstance(cfg_apps, dict):
        for name, target in cfg_apps.items():
            candidates.append(
                {
                    "source": "configured",
                    "name": str(name),
                    "path": str(target),
                    "launch_target": str(target),
                }
            )
    state = snapshot()
    for bucket in ("desktop_apps", "shortcuts", "installed_apps", "running_apps"):
        for item in state.get(bucket) or []:
            candidates.append(dict(item))
    scored = []
    for item in candidates:
        score = _match_score(needle, str(item.get("name") or ""))
        if not score:
            continue
        if item.get("launch_target") or item.get("path") or item.get("exe"):
            score += 8
        source = str(item.get("source") or "")
        if "desktop" in source:
            score += 5
        elif "start_menu" in source or source == "configured":
            score += 4
        scored.append((score, item))
    if not scored:
        return {"found": False, "query": query, "reason": "no matching app in inventory"}
    scored.sort(key=lambda pair: (-pair[0], len(str(pair[1].get("name") or ""))))
    score, best = scored[0]
    if score < 30:
        return {"found": False, "query": query, "reason": "low confidence match", "best": best, "score": score}
    launch_target = str(best.get("launch_target") or best.get("path") or best.get("exe") or "")
    return {
        "found": True,
        "query": query,
        "score": score,
        "name": best.get("name") or query,
        "source": best.get("source") or "",
        "launch_target": launch_target,
        "item": best,
    }


def latest_snapshot() -> dict[str, Any] | None:
    init_db()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM pc_awareness_snapshots ORDER BY id DESC LIMIT 1").fetchone()
    return _row_to_snapshot(row) if row else None


def planner_context() -> dict[str, Any]:
    state = snapshot()
    running = state.get("running_apps") or []
    desktop = state.get("desktop_apps") or []
    installed = state.get("installed_apps") or []
    return {
        "summary": state.get("summary") or "",
        "active_window": state.get("active_window") or "",
        "running_apps": [{"name": item.get("name"), "pid": item.get("pid")} for item in running[:20]],
        "desktop_apps": [{"name": item.get("name"), "source": item.get("source")} for item in desktop[:30]],
        "installed_app_names": [item.get("name") for item in installed[:60]],
        "stats": state.get("stats") or {},
    }


def wipe_all() -> None:
    global _CACHE, _CACHE_TIME
    init_db()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.execute("DELETE FROM pc_awareness_snapshots")
    _CACHE = None
    _CACHE_TIME = 0.0


def _build_snapshot() -> dict[str, Any]:
    running = _collect_running_apps()
    installed = _collect_installed_apps()
    shortcuts = _collect_shortcuts()
    desktop = [item for item in shortcuts if "desktop" in str(item.get("source") or "")]
    active_window = _active_window()
    stats = {
        "running_apps": len(running),
        "installed_apps": len(installed),
        "shortcuts": len(shortcuts),
        "desktop_apps": len(desktop),
    }
    payload = {
        "available": True,
        "timestamp": _now(),
        "active_window": active_window,
        "running_apps": running,
        "installed_apps": installed,
        "shortcuts": shortcuts,
        "desktop_apps": desktop,
        "home_screen_apps": desktop,
        "stats": stats,
    }
    payload["summary"] = _summary(payload)
    return payload


def _collect_running_apps() -> list[dict[str, Any]]:
    if psutil is None:
        return []
    limit = _limit(0, "pc_awareness_max_running_apps", 80)
    items: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for proc in psutil.process_iter(["pid", "name", "exe", "cmdline", "create_time"]):
        try:
            info = proc.info
        except Exception:
            continue
        name = _clean(info.get("name") or "")
        exe = _clean(info.get("exe") or "")
        if not name:
            continue
        key = (name.lower(), exe.lower())
        if key in seen:
            continue
        seen.add(key)
        items.append(
            {
                "source": "running",
                "name": name,
                "pid": int(info.get("pid") or 0),
                "exe": exe,
                "launch_target": exe if exe and Path(exe).exists() else "",
                "create_time": float(info.get("create_time") or 0.0),
            }
        )
    items.sort(key=lambda item: str(item.get("name") or "").lower())
    return items[:limit]


def _collect_installed_apps() -> list[dict[str, Any]]:
    if winreg is None:
        return []
    limit = _limit(0, "pc_awareness_max_installed_apps", 400)
    roots = [
        (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_LOCAL_MACHINE, r"Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
    ]
    items: list[dict[str, Any]] = []
    seen: set[str] = set()
    for root, path in roots:
        try:
            with winreg.OpenKey(root, path) as key:
                count = winreg.QueryInfoKey(key)[0]
                for index in range(count):
                    try:
                        sub_name = winreg.EnumKey(key, index)
                        with winreg.OpenKey(key, sub_name) as sub_key:
                            item = _installed_from_key(sub_key)
                    except OSError:
                        continue
                    name = _clean(item.get("name") or "")
                    if not name or name.lower() in seen:
                        continue
                    seen.add(name.lower())
                    items.append(item)
        except OSError:
            continue
    items.sort(key=lambda item: str(item.get("name") or "").lower())
    return items[:limit]


def _installed_from_key(key: Any) -> dict[str, Any]:
    def value(name: str) -> str:
        try:
            return _clean(winreg.QueryValueEx(key, name)[0])
        except OSError:
            return ""

    display_name = value("DisplayName")
    install_location = value("InstallLocation")
    display_icon = value("DisplayIcon")
    launch_target = _icon_launch_target(display_icon) or _install_location_exe(display_name, install_location)
    return {
        "source": "installed",
        "name": display_name,
        "version": value("DisplayVersion"),
        "publisher": value("Publisher"),
        "install_location": install_location,
        "display_icon": display_icon,
        "launch_target": launch_target,
    }


def _collect_shortcuts() -> list[dict[str, Any]]:
    limit = _limit(0, "pc_awareness_max_shortcuts", 500)
    items: list[dict[str, Any]] = []
    seen: set[str] = set()
    for source, root in _shortcut_roots():
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if path.suffix.lower() not in {".lnk", ".url", ".appref-ms"}:
                continue
            key = str(path).lower()
            if key in seen:
                continue
            seen.add(key)
            name = _shortcut_name(path)
            launch_target = str(path)
            url = ""
            if path.suffix.lower() == ".url":
                url = _url_shortcut_target(path)
                if url:
                    launch_target = url
            items.append(
                {
                    "source": source,
                    "name": name,
                    "path": str(path),
                    "url": url,
                    "launch_target": launch_target,
                }
            )
    items.sort(key=lambda item: (str(item.get("source") or ""), str(item.get("name") or "").lower()))
    return items[:limit]


def _shortcut_roots() -> list[tuple[str, Path]]:
    home = Path.home()
    roots = [
        ("desktop", home / "Desktop"),
        ("onedrive_desktop", home / "OneDrive" / "Desktop"),
        ("public_desktop", Path(os.environ.get("PUBLIC", r"C:\Users\Public")) / "Desktop"),
        ("start_menu_user", Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs"),
        ("start_menu_all", Path(os.environ.get("PROGRAMDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs"),
    ]
    unique: list[tuple[str, Path]] = []
    seen: set[str] = set()
    for source, root in roots:
        key = str(root).lower()
        if key and key not in seen:
            unique.append((source, root))
            seen.add(key)
    return unique


def _active_window() -> str:
    try:
        from tools import pc_control

        return _clean(pc_control.execute({"action": "active_window", "_permission_confirmed": True}))[:300]
    except Exception:
        return ""


def _persist_snapshot(payload: dict[str, Any]) -> None:
    init_db()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.execute(
            """
            INSERT INTO pc_awareness_snapshots(timestamp, summary, active_window, running_json, installed_json, shortcuts_json, stats_json)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(payload.get("timestamp") or _now()),
                str(payload.get("summary") or ""),
                str(payload.get("active_window") or ""),
                json.dumps(payload.get("running_apps") or [], ensure_ascii=True, default=str),
                json.dumps(payload.get("installed_apps") or [], ensure_ascii=True, default=str),
                json.dumps(payload.get("shortcuts") or [], ensure_ascii=True, default=str),
                json.dumps(payload.get("stats") or {}, ensure_ascii=True, default=str),
            ),
        )


def _row_to_snapshot(row: sqlite3.Row) -> dict[str, Any]:
    shortcuts = _loads(row["shortcuts_json"], [])
    desktop = [item for item in shortcuts if "desktop" in str(item.get("source") or "")]
    return {
        "available": True,
        "id": int(row["id"]),
        "timestamp": str(row["timestamp"]),
        "summary": str(row["summary"]),
        "active_window": str(row["active_window"]),
        "running_apps": _loads(row["running_json"], []),
        "installed_apps": _loads(row["installed_json"], []),
        "shortcuts": shortcuts,
        "desktop_apps": desktop,
        "home_screen_apps": desktop,
        "stats": _loads(row["stats_json"], {}),
    }


def _summary(payload: dict[str, Any]) -> str:
    stats = payload.get("stats") or {}
    active = payload.get("active_window") or "no active window detected"
    running_names = [item.get("name") for item in (payload.get("running_apps") or [])[:5] if item.get("name")]
    desktop_names = [item.get("name") for item in (payload.get("desktop_apps") or [])[:4] if item.get("name")]
    parts = [
        f"active window: {active}",
        f"{stats.get('running_apps', 0)} running app entries",
        f"{stats.get('installed_apps', 0)} installed app entries",
        f"{stats.get('desktop_apps', 0)} Desktop/Home-screen shortcuts",
    ]
    if running_names:
        parts.append("running includes " + ", ".join(running_names))
    if desktop_names:
        parts.append("desktop includes " + ", ".join(desktop_names))
    return "; ".join(parts)


def _match_score(needle: str, candidate: str) -> int:
    hay = _norm(candidate)
    if not hay:
        return 0
    if hay == needle:
        return 100
    if hay.startswith(needle):
        return 90
    if needle in hay:
        return 75
    words = [word for word in needle.split() if word]
    if words and all(word in hay for word in words):
        return 70
    overlap = sum(1 for word in words if word in hay)
    return overlap * 25


def _limit(value: int, config_key: str, default: int) -> int:
    try:
        raw = int(value or config_value(config_key, default))
    except Exception:
        raw = default
    return max(1, min(1000, raw))


def _shortcut_name(path: Path) -> str:
    name = path.stem.replace(".lnk", "")
    return _clean(re.sub(r"\s+-\s+Shortcut$", "", name, flags=re.IGNORECASE))


def _url_shortcut_target(path: Path) -> str:
    try:
        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            if line.lower().startswith("url="):
                return _clean(line.split("=", 1)[1])
    except OSError:
        return ""
    return ""


def _icon_launch_target(value: str) -> str:
    raw = _clean(value).strip('"')
    if not raw:
        return ""
    if "," in raw:
        raw = raw.rsplit(",", 1)[0].strip().strip('"')
    if raw.lower().endswith(".exe") and Path(raw).exists():
        return raw
    return ""


def _install_location_exe(display_name: str, install_location: str) -> str:
    cleaned_location = _clean(install_location).strip('"')
    if not cleaned_location:
        return ""
    root = Path(cleaned_location)
    if not display_name or not root.exists() or not root.is_dir():
        return ""
    words = [word for word in _norm(display_name).split() if len(word) >= 3]
    try:
        exes = list(root.glob("*.exe"))[:30]
    except OSError:
        return ""
    if not exes:
        return ""
    for exe in exes:
        name = _norm(exe.stem)
        if any(word in name for word in words):
            return str(exe)
    return str(exes[0]) if len(exes) == 1 else ""


def _loads(value: str, default: Any) -> Any:
    try:
        parsed = json.loads(value or "")
    except Exception:
        return default
    return parsed if parsed is not None else default


def _norm(value: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).split())


def _clean(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds")
