"""Friday's functional self-model and introspection helpers."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from core.config import DATA_DIR, ROOT_DIR, config_value, load_config
from core.lazy_imports import lazy_module


_MODULES = [
    "adaptive_attention", "academic_projects", "agency_mode", "agent_blackboard", "agent_memory", "agent_thought_bus",
    "app_state_memory", "autobiographical_memory", "autonomous_debugger", "autonomous_learning",
    "autonomous_qa_lab", "background_agents", "backup_recovery", "browser_extension_bridge",
    "browser_pc_copilot", "calendar_email_assistant", "capability_center", "codebase_standards",
    "context_aware_silence", "context_fusion", "contextual_workspace", "continuity_brain", "daily_companion",
    "deep_project_autopilot", "emotion_tone", "environment_awareness", "error_radar", "event_nervous_system",
    "evaluation_lab", "executive_capabilities", "git_integration", "goal_manager", "evidence_gate",
    "goal_regulation", "identity", "image_generation", "learning_coach", "local_file_intelligence", "llm",
    "long_term_learning", "meeting_study_companion", "mission_control", "model_3d", "model_router_brain",
    "notification_center", "offline_survival", "operating_rhythm", "permissions", "pc_awareness",
    "pc_timeline", "personal_command_memory", "personal_crm", "personal_data_timeline",
    "personal_knowledge_vault", "personal_finance", "personal_life_os", "personal_safety_guardian",
    "phone_bridge", "phone_mesh", "private_embedding_memory", "privacy_vault", "project_autopilot",
    "project_watchdog", "proactive_guardian", "release_manager", "research_briefings", "search_broker",
    "self_debugger", "self_reflection", "semantic_search", "skill_evolution", "skill_training_studio",
    "task_queue", "task_contracts", "text_to_3d", "trust_proof", "voice_reliability", "world_model",
]

globals().update({name: lazy_module(f"core.{name}") for name in _MODULES})


def status(*, light: bool = False) -> dict[str, Any]:
    cfg = load_config()
    if light:
        return {
            "identity": identity.identity_summary(),
            "runtime": runtime_state(cfg),
            "modules": module_inventory(),
            "activity": current_activity(light=True),
            "limitations": limitations()[:8],
        }
    return {
        "identity": identity.identity_summary(),
        "runtime": runtime_state(cfg),
        "modules": module_inventory(),
        "tools": tool_inventory(),
        "permissions": permission_summary(),
        "memory_stores": memory_stores(cfg),
        "workers": _safe(background_agents.worker_status, {}),
        "activity": current_activity(light=not bool(config_value("self_model_deep_activity_enabled", False))),
        "access": access_report(cfg),
        "limitations": limitations(),
        "uncertainty": uncertainty_report(),
        "recent_failures": recent_failures(limit=8),
        "autobiography": autobiographical_memory.recent_events(limit=8),
    }


def runtime_state(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    cfg = cfg or load_config()
    return {
        "llm_provider": cfg.get("llm_provider"),
        "llm_fallback_provider": cfg.get("llm_fallback_provider"),
        "ollama_model": cfg.get("ollama_model"),
        "nvidia_model": cfg.get("nvidia_model"),
        "gemini_model": cfg.get("gemini_model"),
        "openrouter_model": cfg.get("openrouter_model"),
        "stt_backend": cfg.get("stt_backend"),
        "stt_model": cfg.get("stt_model"),
        "stt_fallback_model": cfg.get("stt_fallback_model"),
        "tts_backend": cfg.get("voice_backend"),
        "edge_voice": cfg.get("fast_voice_edge_voice") or cfg.get("edge_voice"),
        "online_apis": _configured_apis(cfg),
        "api_agent_mode": bool(cfg.get("v2_api_agent_mode_enabled", False)),
        "evidence_gate_enabled": bool(cfg.get("evidence_gate_enabled", True)),
    }


def module_inventory() -> list[dict[str, Any]]:
    modules = [
        ("world_model", "Continuous world snapshots, entities, and expectations."),
        ("self_reflection", "Reviews corrections, slow actions, failures, and permission blocks."),
        ("long_term_learning", "Durable lessons with confidence, evidence count, review timing, and self-update promotion."),
        ("goal_regulation", "Tracks goals and operational state."),
        ("adaptive_attention", "Learns wake-name aliases and listening strictness."),
        ("autobiographical_memory", "Persistent timeline of important events."),
        ("evidence_gate", "Blocks unsupported success claims."),
        ("image_generation", "Generates images through configured local Stable Diffusion or optional Hugging Face image provider; reports setup gaps honestly."),
        ("permissions", "User-controlled allow/ask/block policy center."),
        ("self_update", "Guarded codebase update proposal, approval, testing, and rollback."),
        ("desktop_tasks", "Human-like app control sessions with screenshots and pause/resume controls."),
        ("visual_monitor", "Continuous screen/camera change monitoring."),
        ("pc_awareness", "Inventory of active window, running apps, installed app entries, Desktop/Home-screen shortcuts, and Start Menu apps."),
        ("phone_bridge", "Free-first Android phone bridge for ntfy alerts, ADB status, battery checks, URL handoff, ringing, and guarded dialing."),
        ("capability_center", "Home/device awareness, personal ops, workspace intelligence, maintenance, defensive security lab, and automation recipes."),
        ("workspace_brain", "Deeper repo/codebase mapping, architecture hints, TODO/test tracking, and docs generation."),
        ("app_operators", "Specialist operators for VS Code, Chrome, Figma, Gmail, WhatsApp Web, Discord, and File Explorer."),
        ("personal_life_os", "Daily planning, follow-up detection, routines, mood/energy-aware planning, and end-of-day summaries."),
        ("home_assistant", "Optional Home Assistant bridge for local smart-home entities and services."),
        ("backup_recovery", "Backups, config snapshots, restore guardrails, and risky-delete warnings."),
        ("proactive_guardian", "Quietly watches battery, CPU/disk health, security, reminders, stuck agents, and reliability signals."),
        ("notification_center", "Unified inbox for guardian alerts, phone notices, agent questions, reminders, approvals, and failed tasks."),
        ("emotion_tone", "Detects frustration, tiredness, rushing, calm, and adjusts replies gently."),
        ("personal_crm", "Remembers people, relationships, birthdays, promises, conversations, and follow-ups."),
        ("learning_coach", "Tracks learning topics, spaced-repetition cards, quizzes, and progress."),
        ("research_briefings", "Runs or queues background research briefings and stores reusable findings."),
        ("search_broker", "Dedicated web-search broker with API providers, normalized citations, dedupe, ranking, and short-lived cache."),
        ("academic_projects", "Prepares source-backed final year projects, proposals, research papers, and local Markdown/DOCX/PDF exports."),
        ("agency_mode", "Runs a small agency pipeline for lead search, prospect scoring, approval-gated outreach, client projects, invoices, profit tracking, and API-cost recommendations."),
        ("git_integration", "Runs guarded Git and GitHub CLI workflows for status, diffs, branches, commits, pushes, pull requests, and issues."),
        ("model_3d", "Generates procedural mesh models and can hand photorealistic/PBR targets to a Blender-backed studio pipeline when Blender is configured."),
        ("text_to_3d", "Provider-backed text-to-3D generation through Meshy, Tripo, or a configured local generator command."),
        ("contextual_workspace", "Prepares repo/project context when a workspace is opened or requested."),
        ("offline_survival", "Reduced local-first operating mode for internet or API provider failures."),
        ("personal_data_timeline", "Searches what the user worked on, downloaded, changed, and noted over time."),
        ("skill_training_studio", "Turns user-taught workflows into reusable Friday skills."),
        ("personal_knowledge_vault", "Private memory for goals, projects, habits, people, preferences, repeated corrections, and weekly priorities."),
        ("voice_command_repair", "Learns user transcript corrections such as 'No, I said reduce volume to 40'."),
        ("project_autopilot", "Watches codebases for TODOs, stale docs, dependency health, test failures, and safe fix proposals."),
        ("pc_timeline", "Awareness timeline of active windows, app changes, Friday actions, failures, and learned observations."),
        ("goal_manager", "Breaks big goals into weekly and daily actions, tracks progress, and suggests next actions."),
        ("local_file_intelligence", "Indexes Desktop, Documents, Downloads, projects, PDFs, and image metadata for local file search."),
        ("meeting_study_companion", "Stores transcripts, summaries, action items, flashcards, and follow-up reminders."),
        ("automation_builder", "Builds natural-language automations from rules such as battery low or opening VS Code."),
        ("event_nervous_system", "Event-driven local awareness for app focus, downloads, reminders, phone connection, battery, and stuck agents."),
        ("barge_in", "Interrupt signal for stopping current speech and recording corrections."),
        ("daily_companion", "Morning briefings and low-noise check-ins."),
        ("skill_marketplace", "User-facing local skill marketplace on top of reusable skills."),
        ("personal_finance", "Free/local expense, budget, subscription, and affordability organization."),
        ("private_embedding_memory", "Private local search memory with optional local embeddings and lexical fallback."),
        ("android_companion", "Android companion layer for notification sync, voice-to-Friday, phone ringing, files, photos, and clipboard handoff."),
        ("project_watchdog", "Continuous project health watcher for TODOs, docs, dependencies, tests, and secrets."),
        ("codebase_standards", "Security-first codebase standards guard for performance, maintainability, reliability, and portability."),
        ("sandbox_simulation", "Dry-run plans with expected steps, risks, rollback, and confidence before acting."),
        ("privacy_vault", "Protected sensitive memory and credential-reference vault."),
        ("model_router_brain", "Chooses the best local or online model route per task and tracks provider performance."),
        ("self_debugger", "Creates failure reports, probable causes, test plans, and guarded self-update proposals."),
        ("app_integrations", "Local contacts, reminders, calendar-like events, docs/sheets files, and workspace indexing."),
        ("google_workspace", "OAuth-backed Gmail, Calendar, Docs, and Sheets integrations when Google credentials and user consent are configured."),
        ("agent_blackboard", "Shared agent findings, questions, evidence, blockers, decisions, and needs."),
        ("agent_thought_bus", "Silent internal packets that let agents pass context, questions, risks, and handoffs without speaking aloud."),
        ("task_contracts", "Goal, success criteria, risk, expected output, and verification for queued work."),
        ("evaluation_lab", "Reliability metrics for STT mistakes, latency, failed tools, stuck tasks, and unsupported claims."),
        ("agent_memory", "Per-agent notebooks for sources, facts, patterns, bugs, design rules, and safety checks."),
        ("approval_inbox", "Unified human decision queue for risky actions, blocked tasks, agent questions, and self-updates."),
        ("browser_playwright", "Optional DOM-level browser automation through Playwright."),
        ("voice_reliability", "Voice transcript samples, corrections, backend tracking, and learned wake-name aliases."),
        ("executive_capabilities", "Autonomy layer for memory review, task autopilot, personality profiles, life dashboard, skill recorder, documentation, personal search, trust, learning, relationships, deployment, and privacy firewall."),
        ("mission_control", "Approval-gated long missions with fixed phases, evidence, blockers, deploy gates, and non-interrupting work channels."),
        ("autonomous_qa_lab", "Project QA evidence reports covering tests, security checks, dependencies, performance smoke, and accessibility checklist."),
        ("app_state_memory", "App-specific muscle memory for known buttons, selectors, successful menus, failed interactions, and recovery hints."),
        ("browser_extension_bridge", "Chrome/Edge extension bridge for redacted DOM context and browser console events."),
        ("release_manager", "Changelog, version, build/test/deploy checklist, known risks, and rollback plan before release."),
        ("error_radar", "Watches logs, browser console events, failed tasks, project watchdogs, and creates self-debug reports."),
        ("semantic_search", "Unified local private search over safe files, notes, task history, page snapshots, and memories."),
        ("operating_rhythm", "Learns energy/focus notes, productive windows, and coding-vs-admin recommendations."),
        ("personal_command_memory", "Learns the user's exact command phrases and safely resolves them into canonical actions."),
        ("environment_awareness", "Captures active app, battery, network, open project, idle hints, and contextual recommendations."),
        ("autonomous_debugger", "Analyzes logs, stack traces, commands, and failures into cause, fix, and test-plan reports."),
        ("calendar_email_assistant", "OAuth-backed calendar/email briefing, follow-up detection, and draft-only reply assistance."),
        ("autonomous_learning", "Chooses learning topics from user goals and stores reusable agent notebook lessons."),
        ("trust_proof", "Creates evidence reports for important tasks with changes, tests, failures, risks, and confidence."),
        ("continuity_brain", "Remembers unfinished threads across days and captures where work stopped."),
        ("context_fusion", "Merges PC, browser, Android, calendar, tasks, tone, memory, and project-health signals."),
        ("deep_project_autopilot", "Coordinates project scans, debugger evidence, browser console signals, fix-prep tasks, and proof reports."),
        ("context_aware_silence", "Learns when Friday should stay quiet or interrupt based on mode and severity."),
        ("browser_pc_copilot", "Uses browser extension context plus PC awareness for tab summaries, page debugging, and safe DOM help."),
        ("skill_evolution", "Detects repeated workflows and suggests saving them as reusable skills."),
        ("personal_safety_guardian", "Protects .env, scans for secret-like values, and preflights risky deletes/overwrites."),
        ("phone_mesh", "Queues Android-to-PC and PC-to-Android handoffs for a real device mesh."),
    ]
    return [{"name": name, "description": description, "enabled": _module_enabled(name)} for name, description in modules]


def tool_inventory() -> list[dict[str, Any]]:
    items = []
    for tool in llm.TOOL_DEFINITIONS:
        items.append(
            {
                "name": tool.get("name", ""),
                "description": tool.get("description", ""),
                "actions": list((tool.get("input_schema", {}).get("properties", {}).get("action", {}).get("enum") or [])[:40]),
            }
        )
    return items


def permission_summary() -> dict[str, Any]:
    rules = permissions.list_rules()
    counts = {
        "allow": sum(1 for rule in rules if rule.get("mode") == "allow"),
        "ask": sum(1 for rule in rules if rule.get("mode") == "ask"),
        "block": sum(1 for rule in rules if rule.get("mode") == "block"),
    }
    return {
        "counts": counts,
        "ask_first": [rule for rule in rules if rule.get("mode") == "ask"][:10],
        "blocked": [rule for rule in rules if rule.get("mode") == "block"][:10],
    }


def memory_stores(cfg: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    cfg = cfg or load_config()
    names = [
        ("conversation", "Rolling chat history", f"backend={cfg.get('memory_backend', 'json')}"),
        ("episodic", "Action/event memory", "data/episodic_store.sqlite3"),
        ("semantic", "Facts and long-term memory", "data/memory.json and related stores"),
        ("graph", "Knowledge graph edges", "data/knowledge_graph.json"),
        ("procedural", "Skills and reusable lessons", "data/skill_library.sqlite3"),
        ("world", "World model snapshots/entities/expectations", "data/world_model.sqlite3"),
        ("autobiographical", "Important timeline events", "data/autobiographical_memory.sqlite3"),
        ("reflection", "Self-review findings", "data/self_reflection.sqlite3"),
        ("learning", "Durable lessons and reviews", "data/long_term_learning.sqlite3"),
        ("blackboard", "Shared agent workspace", "data/agent_blackboard.sqlite3"),
        ("thought_bus", "Silent agent-to-agent internal packets", "data/agent_thought_bus.sqlite3"),
        ("agent_notebooks", "Specialist agent memories", "data/agent_memory.sqlite3"),
        ("contracts", "Task contract verification", "data/task_contracts.sqlite3"),
        ("evaluation", "Reliability lab events", "data/evaluation_lab.sqlite3"),
        ("voice_reliability", "STT samples and corrections", "data/voice_reliability.sqlite3"),
        ("pc_awareness", "PC app/process/shortcut awareness snapshots", "data/pc_awareness.sqlite3"),
        ("phone_bridge", "Android phone bridge devices and events", "data/phone_bridge.sqlite3"),
        ("capability_center", "Capability events, automation recipes, security scopes, and security findings", "data/capability_center.sqlite3"),
        ("personal_life_os", "Routines, mood/energy notes, and planning history", "data/personal_life_os.sqlite3"),
        ("backup_recovery", "Backup manifests and restore metadata", "data/backup_recovery.sqlite3"),
        ("notifications", "Unified alerts and decision-worthy notices", "data/notification_center.sqlite3"),
        ("emotion_tone", "Tone observations and reply-adjustment evidence", "data/emotion_tone.sqlite3"),
        ("personal_crm", "People, conversations, birthdays, promises, and follow-ups", "data/personal_crm.sqlite3"),
        ("learning_coach", "Study topics, spaced-repetition cards, quiz attempts, and progress", "data/learning_coach.sqlite3"),
        ("research_briefings", "Subscribed research topics and generated briefings", "data/research_briefings.sqlite3"),
        ("search_broker", "Short-lived normalized web-search result cache", "data/search_broker.sqlite3"),
        ("contextual_workspace", "Prepared active-project context and project health snapshots", "data/contextual_workspace.sqlite3"),
        ("offline_survival", "Offline/local-first mode changes and provider survival state", "data/offline_survival.sqlite3"),
        ("personal_data_timeline", "Personal notes joined with PC and Friday timeline events", "data/personal_data_timeline.sqlite3"),
        ("skill_training_studio", "User-taught workflow drafts and published skill records", "data/skill_training_studio.sqlite3"),
        ("mission_control", "Long mission runs, phases, evidence, blockers, approvals, and desktop locks", "data/mission_control.sqlite3"),
        ("autonomous_qa_lab", "Mission/project QA reports and evidence", "data/autonomous_qa_lab.sqlite3"),
        ("app_state_memory", "App-specific selectors, menus, outcomes, and recovery patterns", "data/app_state_memory.sqlite3"),
        ("browser_extension", "Redacted browser extension contexts and console events", "data/browser_extension.sqlite3"),
        ("release_manager", "Release plans, checklists, risks, rollback metadata, and approval state", "data/release_manager.sqlite3"),
        ("error_radar", "Log, console, task, watchdog, and crash signals", "data/error_radar.sqlite3"),
        ("semantic_search", "Unified local search chunks and source metadata", "data/semantic_search.sqlite3"),
        ("operating_rhythm", "Energy/focus notes and rhythm signals", "data/operating_rhythm.sqlite3"),
        ("guardian", "Proactive guardian scan history", "data/proactive_guardian.sqlite3"),
        ("personal_vault", "Private goals, projects, preferences, corrections, and people", "data/personal_knowledge_vault.sqlite3"),
        ("project_autopilot", "Project health reports and fix preparation history", "data/project_autopilot.sqlite3"),
        ("pc_timeline", "PC/window/action awareness timeline", "data/pc_timeline.sqlite3"),
        ("local_files", "Local file index and snippets", "data/local_file_intelligence.sqlite3"),
        ("study_companion", "Meeting/class transcripts, action items, and flashcards", "data/meeting_study_companion.sqlite3"),
        ("event_nervous_system", "Event stream and local watcher state", "data/event_nervous_system.sqlite3"),
        ("barge_in", "Speech interrupt events", "data/barge_in.sqlite3"),
        ("daily_companion", "Daily brief and check-in history", "data/daily_companion.sqlite3"),
        ("agency_mode", "Leads, outreach drafts, client projects, invoices, ledger, and payment recommendations", "data/agency_mode.sqlite3"),
        ("personal_finance", "Local expenses, budgets, and subscriptions", "data/personal_finance.sqlite3"),
        ("private_embedding_memory", "Private searchable memory chunks", "data/private_embedding_memory.sqlite3"),
        ("android_companion", "Android companion events", "data/android_companion.sqlite3"),
        ("project_watchdog", "Continuous project watchdog reports", "data/project_watchdog.sqlite3"),
        ("codebase_standards", "Codebase standards scan reports", "data/codebase_standards.sqlite3"),
        ("sandbox_simulation", "Dry-run action simulations", "data/sandbox_simulation.sqlite3"),
        ("privacy_vault", "Sensitive item references and hashes", "data/privacy_vault.sqlite3"),
        ("model_router", "Provider routing results and scores", "data/model_router_brain.sqlite3"),
        ("self_debugger", "Failure analysis reports", "data/self_debugger.sqlite3"),
        ("executive_capabilities", "Memory reviews, task autopilots, personality events, recorded skills, and high-level capability events", "data/executive_capabilities.sqlite3"),
        ("personal_command_memory", "Learned user command aliases and shortcut outcomes", "data/personal_command_memory.sqlite3"),
        ("environment_awareness", "Environment snapshots, active apps, battery/network context, and recommendations", "data/environment_awareness.sqlite3"),
        ("autonomous_debugger", "Autonomous debugger reports and watched failure signals", "data/autonomous_debugger.sqlite3"),
        ("autonomous_learning", "Learning cycles, agent notebook updates, and topic progress", "data/autonomous_learning.sqlite3"),
        ("trust_proof", "Proof reports for changed/tested/failed/evidence/risk summaries", "data/trust_proof.sqlite3"),
        ("continuity_brain", "Unfinished threads and cross-day continuity events", "data/continuity_brain.sqlite3"),
        ("context_aware_silence", "Speaking mode, interruption threshold, and silence-mode events", "data/context_aware_silence.sqlite3"),
        ("deep_project_autopilot", "Deep project autopilot runs and proof links", "data/deep_project_autopilot.sqlite3"),
        ("skill_evolution", "Repeated workflow observations and reusable-skill suggestions", "data/skill_evolution.sqlite3"),
        ("personal_safety_guardian", "Practical safety scans, protected-file checks, and secret-like findings", "data/personal_safety_guardian.sqlite3"),
        ("phone_mesh", "Phone-to-PC and PC-to-phone handoffs", "data/phone_mesh.sqlite3"),
    ]
    return [{"name": name, "purpose": purpose, "location": location} for name, purpose, location in names]


def current_activity(*, light: bool = False) -> dict[str, Any]:
    workers = _safe(background_agents.worker_status, {})
    counts = _safe(task_queue.counts, {})
    regulation = _safe(goal_regulation.current_regulation, {})
    if light:
        return {
            "summary": current_activity_summary(),
            "workers": workers,
            "task_counts": counts,
            "regulation": regulation,
        }
    world = _safe(world_model.current_context, {})
    reflections = _safe(lambda: self_reflection.recent_findings(limit=3), [])
    learning = _safe(lambda: long_term_learning.recent_items(limit=3), [])
    return {
        "summary": current_activity_summary(),
        "workers": workers,
        "task_counts": counts,
        "regulation": regulation,
        "world": world,
        "recent_reflections": reflections,
        "recent_learning": learning,
        "guardian": _safe(proactive_guardian.status, {}),
        "notifications": _safe(lambda: notification_center.summary(limit=5), {}),
        "emotion_tone": _safe(emotion_tone.summary, {}),
        "personal_crm": _safe(personal_crm.summary, {}),
        "learning_coach": _safe(learning_coach.progress, {}),
        "research_briefings": _safe(research_briefings.summary, {}),
        "workspace_context": _safe(contextual_workspace.summary, {}),
        "offline_survival": _safe(offline_survival.status, {}),
        "personal_timeline": _safe(personal_data_timeline.summary, {}),
        "skill_training": _safe(skill_training_studio.summary, {}),
        "vault": _safe(lambda: personal_knowledge_vault.summary(limit=5), {}),
        "goal_manager": _safe(goal_manager.progress_summary, {}),
        "pc_timeline": _safe(pc_timeline.summary, {}),
        "events": _safe(lambda: event_nervous_system.summary(limit=5), {}),
        "daily_companion": _safe(daily_companion.status, {}),
        "project_watchdog": _safe(project_watchdog.status, {}),
        "codebase_standards": _safe(codebase_standards.status, {}),
        "model_router": _safe(model_router_brain.summary, {}),
        "self_debugger": _safe(self_debugger.analyze_recent, {}),
        "executive": _safe(executive_capabilities.summary, {}),
        "missions": _safe(mission_control.status, {}),
        "qa_lab": _safe(autonomous_qa_lab.status, {}),
        "error_radar": _safe(error_radar.status, {}),
        "release_manager": _safe(release_manager.status, {}),
        "semantic_search": _safe(semantic_search.status, {}),
        "operating_rhythm": _safe(operating_rhythm.summary, {}),
    }


def current_activity_summary() -> str:
    counts = _safe(task_queue.counts, {})
    workers = _safe(background_agents.worker_status, {})
    regulation = _safe(goal_regulation.current_regulation, {})
    missions = _safe(mission_control.status, {})
    goals = regulation.get("active_goals") or []
    state = (regulation.get("state") or {}).get("state") or "calm"
    active_count = int(counts.get("active") or 0)
    active_missions = missions.get("active") or []
    if active_missions:
        mission = active_missions[0]
        return f"I am listening while mission #{mission['id']} runs in {mission['current_phase'].replace('_', ' ')}."
    if active_count and not workers.get("running"):
        return f"I am listening for your next command. I see {active_count} task marked active in the queue, but agent workers are stopped, so it is not currently executing."
    if active_count:
        return f"I am listening for your next command while {active_count} background task is active."
    if goals:
        return f"I am listening for your next command and tracking goal #{goals[0]['id']}: {goals[0]['title']}."
    return f"I am listening for your next command. My current operating state is {state}."


def access_report(cfg: dict[str, Any] | None = None, *, light: bool = False) -> dict[str, Any]:
    cfg = cfg or load_config()
    rules = permissions.list_rules()
    if light:
        return {
            "filesystem": "Broad local paths allowed" if cfg.get("pc_allow_arbitrary_paths") else "Limited to configured safe paths",
            "desktop": "Mouse/keyboard/screen automation allowed" if cfg.get("pc_allow_desktop_automation") else "Desktop automation disabled",
            "apps": "Configured apps plus trusted arbitrary app search" if cfg.get("pc_allow_arbitrary_apps") else "Configured apps only",
            "search_broker": _safe(lambda: search_broker.status().get("setup_hint"), "Search broker unavailable"),
            "academic_projects": _safe(lambda: f"Academic drafts export to {config_value('academic_project_formats', 'md,docx,pdf')}", "Academic project workflow unavailable"),
            "text_to_3d": _safe(lambda: text_to_3d.status().get("configured"), "Text-to-3D backend unavailable"),
            "web": _safe(lambda: f"Web search uses dedicated broker providers {', '.join(search_broker.status().get('configured') or []) or 'after API keys are configured'}; URL opening is available when requested.", "Web search and URL opening available when network is reachable"),
            "permissions": {"ask_first": [rule["label"] for rule in rules if rule.get("mode") == "ask"][:8]},
        }
    return {
        "filesystem": "Broad local paths allowed" if cfg.get("pc_allow_arbitrary_paths") else "Limited to configured safe paths",
        "desktop": "Mouse/keyboard/screen automation allowed" if cfg.get("pc_allow_desktop_automation") else "Desktop automation disabled",
        "apps": "Configured apps plus trusted arbitrary app search" if cfg.get("pc_allow_arbitrary_apps") else "Configured apps only",
        "pc_awareness": _safe(lambda: pc_awareness.snapshot().get("summary"), "PC awareness unavailable"),
        "phone_bridge": _safe(lambda: phone_bridge.status().get("setup_hint"), "Phone bridge unavailable"),
        "capabilities": _safe(lambda: capability_center.security_overview(light=True).get("scope_policy"), "Capability center unavailable"),
        "guardian": _safe(lambda: proactive_guardian.status().get("status"), "Guardian unavailable"),
        "tone_awareness": _safe(lambda: emotion_tone.summary().get("summary"), "Tone awareness unavailable"),
        "personal_crm": _safe(lambda: personal_crm.summary().get("summary"), "Personal CRM unavailable"),
        "learning_coach": _safe(lambda: learning_coach.progress().get("summary"), "Learning coach unavailable"),
        "research_briefings": _safe(lambda: research_briefings.summary().get("summary"), "Research briefings unavailable"),
        "search_broker": _safe(lambda: search_broker.status().get("setup_hint"), "Search broker unavailable"),
        "academic_projects": _safe(lambda: f"Academic drafts export to {config_value('academic_project_formats', 'md,docx,pdf')}", "Academic project workflow unavailable"),
        "git_integration": _safe(lambda: f"Git/GitHub CLI actions enabled with default remote {config_value('git_integration_default_remote', 'origin')}", "Git integration unavailable"),
        "model_3d": _safe(lambda: f"3D exports available as {config_value('model_3d_default_formats', 'obj,stl,gltf,glb')}; studio quality uses Blender path {config_value('model_3d_blender_path', 'blender')}", "3D model workflow unavailable"),
        "text_to_3d": _safe(lambda: text_to_3d.status().get("configured"), "Text-to-3D backend unavailable"),
        "workspace_context": _safe(lambda: contextual_workspace.summary().get("summary"), "Workspace context unavailable"),
        "offline_survival": _safe(lambda: offline_survival.status().get("summary"), "Offline survival unavailable"),
        "personal_timeline": _safe(lambda: personal_data_timeline.summary().get("summary"), "Personal timeline unavailable"),
        "skill_training": _safe(lambda: skill_training_studio.summary().get("summary"), "Skill training unavailable"),
        "local_files": _safe(lambda: f"{len(local_file_intelligence.search('project', limit=3))} quick matches available after indexing", "Local file index unavailable"),
        "project_autopilot": _safe(lambda: f"{len(project_autopilot.recent_reports(limit=3))} recent project report(s)", "Project autopilot unavailable"),
        "event_nervous_system": _safe(lambda: event_nervous_system.summary(limit=3).get("voice_summary"), "Event nervous system unavailable"),
        "private_memory": _safe(lambda: private_embedding_memory.summary().get("summary"), "Private memory unavailable"),
        "privacy_vault": _safe(lambda: privacy_vault.summary().get("summary"), "Privacy vault unavailable"),
        "agency_mode": _safe(lambda: agency_mode.status().get("summary"), "Agency Mode unavailable"),
        "finance": _safe(lambda: personal_finance.summary().get("summary"), "Finance helper unavailable"),
        "study_companion": _safe(lambda: f"{len(meeting_study_companion.list_sessions(limit=3))} recent study session(s)", "Study companion unavailable"),
        "image_generation": _safe(lambda: image_generation.status().get("setup_hint"), "Image generation unavailable"),
        "executive_capabilities": _safe(lambda: executive_capabilities.summary().get("summary"), "Executive capabilities unavailable"),
        "web": _safe(lambda: f"Web search uses dedicated broker providers {', '.join(search_broker.status().get('configured') or []) or 'after API keys are configured'}; URL opening is available when requested.", "Web search and URL opening available when network is reachable"),
        "camera": "Available only through visual monitor when OpenCV/camera works",
        "cloud_accounts": "No private cloud account API access unless credentials/connectors are configured; web UI can be opened instead",
        "permissions": {"ask_first": [rule["label"] for rule in rules if rule.get("mode") == "ask"][:8]},
    }


def access_summary() -> str:
    report = access_report(light=True)
    return (
        f"I can access {report['filesystem'].lower()}, {report['desktop'].lower()}, configured apps, PC awareness ({report.get('pc_awareness', 'available when requested')}), the Android phone bridge ({report.get('phone_bridge', 'available when configured')}), and guarded capability/security reports ({report.get('capabilities', 'available when requested')}). "
        f"I must ask first for: {', '.join(report['permissions']['ask_first']) or 'nothing currently'}."
    )


def uncertainty_report() -> dict[str, Any]:
    findings = self_reflection.recent_findings(limit=8, promoted=False)
    open_expectations = (world_model.current_context().get("open_expectations") or [])[:5]
    attention = adaptive_attention.current_profile()
    items = []
    if open_expectations:
        items.append({"topic": "world_expectations", "detail": f"{len(open_expectations)} expected outcomes are still open."})
    if findings:
        items.append({"topic": "reflection", "detail": findings[0]["finding"]})
    if float(attention.get("false_negative_rate", 0.0)) > 0:
        items.append({"topic": "attention", "detail": "Recent corrections suggest I may be missing or mishearing some commands."})
    items.append({"topic": "consciousness", "detail": "I am not human-conscious; I am a software agent with inspectable state."})
    return {"items": items[:8], "attention": attention}


def uncertainty_summary() -> str:
    items = uncertainty_report()["items"]
    if not items:
        return "I am not tracking a specific uncertainty right now."
    return "I am unsure about: " + "; ".join(item["detail"] for item in items[:3])


def recent_failures(limit: int = 8) -> list[dict[str, Any]]:
    events = []
    try:
        from core import audit_log, episodic_store

        events.extend(
            {
                "source": "episodic",
                "type": item.get("action_type"),
                "summary": _short(item.get("outputs")),
                "success_score": item.get("success_score"),
                "timestamp": item.get("timestamp"),
            }
            for item in episodic_store.query_events(limit=60)
            if float(item.get("success_score", 1.0)) < 0.5
        )
        events.extend(
            {
                "source": "audit",
                "type": item.get("action"),
                "summary": f"{item.get('category')} {item.get('target')}",
                "success_score": 0.0,
                "timestamp": item.get("timestamp"),
            }
            for item in audit_log.recent(limit=60)
            if not item.get("success")
        )
    except Exception:
        pass
    try:
        events.extend(
            {
                "source": "task_queue",
                "type": "task_failed",
                "summary": item.get("title"),
                "success_score": 0.0,
                "timestamp": item.get("updated_at"),
            }
            for item in task_queue.list_tasks(status="failed", limit=20)
        )
    except Exception:
        pass
    events.sort(key=lambda item: str(item.get("timestamp") or ""), reverse=True)
    return events[: max(1, min(100, int(limit)))]


def failure_summary(limit: int = 3) -> str:
    failures = recent_failures(limit=limit)
    if not failures:
        return "I do not see recent failures in my local logs."
    return "Recent failures: " + "; ".join(_short(item.get("summary"), 100) for item in failures[:limit]) + "."


def tools_summary(limit: int = 8) -> str:
    tools = tool_inventory()
    names = [tool["name"] for tool in tools[:limit]]
    return "My tool groups are: " + ", ".join(names) + ". Ask for capabilities for the broader list."


def capability_summary() -> str:
    return (
        "I can chat, answer quick questions, open apps, control apps, use mouse/keyboard, adjust volume/brightness, "
        "inspect screen/browser/accessibility context, run desktop task sessions, monitor screen/camera changes, read/list files, "
        "search the web, generate images when a local or configured image provider is available, help with code, manage the background agent team, use local integrations, ring or notify your Android phone, hand off links to it, read home/network/device status, produce daily briefs, map projects, check maintenance, run scoped defensive security checks, remember lessons, reflect on failures, "
        "share blackboard evidence, verify task contracts, track reliability metrics, use optional Playwright browser automation, "
        "watch events through a nervous system, keep daily companion briefs, manage local finance records, search private local memory, simulate risky plans, route models by task, debug my failures, "
        "notice your tone, remember people and promises, coach learning with spaced repetition, prepare research briefings, draft source-backed academic projects and papers with DOCX/PDF exports, run guarded Git/GitHub workflows, generate real 3D model files, load workspace context, survive offline, answer timeline questions, learn workflows you teach me, "
        "run task autopilot with checkpoint contracts, periodically review memories, switch personality profiles, show a local life dashboard, record narrated workflows into skills, update project docs, search across my personal/local timeline, assess trust and privacy risk, inspect deployments, "
        "and propose guarded self-updates. I must ask before risky actions based on your Safety Center rules."
    )


def identity_voice_summary() -> str:
    data = identity.identity_summary()
    return f"I am {data['name']}, {data['role']} My priority is to help honestly and never pretend success without evidence."


def why_last_action_summary() -> str:
    events = autobiographical_memory.recent_events(limit=5)
    if events:
        item = events[0]
        return f"My latest notable event was {item['event_type']}: {item['title']}. {item['summary']}".strip()
    findings = self_reflection.recent_findings(limit=1)
    if findings:
        item = findings[0]
        return f"My best explanation is: {item['finding']} Recommendation: {item['recommended_change']}"
    return "I do not have enough evidence to explain the last action yet."


def limitations() -> list[str]:
    identity_data = identity.identity_summary()
    items = identity_data.get("must_never_pretend") or []
    defaults = [
        "I am not human-conscious or human-equivalent.",
        "I only know app or website state that tools, screenshots, DOM, UI Automation, or APIs expose.",
        "My PC awareness sees running processes and installed/shortcut inventory, but not private app internals unless accessibility, DOM, screenshots, or APIs expose them.",
        "CAPTCHAs, private login flows, payments, and security prompts require human handoff.",
        "Cloud account data requires configured credentials/connectors or an already-open web UI.",
        "Phone access needs ntfy for remote alerts and ADB for deeper Android control; I cannot fake carrier calls without a telephony provider.",
        "Security testing is defensive-only and external targets require verified ownership scope.",
        "Free API tiers can rate-limit, fail, or change outside this codebase.",
        "Playwright browser control needs the Python package and browser binaries installed before it can drive websites.",
        "Tone detection is heuristic unless a configured model is explicitly used; it should guide kindness, not diagnose feelings.",
        "Task autopilot can keep working through queued agents and checkpoints, but it must pause for missing credentials, risky approvals, private data consent, or verification it cannot observe.",
    ]
    return list(dict.fromkeys(items + defaults))


def record_notable_event(event_type: str, title: str, summary: str = "", **metadata: Any) -> None:
    try:
        autobiographical_memory.record_event(event_type, title, summary, metadata=metadata, importance=float(metadata.pop("importance", 0.65) if metadata else 0.65))
    except Exception:
        return


def _configured_apis(cfg: dict[str, Any]) -> dict[str, bool]:
    names = {
        "anthropic": "ANTHROPIC_API_KEY",
        "groq_stt": "GROQ_API_KEY",
        "gemini": str(cfg.get("gemini_api_key_env") or "GEMINI_API_KEY"),
        "openrouter": str(cfg.get("openrouter_api_key_env") or "OPENROUTER_API_KEY"),
        "nvidia": str(cfg.get("nvidia_api_key_env") or "NVIDIA_API_KEY"),
        "gmail_smtp": "GMAIL_APP_PASSWORD",
        "google_workspace_client": str(cfg.get("google_oauth_client_id_env") or "GOOGLE_CLIENT_ID"),
        "brave_search": str(cfg.get("search_broker_brave_api_key_env") or "BRAVE_SEARCH_API_KEY"),
        "google_custom_search": str(cfg.get("search_broker_google_api_key_env") or "GOOGLE_SEARCH_API_KEY"),
        "tavily_search": str(cfg.get("search_broker_tavily_api_key_env") or "TAVILY_API_KEY"),
        "serpapi": str(cfg.get("search_broker_serpapi_api_key_env") or "SERPAPI_API_KEY"),
    }
    result = {}
    for name, env_name in names.items():
        value = os.getenv(env_name, "")
        result[name] = bool(value and "your_" not in value.lower() and "placeholder" not in value.lower())
    return result


def _module_enabled(name: str) -> bool:
    key_map = {
        "world_model": "world_model_enabled",
        "self_reflection": "self_reflection_enabled",
        "long_term_learning": "long_term_learning_enabled",
        "goal_regulation": "goal_regulation_enabled",
        "adaptive_attention": "adaptive_attention_enabled",
        "autobiographical_memory": "autobiographical_memory_enabled",
        "evidence_gate": "evidence_gate_enabled",
        "self_update": "self_update_enabled",
        "browser_playwright": "browser_playwright_enabled",
        "voice_reliability": "voice_reliability_enabled",
        "google_workspace": "google_oauth_enabled",
        "pc_awareness": "pc_awareness_enabled",
        "proactive_guardian": "proactive_guardian_enabled",
        "voice_command_repair": "voice_reliability_enabled",
        "executive_capabilities": "executive_capabilities_enabled",
        "search_broker": "search_broker_enabled",
    }
    return bool(config_value(key_map.get(name, f"{name}_enabled"), True))


def _safe(fn: Any, default: Any) -> Any:
    try:
        return fn()
    except Exception:
        return default


def _short(value: Any, limit: int = 140) -> str:
    text = " ".join(str(value or "").split())
    return text if len(text) <= limit else text[: limit - 3] + "..."
