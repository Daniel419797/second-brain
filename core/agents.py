"""Free/local v2 agent roster and task execution helpers."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from core import agent_blackboard, agent_lifecycle, agent_memory, agent_quality_manager, agent_thought_bus, competence, llm, memory, research, skill_library, task_contracts, task_queue
from core.config import config_value


@dataclass(frozen=True)
class AgentProfile:
    id: str
    name: str
    purpose: str
    keywords: tuple[str, ...]


ROSTER: tuple[AgentProfile, ...] = (
    AgentProfile("ceo", "CEO / Friday Core", "Goal decomposition and coordination.", ("goal", "plan", "coordinate", "strategy")),
    AgentProfile("product_manager", "Product Manager", "Requirements, roadmap, and prioritization.", ("requirements", "roadmap", "feature", "product")),
    AgentProfile("project_manager", "Project Manager", "Task tracking, blockers, schedules, and progress reports.", ("schedule", "deadline", "status", "blocker", "sprint")),
    AgentProfile("senior_developer", "Senior Developer", "Architecture, implementation plans, and code quality.", ("code", "build", "implement", "refactor", "architecture")),
    AgentProfile("junior_developer", "Junior Developer", "Small implementation tasks, tests, and documentation.", ("test", "docs", "small fix", "unit")),
    AgentProfile("devops", "DevOps / Infrastructure", "Local automation, scripts, CI, and deployment plans.", ("deploy", "docker", "ci", "server", "infrastructure")),
    AgentProfile("cybersecurity_analyst", "Cybersecurity Analyst", "Defensive security reviews and safe hardening.", ("security", "vulnerability", "audit", "threat")),
    AgentProfile("ethical_hacker", "Ethical Hacker", "Guarded authorized-target security testing only.", ("pentest", "ctf", "exploit", "authorized")),
    AgentProfile("ui_ux_designer", "UI/UX Designer", "Interfaces, flows, accessibility, and design systems.", ("ui", "ux", "design", "wireframe", "frontend")),
    AgentProfile("brand_content_designer", "Brand & Content Designer", "Copy, naming, brand, and presentation assets.", ("brand", "copy", "marketing", "content")),
    AgentProfile("research_analyst", "Research Analyst", "Research, summaries, and knowledge synthesis.", ("research", "find", "study", "summarize", "learn")),
    AgentProfile("data_scientist", "Data Scientist / ML", "Data analysis, metrics, and ML plans.", ("data", "analysis", "chart", "model", "dataset")),
    AgentProfile("qa_engineer", "QA Engineer", "Test plans, regression checks, and acceptance criteria.", ("qa", "quality", "bug", "regression", "test")),
    AgentProfile("code_reviewer", "Code Reviewer", "Code review, risks, and maintainability feedback.", ("review", "style", "bug", "quality")),
)


def roster() -> list[dict[str, str]]:
    return [{"id": agent.id, "name": agent.name, "purpose": agent.purpose} for agent in _all_profiles()]


def get_agent(agent_id: str) -> AgentProfile:
    normalized = normalize_agent_id(agent_id)
    for agent in _all_profiles():
        if agent.id == normalized:
            return agent
    return _default_agent()


def normalize_agent_id(value: str) -> str:
    text = " ".join(str(value or "").lower().replace("-", " ").split())
    aliases = {
        "pm": "product_manager",
        "product": "product_manager",
        "project": "project_manager",
        "senior dev": "senior_developer",
        "senior developer": "senior_developer",
        "junior dev": "junior_developer",
        "junior developer": "junior_developer",
        "dev ops": "devops",
        "security": "cybersecurity_analyst",
        "cybersecurity": "cybersecurity_analyst",
        "hacker": "ethical_hacker",
        "designer": "ui_ux_designer",
        "research": "research_analyst",
        "researcher": "research_analyst",
        "data": "data_scientist",
        "qa": "qa_engineer",
        "reviewer": "code_reviewer",
        "code reviewer": "code_reviewer",
        "friday": "ceo",
        "ceo": "ceo",
    }
    if text in aliases:
        return aliases[text]
    compact = text.replace(" ", "_")
    ids = {agent.id for agent in _all_profiles()}
    return compact if compact in ids else compact


def choose_agent(task_text: str) -> str:
    text = str(task_text or "").lower()
    best_score = 0
    best_agent = _default_agent()
    for agent in _all_profiles():
        score = sum(1 for keyword in agent.keywords if keyword in text)
        if score > best_score:
            best_score = score
            best_agent = agent
    if best_score <= 0:
        try:
            quality = agent_quality_manager.best_agent(_infer_task_type(text))
            if quality and quality.get("agent_id") in {agent.id for agent in _all_profiles()}:
                return str(quality["agent_id"])
        except Exception:
            pass
    return best_agent.id


def create_task(
    title: str,
    *,
    description: str = "",
    agent_id: str = "",
    priority: int = 5,
    scheduled_at: Any | None = None,
) -> int:
    selected_agent = normalize_agent_id(agent_id) if agent_id else choose_agent(f"{title} {description}")
    if selected_agent not in {agent.id for agent in _all_profiles()}:
        selected_agent = choose_agent(f"{title} {description}")
    task_id = task_queue.create_task(
        title,
        description=description or title,
        agent_id=selected_agent,
        priority=priority,
        input_data={"source": "user"},
        scheduled_at=scheduled_at,
    )
    try:
        task = task_queue.get_task(task_id)
        if task:
            task_contracts.ensure_contract(task)
    except Exception:
        pass
    if selected_agent == "ethical_hacker":
        task_queue.update_status(
            task_id,
            "blocked",
            output={"requires": "CEO approval plus explicit user approval before execution.", "ceo_approved": True, "user_approved": False},
        )
        task_queue.post_message(task_id, "security", "Ethical hacker task blocked until explicit user approval.")
    return task_id


def approve_guarded_task(task_id: int, confirmation: str) -> bool:
    task = task_queue.get_task(task_id)
    if not task or task.get("agent_id") != "ethical_hacker" or task.get("status") != "blocked":
        return False
    phrase = f"i authorize task {task_id}"
    if phrase not in str(confirmation or "").lower():
        return False
    task_queue.update_status(
        task_id,
        "pending",
        output={"requires": "approved", "ceo_approved": True, "user_approved": True},
    )
    task_queue.post_message(task_id, "security", "User explicitly approved guarded ethical hacker task.")
    return True


def run_task(task: dict[str, Any]) -> dict[str, Any]:
    agent = get_agent(str(task.get("agent_id") or "research_analyst"))
    title = str(task.get("title") or "")
    description = str(task.get("description") or title)
    task_text = f"{title}\n{description}"
    topics = competence.infer_topics(task_text)
    competence_note = competence.prompt_summary(agent.id, task_text)
    skill_note = skill_library.prompt_prefix(task_text, agent_id=agent.id)
    notebook_note = agent_memory.context_for_agent(agent.id, task_text, limit=int(config_value("agent_memory_prompt_limit", 5)))
    thought_note = agent_thought_bus.context_for_agent(
        agent.id,
        task_text,
        task_id=int(task.get("id") or 0) or None,
        limit=int(config_value("agent_thought_bus_prompt_limit", 6)),
    ) if bool(config_value("agent_thought_bus_enabled", True)) else ""
    contract_note = _contract_note(task)
    blackboard_note = agent_blackboard.task_context(int(task.get("id") or 0), limit=int(config_value("agent_blackboard_prompt_limit", 5))) if task.get("id") else ""
    research_note = _research_note(agent, task, task_text)
    prompt = _agent_prompt(
        agent,
        title,
        description,
        competence_note=competence_note,
        skill_note=skill_note,
        notebook_note=notebook_note,
        thought_note=thought_note,
        contract_note=contract_note,
        blackboard_note=blackboard_note,
        research_note=research_note,
        peer_note=_agent_directory_note(agent.id),
    )
    output = ""
    used_llm = False
    provider_chain = _agent_provider_chain(agent.id)
    if bool(config_value("v2_agent_use_llm", True)):
        output = _ask_agent_text(agent.id, prompt, provider_chain=provider_chain) or ""
        used_llm = bool(output)
    if not output:
        output = _local_fallback_output(agent, title, description)
    spawned_subtasks = _spawn_subtasks(task, agent, title, description, output)
    spawned_subtasks.extend(_spawn_agent_questions(task, agent, title, description, output))
    structured_feedback = _structured_review_feedback(agent, title, output)
    if structured_feedback:
        _store_review_feedback(title, structured_feedback)
    _post_result_thought(task, agent, output, topics, spawned_subtasks)
    skill_library.record_example(agent.id, title, output, tags=topics)
    _store_agent_notebook_memory(agent, title, output, topics)
    competence.record_result(agent.id, task_text, success_score=1.0 if output else 0.0)
    memory.remember_fact(f"{agent.name} completed task '{title}' with output: {output[:240]}", metadata={"source": "agent_task", "agent_id": agent.id})
    return {
        "agent_id": agent.id,
        "agent_name": agent.name,
        "summary": output.strip(),
        "mode": "llm" if used_llm else "local",
        "provider_chain": provider_chain if used_llm else [],
        "topics": topics,
        "researched": bool(research_note),
        "spawned_subtasks": spawned_subtasks,
        "structured_feedback": structured_feedback,
    }


def format_roster() -> str:
    agents = ", ".join(agent.name for agent in _all_profiles())
    return f"Team roster: {agents}."


def agent_provider_chain(agent_id: str) -> list[str]:
    return _agent_provider_chain(agent_id)


def api_agent_mode_enabled() -> bool:
    """Return True when hosted providers can carry multi-agent work off the CPU."""
    if not bool(config_value("v2_api_agent_mode_enabled", False)):
        return False
    providers = _configured_online_provider_text()
    return llm.online_provider_available(providers)


def default_worker_count() -> int:
    """Default background worker count, using API-backed concurrency only when online."""
    if api_agent_mode_enabled():
        return max(1, int(config_value("v2_api_background_worker_count", 10)))
    return max(1, int(config_value("v2_background_worker_count", 1)))


def runtime_summary() -> dict[str, Any]:
    api_mode = api_agent_mode_enabled()
    return {
        "api_agent_mode": api_mode,
        "default_worker_count": default_worker_count(),
        "online_providers": [
            provider
            for provider in llm.provider_sequence(_configured_online_provider_text())
            if llm.provider_is_online(provider) and llm.provider_has_credentials(provider)
        ],
        "provider_limits": llm.provider_limit_status(),
    }


def _agent_prompt(
    agent: AgentProfile,
    title: str,
    description: str,
    *,
    competence_note: str = "",
    skill_note: str = "",
    notebook_note: str = "",
    thought_note: str = "",
    contract_note: str = "",
    blackboard_note: str = "",
    research_note: str = "",
    peer_note: str = "",
) -> str:
    context = "\n".join(line for line in [competence_note, skill_note, notebook_note, thought_note, contract_note, blackboard_note, research_note, peer_note] if line)
    if context:
        context += "\n\n"
    review_instruction = ""
    if agent.id in {"senior_developer", "code_reviewer"} and "review" in f"{title} {description}".lower():
        review_instruction = (
            "\nFor review tasks, include a compact 'Structured feedback' section with: "
            "strengths, issues, lesson, and practice_topic.\n"
        )
    return (
        f"You are {agent.name}, one specialist inside Friday's local v2 agent team.\n"
        f"Purpose: {agent.purpose}\n"
        "Use free/local reasoning. Do not claim to have deployed, purchased, sent, deleted, or modified anything unless a tool did it.\n"
        "Return a concise task result with: Summary, Next step, Risks.\n\n"
        "Satisfy the task contract before saying the work is complete.\n\n"
        "Treat the silent thought bus as internal agent-team context. Use it for reasoning, but do not expose it unless asked.\n\n"
        "If you need another specialist, write a line exactly like: Agent question to agent_id: your question.\n"
        "Use the agent directory in context to choose who can answer.\n\n"
        f"{review_instruction}"
        f"{context}"
        f"Task: {title}\nDetails: {description}"
    )


def _local_fallback_output(agent: AgentProfile, title: str, description: str) -> str:
    return (
        f"Summary: {agent.name} queued a local plan for '{title}'. "
        f"Next step: review the task details and break it into concrete actions. "
        f"Risks: no LLM response was available, so this is a lightweight local fallback. Details: {description[:160]}"
    )


def _contract_note(task: dict[str, Any]) -> str:
    try:
        contract = task_contracts.get_contract(int(task.get("id") or 0)) if task.get("id") else None
        if not contract:
            contract = task_contracts.draft_from_task(task)
        return (
            "Task contract:\n"
            f"- Goal: {contract.get('goal')}\n"
            f"- Success criteria: {'; '.join(contract.get('success_criteria') or [])}\n"
            f"- Expected output: {contract.get('expected_output')}\n"
            f"- Verification: {contract.get('verification_method')}\n"
            f"- Risk: {contract.get('risk_level')}"
        )
    except Exception:
        return ""


def _store_agent_notebook_memory(agent: AgentProfile, title: str, output: str, topics: list[str]) -> None:
    if not output.strip():
        return
    kind_by_agent = {
        "research_analyst": "fact",
        "senior_developer": "implementation_pattern",
        "junior_developer": "implementation_pattern",
        "code_reviewer": "implementation_pattern",
        "qa_engineer": "recurring_bug",
        "ui_ux_designer": "design_rule",
        "brand_content_designer": "lesson",
        "cybersecurity_analyst": "security_check",
        "ethical_hacker": "security_check",
        "devops": "implementation_pattern",
        "data_scientist": "fact",
    }
    try:
        agent_memory.remember(
            agent.id,
            kind_by_agent.get(agent.id, "lesson"),
            f"{agent.name}: {title}",
            _clean_text(output)[:1200],
            tags=topics,
            confidence=0.62,
            source="agent_task_result",
        )
    except Exception:
        return


def _agent_provider_chain(agent_id: str) -> list[str]:
    routes = config_value("v2_agent_provider_routes", {})
    route: Any = ""
    if isinstance(routes, dict):
        route = routes.get(normalize_agent_id(agent_id)) or routes.get("default") or ""
    chain = llm.provider_sequence(route)
    if not chain:
        chain = llm.provider_sequence([config_value("llm_provider", "nvidia"), config_value("llm_fallback_provider", "ollama")])
    if api_agent_mode_enabled() and bool(config_value("v2_api_agent_force_online_first", True)):
        chain = _prefer_online_providers(chain)
    return chain or ["ollama"]


def _prefer_online_providers(chain: list[str]) -> list[str]:
    preferred = [
        provider
        for provider in chain
        if llm.provider_is_online(provider) and llm.provider_has_credentials(provider)
    ]
    if not preferred:
        preferred = [
            provider
            for provider in llm.provider_sequence(_configured_online_provider_text())
            if llm.provider_is_online(provider) and llm.provider_has_credentials(provider)
        ]
    local_and_fallback = [provider for provider in chain if provider not in preferred]
    merged: list[str] = []
    for provider in [*preferred, *local_and_fallback]:
        if provider and provider not in merged:
            merged.append(provider)
    return merged


def _configured_online_provider_text() -> str:
    routes = config_value("v2_agent_provider_routes", {})
    route_text = ""
    if isinstance(routes, dict):
        route_text = ">".join(str(value) for value in routes.values())
    return ">".join(
        [
            str(config_value("v2_api_agent_online_providers", "nvidia>gemini>openrouter>anthropic")),
            str(config_value("llm_provider", "")),
            str(config_value("llm_fallback_provider", "")),
            route_text,
        ]
    )


def _ask_agent_text(agent_id: str, prompt: str, *, provider_chain: list[str] | None = None) -> str | None:
    chain = provider_chain or _agent_provider_chain(agent_id)
    return llm.ask_simple_with_provider_chain(prompt, chain, retries=1)


def _default_agent() -> AgentProfile:
    return next(agent for agent in ROSTER if agent.id == "research_analyst")


def _all_profiles() -> list[AgentProfile]:
    profiles = list(ROSTER)
    try:
        for item in agent_lifecycle.active_agents():
            agent_id = str(item.get("id") or "").strip()
            if not agent_id or agent_id in {profile.id for profile in profiles}:
                continue
            profiles.append(
                AgentProfile(
                    agent_id,
                    str(item.get("name") or agent_id.replace("_", " ").title()),
                    str(item.get("purpose") or "Dynamically hired specialist."),
                    tuple(str(keyword) for keyword in item.get("keywords") or ()),
                )
            )
    except Exception:
        pass
    return profiles


def _infer_task_type(text: str) -> str:
    lowered = str(text or "").lower()
    for name, words in {
        "coding": ("code", "implement", "bug", "test", "refactor"),
        "research": ("research", "find", "summarize", "source"),
        "design": ("design", "ui", "ux", "figma"),
        "security": ("security", "vulnerability", "scan", "harden"),
        "deployment": ("deploy", "release", "server", "render", "vercel"),
    }.items():
        if any(word in lowered for word in words):
            return name
    return "general"


def _research_note(agent: AgentProfile, task: dict[str, Any], task_text: str) -> str:
    if not bool(config_value("v2_agent_autonomous_research_enabled", True)):
        return ""
    text = task_text.lower()
    weak = competence.weakest_topics(agent.id, task_text)
    research_agents = {
        "research_analyst",
        "ui_ux_designer",
        "brand_content_designer",
        "senior_developer",
        "junior_developer",
        "devops",
        "cybersecurity_analyst",
        "qa_engineer",
        "code_reviewer",
        "data_scientist",
        "product_manager",
    }
    should_research = agent.id in research_agents and (
        "research" in text
        or "learn" in text
        or "docs" in text
        or "documentation" in text
        or "youtube" in text
        or bool(weak)
    )
    if not should_research:
        return ""
    findings = research.research_topic(task_text, limit=int(config_value("research_max_sources", 2)))
    notes = str(findings.get("notes") or "")
    _record_research_handoff(task, agent, task_text, notes)
    return notes


def _record_research_handoff(task: dict[str, Any], agent: AgentProfile, task_text: str, notes: str) -> None:
    if not notes.strip():
        return
    task_id = int(task.get("id") or 0)
    excerpt = _clean_text(notes)[:1200]
    if task_id > 0:
        try:
            task_queue.post_message(task_id, "research_analyst", f"Research handoff to {agent.id}: {excerpt}")
        except Exception:
            pass
        try:
            agent_blackboard.post_item(
                "research_analyst",
                "finding",
                f"Research handoff to {agent.id}",
                excerpt,
                task_id=task_id,
                confidence=0.62,
                target_agent_id=agent.id,
                status="open",
                metadata={"topic": task_text[:300]},
            )
        except Exception:
            pass
        _post_thought_safe(
            "research_analyst",
            "research_handoff",
            f"Research handoff to {agent.id}",
            {"topic": task_text[:300], "notes": excerpt},
            target_agent_id=agent.id,
            task_id=task_id,
            confidence=0.62,
            priority=int(task.get("priority") or 5),
            metadata={"source": "autonomous_research"},
        )
    if agent.id == "research_analyst":
        return
    topic = ",".join(competence.infer_topics(task_text)[:3]) or "general"
    try:
        from core import long_term_learning

        long_term_learning.record_learning(
            "research_handoff",
            topic,
            f"{agent.name} should remember: {excerpt}",
            source=f"research_analyst_to_{agent.id}",
            confidence=0.62,
        )
    except Exception:
        pass
    try:
        agent_memory.remember(
            agent.id,
            "source" if "http" in excerpt.lower() or "docs" in task_text.lower() else "fact",
            f"Research handoff: {topic}",
            excerpt,
            tags=["research", "handoff", *[part for part in topic.split(",") if part]],
            confidence=0.62,
            source=f"research_analyst_to_{agent.id}",
        )
    except Exception:
        pass
    try:
        skill_library.add_skill(
            f"Research handoff: {topic}",
            f"Fresh research passed from Research Analyst to {agent.name}.",
            excerpt,
            agent_id=agent.id,
            tags=["research", "handoff", *[part for part in topic.split(",") if part]],
            source="research_handoff",
        )
    except Exception:
        pass


def _agent_directory_note(current_agent_id: str) -> str:
    lines = ["Agent directory for routing questions:"]
    for peer in _all_profiles():
        if peer.id == current_agent_id:
            continue
        lines.append(f"- {peer.id}: {peer.name}. {peer.purpose}")
    return "\n".join(lines)


def _spawn_agent_questions(task: dict[str, Any], agent: AgentProfile, title: str, description: str, output: str) -> list[int]:
    if not bool(config_value("v2_agent_questions_enabled", True)):
        return []
    task_id = int(task.get("id") or 0)
    if task_id <= 0:
        return []
    priority = int(task.get("priority") or 5) + 1
    spawned: list[int] = []
    for target_id, question in _parse_agent_questions(output):
        if target_id == agent.id or target_id not in {item.id for item in _all_profiles()}:
            continue
        child_id = task_queue.create_task(
            f"Answer {agent.name}'s question for {title}",
            description=(
                f"{agent.name} asked: {question}\n\n"
                f"Parent task #{task_id}: {title}\n"
                f"Parent details: {description}\n"
                "Answer concisely with evidence, risks, and any recommendation."
            ),
            agent_id=target_id,
            priority=priority,
            input_data={"source": "agent_question", "from_agent": agent.id, "question": question},
            parent_id=task_id,
        )
        task_queue.post_message(task_id, agent.id, f"Question routed to {target_id}: {question}")
        task_queue.post_message(child_id, "router", f"Question from {agent.id}: {question}")
        _post_thought_safe(
            agent.id,
            "question",
            f"Question for {target_id}",
            {"question": question, "parent_title": title, "child_task_id": child_id},
            target_agent_id=target_id,
            task_id=task_id,
            confidence=0.72,
            priority=priority,
            metadata={"child_task_id": child_id, "source": "agent_question"},
        )
        try:
            agent_blackboard.post_item(
                agent.id,
                "question",
                f"Question for {target_id}",
                question,
                task_id=task_id,
                confidence=0.7,
                target_agent_id=target_id,
                status="needs_answer",
                metadata={"child_task_id": child_id, "parent_title": title},
            )
        except Exception:
            pass
        spawned.append(child_id)
    return spawned


def _parse_agent_questions(output: str) -> list[tuple[str, str]]:
    pattern = re.compile(
        r"^\s*(?:agent\s+question\s+to|ask|question\s+for)\s+([a-zA-Z0-9_\-\s]+?)\s*:\s*(.+)$",
        re.IGNORECASE | re.MULTILINE,
    )
    questions: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for match in pattern.finditer(str(output or "")):
        target = normalize_agent_id(match.group(1))
        question = _clean_text(match.group(2))[:500]
        key = (target, question.lower())
        if target and question and key not in seen:
            seen.add(key)
            questions.append((target, question))
    return questions[:3]


def _spawn_subtasks(task: dict[str, Any], agent: AgentProfile, title: str, description: str, output: str) -> list[int]:
    if not bool(config_value("v2_agent_delegation_enabled", True)):
        return []
    if task.get("parent_id"):
        return []
    task_id = int(task.get("id") or 0)
    if task_id <= 0:
        return []
    text = f"{title} {description}".lower()
    priority = int(task.get("priority") or 5) + 1
    plans: list[tuple[str, str, str]] = _dynamic_subtasks(agent, title, description, output)
    if agent.id == "ceo" and any(word in text for word in ["build", "create", "project", "app", "website", "dashboard"]):
        plans.extend(
            [
                ("product_manager", f"Clarify requirements for {title}", "Define scope, acceptance criteria, and open questions."),
                ("research_analyst", f"Research references for {title}", "Find free/local docs, examples, and risks relevant to the task."),
                ("senior_developer", f"Plan implementation for {title}", "Create a safe technical plan and identify files/tools needed."),
                ("qa_engineer", f"Draft test plan for {title}", "List regression and acceptance tests."),
            ]
        )
    elif agent.id == "senior_developer" and any(word in text for word in ["build", "implement", "refactor", "fix"]):
        plans.extend(
            [
                ("research_analyst", f"Research technical docs for {title}", "Collect relevant official docs and compatibility notes."),
                ("qa_engineer", f"Prepare tests for {title}", "Design focused tests and edge cases."),
            ]
        )
    if agent.id == "junior_developer" and bool(config_value("v2_mentoring_enabled", True)):
        plans.append(
            (
                "senior_developer",
                f"Review Junior Developer output for {title}",
                f"Review the junior output, give structured feedback, and store teachable lessons. Output excerpt: {output[:700]}",
            )
        )
    spawned: list[int] = []
    for child_agent, child_title, child_description in plans[: int(config_value("v2_max_subtasks_per_task", 4))]:
        child_id = task_queue.create_task(
            child_title,
            description=child_description,
            agent_id=child_agent,
            priority=priority,
            input_data={"source": "agent_delegation", "parent_agent": agent.id},
            parent_id=task_id,
        )
        _post_thought_safe(
            agent.id,
            "delegation",
            f"Delegated child task to {child_agent}",
            {"title": child_title, "description": child_description, "child_task_id": child_id},
            target_agent_id=child_agent,
            task_id=task_id,
            confidence=0.65,
            priority=priority,
            metadata={"child_task_id": child_id, "source": "agent_delegation"},
        )
        spawned.append(child_id)
    return spawned


def _post_result_thought(task: dict[str, Any], agent: AgentProfile, output: str, topics: list[str], spawned_subtasks: list[int]) -> None:
    task_id = int(task.get("id") or 0)
    if task_id <= 0 or not bool(config_value("agent_thought_bus_enabled", True)):
        return
    _post_thought_safe(
        agent.id,
        "result_summary",
        f"{agent.name} result for task #{task_id}",
        {
            "title": task.get("title"),
            "summary": _clean_text(output)[:1200],
            "topics": topics,
            "spawned_subtasks": spawned_subtasks,
        },
        task_id=task_id,
        confidence=0.68 if output else 0.3,
        priority=int(task.get("priority") or 5),
        metadata={"status": "prepared", "agent_name": agent.name},
    )


def _post_thought_safe(
    source_agent_id: str,
    packet_type: str,
    summary: str,
    content: dict[str, Any] | str | None = None,
    **kwargs: Any,
) -> None:
    if not bool(config_value("agent_thought_bus_enabled", True)):
        return
    try:
        agent_thought_bus.post_thought(source_agent_id, packet_type, summary, content, **kwargs)
    except Exception:
        return


def _dynamic_subtasks(agent: AgentProfile, title: str, description: str, output: str) -> list[tuple[str, str, str]]:
    if not bool(config_value("v2_dynamic_decomposition_enabled", True)):
        return []
    if not bool(config_value("v2_agent_use_llm", True)):
        return []
    if agent.id not in {"ceo", "senior_developer", "product_manager", "project_manager"}:
        return []
    allowed_agent_ids = ", ".join(agent.id for agent in _all_profiles() if agent.id not in {"ceo", "ethical_hacker"})
    prompt = (
        "Break this Friday v2 agent-team task into at most 4 child tasks. "
        "Return only JSON: an array of objects with agent_id, title, description. "
        f"Allowed agent_id values: {allowed_agent_ids}. "
        "Do not include ethical_hacker. Use free/local/cheap options when relevant.\n\n"
        f"Parent agent: {agent.id}\nTitle: {title}\nDescription: {description}\nParent output: {output[:800]}"
    )
    raw = _ask_agent_text(agent.id, prompt) or ""
    return _parse_subtask_json(raw)


def _parse_subtask_json(raw: str) -> list[tuple[str, str, str]]:
    text = str(raw or "").strip()
    if not text:
        return []
    if "```" in text:
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.IGNORECASE | re.MULTILINE)
    match = re.search(r"\[[\s\S]*\]", text)
    if match:
        text = match.group(0)
    try:
        data = json.loads(text)
    except Exception:
        return []
    if not isinstance(data, list):
        return []
    allowed = {agent.id for agent in _all_profiles()} - {"ceo", "ethical_hacker"}
    plans: list[tuple[str, str, str]] = []
    seen: set[tuple[str, str]] = set()
    for item in data:
        if not isinstance(item, dict):
            continue
        agent_id = normalize_agent_id(str(item.get("agent_id") or "research_analyst"))
        child_title = _clean_text(item.get("title") or "")
        child_description = _clean_text(item.get("description") or child_title)
        key = (agent_id, child_title.lower())
        if agent_id not in allowed or not child_title or key in seen:
            continue
        seen.add(key)
        plans.append((agent_id, child_title[:160], child_description[:1000]))
    return plans


def _structured_review_feedback(agent: AgentProfile, title: str, output: str) -> dict[str, Any]:
    if agent.id not in {"senior_developer", "code_reviewer"}:
        return {}
    if "review" not in title.lower() and "feedback" not in output.lower():
        return {}
    text = str(output or "")
    feedback = {
        "strengths": _extract_review_items(text, ("strength", "strengths", "worked well", "good")),
        "issues": _extract_review_items(text, ("issue", "issues", "bug", "risk", "risks", "improve", "improvement")),
        "lesson": _extract_review_value(text, ("lesson", "teachable lesson", "learning")),
        "practice_topic": _extract_review_value(text, ("practice_topic", "practice topic", "topic")),
    }
    if not feedback["lesson"] and feedback["issues"]:
        feedback["lesson"] = feedback["issues"][0]
    if not feedback["practice_topic"]:
        feedback["practice_topic"] = _infer_feedback_topic(text)
    return {key: value for key, value in feedback.items() if value}


def _store_review_feedback(title: str, feedback: dict[str, Any]) -> None:
    try:
        from core import knowledge_graph

        topic = str(feedback.get("practice_topic") or "code quality")
        lesson = str(feedback.get("lesson") or "").strip()
        knowledge_graph.add_edge("Senior Developer", "REVIEWED", title, feedback=feedback)
        knowledge_graph.add_edge("Senior Developer", "TAUGHT", topic, lesson=lesson)
        knowledge_graph.add_edge("Junior Developer", "NEEDS_PRACTICE", topic, lesson=lesson)
        if lesson:
            skill_library.add_skill(
                f"Review lesson: {topic}",
                "Structured mentoring feedback captured from a Senior Developer review.",
                lesson,
                agent_id="junior_developer",
                tags=["review", topic],
                source="senior_review",
            )
    except Exception:
        return


def _extract_review_items(text: str, labels: tuple[str, ...]) -> list[str]:
    lowered_labels = "|".join(re.escape(label).replace("\\ ", r"\s+") for label in labels)
    pattern = re.compile(rf"^\s*(?:[-*]\s*)?(?:{lowered_labels})\s*[:\-]\s*(.+)$", re.IGNORECASE | re.MULTILINE)
    items: list[str] = []
    for match in pattern.finditer(text):
        value = match.group(1).strip(" .")
        if value:
            items.extend(_split_feedback_value(value))
    return items[:5]


def _extract_review_value(text: str, labels: tuple[str, ...]) -> str:
    lowered_labels = "|".join(re.escape(label).replace("\\ ", r"\s+") for label in labels)
    match = re.search(rf"^\s*(?:[-*]\s*)?(?:{lowered_labels})\s*[:\-]\s*(.+)$", text, re.IGNORECASE | re.MULTILINE)
    if not match:
        return ""
    return _clean_text(match.group(1))[:240]


def _split_feedback_value(value: str) -> list[str]:
    parts = re.split(r"\s*;\s*|\s*\|\s*", value)
    return [_clean_text(part)[:240] for part in parts if _clean_text(part)]


def _infer_feedback_topic(text: str) -> str:
    lowered = text.lower()
    topics = {
        "tests": ("test", "coverage", "regression"),
        "security": ("security", "sanitize", "injection", "secret"),
        "error handling": ("exception", "error", "failure"),
        "performance": ("slow", "performance", "latency"),
        "readability": ("readable", "naming", "style"),
    }
    for topic, words in topics.items():
        if any(word in lowered for word in words):
            return topic
    return "code quality"


def _clean_text(value: Any) -> str:
    return " ".join(str(value or "").strip().split())
