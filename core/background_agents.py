"""Background worker for free/local v2 agents."""

from __future__ import annotations

import os
import threading
import time
from typing import Any

try:
    import psutil
except Exception:  # pragma: no cover
    psutil = None

from core import agent_blackboard, agent_quality_manager, agent_thought_bus, evaluation_lab, agents, episodic_store, failure_autopsy, knowledge_graph, task_contracts, task_queue
from core.config import config_value

_STOP = threading.Event()
_THREADS: list[threading.Thread] = []
_LOCK = threading.Lock()
_LAST_ACTIVITY = ""
_PROCESS_ID = str(os.getpid())


def start_workers(count: int | None = None) -> int:
    if not bool(config_value("v2_background_agents_enabled", True)):
        return 0
    desired = max(1, int(count or agents.default_worker_count()))
    with _LOCK:
        _STOP.clear()
        _THREADS[:] = [thread for thread in _THREADS if thread.is_alive()]
        while len(_THREADS) < desired:
            index = len(_THREADS) + 1
            thread = threading.Thread(target=_worker_loop, name=f"FridayAgentWorker-{index}", daemon=True)
            thread.start()
            _THREADS.append(thread)
        count_started = len(_THREADS)
    _record_heartbeat(alive=count_started)
    return count_started


def stop_workers(timeout: float = 2.0) -> None:
    _STOP.set()
    with _LOCK:
        threads = list(_THREADS)
    for thread in threads:
        thread.join(timeout=timeout)
    with _LOCK:
        _THREADS[:] = [thread for thread in _THREADS if thread.is_alive()]
    _record_heartbeat()


def worker_status() -> dict[str, Any]:
    with _LOCK:
        alive = sum(1 for thread in _THREADS if thread.is_alive())
    local_running = alive > 0 and not _STOP.is_set()
    _record_heartbeat(alive=alive)
    remote = [
        heartbeat
        for heartbeat in task_queue.worker_heartbeats()
        if heartbeat.get("process_id") != _PROCESS_ID and heartbeat.get("running") and int(heartbeat.get("workers") or 0) > 0
    ]
    remote_workers = sum(int(item.get("workers") or 0) for item in remote)
    remote_desired = max([int(item.get("desired_workers") or 0) for item in remote] or [0])
    remote_activity = next((str(item.get("last_activity") or "") for item in remote if item.get("last_activity")), "")
    runtime = agents.runtime_summary()
    mode = "API-backed" if runtime.get("api_agent_mode") else "local-safe"
    if remote and not local_running:
        remote_runtime = remote[0].get("runtime")
        if isinstance(remote_runtime, dict) and remote_runtime:
            runtime = remote_runtime
        mode = str(remote[0].get("mode") or mode)
    counts = task_queue.counts()
    return {
        "running": local_running or remote_workers > 0,
        "workers": alive + remote_workers,
        "desired_workers": max(agents.default_worker_count(), remote_desired),
        "runtime": runtime,
        "mode": mode,
        "last_activity": _LAST_ACTIVITY or remote_activity,
        "external_workers": remote,
        "tasks": counts,
    }


def run_one_task() -> dict[str, Any] | None:
    task = task_queue.claim_next_task()
    if task is None:
        return None
    _run_claimed_task(task)
    return task_queue.get_task(int(task["id"]))


def _worker_loop() -> None:
    while not _STOP.is_set():
        _record_heartbeat()
        if _cpu_guard_active():
            _STOP.wait(float(config_value("v2_worker_cpu_guard_sleep_seconds", 5.0)))
            continue
        task = task_queue.claim_next_task()
        if task is None:
            _STOP.wait(float(config_value("v2_worker_idle_sleep_seconds", 2.0)))
            continue
        _run_claimed_task(task)
        _STOP.wait(float(config_value("v2_worker_between_tasks_sleep_seconds", 0.5)))


def _cpu_guard_active() -> bool:
    if not bool(config_value("v2_cpu_guard_enabled", True)):
        return False
    if psutil is None:
        return False
    try:
        usage = float(psutil.cpu_percent(interval=0.0))
    except Exception:
        return False
    limit = float(config_value("v2_max_cpu_percent", 40.0))
    return usage >= limit


def _run_claimed_task(task: dict[str, Any]) -> None:
    global _LAST_ACTIVITY
    task_id = int(task["id"])
    contract = task_contracts.ensure_contract(task)
    task_queue.post_message(task_id, "worker", f"{task['agent_id']} started.")
    task_queue.post_message(task_id, "contract", f"Contract active: {contract['goal']} ({contract['risk_level']} risk).")
    task_queue.post_message(task_id, "office", "Progress 20%: brief claimed and opened in the agent office.")
    agent_blackboard.post_item(
        str(task["agent_id"]),
        "progress",
        f"Task #{task_id} started",
        "Brief claimed and contract opened.",
        task_id=task_id,
        confidence=0.6,
        status="active",
    )
    _post_thought(
        "ceo",
        "context",
        f"Task #{task_id} entered specialist execution",
        {
            "agent_id": task.get("agent_id"),
            "title": task.get("title"),
            "contract_goal": contract.get("goal"),
            "risk_level": contract.get("risk_level"),
        },
        target_agent_id=str(task.get("agent_id") or ""),
        task_id=task_id,
        confidence=0.72,
        priority=int(task.get("priority") or 5),
        metadata={"source": "background_worker"},
    )
    _LAST_ACTIVITY = f"Task {task_id}: {task['title']}"
    started = time.perf_counter()
    try:
        _record_heartbeat()
        task_queue.post_message(task_id, "office", "Progress 55%: specialist work is in progress.")
        agent_blackboard.post_item(str(task["agent_id"]), "need", f"Task #{task_id} needs output", "Specialist work is in progress.", task_id=task_id, confidence=0.5, status="active")
        result = agents.run_task(task)
        task_queue.post_message(task_id, "office", "Progress 90%: result prepared for review.")
        contract_result = task_contracts.verify_contract(task, result)
        result["contract"] = {
            "status": contract_result.get("status"),
            "satisfied": bool(contract_result.get("satisfied")),
            "verification_method": contract_result.get("verification_method"),
        }
        if not contract_result.get("satisfied"):
            duration_ms = round((time.perf_counter() - started) * 1000, 2)
            try:
                agent_quality_manager.record_task_result(task, result, duration_ms=duration_ms, contract_satisfied=False)
                failure_autopsy.create(
                    f"Task #{task_id} contract unsatisfied",
                    "Task contract was not satisfied.",
                    evidence=[contract_result, result.get("summary")],
                    root_cause="The agent output did not satisfy the task contract.",
                    next_time="Ask for missing evidence or reroute to a better agent before marking done.",
                    source=str(result.get("agent_id") or task.get("agent_id") or "agent"),
                    metadata={"task_id": task_id, "contract": contract_result},
                )
            except Exception:
                pass
            agent_blackboard.post_item(
                str(result.get("agent_id") or task["agent_id"]),
                "blocker",
                f"Task #{task_id} contract not satisfied",
                "The task result did not meet its contract, so Friday will not mark it done.",
                task_id=task_id,
                confidence=0.85,
                status="blocked",
                metadata={"contract": contract_result},
            )
            task_queue.fail_task(task_id, "Task contract was not satisfied.")
            evaluation_lab.record_event("task_stuck", f"Task #{task_id} contract unsatisfied.", source="task_contracts", severity=4, metadata={"task_id": task_id})
            _post_thought(
                str(result.get("agent_id") or task["agent_id"]),
                "risk",
                f"Task #{task_id} could not satisfy its contract",
                {"contract": contract_result, "title": task.get("title")},
                task_id=task_id,
                confidence=0.86,
                priority=1,
                metadata={"source": "task_contracts"},
            )
            return
        duration_ms = round((time.perf_counter() - started) * 1000, 2)
        try:
            agent_quality_manager.record_task_result(task, result, duration_ms=duration_ms, contract_satisfied=True)
        except Exception:
            pass
        task_queue.complete_task(task_id, result)
        task_queue.post_message(task_id, str(result.get("agent_id") or "agent"), str(result.get("summary") or "Done."))
        agent_blackboard.post_item(
            str(result.get("agent_id") or task["agent_id"]),
            "evidence",
            f"Task #{task_id} verified",
            str(result.get("summary") or "")[:1000],
            task_id=task_id,
            confidence=0.78,
            status="resolved",
            metadata={"contract_status": contract_result.get("status")},
        )
        evaluation_lab.record_event("task_completed", f"Task #{task_id} completed by {result.get('agent_id') or task['agent_id']}.", source="background_agents", severity=1, metadata={"task_id": task_id})
        for child_id in result.get("spawned_subtasks") or []:
            task_queue.post_message(task_id, "delegation", f"Spawned child task {child_id}.")
        knowledge_graph.add_edge(result.get("agent_name", "Agent"), "COMPLETED", task["title"], task_id=task_id)
        _record_mentoring_edge(task, result)
        episodic_store.insert_event(
            agent_id=str(result.get("agent_id") or task["agent_id"]),
            action_type="agent_task",
            inputs={"task": task},
            outputs=result,
            success_score=1.0,
            metadata={"duration_ms": duration_ms},
        )
    except Exception as exc:
        message = str(exc)
        duration_ms = round((time.perf_counter() - started) * 1000, 2)
        task_queue.fail_task(task_id, message)
        try:
            agent_quality_manager.record_evaluation(
                str(task.get("agent_id") or "agent"),
                task_id=task_id,
                task_type="failure",
                accuracy=0.1,
                usefulness=0.1,
                speed=0.5,
                evidence=0.0,
                mistakes=1.0,
                notes=message,
                metadata={"duration_ms": duration_ms, "title": task.get("title")},
            )
            failure_autopsy.create(
                f"Task #{task_id} failed",
                message,
                evidence=[task.get("title"), task.get("description")],
                source=str(task.get("agent_id") or "agent"),
                metadata={"task_id": task_id, "duration_ms": duration_ms},
            )
            agent_blackboard.post_item(str(task.get("agent_id") or "agent"), "blocker", f"Task #{task_id} failed", message, task_id=task_id, confidence=0.8, status="blocked")
            evaluation_lab.record_event("agent_failure", f"Task #{task_id} failed: {message}", source="background_agents", severity=4, metadata={"task_id": task_id})
            _post_thought(
                str(task.get("agent_id") or "agent"),
                "risk",
                f"Task #{task_id} failed",
                {"error": message, "title": task.get("title")},
                task_id=task_id,
                confidence=0.82,
                priority=1,
                metadata={"source": "background_agents"},
            )
        except Exception:
            pass
        episodic_store.insert_event(
            agent_id=str(task.get("agent_id") or "agent"),
            action_type="agent_task",
            inputs={"task": task},
            outputs={"error": message},
            success_score=0.0,
        )
    finally:
        _refresh_parent_mission(task)
        _LAST_ACTIVITY = f"Task {task_id} finished."
        _record_heartbeat()


def _refresh_parent_mission(task: dict[str, Any]) -> None:
    try:
        input_data = task.get("input") or {}
        mission_id = int(input_data.get("mission_id") or 0) if isinstance(input_data, dict) else 0
        if mission_id > 0:
            from core import mission_control

            mission_control.refresh_mission(mission_id)
    except Exception:
        return


def _record_heartbeat(alive: int | None = None) -> None:
    try:
        with _LOCK:
            worker_count = sum(1 for thread in _THREADS if thread.is_alive()) if alive is None else int(alive)
        runtime = agents.runtime_summary()
        task_queue.record_worker_heartbeat(
            _PROCESS_ID,
            workers=worker_count,
            desired_workers=agents.default_worker_count(),
            running=worker_count > 0 and not _STOP.is_set(),
            mode="API-backed" if runtime.get("api_agent_mode") else "local-safe",
            last_activity=_LAST_ACTIVITY,
            runtime=runtime,
        )
    except Exception:
        return


def _record_mentoring_edge(task: dict[str, Any], result: dict[str, Any]) -> None:
    title = str(task.get("title") or "").lower()
    agent_id = str(result.get("agent_id") or task.get("agent_id") or "")
    if agent_id == "senior_developer" and "review junior developer output" in title:
        knowledge_graph.add_edge("Senior Developer", "TAUGHT", "Junior Developer", task_id=task.get("id"))
        knowledge_graph.add_edge("Senior Developer", "REVIEWED", str(task.get("title") or "Junior output"), task_id=task.get("id"))


def _post_thought(source_agent_id: str, packet_type: str, summary: str, content: dict[str, Any], **kwargs: Any) -> None:
    if not bool(config_value("agent_thought_bus_enabled", True)):
        return
    try:
        agent_thought_bus.post_thought(source_agent_id, packet_type, summary, content, **kwargs)
    except Exception:
        return
