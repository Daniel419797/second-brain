"""Procedural memory for reusable v2 agent skills."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
import threading
from pathlib import Path
from typing import Any

from core.config import DATA_DIR, config_value, ensure_runtime_dirs

SKILLS_PATH = DATA_DIR / "skill_library.json"
EXAMPLES_PATH = DATA_DIR / "skill_examples.json"
_LOCK = threading.Lock()

BUILTIN_SKILLS: dict[str, dict[str, Any]] = {
    "figma_operator": {
        "name": "Figma operator",
        "description": "Operate Figma through browser/app context, focusing on files, frames, layers, comments, and export workflows.",
        "agent_id": "ui_ux_designer",
        "tags": ["figma", "design", "operator"],
        "pattern": "Open Figma, inspect the visible file or workspace context, identify the current frame/layer goal, prefer DOM/accessibility controls when available, and pause before destructive design changes.",
    },
    "vscode_debugger": {
        "name": "VS Code debugger",
        "description": "Use VS Code like a coding assistant: inspect files, terminals, errors, tests, and debug state.",
        "agent_id": "senior_developer",
        "tags": ["vscode", "debugging", "coding"],
        "pattern": "Check the active workspace, read relevant files, run focused tests where safe, explain failure evidence, then propose the smallest patch and verification command.",
    },
    "research_writer": {
        "name": "Research writer",
        "description": "Collect sources, compare claims, and produce clear research notes with evidence.",
        "agent_id": "research_analyst",
        "tags": ["research", "writing", "sources"],
        "pattern": "Use primary sources when possible, record citations or local evidence, separate facts from inference, summarize tradeoffs, and hand off only reusable findings.",
    },
    "security_auditor": {
        "name": "Security auditor",
        "description": "Run defensive, scoped checks and generate hardening recommendations.",
        "agent_id": "cybersecurity_analyst",
        "tags": ["security", "audit", "defensive"],
        "pattern": "Confirm scope first, use non-invasive checks, report evidence and severity, avoid exploit payloads, and recommend concrete hardening steps.",
    },
    "youtube_summarizer": {
        "name": "YouTube summarizer",
        "description": "Extract transcripts or notes from YouTube and turn them into lessons.",
        "agent_id": "research_analyst",
        "tags": ["youtube", "summary", "learning"],
        "pattern": "Fetch transcript when available, identify the core claims and steps, remove filler, store reusable lessons, and mark uncertainty when transcript data is missing.",
    },
    "react_app_builder": {
        "name": "React app builder",
        "description": "Build polished React/Next.js interfaces consistent with the existing app.",
        "agent_id": "frontend_developer",
        "tags": ["react", "nextjs", "frontend"],
        "pattern": "Inspect existing components and styles, implement the smallest cohesive UI slice, keep responsive layout stable, run build/tests, and avoid unrelated refactors.",
    },
}


def add_skill(
    name: str,
    description: str,
    pattern: str,
    *,
    agent_id: str = "jarvis",
    tags: list[str] | None = None,
    source: str = "manual",
) -> str:
    """Store or update a reusable procedure."""
    cleaned_name = _clean(name) or "Unnamed skill"
    cleaned_pattern = _clean_multiline(pattern)
    skill_id = _skill_id(agent_id, cleaned_name)
    now = _now()
    with _LOCK:
        skills = _load_json(SKILLS_PATH, [])
        for skill in skills:
            if skill.get("id") == skill_id:
                skill.update(
                    {
                        "name": cleaned_name,
                        "description": _clean(description),
                        "pattern": cleaned_pattern,
                        "agent_id": _clean(agent_id) or "jarvis",
                        "tags": sorted(set(tags or [])),
                        "source": _clean(source) or "manual",
                        "enabled": bool(skill.get("enabled", True)),
                        "updated_at": now,
                    }
                )
                _save_json(SKILLS_PATH, skills)
                return skill_id
        skills.append(
            {
                "id": skill_id,
                "name": cleaned_name,
                "description": _clean(description),
                "pattern": cleaned_pattern,
                "agent_id": _clean(agent_id) or "jarvis",
                "tags": sorted(set(tags or [])),
                "source": _clean(source) or "manual",
                "enabled": True,
                "usage_count": 0,
                "created_at": now,
                "updated_at": now,
                "last_used_at": "",
            }
        )
        _save_json(SKILLS_PATH, skills)
    return skill_id


def record_example(agent_id: str, title: str, outcome: str, *, tags: list[str] | None = None) -> dict[str, Any] | None:
    """Record a task example and promote repeated patterns into skills."""
    signature = _signature(title)
    if not signature:
        return None
    now = _now()
    example = {
        "agent_id": _clean(agent_id) or "jarvis",
        "signature": signature,
        "title": _clean(title),
        "outcome": _clean_multiline(outcome)[:1000],
        "tags": sorted(set(tags or [])),
        "created_at": now,
    }
    threshold = int(config_value("procedural_skill_min_examples", 5))
    with _LOCK:
        examples = _load_json(EXAMPLES_PATH, [])
        examples.append(example)
        _save_json(EXAMPLES_PATH, examples[-500:])
        matching = [
            item
            for item in examples
            if item.get("agent_id") == example["agent_id"] and item.get("signature") == signature
        ]
    if len(matching) < threshold:
        return None
    skill_name = f"{example['agent_id']} pattern: {signature.replace('_', ' ')}"
    pattern = _build_pattern(matching[-threshold:])
    skill_id = add_skill(
        skill_name,
        f"Reusable pattern learned from {len(matching)} similar tasks.",
        pattern,
        agent_id=example["agent_id"],
        tags=sorted(set(example["tags"] + signature.split("_"))),
        source="consolidation",
    )
    return get_skill(skill_id)


def search(query: str, *, agent_id: str | None = None, limit: int = 3) -> list[dict[str, Any]]:
    terms = _terms(query)
    if not terms:
        return []
    skills = all_skills()
    scored: list[tuple[float, dict[str, Any]]] = []
    for skill in skills:
        if skill.get("enabled") is False:
            continue
        if agent_id and skill.get("agent_id") not in {agent_id, "jarvis"}:
            continue
        haystack = " ".join(
            [
                str(skill.get("name") or ""),
                str(skill.get("description") or ""),
                str(skill.get("pattern") or ""),
                " ".join(str(tag) for tag in skill.get("tags") or []),
            ]
        )
        skill_terms = _terms(haystack)
        overlap = len(terms & skill_terms)
        if not overlap:
            continue
        score = overlap * 3 + float(skill.get("usage_count") or 0) * 0.2
        scored.append((score, skill))
    scored.sort(key=lambda item: (-item[0], str(item[1].get("updated_at") or "")), reverse=False)
    selected = [skill for _score, skill in scored[: max(1, int(limit))]]
    for skill in selected:
        reinforce_skill(str(skill.get("id") or ""))
    return selected


def prompt_prefix(query: str, *, agent_id: str | None = None, limit: int | None = None) -> str:
    if limit is None:
        limit = int(config_value("procedural_skill_prompt_limit", 3))
    skills = search(query, agent_id=agent_id, limit=limit)
    if not skills:
        return ""
    lines = ["Relevant procedural skills:"]
    for skill in skills:
        pattern = _clean_multiline(skill.get("pattern", ""))[:500]
        lines.append(f"- {skill.get('name')}: {pattern}")
    return "\n".join(lines)


def reinforce_skill(skill_id: str) -> bool:
    if not skill_id:
        return False
    with _LOCK:
        skills = _load_json(SKILLS_PATH, [])
        for skill in skills:
            if skill.get("id") == skill_id:
                skill["usage_count"] = int(skill.get("usage_count") or 0) + 1
                skill["last_used_at"] = _now()
                _save_json(SKILLS_PATH, skills)
                return True
    return False


def get_skill(skill_id: str) -> dict[str, Any] | None:
    for skill in all_skills():
        if skill.get("id") == skill_id:
            return skill
    return None


def all_skills() -> list[dict[str, Any]]:
    return [_normalize_skill(skill) for skill in list(_load_json(SKILLS_PATH, []))]


def install_builtin(skill_key: str = "all") -> list[dict[str, Any]]:
    """Install one or all built-in reusable skills."""
    keys = list(BUILTIN_SKILLS) if str(skill_key or "all").lower() in {"", "all", "*"} else [str(skill_key).strip().lower()]
    installed = []
    for key in keys:
        spec = BUILTIN_SKILLS.get(key)
        if not spec:
            continue
        skill_id = add_skill(
            spec["name"],
            spec["description"],
            spec["pattern"],
            agent_id=spec.get("agent_id", "jarvis"),
            tags=list(spec.get("tags") or []),
            source="builtin",
        )
        installed_skill = get_skill(skill_id)
        if installed_skill:
            installed.append(installed_skill)
    return installed


def enable_skill(skill_id: str, enabled: bool = True) -> dict[str, Any] | None:
    with _LOCK:
        skills = [_normalize_skill(skill) for skill in _load_json(SKILLS_PATH, [])]
        for skill in skills:
            if skill.get("id") == skill_id or _clean(skill.get("name", "")).lower() == _clean(skill_id).lower():
                skill["enabled"] = bool(enabled)
                skill["updated_at"] = _now()
                _save_json(SKILLS_PATH, skills)
                return skill
    return None


def disable_skill(skill_id: str) -> dict[str, Any] | None:
    return enable_skill(skill_id, False)


def skill_summary() -> dict[str, Any]:
    skills = all_skills()
    return {
        "total": len(skills),
        "enabled": len([skill for skill in skills if skill.get("enabled", True)]),
        "disabled": len([skill for skill in skills if skill.get("enabled") is False]),
        "builtins_available": list(BUILTIN_SKILLS),
        "skills": skills[:50],
    }


def wipe_all() -> None:
    with _LOCK:
        for path in [SKILLS_PATH, EXAMPLES_PATH]:
            if path.exists():
                path.unlink()


def _normalize_skill(skill: dict[str, Any]) -> dict[str, Any]:
    item = dict(skill or {})
    item.setdefault("enabled", True)
    item.setdefault("usage_count", 0)
    item.setdefault("tags", [])
    return item


def _build_pattern(examples: list[dict[str, Any]]) -> str:
    titles = "; ".join(_clean(item.get("title", "")) for item in examples[-3:])
    best_outcome = _clean_multiline(examples[-1].get("outcome", ""))
    return (
        "When this pattern appears, first restate the requested outcome, then produce the smallest concrete plan, "
        "call out risks, and identify the next tool or human approval needed.\n"
        f"Recent examples: {titles}\n"
        f"Most recent outcome: {best_outcome[:500]}"
    )


def _skill_id(agent_id: str, name: str) -> str:
    digest = hashlib.sha256(f"{agent_id}:{name}".encode("utf-8")).hexdigest()[:16]
    return f"skill_{digest}"


def _signature(text: str) -> str:
    stop = {"the", "and", "for", "with", "this", "that", "from", "into", "task", "please"}
    terms = [term for term in _terms(text) if term not in stop]
    if not terms:
        return ""
    return "_".join(sorted(terms)[:4])


def _terms(text: str) -> set[str]:
    return {part for part in re.split(r"[^a-z0-9_+.-]+", str(text).lower()) if len(part) > 2}


def _load_json(path: Path, default: Any) -> Any:
    ensure_runtime_dirs()
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _save_json(path: Path, value: Any) -> None:
    ensure_runtime_dirs()
    path.write_text(json.dumps(value, indent=2, ensure_ascii=True), encoding="utf-8")


def _clean(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _clean_multiline(value: Any) -> str:
    lines = [_clean(line) for line in str(value or "").splitlines()]
    return "\n".join(line for line in lines if line)


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds")
