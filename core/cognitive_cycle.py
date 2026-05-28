"""Low-frequency coordinator for Friday's cognition subsystems."""

from __future__ import annotations

import datetime as dt
import threading
import time
from typing import Any

from core import adaptive_attention, goal_regulation, long_term_learning, self_reflection, world_model
from core.config import config_value

_STOP = threading.Event()
_THREAD: threading.Thread | None = None
_LOCK = threading.Lock()
_STATE: dict[str, Any] = {
    "running": False,
    "started_at": "",
    "last_run_at": "",
    "last_result": {},
    "last_error": "",
    "light_mode": False,
}


def start(*, light_mode: bool = False) -> bool:
    if not bool(config_value("cognitive_cycle_enabled", False)):
        return False
    global _THREAD
    with _LOCK:
        if _THREAD and _THREAD.is_alive():
            return True
        _STOP.clear()
        _STATE.update({"running": True, "started_at": _now(), "last_error": "", "light_mode": bool(light_mode)})
        _THREAD = threading.Thread(target=_loop, args=(bool(light_mode),), name="FridayCognitiveCycle", daemon=True)
        _THREAD.start()
    return True


def stop(timeout: float = 2.0) -> None:
    _STOP.set()
    thread = _THREAD
    if thread and thread.is_alive():
        thread.join(timeout=timeout)
    with _LOCK:
        _STATE["running"] = bool(_THREAD and _THREAD.is_alive())


def status() -> dict[str, Any]:
    with _LOCK:
        state = dict(_STATE)
    state["running"] = bool(_THREAD and _THREAD.is_alive())
    return state


def run_once(trigger: str = "manual", *, light_mode: bool | None = None) -> dict[str, Any]:
    light = bool(_STATE.get("light_mode")) if light_mode is None else bool(light_mode)
    result: dict[str, Any] = {"trigger": trigger, "light_mode": light, "ran_at": _now()}
    snapshot = world_model.capture_snapshot(source=f"cycle:{trigger}", confidence=0.55)
    result["world_snapshot"] = snapshot
    world_model.resolve_expectations(snapshot.get("summary", ""))
    result["attention"] = adaptive_attention.update_profile()
    result["regulation"] = goal_regulation.current_regulation()
    if not light:
        result["learning_review"] = long_term_learning.run_reviews(limit=5)
        if _reflection_due():
            result["reflection"] = self_reflection.run_reflection(trigger=trigger, minutes=int(config_value("self_reflection_window_minutes", 60)))
    with _LOCK:
        _STATE.update({"last_run_at": result["ran_at"], "last_result": result, "last_error": ""})
    return result


def _loop(light_mode: bool) -> None:
    interval = max(15.0, float(config_value("cognitive_cycle_interval_seconds", 60.0)))
    while not _STOP.is_set():
        try:
            run_once("scheduled", light_mode=light_mode)
        except Exception as exc:
            with _LOCK:
                _STATE["last_error"] = str(exc)
        _STOP.wait(interval)
    with _LOCK:
        _STATE["running"] = False


def _reflection_due() -> bool:
    last = str(_STATE.get("last_result", {}).get("reflection", {}).get("started_at") or "")
    if not last:
        return True
    try:
        stamp = dt.datetime.fromisoformat(last)
    except Exception:
        return True
    gap = dt.datetime.now(dt.timezone.utc).astimezone() - stamp
    return gap.total_seconds() >= float(config_value("self_reflection_interval_minutes", 30)) * 60.0


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds")
