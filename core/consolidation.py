"""Nightly memory consolidation and forgetting-curve maintenance."""

from __future__ import annotations

import datetime as dt
import json
import re
import time
from typing import Any

try:
    from apscheduler.schedulers.background import BackgroundScheduler
except Exception:  # pragma: no cover - optional runtime fallback
    BackgroundScheduler = None

from core import episodic_store, knowledge_graph, memory, skill_library
from core.config import config_value

_SCHEDULER: Any = None


def consolidate(agent_id: str = "jarvis") -> dict[str, Any]:
    start = time.perf_counter()
    events = episodic_store.today_events(agent_id=agent_id, limit=int(config_value("consolidation_event_limit", 200)))
    facts = _extract_facts(events)
    skills = _extract_procedural_skills(events)
    facts_limit = int(config_value("consolidation_fact_limit", 10))
    stored = 0
    for fact in facts[:facts_limit]:
        memory.remember_fact(fact, user_id=agent_id, metadata={"source": "consolidation"})
        knowledge_graph.add_edge(agent_id.title(), "CONSOLIDATED", fact, source="episodic_store")
        stored += 1
    decay = memory.decay_activation_scores()
    duration = time.perf_counter() - start
    result = {
        "events_processed": len(events),
        "facts_extracted": stored,
        "skills_extracted": skills,
        "memories_archived": int(decay.get("archived", 0)),
        "duration_seconds": round(duration, 3),
    }
    _log(
        "INFO",
        "[CONSOLIDATION] "
        f"events_processed={result['events_processed']} facts_extracted={stored} "
        f"skills_extracted={skills} memories_archived={result['memories_archived']} duration={duration:.2f}s",
    )
    return result


def start_scheduler() -> Any:
    global _SCHEDULER
    if not bool(config_value("memory_consolidation_enabled", True)):
        return None
    if BackgroundScheduler is None:
        _log("WARNING", "[CONSOLIDATION] APScheduler unavailable; nightly job not scheduled.")
        return None
    if _SCHEDULER is not None and getattr(_SCHEDULER, "running", False):
        return _SCHEDULER
    hour = int(config_value("memory_consolidation_hour", 2))
    minute = int(config_value("memory_consolidation_minute", 0))
    _SCHEDULER = BackgroundScheduler(daemon=True)
    _SCHEDULER.add_job(consolidate, "cron", hour=hour, minute=minute, id="memory_consolidation", replace_existing=True)
    _SCHEDULER.start()
    _log("INFO", f"[CONSOLIDATION] scheduled hour={hour:02d}:{minute:02d}")
    return _SCHEDULER


def stop_scheduler() -> None:
    global _SCHEDULER
    if _SCHEDULER is None:
        return
    try:
        if getattr(_SCHEDULER, "running", False):
            _SCHEDULER.shutdown(wait=False)
    finally:
        _SCHEDULER = None


def _extract_facts(events: list[dict[str, Any]]) -> list[str]:
    llm_facts = _extract_facts_with_llm(events) if bool(config_value("consolidation_use_llm", False)) else []
    if llm_facts:
        return _dedupe(llm_facts)
    facts: list[str] = []
    for event in events:
        action = str(event.get("action_type") or "action")
        inputs = event.get("inputs")
        outputs = event.get("outputs")
        if action in {"command", "direct_command", "llm_text", "tool_command"}:
            user_text = _field(inputs, "user_text")
            reply = _field(outputs, "reply")
            if user_text and reply and _worth_remembering(user_text, reply):
                facts.append(f"User asked '{_short(user_text, 80)}' and Friday answered '{_short(reply, 120)}'.")
        elif action == "tool_use":
            tool = _field(inputs, "tool") or _field(inputs, "tool_name")
            result = _field(outputs, "result")
            if tool and result:
                facts.append(f"Friday used {tool} and got result '{_short(result, 120)}'.")
    return _dedupe(facts)


def _extract_procedural_skills(events: list[dict[str, Any]]) -> int:
    created = 0
    for event in events:
        if event.get("action_type") != "agent_task":
            continue
        inputs = event.get("inputs") if isinstance(event.get("inputs"), dict) else {}
        outputs = event.get("outputs") if isinstance(event.get("outputs"), dict) else {}
        task = inputs.get("task") if isinstance(inputs.get("task"), dict) else {}
        title = str(task.get("title") or "")
        summary = str(outputs.get("summary") or "")
        agent_id = str(outputs.get("agent_id") or event.get("agent_id") or "jarvis")
        if title and summary and skill_library.record_example(agent_id, title, summary):
            created += 1
    return created


def _extract_facts_with_llm(events: list[dict[str, Any]]) -> list[str]:
    if not events:
        return []
    try:
        from core import llm

        compact_events = json.dumps(events[:50], ensure_ascii=True, default=str)
        prompt = (
            "From these assistant events, extract 5-10 durable facts worth remembering long-term. "
            "Return only a JSON list of short declarative strings.\n\n"
            + compact_events
        )
        raw = llm.ask_simple(prompt, retries=1) or ""
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            return [str(item).strip() for item in parsed if str(item).strip()]
    except Exception:
        return []
    return []


def _field(value: Any, key: str) -> str:
    if isinstance(value, dict):
        return str(value.get(key) or "").strip()
    return ""


def _worth_remembering(user_text: str, reply: str) -> bool:
    combined = f"{user_text} {reply}".lower()
    if any(marker in combined for marker in ["remember", "my name is", "call me", "favorite", "prefer", "workspace", "project"]):
        return True
    if re.search(r"\b(?:opened|created|wrote|fixed|reviewed|sent|saved|installed|configured)\b", combined):
        return True
    return False


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for item in items:
        cleaned = " ".join(str(item).strip().split())
        if not cleaned:
            continue
        key = cleaned.lower()
        if key not in seen:
            seen.add(key)
            output.append(cleaned)
    return output


def _short(text: str, limit: int) -> str:
    text = " ".join(str(text or "").split())
    return text if len(text) <= limit else text[: limit - 3] + "..."


def _log(level: str, message: str) -> None:
    try:
        from output.display import log

        log(level, message)
    except Exception:
        return
