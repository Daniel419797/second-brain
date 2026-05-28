"""Realtime task autonomy loop: choose, act, verify, retry, or escalate."""

from __future__ import annotations

import datetime as dt
import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

from core import (
    approval_inbox,
    autonomy_control,
    autonomous_fix_loop,
    autonomous_qa_lab,
    awareness_graph,
    certainty_brain,
    mission_control,
    notification_center,
    personal_automation_daemon,
    project_memory,
    project_watchdog,
    release_manager,
    task_queue,
    trust_proof,
)
from core.config import DATA_DIR, config_value, ensure_runtime_dirs, resolve_coding_root

DB_PATH = DATA_DIR / "autonomy_engine.sqlite3"
_LOCK = threading.Lock()
_SUPERVISOR_LOCK = threading.Lock()
_SUPERVISOR_STOP = threading.Event()
_SUPERVISOR_THREAD: threading.Thread | None = None
_SUPERVISOR_STATE: dict[str, Any] = {
    "running": False,
    "started_at": "",
    "last_tick": "",
    "last_error": "",
    "ticks": 0,
    "workers_started": 0,
    "last_summary": "Autonomy supervisor has not started.",
}
_LAST_RUN_START = 0.0


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
            CREATE TABLE IF NOT EXISTS autonomy_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                goal TEXT NOT NULL,
                root TEXT NOT NULL,
                status TEXT NOT NULL,
                current_action TEXT NOT NULL,
                confidence REAL NOT NULL,
                risk_level TEXT NOT NULL,
                retries INTEGER NOT NULL,
                summary TEXT NOT NULL,
                evidence_json TEXT NOT NULL,
                missing_json TEXT NOT NULL,
                metadata_json TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS autonomy_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id INTEGER NOT NULL,
                timestamp TEXT NOT NULL,
                step INTEGER NOT NULL,
                action TEXT NOT NULL,
                status TEXT NOT NULL,
                summary TEXT NOT NULL,
                payload_json TEXT NOT NULL
            )
            """
        )


def start(goal: str = "", *, root: str | Path = "", metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    init_db()
    detected = detect_goal(goal, root=root)
    now = _now()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            """
            INSERT INTO autonomy_runs(created_at, updated_at, goal, root, status, current_action, confidence, risk_level, retries, summary, evidence_json, missing_json, metadata_json)
            VALUES (?, ?, ?, ?, 'running', 'detect_goal', ?, ?, 0, ?, ?, ?, ?)
            """,
            (
                now,
                now,
                detected["goal"],
                str(_safe_root(root)),
                float(detected["confidence"]),
                detected["risk_level"],
                detected["summary"],
                _json_dumps(detected["evidence"]),
                _json_dumps(detected["missing"]),
                _json_dumps(metadata or {}),
            ),
        )
        row = conn.execute("SELECT * FROM autonomy_runs WHERE id=?", (int(cursor.lastrowid),)).fetchone()
    run = _row(row)
    _event(run["id"], 0, "detect_goal", "done", detected["summary"], detected)
    return step(run["id"])


def step(run_id: int) -> dict[str, Any]:
    run = get(run_id)
    if not run:
        raise ValueError("autonomy run not found")
    if run["status"] not in {"running", "retrying"}:
        return run
    decision = choose_next_action(run)
    action = decision["action"]
    outcome = _act(run, decision)
    verified = _verify(run, decision, outcome)
    status = "completed" if verified["complete"] else ("blocked" if verified["blocked"] else "running")
    summary = verified["summary"]
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute(
            """
            UPDATE autonomy_runs
            SET updated_at=?, status=?, current_action=?, confidence=?, risk_level=?, retries=?, summary=?, evidence_json=?, missing_json=?
            WHERE id=?
            """,
            (
                _now(),
                status,
                action,
                float(verified["confidence"]),
                decision["risk_level"],
                int(run["retries"]) + (1 if status == "running" and not verified["complete"] else 0),
                summary,
                _json_dumps([*run.get("evidence", []), *verified.get("evidence", [])]),
                _json_dumps(verified.get("missing", [])),
                int(run_id),
            ),
        )
        row = conn.execute("SELECT * FROM autonomy_runs WHERE id=?", (int(run_id),)).fetchone()
    updated = _row(row)
    _event(run_id, len(events(run_id)) + 1, action, status, summary, {"decision": decision, "outcome": outcome, "verified": verified})
    if status == "blocked":
        _escalate(updated, verified)
    return updated


def run_until_blocked(goal: str = "", *, root: str | Path = "", max_steps: int = 5) -> dict[str, Any]:
    run = start(goal, root=root) if goal or not active_run() else active_run()
    for _ in range(max(0, min(25, int(max_steps or 5))) - 1):
        if run.get("status") != "running":
            break
        run = step(int(run["id"]))
    return run


def detect_goal(goal: str = "", *, root: str | Path = "") -> dict[str, Any]:
    if _clean(goal):
        return {"goal": _clean(goal), "confidence": 0.92, "risk_level": _risk(goal), "evidence": ["explicit user goal"], "missing": [], "summary": f"Using explicit goal: {_clean(goal)}"}
    mission = _first(mission_control.list_missions(status="running", limit=1))
    if mission:
        return {"goal": mission["goal"], "confidence": 0.84, "risk_level": "medium", "evidence": [f"active mission #{mission['id']}"], "missing": [], "summary": f"Detected active mission #{mission['id']}."}
    tasks = task_queue.list_tasks(status="active", limit=1) or task_queue.list_tasks(status="pending", limit=1)
    if tasks:
        task = tasks[0]
        return {"goal": task["title"], "confidence": 0.72, "risk_level": "medium", "evidence": [f"task #{task['id']} {task['status']}"], "missing": ["task-specific success proof"], "summary": f"Detected task queue goal #{task['id']}."}
    graph = _safe(lambda: awareness_graph.status().get("graph", {}), {})
    signals = graph.get("signals") or []
    if signals:
        top = signals[0]
        return {"goal": str(top.get("summary") or "respond to live signal"), "confidence": 0.62, "risk_level": "low", "evidence": [top], "missing": ["user intent"], "summary": "Detected goal from live awareness graph."}
    certainty_brain.record_missing("autonomy_goal", "No active explicit goal, mission, task, or strong live signal was found.", source="autonomy_engine")
    return {"goal": "wait for a clear goal or run low-risk maintenance checks", "confidence": 0.45, "risk_level": "low", "evidence": [], "missing": ["active goal"], "summary": "No clear goal detected; using low-risk maintenance mode."}


def choose_next_action(run: dict[str, Any]) -> dict[str, Any]:
    goal = str(run.get("goal") or "").lower()
    root = str(run.get("root") or "")
    if any(term in goal for term in ("error", "failed", "traceback", "crash", "broken")):
        return {"action": "fix_loop", "tool": "autonomous_fix_loop", "risk_level": "medium", "reason": "failure language in goal"}
    if any(term in goal for term in ("release", "deploy", "ship", "changelog")):
        return {"action": "release_prepare", "tool": "release_manager", "risk_level": "high", "reason": "release/deploy language needs release proof"}
    if any(term in goal for term in ("test", "qa", "verify", "proof")):
        return {"action": "qa_lab", "tool": "autonomous_qa_lab", "risk_level": "low", "reason": "verification language"}
    if root and Path(root).exists():
        return {"action": "project_watchdog", "tool": "project_watchdog", "risk_level": "low", "reason": "project root available"}
    return {"action": "automation_daemon", "tool": "personal_automation_daemon", "risk_level": "low", "reason": "low-risk default autonomy pass"}


def active_run() -> dict[str, Any] | None:
    init_db()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM autonomy_runs WHERE status IN ('running', 'retrying') ORDER BY id DESC LIMIT 1").fetchone()
    return _row(row) if row else None


def get(run_id: int) -> dict[str, Any] | None:
    init_db()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM autonomy_runs WHERE id=?", (int(run_id),)).fetchone()
    return _row(row) if row else None


def events(run_id: int, limit: int = 50) -> list[dict[str, Any]]:
    init_db()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM autonomy_events WHERE run_id=? ORDER BY id ASC LIMIT ?", (int(run_id), max(1, min(200, int(limit or 50))))).fetchall()
    return [_event_row(row) for row in rows]


def recent(limit: int = 20) -> list[dict[str, Any]]:
    init_db()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM autonomy_runs ORDER BY id DESC LIMIT ?", (max(1, min(200, int(limit or 20))),)).fetchall()
    return [_row(row) for row in rows]


def status() -> dict[str, Any]:
    run = active_run()
    runs = recent(limit=8)
    return {
        "active": run,
        "recent": runs,
        "supervisor": supervisor_status(),
        "control": autonomy_control.status(),
        "summary": run.get("summary") if run else f"{len(runs)} autonomy run(s) recorded.",
    }


def start_supervisor(worker_count: int | None = None) -> dict[str, Any]:
    if not bool(config_value("autonomy_supervisor_enabled", autonomy_control.full_autonomy_enabled())):
        _update_supervisor_state(running=False, last_summary="Autonomy supervisor disabled by config.")
        return supervisor_status()
    if not autonomy_control.enabled():
        _update_supervisor_state(running=False, last_summary="Autonomy control is disabled.")
        return supervisor_status()
    with _SUPERVISOR_LOCK:
        global _SUPERVISOR_THREAD
        if _SUPERVISOR_THREAD and _SUPERVISOR_THREAD.is_alive():
            already_running = True
        else:
            already_running = False
        if not already_running:
            _SUPERVISOR_STOP.clear()
            _SUPERVISOR_THREAD = threading.Thread(
                target=_supervisor_loop,
                args=(worker_count,),
                name="FridayAutonomySupervisor",
                daemon=True,
            )
            _SUPERVISOR_THREAD.start()
            _SUPERVISOR_STATE.update(
                {
                    "running": True,
                    "started_at": _now(),
                    "last_error": "",
                    "last_summary": "Autonomy supervisor started.",
                }
            )
    return supervisor_status()


def stop_supervisor(timeout: float = 2.0) -> dict[str, Any]:
    _SUPERVISOR_STOP.set()
    with _SUPERVISOR_LOCK:
        thread = _SUPERVISOR_THREAD
    if thread and thread.is_alive() and thread is not threading.current_thread():
        thread.join(timeout=timeout)
    _update_supervisor_state(running=False, last_summary="Autonomy supervisor stopped.")
    return supervisor_status()


def supervisor_status() -> dict[str, Any]:
    with _SUPERVISOR_LOCK:
        thread_alive = bool(_SUPERVISOR_THREAD and _SUPERVISOR_THREAD.is_alive())
        state = dict(_SUPERVISOR_STATE)
    state["running"] = thread_alive and not _SUPERVISOR_STOP.is_set()
    state["enabled"] = bool(config_value("autonomy_supervisor_enabled", autonomy_control.full_autonomy_enabled()))
    return state


def supervisor_tick(worker_count: int | None = None) -> dict[str, Any]:
    if not autonomy_control.enabled():
        state = {"summary": "Autonomy disabled.", "workers": 0, "task_counts": {}, "mission_refresh": {}}
        _update_supervisor_state(last_tick=_now(), last_summary=state["summary"])
        return state

    workers = _ensure_background_workers(worker_count)
    mission_refresh = _safe(lambda: mission_control.refresh_mission(), {})
    autopilot = _refresh_task_autopilot()
    task_counts = _safe(task_queue.counts, {})
    active = active_run()
    run: dict[str, Any] | None = None
    if active and active.get("status") in {"running", "retrying"}:
        run = _step_active_run(active)
    elif _should_start_autonomy_run(task_counts, mission_refresh):
        run = run_until_blocked(
            "",
            root=resolve_coding_root(),
            max_steps=int(config_value("autonomy_supervisor_tick_max_steps", 2)),
        )

    summary = _supervisor_summary(workers, task_counts, run, mission_refresh)
    state = {
        "summary": summary,
        "workers": workers,
        "task_counts": task_counts,
        "mission_refresh": mission_refresh,
        "task_autopilot": autopilot,
        "active_run": run or active,
        "control": autonomy_control.status(),
    }
    _update_supervisor_state(
        last_tick=_now(),
        last_error="",
        workers_started=workers,
        last_summary=summary,
        ticks=int(_SUPERVISOR_STATE.get("ticks") or 0) + 1,
    )
    return state


def wipe_all() -> None:
    init_db()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.execute("DELETE FROM autonomy_events")
        conn.execute("DELETE FROM autonomy_runs")


def _supervisor_loop(worker_count: int | None = None) -> None:
    interval = max(1.0, float(config_value("autonomy_supervisor_interval_seconds", 5.0)))
    while not _SUPERVISOR_STOP.is_set():
        try:
            supervisor_tick(worker_count=worker_count)
        except Exception as exc:
            _update_supervisor_state(last_tick=_now(), last_error=str(exc), last_summary=f"Autonomy supervisor error: {exc}")
        _SUPERVISOR_STOP.wait(interval)


def _ensure_background_workers(worker_count: int | None = None) -> int:
    if not bool(config_value("autonomy_start_background_workers", True)):
        return 0
    desired = worker_count or int(config_value("autonomy_worker_count", 0) or 0) or None
    try:
        from core import background_agents

        return int(background_agents.start_workers(desired))
    except Exception as exc:
        _update_supervisor_state(last_error=str(exc))
        return 0


def _refresh_task_autopilot() -> dict[str, Any]:
    try:
        from core import executive_capabilities

        return executive_capabilities.refresh_task_autopilot()
    except Exception as exc:
        return {"summary": f"Task autopilot refresh skipped: {exc}"}


def _step_active_run(run: dict[str, Any]) -> dict[str, Any]:
    steps = max(1, min(10, int(config_value("autonomy_supervisor_tick_max_steps", 2))))
    current = run
    for _ in range(steps):
        if current.get("status") not in {"running", "retrying"}:
            break
        current = step(int(current["id"]))
    return current


def _should_start_autonomy_run(task_counts: dict[str, Any], mission_refresh: dict[str, Any]) -> bool:
    global _LAST_RUN_START
    if not bool(config_value("autonomy_supervisor_start_runs", True)):
        return False
    now = time.monotonic()
    interval = max(5.0, float(config_value("autonomy_supervisor_new_run_interval_seconds", 60.0)))
    if now - _LAST_RUN_START < interval:
        return False
    active_tasks = sum(int(task_counts.get(status) or 0) for status in ("pending", "active", "blocked"))
    active_missions = len(mission_refresh.get("missions") or []) if isinstance(mission_refresh, dict) else 0
    if active_tasks <= 0 and active_missions <= 0:
        return False
    _LAST_RUN_START = now
    return True


def _supervisor_summary(
    workers: int,
    task_counts: dict[str, Any],
    run: dict[str, Any] | None,
    mission_refresh: dict[str, Any],
) -> str:
    active_tasks = sum(int(task_counts.get(status) or 0) for status in ("pending", "active", "blocked"))
    active_missions = len(mission_refresh.get("missions") or []) if isinstance(mission_refresh, dict) else 0
    if run:
        return f"Autonomy supervisor active with {workers} worker(s); {active_tasks} task(s), {active_missions} mission(s), run #{run.get('id')} is {run.get('status')}."
    return f"Autonomy supervisor active with {workers} worker(s); {active_tasks} task(s) and {active_missions} mission(s) need no autonomy step right now."


def _update_supervisor_state(**updates: Any) -> None:
    with _SUPERVISOR_LOCK:
        _SUPERVISOR_STATE.update(updates)


def _act(run: dict[str, Any], decision: dict[str, Any]) -> dict[str, Any]:
    root = run.get("root") or ""
    action = decision["action"]
    if action == "fix_loop":
        return autonomous_fix_loop.run(root=root, log_text=run["goal"], run_tests=False, source="autonomy_engine")
    if action == "release_prepare":
        return release_manager.prepare_release(root)
    if action == "qa_lab":
        return autonomous_qa_lab.run_qa(root, run_tests=False)
    if action == "project_watchdog":
        project_memory.profile(root, refresh=True)
        return project_watchdog.run_once(root, notify=True)
    return personal_automation_daemon.run_once(run_actions=True)


def _verify(run: dict[str, Any], decision: dict[str, Any], outcome: dict[str, Any]) -> dict[str, Any]:
    text = json.dumps(outcome, ensure_ascii=True, default=str).lower()
    evidence = [outcome.get("summary") or f"{decision['action']} produced a result."]
    blocked = any(term in text for term in ("approval", "blocked", "needs_approval", "permission required"))
    failed = any(term in text for term in ("failed", "traceback", "error")) and not blocked
    complete = decision["action"] in {"qa_lab", "release_prepare", "project_watchdog", "automation_daemon"} and not failed and not blocked
    confidence = 0.82 if complete else (0.52 if blocked else 0.45)
    if complete:
        proof = trust_proof.create_report(
            "Autonomy engine step proof",
            tested=[decision["action"]],
            evidence=evidence,
            risks=["Hard-stop actions still require explicit approval even in full autonomy mode."],
            confidence=confidence,
            metadata={"run_id": run["id"], "action": decision["action"]},
        )
        evidence.append(f"proof report #{proof.get('id')}")
    missing = [] if complete else ["approval or stronger evidence required" if blocked else "successful verification"]
    return {"complete": complete, "blocked": blocked, "confidence": confidence, "summary": _summary(decision, complete, blocked, failed), "evidence": evidence, "missing": missing}


def _summary(decision: dict[str, Any], complete: bool, blocked: bool, failed: bool) -> str:
    if complete:
        return f"Autonomy step completed with {decision['action']}."
    if blocked:
        return f"Autonomy paused: {decision['action']} needs approval or more evidence."
    if failed:
        return f"Autonomy step found a failure during {decision['action']}."
    return f"Autonomy will retry after {decision['action']} because verification was incomplete."


def _escalate(run: dict[str, Any], verified: dict[str, Any]) -> None:
    approval = _safe(
        lambda: approval_inbox.create(
            kind="autonomy_blocker",
            title="Autonomy run needs a decision",
            summary=verified["summary"],
            source="autonomy_engine",
            payload={"run_id": run["id"], "missing": verified.get("missing", [])},
        ),
        {},
    )
    notification_center.add(
        source="autonomy_engine",
        category="approval",
        severity=4,
        title="Autonomy run paused",
        message=verified["summary"],
        dedupe_key=f"autonomy-engine:{run['id']}",
        metadata={"run_id": run["id"], "approval": approval},
    )


def _event(run_id: int, step: int, action: str, status: str, summary: str, payload: dict[str, Any]) -> None:
    init_db()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.execute(
            "INSERT INTO autonomy_events(run_id, timestamp, step, action, status, summary, payload_json) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (int(run_id), _now(), int(step), action, status, summary, _json_dumps(payload)),
        )


def _row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "created_at": str(row["created_at"]),
        "updated_at": str(row["updated_at"]),
        "goal": str(row["goal"]),
        "root": str(row["root"]),
        "status": str(row["status"]),
        "current_action": str(row["current_action"]),
        "confidence": float(row["confidence"]),
        "risk_level": str(row["risk_level"]),
        "retries": int(row["retries"]),
        "summary": str(row["summary"]),
        "evidence": _json_loads(row["evidence_json"], []),
        "missing": _json_loads(row["missing_json"], []),
        "metadata": _json_loads(row["metadata_json"], {}),
    }


def _event_row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "run_id": int(row["run_id"]),
        "timestamp": str(row["timestamp"]),
        "step": int(row["step"]),
        "action": str(row["action"]),
        "status": str(row["status"]),
        "summary": str(row["summary"]),
        "payload": _json_loads(row["payload_json"], {}),
    }


def _risk(text: str) -> str:
    lowered = str(text or "").lower()
    if any(term in lowered for term in ("deploy", "delete", "send", "email", "payment", "security scan")):
        return "high"
    if any(term in lowered for term in ("edit", "fix", "code", "install", "write")):
        return "medium"
    return "low"


def _safe_root(value: str | Path) -> Path:
    try:
        return resolve_coding_root(value)
    except Exception:
        return resolve_coding_root()


def _first(items: list[dict[str, Any]]) -> dict[str, Any] | None:
    return items[0] if items else None


def _safe(fn: Any, default: Any) -> Any:
    try:
        return fn()
    except Exception:
        return default


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
