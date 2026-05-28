"""User-facing local skill marketplace built on Friday's skill library."""

from __future__ import annotations

from typing import Any

from core import skill_library
from core.config import config_value

CATALOG: dict[str, dict[str, Any]] = {
    "figma_designer": {
        "name": "Figma designer",
        "description": "Operate Figma through browser/app context and produce UI design decisions.",
        "agent_id": "ui_ux_designer",
        "tags": ["figma", "design", "ui"],
        "pattern": "Inspect visible frames, use DOM/accessibility when available, ask before destructive changes, and record design rationale.",
        "permissions": ["browser_dom", "screenshot", "design_context"],
        "trust_level": "verified",
    },
    "gmail_operator": {
        "name": "Gmail operator",
        "description": "Draft, search, and organize Gmail through OAuth or web UI control.",
        "agent_id": "customer_support",
        "tags": ["gmail", "email", "office"],
        "pattern": "Prefer OAuth read APIs when configured. For sending or deleting messages, require approval and verify the result after the UI/API action.",
        "permissions": ["gmail_read", "gmail_draft"],
        "secret_envs": ["GMAIL_ADDRESS", "GMAIL_APP_PASSWORD"],
        "trust_level": "sandboxed",
    },
    "pdf_analyst": {
        "name": "PDF analyst",
        "description": "Read, summarize, compare, and extract actions from PDF files.",
        "agent_id": "research_analyst",
        "tags": ["pdf", "research", "documents"],
        "pattern": "Extract text structurally, cite page/source context when possible, summarize risks and action items, and store reusable facts.",
    },
    "video_summarizer": {
        "name": "Video summarizer",
        "description": "Summarize YouTube/video transcripts and produce notes or tasks.",
        "agent_id": "research_analyst",
        "tags": ["youtube", "video", "summary"],
        "pattern": "Fetch transcript when available, summarize key claims, separate facts from opinions, and create follow-up tasks when requested.",
        "permissions": ["web_read", "transcript_read"],
        "trust_level": "verified",
    },
    "github_release_operator": {
        "name": "GitHub release operator",
        "description": "Prepare branches, PRs, issues, and release evidence for owned repositories.",
        "agent_id": "devops",
        "tags": ["github", "git", "release", "ci"],
        "pattern": "Read repository state first, create small branches, require approval before push/PR writes, include test proof and rollback notes.",
        "permissions": ["git_read", "git_write_approval", "github_pr"],
        "secret_envs": ["GITHUB_TOKEN"],
        "trust_level": "sandboxed",
    },
    "render_deployer": {
        "name": "Render deployer",
        "description": "Inspect and operate Render deployment workflows when API credentials are configured.",
        "agent_id": "devops",
        "tags": ["render", "deploy", "backend"],
        "pattern": "Inspect service status and environment readiness, require deploy approval, trigger only configured owned services, then verify HTTPS and logs.",
        "permissions": ["deploy_read", "deploy_approval"],
        "secret_envs": ["RENDER_API_KEY"],
        "trust_level": "sandboxed",
    },
    "vercel_deployer": {
        "name": "Vercel deployer",
        "description": "Inspect and operate Vercel frontend deploy previews and production promotions.",
        "agent_id": "devops",
        "tags": ["vercel", "deploy", "frontend"],
        "pattern": "Check build settings and env readiness, create preview deployments first, require approval before production promotion, and record proof URLs.",
        "permissions": ["deploy_read", "deploy_approval"],
        "secret_envs": ["VERCEL_TOKEN"],
        "trust_level": "sandboxed",
    },
    "agency_sales_operator": {
        "name": "Agency sales operator",
        "description": "Research prospects, score leads, draft outreach, and manage approval-gated CRM follow-up.",
        "agent_id": "sales_agent",
        "tags": ["sales", "crm", "agency", "outreach"],
        "pattern": "Collect source links, score fit, draft personalized messages, never send cold outreach without approval, and respect daily warmup limits.",
        "permissions": ["web_search", "crm_write", "outreach_draft"],
        "trust_level": "verified",
    },
    "client_portal_operator": {
        "name": "Client portal operator",
        "description": "Generate and maintain client-facing portal, intake, support, invoice, and project status pages.",
        "agent_id": "project_manager",
        "tags": ["client portal", "agency", "support", "invoice"],
        "pattern": "Use agency records as source of truth, redact private notes, generate static pages, and flag anything needing human/legal/payment review.",
        "permissions": ["agency_read", "static_site_write"],
        "trust_level": "verified",
    },
    "browser_workflow_operator": {
        "name": "Browser workflow operator",
        "description": "Use Playwright DOM automation with screenshot fallback and site-specific workflow memory.",
        "agent_id": "project_manager",
        "tags": ["browser", "playwright", "automation"],
        "pattern": "Prefer semantic selectors and DOM reads, fall back to screenshots only when needed, queue risky form submissions for approval, and store successful selectors.",
        "permissions": ["browser_dom", "playwright", "form_fill_queue"],
        "trust_level": "sandboxed",
    },
}


def catalog(include_installed: bool = True) -> dict[str, Any]:
    installed = {item["name"].lower(): item for item in skill_library.all_skills()} if include_installed else {}
    items = []
    for key, spec in {**_builtin_specs(), **CATALOG}.items():
        installed_item = installed.get(str(spec["name"]).lower())
        items.append(
            {
                "key": key,
                **spec,
                "installed": bool(installed_item),
                "enabled": bool(installed_item.get("enabled", False)) if installed_item else False,
                "skill_id": installed_item.get("id", "") if installed_item else "",
            }
        )
    return {
        "enabled": bool(config_value("skill_marketplace_enabled", True)),
        "count": len(items),
        "items": sorted(items, key=lambda item: item["key"]),
        "summary": f"{len(items)} local skill(s) available in the marketplace.",
    }


def install(key: str = "all") -> dict[str, Any]:
    key = str(key or "all").strip().lower()
    specs = {**_builtin_specs(), **CATALOG}
    wanted = specs if key == "all" else {key: specs[key]} if key in specs else {}
    installed = []
    for skill_key, spec in wanted.items():
        skill_id = skill_library.add_skill(
            spec["name"],
            spec["description"],
            spec["pattern"],
            agent_id=spec.get("agent_id", "jarvis"),
            tags=list(spec.get("tags") or []),
            source=f"marketplace:{skill_key}",
            permissions=list(spec.get("permissions") or []),
            secret_envs=list(spec.get("secret_envs") or []),
            trust_level=str(spec.get("trust_level") or "unverified"),
            agent_allowlist=list(spec.get("agent_allowlist") or [spec.get("agent_id", "jarvis")]),
            verified=str(spec.get("trust_level") or "") == "verified",
            sandboxed=bool(spec.get("sandboxed", True)),
        )
        installed.append({"key": skill_key, "skill_id": skill_id, "name": spec["name"]})
    return {"installed": installed, "summary": f"Installed {len(installed)} marketplace skill(s)."}


def enable(key_or_id: str, enabled: bool = True) -> dict[str, Any]:
    key_or_id = str(key_or_id or "").strip()
    if key_or_id in CATALOG or key_or_id in _builtin_specs():
        result = install(key_or_id)
        skill_id = (result.get("installed") or [{}])[0].get("skill_id", "")
    else:
        skill_id = key_or_id
    item = skill_library.enable_skill(skill_id, enabled=enabled)
    return {"skill": item, "summary": f"Skill {'enabled' if enabled else 'disabled'}." if item else "Skill not found."}


def search(query: str) -> dict[str, Any]:
    matches = skill_library.search(query)
    marketplace_matches = [
        {"key": key, **spec}
        for key, spec in {**_builtin_specs(), **CATALOG}.items()
        if str(query or "").lower() in (key + " " + spec["name"] + " " + spec["description"]).lower()
    ]
    return {"installed": matches, "marketplace": marketplace_matches, "summary": f"{len(matches) + len(marketplace_matches)} skill match(es)."}


def summary() -> dict[str, Any]:
    data = catalog()
    installed = skill_library.skill_summary()
    return {
        "marketplace_count": data["count"],
        "installed": installed,
        "summary": f"{installed['enabled']} enabled skill(s), {data['count']} available in the local marketplace.",
    }


def _builtin_specs() -> dict[str, dict[str, Any]]:
    return {key: dict(spec) for key, spec in skill_library.BUILTIN_SKILLS.items()}
