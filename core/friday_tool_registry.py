"""Shared tool registry for Friday agents and product-studio workflows."""

from __future__ import annotations

import traceback
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from core import approval_inbox, autonomy_control, friday_trace, langgraph_backbone

ToolHandler = Callable[[dict[str, Any]], dict[str, Any]]


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    handler: ToolHandler
    input_schema: dict[str, Any] = field(default_factory=dict)
    requires_approval: bool = False
    category: str = "general"


_REGISTRY: dict[str, ToolSpec] = {}
_BUILTINS_READY = False


def register_tool(
    name: str,
    handler: ToolHandler,
    *,
    description: str,
    input_schema: dict[str, Any] | None = None,
    requires_approval: bool = False,
    category: str = "general",
) -> ToolSpec:
    clean = _tool_name(name)
    if not clean:
        raise ValueError("Tool name is required.")
    spec = ToolSpec(
        name=clean,
        description=str(description or "").strip(),
        handler=handler,
        input_schema=input_schema or {},
        requires_approval=bool(requires_approval),
        category=str(category or "general").strip() or "general",
    )
    _REGISTRY[clean] = spec
    return spec


def list_tools() -> list[dict[str, Any]]:
    _ensure_builtins()
    return [
        {
            "name": spec.name,
            "description": spec.description,
            "input_schema": spec.input_schema,
            "requires_approval": spec.requires_approval,
            "category": spec.category,
        }
        for spec in sorted(_REGISTRY.values(), key=lambda item: item.name)
    ]


def execute_tool(
    name: str,
    payload: dict[str, Any] | None = None,
    *,
    trace_id: str = "",
    approval_override: bool | None = None,
) -> dict[str, Any]:
    _ensure_builtins()
    clean = _tool_name(name)
    spec = _REGISTRY.get(clean)
    if spec is None:
        return {"ok": False, "status": "failed", "summary": f"Unknown Friday tool: {name}", "tool": clean}
    args = dict(payload or {})
    trace_id, trace_metadata = friday_trace.ensure_trace_id({"tool": clean, "trace_id": trace_id}, prefix="tool")
    friday_trace.start_trace(trace_id, kind="tool", title=clean, metadata=trace_metadata)
    validation = _validate_schema(spec.input_schema, args)
    if validation:
        friday_trace.record_event(trace_id, event_type="tool_validation", title=clean, summary="Tool input validation failed.", status="failed", metadata={"errors": validation})
        return {"ok": False, "status": "failed", "summary": "Tool input validation failed.", "tool": clean, "errors": validation, "trace_id": trace_id}
    requires_approval = bool(spec.requires_approval or approval_override)
    authority_override: dict[str, Any] | None = None
    if requires_approval:
        authority_override = _authority_approval_override(clean, args)
        if authority_override:
            requires_approval = False
    if requires_approval:
        wait = langgraph_backbone.request_approval(
            {"trace_id": trace_id, "workflow_backend": trace_metadata.get("workflow_backend") or ""},
            kind="tool_approval",
            title=f"Approve tool: {clean}",
            summary=spec.description,
            source="friday_tool_registry",
            payload={"tool": clean, "args": args, "trace_id": trace_id},
        )
        approval = wait.get("approval") if isinstance(wait.get("approval"), dict) else {}
        friday_trace.record_event(trace_id, event_type="tool_waiting_approval", title=clean, summary=spec.description, status="blocked", metadata={"approval": approval})
        return {"ok": False, "status": "blocked_for_approval", "summary": f"Tool {clean} requires approval.", "tool": clean, "approval": approval, "workflow_interrupt": wait.get("workflow_interrupt"), "trace_id": trace_id}
    friday_trace.record_event(
        trace_id,
        event_type="tool_start",
        title=clean,
        summary=spec.description,
        status="running",
        metadata={"args": _safe_args(args), "authority_override": authority_override or {}},
    )
    try:
        result = spec.handler(args) or {}
        if not isinstance(result, dict):
            result = {"ok": True, "result": result}
        result.setdefault("ok", True)
        result.setdefault("status", "done" if result.get("ok") is not False else "failed")
        result.setdefault("summary", f"Tool {clean} finished.")
        result["tool"] = clean
        result["trace_id"] = trace_id
        if authority_override:
            result["authority_override"] = authority_override
        friday_trace.record_event(trace_id, event_type="tool_finish", title=clean, summary=str(result.get("summary") or ""), status=str(result.get("status") or ""), metadata={"result_keys": sorted(result.keys())})
        return result
    except Exception as exc:
        friday_trace.record_event(trace_id, event_type="tool_error", title=clean, summary=str(exc), status="failed", metadata={"traceback": traceback.format_exc(limit=8)})
        return {"ok": False, "status": "failed", "summary": f"Tool {clean} failed: {exc}", "tool": clean, "error": str(exc), "trace_id": trace_id}


def to_langchain_tools(names: list[str] | None = None) -> list[Any]:
    _ensure_builtins()
    try:
        from langchain_core.tools import StructuredTool  # type: ignore
    except Exception:
        return []
    selected = [_REGISTRY[_tool_name(name)] for name in names or sorted(_REGISTRY) if _tool_name(name) in _REGISTRY]
    tools = []
    for spec in selected:
        def _run(_spec: ToolSpec = spec, **kwargs: Any) -> dict[str, Any]:
            return execute_tool(_spec.name, kwargs)

        tools.append(
            StructuredTool.from_function(
                func=_run,
                name=spec.name.replace(".", "_"),
                description=spec.description,
            )
        )
    return tools


def _ensure_builtins() -> None:
    global _BUILTINS_READY
    if _BUILTINS_READY:
        return
    _BUILTINS_READY = True
    register_tool(
        "documents.read",
        _documents_read,
        description="Read a Markdown, text, DOCX, or PDF document.",
        input_schema={"required": ["path"], "properties": {"path": {"type": "string"}, "max_chars": {"type": "integer"}}},
        category="documents",
    )
    register_tool(
        "documents.index",
        _documents_index,
        description="Index readable documents into source-grounded chunks using Friday's LlamaIndex adapter when available.",
        input_schema={"required": ["paths"], "properties": {"paths": {"type": "array"}, "root": {"type": "string"}, "query": {"type": "string"}}},
        category="documents",
    )
    register_tool(
        "project_memory.search",
        _project_memory_search,
        description="Search per-project Friday memory.",
        input_schema={"required": ["query"], "properties": {"query": {"type": "string"}, "root": {"type": "string"}, "limit": {"type": "integer"}}},
        category="memory",
    )
    register_tool(
        "approval.create",
        _approval_create,
        description="Create an approval request Friday must not decide alone.",
        input_schema={"required": ["title", "summary"], "properties": {"title": {"type": "string"}, "summary": {"type": "string"}, "kind": {"type": "string"}}},
        category="approvals",
    )
    register_tool(
        "production.rerun_gates",
        _production_rerun_gates,
        description="Rerun production readiness gates for an existing run.",
        input_schema={"required": ["run_id"], "properties": {"run_id": {"type": "integer"}, "failed_only": {"type": "boolean"}}},
        requires_approval=False,
        category="production",
    )
    register_tool(
        "security_lab.status",
        _security_lab_status,
        description="Inspect Security Lab tools, scopes, and recent runs.",
        category="security",
    )
    register_tool(
        "security_lab.run",
        _security_lab_run,
        description="Run scoped authorized Security Lab tools such as Semgrep, Bandit, Gitleaks, Trivy, Nmap, Nuclei, and ZAP.",
        input_schema={"required": [], "properties": {"root": {"type": "string"}, "target": {"type": "string"}, "profile": {"type": "string"}, "tools": {"type": "array"}, "timeout": {"type": "integer"}}},
        requires_approval=True,
        category="security",
    )
    register_tool(
        "security_lab.hardening",
        _security_lab_hardening,
        description="Generate a defensive hardening plan and threat model for a project or target.",
        input_schema={"required": [], "properties": {"root": {"type": "string"}, "target": {"type": "string"}}},
        category="security",
    )
    register_tool(
        "security_lab.remediate",
        _security_lab_remediate,
        description="Create a remediation plan from a Security Lab run.",
        input_schema={"required": [], "properties": {"run_id": {"type": "integer"}, "root": {"type": "string"}, "target": {"type": "string"}, "apply": {"type": "boolean"}}},
        requires_approval=True,
        category="security",
    )


def _documents_read(args: dict[str, Any]) -> dict[str, Any]:
    from core import document_intelligence

    return document_intelligence.read_document(args["path"], max_chars=int(args.get("max_chars") or 12000))


def _documents_index(args: dict[str, Any]) -> dict[str, Any]:
    from core import document_intelligence

    return document_intelligence.index_documents(args.get("paths") or [], root=args.get("root") or "", query=args.get("query") or "", max_chars=int(args.get("max_chars") or 60000))


def _project_memory_search(args: dict[str, Any]) -> dict[str, Any]:
    from core import project_memory

    return {"ok": True, "results": project_memory.search(args.get("query") or "", root=args.get("root") or "", limit=int(args.get("limit") or 20))}


def _approval_create(args: dict[str, Any]) -> dict[str, Any]:
    return approval_inbox.create(kind=args.get("kind") or "approval", title=args["title"], summary=args["summary"], source="friday_tool_registry", payload=args.get("payload") or {})


def _production_rerun_gates(args: dict[str, Any]) -> dict[str, Any]:
    from core import production_readiness

    return production_readiness.rerun_gates(int(args["run_id"]), failed_only=bool(args.get("failed_only", True)))


def _security_lab_status(args: dict[str, Any]) -> dict[str, Any]:
    from core import security_lab

    return security_lab.status()


def _security_lab_run(args: dict[str, Any]) -> dict[str, Any]:
    from core import security_lab

    return security_lab.run_scan(
        root=args.get("root") or "",
        target=args.get("target") or "",
        profile=args.get("profile") or "auto",
        tools=args.get("tools") or [],
        timeout=int(args.get("timeout") or 180),
        ctf_lab=bool(args.get("ctf_lab", False)),
        authorization_note=args.get("authorization_note") or "",
        scope_id=int(args.get("scope_id") or 0),
        apply_fixes=bool(args.get("apply_fixes", False)),
    )


def _security_lab_hardening(args: dict[str, Any]) -> dict[str, Any]:
    from core import security_lab

    return security_lab.hardening_plan(root=args.get("root") or "", target=args.get("target") or "")


def _security_lab_remediate(args: dict[str, Any]) -> dict[str, Any]:
    from core import security_lab

    return security_lab.remediate(
        run_id=int(args.get("run_id") or 0),
        root=args.get("root") or "",
        target=args.get("target") or "",
        apply=bool(args.get("apply", False)),
    )


def _validate_schema(schema: dict[str, Any], payload: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for key in schema.get("required") or []:
        value = payload.get(key)
        if key not in payload or value is None or value == "" or (isinstance(value, (list, dict)) and not value):
            errors.append(f"Missing required field: {key}")
    properties = schema.get("properties") if isinstance(schema.get("properties"), dict) else {}
    for key, spec in properties.items():
        if key not in payload or not isinstance(spec, dict):
            continue
        expected = spec.get("type")
        if expected == "array" and not isinstance(payload[key], list):
            errors.append(f"{key} must be an array")
        if expected == "integer" and not isinstance(payload[key], int):
            try:
                payload[key] = int(payload[key])
            except Exception:
                errors.append(f"{key} must be an integer")
        if expected == "boolean" and not isinstance(payload[key], bool):
            payload[key] = str(payload[key]).strip().lower() in {"1", "true", "yes", "y"}
    return errors


def _safe_args(args: dict[str, Any]) -> dict[str, Any]:
    blocked = {"password", "secret", "token", "api_key", "key"}
    return {key: "[redacted]" if any(part in key.lower() for part in blocked) else value for key, value in args.items()}


def _authority_approval_override(tool: str, args: dict[str, Any]) -> dict[str, Any] | None:
    if not autonomy_control.full_access_enabled():
        return None
    if not autonomy_control.is_trusted_scope(args):
        return None
    return {
        "authority_mode": "full_access",
        "summary": "Approval bypassed by full-access authority mode in a trusted scope.",
        "scope": [str(path) for path in autonomy_control.scope_paths(args)],
    }


def _tool_name(name: str) -> str:
    return ".".join(part for part in str(name or "").strip().lower().replace(" ", "_").split(".") if part)
