"""Central intent classification and slot extraction for Friday commands."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Callable

from core import llm
from core.config import config_value, resolve_coding_root


@dataclass(frozen=True)
class IntentSpec:
    name: str
    description: str
    tool_name: str
    tool_action: str
    risk: str
    min_confidence: float
    required_slots: tuple[str, ...] = ()


@dataclass
class IntentResult:
    intent: str = "none"
    confidence: float = 0.0
    slots: dict[str, Any] = field(default_factory=dict)
    source: str = "none"
    reason: str = ""
    tool_name: str = ""
    tool_input: dict[str, Any] = field(default_factory=dict)
    risk: str = "none"
    min_confidence: float = 1.0
    ask_user: str = ""

    @property
    def actionable(self) -> bool:
        return bool(
            self.intent
            and self.intent != "none"
            and self.tool_name
            and self.confidence >= self.min_confidence
            and not self.ask_user
        )


INTENT_SPECS: dict[str, IntentSpec] = {
    "start_coding_project": IntentSpec(
        name="start_coding_project",
        description="Start a guarded autonomous programming project or app build.",
        tool_name="power_center",
        tool_action="autonomous_coding",
        risk="writes_project_files",
        min_confidence=0.82,
        required_slots=("request",),
    ),
    "project_ideas": IntentSpec(
        name="project_ideas",
        description="Research source-backed project ideas before recommending what to build next.",
        tool_name="power_center",
        tool_action="project_ideas_research",
        risk="network_read",
        min_confidence=0.78,
        required_slots=("context",),
    ),
    "create_agent_task": IntentSpec(
        name="create_agent_task",
        description="Delegate a task to Friday's background agent team.",
        tool_name="agent_team",
        tool_action="create_task",
        risk="queues_background_work",
        min_confidence=0.78,
        required_slots=("title",),
    ),
    "run_diagnostics": IntentSpec(
        name="run_diagnostics",
        description="Delegate self, system, repo, provider, build, test, or production diagnostics to the Doctor agent.",
        tool_name="agent_team",
        tool_action="run_diagnostics",
        risk="queues_background_work",
        min_confidence=0.82,
    ),
    "list_tasks": IntentSpec(
        name="list_tasks",
        description="List agent tasks, optionally filtered by status.",
        tool_name="agent_team",
        tool_action="list_tasks",
        risk="read_only",
        min_confidence=0.72,
    ),
    "agent_status": IntentSpec(
        name="agent_status",
        description="Report background agent worker status.",
        tool_name="agent_team",
        tool_action="status",
        risk="read_only",
        min_confidence=0.72,
    ),
    "create_reminder": IntentSpec(
        name="create_reminder",
        description="Create a local reminder.",
        tool_name="app_integrations",
        tool_action="create_reminder",
        risk="writes_personal_data",
        min_confidence=0.82,
        required_slots=("title",),
    ),
    "search_workspace": IntentSpec(
        name="search_workspace",
        description="Search indexed workspace documents.",
        tool_name="app_integrations",
        tool_action="search_workspace",
        risk="read_only",
        min_confidence=0.78,
        required_slots=("query",),
    ),
    "generate_image": IntentSpec(
        name="generate_image",
        description="Generate an image, logo, illustration, or visual asset.",
        tool_name="image_generation",
        tool_action="generate",
        risk="creates_asset",
        min_confidence=0.82,
        required_slots=("prompt",),
    ),
    "draft_ad_campaign": IntentSpec(
        name="draft_ad_campaign",
        description="Draft ad campaign copy, variants, CTAs, hashtags, and creative prompts.",
        tool_name="power_center",
        tool_action="ad_campaign_draft",
        risk="creates_marketing_copy",
        min_confidence=0.82,
        required_slots=("product",),
    ),
    "post_ad_campaign": IntentSpec(
        name="post_ad_campaign",
        description="Queue an ad campaign post through an approval-gated connector outbox.",
        tool_name="power_center",
        tool_action="ad_campaign_post",
        risk="network_write",
        min_confidence=0.84,
        required_slots=("product", "connector", "target"),
    ),
    "web_search": IntentSpec(
        name="web_search",
        description="Search the web for current or external information.",
        tool_name="web_search",
        tool_action="search",
        risk="network_read",
        min_confidence=0.8,
        required_slots=("query",),
    ),
    "academic_project": IntentSpec(
        name="academic_project",
        description="Prepare a source-backed final year project, proposal, literature review, thesis draft, or research paper with document exports.",
        tool_name="power_center",
        tool_action="academic_project",
        risk="writes_academic_documents",
        min_confidence=0.82,
        required_slots=("topic",),
    ),
    "git_status": IntentSpec(
        name="git_status",
        description="Read Git status for a local repository.",
        tool_name="power_center",
        tool_action="git_status",
        risk="read_only",
        min_confidence=0.78,
    ),
    "git_branches": IntentSpec(
        name="git_branches",
        description="Read local and remote Git branches.",
        tool_name="power_center",
        tool_action="git_branches",
        risk="read_only",
        min_confidence=0.78,
    ),
    "git_diff": IntentSpec(
        name="git_diff",
        description="Read Git diff for a local repository.",
        tool_name="power_center",
        tool_action="git_diff",
        risk="read_only",
        min_confidence=0.78,
    ),
    "git_log": IntentSpec(
        name="git_log",
        description="Read recent Git commit history.",
        tool_name="power_center",
        tool_action="git_log",
        risk="read_only",
        min_confidence=0.78,
    ),
    "git_clone": IntentSpec(
        name="git_clone",
        description="Clone a Git or GitHub repository under the configured coding projects root.",
        tool_name="power_center",
        tool_action="git_clone",
        risk="writes_project_files",
        min_confidence=0.82,
        required_slots=("repo",),
    ),
    "git_checkout": IntentSpec(
        name="git_checkout",
        description="Checkout or create a Git branch.",
        tool_name="power_center",
        tool_action="git_checkout",
        risk="changes_repository_state",
        min_confidence=0.8,
        required_slots=("branch",),
    ),
    "git_pull": IntentSpec(
        name="git_pull",
        description="Pull latest changes from a Git remote.",
        tool_name="power_center",
        tool_action="git_pull",
        risk="changes_repository_state",
        min_confidence=0.8,
    ),
    "git_add": IntentSpec(
        name="git_add",
        description="Stage files for a Git commit.",
        tool_name="power_center",
        tool_action="git_add",
        risk="changes_repository_state",
        min_confidence=0.82,
        required_slots=("paths",),
    ),
    "git_commit": IntentSpec(
        name="git_commit",
        description="Create a Git commit with a user-provided message.",
        tool_name="power_center",
        tool_action="git_commit",
        risk="changes_repository_history",
        min_confidence=0.82,
        required_slots=("message",),
    ),
    "git_push": IntentSpec(
        name="git_push",
        description="Push local Git commits to a remote.",
        tool_name="power_center",
        tool_action="git_push",
        risk="network_write",
        min_confidence=0.82,
    ),
    "github_status": IntentSpec(
        name="github_status",
        description="Read GitHub CLI authentication and setup status.",
        tool_name="power_center",
        tool_action="github_status",
        risk="network_read",
        min_confidence=0.78,
    ),
    "github_pr_create": IntentSpec(
        name="github_pr_create",
        description="Create a GitHub pull request through the GitHub CLI.",
        tool_name="power_center",
        tool_action="github_pr_create",
        risk="network_write",
        min_confidence=0.82,
        required_slots=("title",),
    ),
    "github_pr_list": IntentSpec(
        name="github_pr_list",
        description="List GitHub pull requests through the GitHub CLI.",
        tool_name="power_center",
        tool_action="github_pr_list",
        risk="network_read",
        min_confidence=0.78,
    ),
    "github_issue_create": IntentSpec(
        name="github_issue_create",
        description="Create a GitHub issue through the GitHub CLI.",
        tool_name="power_center",
        tool_action="github_issue_create",
        risk="network_write",
        min_confidence=0.82,
        required_slots=("title",),
    ),
    "create_3d_model": IntentSpec(
        name="create_3d_model",
        description="Generate and export a real local 3D mesh file such as OBJ, STL, glTF, or GLB.",
        tool_name="power_center",
        tool_action="model3d_create",
        risk="creates_asset",
        min_confidence=0.84,
        required_slots=("prompt",),
    ),
    "workspace_analyze": IntentSpec(
        name="workspace_analyze",
        description="Analyze or map a software workspace.",
        tool_name="power_center",
        tool_action="workspace_analyze",
        risk="read_only",
        min_confidence=0.78,
    ),
    "codebase_standards": IntentSpec(
        name="codebase_standards",
        description="Scan code quality, architecture, hygiene, or coding standards.",
        tool_name="power_center",
        tool_action="codebase_standards",
        risk="read_only",
        min_confidence=0.78,
    ),
}

TASK_STATUSES = {"active", "pending", "blocked", "done", "failed", "cancelled"}
SOFTWARE_HINTS = {
    "app",
    "application",
    "api",
    "backend",
    "code",
    "coding",
    "dashboard",
    "frontend",
    "program",
    "project",
    "saas",
    "site",
    "software",
    "system",
    "tool",
    "web app",
    "website",
    "workflow",
}
VISUAL_HINTS = {"image", "picture", "photo", "art", "illustration", "logo", "brand mark", "logomark", "mockup"}
ACTIONABLE_HINTS = {
    "add",
    "analyze",
    "assign",
    "build",
    "create",
    "delegate",
    "generate",
    "draft",
    "advertise",
    "give",
    "get",
    "have",
    "index",
    "look up",
    "make",
    "queue",
    "prepare",
    "post",
    "publish",
    "recommend",
    "remind",
    "schedule",
    "search",
    "show",
    "start",
    "suggest",
    "tell",
    "write",
}

RuleClassifier = Callable[[str], IntentResult | None]


def classify(text: str, *, allow_llm: bool = False) -> IntentResult:
    """Classify a command into an executable intent plus validated tool input."""
    cleaned = _clean_command(text)
    if not cleaned:
        return IntentResult()

    for classifier in _RULE_CLASSIFIERS:
        result = classifier(cleaned)
        if result and result.intent != "none":
            return _materialize(result)

    if allow_llm and _semantic_intents_enabled() and _looks_actionable(cleaned):
        result = _classify_with_llm(cleaned)
        if result and result.intent != "none":
            return _materialize(result)

    return IntentResult()


def available_intents() -> list[dict[str, Any]]:
    return [
        {
            "intent": spec.name,
            "description": spec.description,
            "tool": spec.tool_name,
            "action": spec.tool_action,
            "risk": spec.risk,
            "required_slots": list(spec.required_slots),
            "min_confidence": spec.min_confidence,
        }
        for spec in INTENT_SPECS.values()
    ]


def _materialize(result: IntentResult) -> IntentResult:
    spec = INTENT_SPECS.get(result.intent)
    if not spec:
        return IntentResult(source=result.source, reason=f"Unsupported intent: {result.intent}")
    slots = _normalize_slots(result.intent, result.slots)
    missing = [slot for slot in spec.required_slots if not _slot_text(slots, slot)]
    if missing:
        return IntentResult(
            intent=result.intent,
            confidence=result.confidence,
            slots=slots,
            source=result.source,
            reason=result.reason,
            risk=spec.risk,
            min_confidence=spec.min_confidence,
            ask_user=_clarifying_question(result.intent, missing),
        )
    payload = _tool_input(spec, slots)
    if not payload:
        return IntentResult(
            intent=result.intent,
            confidence=result.confidence,
            slots=slots,
            source=result.source,
            reason=result.reason,
            risk=spec.risk,
            min_confidence=spec.min_confidence,
            ask_user=_clarifying_question(result.intent, list(spec.required_slots)),
        )
    return IntentResult(
        intent=result.intent,
        confidence=max(0.0, min(1.0, float(result.confidence or 0.0))),
        slots=slots,
        source=result.source,
        reason=result.reason,
        tool_name=spec.tool_name,
        tool_input=payload,
        risk=spec.risk,
        min_confidence=spec.min_confidence,
    )


def _tool_input(spec: IntentSpec, slots: dict[str, Any]) -> dict[str, Any]:
    action = spec.tool_action
    if spec.name == "start_coding_project":
        request = _slot_text(slots, "request", "project_description", "goal", "title")
        if not request:
            return {}
        return {
            "action": action,
            "request": _normalize_coding_request(request),
            "root": str(resolve_coding_root(_slot_text(slots, "root"))),
            "risk_level": _slot_text(slots, "risk_level") or "medium",
        }
    if spec.name == "project_ideas":
        context = _slot_text(slots, "context", "topic", "query", "request")
        if not context:
            return {}
        payload: dict[str, Any] = {
            "action": action,
            "context": context,
            "root": str(resolve_coding_root(_slot_text(slots, "root"))),
            "limit": _slot_int(slots, "limit", 5),
            "max_sources": _slot_int(slots, "max_sources", 8),
        }
        audience = _slot_text(slots, "audience")
        if audience:
            payload["audience"] = audience
        return payload
    if spec.name == "create_agent_task":
        title = _slot_text(slots, "title", "task", "goal")
        if not title:
            return {}
        payload: dict[str, Any] = {"action": action, "title": title}
        description = _slot_text(slots, "description")
        agent_id = _agent_id(_slot_text(slots, "agent_id", "agent"))
        if description:
            payload["description"] = description
        if agent_id:
            payload["agent_id"] = agent_id
        return payload
    if spec.name == "run_diagnostics":
        payload = {
            "action": action,
            "title": _slot_text(slots, "title", "request") or "Run Friday diagnostics",
            "description": _slot_text(slots, "description", "request") or "Run evidence-backed Friday diagnostics.",
            "profile": _slot_text(slots, "profile", "scope") or "standard",
        }
        root = _slot_text(slots, "root")
        if root:
            payload["root"] = root
        return payload
    if spec.name == "list_tasks":
        status = _task_status(_slot_text(slots, "status"))
        payload = {"action": action, "limit": _slot_int(slots, "limit", 8)}
        if status:
            payload["status"] = status
        return payload
    if spec.name == "agent_status":
        return {"action": action}
    if spec.name == "create_reminder":
        title = _slot_text(slots, "title", "task")
        if not title:
            return {}
        return {"action": action, "title": title, "due_at": _slot_text(slots, "due_at", "when")}
    if spec.name == "search_workspace":
        query = _slot_text(slots, "query", "target")
        return {"action": action, "query": query} if query else {}
    if spec.name == "generate_image":
        prompt = _slot_text(slots, "prompt", "description", "target")
        return {"action": action, "prompt": prompt} if prompt else {}
    if spec.name in {"draft_ad_campaign", "post_ad_campaign"}:
        product = _slot_text(slots, "product", "name", "target", "request")
        if not product:
            return {}
        payload: dict[str, Any] = {"action": action, "product": product}
        for key in ("audience", "offer", "platform", "objective", "tone", "connector", "target"):
            value = _slot_text(slots, key)
            if value:
                payload[key] = value
        campaign_id = _slot_int(slots, "campaign_id", 0)
        if campaign_id:
            payload["campaign_id"] = campaign_id
        variant_index = _slot_int(slots, "variant_index", 0)
        if variant_index:
            payload["variant_index"] = variant_index
        return payload
    if spec.name == "web_search":
        query = _slot_text(slots, "query", "target")
        return {"action": action, "query": query} if query else {}
    if spec.name == "academic_project":
        topic = _slot_text(slots, "topic", "title", "target", "request")
        if not topic:
            return {}
        payload = {
            "action": action,
            "topic": topic,
            "kind": _academic_kind(_slot_text(slots, "kind", "document_type")),
            "citation_style": _slot_text(slots, "citation_style", "style") or "APA",
            "formats": _academic_formats(slots.get("formats") or slots.get("format") or ["md", "docx", "pdf"]),
        }
        requirements = _slot_text(slots, "requirements", "description", "notes")
        if requirements:
            payload["requirements"] = requirements
        max_sources = _slot_int(slots, "max_sources", 0)
        if max_sources:
            payload["max_sources"] = max_sources
        return payload
    if spec.name in {"git_status", "git_branches", "git_diff", "git_log", "git_pull", "git_push", "github_status", "github_pr_list"}:
        payload = {"action": action}
        root = _slot_text(slots, "root")
        if root:
            payload["root"] = root
        if spec.name == "git_diff":
            path = _slot_text(slots, "path", "target")
            if path:
                payload["path"] = path
            payload["staged"] = bool(slots.get("staged", False))
        if spec.name == "git_log":
            payload["limit"] = _slot_int(slots, "limit", 5)
        if spec.name in {"git_pull", "git_push"}:
            remote = _slot_text(slots, "remote")
            branch = _slot_text(slots, "branch")
            if remote:
                payload["remote"] = remote
            if branch:
                payload["branch"] = branch
            if spec.name == "git_push" and bool(slots.get("set_upstream", False)):
                payload["set_upstream"] = True
        if spec.name == "github_pr_list":
            state = _slot_text(slots, "state")
            if state:
                payload["state"] = state
            payload["limit"] = _slot_int(slots, "limit", 10)
        return payload
    if spec.name == "git_clone":
        repo = _slot_text(slots, "repo", "url", "target")
        if not repo:
            return {}
        payload = {"action": action, "repo": repo}
        destination = _slot_text(slots, "destination", "path", "name")
        if destination:
            payload["destination"] = destination
        return payload
    if spec.name == "git_checkout":
        branch = _slot_text(slots, "branch", "target")
        if not branch:
            return {}
        payload = {"action": action, "branch": branch}
        root = _slot_text(slots, "root")
        if root:
            payload["root"] = root
        if bool(slots.get("create", False)):
            payload["create"] = True
        return payload
    if spec.name == "git_add":
        raw_paths = slots.get("paths") or slots.get("path") or slots.get("target")
        paths = raw_paths if isinstance(raw_paths, list) else _slot_text(slots, "paths", "path", "target")
        if not paths:
            return {}
        payload = {"action": action, "paths": paths}
        root = _slot_text(slots, "root")
        if root:
            payload["root"] = root
        return payload
    if spec.name == "git_commit":
        message = _slot_text(slots, "message", "title", "target")
        if not message:
            return {}
        payload = {"action": action, "message": message}
        root = _slot_text(slots, "root")
        if root:
            payload["root"] = root
        return payload
    if spec.name in {"github_pr_create", "github_issue_create"}:
        title = _slot_text(slots, "title", "target")
        if not title:
            return {}
        payload = {"action": action, "title": title}
        for key in ("root", "body", "base", "head"):
            value = _slot_text(slots, key)
            if value:
                payload[key] = value
        return payload
    if spec.name == "create_3d_model":
        prompt = _slot_text(slots, "prompt", "description", "target", "request")
        if not prompt:
            return {}
        payload = {"action": action, "prompt": prompt, "formats": _model_formats(slots.get("formats") or slots.get("format") or [])}
        shape = _slot_text(slots, "shape", "kind")
        if shape:
            payload["shape"] = shape
        quality = _slot_text(slots, "quality", "mode")
        if quality:
            payload["quality"] = quality
        name = _slot_text(slots, "name", "title")
        if name:
            payload["name"] = name
        return payload
    if spec.name == "workspace_analyze":
        root = _slot_text(slots, "root")
        payload = {"action": action}
        if root:
            payload["root"] = root
        return payload
    if spec.name == "codebase_standards":
        return {"action": action, "focus": _slot_text(slots, "focus", "target")}
    return {"action": action}


def _classify_3d_model(text: str) -> IntentResult | None:
    lowered = text.lower()
    if re.search(r"\b(?:image|picture|photo|illustration|logo)\b", lowered):
        return None
    if not re.search(r"\b(?:3d|three[-\s]?d|obj|stl|gltf|glb|mesh)\b", lowered):
        return None
    patterns = (
        r"(?:generate|create|make|build|export|design)\s+(?:an?\s+)?(?:(?:photo\s*realistic|photorealistic|realistic|zbrush\s+quality|studio|high[-\s]?quality|blender|pbr|cinematic)\s+)*(?:3d|three[-\s]?d)\s+(?:model|asset|mesh|object|file)?\s*(?:of|for)?\s*(?P<prompt>.+)",
        r"(?:generate|create|make|build|export|design)\s+(?:an?\s+)?(?:3d|three[-\s]?d)\s+(?:model|asset|mesh|object|file)?\s*(?:of|for)?\s*(?P<prompt>.+)",
        r"(?:generate|create|make|build|export|design)\s+(?P<prompt>.+?)\s+(?:as|to|into)\s+(?P<format>obj|stl|gltf|glb)(?:\s+(?:3d\s+)?(?:model|mesh|file))?",
        r"(?:3d|three[-\s]?d)\s+(?:model|asset|mesh)\s+(?:of|for)\s+(?P<prompt>.+)",
    )
    for pattern in patterns:
        match = re.fullmatch(pattern, text, flags=re.IGNORECASE)
        if not match:
            continue
        prompt = _clean_model_prompt(match.group("prompt"))
        if not prompt:
            continue
        formats = _extract_model_formats(text)
        return IntentResult(
            "create_3d_model",
            0.9,
            {"prompt": prompt, "formats": formats, "quality": _model_quality(text)},
            "rules",
            "3D model generation request",
        )
    return None


def _classify_git(text: str) -> IntentResult | None:
    lowered = text.lower()
    if not re.search(r"\b(?:git|github|repo|repository|pull\s+request|pr)\b", lowered):
        return None
    if re.fullmatch(r"(?:show|check|get|run)?\s*(?:the\s+)?git\s+status(?:\s+(?:for|of)\s+(?P<root>.+))?", text, flags=re.IGNORECASE):
        root = _clean_slot(re.sub(r"^(?:show|check|get|run)?\s*(?:the\s+)?git\s+status(?:\s+(?:for|of))?", "", text, flags=re.IGNORECASE))
        slots = {"root": root} if root and root.lower() != text.lower() else {}
        return IntentResult("git_status", 0.88, slots, "rules", "git status request")
    if re.fullmatch(r"(?:show|list|get)?\s*(?:the\s+)?git\s+(?:branches|branch(?:es)?)(?:\s+--all)?", text, flags=re.IGNORECASE):
        return IntentResult("git_branches", 0.86, {}, "rules", "git branch list request")
    if re.fullmatch(r"(?:show|check|get|run)?\s*(?:the\s+)?(?:github|gh)\s+(?:status|auth\s+status)", text, flags=re.IGNORECASE):
        return IntentResult("github_status", 0.84, {}, "rules", "github cli status request")
    if re.fullmatch(r"(?:show|check|get|run)?\s*(?:the\s+)?git\s+diff(?:\s+(?P<staged>staged|--staged))?", text, flags=re.IGNORECASE):
        return IntentResult("git_diff", 0.86, {"staged": "staged" in lowered or "--staged" in lowered}, "rules", "git diff request")
    if re.fullmatch(r"(?:show|get)?\s*(?:the\s+)?git\s+log(?:\s+(?P<limit>\d+))?", text, flags=re.IGNORECASE):
        match = re.search(r"\b(?P<limit>\d+)\b", text)
        return IntentResult("git_log", 0.84, {"limit": int(match.group("limit")) if match else 5}, "rules", "git log request")
    clone_match = re.fullmatch(
        r"(?:git\s+)?clone\s+(?:(?:github\s+)?(?:repo|repository)\s+)?(?P<repo>\S+)(?:\s+(?:to|into|as)\s+(?P<destination>.+))?",
        text,
        flags=re.IGNORECASE,
    )
    if clone_match:
        slots = {"repo": _clean_slot(clone_match.group("repo"))}
        destination = _clean_slot(clone_match.groupdict().get("destination", ""))
        if destination:
            slots["destination"] = destination
        return IntentResult("git_clone", 0.9, slots, "rules", "git clone request")
    checkout_match = re.fullmatch(
        r"(?:git\s+)?(?P<create>create\s+and\s+checkout|checkout\s+-b|new\s+branch|create\s+branch|switch\s+to|checkout)\s+(?:branch\s+)?(?P<branch>[A-Za-z0-9._/\-]+)",
        text,
        flags=re.IGNORECASE,
    )
    if checkout_match:
        verb = checkout_match.group("create").lower()
        return IntentResult(
            "git_checkout",
            0.86,
            {"branch": checkout_match.group("branch"), "create": "create" in verb or "-b" in verb or "new branch" in verb},
            "rules",
            "git checkout request",
        )
    if re.fullmatch(r"(?:git\s+)?pull(?:\s+(?P<remote>[A-Za-z0-9._/\-]+))?(?:\s+(?P<branch>[A-Za-z0-9._/\-]+))?|pull\s+latest", text, flags=re.IGNORECASE):
        parts = text.split()
        slots: dict[str, Any] = {}
        if len(parts) >= 3 and parts[0].lower() == "git" and parts[1].lower() == "pull":
            slots["remote"] = parts[2]
            if len(parts) >= 4:
                slots["branch"] = parts[3]
        return IntentResult("git_pull", 0.84, slots, "rules", "git pull request")
    add_match = re.fullmatch(r"(?:git\s+)?add\s+(?P<paths>.+)", text, flags=re.IGNORECASE)
    if add_match:
        raw_paths = _clean_slot(add_match.group("paths"))
        paths = [item for item in raw_paths.split() if item] if raw_paths != "." else ["."]
        return IntentResult("git_add", 0.86, {"paths": paths}, "rules", "git add request")
    commit_match = re.fullmatch(
        r"(?:git\s+)?commit(?:\s+(?:changes|everything|all))?(?:\s+(?:with\s+message|message|as|saying))\s+(?P<message>.+)",
        text,
        flags=re.IGNORECASE,
    )
    if commit_match:
        return IntentResult("git_commit", 0.9, {"message": _strip_quotes(commit_match.group("message"))}, "rules", "git commit request")
    if re.fullmatch(r"(?:git\s+)?push(?:\s+(?P<remote>[A-Za-z0-9._/\-]+))?(?:\s+(?P<branch>[A-Za-z0-9._/\-]+))?(?:\s+upstream)?", text, flags=re.IGNORECASE):
        parts = text.split()
        slots = {"set_upstream": "upstream" in lowered}
        if len(parts) >= 3 and parts[0].lower() == "git" and parts[1].lower() == "push":
            slots["remote"] = parts[2]
            if len(parts) >= 4 and parts[3].lower() != "upstream":
                slots["branch"] = parts[3]
        return IntentResult("git_push", 0.84, slots, "rules", "git push request")
    if re.fullmatch(r"(?:list|show|get)\s+(?:github\s+)?(?:pull\s+requests|prs)(?:\s+(?P<state>open|closed|merged|all))?", text, flags=re.IGNORECASE):
        state_match = re.search(r"\b(open|closed|merged|all)\b", lowered)
        return IntentResult("github_pr_list", 0.84, {"state": state_match.group(1) if state_match else "open"}, "rules", "github pr list request")
    pr_match = re.fullmatch(
        r"(?:create|open)\s+(?:a\s+)?(?:github\s+)?(?:pull\s+request|pr)(?:\s+(?:titled|called|for))?\s*(?P<title>.+)?",
        text,
        flags=re.IGNORECASE,
    )
    if pr_match and _clean_slot(pr_match.groupdict().get("title", "")):
        return IntentResult("github_pr_create", 0.86, {"title": _strip_quotes(pr_match.group("title"))}, "rules", "github pr create request")
    issue_match = re.fullmatch(
        r"(?:create|open)\s+(?:a\s+)?(?:github\s+)?issue(?:\s+(?:titled|called|for))?\s*(?P<title>.+)?",
        text,
        flags=re.IGNORECASE,
    )
    if issue_match and _clean_slot(issue_match.groupdict().get("title", "")):
        return IntentResult("github_issue_create", 0.86, {"title": _strip_quotes(issue_match.group("title"))}, "rules", "github issue request")
    return None


def _classify_ad_campaign(text: str) -> IntentResult | None:
    lowered = text.lower()
    has_ad_word = re.search(r"\b(?:ad|ads|advert|advertisement|advertising|promo|promotion)\b", lowered)
    has_marketing_campaign = re.search(r"\bmarketing\s+campaign\b|\bcampaign\s+(?:ad|ads|copy|post|creative)\b", lowered)
    if not has_ad_word and not has_marketing_campaign:
        return None
    if not re.search(r"\b(?:make|create|draft|write|generate|prepare|post|publish|send|queue|run|launch|advertise)\b", lowered):
        return None

    post_requested = bool(re.search(r"\b(?:post|publish|send|queue|run|launch)\b", lowered))
    product = _extract_ad_product(text)
    if not product:
        return None

    slots: dict[str, Any] = {"product": product}
    connector, target = _extract_ad_destination(text)
    if connector:
        slots["connector"] = connector
        slots["platform"] = connector
    if target:
        slots["target"] = target
    campaign_match = re.search(r"\bcampaign\s+#?(?P<id>\d+)\b", lowered)
    if campaign_match:
        slots["campaign_id"] = int(campaign_match.group("id"))
    audience = _extract_after_marker(text, ("for audience", "for users", "targeting"))
    if audience and audience.lower() != product.lower():
        slots["audience"] = audience
    return IntentResult(
        "post_ad_campaign" if post_requested else "draft_ad_campaign",
        0.9 if post_requested else 0.88,
        slots,
        "rules",
        "marketing ad request",
    )


def _classify_visual_asset(text: str) -> IntentResult | None:
    lowered = text.lower()
    if "illustrator" in lowered:
        return None
    logo_match = re.fullmatch(
        r"(?:generate|create|make|draw|render|design|mock\s+up)\s+(?P<prompt>(?:an?\s+)?(?:logo|brand\s+mark|logomark)(?:\s+(?:of|for|about|showing))?\s+.+)",
        text,
        flags=re.IGNORECASE,
    )
    if logo_match:
        prompt = _normalize_visual_prompt(logo_match.group("prompt"))
        return IntentResult("generate_image", 0.9, {"prompt": prompt}, "rules", "logo generation phrasing")
    patterns = (
        r"(?:generate|create|make|draw|render|design|mock\s+up)\s+(?:an?\s+)?(?:image|picture|photo|art|illustration|logo|brand\s+mark|logomark|mockup)\s+(?:of|for|about|showing|as)?\s*(?P<prompt>.+)",
        r"(?:generate|create|make|draw|render|design|mock\s+up)\s+(?:an?\s+)?(?P<prompt>.+?\b(?:image|picture|photo|art|illustration|logo|brand\s+mark|logomark|mockup)\b.*)",
    )
    for pattern in patterns:
        match = re.fullmatch(pattern, text, flags=re.IGNORECASE)
        if match:
            prompt = _normalize_visual_prompt(match.group("prompt"))
            if prompt and any(hint in lowered for hint in VISUAL_HINTS):
                return IntentResult("generate_image", 0.88, {"prompt": prompt}, "rules", "visual asset verb and noun")
    return None


def _classify_academic_project(text: str) -> IntentResult | None:
    lowered = text.lower()
    if not re.search(r"\b(?:final\s+year|research\s+paper|paper|project\s+proposal|proposal|literature\s+review|thesis|dissertation|seminar)\b", lowered):
        return None
    patterns = (
        r"(?:help\s+me\s+)?(?:write|draft|prepare|create|generate|make)\s+(?:my\s+|a\s+|an\s+)?(?P<kind>final\s+year\s+project|research\s+paper|project\s+proposal|proposal|literature\s+review|thesis|dissertation|seminar\s+paper)\s+(?:on|about|for)?\s*(?P<topic>.+)",
        r"(?:research\s+and\s+)?(?:write|draft|prepare)\s+(?:a\s+|an\s+)?(?P<kind>paper|project|proposal)\s+(?:on|about|for)\s+(?P<topic>.+)",
        r"(?P<kind>final\s+year\s+project|research\s+paper|project\s+proposal|literature\s+review|thesis)\s+(?:on|about|for)\s+(?P<topic>.+)",
    )
    for pattern in patterns:
        match = re.fullmatch(pattern, text, flags=re.IGNORECASE)
        if not match:
            continue
        topic = _clean_slot(match.group("topic"))
        if not topic or topic.lower() in {"it", "this", "that"}:
            continue
        kind = _clean_slot(match.group("kind"))
        return IntentResult(
            "academic_project",
            0.9,
            {"topic": topic, "kind": _academic_kind(kind), "formats": ["md", "docx", "pdf"], "citation_style": "APA"},
            "rules",
            "academic drafting request",
        )
    return None


def _classify_project_ideas(text: str) -> IntentResult | None:
    lowered = text.lower()
    if not re.search(r"\b(?:idea|ideas|what\s+to\s+build|build\s+next|project\s+to\s+build|app\s+idea|startup\s+idea)\b", lowered):
        return None
    patterns = (
        r"(?:what\s+should\s+i\s+build\s+next|what\s+to\s+build\s+next)(?:\s+(?:for|about|around)\s+(?P<context>.+))?",
        r"(?:give\s+me\s+an?\s+idea\s+on\s+what\s+to\s+build\s+next)(?:\s+(?:for|about|around)\s+(?P<context>.+))?",
        r"(?:give\s+me|suggest|recommend|find|research|look\s+for)\s+(?:some\s+|an?\s+|the\s+)?(?:project\s+|app\s+|startup\s+|software\s+)?ideas?(?:\s+(?:on|for|about|around)\s+(?P<context>.+))?",
    )
    for pattern in patterns:
        match = re.fullmatch(pattern, text, flags=re.IGNORECASE)
        if not match:
            continue
        context = _clean_slot((match.groupdict().get("context") or "AI-assisted everyday tools for individuals, small teams, and SMBs"))
        if context.lower() in {"what to build next", "what i should build next"}:
            context = "AI-assisted everyday tools for individuals, small teams, and SMBs"
        return IntentResult(
            "project_ideas",
            0.9,
            {"context": context, "audience": "individuals, small teams, and SMBs"},
            "rules",
            "project idea request must use research-backed ideation",
        )
    return None


def _classify_coding_project(text: str) -> IntentResult | None:
    lowered = text.lower()
    if re.match(r"^(?:create|queue|add)\s+(?:a\s+)?task\b", lowered):
        return None
    if any(hint in lowered for hint in VISUAL_HINTS) and not any(hint in lowered for hint in SOFTWARE_HINTS):
        return None
    patterns = (
        r"(?:i\s+(?:want|need)\s+(?:you|friday)\s+to\s+|can\s+you\s+|could\s+you\s+|please\s+|friday\s+)?(?:build|create|make|develop|scaffold|spin\s+up|implement|code|program|put\s+together|set\s+up)\s+(?:me\s+)?(?P<request>.+)",
        r"(?:i\s+(?:need|want)\s+)(?P<request>(?:an?\s+)?(?:web\s+app|app|application|api|dashboard|website|software|tool|system|platform|backend|frontend|saas|program|project)\b.+)",
        r"(?:start|launch|begin)\s+(?:a\s+)?(?:coding|programming|software)\s+(?:project|task)\s+(?:for|to)?\s*(?P<request>.+)",
    )
    for pattern in patterns:
        match = re.fullmatch(pattern, text, flags=re.IGNORECASE)
        if not match:
            continue
        request = _clean_slot(match.group("request"))
        if request and _looks_like_software_request(request):
            return IntentResult(
                "start_coding_project",
                0.88,
                {"request": request},
                "rules",
                "software build verb with project description",
            )
    return None


def _classify_agent_task(text: str) -> IntentResult | None:
    patterns = (
        r"(?:get|have|tell|ask)\s+(?:the\s+)?(?P<agent>team|agents?|research(?:\s+analyst)?|qa(?:\s+engineer)?|developer|dev|senior\s+developer|product\s+manager)\s+(?:agent\s+)?(?:to\s+)?(?P<title>.+)",
        r"(?:delegate|assign|give)\s+(?P<title>.+?)\s+to\s+(?:the\s+)?(?P<agent>team|agents?|research(?:\s+analyst)?|qa(?:\s+engineer)?|developer|dev|senior\s+developer|product\s+manager)(?:\s+agent)?",
        r"(?:put|add|queue)\s+(?P<title>.+?)\s+(?:on|in)\s+(?:the\s+)?(?:agent\s+)?(?:queue|backlog)",
    )
    for pattern in patterns:
        match = re.fullmatch(pattern, text, flags=re.IGNORECASE)
        if not match:
            continue
        title = _clean_slot(match.group("title"))
        if re.fullmatch(r"task\s+#?\d+", title, flags=re.IGNORECASE):
            return None
        if not title:
            continue
        slots = {"title": title}
        agent = _clean_slot(match.groupdict().get("agent", ""))
        if agent:
            slots["agent_id"] = agent
        return IntentResult("create_agent_task", 0.86, slots, "rules", "delegation phrasing")
    return None


def _classify_diagnostics(text: str) -> IntentResult | None:
    lowered = text.lower()
    if not re.search(r"\b(?:diagnostic|diagnostics|diagnose|health\s+check|self\s+test|self\s+diagnostic|system\s+check|doctor)\b", lowered):
        return None
    if re.fullmatch(r"(?:what|why|how|when|where|who)\b.+", lowered):
        return None
    if not re.search(r"\b(?:run|start|perform|do|check|scan|test|diagnose|give|have|tell|ask)\b", lowered):
        return None
    profile = "deep" if re.search(r"\b(?:deep|full|all|everything|complete)\b", lowered) else "quick" if re.search(r"\b(?:quick|fast|light)\b", lowered) else "standard"
    return IntentResult(
        "run_diagnostics",
        0.92,
        {
            "title": "Run Friday diagnostics",
            "description": text,
            "profile": profile,
        },
        "rules",
        "explicit diagnostics request",
    )


def _classify_task_status(text: str) -> IntentResult | None:
    lowered = text.lower()
    if re.search(r"\b(?:agent|agents|team|tasks?|friday)\b", lowered):
        status = _task_status(lowered)
        if re.search(r"\b(?:what|show|list|any|current|currently|working\s+on|doing|progress)\b", lowered) and re.search(
            r"\b(?:tasks?|working\s+on|doing|progress|queue)\b", lowered
        ):
            return IntentResult("list_tasks", 0.82, {"status": status or ("active" if "working on" in lowered else "")}, "rules", "task status query")
        if re.fullmatch(r"(?:team|agent|agents|background agents)\s+(?:status|state|running)", lowered):
            return IntentResult("agent_status", 0.86, {}, "rules", "agent status query")
    return None


def _classify_reminder(text: str) -> IntentResult | None:
    patterns = (
        r"(?:remind\s+me\s+to|add\s+reminder\s+to|create\s+reminder\s+to|set\s+reminder\s+to)\s+(?P<body>.+)",
        r"(?:remind\s+me|add\s+reminder|create\s+reminder|set\s+reminder)\s+(?P<body>.+)",
        r"(?:do\s+not|don't)\s+let\s+me\s+forget\s+(?:to\s+)?(?P<body>.+)",
    )
    for pattern in patterns:
        match = re.fullmatch(pattern, text, flags=re.IGNORECASE)
        if match:
            title, when = _split_when(match.group("body"))
            if title:
                return IntentResult("create_reminder", 0.9, {"title": title, "due_at": when}, "rules", "reminder phrasing")
    return None


def _classify_workspace(text: str) -> IntentResult | None:
    lowered = text.lower()
    match = re.fullmatch(r"(?:search|find|look\s+through)\s+(?:my\s+)?(?:workspace|project|codebase)\s+(?:for\s+)?(?P<query>.+)", text, flags=re.IGNORECASE)
    if match:
        return IntentResult("search_workspace", 0.86, {"query": _clean_slot(match.group("query"))}, "rules", "workspace search")
    if re.fullmatch(r"(?:analyze|map|understand|inspect)\s+(?:my\s+)?(?:workspace|project|codebase)(?:\s+deeply|\s+architecture)?", lowered):
        return IntentResult("workspace_analyze", 0.84, {}, "rules", "workspace analysis")
    if re.search(r"\b(?:code\s+quality|codebase\s+standards|coding\s+standards|code\s+hygiene|architecture\s+hygiene)\b", lowered):
        focus = re.sub(r"^(?:check|scan|run|analyze|audit)\s+(?:the\s+)?", "", text, flags=re.IGNORECASE).strip()
        return IntentResult("codebase_standards", 0.84, {"focus": focus}, "rules", "code standards request")
    return None


def _classify_web_search(text: str) -> IntentResult | None:
    match = re.fullmatch(r"(?:search|google|look\s+up|find\s+online|browse)\s+(?:for\s+)?(?P<query>.+)", text, flags=re.IGNORECASE)
    if match:
        query = _clean_slot(match.group("query"))
        if query:
            return IntentResult("web_search", 0.86, {"query": query}, "rules", "explicit web search")
    return None


_RULE_CLASSIFIERS: tuple[RuleClassifier, ...] = (
    _classify_3d_model,
    _classify_git,
    _classify_ad_campaign,
    _classify_visual_asset,
    _classify_academic_project,
    _classify_project_ideas,
    _classify_coding_project,
    _classify_diagnostics,
    _classify_agent_task,
    _classify_task_status,
    _classify_reminder,
    _classify_workspace,
    _classify_web_search,
)


def _classify_with_llm(text: str) -> IntentResult:
    prompt = _llm_prompt(text)
    try:
        raw = llm.ask_simple(prompt, retries=1) or ""
    except Exception:
        return IntentResult(source="llm", reason="LLM classifier failed")
    data = _parse_json_object(raw)
    if not isinstance(data, dict):
        return IntentResult(source="llm", reason="LLM classifier returned non-JSON")
    intent = str(data.get("intent") or "none").strip()
    if intent not in INTENT_SPECS:
        return IntentResult(source="llm", reason=f"LLM returned unsupported intent {intent}")
    confidence = _float(data.get("confidence"), 0.0)
    slots = data.get("slots") if isinstance(data.get("slots"), dict) else {}
    reason = str(data.get("reason") or "semantic classifier").strip()
    return IntentResult(intent=intent, confidence=confidence, slots=slots, source="llm", reason=reason)


def _llm_prompt(text: str) -> str:
    intents = "\n".join(
        f"- {spec.name}: {spec.description}; required slots: {', '.join(spec.required_slots) or 'none'}"
        for spec in INTENT_SPECS.values()
    )
    return (
        "Classify the user's command into one executable intent for a local assistant.\n"
        "Return only compact JSON with keys: intent, confidence, slots, reason.\n"
        "Use intent \"none\" with confidence 0 when the user is asking a general question, chatting, or the action is ambiguous.\n"
        "Do not invent missing required slots. Do not classify destructive actions.\n"
        "Supported intents:\n"
        f"{intents}\n\n"
        f"User command: {json.dumps(text)}"
    )


def _semantic_intents_enabled() -> bool:
    return bool(config_value("intent_llm_enabled", True))


def _looks_actionable(text: str) -> bool:
    lowered = text.lower()
    if re.fullmatch(r"(?:what|why|how|when|where|who)\b.+", lowered) and not re.search(
        r"\b(tasks?|agents?|working\s+on|progress|search|look\s+up|find)\b", lowered
    ):
        return False
    if re.search(r"\b(?:can|could|please|need|want|have|tell|get|ask|let|make|create|build|start|search|generate|write|draft|prepare|remind|schedule|delegate|assign|queue|clone|commit|push|pull|checkout|export)\b", lowered):
        return True
    return any(hint in lowered for hint in ACTIONABLE_HINTS)


def _looks_like_software_request(text: str) -> bool:
    lowered = text.lower()
    if re.search(r"\b(?:message|email|reminder|calendar|contact|image|picture|photo|logo|illustration)\b", lowered) and not re.search(
        r"\b(?:app|application|web|website|software|dashboard|api|frontend|backend|code|program)\b", lowered
    ):
        return False
    return any(hint in lowered for hint in SOFTWARE_HINTS)


def _extract_ad_product(text: str) -> str:
    patterns = (
        r"(?:for|about|promoting|promote|advertise)\s+(?P<product>.+?)(?:\s+(?:to|on|via|through|in)\s+(?:discord|slack|telegram|whatsapp|gmail|email|notion|web)\b.*)?$",
        r"(?:ad|ads|advertisement|advertising|promo|promotion|marketing\s+campaign)\s+(?:for|about)\s+(?P<product>.+?)(?:\s+(?:to|on|via|through|in)\s+.+)?$",
    )
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            product = _clean_slot(match.group("product"))
            product = re.sub(r"\s+(?:campaign\s+)?#?\d+$", "", product, flags=re.IGNORECASE).strip()
            if product:
                return product
    product = re.sub(
        r"^(?:make|create|draft|write|generate|prepare|post|publish|send|queue|run|launch|advertise)\s+(?:an?\s+|some\s+)?(?:ad|ads|advertisement|advertising|promo|promotion|marketing\s+campaign|campaign)\s*",
        "",
        text,
        flags=re.IGNORECASE,
    )
    product = re.sub(r"\s+(?:to|on|via|through|in)\s+(?:discord|slack|telegram|whatsapp|gmail|email|notion|web)\b.*$", "", product, flags=re.IGNORECASE)
    return _clean_slot(product)


def _extract_ad_destination(text: str) -> tuple[str, str]:
    lowered = text.lower()
    connector_match = re.search(r"\b(discord|slack|telegram|whatsapp|gmail|email|notion|web)\b", lowered)
    connector = connector_match.group(1) if connector_match else ""
    if connector == "email":
        connector = "gmail"
    target = ""
    if connector_match:
        after = text[connector_match.end() :].strip(" ,.!?:;")
        target = _clean_slot(re.sub(r"^(?:channel|room|chat|to|at|in)\s+", "", after, flags=re.IGNORECASE))
    explicit = re.search(r"\b(?:to|on|via|through|in)\s+(?P<target>#[A-Za-z0-9_\-]+|[A-Za-z0-9_.@+\-/]+)$", text, flags=re.IGNORECASE)
    if explicit and not connector:
        target = _clean_slot(explicit.group("target"))
    return connector, target


def _extract_after_marker(text: str, markers: tuple[str, ...]) -> str:
    lowered = text.lower()
    for marker in markers:
        index = lowered.find(marker)
        if index >= 0:
            return _clean_slot(text[index + len(marker) :])
    return ""


def _normalize_slots(intent: str, slots: dict[str, Any]) -> dict[str, Any]:
    normalized = {str(key).strip(): value for key, value in (slots or {}).items() if str(key).strip()}
    if intent == "start_coding_project":
        request = _slot_text(normalized, "request", "project_description", "description", "goal", "title")
        if request:
            normalized["request"] = request
    if intent == "project_ideas":
        context = _slot_text(normalized, "context", "topic", "query", "request")
        if context:
            normalized["context"] = context
    if intent == "create_agent_task":
        title = _slot_text(normalized, "title", "task", "goal", "request")
        if title:
            normalized["title"] = title
    if intent == "run_diagnostics":
        profile = _slot_text(normalized, "profile", "scope", "request", "description").lower()
        if re.search(r"\b(?:deep|full|all|everything|complete)\b", profile):
            normalized["profile"] = "deep"
        elif re.search(r"\b(?:quick|fast|light)\b", profile):
            normalized["profile"] = "quick"
        else:
            normalized["profile"] = _slot_text(normalized, "profile") or "standard"
    if intent == "create_reminder":
        title = _slot_text(normalized, "title", "task", "reminder")
        if title:
            normalized["title"] = title
    if intent == "generate_image":
        prompt = _slot_text(normalized, "prompt", "description", "target")
        if prompt:
            normalized["prompt"] = prompt
    if intent in {"draft_ad_campaign", "post_ad_campaign"}:
        product = _slot_text(normalized, "product", "name", "target", "request")
        if product:
            normalized["product"] = product
    if intent == "academic_project":
        topic = _slot_text(normalized, "topic", "title", "target", "request")
        if topic:
            normalized["topic"] = topic
        normalized["kind"] = _academic_kind(_slot_text(normalized, "kind", "document_type"))
    if intent == "create_3d_model":
        prompt = _slot_text(normalized, "prompt", "description", "target", "request")
        if prompt:
            normalized["prompt"] = _clean_model_prompt(prompt)
        normalized["formats"] = _model_formats(normalized.get("formats") or normalized.get("format") or [])
        quality = _model_quality(_slot_text(normalized, "quality", "mode", "prompt"))
        if quality:
            normalized["quality"] = quality
    if intent == "git_clone":
        repo = _slot_text(normalized, "repo", "url", "target")
        if repo:
            normalized["repo"] = repo
    if intent == "git_checkout":
        branch = _slot_text(normalized, "branch", "target")
        if branch:
            normalized["branch"] = branch
    if intent == "git_add":
        paths = normalized.get("paths") or normalized.get("path") or normalized.get("target")
        if paths:
            normalized["paths"] = paths
    if intent == "git_commit":
        message = _slot_text(normalized, "message", "title", "target")
        if message:
            normalized["message"] = message
    if intent in {"github_pr_create", "github_issue_create"}:
        title = _slot_text(normalized, "title", "target")
        if title:
            normalized["title"] = title
    return normalized


def _clean_command(text: str) -> str:
    cleaned = re.sub(r"\s+", " ", str(text or "")).strip(" ,.!?:;")
    names = str(config_value("attention_names", "friday,computer,jarvis")).split(",")
    names.extend(["jarvis", "jervis"])
    for name in sorted({item.strip().lower() for item in names if item.strip()}, key=len, reverse=True):
        cleaned = re.sub(rf"^(?:hey\s+)?{re.escape(name)}\b[\s,.:;!-]*", "", cleaned, flags=re.IGNORECASE)
    return cleaned.strip(" ,.!?:;")


def _normalize_coding_request(request: str) -> str:
    cleaned = _clean_slot(request)
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


def _clean_slot(value: Any) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip(" ,.!?:;")
    return text


def _normalize_visual_prompt(value: Any) -> str:
    text = _clean_slot(value)
    text = re.sub(r"^(?:me\s+)", "", text, flags=re.IGNORECASE).strip()
    text = re.sub(r"^i\s+can\s+use\s+(?:as|for)\s+", "", text, flags=re.IGNORECASE).strip()
    return text.strip(" ,.!?:;")


def _clean_model_prompt(value: Any) -> str:
    text = _clean_slot(value)
    text = re.sub(r"\s+(?:as|to|into)\s+(?:an?\s+)?(?:obj|stl|gltf|glb)(?:\s+(?:file|model|mesh))?$", "", text, flags=re.IGNORECASE)
    text = re.sub(r"^(?:(?:photo\s*realistic|photorealistic|realistic|zbrush\s+quality|studio|high[-\s]?quality|blender|pbr|cinematic)\s+)+", "", text, flags=re.IGNORECASE)
    text = re.sub(r"^(?:a|an)\s+(?:3d|three[-\s]?d)\s+(?:model|asset|mesh|object)\s+(?:of|for)\s+", "", text, flags=re.IGNORECASE)
    return text.strip(" ,.!?:;")


def _extract_model_formats(text: str) -> list[str]:
    formats = re.findall(r"\b(obj|stl|gltf|glb)\b", str(text or ""), flags=re.IGNORECASE)
    return _model_formats(formats)


def _model_formats(value: Any) -> list[str]:
    if isinstance(value, str):
        raw = re.split(r"[, ]+", value)
    elif isinstance(value, (list, tuple, set)):
        raw = list(value)
    else:
        raw = []
    allowed = {"obj", "stl", "gltf", "glb"}
    formats = [str(item).strip().lower().lstrip(".") for item in raw if str(item).strip()]
    return [item for item in formats if item in allowed] or ["obj", "stl", "gltf", "glb"]


def _model_quality(value: Any) -> str:
    text = str(value or "").lower()
    if re.search(r"\b(?:photo\s*real|photorealistic|realistic|studio|blender|zbrush|sculpt|production|cinematic|pbr|high[-\s]?quality)\b", text):
        return "studio"
    return ""


def _strip_quotes(value: Any) -> str:
    return _clean_slot(value).strip("\"'")


def _slot_text(slots: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = slots.get(key)
        if isinstance(value, (list, tuple)):
            value = " ".join(str(item) for item in value if str(item).strip())
        text = _clean_slot(value)
        if text:
            return text
    return ""


def _slot_int(slots: dict[str, Any], key: str, default: int) -> int:
    try:
        return int(slots.get(key) or default)
    except (TypeError, ValueError):
        return default


def _task_status(text: str) -> str:
    lowered = str(text or "").lower()
    for status in TASK_STATUSES:
        if re.search(rf"\b{status}\b", lowered):
            return status
    if re.search(r"\b(?:current|currently|working\s+on|in\s+progress|progress)\b", lowered):
        return "active"
    return ""


def _agent_id(text: str) -> str:
    lowered = re.sub(r"[^a-z0-9]+", " ", str(text or "").lower()).strip()
    aliases = {
        "research": "research_analyst",
        "research analyst": "research_analyst",
        "qa": "qa_engineer",
        "qa engineer": "qa_engineer",
        "quality": "qa_engineer",
        "quality engineer": "qa_engineer",
        "developer": "senior_developer",
        "dev": "senior_developer",
        "senior developer": "senior_developer",
        "product": "product_manager",
        "product manager": "product_manager",
        "doctor": "doctor",
        "diagnostics": "doctor",
        "diagnostic": "doctor",
    }
    return aliases.get(lowered, "" if lowered in {"team", "agent", "agents"} else lowered.replace(" ", "_"))


def _academic_kind(text: str) -> str:
    lowered = re.sub(r"[^a-z0-9]+", "_", str(text or "").lower()).strip("_")
    aliases = {
        "final_year": "final_year_project",
        "final_year_project": "final_year_project",
        "project": "final_year_project",
        "thesis": "final_year_project",
        "dissertation": "final_year_project",
        "paper": "research_paper",
        "research_paper": "research_paper",
        "seminar_paper": "research_paper",
        "literature_review": "research_paper",
        "proposal": "proposal",
        "project_proposal": "proposal",
    }
    return aliases.get(lowered, lowered or "final_year_project")


def _academic_formats(value: Any) -> list[str]:
    if isinstance(value, str):
        raw = value.replace(";", ",").split(",")
    elif isinstance(value, (list, tuple, set)):
        raw = list(value)
    else:
        raw = ["md", "docx", "pdf"]
    allowed = {"md", "docx", "pdf"}
    formats = [str(item).strip().lower().lstrip(".") for item in raw if str(item).strip()]
    return [item for item in formats if item in allowed] or ["md", "docx", "pdf"]


def _split_when(raw: str) -> tuple[str, str]:
    text = _clean_slot(raw)
    patterns = [
        r"\s+(tomorrow|today|tonight)$",
        r"\s+(on\s+\w+(?:\s+\d{1,2})?)$",
        r"\s+(at\s+\d{1,2}(?::\d{2})?\s*(?:am|pm)?)$",
        r"\s+(by\s+.+)$",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return text[: match.start()].strip(" .,!?:;") or text, match.group(1).strip()
    return text, ""


def _parse_json_object(raw: str) -> dict[str, Any] | None:
    text = str(raw or "").strip()
    if not text:
        return None
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if not match:
            return None
        try:
            value = json.loads(match.group(0))
        except json.JSONDecodeError:
            return None
    return value if isinstance(value, dict) else None


def _clarifying_question(intent: str, missing: list[str]) -> str:
    if intent == "start_coding_project":
        return "Tell me what you want built."
    if intent == "project_ideas":
        return "Tell me the audience or problem space to research for project ideas."
    if intent == "create_agent_task":
        return "Tell me what task to give the agents."
    if intent == "create_reminder":
        return "Tell me what to remind you about."
    if intent == "generate_image":
        return "Tell me what image to generate."
    if intent == "draft_ad_campaign":
        return "Tell me what product or offer to advertise."
    if intent == "post_ad_campaign":
        if "connector" in missing:
            return "Tell me where to post the ad, like Discord, Slack, Gmail, WhatsApp, or Telegram."
        if "target" in missing:
            return "Tell me the channel, address, or destination for the ad."
        return "Tell me what product or offer to advertise."
    if intent == "create_3d_model":
        return "Tell me what 3D model to generate."
    if intent == "git_clone":
        return "Tell me which repository to clone."
    if intent == "git_checkout":
        return "Tell me which branch to checkout."
    if intent == "git_add":
        return "Tell me which files to stage."
    if intent == "git_commit":
        return "Tell me the commit message."
    if intent in {"github_pr_create", "github_issue_create"}:
        return "Tell me the title."
    if missing:
        return f"Tell me the {missing[0]}."
    return "Tell me a little more."


def _float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
