"""Central command routing and tool dispatch."""

from __future__ import annotations

import datetime as _dt
import time
import re
import threading
from pathlib import Path
from typing import Any, Callable

try:
    import psutil
except Exception:  # pragma: no cover - optional in scaffold tests
    psutil = None

from core.config import config_value, resolve_coding_root
from core.lazy_imports import lazy_callable, lazy_module


adaptive_attention = lazy_module("core.adaptive_attention")
agent_blackboard = lazy_module("core.agent_blackboard")
approval_inbox = lazy_module("core.approval_inbox")
autobiographical_memory = lazy_module("core.autobiographical_memory")
barge_in = lazy_module("core.barge_in")
capability_center = lazy_module("core.capability_center")
daily_companion = lazy_module("core.daily_companion")
emotion_tone = lazy_module("core.emotion_tone")
episodic_store = lazy_module("core.episodic_store")
evaluation_lab = lazy_module("core.evaluation_lab")
event_nervous_system = lazy_module("core.event_nervous_system")
evidence_gate = lazy_module("core.evidence_gate")
goal_regulation = lazy_module("core.goal_regulation")
intent_engine = lazy_module("core.intent_engine")
knowledge_graph = lazy_module("core.knowledge_graph")
llm = lazy_module("core.llm")
long_term_learning = lazy_module("core.long_term_learning")
memory = lazy_module("core.memory")
model_router_brain = lazy_module("core.model_router_brain")
pc_awareness = lazy_module("core.pc_awareness")
permissions = lazy_module("core.permissions")
personal_command_memory = lazy_module("core.personal_command_memory")
self_debugger = lazy_module("core.self_debugger")
self_model = lazy_module("core.self_model")
self_reflection = lazy_module("core.self_reflection")
voice_reliability = lazy_module("core.voice_reliability")
world_model = lazy_module("core.world_model")

agent_team = lazy_module("tools.agent_team")
app_integrations = lazy_module("tools.app_integrations")
capability_tool = lazy_module("tools.capability_center")
coding_tool = lazy_module("tools.coding_tool")
email_tool = lazy_module("tools.email_tool")
image_generation_tool = lazy_module("tools.image_generation")
pc_control = lazy_module("tools.pc_control")
phone_bridge = lazy_module("tools.phone_bridge")
power_center = lazy_module("tools.power_center")
self_update_tool = lazy_module("tools.self_update")
trading_tool = lazy_module("tools.trading_tool")
web_search = lazy_module("tools.web_search")
record_and_transcribe = lazy_callable("input.speech_to_text", "record_and_transcribe")
log = lazy_callable("output.display", "log")
speak = lazy_callable("output.voice", "speak")

TOOLS: dict[str, Callable[[dict[str, Any]], str]] = {
    "pc_control": lazy_callable("tools.pc_control", "execute"),
    "web_search": lazy_callable("tools.web_search", "execute"),
    "trading_data": lazy_callable("tools.trading_tool", "execute"),
    "send_email": lazy_callable("tools.email_tool", "execute"),
    "coding_assist": lazy_callable("tools.coding_tool", "execute"),
    "agent_team": lazy_callable("tools.agent_team", "execute"),
    "app_integrations": lazy_callable("tools.app_integrations", "execute"),
    "phone_bridge": lazy_callable("tools.phone_bridge", "execute"),
    "image_generation": lazy_callable("tools.image_generation", "execute"),
    "capability_center": lazy_callable("tools.capability_center", "execute"),
    "power_center": lazy_callable("tools.power_center", "execute"),
    "self_update": lazy_callable("tools.self_update", "execute"),
}

ROUTER_BUILD = "2026-05-22-logo-image-routing-v1"

DESTRUCTIVE = {"send_email", "delete_file"}
PRE_DIRECT_INTENTS = {
    "start_coding_project",
    "project_ideas",
    "create_agent_task",
    "create_reminder",
    "generate_image",
    "search_workspace",
    "web_search",
    "academic_project",
    "git_status",
    "git_branches",
    "git_diff",
    "git_log",
    "git_clone",
    "git_checkout",
    "git_pull",
    "git_add",
    "git_commit",
    "git_push",
    "github_status",
    "github_pr_create",
    "github_pr_list",
    "github_issue_create",
    "create_3d_model",
    "workspace_analyze",
    "codebase_standards",
}
_PENDING_CONFIRMATION: dict[str, Any] | None = None
_PENDING_CONFIRMATION_LOCK = threading.Lock()
TOOL_HINTS = (
    "open",
    "close",
    "launch",
    "start app",
    "run command",
    "shell",
    "powershell",
    "terminal",
    "mouse",
    "click",
    "double click",
    "right click",
    "scroll",
    "type",
    "press",
    "hotkey",
    "screenshot",
    "screen shot",
    "inspect screen",
    "look at screen",
    "see my screen",
    "desktop task",
    "operate",
    "navigate",
    "focus window",
    "active window",
    "list files",
    "read file",
    "folder",
    "chrome",
    "notepad",
    "vscode",
    "spotify",
    "explorer",
    "camera",
    "search",
    "google",
    "look up",
    "find online",
    "browse",
    "http://",
    "https://",
    ".com",
    "price of",
    "stock",
    "market",
    "ticker",
    "crypto",
    "bitcoin",
    "btc",
    "eth",
    "news",
    "email",
    "mail",
    "calendar",
    "docs",
    "sheets",
    "whatsapp",
    "discord",
    "contact",
    "contacts",
    "reminder",
    "remind me",
    "workspace index",
    "index workspace",
    "search workspace",
    "send",
    "review this file",
    "review file",
    "debug this file",
    "agent",
    "agents",
    "team",
    "task",
    "queue task",
    "assign",
    "working on",
    "permission",
    "permissions",
    "safety",
    "self update",
    "update your codebase",
    "update your own code",
    "modify your code",
    "improve your code",
    "stage change",
    "apply self update",
    "friday's brain",
    "your brain",
    "world model",
    "going on right now",
    "current goals",
    "focused on",
    "reflect",
    "learned recently",
    "attention profile",
    "approval inbox",
    "blackboard",
    "evaluation lab",
    "voice reliability",
    "generate image",
    "create image",
    "make image",
    "generate logo",
    "create logo",
    "make logo",
    "design logo",
    "draw",
    "text to image",
    "phone bridge",
    "ring my phone",
    "call me on my phone",
    "open on my phone",
    "daily brief",
    "what should i do next",
    "maintenance report",
    "security overview",
    "security lab",
    "hardening plan",
    "codebase standards",
    "coding standards",
    "programmer laws",
    "code hygiene",
    "project map",
    "dependency health",
    "network devices",
    "router status",
    "automation recipe",
    "git status",
    "git branches",
    "git diff",
    "git log",
    "git clone",
    "git add",
    "git commit",
    "git push",
    "github status",
    "github pr",
    "pull request",
    "3d model",
    "3d asset",
    "glb",
    "gltf",
    "stl",
)


def handle_command(user_text: str) -> str:
    original_text = user_text
    learned_command: dict[str, Any] | None = None
    interrupt_reply = barge_in.handle_if_interrupt(user_text)
    if interrupt_reply:
        return _record_command_event(user_text, interrupt_reply, "barge_in")
    if _looks_like_transcription_artifact(user_text):
        return _record_command_event(
            user_text,
            "I ignored that because it looked like a transcription artifact.",
            "transcription_artifact",
            success=False,
        )
    confirmation_reply = _handle_pending_confirmation(user_text)
    if confirmation_reply:
        success = not confirmation_reply.lower().startswith(("action cancelled", "permission expired"))
        memory.add_user(user_text)
        memory.add_assistant(confirmation_reply)
        return _record_command_event(user_text, confirmation_reply, "permission_confirmation", success=success)
    try:
        emotion_tone.analyze_text(user_text)
    except Exception:
        pass
    try:
        learned_command = personal_command_memory.resolve(user_text)
        if learned_command and learned_command.get("canonical_command"):
            user_text = str(learned_command["canonical_command"])
    except Exception:
        learned_command = None
    memory.add_user(user_text)
    profile_reply = _handle_profile_fact(user_text)
    if profile_reply:
        memory.add_assistant(profile_reply)
        if learned_command:
            personal_command_memory.record_result(int(learned_command["id"]), success=True, note=f"Expanded from: {original_text}")
        return _record_command_event(user_text, profile_reply, "profile")

    intent_reply, intent_action = _handle_intent_command(user_text, allow_llm=False, phase="pre_direct")
    if intent_reply:
        memory.add_assistant(intent_reply)
        if learned_command:
            personal_command_memory.record_result(int(learned_command["id"]), success=not _reply_failed(intent_reply), note=f"Expanded from: {original_text}")
        return _record_command_event(user_text, intent_reply, intent_action, success=not _reply_failed(intent_reply))

    direct_reply = _handle_direct_command(user_text)
    if direct_reply:
        memory.add_assistant(direct_reply)
        if learned_command:
            personal_command_memory.record_result(int(learned_command["id"]), success=True, note=f"Expanded from: {original_text}")
        return _record_command_event(user_text, direct_reply, "learned_direct_command" if learned_command else "direct_command")

    intent_reply, intent_action = _handle_intent_command(user_text, allow_llm=True, phase="semantic_fallback")
    if intent_reply:
        memory.add_assistant(intent_reply)
        if learned_command:
            personal_command_memory.record_result(int(learned_command["id"]), success=not _reply_failed(intent_reply), note=f"Expanded from: {original_text}")
        return _record_command_event(user_text, intent_reply, intent_action, success=not _reply_failed(intent_reply))

    facts = memory.recall(user_text)
    messages = _conversation_messages(user_text, facts)

    response = llm.ask(messages, tools=_tools_for_command(user_text))
    if response is None:
        if learned_command:
            personal_command_memory.record_result(int(learned_command["id"]), success=False, note="LLM connection failed after command expansion.")
        return _record_command_event(user_text, "I am having trouble connecting. Please try again.", "llm_error", success=False)

    for block in _content_blocks(response):
        block_type = _block_value(block, "type")
        if block_type == "tool_use":
            reply = _handle_tool_block(block, user_text=user_text)
            if learned_command:
                failed = reply.lower().startswith(("action cancelled", "permission blocked", "power center action failed", "i could not", "failed"))
                personal_command_memory.record_result(int(learned_command["id"]), success=not failed, note=f"Expanded from: {original_text}")
            return _record_command_event(user_text, reply, "tool_command")
        if block_type == "text":
            text = str(_block_value(block, "text") or "")
            guarded_reply = _guard_unverified_pc_claim(user_text, text)
            if not guarded_reply:
                guarded_reply = evidence_gate.guard_reply(user_text, text, evidence=None)
                if guarded_reply == text:
                    guarded_reply = ""
            if guarded_reply:
                memory.add_assistant(guarded_reply)
                if learned_command:
                    personal_command_memory.record_result(int(learned_command["id"]), success=True, note=f"Expanded from: {original_text}")
                return _record_command_event(user_text, guarded_reply, "guarded_direct_command")
            memory.add_assistant(text)
            reply = memory.strip_remember_tags(text)
            if learned_command:
                personal_command_memory.record_result(int(learned_command["id"]), success=True, note=f"Expanded from: {original_text}")
            return _record_command_event(user_text, reply, "llm_text")
    if learned_command:
        personal_command_memory.record_result(int(learned_command["id"]), success=False, note="Expanded command was not understood.")
    return _record_command_event(user_text, "I did not understand that command.", "unknown", success=False)


def _looks_like_transcription_artifact(text: str) -> bool:
    normalized = re.sub(r"[^\w\s]", " ", text or "").lower()
    normalized = re.sub(r"\s+", " ", normalized).strip()
    phrases = (
        "audio is a short command for an ai assistant",
        "the audio is a short command for an ai assistant",
        "short command for an ai assistant named",
        "common words include",
        "thank you for watching",
        "thanks for watching",
        "do not forget to subscribe",
        "i'm going to show you how to",
        "i am going to show you how to",
        "the ai assistant is a",
    )
    return any(phrase in normalized for phrase in phrases)


def _handle_profile_fact(user_text: str) -> str:
    text = user_text.strip()
    match = re.search(r"\b(?:my name is|call me)\s+([a-z][a-z .'-]{1,40})\b", text, re.IGNORECASE)
    if match:
        raw_name = match.group(1).strip(" .,!?:;")
    else:
        match = re.search(r"\b(?:i am|i'm)\s+([a-z][a-z'-]{1,24})\s*$", text, re.IGNORECASE)
        if not match:
            return ""
        raw_name = match.group(1).strip(" .,!?:;")
        if raw_name.lower() in {"doing", "going", "here", "there", "fine", "good", "okay", "ok", "talking", "speaking", "trying"}:
            return ""
    if not raw_name:
        return ""
    raw_name = re.split(r"\b(?:and|but|so|because|from|in)\b", raw_name, maxsplit=1, flags=re.IGNORECASE)[0].strip()
    if not raw_name:
        return ""
    name = " ".join(part.capitalize() for part in raw_name.split())
    memory.remember_fact(f"user's name is {name}")
    _record_autobiography("preference", "Learned user's name", f"The user prefers to be called {name}.", importance=0.75)
    return f"Nice to meet you, {name}."


def _handle_tool_block(block: Any, *, user_text: str = "") -> str:
    tool_name = str(_block_value(block, "name") or "")
    tool_input = _block_value(block, "input") or {}
    tool_id = str(_block_value(block, "id") or tool_name)
    permission = permissions.evaluate(tool_name, tool_input)
    if permission["blocked"]:
        reply = f"Permission blocked: {permission['label']} is set to block."
        permissions.record_decision(tool_name, tool_input, decision="blocked", mode=permission["mode"], key=permission["key"])
        _record_tool_event(tool_name, tool_input, reply, success=False)
        return reply
    if permission["requires_confirmation"]:
        if not tool_input.get("_permission_confirmed"):
            return _queue_confirmation(tool_name, tool_input, permission, tool_id=tool_id, user_text=user_text)
        permissions.record_decision(tool_name, tool_input, decision="approved", mode=permission["mode"], key=permission["key"])
        if isinstance(tool_input, dict):
            tool_input = dict(tool_input)
            tool_input["_permission_confirmed"] = True
    else:
        permissions.record_decision(tool_name, tool_input, decision="allowed", mode=permission["mode"], key=permission["key"])
    if _tool_requires_confirmation(tool_name, tool_input, permission=permission) and not tool_input.get("_permission_confirmed"):
        return _queue_confirmation(
            tool_name,
            tool_input,
            {"label": tool_name, "mode": "ask", "key": f"{tool_name}.confirmation"},
            tool_id=tool_id,
            user_text=user_text,
        )
    tool_fn = TOOLS.get(tool_name)
    if tool_fn is None:
        return f"Tool {tool_name} not found."

    start = time.perf_counter()
    try:
        result = tool_fn(tool_input)
    except Exception as exc:
        log("ERROR", str(exc))
        _record_tool_event(tool_name, tool_input, str(exc), success=False)
        return "I ran into a problem with that. Please try again."

    latency_ms = (time.perf_counter() - start) * 1000
    log("DEBUG", f"[ORCH] tool={tool_name} input={tool_input} result={result!r} latency={latency_ms:.0f}ms")
    verified_success = evidence_gate.tool_result_success(result) and not evidence_gate.is_unverified_result(result)
    _record_tool_event(tool_name, tool_input, result, success=verified_success, latency_ms=latency_ms)
    memory.add_tool_result(tool_id, result)
    if not bool(config_value("tool_result_summarize", False)):
        reply = _voice_tool_result(result)
        reply = evidence_gate.guard_reply(user_text, reply, evidence=result)
        memory.add_assistant(reply)
        return reply

    final = llm.ask(
        memory.get_messages()
        + [{"role": "user", "content": f"The tool {tool_name} returned: {result}. Give a concise voice response."}],
        tools=[],
    )
    reply = llm.extract_text(final) if final else result
    if not reply:
        reply = result
    reply = evidence_gate.guard_reply(user_text, reply, evidence=result)
    memory.add_assistant(reply)
    return memory.strip_remember_tags(reply)


def _record_command_event(user_text: str, reply: str, action_type: str, success: bool = True) -> str:
    try:
        reply = emotion_tone.adjust_reply(user_text, reply)
    except Exception:
        pass
    try:
        episodic_store.insert_event(
            agent_id="jarvis",
            action_type=action_type,
            inputs={"user_text": user_text},
            outputs={"reply": reply},
            success_score=1.0 if success else 0.0,
        )
        knowledge_graph.add_edge("User", "ASKED", _graph_label(user_text), action_type=action_type)
        knowledge_graph.add_edge("Jarvis", "ANSWERED", _graph_label(reply), action_type=action_type, success=success)
    except Exception as exc:
        log("DEBUG", f"[MEM] command event skipped: {exc}")
    _record_autobiographical_command_event(user_text, reply, action_type, success)
    _record_cognitive_feedback(user_text, reply, success=success)
    return reply


def _record_tool_event(
    tool_name: str,
    tool_input: dict[str, Any],
    result: str,
    *,
    success: bool,
    latency_ms: float | None = None,
) -> None:
    try:
        metadata = {"latency_ms": latency_ms} if latency_ms is not None else {}
        episodic_store.insert_event(
            agent_id="jarvis",
            action_type="tool_use",
            inputs={"tool": tool_name, "input": tool_input},
            outputs={"result": result},
            success_score=1.0 if success else 0.0,
            metadata=metadata,
        )
        knowledge_graph.add_edge("Jarvis", "EXECUTED", tool_name, success=success, latency_ms=latency_ms)
    except Exception as exc:
        log("DEBUG", f"[MEM] tool event skipped: {exc}")
    if not success:
        try:
            evaluation_lab.record_event(
                "failed_tool",
                f"{tool_name} did not verify success: {str(result)[:240]}",
                source="orchestrator",
                severity=3,
                metadata={"tool": tool_name, "input": tool_input, "latency_ms": latency_ms},
            )
        except Exception:
            pass
        _record_autobiography(
            "tool_failure",
            f"{tool_name} did not verify success",
            str(result)[:500],
            importance=0.8,
            tool=tool_name,
            input=tool_input,
            latency_ms=latency_ms,
        )
    elif tool_name in {"pc_control", "self_update", "app_integrations"}:
        _record_autobiography(
            "tool_success",
            f"{tool_name} succeeded",
            str(result)[:500],
            importance=0.55,
            tool=tool_name,
            input=tool_input,
            latency_ms=latency_ms,
        )


def _record_cognitive_feedback(user_text: str, reply: str, *, success: bool) -> None:
    try:
        if bool(config_value("self_reflection_failure_trigger_enabled", True)):
            finding = self_reflection.reflect_on_command(user_text, reply, success_score=1.0 if success else 0.0)
            if finding:
                goal_regulation.infer_state_from_feedback(user_text)
                adaptive_attention.record_user_correction(user_text, reply if not success else "")
                _record_autobiography(
                    "user_correction",
                    str(finding.get("category") or "User correction"),
                    str(finding.get("finding") or ""),
                    importance=0.85,
                    finding=finding,
                )
    except Exception as exc:
        log("DEBUG", f"[COG] feedback reflection skipped: {exc}")


def _graph_label(text: str, limit: int = 120) -> str:
    cleaned = " ".join(str(text or "").split())
    return cleaned if len(cleaned) <= limit else cleaned[: limit - 3] + "..."


def _tools_for_command(user_text: str) -> list[dict[str, Any]] | None:
    text = user_text.lower()
    if any(hint in text for hint in TOOL_HINTS):
        return None
    return []


def _handle_intent_command(user_text: str, *, allow_llm: bool, phase: str) -> tuple[str, str]:
    if not bool(config_value("intent_router_enabled", True)):
        return "", ""
    result = intent_engine.classify(user_text, allow_llm=allow_llm)
    if phase == "pre_direct" and result.intent not in PRE_DIRECT_INTENTS:
        return "", ""
    if result.ask_user and result.confidence >= max(0.65, result.min_confidence - 0.1):
        action = "semantic_intent_clarification" if result.source == "llm" else "intent_clarification"
        return result.ask_user, action
    if not result.actionable:
        return "", ""
    tool_result = _run_tool_with_permissions(result.tool_name, dict(result.tool_input))
    reply = _voice_tool_result(tool_result)
    action = "semantic_intent_command" if result.source == "llm" else "intent_command"
    return reply, action


def _reply_failed(reply: str) -> bool:
    lowered = str(reply or "").strip().lower()
    return lowered.startswith(
        (
            "action cancelled",
            "permission blocked",
            "permission expired",
            "i could not",
            "failed",
            "unknown ",
        )
    )


def _tool_requires_confirmation(tool_name: str, tool_input: dict[str, Any], permission: dict[str, Any] | None = None) -> bool:
    if tool_name in DESTRUCTIVE:
        return True
    if permission and permission.get("autonomy_override") and permission.get("mode") == "allow":
        return False
    if tool_name == "pc_control":
        action = str((tool_input or {}).get("action", "")).lower()
        return action in {"run_command"}
    return False


def _run_tool_with_permissions(tool_name: str, tool_input: dict[str, Any]) -> str:
    permission = permissions.evaluate(tool_name, tool_input)
    if permission["blocked"]:
        permissions.record_decision(tool_name, tool_input, decision="blocked", mode=permission["mode"], key=permission["key"])
        return f"Permission blocked: {permission['label']} is set to block."
    if permission["requires_confirmation"]:
        if not tool_input.get("_permission_confirmed"):
            return _queue_confirmation(tool_name, tool_input, permission)
        tool_input = dict(tool_input)
        tool_input["_permission_confirmed"] = True
        permissions.record_decision(tool_name, tool_input, decision="approved", mode=permission["mode"], key=permission["key"])
    else:
        permissions.record_decision(tool_name, tool_input, decision="allowed", mode=permission["mode"], key=permission["key"])
    if _tool_requires_confirmation(tool_name, tool_input, permission=permission) and not tool_input.get("_permission_confirmed"):
        return _queue_confirmation(tool_name, tool_input, {"label": tool_name, "mode": "ask", "key": f"{tool_name}.confirmation"})
    if tool_name == "pc_control":
        tool_fn = pc_control.execute
    elif tool_name == "app_integrations":
        tool_fn = app_integrations.execute
    elif tool_name == "phone_bridge":
        tool_fn = phone_bridge.execute
    elif tool_name == "capability_center":
        tool_fn = capability_tool.execute
    elif tool_name == "agent_team":
        tool_fn = agent_team.execute
    elif tool_name == "image_generation":
        tool_fn = image_generation_tool.execute
    elif tool_name == "web_search":
        tool_fn = web_search.execute
    elif tool_name == "power_center":
        tool_fn = power_center.execute
    elif tool_name == "self_update":
        tool_fn = self_update_tool.execute
    else:
        tool_fn = TOOLS.get(tool_name)
    if tool_fn is None:
        return f"Tool {tool_name} not found."
    return tool_fn(tool_input)


def _pc(inputs: dict[str, Any]) -> str:
    return _run_tool_with_permissions("pc_control", inputs)


def _apps(inputs: dict[str, Any]) -> str:
    return _run_tool_with_permissions("app_integrations", inputs)


def _phone(inputs: dict[str, Any]) -> str:
    return _run_tool_with_permissions("phone_bridge", inputs)


def _capability(inputs: dict[str, Any]) -> str:
    return _run_tool_with_permissions("capability_center", inputs)


def _power(inputs: dict[str, Any]) -> str:
    return _run_tool_with_permissions("power_center", inputs)


def _self_update(inputs: dict[str, Any]) -> str:
    return _run_tool_with_permissions("self_update", inputs)


def _queue_confirmation(
    tool_name: str,
    tool_input: dict[str, Any],
    permission: dict[str, Any],
    *,
    tool_id: str = "",
    user_text: str = "",
) -> str:
    label = str(permission.get("label") or tool_name or "this action").strip()
    ttl = max(30.0, float(config_value("permission_confirmation_ttl_seconds", 180.0)))
    pending = {
        "tool_name": str(tool_name or ""),
        "tool_input": dict(tool_input or {}),
        "tool_id": str(tool_id or ""),
        "user_text": str(user_text or ""),
        "label": label,
        "key": str(permission.get("key") or ""),
        "mode": str(permission.get("mode") or "ask"),
        "created_at": time.time(),
        "expires_at": time.time() + ttl,
    }
    with _PENDING_CONFIRMATION_LOCK:
        global _PENDING_CONFIRMATION
        _PENDING_CONFIRMATION = pending
    return f"Are you sure you want to run {label}? Reply yes to continue, or no to cancel."


def _handle_pending_confirmation(user_text: str) -> str:
    pending = _current_pending_confirmation()
    if not pending:
        return ""
    lowered = _strip_leading_assistant_name(user_text).strip(" ,.!?:;").lower()
    if not lowered:
        return ""
    if time.time() > float(pending.get("expires_at") or 0):
        _clear_pending_confirmation()
        if _is_confirmation_yes(lowered) or _is_confirmation_no(lowered):
            return "Permission expired. Please ask me to run it again."
        return ""
    if _is_confirmation_no(lowered):
        _clear_pending_confirmation()
        permissions.record_decision(
            str(pending.get("tool_name") or ""),
            dict(pending.get("tool_input") or {}),
            decision="cancelled",
            mode=str(pending.get("mode") or "ask"),
            key=str(pending.get("key") or ""),
        )
        return "Action cancelled."
    if not _is_confirmation_yes(lowered):
        return ""
    _clear_pending_confirmation()
    tool_name = str(pending.get("tool_name") or "")
    tool_input = dict(pending.get("tool_input") or {})
    tool_input["_permission_confirmed"] = True
    result = _run_tool_with_permissions(tool_name, tool_input)
    tool_id = str(pending.get("tool_id") or "")
    if tool_id:
        memory.add_tool_result(tool_id, result)
    return _voice_tool_result(result)


def _current_pending_confirmation() -> dict[str, Any] | None:
    with _PENDING_CONFIRMATION_LOCK:
        return dict(_PENDING_CONFIRMATION) if _PENDING_CONFIRMATION else None


def _clear_pending_confirmation() -> None:
    with _PENDING_CONFIRMATION_LOCK:
        global _PENDING_CONFIRMATION
        _PENDING_CONFIRMATION = None


def _is_confirmation_yes(lowered: str) -> bool:
    return bool(
        re.fullmatch(
            r"(?:yes|yeah|yep|yup|confirm|confirmed|approve|approved|authorize|authorized|do it|go ahead|continue|proceed|sure|affirmative)(?:\s+please)?",
            lowered,
        )
    )


def _is_confirmation_no(lowered: str) -> bool:
    return bool(re.fullmatch(r"(?:no|nope|cancel|cancel it|stop|abort|wait|not now|never mind|nevermind)", lowered))


def _conversation_messages(user_text: str, facts: list[str]) -> list[dict[str, Any]]:
    max_messages = max(1, int(config_value("conversation_context_messages", 1)))
    messages = memory.get_messages()[-max_messages:]
    if not messages or messages[-1].get("content") != user_text:
        messages.append({"role": "user", "content": user_text})
    style = _conversation_style_context(user_text)
    if style:
        messages = [{"role": "user", "content": style}] + messages
    context = memory.build_context(user_text, facts=facts)
    if context:
        messages = [{"role": "user", "content": "Relevant context:\n" + context}] + messages
    cognitive = _cognitive_context_for(user_text)
    if cognitive:
        messages = [{"role": "user", "content": cognitive}] + messages
    return messages


def _conversation_style_context(user_text: str) -> str:
    if not bool(config_value("conversation_style_context_enabled", True)):
        return ""
    lines = [
        "Conversation style for this turn:",
        "- Treat this as an ongoing chat, not a stateless command.",
        "- Respond to the user's actual wording; a brief acknowledgement is okay when it makes the reply feel more human.",
        "- Keep the useful answer close to the top, and use recent messages for continuity.",
        "- If the user is asking for an action, execute or route the action first, then summarize plainly.",
        "- Avoid canned closers, generic reassurance, and repeated status-bot phrasing.",
    ]
    try:
        guidance = emotion_tone.response_guidance(user_text)
        if guidance.get("should_adjust_reply"):
            lines.append(f"- Tone guidance: {guidance.get('need')}")
    except Exception:
        pass
    return "\n".join(lines)


def _cognitive_context_for(user_text: str) -> str:
    lowered = str(user_text or "").lower()
    if not bool(config_value("cognitive_context_in_llm_enabled", True)):
        return ""
    triggers = ("screen", "app", "desktop", "goal", "focus", "remember", "learn", "why", "failed", "didn't work", "did not work", "wrong")
    if not any(trigger in lowered for trigger in triggers):
        return ""
    parts: list[str] = []
    try:
        if bool(config_value("world_model_enabled", True)):
            parts.append(world_model.planner_context())
    except Exception:
        pass
    try:
        if bool(config_value("goal_regulation_enabled", True)):
            parts.append(goal_regulation.regulation_prompt_context())
    except Exception:
        pass
    try:
        reflection = self_reflection.reflection_context(limit=3)
        if reflection:
            parts.append(reflection)
    except Exception:
        pass
    try:
        learning = long_term_learning.learning_context(user_text, limit=3)
        if learning:
            parts.append(learning)
    except Exception:
        pass
    try:
        tone = emotion_tone.tone_context()
        if tone:
            parts.append(tone)
    except Exception:
        pass
    return "\n\n".join(part for part in parts if part)


def _handle_direct_command(user_text: str) -> str:
    text = _clean_text(user_text)
    if not text:
        return ""

    reply = _direct_personal_command_memory(text)
    if reply:
        return reply

    reply = _direct_small_talk(text)
    if reply:
        return reply

    reply = _direct_datetime(text)
    if reply:
        return reply

    reply = _direct_phone_bridge(text)
    if reply:
        return reply

    reply = _direct_self_model(text)
    if reply:
        return reply

    reply = _direct_cognition(text)
    if reply:
        return reply

    reply = _direct_capability_center(text)
    if reply:
        return reply

    reply = _direct_power_center(text)
    if reply:
        return reply

    reply = _direct_system_status(text)
    if reply:
        return reply

    reply = _direct_quick_knowledge(text)
    if reply:
        return reply

    reply = _direct_project_ideas(text)
    if reply:
        return reply

    reply = _direct_agent_team(text)
    if reply:
        return reply

    reply = _direct_operational_labs(text)
    if reply:
        return reply

    reply = _direct_memory(text)
    if reply:
        return reply

    reply = _direct_permissions(text)
    if reply:
        return reply

    reply = _direct_self_update(text)
    if reply:
        return reply

    reply = _direct_app_integrations(text)
    if reply:
        return reply

    reply = _direct_build_request(text)
    if reply:
        return reply

    reply = _direct_image_generation(text)
    if reply:
        return reply

    reply = _direct_pc_awareness(text)
    if reply:
        return reply

    reply = _direct_pc_control(text)
    if reply:
        return reply

    reply = _direct_web_search(text)
    if reply:
        return reply

    reply = _direct_draft(text)
    if reply:
        return reply

    reply = _direct_coding(text)
    if reply:
        return reply

    reply = _direct_file_request(text)
    if reply:
        return reply

    return ""


def _direct_personal_command_memory(text: str) -> str:
    learned = personal_command_memory.parse_learning_phrase(text)
    if learned:
        item = personal_command_memory.learn(learned[0], learned[1], notes="learned from voice/chat")
        return item.get("summary", "Command shortcut learned.")
    lowered = text.lower().strip()
    if lowered in {"what commands have you learned", "list learned commands", "show command memory", "personal command memory"}:
        items = personal_command_memory.list_commands(limit=8)
        if not items:
            return "I have not learned any personal command shortcuts yet."
        return "\n".join(f"{item['heard_phrase']} -> {item['canonical_command']}" for item in items)
    return ""


def _direct_small_talk(text: str) -> str:
    lowered = text.lower()
    addressed = _strip_assistant_names(lowered)
    if addressed in {"hello", "hi", "hey"} or lowered in {"hey jarvis", "jarvis"}:
        name = _remembered_name()
        return f"Hey {name}. What are we getting into today?" if name else "Hey. What are we getting into today?"
    if re.fullmatch(r"(?:thanks|thank you|thank you very much|appreciate it)", addressed):
        return "You're welcome."
    if re.fullmatch(r"(?:how are you|how are you doing|how are you doing today|how's it going)", addressed):
        return "I'm good. What are you thinking through?"
    if re.fullmatch(
        r"(?:what are you doing|what're you doing|what are you working on|what're you working on|what are you up to|are you doing anything)",
        addressed,
    ):
        return self_model.current_activity_summary() + " Ask 'team status' if you want the agent queue."
    if re.fullmatch(r"(?:what is your name|what's your name|who are you)", addressed):
        return f"My name is {config_value('jarvis_name', 'Friday')}."
    if re.fullmatch(
        r"(?:what build are you running|what version are you running|what(?:'s| is) your build|router build|router version|build version)",
        addressed,
    ):
        return f"Router build {ROUTER_BUILD} from {Path(__file__).resolve()}."
    if re.fullmatch(r"(?:can you code|do you code|can you help me code|do you know how to code)", addressed):
        return "Yes. I can help write, review, debug, and explain code."
    if re.fullmatch(
        r"(?:what can you do|what are your abilities|what are your capabilities|list(?: all)?(?: the)? functions you have|list(?: your| all)? capabilities|list(?: your| all)? functions|list(?: all)?(?: the)? things you can do|show(?: me)?(?: all)?(?: your)? functions|show(?: me)?(?: all)?(?: your)? capabilities)",
        addressed,
    ):
        return _capabilities_summary()
    if re.search(r"\bwhat(?:'s| is) my name\b", lowered):
        name = _remembered_name()
        return f"Your name is {name}." if name else "I do not know your name yet."
    return ""


def _capabilities_summary() -> str:
    return self_model.capability_summary()


def _direct_self_model(text: str) -> str:
    cleaned = _strip_leading_assistant_name(text).strip(" ,.!?:;")
    lowered = cleaned.lower()
    if not lowered:
        return ""
    if re.fullmatch(r"(?:what(?:'s| is)\s+)?(?:your\s+)?(?:self model|self status|introspection|self awareness|self-aware status)", lowered):
        status = self_model.status()
        runtime = status.get("runtime") or {}
        return f"I am {runtime.get('llm_provider')} online with {runtime.get('stt_backend')} STT, {len(status.get('tools') or [])} tool groups, and {len(status.get('limitations') or [])} known limitations."
    if re.fullmatch(r"(?:what tools do you have|list your tools|show your tools)", lowered):
        return self_model.tools_summary()
    if re.fullmatch(r"(?:what are you unsure about|what are you uncertain about|what don't you know|what do you not know)", lowered):
        return self_model.uncertainty_summary()
    if re.fullmatch(r"(?:what can you currently access|what do you have access to|what can you access)", lowered):
        return self_model.access_summary()
    if re.fullmatch(r"(?:what failed recently|show recent failures|what has failed recently|recent failures)", lowered):
        return self_model.failure_summary()
    if re.fullmatch(r"(?:why did you say that|why did you answer that|why did you do that|explain your last action)", lowered):
        return self_model.why_last_action_summary()
    if re.fullmatch(r"(?:who are you really|what are your values|what is your identity|show your identity|what must you never pretend)", lowered):
        return self_model.identity_voice_summary()
    if re.fullmatch(r"(?:show|tell me)\s+(?:your\s+)?(?:timeline|autobiography|autobiographical memory)", lowered):
        return autobiographical_memory.timeline_summary(limit=6)
    return ""


def _direct_datetime(text: str) -> str:
    lowered = _strip_assistant_names(text.lower())
    lowered = lowered.strip(" ,.!?:;")
    now = _dt.datetime.now()
    if re.fullmatch(
        r"(?:can you tell me )?(?:what time is it|what (?:the )?time is|what(?:'s| is) (?:the )?time|(?:the )?(?:current )?time)",
        lowered,
    ):
        return f"It is {_format_time(now)}."
    if re.fullmatch(
        r"(?:can you tell me )?(?:what date is it|what (?:the )?date is|what(?:'s| is) (?:the )?date|(?:the )?(?:current |today's )?date)",
        lowered,
    ):
        return f"Today is {_format_date(now)}."
    if re.fullmatch(r"(?:can you tell me )?(?:what|which) day(?: is it| is today)?", lowered):
        return f"Today is {now.strftime('%A')}."
    return ""


def _direct_system_status(text: str) -> str:
    lowered = _strip_assistant_names(text.lower()).strip(" ,.!?:;")
    if re.search(r"\b(?:battery|laptop(?:'s)? percentage|percentage of my laptop|power level|charge level)\b", lowered):
        return _battery_percentage()
    return ""


def _direct_quick_knowledge(text: str) -> str:
    lowered = _strip_assistant_names(text.lower()).strip(" ,.!?:;")
    definitions = {
        "adjective": "An adjective is a word that describes a noun, like blue, tall, or careful.",
        "noun": "A noun is a word for a person, place, thing, or idea.",
        "verb": "A verb is a word that shows an action or state, like run, think, or is.",
        "adverb": "An adverb describes a verb, adjective, or another adverb, often telling how, when, or where.",
        "pronoun": "A pronoun replaces a noun, like he, she, they, it, or you.",
        "preposition": "A preposition shows relationship, often location or time, like in, on, under, or before.",
        "conjunction": "A conjunction joins words or ideas, like and, but, or because.",
        "interjection": "An interjection is a short expression of feeling, like wow, oh, or hey.",
        "article": "An article is a word before a noun: a, an, or the.",
        "phrase": "A phrase is a group of words that works together but does not have both a subject and a verb.",
        "clause": "A clause is a group of words with a subject and a verb.",
        "sentence": "A sentence is a complete thought with a subject and a predicate.",
    }
    match = re.fullmatch(r"(?:can you tell me )?(?:what(?:'s| is)|define|explain)\s+(?:an?|the)?\s*([a-z ]+)", lowered)
    if not match:
        return ""
    term = re.sub(r"\s+", " ", match.group(1)).strip()
    if term in definitions:
        return definitions[term]
    return ""


def _battery_percentage() -> str:
    if psutil is None or not hasattr(psutil, "sensors_battery"):
        return "I cannot read the battery percentage on this PC."
    try:
        battery = psutil.sensors_battery()
    except Exception:
        battery = None
    if battery is None:
        return "I cannot read the battery percentage on this PC."
    percent = int(round(float(getattr(battery, "percent", 0.0))))
    plugged = bool(getattr(battery, "power_plugged", False))
    suffix = " and charging" if plugged else ""
    return f"Battery is at {percent}%{suffix}."


def _format_time(value: _dt.datetime) -> str:
    return value.strftime("%I:%M %p").lstrip("0")


def _format_date(value: _dt.datetime) -> str:
    return value.strftime("%A, %B %d, %Y").replace(" 0", " ")


def _strip_assistant_names(text: str) -> str:
    cleaned = text
    names = str(config_value("attention_names", "friday,computer,jarvis")).split(",")
    names.extend(["jarvis", "jervis"])
    for name in sorted({item.strip().lower() for item in names if item.strip()}, key=len, reverse=True):
        cleaned = re.sub(rf"\b{re.escape(name)}\b", "", cleaned, flags=re.IGNORECASE)
    return cleaned.strip(" ,.!?:;")


def _strip_leading_assistant_name(text: str) -> str:
    cleaned = str(text or "").strip()
    names = str(config_value("attention_names", "friday,computer,jarvis")).split(",")
    names.extend(["jarvis", "jervis"])
    for name in sorted({item.strip().lower() for item in names if item.strip()}, key=len, reverse=True):
        cleaned = re.sub(rf"^(?:hey\s+)?{re.escape(name)}\b[\s,.:;!-]*", "", cleaned, flags=re.IGNORECASE)
    return cleaned.strip(" ,.!?:;")


def _direct_memory(text: str) -> str:
    match = re.search(r"\bremember(?: that)?\s+(.+)$", text, re.IGNORECASE)
    if not match:
        return ""
    fact = match.group(1).strip(" .,!?:;")
    if not fact:
        return ""
    memory.remember_fact(fact)
    _record_autobiography("preference", "Remembered user-provided fact", fact, importance=0.7)
    return "Remembered."


def _direct_permissions(text: str) -> str:
    cleaned = _strip_leading_assistant_name(text).strip(" ,.!?:;")
    lowered = cleaned.lower()
    if not lowered:
        return ""

    if re.fullmatch(r"(?:show|list|open|what are)\s+(?:my\s+)?(?:safety|permission|permissions)(?:\s+settings|\s+rules)?", lowered):
        rules = permissions.list_rules()
        ask = [rule["label"] for rule in rules if rule["mode"] == "ask"][:5]
        blocked = [rule["label"] for rule in rules if rule["mode"] == "block"][:5]
        return f"Safety center has {len(rules)} rules. Ask: {', '.join(ask) or 'none'}. Blocked: {', '.join(blocked) or 'none'}."

    if re.fullmatch(r"(?:reset|restore)\s+(?:safety|permission|permissions)(?:\s+settings|\s+rules)?", lowered):
        permissions.reset_defaults()
        return "Safety permissions reset to defaults."

    if re.search(r"\bmay\b", lowered) and re.search(r"\bvolume|audio\b", lowered):
        changed = permissions.set_named_policy("volume", "allow")
        return _permission_change_reply(changed, "allow")

    if re.search(r"\bmust ask\b|\bask before\b|\bask me before\b", lowered):
        changed: list[dict[str, Any]] = []
        if re.search(r"\bdelete|deleting|remove files?|deleting files?\b", lowered):
            changed.extend(permissions.set_named_policy("deleting files", "ask"))
        if re.search(r"\bsend|sending|message|messages|email|mail\b", lowered):
            changed.extend(permissions.set_named_policy("messages", "ask"))
        if re.search(r"\bcommand|shell|powershell|terminal\b", lowered):
            changed.extend(permissions.set_named_policy("shell", "ask"))
        if re.search(r"\bdesktop|mouse|keyboard|click|type\b", lowered):
            changed.extend(permissions.set_named_policy("desktop", "ask"))
        if changed:
            return _permission_change_reply(changed, "ask")

    match = re.fullmatch(r"(?:set\s+)?(?:permission\s+)?(?:for\s+)?(.+?)\s+(?:to\s+)?(allow|ask|block)", lowered)
    if not match:
        match = re.fullmatch(r"(allow|ask|block)\s+(?:before\s+)?(.+)", lowered)
        if match:
            mode = match.group(1)
            name = match.group(2)
        else:
            mode = ""
            name = ""
    else:
        name = match.group(1)
        mode = match.group(2)
    if mode and name:
        changed = permissions.set_named_policy(name.strip(), mode.strip())
        if changed:
            return _permission_change_reply(changed, mode)

    return ""


def _permission_change_reply(changed: list[dict[str, Any]], mode: str) -> str:
    labels = ", ".join(rule["label"] for rule in changed[:4])
    suffix = " and more" if len(changed) > 4 else ""
    return f"Permission updated: {labels}{suffix} set to {mode}."


def _direct_self_update(text: str) -> str:
    cleaned = _strip_leading_assistant_name(text).strip(" ,.!?:;")
    lowered = cleaned.lower()
    if not lowered:
        return ""

    if re.fullmatch(
        r"(?:what(?:'s| is)|explain|describe)\s+(?:your|friday'?s)\s+brain(?:\s+like)?",
        lowered,
    ):
        return _voice_tool_result(self_update_tool.execute({"action": "brain"}))

    if re.fullmatch(r"(?:list|show)\s+(?:the\s+)?self[- ]updates?", lowered):
        return _voice_tool_result(_self_update({"action": "list", "limit": 8}))

    match = re.fullmatch(r"(?:show|open|get)\s+(?:self[- ]update\s+)?#?(\d+)", cleaned, re.IGNORECASE)
    if match:
        return _voice_tool_result(_self_update({"action": "get", "update_id": match.group(1)}))

    match = re.fullmatch(r"(?:cancel|stop)\s+(?:self[- ]update\s+)?#?(\d+)", cleaned, re.IGNORECASE)
    if match:
        return _voice_tool_result(_self_update({"action": "cancel", "update_id": match.group(1)}))

    match = re.fullmatch(r"i authorize applying self[- ]update\s+#?(\d+)", lowered)
    if match:
        update_id = match.group(1)
        return _voice_tool_result(
            _self_update(
                {
                    "action": "apply",
                    "update_id": update_id,
                    "confirmation": cleaned,
                    "_permission_confirmed": True,
                }
            )
        )

    match = re.fullmatch(r"i authorize self[- ]update\s+#?(\d+)", lowered)
    if match:
        update_id = match.group(1)
        return _voice_tool_result(
            _self_update(
                {
                    "action": "approve",
                    "update_id": update_id,
                    "confirmation": cleaned,
                    "_permission_confirmed": True,
                }
            )
        )

    proposal_patterns = (
        r"(?:create|propose|queue|plan)\s+(?:a\s+)?self[- ]update(?:\s+to)?\s+(.+)",
        r"(?:update|modify|improve)\s+(?:your|friday'?s)\s+(?:own\s+)?(?:codebase|code|source code)(?:\s+to)?\s+(.+)",
        r"(?:make|let)\s+(?:yourself|friday)\s+(.+?)\s+(?:by|with)\s+(?:a\s+)?self[- ]update",
    )
    for pattern in proposal_patterns:
        match = re.fullmatch(pattern, cleaned, re.IGNORECASE)
        if match:
            request = match.group(1).strip(" .,!?:;")
            if request:
                return _voice_tool_result(_self_update({"action": "propose", "request": request}))

    if re.fullmatch(r"(?:can you|are you able to)\s+(?:update|modify|improve)\s+(?:your|friday'?s)\s+(?:own\s+)?(?:codebase|code|source code)", lowered):
        return "Yes. I can propose guarded self-updates, stage exact code changes, apply them after explicit approval, run tests, and roll back on failure."

    return ""


def _direct_cognition(text: str) -> str:
    cleaned = _strip_leading_assistant_name(text).strip(" ,.!?:;")
    lowered = cleaned.lower()
    if not lowered:
        return ""

    if re.fullmatch(r"(?:what(?:'s| is)|tell me)\s+(?:going on|happening)(?:\s+right now)?", lowered) or re.fullmatch(
        r"(?:what(?:'s| is)\s+)?(?:your\s+)?(?:world model|current context)",
        lowered,
    ):
        context = world_model.current_context()
        return _voice_tool_result(context.get("summary") or "I do not have a current world snapshot yet.")

    if re.fullmatch(r"(?:what(?:'s| is)\s+)?(?:your\s+)?(?:current\s+)?(?:focus|focused on)", lowered):
        regulation = goal_regulation.current_regulation()
        goals = regulation.get("active_goals") or []
        state = regulation.get("state") or {}
        if goals:
            top = goals[0]
            return f"I am {state.get('state', 'calm')} and focused on goal #{top['id']}: {top['title']}."
        return f"I am {state.get('state', 'calm')} with no active goal."

    if re.fullmatch(r"(?:what(?:'s| is)\s+)?(?:your\s+)?(?:current\s+)?goals?", lowered):
        goals = goal_regulation.active_goals(limit=5)
        if not goals:
            return "I do not have active goals right now."
        return "Active goals: " + "; ".join(f"#{goal['id']} {goal['title']}" for goal in goals[:5]) + "."

    match = re.fullmatch(r"(?:create|add|set)\s+(?:a\s+)?goal\s+(.+)", cleaned, re.IGNORECASE)
    if match:
        title = match.group(1).strip(" .,!?:;")
        goal_id = goal_regulation.create_goal(title, source="user")
        _record_autobiography("goal", f"Goal {goal_id} created", title, importance=0.7)
        return f"Goal {goal_id} created: {title}."

    if re.fullmatch(r"(?:reflect|reflect on that|run reflection|self reflect)", lowered):
        result = self_reflection.run_reflection(trigger="user")
        return _voice_tool_result(result.get("summary") or "Reflection complete.")

    if re.fullmatch(r"(?:why did you do that|why did that happen)", lowered):
        context = self_reflection.reflection_context(limit=3)
        return _voice_tool_result(context or "I do not have a recent reflection finding for that yet.")

    if re.fullmatch(r"(?:what did you learn recently|what have you learned recently|show learning)", lowered):
        items = long_term_learning.recent_items(limit=5)
        if not items:
            return "I have not stored durable learning items yet."
        return "Recent learning: " + "; ".join(item["content"][:80] for item in items[:3]) + "."

    if re.fullmatch(r"(?:review learning|run learning review)", lowered):
        result = long_term_learning.run_reviews(limit=5)
        return f"Learning review complete: {result.get('reviewed', 0)} item reviewed."

    if re.fullmatch(r"(?:attention status|show attention profile|how strict are you listening)", lowered):
        profile = adaptive_attention.current_profile()
        return (
            f"Attention strictness is {profile['name_strictness']:.2f}; "
            f"false positives {profile['false_positive_rate']:.2f}, false negatives {profile['false_negative_rate']:.2f}."
        )

    if re.fullmatch(r"(?:be stricter about listening|listen stricter|ignore background speech)", lowered):
        for _ in range(3):
            adaptive_attention.record_attention_event("manual stricter request", "ignored", "user requested stricter listening", accepted=False)
        profile = adaptive_attention.update_profile()
        return f"I will listen more strictly. Attention strictness is now {profile['name_strictness']:.2f}."

    if re.fullmatch(r"(?:listen more carefully for friday|be less strict about friday|you are missing your name)", lowered):
        adaptive_attention.record_user_correction("Friday", "missed wake name")
        profile = adaptive_attention.current_profile()
        return f"I will be more forgiving around my name. Attention strictness is now {profile['name_strictness']:.2f}."

    return ""


def _direct_agent_team(text: str) -> str:
    cleaned = _strip_leading_assistant_name(text).strip(" ,.!?:;")
    lowered = cleaned.lower()
    if not lowered:
        return ""

    if re.fullmatch(r"(?:team|agent|agents|background agents)\s+(?:status|state)", lowered):
        return _voice_tool_result(agent_team.execute({"action": "status"}))
    match = re.fullmatch(
        r"(?:(?:do|does)\s+(?:you|friday|the\s+team|agents?)\s+have\s+)?(?:any\s+)?(active|pending|blocked|done|failed|cancelled)\s+tasks?",
        lowered,
    )
    if match:
        return _voice_tool_result(agent_team.execute({"action": "list_tasks", "status": match.group(1), "limit": 8}))
    match = re.fullmatch(
        r"(?:are\s+there\s+)?(?:any\s+)?tasks?\s+(?:that\s+are\s+)?(active|pending|blocked|done|failed|cancelled)",
        lowered,
    )
    if match:
        return _voice_tool_result(agent_team.execute({"action": "list_tasks", "status": match.group(1), "limit": 8}))
    match = re.fullmatch(
        r"(?:do|does)\s+(?:you|friday|the\s+team|agents?)\s+have\s+(?:any\s+)?tasks?\s+(active|pending|blocked|done|failed|cancelled)",
        lowered,
    )
    if match:
        return _voice_tool_result(agent_team.execute({"action": "list_tasks", "status": match.group(1), "limit": 8}))
    match = re.fullmatch(r"(?:what\s+)?tasks?\s+(?:are\s+)?(?:currently\s+)?(active|pending|blocked|done|failed|cancelled)", lowered)
    if match:
        return _voice_tool_result(agent_team.execute({"action": "list_tasks", "status": match.group(1), "limit": 8}))
    match = re.fullmatch(r"(?:list|show)\s+(active|pending|blocked|done|failed|cancelled)\s+tasks?", lowered)
    if match:
        return _voice_tool_result(agent_team.execute({"action": "list_tasks", "status": match.group(1), "limit": 8}))
    if re.fullmatch(r"(?:what(?:'s| is) )?(?:the )?(?:team|agents)(?: working on| doing)\??", lowered):
        listing = agent_team.execute({"action": "list_tasks", "status": "active", "limit": 5})
        if listing == "No tasks found.":
            listing = agent_team.execute({"action": "list_tasks", "status": "pending", "limit": 5})
        return _voice_tool_result(listing if listing != "No tasks found." else agent_team.execute({"action": "status"}))
    if re.fullmatch(r"(?:what\s+)?(?:agent\s+)?questions?(?:\s+are\s+(?:open|waiting|pending|active))?", lowered):
        return _voice_tool_result(agent_team.execute({"action": "list_questions", "limit": 8}))
    if re.fullmatch(r"(?:what\s+are\s+)?agents\s+asking(?:\s+each\s+other)?\??", lowered):
        return _voice_tool_result(agent_team.execute({"action": "list_questions", "limit": 8}))
    if re.fullmatch(r"(?:show|open|list)\s+(?:the\s+)?(?:agent\s+)?(?:offices|office floor|virtual offices)", lowered):
        return _voice_tool_result(agent_team.execute({"action": "offices", "limit": 6}))
    match = re.fullmatch(r"(?:what(?:'s| is)|show|open)\s+(?:the\s+)?(.+?)\s+(?:office|agent office|doing|working on)", cleaned, re.IGNORECASE)
    if match:
        agent_id = match.group(1).strip(" .,!?:;")
        if agent_id.lower() not in {"team", "agents", "agent"}:
            return _voice_tool_result(agent_team.execute({"action": "office", "agent_id": agent_id}))
    if re.fullmatch(r"(?:list|show)\s+(?:the\s+)?(?:agents|agent roster|team roster)", lowered):
        return _voice_tool_result(agent_team.execute({"action": "roster"}))
    if re.fullmatch(r"start\s+(?:the\s+)?(?:agents|agent workers|background agents)", lowered):
        return _voice_tool_result(agent_team.execute({"action": "start_workers"}))
    if re.fullmatch(r"stop\s+(?:the\s+)?(?:agents|agent workers|background agents)", lowered):
        return _voice_tool_result(agent_team.execute({"action": "stop_workers"}))
    if re.fullmatch(r"(?:run|process)\s+(?:one\s+)?(?:task|queued task|next task)", lowered):
        return _voice_tool_result(agent_team.execute({"action": "run_one"}))

    match = re.fullmatch(r"(?:show|open|get)\s+(?:task\s+)?#?(\d+)", cleaned, re.IGNORECASE)
    if match:
        return _voice_tool_result(agent_team.execute({"action": "get_task", "task_id": match.group(1)}))

    match = re.fullmatch(r"(?:cancel|stop)\s+(?:task\s+)?#?(\d+)", cleaned, re.IGNORECASE)
    if match:
        return _voice_tool_result(agent_team.execute({"action": "cancel_task", "task_id": match.group(1)}))

    match = re.fullmatch(r"(?:assign|reassign|give)\s+(?:task\s+)?#?(\d+)\s+to\s+(?:the\s+)?(.+?)(?:\s+agent)?", cleaned, re.IGNORECASE)
    if match:
        return _voice_tool_result(
            agent_team.execute({"action": "reassign_task", "task_id": match.group(1), "agent_id": match.group(2), "status": "pending"})
        )

    match = re.fullmatch(r"(?:create|queue|add)\s+(?:a\s+)?task\s+(.+)", cleaned, re.IGNORECASE)
    if match:
        title = match.group(1).strip(" .,!?:;")
        return _voice_tool_result(agent_team.execute({"action": "create_task", "title": title}))

    match = re.fullmatch(r"(?:assign|give)\s+(.+?)\s+to\s+(?:the\s+)?(.+?)(?:\s+agent)?", cleaned, re.IGNORECASE)
    if match:
        title = match.group(1).strip(" .,!?:;")
        agent_id = match.group(2).strip(" .,!?:;")
        return _voice_tool_result(agent_team.execute({"action": "create_task", "title": title, "agent_id": agent_id}))

    match = re.fullmatch(r"ask\s+(?:the\s+)?(.+?)\s+(?:agent\s+)?to\s+(.+)", cleaned, re.IGNORECASE)
    if match:
        agent_id = match.group(1).strip(" .,!?:;")
        title = match.group(2).strip(" .,!?:;")
        return _voice_tool_result(agent_team.execute({"action": "create_task", "title": title, "agent_id": agent_id}))

    match = re.fullmatch(r"(?:have|tell)\s+(?:the\s+)?team\s+(?:to\s+)?(.+)", cleaned, re.IGNORECASE)
    if match:
        title = match.group(1).strip(" .,!?:;")
        return _voice_tool_result(agent_team.execute({"action": "create_task", "title": title}))

    return ""


def _direct_operational_labs(text: str) -> str:
    cleaned = _strip_leading_assistant_name(text).strip(" ,.!?:;")
    lowered = cleaned.lower()
    if not lowered:
        return ""
    if re.fullmatch(r"(?:approval inbox|decision inbox|decisions waiting|what decisions are waiting|what needs my approval|what needs my decision)", lowered):
        return approval_inbox.voice_summary()
    if re.fullmatch(r"(?:show|list|open)\s+(?:the\s+)?(?:silent\s+)?(?:thought\s+bus|agent\s+thoughts|silent\s+thoughts)", lowered) or re.fullmatch(
        r"(?:what(?:'s| is)\s+)?(?:on\s+)?(?:the\s+)?(?:silent\s+)?(?:thought\s+bus|agent\s+thoughts|silent\s+thoughts)", lowered
    ):
        return _voice_tool_result(agent_team.execute({"action": "thoughts"}))
    if re.fullmatch(r"(?:show|list|open)\s+(?:the\s+)?(?:agent\s+)?blackboard", lowered) or re.fullmatch(
        r"(?:what(?:'s| is)\s+)?(?:on\s+)?(?:the\s+)?(?:agent\s+)?blackboard", lowered
    ):
        summary = agent_blackboard.summary(limit=5)
        open_count = int(summary.get("open_count") or 0)
        blockers = summary.get("blockers") or []
        questions = summary.get("questions") or []
        if not open_count:
            return "The agent blackboard has no open items."
        parts = []
        if questions:
            parts.append(f"{len(questions)} question{'s' if len(questions) != 1 else ''}")
        if blockers:
            parts.append(f"{len(blockers)} blocker{'s' if len(blockers) != 1 else ''}")
        return f"The blackboard has {open_count} open item{'s' if open_count != 1 else ''}: {', '.join(parts) or 'findings and progress notes'}."
    if re.fullmatch(r"(?:evaluation lab|show evaluation lab|reliability report|show reliability report|what is failing)", lowered):
        payload = evaluation_lab.summary(limit=5)
        counts = payload.get("counts") or {}
        return (
            f"Evaluation lab: {counts.get('stt_mistake', 0)} STT mistakes, "
            f"{counts.get('slow_response', 0)} slow responses, {counts.get('failed_tool', 0)} failed tools, "
            f"{counts.get('unsupported_claim', 0)} unsupported claims."
        )
    if re.fullmatch(r"(?:voice reliability|voice reliability lab|stt mistakes|transcription mistakes)", lowered):
        payload = voice_reliability.summary(limit=5)
        mistakes = payload.get("recent_mistakes") or []
        aliases = payload.get("learned_aliases") or []
        return f"Voice lab has {len(mistakes)} recent mistake samples. Learned aliases: {', '.join(aliases[:5]) or 'none yet'}."
    return ""


def _direct_app_integrations(text: str) -> str:
    cleaned = _strip_leading_assistant_name(text).strip(" ,.!?:;")
    lowered = cleaned.lower()
    if not lowered:
        return ""

    match = re.fullmatch(r"(?:open|launch|start)\s+(?:my\s+|the\s+)?(calendar|google calendar|docs|google docs|sheets|google sheets|whatsapp|whatsapp web|discord|gmail)", lowered)
    if match:
        target = match.group(1).replace("google ", "").replace(" web", "")
        return _voice_tool_result(_apps({"action": "open_app", "target": target}))

    if re.fullmatch(r"(?:google workspace status|google oauth status|is google connected)", lowered):
        return _voice_tool_result(_apps({"action": "google_status"}))
    if re.fullmatch(r"(?:list|show|read)\s+(?:my\s+)?(?:recent\s+)?(?:gmail|emails|email messages)", lowered):
        return _voice_tool_result(_apps({"action": "list_gmail_messages", "limit": 5}))

    if re.fullmatch(r"(?:list|show|search)\s+(?:my\s+)?contacts", lowered):
        return _voice_tool_result(_apps({"action": "search_contacts"}))
    match = re.fullmatch(r"(?:search|find|look up)\s+(?:contact|contacts)\s+(.+)", cleaned, re.IGNORECASE)
    if match:
        return _voice_tool_result(_apps({"action": "search_contacts", "query": match.group(1).strip()}))
    match = re.fullmatch(r"(?:add|save|create)\s+(?:a\s+)?contact\s+(.+)", cleaned, re.IGNORECASE)
    if match:
        return _voice_tool_result(_apps({"action": "create_contact"} | _contact_inputs(match.group(1))))

    match = re.fullmatch(r"(?:remind me to|add reminder to|create reminder to|set reminder to)\s+(.+)", cleaned, re.IGNORECASE)
    if match:
        title, when = _split_when(match.group(1))
        return _voice_tool_result(_apps({"action": "create_reminder", "title": title, "due_at": when}))
    match = re.fullmatch(r"(?:remind me|add reminder|create reminder|set reminder)\s+(.+)", cleaned, re.IGNORECASE)
    if match:
        title, when = _split_when(match.group(1))
        return _voice_tool_result(_apps({"action": "create_reminder", "title": title, "due_at": when}))
    if re.fullmatch(r"(?:list|show|what are)\s+(?:my\s+)?reminders", lowered):
        return _voice_tool_result(_apps({"action": "list_reminders"}))
    match = re.fullmatch(r"(?:complete|finish|done)\s+reminder\s+#?(\d+)", lowered)
    if match:
        return _voice_tool_result(_apps({"action": "complete_reminder", "reminder_id": match.group(1)}))

    match = re.fullmatch(r"(?:add|create|schedule)\s+(?:a\s+)?(?:calendar\s+)?event\s+(.+)", cleaned, re.IGNORECASE)
    if match:
        title, when = _split_when(match.group(1))
        return _voice_tool_result(_apps({"action": "create_calendar_event", "title": title, "start_at": when}))
    if re.fullmatch(r"(?:list|show)\s+(?:my\s+)?(?:calendar\s+)?events", lowered):
        return _voice_tool_result(_apps({"action": "list_calendar_events"}))

    match = re.fullmatch(r"(?:create|make|draft)\s+(?:a\s+)?(?:doc|document)(?:\s+(?:called|named|titled))?\s+(.+)", cleaned, re.IGNORECASE)
    if match:
        return _voice_tool_result(_apps({"action": "create_doc", "title": match.group(1).strip()}))
    match = re.fullmatch(r"(?:create|make)\s+(?:a\s+)?(?:sheet|spreadsheet)(?:\s+(?:called|named|titled))?\s+(.+)", cleaned, re.IGNORECASE)
    if match:
        return _voice_tool_result(_apps({"action": "create_sheet", "title": match.group(1).strip()}))

    if re.fullmatch(r"(?:index|scan)\s+(?:my\s+)?(?:workspace|project|current folder|current directory)", lowered):
        return _voice_tool_result(_apps({"action": "index_workspace"}))
    if re.fullmatch(r"(?:read|understand|analyze)\s+(?:my\s+)?(?:whole\s+)?(?:workspace|project)\s+(?:intelligently|smartly)?", lowered):
        indexed = _apps({"action": "index_workspace"})
        overview = _apps({"action": "workspace_overview"})
        return _voice_tool_result(f"{indexed} {overview}")
    if re.fullmatch(r"(?:workspace|project)\s+(?:overview|summary)", lowered):
        return _voice_tool_result(_apps({"action": "workspace_overview"}))
    match = re.fullmatch(r"(?:search|find)\s+(?:my\s+)?(?:workspace|project)\s+(?:for\s+)?(.+)", cleaned, re.IGNORECASE)
    if match:
        return _voice_tool_result(_apps({"action": "search_workspace", "query": match.group(1).strip()}))

    return ""


def _direct_image_generation(text: str) -> str:
    cleaned = _strip_leading_assistant_name(text).strip(" ,.!?:;")
    lowered = cleaned.lower()
    if not lowered:
        return ""
    if re.search(r"\b(?:open|launch|use)\s+(?:adobe\s+)?illustrator\b|\bin\s+(?:adobe\s+)?illustrator\b", lowered):
        return ""
    if re.fullmatch(r"(?:image generation|image generator|text to image)(?:\s+status)?", lowered):
        return _voice_tool_result(image_generation_tool.execute({"action": "status"}))
    if re.fullmatch(r"(?:list|show)\s+(?:generated\s+)?images?", lowered):
        return _voice_tool_result(image_generation_tool.execute({"action": "list", "limit": 8}))
    patterns = (
        r"(?:generate|create|make|draw|render|design)\s+(?:an?\s+)?(?:image|picture|photo|art|illustration)\s+(?:i\s+can\s+use\s+)?(?:as|for)\s+(.+)",
        r"(?:generate|create|make|draw|render|design)\s+(?:an?\s+)?(?:image|picture|photo|art|illustration)\s+(?:of|showing|for|about)\s+(.+)",
        r"(?:generate|create|make|draw|render|design)\s+((?:an?\s+)?(?:logo|brand\s+mark|logomark)(?:\s+(?:of|showing|for|about))?\s+.+)",
        r"(?:generate|create|make|draw|render|design)\s+(.+?)\s+(?:image|picture|photo|art|illustration)",
        r"(?:generate|create|make|draw|render|design)\s+((?:.+?)\s+(?:logo|brand\s+mark|logomark))",
        r"(?:text[- ]?to[- ]?image|image prompt)\s+(.+)",
    )
    for pattern in patterns:
        match = re.fullmatch(pattern, cleaned, re.IGNORECASE)
        if match:
            prompt = match.group(1).strip(" .,!?:;")
            if prompt:
                return _voice_tool_result(image_generation_tool.execute({"action": "generate", "prompt": prompt}))
    return ""


def _contact_inputs(raw: str) -> dict[str, str]:
    text = raw.strip(" .,!?:;")
    email_match = re.search(r"[\w.+-]+@[\w.-]+\.[a-zA-Z]{2,}", text)
    phone_match = re.search(r"(?:phone|number)?\s*(\+?\d[\d\s().-]{5,}\d)", text, re.IGNORECASE)
    email = email_match.group(0) if email_match else ""
    phone = phone_match.group(1).strip() if phone_match else ""
    name = text
    if email:
        name = name.replace(email, "")
    if phone_match:
        name = name.replace(phone_match.group(0), "")
    name = re.sub(r"\b(?:email|phone|number|with|and|is)\b", " ", name, flags=re.IGNORECASE)
    return {"name": " ".join(name.split()).strip() or text, "email": email, "phone": phone}


def _split_when(raw: str) -> tuple[str, str]:
    text = raw.strip(" .,!?:;")
    patterns = [
        r"\s+(tomorrow|today|tonight)$",
        r"\s+(on\s+\w+(?:\s+\d{1,2})?)$",
        r"\s+(at\s+\d{1,2}(?::\d{2})?\s*(?:am|pm)?)$",
        r"\s+(by\s+.+)$",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            when = match.group(1).strip()
            title = text[: match.start()].strip(" .,!?:;") or text
            return title, when
    return text, ""


def _direct_phone_bridge(text: str) -> str:
    cleaned = _strip_leading_assistant_name(text).strip(" ,.!?:;")
    lowered = cleaned.lower()
    if not lowered:
        return ""

    if re.fullmatch(r"(?:phone status|phone bridge status|android status|is my phone connected|is my android connected)", lowered):
        return _voice_tool_result(_phone({"action": "status"}))
    if re.fullmatch(r"(?:list|show)\s+(?:my\s+)?(?:phone devices|android devices)", lowered):
        return _voice_tool_result(_phone({"action": "list_devices"}))
    if re.fullmatch(r"(?:what(?:'s| is)\s+)?(?:my\s+)?phone battery(?: level)?|(?:battery|battery level) of my phone", lowered):
        return _voice_tool_result(_phone({"action": "battery"}))
    if re.fullmatch(r"(?:ring|find|call)\s+(?:my\s+)?phone", lowered) or re.fullmatch(
        r"(?:call me|ring me|get my attention)(?:\s+on\s+(?:my\s+)?phone)?", lowered
    ):
        return _voice_tool_result(_phone({"action": "ring", "message": "Friday is trying to reach you."}))

    match = re.fullmatch(r"(?:send|notify)\s+(?:my\s+)?phone\s+(?:that\s+)?(.+)", cleaned, re.IGNORECASE)
    if match:
        return _voice_tool_result(_phone({"action": "notify", "title": "Friday", "message": match.group(1).strip()}))
    match = re.fullmatch(r"(?:send|push)\s+(.+?)\s+to\s+(?:my\s+)?phone", cleaned, re.IGNORECASE)
    if match:
        payload = match.group(1).strip(" .,!?:;")
        return _voice_tool_result(_phone({"action": "notify", "title": "Friday", "message": payload}))

    match = re.fullmatch(r"(?:open|send|push)\s+(.+?)\s+on\s+(?:my\s+)?phone", cleaned, re.IGNORECASE)
    if match:
        target = match.group(1).strip(" .,!?:;")
        if _looks_like_url(target):
            return _voice_tool_result(_phone({"action": "open_url", "url": target}))

    match = re.fullmatch(r"(?:open|send|push)\s+(?:this\s+)?(?:url|link)\s+(.+?)\s+(?:on|to)\s+(?:my\s+)?phone", cleaned, re.IGNORECASE)
    if match:
        return _voice_tool_result(_phone({"action": "open_url", "url": match.group(1).strip()}))

    match = re.fullmatch(r"(?:dial|call)\s+(.+?)\s+(?:on|from)\s+(?:my\s+)?phone", cleaned, re.IGNORECASE)
    if match:
        target = match.group(1).strip(" .,!?:;")
        phone_match = re.search(r"\+?\d[\d\s().-]{5,}\d", target)
        if phone_match:
            return _voice_tool_result(_phone({"action": "dial", "number": phone_match.group(0)}))
        return _voice_tool_result(_phone({"action": "call_contact", "name": target}))

    match = re.fullmatch(r"(?:draft|write|compose)\s+(?:an?\s+)?sms\s+(?:to\s+)?(.+?)(?:\s+saying\s+(.+))?", cleaned, re.IGNORECASE)
    if match:
        target = match.group(1).strip(" .,!?:;")
        body = (match.group(2) or "").strip()
        phone_match = re.search(r"\+?\d[\d\s().-]{5,}\d", target)
        if phone_match:
            return _voice_tool_result(_phone({"action": "sms_draft", "number": phone_match.group(0), "message": body}))
    match = re.fullmatch(r"(?:copy|send)\s+(.+?)\s+to\s+(?:my\s+)?phone clipboard", cleaned, re.IGNORECASE)
    if match:
        return _voice_tool_result(_phone({"action": "set_clipboard", "text": match.group(1).strip()}))
    if re.fullmatch(r"(?:import|pull)\s+(?:my\s+)?(?:phone\s+)?photos", lowered):
        return _voice_tool_result(_phone({"action": "import_photos"}))

    return ""


def _direct_capability_center(text: str) -> str:
    cleaned = _strip_leading_assistant_name(text).strip(" ,.!?:;")
    lowered = cleaned.lower()
    if not lowered:
        return ""
    if re.fullmatch(r"(?:capability center|capabilities overview|power center)", lowered):
        return _voice_tool_result(_capability({"action": "overview"}))
    if re.fullmatch(r"(?:daily brief|give me my daily brief|brief me)", lowered):
        return _voice_tool_result(_capability({"action": "daily_brief"}))
    if re.fullmatch(r"(?:what should i do next|next action|what next)", lowered):
        return _voice_tool_result(_capability({"action": "next_action"}))
    if re.fullmatch(r"(?:plan my day|make a day plan|calendar planning)", lowered):
        return _voice_tool_result(_capability({"action": "plan_day"}))
    if re.fullmatch(r"(?:home status|home device status|device status)", lowered):
        return _voice_tool_result(_capability({"action": "home_status"}))
    match = re.fullmatch(r"(?:turn|switch)\s+(on|off)\s+(.+)", cleaned, re.IGNORECASE)
    if match:
        return _voice_tool_result(_capability({"action": "control_smart_device", "target": match.group(2).strip(), "device_action": match.group(1).lower()}))
    match = re.fullmatch(r"(?:toggle|control)\s+(?:smart\s+)?(?:device\s+)?(.+?)(?:\s+to\s+(.+))?", cleaned, re.IGNORECASE)
    if match and any(word in lowered for word in {"smart", "device", "lamp", "bulb", "plug", "light"}):
        return _voice_tool_result(_capability({"action": "control_smart_device", "target": match.group(1).strip(), "device_action": (match.group(2) or "toggle").strip().lower()}))
    if re.fullmatch(r"(?:router status|router page|is my router online)", lowered):
        return _voice_tool_result(_capability({"action": "router_status"}))
    if re.fullmatch(r"(?:show|list)\s+(?:local\s+)?network devices", lowered):
        return _voice_tool_result(_capability({"action": "local_network", "limit": 20}))
    if re.fullmatch(r"(?:connection quality|internet quality|network quality)", lowered):
        return _voice_tool_result(_capability({"action": "connection_quality"}))
    if re.fullmatch(r"(?:project map|map this project|workspace map)", lowered):
        return _voice_tool_result(_capability({"action": "workspace_map"}))
    if re.fullmatch(r"(?:dependency health|check dependencies|dependency audit)", lowered):
        return _voice_tool_result(_capability({"action": "dependency_health"}))
    if re.fullmatch(r"(?:generate docs|auto docs|create project docs)", lowered):
        return _voice_tool_result(_capability({"action": "auto_docs"}))
    if re.fullmatch(r"(?:maintenance report|pc maintenance|computer maintenance)", lowered):
        return _voice_tool_result(_capability({"action": "maintenance_report"}))
    if re.fullmatch(r"(?:security overview|security dashboard|security lab)", lowered):
        return _voice_tool_result(_capability({"action": "security_overview"}))
    match = re.fullmatch(r"(?:hack|pentest|penetration test)\s+(.+)", cleaned, re.IGNORECASE)
    if match:
        target = match.group(1).strip()
        return (
            "I can help with defensive testing only after scope is verified. "
            f"Create a security scope for {target}, verify ownership, then I can run low-impact checks and generate a hardening plan."
        )
    match = re.fullmatch(r"(?:create|add)\s+(?:a\s+)?security scope\s+(?:for\s+)?(.+)", cleaned, re.IGNORECASE)
    if match:
        return _voice_tool_result(_capability({"action": "create_security_scope", "target": match.group(1).strip()}))
    match = re.fullmatch(r"(?:verify)\s+(?:security\s+)?scope\s+(\d+)(?:\s+at\s+(.+))?", cleaned, re.IGNORECASE)
    if match:
        return _voice_tool_result(_capability({"action": "verify_security_scope", "scope_id": match.group(1), "proof_url": (match.group(2) or "").strip()}))
    if re.fullmatch(r"(?:list|show)\s+security scopes", lowered):
        return _voice_tool_result(_capability({"action": "list_security_scopes"}))
    match = re.fullmatch(r"(?:scan|check)\s+(?:open\s+)?ports\s+(?:on\s+)?(.+)", cleaned, re.IGNORECASE)
    if match:
        return _voice_tool_result(_capability({"action": "open_port_scan", "target": match.group(1).strip()}))
    match = re.fullmatch(r"(?:check|scan)\s+(?:security\s+)?headers\s+(?:on\s+)?(.+)", cleaned, re.IGNORECASE)
    if match:
        return _voice_tool_result(_capability({"action": "web_security_check", "target": match.group(1).strip()}))
    if re.fullmatch(r"(?:scan|check)\s+(?:project\s+)?secrets", lowered):
        return _voice_tool_result(_capability({"action": "secret_scan"}))
    match = re.fullmatch(r"(?:hardening plan|harden)\s+(?:for\s+)?(.+)?", cleaned, re.IGNORECASE)
    if match:
        return _voice_tool_result(_capability({"action": "hardening_plan", "target": (match.group(1) or "").strip()}))
    if re.fullmatch(r"(?:security report|generate security report)", lowered):
        return _voice_tool_result(_capability({"action": "security_report"}))
    if re.fullmatch(r"(?:list|show)\s+automation recipes", lowered):
        return _voice_tool_result(_capability({"action": "list_recipes"}))
    return ""


def _direct_power_center(text: str) -> str:
    cleaned = _strip_leading_assistant_name(text).strip(" ,.!?:;")
    lowered = cleaned.lower()
    if not lowered:
        return ""
    if re.fullmatch(r"(?:install|enable|set up)\s+(?:the\s+)?(?:built[- ]in\s+)?(?:skill library|skills|plugin system)", lowered):
        return _voice_tool_result(_power({"action": "install_builtin_skills", "key": "all"}))
    if re.fullmatch(r"(?:list|show)\s+(?:your\s+)?(?:skills|plugins)", lowered):
        return _voice_tool_result(_power({"action": "list_skills"}))
    if re.fullmatch(r"(?:guardian scan|run guardian|check important signals|what needs attention)", lowered):
        return _voice_tool_result(_power({"action": "guardian_scan"}))
    if re.fullmatch(r"(?:guardian status|proactive guardian status)", lowered):
        return _voice_tool_result(_power({"action": "guardian_status"}))
    if re.fullmatch(r"(?:nervous system|event system|awake status|what events are happening)", lowered):
        return _voice_tool_result(_power({"action": "event_status"}))
    if re.fullmatch(r"(?:run nervous system|check events|event scan)", lowered):
        return _voice_tool_result(_power({"action": "event_scan"}))
    if re.fullmatch(r"(?:morning brief|daily companion|daily companion brief|start my day)", lowered):
        return _voice_tool_result(_power({"action": "daily_companion_brief"}))
    if re.fullmatch(r"(?:check in|daily check in|companion check in)", lowered):
        return _voice_tool_result(_power({"action": "daily_companion_checkin"}))
    if re.fullmatch(r"(?:notifications|notification center|what notifications do i have|any notifications)", lowered):
        return _voice_tool_result(_power({"action": "notifications"}))
    if re.fullmatch(r"(?:skill marketplace|show skill marketplace|marketplace skills)", lowered):
        return _voice_tool_result(_power({"action": "skill_marketplace"}))
    match = re.fullmatch(r"(?:install|enable)\s+(?:marketplace\s+)?skill\s+(.+)", cleaned, re.IGNORECASE)
    if match:
        return _voice_tool_result(_power({"action": "skill_marketplace_install", "key": match.group(1).strip()}))
    if re.fullmatch(r"(?:finance summary|budget summary|personal finance)", lowered):
        return _voice_tool_result(_power({"action": "finance_summary"}))
    match = re.fullmatch(r"(?:can i afford)\s+([0-9,.]+)(?:\s+(.+))?", cleaned, re.IGNORECASE)
    if match:
        return _voice_tool_result(_power({"action": "can_afford", "amount": match.group(1), "category": (match.group(2) or "general").strip()}))
    match = re.fullmatch(r"(?:add expense|record expense)\s+([0-9,.]+)(?:\s+(.+))?", cleaned, re.IGNORECASE)
    if match:
        return _voice_tool_result(_power({"action": "add_expense", "amount": match.group(1), "category": (match.group(2) or "general").strip()}))
    if re.fullmatch(r"(?:private memory summary|embedding memory summary)", lowered):
        return _voice_tool_result(_power({"action": "private_memory_summary"}))
    match = re.fullmatch(r"(?:search private memory|private memory search)\s+(.+)", cleaned, re.IGNORECASE)
    if match:
        return _voice_tool_result(_power({"action": "private_memory_search", "query": match.group(1).strip()}))
    if re.fullmatch(r"(?:android companion status|companion app status)", lowered):
        return _voice_tool_result(_power({"action": "android_companion_status"}))
    if re.fullmatch(r"(?:android app devices|phone app devices|companion devices)", lowered):
        return _voice_tool_result(_power({"action": "android_app_devices"}))
    if re.fullmatch(r"(?:project watchdog|watchdog status)", lowered):
        return _voice_tool_result(_power({"action": "project_watchdog_status"}))
    if re.fullmatch(r"(?:run project watchdog|check project watchdog)", lowered):
        return _voice_tool_result(_power({"action": "project_watchdog_run"}))
    if re.fullmatch(r"(?:codebase standards|coding standards|programmer laws|programmers law|programmer's laws|what are your code standards|what are your codebase standards)", lowered):
        return _voice_tool_result(_power({"action": "codebase_standards_rules"}))
    if re.search(r"\b(?:do you know|does friday know|know how)\b", lowered) and re.search(r"\b(?:programmer laws|coding standards|codebase standards|organize codebase|organise codebase)\b", lowered):
        return _voice_tool_result(_power({"action": "codebase_standards_rules"}))
    match = re.fullmatch(r"(?:check|scan|run)\s+(?:the\s+)?(?:codebase standards|coding standards|programmer laws|code quality|code hygiene)(?:\s+(.*))?", cleaned, re.IGNORECASE)
    if match:
        return _voice_tool_result(_power({"action": "codebase_standards", "focus": (match.group(1) or "").strip()}))
    match = re.fullmatch(r"(?:simulate|dry run|sandbox)\s+(.+)", cleaned, re.IGNORECASE)
    if match:
        return _voice_tool_result(_power({"action": "simulate_action", "instruction": match.group(1).strip()}))
    if re.fullmatch(r"(?:privacy vault|privacy vault summary)", lowered):
        return _voice_tool_result(_power({"action": "privacy_vault_summary"}))
    match = re.fullmatch(r"(?:store private|save private|privacy vault save)\s+(.+)", cleaned, re.IGNORECASE)
    if match:
        return _voice_tool_result(_power({"action": "privacy_vault_store", "title": match.group(1).strip()}))
    if re.fullmatch(r"(?:model router|model router status|which brain will you use)", lowered):
        return _voice_tool_result(_power({"action": "model_router_status"}))
    match = re.fullmatch(r"(?:choose model|route model)\s+(.+)", cleaned, re.IGNORECASE)
    if match:
        return _voice_tool_result(_power({"action": "model_router_choose", "text": match.group(1).strip()}))
    if re.fullmatch(r"(?:self debugger|self debug status|debug yourself)", lowered):
        return _voice_tool_result(_power({"action": "self_debugger_status"}))
    match = re.fullmatch(r"(?:report failure|debug failure)\s+(.+)", cleaned, re.IGNORECASE)
    if match:
        return _voice_tool_result(_power({"action": "self_debugger_report", "summary": match.group(1).strip()}))
    if re.fullmatch(r"(?:autonomous debugger|debugger mode|watch debugger|watch errors deeply)", lowered):
        return _voice_tool_result(_power({"action": "autonomous_debugger"}))
    match = re.fullmatch(r"(?:debug this|analyze error|analyze stack trace)\s+(.+)", cleaned, re.IGNORECASE)
    if match:
        return _voice_tool_result(_power({"action": "autonomous_debugger_analyze", "text": match.group(1).strip()}))
    if re.fullmatch(r"(?:learned commands|command memory|what commands have you learned)", lowered):
        return _voice_tool_result(_power({"action": "command_memory"}))
    if re.fullmatch(r"(?:install default commands|install personal command language|default command language)", lowered):
        return _voice_tool_result(_power({"action": "command_memory_defaults"}))
    if re.fullmatch(r"(?:tone status|emotion status|how do i sound)", lowered):
        return _voice_tool_result(_power({"action": "tone_status"}))
    match = re.fullmatch(r"(?:analyze tone|tone check)\s+(.+)", cleaned, re.IGNORECASE)
    if match:
        return _voice_tool_result(_power({"action": "tone_analyze", "text": match.group(1).strip()}))
    if re.fullmatch(r"(?:personal crm|crm summary|people summary)", lowered):
        return _voice_tool_result(_power({"action": "crm_summary"}))
    match = re.fullmatch(r"(?:remember person|add person)\s+(.+)", cleaned, re.IGNORECASE)
    if match:
        return _voice_tool_result(_power({"action": "crm_remember_person", "name": match.group(1).strip()}))
    if re.fullmatch(r"(?:crm followups|people followups|who should i follow up with)", lowered):
        return _voice_tool_result(_power({"action": "crm_followups"}))
    if re.fullmatch(r"(?:learning coach|learning progress|study progress)", lowered):
        return _voice_tool_result(_power({"action": "learning_progress"}))
    if re.fullmatch(r"(?:autonomous learning|learn on your own|self learning plan)", lowered):
        return _voice_tool_result(_power({"action": "autonomous_learning"}))
    match = re.fullmatch(r"(?:learn about|study on your own)\s+(.+)", cleaned, re.IGNORECASE)
    if match:
        return _voice_tool_result(_power({"action": "autonomous_learning", "goal": match.group(1).strip()}))
    match = re.fullmatch(r"(?:quiz me|start quiz)(?:\s+on\s+(.+))?", cleaned, re.IGNORECASE)
    if match:
        return _voice_tool_result(_power({"action": "learning_quiz", "topic": (match.group(1) or "").strip()}))
    match = re.fullmatch(r"(?:add learning card|teach me card)\s+(.+?)\s+(?:means|is|=)\s+(.+)", cleaned, re.IGNORECASE)
    if match:
        return _voice_tool_result(_power({"action": "learning_add_card", "topic": "general", "question": match.group(1).strip(), "answer": match.group(2).strip()}))
    if re.fullmatch(r"(?:research briefings|research briefing status)", lowered):
        return _voice_tool_result(_power({"action": "research_briefings"}))
    match = re.fullmatch(r"(?:research briefing|brief me on)\s+(.+)", cleaned, re.IGNORECASE)
    if match:
        return _voice_tool_result(_power({"action": "research_brief", "topic": match.group(1).strip(), "create_task": True}))
    match = re.fullmatch(r"(?:subscribe research|watch research topic)\s+(.+)", cleaned, re.IGNORECASE)
    if match:
        return _voice_tool_result(_power({"action": "research_subscribe", "topic": match.group(1).strip()}))
    if re.fullmatch(r"(?:workspace context|contextual workspace|project context)", lowered):
        return _voice_tool_result(_power({"action": "workspace_context"}))
    if re.fullmatch(r"(?:workspace context status|latest workspace context)", lowered):
        return _voice_tool_result(_power({"action": "workspace_context_status"}))
    if re.fullmatch(r"(?:offline survival|offline status|survival mode status)", lowered):
        return _voice_tool_result(_power({"action": "offline_status"}))
    if re.fullmatch(r"(?:activate offline survival|start offline mode|go offline)", lowered):
        return _voice_tool_result(_power({"action": "offline_activate"}))
    if re.fullmatch(r"(?:deactivate offline survival|stop offline mode|go online)", lowered):
        return _voice_tool_result(_power({"action": "offline_deactivate"}))
    match = re.fullmatch(r"(?:what did i work on|timeline search|personal timeline)\s*(.*)", cleaned, re.IGNORECASE)
    if match and ("timeline" in lowered or "work on" in lowered):
        return _voice_tool_result(_power({"action": "data_timeline", "query": (match.group(1) or "today").strip() or "today"}))
    match = re.fullmatch(r"(?:timeline note|remember timeline)\s+(.+)", cleaned, re.IGNORECASE)
    if match:
        return _voice_tool_result(_power({"action": "data_timeline_note", "title": match.group(1).strip()}))
    if re.fullmatch(r"(?:skill training|training studio|workflow studio)", lowered):
        return _voice_tool_result(_power({"action": "skill_training_summary"}))
    match = re.fullmatch(r"(?:teach friday workflow|start workflow)\s+(.+)", cleaned, re.IGNORECASE)
    if match:
        return _voice_tool_result(_power({"action": "skill_training_start", "title": match.group(1).strip()}))
    if re.fullmatch(r"(?:executive summary|executive powers|autonomy summary)", lowered):
        return _voice_tool_result(_power({"action": "executive_summary"}))
    match = re.fullmatch(r"(?:start mission|mission start|begin mission|run mission)\s+(.+)", cleaned, re.IGNORECASE)
    if match:
        return _voice_tool_result(_power({"action": "mission_start", "goal": match.group(1).strip()}))
    if re.fullmatch(r"(?:mission status|autonomy status|mission control status|what mission is running)", lowered):
        return _voice_tool_result(_power({"action": "mission_status"}))
    match = re.fullmatch(r"(?:pause mission)\s*([0-9]+)?", cleaned, re.IGNORECASE)
    if match:
        return _voice_tool_result(_power({"action": "mission_pause", "mission_id": match.group(1) or 0}))
    match = re.fullmatch(r"(?:resume mission)\s*([0-9]+)?", cleaned, re.IGNORECASE)
    if match:
        return _voice_tool_result(_power({"action": "mission_resume", "mission_id": match.group(1) or 0}))
    match = re.fullmatch(r"(?:stop mission|cancel mission)\s*([0-9]+)?", cleaned, re.IGNORECASE)
    if match:
        return _voice_tool_result(_power({"action": "mission_stop", "mission_id": match.group(1) or 0}))
    match = re.fullmatch(r"(?:approve mission)\s+([0-9]+)(?:\s+(.+))?", cleaned, re.IGNORECASE)
    if match:
        return _voice_tool_result(_power({"action": "mission_approve", "mission_id": match.group(1), "note": (match.group(2) or "").strip()}))
    match = re.fullmatch(r"(?:approve deploy|approve deployment)\s+([0-9]+)(?:\s+(.+))?", cleaned, re.IGNORECASE)
    if match:
        return _voice_tool_result(_power({"action": "mission_approve_deploy", "mission_id": match.group(1), "note": (match.group(2) or "").strip()}))
    if re.fullmatch(r"(?:what evidence do you have|show mission evidence|show evidence)", lowered):
        return _voice_tool_result(_power({"action": "mission_evidence"}))
    if re.fullmatch(r"(?:proof report|trust proof|create proof report)", lowered):
        return _voice_tool_result(_power({"action": "proof_report"}))
    if re.fullmatch(r"(?:continuity status|unfinished threads|what did we leave unfinished)", lowered):
        return _voice_tool_result(_power({"action": "continuity_status"}))
    if re.fullmatch(r"(?:capture continuity|remember unfinished work|save where we stopped)", lowered):
        return _voice_tool_result(_power({"action": "continuity_capture"}))
    if re.fullmatch(r"(?:context fusion|live context|fuse context)", lowered):
        return _voice_tool_result(_power({"action": "context_fusion"}))
    if re.fullmatch(r"(?:awareness graph|what is happening now|what's happening now|what is happening right now|what's happening right now|what is going on right now)", lowered):
        return _voice_tool_result(_power({"action": "awareness_graph", "question": cleaned}))
    match = re.fullmatch(r"(?:deep project autopilot|run deep project autopilot|check project deeply)\s*(.*)", cleaned, re.IGNORECASE)
    if match and ("project" in lowered or "autopilot" in lowered):
        return _voice_tool_result(_power({"action": "deep_project_autopilot", "root": (match.group(1) or "").strip()}))
    match = re.fullmatch(r"(?:set silence mode|silence mode)\s+(.+)", cleaned, re.IGNORECASE)
    if match:
        return _voice_tool_result(_power({"action": "silence_mode", "mode": match.group(1).strip()}))
    if re.fullmatch(r"(?:silence mode|context aware silence)", lowered):
        return _voice_tool_result(_power({"action": "silence_mode"}))
    if re.fullmatch(r"(?:browser pc copilot|local browser copilot|pc copilot)", lowered):
        return _voice_tool_result(_power({"action": "browser_pc_copilot"}))
    if re.fullmatch(r"(?:debug current page|debug this page|browser pc debug)", lowered):
        return _voice_tool_result(_power({"action": "browser_pc_debug"}))
    if re.fullmatch(r"(?:skill evolution|suggest skills|workflow suggestions)", lowered):
        return _voice_tool_result(_power({"action": "skill_evolution"}))
    match = re.fullmatch(r"(?:i did workflow|record workflow signal)\s+(.+)", cleaned, re.IGNORECASE)
    if match:
        return _voice_tool_result(_power({"action": "skill_evolution_observe", "signature": match.group(1).strip(), "description": match.group(1).strip()}))
    if re.fullmatch(r"(?:safety guardian|personal safety scan|scan for secrets)", lowered):
        return _voice_tool_result(_power({"action": "safety_guardian"}))
    match = re.fullmatch(r"(?:safety preflight|check risky action)\s+(.+)", cleaned, re.IGNORECASE)
    if match:
        return _voice_tool_result(_power({"action": "safety_preflight", "instruction": match.group(1).strip()}))
    if re.fullmatch(r"(?:phone mesh|phone handoffs|phone to pc mesh)", lowered):
        return _voice_tool_result(_power({"action": "phone_mesh"}))
    match = re.fullmatch(r"(?:handoff from phone|phone handoff)\s+(.+)", cleaned, re.IGNORECASE)
    if match:
        return _voice_tool_result(_power({"action": "phone_handoff", "title": match.group(1).strip()}))
    if re.fullmatch(r"(?:agent scheduler|scheduler status|agent schedule)", lowered):
        return _voice_tool_result(_power({"action": "agent_scheduler_status"}))
    if re.fullmatch(r"(?:plan agents|schedule agents|agent scheduler plan)", lowered):
        return _voice_tool_result(_power({"action": "agent_scheduler_plan"}))
    if re.fullmatch(r"(?:retry failed tasks|retry failed agents)", lowered):
        return _voice_tool_result(_power({"action": "retry_failed_tasks"}))
    match = re.fullmatch(r"(?:schedule overnight research|overnight research)\s*(.*)", cleaned, re.IGNORECASE)
    if match and ("research" in lowered):
        return _voice_tool_result(_power({"action": "schedule_overnight_research", "topic": (match.group(1) or "").strip()}))
    if re.fullmatch(r"(?:test build monitor|build monitor|run test monitor)", lowered):
        return _voice_tool_result(_power({"action": "test_build_monitor"}))
    if re.fullmatch(r"(?:reliability score|score yourself|score friday)", lowered):
        return _voice_tool_result(_power({"action": "reliability_score"}))
    if re.fullmatch(r"(?:model benchmark|benchmark models|local model benchmark)", lowered):
        return _voice_tool_result(_power({"action": "model_benchmark"}))
    match = re.fullmatch(r"(?:deployment brain|inspect deployment)\s*(.*)", cleaned, re.IGNORECASE)
    if match and ("deploy" in lowered):
        return _voice_tool_result(_power({"action": "deployment_brain", "target": (match.group(1) or "").strip()}))
    if re.fullmatch(r"(?:os autopilot|what should i do next|next move)", lowered):
        return _voice_tool_result(_power({"action": "os_autopilot"}))
    if re.fullmatch(r"(?:version guardian|version preflight|backup guardian)", lowered):
        return _voice_tool_result(_power({"action": "version_guardian_preflight", "instruction": cleaned}))
    if re.fullmatch(r"(?:fix loop status|autonomous fix status)", lowered):
        return _voice_tool_result(_power({"action": "fix_loop_status"}))
    match = re.fullmatch(r"(?:run fix loop|autonomous fix loop|fix this error)\s*(.*)", cleaned, re.IGNORECASE)
    if match and ("fix" in lowered or "error" in lowered):
        return _voice_tool_result(_power({"action": "fix_loop", "log_text": (match.group(1) or "").strip()}))
    if re.fullmatch(r"(?:browser pro|browser pro guidance|what button should i click|what should i click)", lowered):
        return _voice_tool_result(_power({"action": "browser_pro", "question": cleaned}))
    if re.fullmatch(r"(?:watch this page|browser watch page)", lowered):
        return _voice_tool_result(_power({"action": "browser_pro_watch"}))
    if re.fullmatch(r"(?:android pro|android companion pro)", lowered):
        return _voice_tool_result(_power({"action": "android_pro"}))
    if re.fullmatch(r"(?:memory review pro|review my memory|review your memories)", lowered):
        return _voice_tool_result(_power({"action": "memory_review_pro"}))
    match = re.fullmatch(r"(?:app mastery|operator mastery|master app)\s+([a-zA-Z0-9 _-]+)(?:\s+(.+))?", cleaned, re.IGNORECASE)
    if match:
        return _voice_tool_result(_power({"action": "app_mastery", "app": match.group(1).strip(), "instruction": (match.group(2) or "").strip()}))
    match = re.fullmatch(r"(?:local ai search|private search|search my private index for)\s+(.+)", cleaned, re.IGNORECASE)
    if match:
        return _voice_tool_result(_power({"action": "local_ai_search", "query": match.group(1).strip()}))
    if re.fullmatch(r"(?:life os|life os brief|daily life os)", lowered):
        return _voice_tool_result(_power({"action": "life_os"}))
    if re.fullmatch(r"(?:life os next|what should i do next life os)", lowered):
        return _voice_tool_result(_power({"action": "life_os_next"}))
    if re.fullmatch(r"(?:security guardian pro|defensive security scan)", lowered):
        return _voice_tool_result(_power({"action": "security_guardian_pro"}))
    if re.fullmatch(r"(?:cloud worker|cloud worker mode)", lowered):
        return _voice_tool_result(_power({"action": "cloud_worker"}))
    if re.fullmatch(r"(?:autonomy engine|autonomy engine status|real time autonomy|autonomy status)", lowered):
        return _voice_tool_result(_power({"action": "autonomy_status"}))
    match = re.fullmatch(r"(?:run autonomy engine|continue autonomously|figure this out autonomously|autonomously do)\s+(.+)", cleaned, re.IGNORECASE)
    if match:
        return _voice_tool_result(_power({"action": "autonomy_engine", "goal": match.group(1).strip()}))
    if re.fullmatch(r"(?:what do you know|what don't you know|what do you not know|certainty brain|what are you unsure about)", lowered):
        return _voice_tool_result(_power({"action": "certainty_brain", "query": cleaned}))
    match = re.fullmatch(r"(?:remember certainty|record fact|record guess|record missing)\s+(.+)", cleaned, re.IGNORECASE)
    if match:
        kind = "missing" if "missing" in lowered else ("guess" if "guess" in lowered else "known")
        return _voice_tool_result(_power({"action": "certainty_record", "kind": kind, "statement": match.group(1).strip()}))
    if re.fullmatch(r"(?:vision skill status|ui pattern memory|computer vision skills)", lowered):
        return _voice_tool_result(_power({"action": "vision_skill_recognize", "query": ""}))
    match = re.fullmatch(r"(?:learn ui pattern|remember ui pattern|learn this screen)\s+(.+)", cleaned, re.IGNORECASE)
    if match:
        return _voice_tool_result(_power({"action": "vision_skill_learn", "label": match.group(1).strip(), "meaning": match.group(1).strip()}))
    if re.fullmatch(r"(?:automation daemon|automation daemon status)", lowered):
        return _voice_tool_result(_power({"action": "automation_daemon_status"}))
    if re.fullmatch(r"(?:run automation daemon|check automation daemon)", lowered):
        return _voice_tool_result(_power({"action": "automation_daemon"}))
    if re.fullmatch(r"(?:rank notifications|notification intelligence|sort notifications)", lowered):
        return _voice_tool_result(_power({"action": "notification_intelligence"}))
    if re.fullmatch(r"(?:test yourself|self test personality|self testing personality)", lowered):
        return _voice_tool_result(_power({"action": "self_test_personality"}))
    if re.fullmatch(r"(?:project memory|repo memory|remember this repo)", lowered):
        return _voice_tool_result(_power({"action": "project_memory"}))
    match = re.fullmatch(r"(?:remember project note|save project memory)\s+(.+)", cleaned, re.IGNORECASE)
    if match:
        return _voice_tool_result(_power({"action": "project_memory_remember", "title": "Voice project note", "content": match.group(1).strip()}))
    if re.fullmatch(r"(?:operator skills|specialist operators|app operators pro)", lowered):
        return _voice_tool_result(_power({"action": "operator_skills"}))
    match = re.fullmatch(r"(?:start operator skill|use operator skill|operator skill)\s+([a-zA-Z0-9 _-]+)(?:\s+to\s+(.+))?", cleaned, re.IGNORECASE)
    if match:
        return _voice_tool_result(_power({"action": "operator_skill_start", "app": match.group(1).strip(), "instruction": (match.group(2) or "").strip()}))
    match = re.fullmatch(r"(?:learning roadmap|make learning roadmap|plan my learning)\s*(.*)", cleaned, re.IGNORECASE)
    if match and "learning" in lowered:
        return _voice_tool_result(_power({"action": "learning_roadmap", "topic": (match.group(1) or "general").strip() or "general"}))
    if re.fullmatch(r"(?:roadmap quiz|learning roadmap quiz)", lowered):
        return _voice_tool_result(_power({"action": "learning_roadmap_quiz"}))
    match = re.fullmatch(r"(?:privacy firewall pro|privacy pro check)\s+(.+)", cleaned, re.IGNORECASE)
    if match:
        return _voice_tool_result(_power({"action": "privacy_firewall_pro", "instruction": match.group(1).strip()}))
    if re.fullmatch(r"(?:device mesh|command mesh|multi device mesh)", lowered):
        return _voice_tool_result(_power({"action": "device_mesh"}))
    match = re.fullmatch(r"(?:device handoff|continue on laptop|send to laptop)\s+(.+)", cleaned, re.IGNORECASE)
    if match:
        return _voice_tool_result(_power({"action": "device_mesh_handoff", "title": match.group(1).strip()}))
    if re.fullmatch(r"(?:release engine|release engineer status)", lowered):
        return _voice_tool_result(_power({"action": "release_engine_status"}))
    match = re.fullmatch(r"(?:autonomous release engineer|prepare release proof|release engineer)\s*(.*)", cleaned, re.IGNORECASE)
    if match and "release" in lowered:
        return _voice_tool_result(_power({"action": "release_engine", "root": (match.group(1) or "").strip()}))
    if re.fullmatch(r"(?:decision memory|decision preferences|how do i decide)", lowered):
        return _voice_tool_result(_power({"action": "decision_memory"}))
    match = re.fullmatch(r"(?:remember decision|remember preference decision)\s+(.+)", cleaned, re.IGNORECASE)
    if match:
        return _voice_tool_result(_power({"action": "decision_memory", "category": "communication", "preference": match.group(1).strip()}))
    match = re.fullmatch(r"(?:infer my preference|learn my decision style)\s+(.+)", cleaned, re.IGNORECASE)
    if match:
        return _voice_tool_result(_power({"action": "decision_memory_infer", "text": match.group(1).strip()}))
    if re.fullmatch(r"(?:skill improvement|skill improvement status|improve your skills)", lowered):
        return _voice_tool_result(_power({"action": "skill_improvement"}))
    match = re.fullmatch(r"(?:record skill failure|skill failed)\s+(.+)", cleaned, re.IGNORECASE)
    if match:
        return _voice_tool_result(_power({"action": "skill_failure", "skill": "voice_reported", "failure": match.group(1).strip()}))
    if re.fullmatch(r"(?:workspace coach|live workspace coach|coach this workspace)", lowered):
        return _voice_tool_result(_power({"action": "workspace_coach"}))
    match = re.fullmatch(r"(?:memory debate|debate memory|what do you believe about)\s*(.*)", cleaned, re.IGNORECASE)
    if match and ("debate" in lowered or "believe" in lowered):
        return _voice_tool_result(_power({"action": "memory_debate", "topic": (match.group(1) or "").strip()}))
    if re.fullmatch(r"(?:focus protection|protect my focus|focus status)", lowered):
        return _voice_tool_result(_power({"action": "focus_protection"}))
    match = re.fullmatch(r"(?:start focus mode|set focus mode|focus mode)\s*(.*)", cleaned, re.IGNORECASE)
    if match and "focus" in lowered:
        return _voice_tool_result(_power({"action": "focus_mode", "mode": (match.group(1) or "focus").strip() or "focus"}))
    match = re.fullmatch(r"(?:start app apprenticeship|teach app workflow)\s+([a-zA-Z0-9 _-]+)(?:\s+(.+))?", cleaned, re.IGNORECASE)
    if match:
        return _voice_tool_result(_power({"action": "app_apprenticeship_start", "app": match.group(1).strip(), "workflow": (match.group(2) or "workflow").strip()}))
    match = re.fullmatch(r"(?:record apprenticeship step)\s+([0-9]+)\s+(.+)", cleaned, re.IGNORECASE)
    if match:
        return _voice_tool_result(_power({"action": "app_apprenticeship_step", "session_id": match.group(1), "narration": match.group(2).strip()}))
    match = re.fullmatch(r"(?:finish app apprenticeship|publish app apprenticeship)\s+([0-9]+)", cleaned, re.IGNORECASE)
    if match:
        return _voice_tool_result(_power({"action": "app_apprenticeship_finish", "session_id": match.group(1)}))
    if re.fullmatch(r"(?:project cto|cto report|act as cto)", lowered):
        return _voice_tool_result(_power({"action": "project_cto"}))
    if re.fullmatch(r"(?:conversation continuity|open threads|what threads are open)", lowered):
        return _voice_tool_result(_power({"action": "conversation_continuity"}))
    match = re.fullmatch(r"(?:remember this thread|save conversation thread)\s+(.+)", cleaned, re.IGNORECASE)
    if match:
        return _voice_tool_result(_power({"action": "conversation_capture", "title": match.group(1).strip(), "summary": match.group(1).strip()}))
    if re.fullmatch(r"(?:local voice brain|voice brain status)", lowered):
        return _voice_tool_result(_power({"action": "local_voice_brain"}))
    if re.fullmatch(r"(?:install voice defaults|tune local voice|voice defaults)", lowered):
        return _voice_tool_result(_power({"action": "local_voice_defaults"}))
    match = re.fullmatch(r"(?:voice repair|repair voice)\s+(.+?)\s+(?:means|should be|is)\s+(.+)", cleaned, re.IGNORECASE)
    if match:
        return _voice_tool_result(_power({"action": "voice_brain_repair", "heard": match.group(1).strip(), "expected": match.group(2).strip()}))
    if re.fullmatch(r"(?:trust dashboard|what can i trust|show trust)", lowered):
        return _voice_tool_result(_power({"action": "trust_dashboard"}))
    if re.fullmatch(r"(?:agent quality|agent quality status|quality manager)", lowered):
        return _voice_tool_result(_power({"action": "agent_quality"}))
    if re.fullmatch(r"(?:agent leaderboard|best agents|rank agents)", lowered):
        return _voice_tool_result(_power({"action": "agent_leaderboard"}))
    match = re.fullmatch(r"(?:hire agent|create agent)\s+(.+?)\s+(?:for|to)\s+(.+)", cleaned, re.IGNORECASE)
    if match:
        return _voice_tool_result(_power({"action": "agent_hire", "name": match.group(1).strip(), "purpose": match.group(2).strip()}))
    match = re.fullmatch(r"(?:retire agent|fire agent)\s+(.+)", cleaned, re.IGNORECASE)
    if match:
        return _voice_tool_result(_power({"action": "agent_retire", "agent_id": match.group(1).strip()}))
    match = re.fullmatch(r"(?:promote agent)\s+(.+)", cleaned, re.IGNORECASE)
    if match:
        return _voice_tool_result(_power({"action": "agent_promote", "agent_id": match.group(1).strip()}))
    match = re.fullmatch(r"(?:agent council|ask the council|council)\s+(.+)", cleaned, re.IGNORECASE)
    if match:
        return _voice_tool_result(_power({"action": "agent_council", "question": match.group(1).strip()}))
    match = re.fullmatch(r"(?:do not forget|remember this deeply)\s+(.+)", cleaned, re.IGNORECASE)
    if match:
        return _voice_tool_result(_power({"action": "do_not_forget", "content": match.group(1).strip()}))
    if re.fullmatch(r"(?:dev server copilot|dev copilot)", lowered):
        return _voice_tool_result(_power({"action": "dev_server_copilot"}))
    match = re.fullmatch(r"(?:simulate code change|code change simulator)\s+(.+)", cleaned, re.IGNORECASE)
    if match:
        return _voice_tool_result(_power({"action": "code_change_simulator", "instruction": match.group(1).strip()}))
    match = re.fullmatch(r"(?:refactor plan|plan refactor|autonomous refactor planner)\s*(.*)", cleaned, re.IGNORECASE)
    if match and ("refactor" in lowered):
        return _voice_tool_result(_power({"action": "refactor_planner", "focus": (match.group(1) or "").strip()}))
    match = re.fullmatch(r"(?:organize|clean up|audit)\s+(?:this\s+)?(?:codebase|repo|project)(?:\s+(.*))?", cleaned, re.IGNORECASE)
    if match:
        return _voice_tool_result(_power({"action": "codebase_standards", "focus": (match.group(1) or "").strip()}))
    match = re.fullmatch(r"(?:taste engine|learn my taste)\s+(.+)", cleaned, re.IGNORECASE)
    if match:
        return _voice_tool_result(_power({"action": "taste_engine", "correction": match.group(1).strip()}))
    if re.fullmatch(r"(?:memory constitution|memory policy)", lowered):
        return _voice_tool_result(_power({"action": "memory_constitution"}))
    match = re.fullmatch(r"(?:reality check|verify claim)\s+(.+)", cleaned, re.IGNORECASE)
    if match:
        return _voice_tool_result(_power({"action": "reality_check", "claim": match.group(1).strip()}))
    match = re.fullmatch(r"(?:simulate agents|agent simulation|simulate mission)\s+(.+)", cleaned, re.IGNORECASE)
    if match:
        return _voice_tool_result(_power({"action": "agent_simulation", "goal": match.group(1).strip()}))
    if re.fullmatch(r"(?:install command graph defaults|command graph defaults)", lowered):
        return _voice_tool_result(_power({"action": "command_graph_defaults"}))
    match = re.fullmatch(r"(?:command graph|resolve command)\s+(.+)", cleaned, re.IGNORECASE)
    if match:
        return _voice_tool_result(_power({"action": "command_graph", "phrase": match.group(1).strip()}))
    match = re.fullmatch(r"(?:emotional timing|timing advice)\s*(.*)", cleaned, re.IGNORECASE)
    if match and ("timing" in lowered or "emotional" in lowered):
        return _voice_tool_result(_power({"action": "emotional_timing", "text": (match.group(1) or cleaned).strip()}))
    match = re.fullmatch(r"(?:learn screen|visual skill memory|remember screen)\s+(.+)", cleaned, re.IGNORECASE)
    if match:
        return _voice_tool_result(_power({"action": "visual_skill_memory", "screen_label": match.group(1).strip()}))
    match = re.fullmatch(r"(?:failure autopsy|write autopsy)\s+(.+)", cleaned, re.IGNORECASE)
    if match:
        return _voice_tool_result(_power({"action": "failure_autopsy", "title": "Voice failure autopsy", "what_happened": match.group(1).strip()}))
    if re.fullmatch(r"(?:what are you trying next|what will you try next|explain your mind|what are you thinking)", lowered):
        return _voice_tool_result(_power({"action": "mission_status"}))
    match = re.fullmatch(r"(?:run qa lab|qa lab|autonomous qa)\s*(.*)", cleaned, re.IGNORECASE)
    if match and ("qa" in lowered or "lab" in lowered):
        return _voice_tool_result(_power({"action": "qa_lab", "root": (match.group(1) or "").strip()}))
    match = re.fullmatch(r"(?:prepare release|release manager)\s*(.*)", cleaned, re.IGNORECASE)
    if match and ("release" in lowered):
        return _voice_tool_result(_power({"action": "release_prepare", "root": (match.group(1) or "").strip()}))
    if re.fullmatch(r"(?:error radar|watch errors|check errors)", lowered):
        return _voice_tool_result(_power({"action": "error_radar"}))
    match = re.fullmatch(r"(?:semantic index|index everything|index this project)\s*(.*)", cleaned, re.IGNORECASE)
    if match and ("index" in lowered):
        return _voice_tool_result(_power({"action": "semantic_index", "path": (match.group(1) or "").strip()}))
    match = re.fullmatch(r"(?:search everything for|semantic search|search all memory for)\s+(.+)", cleaned, re.IGNORECASE)
    if match:
        return _voice_tool_result(_power({"action": "semantic_search", "query": match.group(1).strip()}))
    if re.fullmatch(r"(?:browser extension status|extension status)", lowered):
        return _voice_tool_result(_power({"action": "browser_extension_status"}))
    if re.fullmatch(r"(?:browser insight|page insight|understand this page)", lowered):
        return _voice_tool_result(_power({"action": "browser_extension_insight"}))
    if re.fullmatch(r"(?:app state memory|muscle memory)", lowered):
        return _voice_tool_result(_power({"action": "app_state_memory"}))
    if re.fullmatch(r"(?:operating rhythm|rhythm summary|energy plan)", lowered):
        return _voice_tool_result(_power({"action": "rhythm_summary"}))
    if re.fullmatch(r"(?:environment status|environment awareness|what is my pc environment)", lowered):
        return _voice_tool_result(_power({"action": "environment_status"}))
    if re.fullmatch(r"(?:capture environment|environment snapshot)", lowered):
        return _voice_tool_result(_power({"action": "environment_snapshot"}))
    if re.fullmatch(r"(?:calendar email brief|email calendar brief|real assistant brief)", lowered):
        return _voice_tool_result(_power({"action": "calendar_email_brief"}))
    if re.fullmatch(r"(?:email followups|calendar followups|follow up review)", lowered):
        return _voice_tool_result(_power({"action": "calendar_email_followups"}))
    match = re.fullmatch(r"(?:energy note|record energy)\s+(.+)", cleaned, re.IGNORECASE)
    if match:
        return _voice_tool_result(_power({"action": "energy_note", "mood": match.group(1).strip()}))
    if re.fullmatch(r"(?:memory review|review your memory|real memory review)", lowered):
        return _voice_tool_result(_power({"action": "memory_review"}))
    match = re.fullmatch(r"(?:mark memory review|resolve memory review)\s+([0-9]+)\s+(confirm|keep|forget|update|skip)(?:\s+(.+))?", cleaned, re.IGNORECASE)
    if match:
        return _voice_tool_result(_power({"action": "memory_review_resolve", "review_id": match.group(1), "decision": match.group(2), "note": (match.group(3) or "").strip()}))
    match = re.fullmatch(r"(?:start task autopilot|task autopilot|run autopilot for|figure out)\s+(.+)", cleaned, re.IGNORECASE)
    if match:
        return _voice_tool_result(_power({"action": "task_autopilot", "goal": match.group(1).strip()}))
    if re.fullmatch(r"(?:task autopilot status|autopilot status|checkpoint status)", lowered):
        return _voice_tool_result(_power({"action": "task_autopilot_status"}))
    match = re.fullmatch(r"(?:set personality|voice personality|set profile)\s+(.+)", cleaned, re.IGNORECASE)
    if match:
        return _voice_tool_result(_power({"action": "personality_profile", "profile": match.group(1).strip()}))
    if re.fullmatch(r"(?:life dashboard|show life dashboard|my dashboard)", lowered):
        return _voice_tool_result(_power({"action": "life_dashboard"}))
    match = re.fullmatch(r"(?:start skill recording|record skill|skill recorder)\s+(.+)", cleaned, re.IGNORECASE)
    if match:
        return _voice_tool_result(_power({"action": "skill_record_start", "name": match.group(1).strip()}))
    match = re.fullmatch(r"(?:record skill step|add skill step)\s+([0-9]+)\s+(.+)", cleaned, re.IGNORECASE)
    if match:
        return _voice_tool_result(_power({"action": "skill_record_step", "recording_id": match.group(1), "narration": match.group(2).strip()}))
    match = re.fullmatch(r"(?:finish skill recording|publish recorded skill)\s+([0-9]+)", cleaned, re.IGNORECASE)
    if match:
        return _voice_tool_result(_power({"action": "skill_record_finish", "recording_id": match.group(1)}))
    if re.fullmatch(r"(?:documentation brain|update autonomous docs|update project documentation)", lowered):
        return _voice_tool_result(_power({"action": "documentation_brain"}))
    match = re.fullmatch(r"(?:personal search|search everything|find across friday)\s+(.+)", cleaned, re.IGNORECASE)
    if match:
        return _voice_tool_result(_power({"action": "personal_search", "query": match.group(1).strip()}))
    match = re.fullmatch(r"(?:trust meter|assess risk|can i trust this)\s+(.+)", cleaned, re.IGNORECASE)
    if match:
        return _voice_tool_result(_power({"action": "trust_meter", "instruction": match.group(1).strip()}))
    if re.fullmatch(r"(?:learning twin|how do i learn|my learning profile)", lowered):
        return _voice_tool_result(_power({"action": "learning_twin"}))
    if re.fullmatch(r"(?:relationship assistant|relationships|who did i promise)", lowered):
        return _voice_tool_result(_power({"action": "relationship_assistant"}))
    match = re.fullmatch(r"(?:deployment commander|inspect deployment|check deployed app)\s*(.*)", cleaned, re.IGNORECASE)
    if match and ("deployment" in lowered or "deployed" in lowered):
        return _voice_tool_result(_power({"action": "deployment_commander", "target": (match.group(1) or "").strip()}))
    match = re.fullmatch(r"(?:privacy firewall|privacy check)\s+(.+)", cleaned, re.IGNORECASE)
    if match:
        return _voice_tool_result(_power({"action": "privacy_firewall", "instruction": match.group(1).strip()}))
    match = re.fullmatch(r"(?:no|nah|actually|correction)[,\s]+(?:i\s+said\s+)?(.+)", cleaned, re.IGNORECASE)
    if match:
        return _voice_tool_result(_power({"action": "voice_repair", "expected_text": match.group(1).strip()}))
    match = re.fullmatch(r"(?:remember in vault|save to vault|remember preference|remember priority)\s+(.+)", cleaned, re.IGNORECASE)
    if match:
        kind = "weekly_priority" if "priority" in lowered else ("preference" if "preference" in lowered else "fact")
        return _voice_tool_result(_power({"action": "remember_vault", "kind": kind, "title": match.group(1).strip()}))
    match = re.fullmatch(r"(?:search vault|vault search|what do you know about)\s+(.+)", cleaned, re.IGNORECASE)
    if match:
        return _voice_tool_result(_power({"action": "vault_search", "query": match.group(1).strip()}))
    if re.fullmatch(r"(?:what matters this week|weekly priorities)", lowered):
        return _voice_tool_result(_power({"action": "weekly_priorities"}))
    if re.fullmatch(r"(?:analyze|map)\s+(?:this\s+)?(?:workspace|project|codebase)\s+(?:deeply|brain)?", lowered):
        return _voice_tool_result(_power({"action": "workspace_analyze"}))
    match = re.fullmatch(r"(?:where is|where's|find)\s+(.+?)\s+(?:logic|code|in this workspace|in the codebase)?", cleaned, re.IGNORECASE)
    if match and any(word in lowered for word in {"auth", "login", "logic", "code", "workspace", "codebase"}):
        return _voice_tool_result(_power({"action": "workspace_question", "question": cleaned}))
    if re.fullmatch(r"(?:generate|update)\s+(?:workspace|project|codebase)\s+docs", lowered):
        return _voice_tool_result(_power({"action": "workspace_docs"}))
    if re.fullmatch(r"(?:project autopilot|inspect project|watch project)", lowered):
        return _voice_tool_result(_power({"action": "project_autopilot"}))
    if re.fullmatch(r"(?:prepare project fixes|autopilot prepare fixes)", lowered):
        return _voice_tool_result(_power({"action": "project_prepare_fixes"}))
    if re.fullmatch(r"(?:pc timeline|capture pc timeline|screen timeline)", lowered):
        return _voice_tool_result(_power({"action": "pc_timeline"}))
    if re.fullmatch(r"(?:pc timeline summary|awareness timeline summary)", lowered):
        return _voice_tool_result(_power({"action": "pc_timeline_summary"}))
    match = re.fullmatch(r"(?:create goal plan|plan goal|big goal)\s+(.+)", cleaned, re.IGNORECASE)
    if match:
        return _voice_tool_result(_power({"action": "goal_plan", "title": match.group(1).strip()}))
    if re.fullmatch(r"(?:next goal action|what should i do for my goal)", lowered):
        return _voice_tool_result(_power({"action": "goal_next"}))
    if re.fullmatch(r"(?:index my files|index local files|file intelligence)", lowered):
        return _voice_tool_result(_power({"action": "file_index"}))
    match = re.fullmatch(r"(?:find file|search files|where is the file about)\s+(.+)", cleaned, re.IGNORECASE)
    if match:
        return _voice_tool_result(_power({"action": "file_search", "query": match.group(1).strip()}))
    match = re.fullmatch(r"(?:summarize folder|folder summary)\s+(.+)", cleaned, re.IGNORECASE)
    if match:
        return _voice_tool_result(_power({"action": "folder_summary", "path": match.group(1).strip()}))
    match = re.fullmatch(r"(?:study session|summarize transcript|meeting notes)\s+(.+)", cleaned, re.IGNORECASE)
    if match:
        return _voice_tool_result(_power({"action": "study_session", "title": "Voice study session", "transcript": match.group(1).strip()}))
    match = re.fullmatch(r"(?:create automation|automation recipe|when .+)", cleaned, re.IGNORECASE)
    if match and ("when " in lowered or "automation" in lowered):
        return _voice_tool_result(_power({"action": "automation_from_text", "text": cleaned}))
    if re.fullmatch(r"(?:run matching automations|check automations)", lowered):
        return _voice_tool_result(_power({"action": "automation_run_matches"}))
    if re.fullmatch(r"(?:list|show)\s+app operators", lowered):
        return _voice_tool_result(_power({"action": "list_app_operators"}))
    match = re.fullmatch(r"(?:use|start)\s+(.+?)\s+operator\s+(?:to\s+)?(.+)", cleaned, re.IGNORECASE)
    if match:
        return _voice_tool_result(_power({"action": "operate_app", "app": match.group(1).strip(), "instruction": match.group(2).strip()}))
    match = re.fullmatch(r"(?:start|create)\s+(?:an\s+)?autonomous coding\s+(?:task\s+)?(?:to\s+)?(.+)", cleaned, re.IGNORECASE)
    if match:
        return _voice_tool_result(_power({"action": "autonomous_coding", "request": match.group(1).strip()}))
    if re.fullmatch(r"(?:personal life os|daily plan|plan my day deeply)", lowered):
        return _voice_tool_result(_power({"action": "daily_plan"}))
    if re.fullmatch(r"(?:what should i do next|next personal action)", lowered):
        return _voice_tool_result(_power({"action": "next_action"}))
    if re.fullmatch(r"(?:end of day summary|summarize my day)", lowered):
        return _voice_tool_result(_power({"action": "end_of_day"}))
    if re.fullmatch(r"(?:home assistant status|smart home status)", lowered):
        return _voice_tool_result(_power({"action": "home_assistant_status"}))
    if re.fullmatch(r"(?:turn on focus mode|start focus mode)", lowered):
        return _voice_tool_result(_power({"action": "home_assistant_focus", "on": True}))
    if re.fullmatch(r"(?:turn off focus mode|stop focus mode)", lowered):
        return _voice_tool_result(_power({"action": "home_assistant_focus", "on": False}))
    if re.fullmatch(r"(?:backup config|snapshot config)", lowered):
        return _voice_tool_result(_power({"action": "backup_config"}))
    match = re.fullmatch(r"(?:backup file|backup)\s+(.+)", cleaned, re.IGNORECASE)
    if match:
        return _voice_tool_result(_power({"action": "backup_file", "path": match.group(1).strip()}))
    if re.fullmatch(r"(?:list|show)\s+backups", lowered):
        return _voice_tool_result(_power({"action": "list_backups"}))
    match = re.fullmatch(r"(?:is it safe to delete|delete guard)\s+(.+)", cleaned, re.IGNORECASE)
    if match:
        return _voice_tool_result(_power({"action": "delete_guard", "path": match.group(1).strip()}))
    return ""


def _direct_pc_control(text: str) -> str:
    task_reply = _direct_desktop_task(text)
    if task_reply:
        return task_reply

    match = re.search(r"\b(?:open|launch|start)\s+(?:the\s+)?(.+)$", text, re.IGNORECASE)
    if match:
        spoken_target = match.group(1).strip(" .,!?:;")
        if _looks_like_path_request(spoken_target):
            return _voice_tool_result(_pc({"action": "open_path", "target": _spoken_path(spoken_target)}))
        target = _app_name(spoken_target)
        if target:
            return _voice_tool_result(_pc({"action": "open_app", "target": target}))
        if bool(config_value("pc_trusted_mode_enabled", False)) and bool(config_value("pc_allow_arbitrary_apps", False)):
            return _voice_tool_result(_pc({"action": "open_app", "target": spoken_target}))

    match = re.search(r"\b(?:close|quit|exit)\s+(?:the\s+)?(.+)$", text, re.IGNORECASE)
    if match:
        target = _app_name(match.group(1))
        if target:
            return _voice_tool_result(_pc({"action": "close_app", "target": target}))

    reply = _direct_desktop_control(text)
    if reply:
        return reply
    return ""


def _direct_pc_awareness(text: str) -> str:
    cleaned = _strip_leading_assistant_name(text).strip(" ,.!?:;")
    lowered = cleaned.lower()
    if not lowered:
        return ""
    if re.fullmatch(
        r"(?:what(?:'s| is) happening on (?:my|the) pc|what(?:'s| is) on (?:my|the) pc|pc awareness|scan (?:my|the) pc|refresh pc awareness)",
        lowered,
    ):
        force = "refresh" in lowered or "scan" in lowered
        return _voice_tool_result(_pc({"action": "pc_awareness_snapshot", "force_refresh": force}))
    if re.fullmatch(
        r"(?:what apps are (?:open|opened|running)|which apps are (?:open|opened|running)|list (?:open|opened|running) apps|show (?:open|opened|running) apps)",
        lowered,
    ):
        return _voice_tool_result(_pc({"action": "list_running_apps", "limit": 20}))
    if re.fullmatch(
        r"(?:what apps are installed|which apps are installed|list installed apps|show installed apps|what programs are installed)",
        lowered,
    ):
        return _voice_tool_result(_pc({"action": "list_installed_apps", "limit": 30}))
    if re.fullmatch(
        r"(?:what apps are on (?:my|the) (?:desktop|home screen)|which apps are on (?:my|the) (?:desktop|home screen)|list (?:desktop|home screen) apps|show (?:desktop|home screen) apps)",
        lowered,
    ):
        return _voice_tool_result(_pc({"action": "list_desktop_apps", "limit": 30}))
    match = re.fullmatch(r"(?:find|look for|can you find)\s+(?:the\s+)?(?:app|program|application)?\s*(.+?)(?:\s+on (?:my|the) pc)?", lowered)
    if match and not lowered.startswith(("find online", "find on web")):
        query = match.group(1).strip(" .,!?:;")
        if query and len(query.split()) <= 5:
            return _voice_tool_result(_pc({"action": "find_app", "target": query}))
    return ""


def _direct_desktop_control(text: str) -> str:
    cleaned = _strip_leading_assistant_name(text).strip(" ,.!?:;")
    lowered = cleaned.lower()
    if not lowered:
        return ""

    task_control_reply = _direct_desktop_task_control(cleaned)
    if task_control_reply:
        return task_control_reply

    brightness_reply = _direct_brightness_control(cleaned)
    if brightness_reply:
        return brightness_reply

    volume_reply = _direct_volume_control(cleaned)
    if volume_reply:
        return volume_reply

    browser_reply = _direct_browser_playwright(cleaned)
    if browser_reply:
        return browser_reply

    visual_reply = _direct_visual_monitor(cleaned)
    if visual_reply:
        return visual_reply

    if re.fullmatch(r"(?:where is (?:the )?mouse|mouse position|where(?:'s| is) (?:the )?cursor|cursor position)", lowered):
        return _voice_tool_result(_pc({"action": "mouse_position"}))

    if re.fullmatch(r"(?:screen size|what(?:'s| is) (?:the )?screen size|how big is (?:the )?screen)", lowered):
        return _voice_tool_result(_pc({"action": "screen_size"}))

    if re.fullmatch(r"(?:active window|current window|what window is active|what(?:'s| is) (?:the )?active window)", lowered):
        return _voice_tool_result(_pc({"action": "active_window"}))

    match = re.search(r"\b(?:take|capture|save)\s+(?:a\s+)?(?:screenshot|screen shot)(?:\s+(?:to|in|as)\s+(.+))?$", cleaned, re.IGNORECASE)
    if match:
        return _voice_tool_result(_pc({"action": "screenshot", "target": (match.group(1) or "").strip()}))

    match = re.fullmatch(r"(?:look at|inspect|analyze|see|read)\s+(?:my\s+)?(?:screen|desktop)(?:\s+(.*))?", cleaned, re.IGNORECASE)
    if match:
        instruction = (match.group(1) or "").strip()
        return _voice_tool_result(_pc({"action": "inspect_screen", "instruction": instruction}))

    task_reply = _direct_desktop_task(cleaned)
    if task_reply:
        return task_reply

    match = re.fullmatch(r"(?:use|control)\s+(?:the\s+)?(?:screen|desktop)\s+(?:to\s+)?(.+)", cleaned, re.IGNORECASE)
    if match:
        instruction = match.group(1).strip()
        return _voice_tool_result(_pc({"action": "screen_step", "instruction": instruction}))

    match = re.fullmatch(r"(?:focus|activate|switch to|bring up)\s+(?:the\s+)?(.+?)(?:\s+window)?", cleaned, re.IGNORECASE)
    if match:
        target = match.group(1).strip(" .,!?:;")
        if target:
            return _voice_tool_result(_pc({"action": "focus_window", "target": target}))

    match = re.fullmatch(r"move\s+(?:the\s+)?(?:mouse|cursor)(?:\s+to)?\s+(.+)", cleaned, re.IGNORECASE)
    if match:
        inputs = {"action": "move_mouse"} | _desktop_point_inputs(match.group(1))
        return _voice_tool_result(_pc(inputs))

    match = re.fullmatch(r"drag\s+(?:the\s+)?(?:mouse|cursor)(?:\s+to)?\s+(.+)", cleaned, re.IGNORECASE)
    if match:
        inputs = {"action": "drag_mouse"} | _desktop_point_inputs(match.group(1))
        return _voice_tool_result(_pc(inputs))

    match = re.fullmatch(r"double\s+click(?:\s+(?:at|on)?\s*(.*))?", cleaned, re.IGNORECASE)
    if match:
        inputs = {"action": "double_click"} | _desktop_point_inputs(match.group(1) or "")
        return _voice_tool_result(_pc(inputs))

    match = re.fullmatch(r"right\s+click(?:\s+(?:at|on)?\s*(.*))?", cleaned, re.IGNORECASE)
    if match:
        inputs = {"action": "right_click"} | _desktop_point_inputs(match.group(1) or "")
        return _voice_tool_result(_pc(inputs))

    match = re.fullmatch(r"(?:left\s+)?click(?:\s+(?:at|on)?\s*(.*))?", cleaned, re.IGNORECASE)
    if match:
        inputs = {"action": "click"} | _desktop_point_inputs(match.group(1) or "")
        return _voice_tool_result(_pc(inputs))

    match = re.fullmatch(r"scroll(?:\s+(.+))?", cleaned, re.IGNORECASE)
    if match:
        target = (match.group(1) or "down").strip()
        return _voice_tool_result(_pc({"action": "scroll", "target": target}))

    match = re.fullmatch(r"(?:type|enter text|write text)\s+(.+)", cleaned, re.IGNORECASE)
    if match:
        text_to_type = match.group(1).strip()
        return _voice_tool_result(_pc({"action": "type_text", "text": text_to_type}))

    match = re.fullmatch(r"(?:press|hit|tap)\s+(.+)", cleaned, re.IGNORECASE)
    if match:
        key_text = match.group(1).strip()
        action = "hotkey" if _looks_like_hotkey(key_text) else "press_key"
        return _voice_tool_result(_pc({"action": action, "target": key_text}))

    match = re.fullmatch(r"hotkey\s+(.+)", cleaned, re.IGNORECASE)
    if match:
        return _voice_tool_result(_pc({"action": "hotkey", "target": match.group(1).strip()}))

    return ""


def _direct_browser_playwright(text: str) -> str:
    cleaned = text.strip(" ,.!?:;")
    lowered = cleaned.lower()
    if "playwright" not in lowered:
        return ""
    if re.fullmatch(r"(?:playwright|browser automation)\s+(?:status|available|installed)", lowered):
        try:
            from core import browser_playwright

            status = browser_playwright.available()
            return "Playwright is available." if status.get("available") else f"Playwright is not ready: {status.get('install_hint') or status.get('reason')}."
        except Exception as exc:
            return f"Playwright status failed: {exc}"
    match = re.fullmatch(r"(?:inspect|read|check)\s+(.+?)\s+with\s+playwright", cleaned, re.IGNORECASE)
    if match:
        return _voice_tool_result(_pc({"action": "playwright_inspect", "url": match.group(1).strip()}))
    match = re.fullmatch(r"(?:open|launch)\s+(.+?)\s+with\s+playwright", cleaned, re.IGNORECASE)
    if match:
        return _voice_tool_result(_pc({"action": "playwright_open", "url": match.group(1).strip()}))
    return ""


def _direct_visual_monitor(text: str) -> str:
    cleaned = text.strip(" ,.!?:;")
    lowered = cleaned.lower()
    visual_words = r"(?:visual monitor|vision monitor|live vision|watching|watch|camera monitor|screen monitor)"
    if not re.search(r"\b(?:visual|vision|watch|watching|camera|webcam|screen)\b", lowered):
        return ""
    source = "screen"
    if re.search(r"\b(?:both|screen and camera|camera and screen|webcam and screen)\b", lowered):
        source = "both"
    elif re.search(r"\b(?:camera|webcam)\b", lowered):
        source = "camera"
    if re.search(rf"\b(?:start|begin|turn on|enable|run)\b.*\b{visual_words}\b|\bwatch\s+(?:my\s+)?(?:screen|camera|webcam|desktop)\b", lowered):
        return _voice_tool_result(_pc({"action": "visual_monitor_start", "source": source}))
    if re.search(rf"\b(?:stop|turn off|disable|pause)\b.*\b{visual_words}\b|\bstop\s+watching\b", lowered):
        return _voice_tool_result(_pc({"action": "visual_monitor_stop"}))
    if re.search(rf"\b(?:status|state|what(?:'s| is))\b.*\b{visual_words}\b|\bvisual\s+monitor\s+status\b", lowered):
        return _voice_tool_result(_pc({"action": "visual_monitor_status"}))
    if re.search(r"\b(?:capture|snap|take)\b.*\b(?:visual|vision|frame|camera frame|screen frame)\b", lowered):
        analyze = bool(re.search(r"\b(?:analyze|describe|summarize)\b", lowered))
        return _voice_tool_result(_pc({"action": "visual_capture_once", "source": source, "analyze": analyze}))
    return ""


def _direct_desktop_task_control(text: str) -> str:
    cleaned = text.strip(" ,.!?:;")
    lowered = cleaned.lower()
    if not re.search(r"\b(?:desktop task|screen task|app task|desktop session|screen session)\b", lowered):
        return ""
    session_id = _session_id_from_text(lowered)
    inputs = {"session_id": session_id} if session_id else {}
    if re.search(r"\b(?:pause|hold|stop for now)\b", lowered):
        return _voice_tool_result(_pc({"action": "desktop_task_pause"} | inputs))
    if re.search(r"\b(?:resume|continue|restart)\b", lowered):
        return _voice_tool_result(_pc({"action": "desktop_task_resume"} | inputs))
    if re.search(r"\b(?:confirm|approve|authorize|yes)\b", lowered):
        return _voice_tool_result(_pc({"action": "desktop_task_confirm"} | inputs))
    if re.search(r"\b(?:cancel|abort|stop)\b", lowered):
        return _voice_tool_result(_pc({"action": "desktop_task_cancel"} | inputs))
    return ""


def _direct_desktop_task(text: str) -> str:
    cleaned = text.strip(" ,.!?:;")
    named_app_match = re.fullmatch(
        r"(?:use|operate|control|navigate|drive)\s+(?:the\s+)?(.+?)\s+(?:to|and)\s+(.+)",
        cleaned,
        re.IGNORECASE,
    )
    if named_app_match:
        app_candidate = named_app_match.group(1).strip(" .,!?:;")
        goal = named_app_match.group(2).strip(" .,!?:;")
        app_target = _app_name(app_candidate)
        if app_target and goal:
            open_result = _pc({"action": "open_app", "target": app_target})
            if not re.search(r"\b(?:could not|blocked|disabled|permission required|access denied)\b", open_result, re.IGNORECASE):
                return _voice_tool_result(_pc({"action": "desktop_task", "instruction": f"Use {app_candidate} to {goal}"}))
            return _voice_tool_result(open_result)
    patterns = (
        r"(?:operate|navigate|control)\s+(?:the\s+)?(?:app|application|window|screen|desktop|computer|pc|browser|chrome|gmail)\s+(?:to\s+)?(.+)",
        r"(?:use)\s+(?:the\s+)?(?:app|application|window|screen|desktop|computer|pc|browser|chrome|gmail)\s+(?:to\s+)?(.+)",
        r"(?:perform|complete|finish|do)\s+(?:the\s+)?(.+?)\s+(?:on|in|using)\s+(?:the\s+)?(?:screen|desktop|app|application|window|browser|chrome|gmail)",
        r"(?:take over|drive)\s+(?:the\s+)?(?:screen|desktop|app|browser|chrome|gmail)\s+(?:and\s+)?(.+)",
    )
    for pattern in patterns:
        match = re.fullmatch(pattern, cleaned, re.IGNORECASE)
        if match:
            instruction = match.group(1).strip(" .,!?:;")
            if instruction:
                return _voice_tool_result(_pc({"action": "desktop_task", "instruction": instruction}))
    return ""


def _session_id_from_text(text: str) -> int:
    match = re.search(r"(?:#|session\s+|task\s+)(\d+)", text, re.IGNORECASE)
    return int(match.group(1)) if match else 0


def _direct_brightness_control(text: str) -> str:
    cleaned = text.strip(" ,.!?:;")
    lowered = cleaned.lower()
    if not re.search(r"\b(brightness|screen brightness|display brightness)\b", lowered):
        return ""
    if re.search(r"\b(?:what(?:'s| is)|check|get|read|current|meet|meets)\b.*\bbrightness\b", lowered) or re.fullmatch(
        r"(?:screen\s+|display\s+)?brightness", lowered
    ):
        return _voice_tool_result(_pc({"action": "get_brightness"}))
    if re.search(r"\b(?:max|maximum|full|highest|100|100 percent|one hundred percent)\b", lowered):
        return _voice_tool_result(_pc({"action": "set_brightness", "target": "100"}))
    if re.search(r"\b(?:min|minimum|zero|0|0 percent|darkest)\b", lowered):
        return _voice_tool_result(_pc({"action": "set_brightness", "target": "0"}))
    match = re.search(r"\b(?:set|change|put|make|turn)\s+(?:my\s+|the\s+)?(?:screen\s+|display\s+)?brightness\s+(?:to|at)\s+(\d{1,3})\s*(?:%|percent)?\b", lowered)
    if match:
        return _voice_tool_result(_pc({"action": "set_brightness", "target": match.group(1)}))
    percent = _explicit_percent_target(lowered)
    if percent is not None:
        return _voice_tool_result(_pc({"action": "set_brightness", "target": str(percent)}))
    if re.search(r"\b(?:increase|raise|turn up|brighter|brighten)\b", lowered):
        return _voice_tool_result(_pc({"action": "adjust_brightness", "direction": "up"}))
    if re.search(r"\b(?:reduce|reduced|decrease|lower|turn down|dim|dimmer|darker)\b", lowered):
        return _voice_tool_result(_pc({"action": "adjust_brightness", "direction": "down"}))
    return ""


def _direct_volume_control(text: str) -> str:
    cleaned = text.strip(" ,.!?:;")
    lowered = cleaned.lower()
    if not _looks_like_volume_request(lowered):
        return ""
    if re.search(r"\bunmute\b", lowered):
        return _voice_tool_result(_pc({"action": "mute_volume", "target": "unmute"}))
    if re.search(r"\b(?:mute|silence)\b", lowered):
        return _voice_tool_result(_pc({"action": "mute_volume", "target": "mute"}))
    if re.search(r"\b(?:what(?:'s| is)|check|get|read|current|meet|meets)\b.*\b(?:pc\s+)?(?:volume|sound|audio)\b", lowered) or re.fullmatch(
        r"(?:pc\s+)?(?:volume|sound|audio)", lowered
    ):
        return _voice_tool_result(_pc({"action": "get_volume"}))
    if re.search(r"\b(?:max|maximum|full|highest|100|100 percent|one hundred percent)\b", lowered):
        return _voice_tool_result(_pc({"action": "set_volume", "target": "100"}))
    if re.search(r"\b(?:min|minimum|zero|0|0 percent|silent)\b", lowered):
        return _voice_tool_result(_pc({"action": "set_volume", "target": "0"}))
    match = re.search(r"\b(?:set|change|put|make|turn)\s+(?:my\s+|the\s+)?(?:volume|sound|audio)\s+(?:to|at)\s+(\d{1,3})\s*(?:%|percent)?\b", lowered)
    if match:
        return _voice_tool_result(_pc({"action": "set_volume", "target": match.group(1)}))
    percent = _explicit_percent_target(lowered)
    if percent is not None:
        return _voice_tool_result(_pc({"action": "set_volume", "target": str(percent)}))
    if re.search(r"\b(?:increase|raise|turn up|volume up|louder)\b", lowered):
        return _voice_tool_result(_pc({"action": "adjust_volume", "direction": "up", "presses": 5}))
    if re.search(r"\b(?:reduce|reduced|decrease|lower|turn down|volume down|quieter)\b", lowered):
        return _voice_tool_result(_pc({"action": "adjust_volume", "direction": "down", "presses": 5}))
    return ""


def _guard_unverified_pc_claim(user_text: str, reply_text: str) -> str:
    user_lowered = (user_text or "").lower()
    reply_lowered = (reply_text or "").lower()
    if _looks_like_volume_request(user_lowered) and re.search(
        r"\b(?:volume|sound|audio|speaker)s?\b.*\b(?:set|increased|decreased|raised|lowered|muted|unmuted|changed|adjusted)\b|\bvolume\s+(?:muted|unmuted|set|increased|decreased)\b",
        reply_lowered,
    ):
        direct = _direct_volume_control(user_text)
        if direct:
            return direct
        return "I did not change the volume because I could not map that to a safe volume action."
    if re.search(r"\b(?:brightness|screen brightness|display brightness)\b", user_lowered) and re.search(
        r"\bbrightness\b.*\b(?:set|increased|decreased|raised|lowered|changed|adjusted|reduced)\b",
        reply_lowered,
    ):
        direct = _direct_brightness_control(user_text)
        if direct:
            return direct
        return "I did not change the brightness because I could not map that to a safe brightness action."
    return ""


def _looks_like_volume_request(text: str) -> bool:
    lowered = (text or "").lower()
    return bool(re.search(r"\b(volume|sound|audio|speaker|speakers|loudness)\b", lowered))


def _explicit_percent_target(text: str) -> int | None:
    lowered = (text or "").lower()
    match = re.search(r"\b(?:to|at)\s+(\d{1,3})\s*(?:%|percent)?\b", lowered)
    if not match:
        match = re.search(r"\b(\d{1,3})\s*(?:%|percent)\b", lowered)
    if not match:
        return None
    return max(0, min(100, int(match.group(1))))


def _direct_web_search(text: str) -> str:
    match = re.search(r"\b(?:search|google|look up|find online|browse)\s+(?:for\s+)?(.+)$", text, re.IGNORECASE)
    if not match:
        return ""
    query = match.group(1).strip(" .,!?:;")
    if not query:
        return ""
    result = web_search.execute({"action": "search", "query": query})
    if result.startswith("- "):
        first = result.splitlines()[0].lstrip("- ").strip()
        title = first.split(":", 1)[0].strip()
        return f"I found: {title}."
    return _voice_tool_result(result)


def _direct_draft(text: str) -> str:
    match = re.search(r"\b(?:draft|write|compose)\s+(?:a\s+)?(?:message|email|reply|text)\b(?:\s+(.+))?$", text, re.IGNORECASE)
    if not match:
        return ""
    details = (match.group(1) or "").strip(" .,!?:;")
    if not details:
        return "Tell me who it is for and what it should say."
    prompt = (
        "Draft this message in a natural tone. Keep it concise and ready to send. "
        "Return only the draft text, no preamble:\n\n"
        + details
    )
    draft = llm.ask_simple(prompt, retries=1) or ""
    return _voice_tool_result(draft or "I could not draft that right now.")


def _direct_project_ideas(text: str) -> str:
    lowered = text.lower()
    if not re.search(r"\b(?:idea|ideas|what\s+to\s+build|build\s+next|project\s+to\s+build|app\s+idea|startup\s+idea)\b", lowered):
        return ""
    patterns = (
        r"(?:what\s+should\s+i\s+build\s+next|what\s+to\s+build\s+next)(?:\s+(?:for|about|around)\s+(?P<context>.+))?",
        r"(?:give\s+me\s+an?\s+idea\s+on\s+what\s+to\s+build\s+next)(?:\s+(?:for|about|around)\s+(?P<context>.+))?",
        r"(?:give\s+me|suggest|recommend|find|research|look\s+for)\s+(?:some\s+|an?\s+|the\s+)?(?:project\s+|app\s+|startup\s+|software\s+)?ideas?(?:\s+(?:on|for|about|around)\s+(?P<context>.+))?",
    )
    for pattern in patterns:
        match = re.fullmatch(pattern, text, flags=re.IGNORECASE)
        if not match:
            continue
        context = _clean_text((match.groupdict().get("context") or "AI-assisted everyday tools for individuals, small teams, and SMBs"))
        if context.lower() in {"what to build next", "what i should build next"}:
            context = "AI-assisted everyday tools for individuals, small teams, and SMBs"
        result = _power(
            {
                "action": "project_ideas_research",
                "context": context,
                "audience": "individuals, small teams, and SMBs",
                "root": str(resolve_coding_root()),
                "limit": 5,
                "max_sources": 8,
            }
        )
        return _voice_tool_result(result)
    return ""


def _direct_build_request(text: str) -> str:
    cleaned = text.strip()
    if not cleaned:
        return ""
    match = re.match(
        r"^(?:friday[, ]+)?(?:i\s+want\s+you\s+to|i\s+need\s+you\s+to|can\s+you|could\s+you|please)?\s*build\s+(?:me\s+)?(?:this|the\s+following|an?|a\s+solution|a\s+tool|a\s+web\s+app|an\s+app|software|platform)?\s*:?\s*(.+)$",
        cleaned,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if not match:
        return ""
    request = _clean_text(match.group(1))
    if not request or request.lower() in {"this", "it", "that"}:
        return "Tell me what you want built, and I will turn it into a guarded coding task instead of opening an app."
    if not _looks_like_software_build_request(request):
        return ""
    result = _power({"action": "autonomous_coding", "request": _normalize_build_request(request), "root": str(resolve_coding_root()), "risk_level": "medium"})
    return _voice_tool_result(result)


def _normalize_build_request(request: str) -> str:
    cleaned = _clean_text(request)
    if not cleaned:
        return ""
    lowered = cleaned.lower()
    if re.match(r"^(?:build|create|make|develop|scaffold|spin\s+up|implement|code|program|put\s+together|set\s+up)\b", lowered):
        return cleaned
    subject = re.sub(r"^(?:an?|the)\s+", "", cleaned, flags=re.IGNORECASE).strip() or cleaned
    if re.search(r"\b(?:dashboard|portal|website|site|frontend)\b", lowered) and not re.search(r"\b(?:web[-\s]?app|next(?:\.js|js)?)\b", lowered):
        return f"Build a web-app for {subject}"
    if re.search(r"\b(?:mobile|flutter|android|ios)\b", lowered) and not re.search(r"\b(?:screenshot|screenshots|viewport|viewports|responsive|browser|desktop\s+and\s+mobile|mobile\s+and\s+desktop)\b", lowered):
        return f"Build a mobile app for {subject}"
    if re.search(r"\b(?:backend|api|server|service|microservice)\b", lowered):
        return f"Build a backend for {subject}"
    return f"Build {cleaned}"


def _looks_like_software_build_request(text: str) -> bool:
    return bool(
        re.search(
            r"\b(?:ai|app|application|api|backend|dashboard|frontend|model|platform|predictive|software|solution|system|tool|web|website|workflow)\b",
            text.lower(),
        )
    )


def _direct_coding(text: str) -> str:
    lowered = text.lower()
    if not re.search(r"\b(?:write|create|build|debug|explain|fix)\s+(?:some\s+)?(?:code|script|function|program|software|app)\b|^code\b", lowered):
        return ""
    return _voice_tool_result(coding_tool.execute({"action": "qa", "question": text}))


def _direct_file_request(text: str) -> str:
    if re.search(
        r"\bcan\s+you\s+see\s+(?:my\s+)?(?:workspace|project|current folder|current directory)\??$",
        text,
        re.IGNORECASE,
    ):
        if bool(config_value("pc_trusted_mode_enabled", False)) and bool(config_value("pc_allow_arbitrary_paths", False)):
            return "I can access files and folders on this laptop, and I can control the visible desktop when you ask."
        return "I can access files in this project folder, but broad desktop access is disabled."

    if re.search(
        r"\bcan\s+you\s+see\s+(?:the\s+)?file(?:\s+(?:opened|open))?(?:\s+on\s+my\s+(?:workspace|vs|v s|visual studio code|editor))?\??$",
        text,
        re.IGNORECASE,
    ):
        return "I cannot see your open editor tab directly. Tell me the file name or path, and I can read it."

    if re.search(r"\bwhat\s+does\s+(?:the\s+)?file(?:\s+say)?\??$", text, re.IGNORECASE):
        return "Which file should I read?"

    match = re.search(r"\b(?:list|show)\s+(?:the\s+)?files(?:\s+in\s+(.+))?$", text, re.IGNORECASE)
    if match:
        target = _spoken_path(match.group(1) or "home")
        result = _pc({"action": "list_files", "target": target})
        return _voice_tool_result(_summarize_file_listing(result))

    match = re.search(r"\b(?:read|open)\s+(?:the\s+)?file\s+(.+)$", text, re.IGNORECASE)
    if match:
        target = _spoken_path(match.group(1))
        result = _pc({"action": "read_file", "target": target})
        return _voice_tool_result(_summarize_read_file(result))

    match = re.search(r"\breview\s+(?:the\s+)?file\s+(.+)$", text, re.IGNORECASE)
    if match:
        target = _spoken_path(match.group(1))
        return _voice_tool_result(coding_tool.execute({"action": "review", "file_path": target}))
    return ""


def _voice_tool_result(result: str) -> str:
    text = str(result or "").strip()
    if not text:
        return "I did not get a result to verify."
    if "\n" not in text and len(text) <= 180:
        return text
    first_line = text.splitlines()[0].strip()
    if first_line:
        return first_line[:180]
    return text[:180]


def _summarize_file_listing(result: str) -> str:
    if not result or result.startswith(("Access denied", "Folder not found")):
        return result
    entries = [line.strip() for line in result.splitlines() if line.strip()]
    if not entries:
        return "Folder is empty."
    preview = ", ".join(entries[:5])
    suffix = "" if len(entries) <= 5 else f", and {len(entries) - 5} more"
    return f"I found {len(entries)} item{'s' if len(entries) != 1 else ''}: {preview}{suffix}."


def _summarize_read_file(result: str) -> str:
    if not result or result.startswith(("Access denied", "File not found", "Cannot")):
        return result
    return result[:300]


def _clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _record_autobiographical_command_event(user_text: str, reply: str, action_type: str, success: bool) -> None:
    lowered_user = str(user_text or "").lower()
    lowered_reply = str(reply or "").lower()
    if not success:
        _record_autobiography("failure", "Command did not succeed", f"User: {user_text}. Reply: {reply}", importance=0.8)
        return
    if "self-update" in lowered_reply or "self update" in lowered_reply:
        _record_autobiography("self_update", "Self-update workflow event", reply, importance=0.8)
    elif "permission updated" in lowered_reply:
        _record_autobiography("safety_rule", "Safety permission changed", reply, importance=0.75)
    elif "goal " in lowered_reply and "created" in lowered_reply:
        _record_autobiography("goal", "Goal changed", reply, importance=0.7)
    elif action_type == "guarded_direct_command":
        _record_autobiography("honesty_gate", "Blocked unsupported success claim", reply, importance=0.85, user_text=user_text)
    elif any(term in lowered_user for term in ("you lied", "didn't work", "did not work", "i said", "wrong")):
        _record_autobiography("user_correction", "User corrected Friday", f"User: {user_text}. Reply: {reply}", importance=0.85)


def _record_autobiography(event_type: str, title: str, summary: str = "", *, importance: float = 0.65, **metadata: Any) -> None:
    try:
        autobiographical_memory.record_event(
            event_type,
            title,
            summary,
            source="orchestrator",
            importance=importance,
            metadata=metadata,
        )
    except Exception:
        return


def _looks_like_path_request(spoken: str) -> bool:
    target = (spoken or "").strip().lower()
    if target in {
        "home",
        "desktop",
        "downloads",
        "documents",
        "pictures",
        "music",
        "videos",
        "workspace",
        "project",
        "current folder",
        "current directory",
    }:
        return True
    return ":" in spoken or "\\" in spoken or "/" in spoken or Path(spoken).suffix != ""


def _looks_like_url(spoken: str) -> bool:
    target = (spoken or "").strip().lower()
    return target.startswith(("http://", "https://")) or "." in target and " " not in target


def _desktop_point_inputs(spoken: str) -> dict[str, Any]:
    text = (spoken or "").strip()
    if not text:
        return {}
    numbers = [int(value) for value in re.findall(r"-?\d+", text)]
    if len(numbers) >= 2:
        return {"x": numbers[0], "y": numbers[1]}
    return {"target": text}


def _looks_like_hotkey(spoken: str) -> bool:
    words = set(re_split_words(spoken))
    modifiers = {"ctrl", "control", "alt", "shift", "win", "windows", "command"}
    return bool(words & modifiers) and len(words) >= 2


def re_split_words(text: str) -> list[str]:
    return [part.strip() for part in "".join(ch if ch.isalnum() else " " for ch in text.lower()).split()]


def _app_name(spoken: str) -> str:
    target = re.sub(r"[^\w\s.-]", " ", spoken or "").strip().lower()
    target = re.sub(r"\s+", " ", target)
    aliases = {
        "browser": "chrome",
        "google": "chrome",
        "google chrome": "chrome",
        "chrome browser": "chrome",
        "note pad": "notepad",
        "visual studio code": "vscode",
        "vs code": "vscode",
        "vscode": "vscode",
        "file explorer": "explorer",
        "windows explorer": "explorer",
        "camera": "camera",
        "windows camera": "camera",
        "webcam": "camera",
        "google mail": "gmail",
        "g mail": "gmail",
        "g-mail": "gmail",
        "gmail": "gmail",
        "gym": "gmail",
        "jim": "gmail",
        "jimmy": "gmail",
        "female": "gmail",
        "email": "gmail",
        "mail": "gmail",
        "figma": "figma",
        "figma app": "figma",
    }
    if target in aliases:
        return aliases[target]
    allowed = config_value("allowed_apps", {})
    if isinstance(allowed, dict) and target in {str(name).lower() for name in allowed}:
        return target
    return ""


def _spoken_path(spoken: str) -> str:
    text = (spoken or "").strip().strip('"')
    lowered = text.lower()
    home = Path.home()
    known = {
        "home": home,
        "desktop": home / "Desktop",
        "downloads": home / "Downloads",
        "documents": home / "Documents",
        "second brain": Path.cwd(),
        "project": Path.cwd(),
        "current folder": Path.cwd(),
        "current directory": Path.cwd(),
    }
    if lowered in known:
        return str(known[lowered])
    if lowered.startswith("desktop "):
        return str(home / "Desktop" / text.split(" ", 1)[1])
    if ":" in text or "\\" in text or "/" in text:
        return text
    return str((Path.cwd() / text).resolve())


def _remembered_name() -> str:
    for fact in reversed(memory.recall("user's name", n=5)):
        match = re.search(r"user'?s name is ([a-z][a-z .'-]{1,40})", fact, re.IGNORECASE)
        if match:
            return match.group(1).strip()
    return ""


def _confirm(tool_name: str) -> bool:
    for attempt in range(2):
        speak(f"Are you sure you want to run {tool_name}?")
        answer = (record_and_transcribe() or "").lower()
        if "yes" in answer or "confirm" in answer or "do it" in answer:
            return True
        if any(word in answer for word in ["no", "cancel", "stop", "abort", "wait"]):
            return False
        if attempt == 0:
            speak("I did not catch that. Please say yes or no.")
    return False


def _content_blocks(response: Any) -> list[Any]:
    if response is None:
        return []
    if isinstance(response, dict):
        return response.get("content", [])
    return list(getattr(response, "content", []) or [])


def _block_value(block: Any, key: str) -> Any:
    if isinstance(block, dict):
        return block.get(key)
    return getattr(block, key, None)

