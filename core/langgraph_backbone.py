"""Optional LangGraph backbone for Friday's durable execution loop.

Friday keeps its product-studio gates, artifacts, approvals, and readiness
rules. This module only provides the workflow spine underneath those rules.
When LangGraph is unavailable, Friday falls back to the native sequential
runner with the same phase contract.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from core.config import config_value

PhaseHandler = Callable[[dict[str, Any]], dict[str, Any] | None]

DEFAULT_PHASES = ("inspect", "plan", "build", "verify", "fix", "prove")


def capabilities() -> dict[str, Any]:
    loaded = _load_langgraph()
    available = loaded.get("available", False)
    preferred = str(config_value("friday_workflow_backend", "auto") or "auto").strip().lower()
    backend = "native"
    if preferred not in {"native", "off", "disabled"} and available:
        backend = "langgraph"
    return {
        "preferred_backend": preferred,
        "active_backend": backend,
        "langgraph_available": available,
        "langgraph_error": loaded.get("error", ""),
        "interrupts_available": bool(loaded.get("interrupt")),
        "phases": list(DEFAULT_PHASES),
        "summary": (
            "Friday will run durable work through LangGraph when available, "
            "then fall back to the native phase runner without changing product-studio contracts."
        ),
    }


def run_phase_graph(
    phases: list[tuple[str, PhaseHandler]],
    initial_state: dict[str, Any] | None = None,
    *,
    thread_id: str = "",
) -> dict[str, Any]:
    """Run named phase handlers using LangGraph when available.

    Each phase handler receives the current mutable-ish state and returns a
    dictionary delta. The returned state always includes ``workflow_backend`` and
    ``workflow_phases`` so callers can attach proof to the Friday run record.
    """

    normalized = [(str(name or "").strip(), handler) for name, handler in phases if str(name or "").strip()]
    if not normalized:
        return {**(initial_state or {}), "workflow_backend": "native", "workflow_phases": []}

    preferred = str(config_value("friday_workflow_backend", "auto") or "auto").strip().lower()
    if preferred in {"native", "off", "disabled"}:
        return _run_native(normalized, initial_state or {}, backend_note="native")

    loaded = _load_langgraph()
    if not loaded.get("available"):
        return _run_native(
            normalized,
            initial_state or {},
            backend_note="native",
            backend_error=loaded.get("error", "LangGraph is not installed."),
        )

    try:
        return _run_langgraph(normalized, initial_state or {}, loaded, thread_id=thread_id)
    except Exception as exc:
        if preferred in {"langgraph", "required"}:
            raise
        return _run_native(normalized, initial_state or {}, backend_note="native", backend_error=str(exc))


def request_approval(
    state: dict[str, Any] | None,
    *,
    kind: str,
    title: str,
    summary: str,
    payload: dict[str, Any] | None = None,
    source: str = "langgraph_backbone",
) -> dict[str, Any]:
    """Create a human approval wait, using LangGraph interrupts when possible.

    This helper keeps Friday's approval rules custom while giving LangGraph-backed
    workflows a real pause point. When it is called outside a live LangGraph node,
    the approval inbox entry is still created and the returned state is marked
    blocked for approval.
    """

    from core import approval_inbox, friday_trace

    current = dict(state or {})
    trace_id = str(current.get("trace_id") or "").strip()
    approval = approval_inbox.create(
        kind=kind,
        title=title,
        summary=summary,
        source=source,
        payload={**(payload or {}), **({"trace_id": trace_id} if trace_id else {})},
    )
    if trace_id:
        if friday_trace.get_trace(trace_id) is None:
            friday_trace.start_trace(trace_id, kind="approval", title=title, metadata={"source": source})
        friday_trace.record_event(
            trace_id,
            event_type="approval_wait",
            title=title,
            summary=summary,
            status="blocked",
            metadata={"approval": approval, "source": source},
        )

    interrupt_payload = {
        "approval": approval,
        "kind": kind,
        "title": title,
        "summary": summary,
        "payload": payload or {},
    }
    decision: Any = None
    interrupt_error = ""
    if current.get("workflow_backend") == "langgraph":
        interrupt_fn = _load_langgraph().get("interrupt")
        if interrupt_fn:
            try:
                decision = interrupt_fn(interrupt_payload)
            except Exception as exc:
                interrupt_error = str(exc)

    return {
        "workflow_interrupted": decision is None,
        "workflow_interrupt": interrupt_payload,
        "approval": approval,
        "approval_decision": decision,
        "approval_interrupt_error": interrupt_error,
        "status": "blocked_for_approval" if decision is None else "approval_resumed",
    }


def _run_native(
    phases: list[tuple[str, PhaseHandler]],
    initial_state: dict[str, Any],
    *,
    backend_note: str,
    backend_error: str = "",
) -> dict[str, Any]:
    state = {
        **initial_state,
        "workflow_backend": backend_note,
        "workflow_backend_error": backend_error,
        "workflow_phases": [],
    }
    for name, handler in phases:
        state["current_phase"] = name
        delta = handler(dict(state)) or {}
        state.update(delta)
        state["workflow_phases"] = [*state.get("workflow_phases", []), name]
        if state.get("workflow_interrupted"):
            break
    return state


def _run_langgraph(
    phases: list[tuple[str, PhaseHandler]],
    initial_state: dict[str, Any],
    loaded: dict[str, Any],
    *,
    thread_id: str,
) -> dict[str, Any]:
    StateGraph = loaded["StateGraph"]
    START = loaded["START"]
    END = loaded["END"]
    MemorySaver = loaded.get("MemorySaver")

    graph = StateGraph(dict)

    for name, handler in phases:
        graph.add_node(name, _node(name, handler))

    graph.add_edge(START, phases[0][0])
    for (current_name, _), (next_name, _) in zip(phases, phases[1:]):
        graph.add_edge(current_name, next_name)
    graph.add_edge(phases[-1][0], END)

    use_checkpointer = bool(config_value("friday_langgraph_memory_checkpointer", False))
    checkpointer = MemorySaver() if MemorySaver and use_checkpointer else None
    compiled = graph.compile(checkpointer=checkpointer) if checkpointer else graph.compile()
    state = {
        **initial_state,
        "workflow_backend": "langgraph",
        "workflow_backend_error": "",
        "workflow_phases": [],
    }
    config = {"configurable": {"thread_id": thread_id or "friday-run"}}
    result = compiled.invoke(state, config=config)
    result["workflow_backend"] = "langgraph"
    return result


def _node(name: str, handler: PhaseHandler) -> PhaseHandler:
    def _wrapped(state: dict[str, Any]) -> dict[str, Any]:
        next_state = dict(state)
        if next_state.get("workflow_interrupted"):
            return next_state
        next_state["current_phase"] = name
        delta = handler(dict(next_state)) or {}
        next_state.update(delta)
        next_state["workflow_phases"] = [*next_state.get("workflow_phases", []), name]
        return next_state

    return _wrapped


def _load_langgraph() -> dict[str, Any]:
    try:
        from langgraph.checkpoint.memory import MemorySaver  # type: ignore
        from langgraph.graph import END, START, StateGraph  # type: ignore
        try:
            from langgraph.types import interrupt  # type: ignore
        except Exception:
            interrupt = None

        return {
            "available": True,
            "StateGraph": StateGraph,
            "START": START,
            "END": END,
            "MemorySaver": MemorySaver,
            "interrupt": interrupt,
            "error": "",
        }
    except Exception as exc:
        return {"available": False, "error": str(exc)}
