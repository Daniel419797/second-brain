"""LLM provider boundary for Anthropic Claude and local Ollama."""

from __future__ import annotations

import contextvars
import datetime as _dt
import json
import os
import threading
import time
from contextlib import contextmanager
from types import SimpleNamespace
from typing import Any

try:
    import anthropic
except Exception:  # pragma: no cover - dependency may be absent in scaffold tests
    anthropic = None

try:
    import requests
except Exception:  # pragma: no cover - dependency may be absent in scaffold tests
    requests = None

from core.config import LOG_DIR, config_value, ensure_runtime_dirs, load_config

DEFAULT_MODEL = "claude-3-5-sonnet-20240620"

FALLBACK_SYSTEM_PROMPT = (
    "You are Friday, a personal AI agent running on Windows. "
    "Keep voice responses under 2 sentences and usually under 25 words. "
    "Answer direct questions directly; do not ask for a more specific request unless the question is genuinely ambiguous. "
    "For common acronyms, prefer the everyday meaning unless the user gives a technical domain; POS usually means Point of Sale. "
    "When the user asks you to do something on the PC, use the appropriate tool. "
    "Use [REMEMBER: fact] only when the user explicitly asks you to remember something "
    "or shares a stable personal preference/profile fact. "
    "Do not add memory tags for ordinary explanations. "
    "Prefer tool use over text for actionable commands."
)


def _system_prompt() -> str:
    cfg = load_config()
    prompt = cfg.get("system_prompt") or FALLBACK_SYSTEM_PROMPT
    return prompt + f"\nToday's date and time: {_dt.datetime.now().isoformat(timespec='seconds')}. User name: {cfg.get('user_name', 'User')}."


SYSTEM_PROMPT = _system_prompt()

ONLINE_PROVIDERS = {"anthropic", "gemini", "nvidia", "openrouter"}
_PROVIDER_LIMITERS: dict[tuple[str, int], threading.BoundedSemaphore] = {}
_PROVIDER_LOCK = threading.Lock()
_PROVIDER_LAST_START: dict[str, float] = {}
_PROVIDER_BACKOFF_UNTIL: dict[str, float] = {}
_PROVIDER_FAILURE_STREAK: dict[str, int] = {}
_REQUEST_PROVIDER_CHAIN: contextvars.ContextVar[str | list[str] | tuple[str, ...] | None] = contextvars.ContextVar(
    "request_provider_chain",
    default=None,
)
_REQUEST_CONFIG: contextvars.ContextVar[dict[str, Any] | None] = contextvars.ContextVar("request_config", default=None)

TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "name": "pc_control",
        "description": "Controls the Windows PC: opens apps/files/folders, closes apps, inventories running/installed/Desktop apps, lists/reads files, runs confirmed shell commands, and can operate the visible desktop with mouse, keyboard, screenshots, scrolling, window focus, Playwright, browser DOM, and Windows accessibility context.",
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": [
                        "open_app",
                        "close_app",
                        "open_path",
                        "list_files",
                        "read_file",
                        "run_command",
                        "mouse_position",
                        "screen_size",
                        "move_mouse",
                        "click",
                        "double_click",
                        "right_click",
                        "drag_mouse",
                        "scroll",
                        "type_text",
                        "press_key",
                        "hotkey",
                        "screenshot",
                        "focus_window",
                        "active_window",
                        "pc_awareness_snapshot",
                        "list_running_apps",
                        "list_installed_apps",
                        "list_desktop_apps",
                        "find_app",
                        "inspect_screen",
                        "screen_step",
                        "inspect_browser",
                        "playwright_inspect",
                        "playwright_open",
                        "playwright_run",
                        "inspect_accessibility",
                        "open_browser_debug",
                        "visual_monitor_start",
                        "visual_monitor_stop",
                        "visual_monitor_status",
                        "visual_capture_once",
                        "desktop_task",
                        "desktop_task_pause",
                        "desktop_task_resume",
                        "desktop_task_confirm",
                        "desktop_task_cancel",
                        "wait",
                    ],
                },
                "target": {"type": "string", "description": "App name, app lookup query, file/folder path, shell command, window title, text to type, key name, hotkey combo, coordinates, screenshot path, or screen instruction."},
                "query": {"type": "string", "description": "App search query for find_app."},
                "limit": {"type": "integer", "description": "Maximum inventory items for list_running_apps, list_installed_apps, or list_desktop_apps."},
                "instruction": {"type": "string", "description": "Natural-language instruction for inspect_screen, screen_step, or desktop_task. Use desktop_task for multi-step app workflows; it can use screenshots, browser DOM, and Windows accessibility context."},
                "x": {"type": "number", "description": "Screen x coordinate for mouse actions."},
                "y": {"type": "number", "description": "Screen y coordinate for mouse actions."},
                "button": {"type": "string", "enum": ["left", "right", "middle"], "description": "Mouse button for click or drag actions."},
                "clicks": {"type": "integer", "description": "Number of mouse clicks."},
                "amount": {"type": "integer", "description": "Scroll amount. Positive scrolls up, negative scrolls down."},
                "text": {"type": "string", "description": "Text to type for type_text."},
                "key": {"type": "string", "description": "Single key for press_key."},
                "keys": {"type": "array", "items": {"type": "string"}, "description": "Keys for a hotkey, such as ['ctrl','l']."},
                "duration": {"type": "number", "description": "Mouse movement duration in seconds."},
                "seconds": {"type": "number", "description": "Seconds to wait."},
                "max_steps": {"type": "integer", "description": "Maximum steps for desktop_task."},
                "session_id": {"type": "integer", "description": "Desktop task session id for pause, resume, confirm, or cancel."},
                "url": {"type": "string", "description": "URL for open_browser_debug."},
                "steps": {
                    "type": "array",
                    "items": {"type": "object"},
                    "description": "Playwright steps for playwright_run, e.g. [{'action':'fill','selector':'input[name=q]','text':'Friday'}].",
                },
                "source": {"type": "string", "enum": ["screen", "camera", "both"], "description": "Visual monitor source for start/capture actions."},
                "analyze": {"type": "boolean", "description": "Whether visual_capture_once should ask the vision model to summarize the frame."},
            },
            "required": ["action"],
        },
    },
    {
        "name": "web_search",
        "description": "Searches the web through Friday's dedicated search broker, or opens a URL only when the user explicitly asks to open or go to it.",
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["search", "open_url"]},
                "query": {"type": "string", "description": "Search query for search action"},
                "url": {"type": "string", "description": "URL for open_url action"},
            },
            "required": ["action"],
        },
    },
    {
        "name": "trading_data",
        "description": "Fetches read-only market price or news for stocks, crypto, forex, and NGX symbols. Never places trades.",
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["price", "news"]},
                "ticker": {"type": "string", "description": "Ticker such as AAPL, BTC-USD, EURUSD=X, or DANGCEM.LG"},
            },
            "required": ["action", "ticker"],
        },
    },
    {
        "name": "send_email",
        "description": "Sends an email through Gmail SMTP after explicit user confirmation.",
        "input_schema": {
            "type": "object",
            "properties": {
                "to": {"type": "string", "description": "Recipient email address"},
                "subject": {"type": "string", "description": "Email subject"},
                "body": {"type": "string", "description": "Drafted email body"},
            },
            "required": ["to", "subject", "body"],
        },
    },
    {
        "name": "coding_assist",
        "description": "Answers coding questions or reviews a code file.",
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["qa", "review"],
                    "description": "Use qa for questions, review when user mentions a file path.",
                },
                "question": {"type": "string", "description": "The coding question for qa mode"},
                "file_path": {"type": "string", "description": "Absolute path to the file for review mode"},
            },
            "required": ["action"],
        },
    },
    {
        "name": "image_generation",
        "description": "Generates images from text prompts when a local Stable Diffusion/AUTOMATIC1111 server or optional Hugging Face image API is configured. If no provider is available, it reports the setup gap instead of opening Paint or pretending success.",
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["generate", "status", "list"]},
                "prompt": {"type": "string", "description": "The image prompt to generate."},
                "negative_prompt": {"type": "string", "description": "Optional things to avoid."},
                "provider": {"type": "string", "description": "auto, stable_diffusion, or hugging_face."},
                "width": {"type": "integer", "description": "Image width in pixels."},
                "height": {"type": "integer", "description": "Image height in pixels."},
                "steps": {"type": "integer", "description": "Inference steps."},
                "limit": {"type": "integer", "description": "Maximum generated image records to list."},
            },
            "required": ["action"],
        },
    },
    {
        "name": "app_integrations",
        "description": "Free/local app integrations plus real Google Workspace OAuth when connected: Gmail read, Calendar events, Docs/Sheets creation, reminders, contacts, workspace indexing/search, and opening web apps.",
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": [
                        "open_app",
                        "google_status",
                        "list_gmail_messages",
                        "create_contact",
                        "search_contacts",
                        "create_reminder",
                        "list_reminders",
                        "complete_reminder",
                        "create_calendar_event",
                        "list_calendar_events",
                        "create_doc",
                        "create_sheet",
                        "index_workspace",
                        "search_workspace",
                        "workspace_overview",
                    ],
                },
                "target": {"type": "string", "description": "Fallback app, title, contact, or query target."},
                "name": {"type": "string", "description": "Contact name or app name."},
                "email": {"type": "string", "description": "Contact email."},
                "phone": {"type": "string", "description": "Contact phone number."},
                "title": {"type": "string", "description": "Reminder, event, document, or sheet title."},
                "body": {"type": "string", "description": "Document body text."},
                "headers": {"type": "array", "items": {"type": "string"}, "description": "CSV sheet column names."},
                "query": {"type": "string", "description": "Contacts or workspace search query."},
                "due_at": {"type": "string", "description": "Reminder due date/time."},
                "start_at": {"type": "string", "description": "Calendar event start date/time."},
                "end_at": {"type": "string", "description": "Calendar event end date/time."},
                "location": {"type": "string", "description": "Calendar event location."},
                "notes": {"type": "string", "description": "Notes for contacts, reminders, or events."},
                "root": {"type": "string", "description": "Workspace root to index."},
                "limit": {"type": "integer", "description": "Maximum items to return."},
                "reminder_id": {"type": "integer", "description": "Reminder ID for completion."},
            },
            "required": ["action"],
        },
    },
    {
        "name": "phone_bridge",
        "description": "Free-first Android phone bridge: read phone status/battery, send ntfy notifications, ring/find the phone, open links on Android through ADB/ntfy, and open the Android dialer for calls after permission.",
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": [
                        "status",
                        "list_devices",
                        "register_device",
                        "battery",
                        "notify",
                        "send_to_phone",
                        "ring",
                        "call_me",
                        "find_phone",
                        "open_url",
                        "dial",
                        "call_number",
                        "call_contact",
                        "sms_draft",
                        "push_file",
                        "pull_file",
                        "set_clipboard",
                        "import_photos",
                        "events",
                    ],
                },
                "target": {"type": "string", "description": "Fallback target, message, contact, URL, or phone number."},
                "name": {"type": "string", "description": "Device or contact name."},
                "adb_serial": {"type": "string", "description": "ADB serial for the Android phone."},
                "ntfy_topic": {"type": "string", "description": "Private ntfy topic subscribed on the phone."},
                "phone_number": {"type": "string", "description": "Optional phone number for the registered device."},
                "title": {"type": "string", "description": "Phone notification title."},
                "message": {"type": "string", "description": "Phone notification or ring message."},
                "priority": {"type": "string", "description": "ntfy priority such as high or urgent."},
                "tags": {"type": "string", "description": "ntfy tag list."},
                "url": {"type": "string", "description": "URL to open on the phone."},
                "number": {"type": "string", "description": "Phone number to open in Android dialer."},
                "body": {"type": "string", "description": "SMS draft body."},
                "local_path": {"type": "string", "description": "Local file path to send to Android."},
                "phone_path": {"type": "string", "description": "Android file path for push/pull."},
                "local_dir": {"type": "string", "description": "Local destination folder for Android imports."},
                "text": {"type": "string", "description": "Text to copy to Android clipboard or send as copy notification."},
                "direct": {"type": "boolean", "description": "Request direct ACTION_CALL when enabled; otherwise opens the dialer."},
                "limit": {"type": "integer", "description": "Maximum events or devices to list."},
            },
            "required": ["action"],
        },
    },
    {
        "name": "capability_center",
        "description": "Runs Friday's guarded power features: home/device awareness, local network awareness, personal daily brief and next-action planning, workspace project mapping, dependency health, maintenance reports, scoped defensive security lab, hardening plans, and automation recipes.",
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": [
                        "overview",
                        "home_status",
                        "control_smart_device",
                        "router_status",
                        "local_network",
                        "connection_quality",
                        "daily_brief",
                        "next_action",
                        "plan_day",
                        "workspace_map",
                        "dependency_health",
                        "auto_docs",
                        "test_watch",
                        "maintenance_report",
                        "security_overview",
                        "create_security_scope",
                        "verify_security_scope",
                        "list_security_scopes",
                        "open_port_scan",
                        "dependency_security_scan",
                        "web_security_check",
                        "secret_scan",
                        "security_report",
                        "hardening_plan",
                        "list_recipes",
                        "create_recipe",
                        "run_recipe",
                    ],
                },
                "target": {"type": "string", "description": "Host, URL, app, recipe id, or fallback target."},
                "root": {"type": "string", "description": "Project root for workspace/security checks."},
                "host": {"type": "string", "description": "Network host to check."},
                "ports": {"type": "array", "items": {"type": "integer"}, "description": "TCP ports for scoped open-port checks."},
                "kind": {"type": "string", "description": "Security scope kind such as web, api, local, or lab."},
                "proof": {"type": "string", "description": "Ownership proof note or proof URL."},
                "proof_url": {"type": "string", "description": "URL containing Friday's ownership token."},
                "scope_id": {"type": "integer", "description": "Security scope id."},
                "name": {"type": "string", "description": "Automation recipe or smart-device name."},
                "device_action": {"type": "string", "description": "Configured smart-device action such as on, off, toggle, or brightness."},
                "params": {"type": "object", "description": "Optional smart-device action parameters."},
                "trigger_type": {"type": "string", "description": "Recipe trigger type, e.g. manual, app_opened, battery_below."},
                "trigger": {"type": "object", "description": "Recipe trigger data."},
                "action_type": {"type": "string", "description": "Recipe action type, e.g. notify_phone, open_app, set_brightness."},
                "action_data": {"type": "object", "description": "Recipe action data."},
                "recipe_id": {"type": "integer", "description": "Automation recipe id."},
                "command": {"type": "string", "description": "Test command for test watcher."},
                "limit": {"type": "integer", "description": "Maximum items to return."},
            },
            "required": ["action"],
        },
    },
    {
        "name": "power_center",
        "description": "Uses Friday's extended power modules: guardian mode, notifications, knowledge vault, voice repair, project autopilot, Git/GitHub workflows, 3D model exports, PC timeline, goals, local files, study sessions, automations, skills, workspace brain, app operators, Personal Life OS, Home Assistant, and backup/recovery guardrails.",
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": [
                        "install_builtin_skills",
                        "list_skills",
                        "workspace_analyze",
                        "workspace_question",
                        "workspace_docs",
                        "list_app_operators",
                        "operate_app",
                        "autonomous_coding",
                        "daily_plan",
                        "next_action",
                        "end_of_day",
                        "home_assistant_status",
                        "home_assistant_focus",
                        "backup_config",
                        "backup_file",
                        "list_backups",
                        "delete_guard",
                        "guardian_scan",
                        "guardian_status",
                        "notifications",
                        "remember_vault",
                        "vault_search",
                        "weekly_priorities",
                        "voice_repair",
                        "project_autopilot",
                        "project_prepare_fixes",
                        "pc_timeline",
                        "pc_timeline_summary",
                        "goal_plan",
                        "goal_next",
                        "file_index",
                        "file_search",
                        "folder_summary",
                        "study_session",
                        "automation_from_text",
                        "automation_run_matches",
                        "event_status",
                        "event_scan",
                        "daily_companion_brief",
                        "daily_companion_checkin",
                        "skill_marketplace",
                        "skill_marketplace_install",
                        "gateway_status",
                        "gateway_connectors",
                        "gateway_configure_connector",
                        "gateway_ingest_event",
                        "control_room",
                        "gateway_business_memory",
                        "gateway_remember_business",
                        "gateway_emergency_stop",
                        "finance_summary",
                        "add_expense",
                        "can_afford",
                        "agency_status",
                        "agency_lead_search",
                        "agency_add_lead",
                        "agency_score_leads",
                        "agency_draft_outreach",
                        "agency_approve_outreach",
                        "agency_send_outreach",
                        "agency_draft_proposal",
                        "agency_draft_contract",
                        "agency_project_plan",
                        "agency_start_project",
                        "agency_project_workflow",
                        "agency_invoice",
                        "agency_profit",
                        "agency_recommend_payment",
                        "agency_approve_payment",
                        "agency_trigger_payment",
                        "agency_pipeline",
                        "agency_api_budget",
                        "agency_business_layer",
                        "private_memory_summary",
                        "private_memory_search",
                        "android_companion_status",
                        "project_watchdog_status",
                        "project_watchdog_run",
                        "codebase_standards",
                        "codebase_standards_rules",
                        "simulate_action",
                        "privacy_vault_summary",
                        "privacy_vault_store",
                        "model_router_status",
                        "model_router_choose",
                        "self_debugger_status",
                        "self_debugger_report",
                        "tone_status",
                        "tone_analyze",
                        "crm_summary",
                        "crm_remember_person",
                        "crm_followups",
                        "learning_progress",
                        "learning_add_card",
                        "learning_quiz",
                        "research_briefings",
                        "research_brief",
                        "research_subscribe",
                        "academic_project",
                        "academic_export",
                        "git_status",
                        "git_branches",
                        "git_log",
                        "git_diff",
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
                        "model3d_create",
                        "workspace_context",
                        "workspace_context_status",
                        "offline_status",
                        "offline_activate",
                        "offline_deactivate",
                        "data_timeline",
                        "data_timeline_note",
                        "skill_training_summary",
                        "skill_training_start",
                        "skill_training_add_step",
                        "skill_training_finish",
                        "executive_summary",
                        "memory_review",
                        "memory_review_resolve",
                        "task_autopilot",
                        "task_autopilot_status",
                        "personality_profile",
                        "life_dashboard",
                        "skill_record_start",
                        "skill_record_step",
                        "skill_record_finish",
                        "documentation_brain",
                        "personal_search",
                        "trust_meter",
                        "learning_twin",
                        "relationship_assistant",
                        "deployment_commander",
                        "privacy_firewall",
                        "mission_start",
                        "mission_status",
                        "mission_pause",
                        "mission_resume",
                        "mission_stop",
                        "mission_approve",
                        "mission_approve_deploy",
                        "mission_evidence",
                        "qa_lab",
                        "qa_lab_reports",
                        "release_prepare",
                        "release_status",
                        "release_approve_deploy",
                        "error_radar",
                        "error_radar_status",
                        "semantic_index",
                        "semantic_search",
                        "semantic_status",
                        "browser_extension_status",
                        "browser_extension_insight",
                        "app_state_memory",
                        "app_state_search",
                        "rhythm_summary",
                        "energy_note",
                        "autonomous_debugger",
                        "autonomous_debugger_analyze",
                        "command_memory",
                        "command_memory_learn",
                        "calendar_email_brief",
                        "calendar_email_followups",
                        "autonomous_learning",
                        "environment_status",
                        "environment_snapshot",
                        "proof_report",
                        "continuity_status",
                        "continuity_capture",
                        "context_fusion",
                        "deep_project_autopilot",
                        "command_memory_defaults",
                        "silence_mode",
                        "browser_pc_copilot",
                        "browser_pc_debug",
                        "skill_evolution",
                        "skill_evolution_observe",
                        "safety_guardian",
                        "safety_preflight",
                        "phone_mesh",
                        "phone_handoff",
                        "agent_scheduler_status",
                        "agent_scheduler_plan",
                        "agent_scheduler_apply",
                        "retry_failed_tasks",
                        "schedule_overnight_research",
                        "test_build_monitor",
                        "test_build_monitor_status",
                        "reliability_score",
                        "reliability_score_status",
                        "model_benchmark",
                        "model_benchmark_status",
                        "deployment_brain",
                        "deployment_brain_status",
                        "os_autopilot",
                        "os_autopilot_status",
                        "version_guardian_snapshot",
                        "version_guardian_preflight",
                        "awareness_graph",
                        "awareness_graph_status",
                        "fix_loop",
                        "fix_loop_status",
                        "browser_pro",
                        "browser_pro_watch",
                        "browser_pro_fill",
                        "android_pro",
                        "memory_review_pro",
                        "app_mastery",
                        "local_ai_search",
                        "local_ai_index",
                        "life_os",
                        "life_os_next",
                        "security_guardian_pro",
                        "cloud_worker",
                        "cloud_worker_submit",
                        "autonomy_engine",
                        "autonomy_status",
                        "certainty_brain",
                        "certainty_record",
                        "vision_skill_learn",
                        "vision_skill_recognize",
                        "automation_daemon",
                        "automation_daemon_status",
                        "notification_intelligence",
                        "self_test_personality",
                        "project_memory",
                        "project_memory_remember",
                        "operator_skills",
                        "operator_skill_start",
                        "learning_roadmap",
                        "learning_roadmap_quiz",
                        "privacy_firewall_pro",
                        "device_mesh",
                        "device_mesh_handoff",
                        "release_engine",
                        "release_engine_status",
                        "decision_memory",
                        "decision_memory_infer",
                        "skill_improvement",
                        "skill_failure",
                        "workspace_coach",
                        "memory_debate",
                        "memory_review_debate",
                        "focus_protection",
                        "focus_mode",
                        "app_apprenticeship_start",
                        "app_apprenticeship_step",
                        "app_apprenticeship_finish",
                        "project_cto",
                        "conversation_continuity",
                        "conversation_capture",
                        "local_voice_brain",
                        "local_voice_defaults",
                        "voice_brain_repair",
                        "trust_dashboard",
                        "agent_quality",
                        "agent_leaderboard",
                        "agent_hire",
                        "agent_retire",
                        "agent_promote",
                        "agent_rewrite_role",
                        "agent_council",
                        "do_not_forget",
                        "dev_server_copilot",
                        "code_change_simulator",
                        "refactor_planner",
                        "taste_engine",
                        "taste_guidance",
                        "memory_constitution",
                        "reality_check",
                        "agent_simulation",
                        "command_graph",
                        "command_graph_defaults",
                        "emotional_timing",
                        "visual_skill_memory",
                        "failure_autopsy",
                    ],
                },
                "key": {"type": "string", "description": "Skill key such as all, figma_operator, vscode_debugger."},
                "root": {"type": "string", "description": "Project root for workspace brain."},
                "question": {"type": "string", "description": "Workspace question, e.g. where is auth logic?"},
                "app": {"type": "string", "description": "App operator id such as vscode, chrome, figma, gmail, whatsapp, discord, file_explorer."},
                "instruction": {"type": "string", "description": "Goal for an app-specific operator."},
                "request": {"type": "string", "description": "Autonomous coding request."},
                "prompt": {"type": "string", "description": "Prompt for a 3D model or creative asset."},
                "repo": {"type": "string", "description": "Git repository URL or GitHub owner/repo shorthand."},
                "destination": {"type": "string", "description": "Destination folder for cloning a repository, relative to the coding projects root when not absolute."},
                "remote": {"type": "string", "description": "Git remote name such as origin."},
                "branch": {"type": "string", "description": "Git branch name."},
                "base": {"type": "string", "description": "Base branch for a GitHub pull request."},
                "head": {"type": "string", "description": "Head branch for a GitHub pull request."},
                "message": {"type": "string", "description": "Git commit message."},
                "body": {"type": "string", "description": "GitHub pull request or issue body."},
                "state": {"type": "string", "description": "GitHub pull request state such as open, closed, merged, or all."},
                "staged": {"type": "boolean", "description": "Whether a Git diff should show staged changes."},
                "set_upstream": {"type": "boolean", "description": "Whether git push should set upstream tracking."},
                "create": {"type": "boolean", "description": "Whether git checkout should create a new branch."},
                "shape": {"type": "string", "description": "3D model shape hint such as city, house, human, cube, sphere, cylinder, cone, terrain, or spaceship."},
                "quality": {"type": "string", "description": "3D generation quality such as procedural or studio for Blender-backed photorealistic/PBR output."},
                "backend": {"type": "string", "description": "Preferred text-to-3D backend such as meshy, tripo, local_command, or a provider chain."},
                "path": {"type": "string", "description": "File path for backup/delete guard."},
                "label": {"type": "string", "description": "Backup label."},
                "on": {"type": "boolean", "description": "Turn Home Assistant focus mode on or off."},
                "target": {"type": "string", "description": "Fallback target."},
                "title": {"type": "string", "description": "Title for a vault item, goal, or study session."},
                "content": {"type": "string", "description": "Vault content, transcript, notes, or automation text."},
                "description": {"type": "string", "description": "Goal description."},
                "kind": {"type": "string", "description": "Vault item or study kind."},
                "query": {"type": "string", "description": "Vault, file, or project issue query."},
                "text": {"type": "string", "description": "Natural language automation or command repair text."},
                "heard_phrase": {"type": "string", "description": "Personal command phrase the user says."},
                "canonical_command": {"type": "string", "description": "Actual Friday command to run for a learned phrase."},
                "evidence": {"type": "string", "description": "Evidence text for proof reports."},
                "mode": {"type": "string", "description": "Context-aware silence mode such as normal, coding, debugging, study, silent_operator, gaming, or movie."},
                "signature": {"type": "string", "description": "Repeated workflow signature for skill evolution."},
                "log_text": {"type": "string", "description": "Terminal, browser, or test log text for deep project autopilot."},
                "prepare_fix": {"type": "boolean", "description": "Whether to create a safe fix-prep task."},
                "device_id": {"type": "string", "description": "Android companion device id for phone mesh handoffs."},
                "expected_text": {"type": "string", "description": "Correct transcript for voice repair."},
                "heard_text": {"type": "string", "description": "Incorrect transcript for voice repair."},
                "transcript": {"type": "string", "description": "Meeting or study transcript."},
                "paths": {"type": "array", "items": {"type": "string"}, "description": "Local folders to index."},
                "run_tests": {"type": "boolean", "description": "Whether project autopilot should run the configured test command."},
                "amount": {"type": "number", "description": "Money amount for finance actions."},
                "budget": {"type": "number", "description": "Budget amount for agency client projects."},
                "price": {"type": "number", "description": "Quoted price for agency proposals or contracts."},
                "currency": {"type": "string", "description": "Currency code such as USD or NGN."},
                "category": {"type": "string", "description": "Finance category or event category."},
                "company": {"type": "string", "description": "Company name for an agency lead."},
                "email": {"type": "string", "description": "Email address for a lead, client, or invoice recipient."},
                "website": {"type": "string", "description": "Website URL for a lead or client."},
                "niche": {"type": "string", "description": "Client niche or industry for agency lead search."},
                "location": {"type": "string", "description": "Lead or client location for agency search."},
                "need": {"type": "string", "description": "Client problem, opportunity, or project need."},
                "lead_id": {"type": "integer", "description": "Agency lead id."},
                "outreach_id": {"type": "integer", "description": "Agency outreach draft id."},
                "ids": {"type": "array", "items": {"type": "integer"}, "description": "Agency outreach draft ids for bulk approval or send."},
                "service_offer": {"type": "string", "description": "Service offer for agency outreach drafts."},
                "portfolio_url": {"type": "string", "description": "Portfolio link to include in agency outreach."},
                "call_to_action": {"type": "string", "description": "Call to action for agency outreach."},
                "tone": {"type": "string", "description": "Agency outreach tone such as professional or short."},
                "scope": {"type": "string", "description": "Scope for proposals, contracts, or project plans."},
                "timeline": {"type": "string", "description": "Timeline for agency project plans."},
                "provider": {"type": "string", "description": "API or subscription provider for agency payment recommendations."},
                "connector": {"type": "string", "description": "Friday Gateway connector id such as gmail, github, render, vercel, slack, discord, telegram, whatsapp, web, desktop, or browser_extension."},
                "event_type": {"type": "string", "description": "Friday Gateway event type such as message, task_request, lead, approval, deploy_signal, payment_signal, browser_event, mobile_event, github_event, calendar_event, error, cost, or proof."},
                "actor": {"type": "string", "description": "Person, service, or connector actor that produced a gateway event."},
                "route": {"type": "boolean", "description": "Whether a Friday Gateway event should be routed into tasks or approval inbox."},
                "enabled": {"type": "boolean", "description": "Whether to enable a connector, skill, or mode."},
                "trust_level": {"type": "string", "description": "Skill or connector trust level: verified, unverified, sandboxed, or blocked."},
                "metadata": {"type": "object", "description": "Small non-secret metadata payload."},
                "business_name": {"type": "string", "description": "Public-facing agency/business name."},
                "tagline": {"type": "string", "description": "Public-facing agency tagline."},
                "owner_email": {"type": "string", "description": "Public business contact email."},
                "recommendation_id": {"type": "integer", "description": "Agency payment recommendation ledger id."},
                "ledger_id": {"type": "integer", "description": "Agency ledger item id."},
                "client_name": {"type": "string", "description": "Invoice client name."},
                "client_email": {"type": "string", "description": "Invoice client email."},
                "project_id": {"type": "integer", "description": "Agency or project id."},
                "commit": {"type": "boolean", "description": "Whether an agency project workflow should commit changes."},
                "push": {"type": "boolean", "description": "Whether an agency project workflow should push changes."},
                "deploy": {"type": "boolean", "description": "Whether an agency project workflow should run the configured deploy command."},
                "deploy_command": {"type": "string", "description": "Configured deploy command for agency project workflows."},
                "task_type": {"type": "string", "description": "Model-router task type such as general, coding, writing, math, or vision."},
                "summary": {"type": "string", "description": "Failure summary for self-debugger reports."},
                "name": {"type": "string", "description": "Person name or workflow name."},
                "relationship": {"type": "string", "description": "Relationship for Personal CRM."},
                "notes": {"type": "string", "description": "Notes for CRM, timeline, or workflows."},
                "topic": {"type": "string", "description": "Learning or research topic."},
                "answer": {"type": "string", "description": "Learning card answer."},
                "cadence": {"type": "string", "description": "Briefing or routine cadence."},
                "citation_style": {"type": "string", "description": "Academic citation style such as APA, MLA, IEEE, or Chicago."},
                "formats": {"type": "array", "items": {"type": "string"}, "description": "Document export formats such as md, docx, and pdf."},
                "max_sources": {"type": "integer", "description": "Maximum research sources to gather for academic drafts."},
                "requirements": {"type": "string", "description": "Extra academic project or paper requirements from the user."},
                "workflow_id": {"type": "integer", "description": "Skill Training Studio workflow id."},
                "recording_id": {"type": "integer", "description": "Friday Skill Recorder recording id."},
                "review_id": {"type": "integer", "description": "Memory review id."},
                "decision": {"type": "string", "description": "Memory review decision such as confirm, keep, forget, update, or skip."},
                "profile": {"type": "string", "description": "Voice personality profile: focused, gentle, teacher, big_brother, silent_operator, debugger."},
                "goal": {"type": "string", "description": "Large goal for Task Autopilot with checkpoints."},
                "sphere": {"type": "string", "description": "Goal sphere such as programming, study, personal, deployment, finance, security, or general."},
                "domain": {"type": "string", "description": "Trust-meter domain such as code, desktop, deployment, security, money, or general."},
                "context": {"type": "string", "description": "Extra context for privacy firewall checks."},
                "mission_id": {"type": "integer", "description": "Mission id for Mission Control actions."},
                "mission_type": {"type": "string", "description": "Mission type such as project_builder, deployment, learning, or general."},
                "release_id": {"type": "integer", "description": "Release plan id for deploy approval."},
                "version": {"type": "string", "description": "Release version."},
                "include_private": {"type": "boolean", "description": "Whether search/index actions may include private chunks when allowed."},
                "energy": {"type": "integer", "description": "User energy from 1 to 10."},
                "focus": {"type": "integer", "description": "User focus from 1 to 10."},
                "mood": {"type": "string", "description": "User mood for operating rhythm."},
                "narration": {"type": "string", "description": "Narrated workflow step for Friday Skill Recorder."},
                "expected_result": {"type": "string", "description": "Expected result for a taught workflow step."},
                "reason": {"type": "string", "description": "Reason for offline survival mode changes."},
                "voice_active": {"type": "boolean", "description": "Whether the live voice loop is active and heavy workers should pause."},
                "command": {"type": "string", "description": "Local test/build command for guarded monitoring."},
                "task_types": {"type": "array", "items": {"type": "string"}, "description": "Benchmark task types such as coding, writing, math, fast_reply, or tool_planning."},
                "run_live": {"type": "boolean", "description": "Whether model benchmarking may call live providers."},
                "create_proof": {"type": "boolean", "description": "Whether a monitor action should create a proof report."},
                "selector": {"type": "string", "description": "Safe browser DOM selector for browser pro actions."},
                "value": {"type": "string", "description": "Safe non-secret value for browser pro fill actions."},
                "job_type": {"type": "string", "description": "Cloud worker safe job type: research, long_tests, deployment_check, document_indexing, scheduled_mission."},
                "prefer_cloud": {"type": "boolean", "description": "Whether cloud worker mode should prefer configured cloud workers over local fallback."},
                "force": {"type": "boolean", "description": "Force refresh live awareness/context."},
                "statement": {"type": "string", "description": "Fact, guess, or missing-evidence statement for the certainty brain."},
                "confidence": {"type": "number", "description": "Confidence score from 0.0 to 1.0 for certainty, UI patterns, or proof."},
                "source": {"type": "string", "description": "Source of an observation, evidence item, command handoff, or correction."},
                "pattern_type": {"type": "string", "description": "Vision skill pattern type such as toolbar, button, modal, crash_screen, login_expired, or deploy_button."},
                "meaning": {"type": "string", "description": "What a learned UI pattern means."},
                "action_hint": {"type": "string", "description": "Suggested action when a learned UI pattern appears."},
                "visual_cues": {"type": "array", "items": {"type": "string"}, "description": "Visible cues for computer vision skill learning."},
                "dom_cues": {"type": "array", "items": {"type": "string"}, "description": "DOM selectors or labels for browser/app skill learning."},
                "accessibility_cues": {"type": "array", "items": {"type": "string"}, "description": "Accessibility names/roles for app skill learning."},
                "purpose": {"type": "string", "description": "Why sensitive data is requested for Privacy Firewall Pro."},
                "source_device": {"type": "string", "description": "Device creating a command mesh handoff, such as laptop, android, or browser_extension."},
                "target_device": {"type": "string", "description": "Device that should receive a command mesh handoff."},
                "command_type": {"type": "string", "description": "Device mesh command type such as continue_on_laptop, browser_page, phone_camera, clipboard, or file_handoff."},
                "build_command": {"type": "string", "description": "Guarded build command for the autonomous release engineer."},
                "target_url": {"type": "string", "description": "Owned deployment URL to inspect for release proof checks."},
                "preference": {"type": "string", "description": "Decision preference to remember."},
                "threshold": {"type": "string", "description": "When a preference applies or should stop."},
                "failure": {"type": "string", "description": "Skill or tool failure to learn from."},
                "current_file": {"type": "string", "description": "Currently open file for workspace coaching."},
                "workflow": {"type": "string", "description": "App workflow name being demonstrated."},
                "session_id": {"type": "integer", "description": "App apprenticeship session id."},
                "observation": {"type": "string", "description": "Observed result from an app step."},
                "blocker": {"type": "string", "description": "Conversation or project blocker."},
                "expected": {"type": "string", "description": "Expected voice transcript or command."},
                "heard": {"type": "string", "description": "Incorrect heard voice transcript."},
                "agent_id": {"type": "string", "description": "Agent id for governance actions."},
                "agent_ids": {"type": "array", "items": {"type": "string"}, "description": "Agent ids for council or simulation."},
                "keywords": {"type": "array", "items": {"type": "string"}, "description": "Keywords for agent routing."},
                "risk_level": {"type": "string", "description": "Risk level for simulations."},
                "claim": {"type": "string", "description": "Claim to check for verified evidence."},
                "tool_result": {"type": "string", "description": "Tool result evidence for reality checks."},
                "correction": {"type": "string", "description": "User taste correction."},
                "sensitivity": {"type": "string", "description": "Memory sensitivity such as normal, private, or secret."},
                "phrase": {"type": "string", "description": "Personal command graph phrase."},
                "intent": {"type": "string", "description": "Command graph intent."},
                "steps": {"type": "array", "items": {"type": "string"}, "description": "Command graph workflow steps."},
                "screen_label": {"type": "string", "description": "Named app screen for visual skill memory."},
                "cues": {"type": "array", "items": {"type": "string"}, "description": "Visual cues for a learned app screen."},
                "root_cause": {"type": "string", "description": "Failure autopsy root cause."},
                "next_time": {"type": "string", "description": "What Friday should do next time after a failure."},
                "code_change_needed": {"type": "boolean", "description": "Whether a failure likely needs code improvement."},
                "limit": {"type": "integer"},
                "max_steps": {"type": "integer"},
            },
            "required": ["action"],
        },
    },
    {
        "name": "agent_team",
        "description": "Manages Friday v2's free/local background agent team: create/reassign persistent tasks, list work, inspect/cancel tasks, show roster, and start or stop local workers.",
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": [
                        "create_task",
                        "list_tasks",
                        "list_questions",
                        "get_task",
                        "reassign_task",
                        "cancel_task",
                        "approve_task",
                        "blackboard",
                        "thoughts",
                        "approval_inbox",
                        "status",
                        "roster",
                        "offices",
                        "office",
                        "start_workers",
                        "stop_workers",
                        "run_one",
                    ],
                },
                "title": {"type": "string", "description": "Task title for create_task."},
                "description": {"type": "string", "description": "Task details for create_task."},
                "agent_id": {"type": "string", "description": "Agent id, such as senior_developer, qa_engineer, research_analyst, product_manager."},
                "priority": {"type": "integer", "description": "Lower numbers run first."},
                "scheduled_at": {"type": "string", "description": "Optional ISO timestamp for future scheduled tasks."},
                "status": {"type": "string", "description": "Optional status filter for list_tasks."},
                "task_id": {"type": "integer", "description": "Task ID for get_task, reassign_task, or cancel_task."},
                "confirmation": {"type": "string", "description": "Explicit approval phrase for guarded tasks, e.g. I authorize task 4."},
                "limit": {"type": "integer", "description": "Maximum tasks to list."},
                "target": {"type": "string", "description": "Fallback free-form target."},
            },
            "required": ["action"],
        },
    },
    {
        "name": "self_update",
        "description": "Guarded workflow for improving Friday's own codebase. It can propose self-updates, stage exact replacements, and apply them only after explicit approval, tests, and rollback safety.",
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": [
                        "propose",
                        "list",
                        "get",
                        "approve",
                        "cancel",
                        "stage_change",
                        "apply",
                        "brain",
                    ],
                },
                "request": {"type": "string", "description": "Natural-language self-update request."},
                "update_id": {"type": "integer", "description": "Self-update session id."},
                "path": {"type": "string", "description": "Repo-relative path for a staged change."},
                "find_text": {"type": "string", "description": "Exact existing text to replace. Must match once."},
                "replace_text": {"type": "string", "description": "Replacement text or new file contents."},
                "summary": {"type": "string", "description": "Short reason for the staged change."},
                "confirmation": {"type": "string", "description": "Exact user approval phrase, such as I authorize self update 3 or I authorize applying self update 3."},
                "run_tests": {"type": "boolean", "description": "Whether to run tests after applying staged changes."},
                "target": {"type": "string", "description": "Fallback text target."},
                "limit": {"type": "integer", "description": "Maximum updates to list."},
            },
            "required": ["action"],
        },
    },
]

client = None


def configure_client(api_key: str | None = None) -> Any:
    global client
    if anthropic is None:
        client = None
    else:
        try:
            client = anthropic.Anthropic(api_key=api_key or os.getenv("ANTHROPIC_API_KEY"))
        except Exception as exc:
            client = None
            _log_failure("ANTHROPIC", 1, exc)
    return client


def ask(messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None, retries: int = 3) -> Any | None:
    request_chain = _REQUEST_PROVIDER_CHAIN.get()
    if request_chain:
        return ask_with_provider_chain(messages, request_chain, tools=tools, retries=retries)
    provider = str(config_value("llm_provider", "anthropic"))
    fallback = str(config_value("llm_fallback_provider", "none"))
    return ask_with_provider_chain(messages, [provider, fallback], tools=tools, retries=retries)


@contextmanager
def voice_route():
    """Temporarily route LLM calls through the fast voice model/provider chain."""
    chain = str(config_value("voice_llm_provider_chain", "nvidia")).strip() or "nvidia"
    nvidia_model = str(config_value("voice_nvidia_model", "meta/llama-3.1-8b-instruct")).strip()
    overrides = {
        "nvidia_model": nvidia_model or str(config_value("nvidia_model", "meta/llama-3.3-70b-instruct")),
        "nvidia_timeout": int(float(config_value("voice_llm_timeout", 25))),
        "nvidia_temperature": float(config_value("voice_llm_temperature", 0.2)),
        "nvidia_max_tokens": int(config_value("voice_llm_max_tokens", 160)),
    }
    chain_token = _REQUEST_PROVIDER_CHAIN.set(chain)
    config_token = _REQUEST_CONFIG.set(overrides)
    try:
        yield
    finally:
        _REQUEST_CONFIG.reset(config_token)
        _REQUEST_PROVIDER_CHAIN.reset(chain_token)


def _request_config_value(key: str, default: Any = None) -> Any:
    overrides = _REQUEST_CONFIG.get()
    if overrides and key in overrides:
        return overrides[key]
    return config_value(key, default)


def _canonical_provider(value: str) -> str:
    provider = str(value or "").strip().lower().replace("_", "-")
    aliases = {
        "local": "ollama",
        "nvidia-nim": "nvidia",
        "nim": "nvidia",
        "nvidia-build": "nvidia",
        "open-router": "openrouter",
    }
    return aliases.get(provider, provider)


def provider_sequence(providers: str | list[str] | tuple[str, ...] | None) -> list[str]:
    """Return a de-duplicated provider chain such as ['nvidia', 'ollama'].""" 
    if providers is None:
        raw_items: list[Any] = []
    elif isinstance(providers, str):
        normalized = providers.replace(",", ">").replace("|", ">")
        raw_items = normalized.split(">")
    else:
        raw_items = list(providers)

    sequence: list[str] = []
    for item in raw_items:
        provider = _canonical_provider(str(item or ""))
        if not provider or provider == "none" or provider in sequence:
            continue
        sequence.append(provider)
    return sequence


def provider_is_online(provider: str) -> bool:
    """Return True for hosted API providers that do not spend local CPU on inference."""
    return _canonical_provider(provider) in ONLINE_PROVIDERS


def provider_has_credentials(provider: str) -> bool:
    """Return whether a provider is usable without prompting for a missing API key."""
    provider = _canonical_provider(provider)
    if provider == "ollama":
        return True
    env_names = {
        "anthropic": "ANTHROPIC_API_KEY",
        "gemini": str(config_value("gemini_api_key_env", "GEMINI_API_KEY")),
        "nvidia": str(config_value("nvidia_api_key_env", "NVIDIA_API_KEY")),
        "openrouter": str(config_value("openrouter_api_key_env", "OPENROUTER_API_KEY")),
    }
    env_name = env_names.get(provider, "")
    return bool(env_name and not _is_placeholder_key(os.getenv(env_name, "")))


def online_provider_available(providers: str | list[str] | tuple[str, ...] | None = None) -> bool:
    """Return True when at least one configured hosted provider has credentials."""
    if providers is None:
        providers = ">".join(
            [
                str(config_value("llm_provider", "")),
                str(config_value("llm_fallback_provider", "")),
                str(config_value("v2_api_agent_online_providers", "nvidia>gemini>openrouter>anthropic")),
            ]
        )
    return any(provider_is_online(provider) and provider_has_credentials(provider) for provider in provider_sequence(providers))


def provider_limit_status() -> dict[str, Any]:
    """Small runtime snapshot for dashboards/tests without exposing secrets."""
    providers = provider_sequence(str(config_value("v2_api_agent_online_providers", "nvidia>gemini>openrouter>anthropic")) + ">ollama")
    now = time.monotonic()
    with _PROVIDER_LOCK:
        return {
            provider: {
                "online": provider_is_online(provider),
                "configured": provider_has_credentials(provider),
                "max_concurrency": _provider_max_concurrency(provider),
                "backoff_seconds": max(0.0, round(_PROVIDER_BACKOFF_UNTIL.get(provider, 0.0) - now, 2)),
                "failure_streak": int(_PROVIDER_FAILURE_STREAK.get(provider, 0)),
            }
            for provider in providers
        }


def ask_with_provider_chain(
    messages: list[dict[str, Any]],
    providers: str | list[str] | tuple[str, ...] | None,
    tools: list[dict[str, Any]] | None = None,
    retries: int = 3,
) -> Any | None:
    chain = provider_sequence(providers)
    if not chain:
        chain = provider_sequence([config_value("llm_provider", "anthropic"), config_value("llm_fallback_provider", "none")])
    for index, provider in enumerate(chain):
        response = _ask_provider(provider, messages, tools=tools, retries=retries if index == 0 else 1)
        if response is not None:
            return response
    return None


def ask_with_provider(
    messages: list[dict[str, Any]],
    provider: str = "",
    fallback_provider: str = "",
    tools: list[dict[str, Any]] | None = None,
    retries: int = 3,
) -> Any | None:
    primary = provider or str(config_value("llm_provider", "anthropic"))
    fallback = fallback_provider or str(config_value("llm_fallback_provider", "none"))
    return ask_with_provider_chain(messages, [primary, fallback], tools=tools, retries=retries)


def _ask_provider(provider: str, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None, retries: int) -> Any | None:
    provider = _canonical_provider(provider)
    if provider in {"none", ""}:
        return None
    with _provider_call_window(provider) as allowed:
        if not allowed:
            return None
        return _ask_provider_unlimited(provider, messages, tools=tools, retries=retries)


def _ask_provider_unlimited(provider: str, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None, retries: int) -> Any | None:
    if provider == "ollama":
        return _ask_ollama(messages, tools=tools, retries=retries)
    if provider == "gemini":
        return _ask_gemini(messages, tools=tools, retries=retries)
    if provider == "openrouter":
        return _ask_openrouter(messages, tools=tools, retries=retries)
    if provider == "nvidia":
        return _ask_nvidia(messages, tools=tools, retries=retries)
    return _ask_anthropic(messages, tools=tools, retries=retries)


@contextmanager
def _provider_call_window(provider: str):
    if not bool(config_value("llm_provider_limits_enabled", False)):
        yield True
        return
    provider = _canonical_provider(provider)
    if not _provider_backoff_allows(provider):
        yield False
        return
    semaphore = _provider_semaphore(provider)
    timeout = float(config_value("llm_provider_queue_timeout_seconds", 45.0))
    acquired = semaphore.acquire(timeout=max(0.0, timeout))
    if not acquired:
        _log_failure(provider.upper(), 1, RuntimeError("provider concurrency queue timed out"))
        yield False
        return
    try:
        _respect_provider_min_interval(provider)
        yield True
    finally:
        semaphore.release()


def _provider_semaphore(provider: str) -> threading.BoundedSemaphore:
    limit = _provider_max_concurrency(provider)
    key = (_canonical_provider(provider), limit)
    with _PROVIDER_LOCK:
        semaphore = _PROVIDER_LIMITERS.get(key)
        if semaphore is None:
            semaphore = threading.BoundedSemaphore(limit)
            _PROVIDER_LIMITERS[key] = semaphore
        return semaphore


def _provider_max_concurrency(provider: str) -> int:
    default = 1 if _canonical_provider(provider) == "ollama" else 2
    return max(1, int(_provider_config_value("llm_provider_max_concurrency", provider, default)))


def _provider_config_value(key: str, provider: str, default: Any) -> Any:
    raw = config_value(key, default)
    if isinstance(raw, dict):
        return raw.get(_canonical_provider(provider), raw.get("default", default))
    if isinstance(raw, str) and raw.strip().startswith("{"):
        try:
            data = json.loads(raw)
            if isinstance(data, dict):
                return data.get(_canonical_provider(provider), data.get("default", default))
        except json.JSONDecodeError:
            return default
    return raw


def _provider_backoff_allows(provider: str) -> bool:
    provider = _canonical_provider(provider)
    with _PROVIDER_LOCK:
        wait_seconds = _PROVIDER_BACKOFF_UNTIL.get(provider, 0.0) - time.monotonic()
    if wait_seconds <= 0:
        return True
    max_wait = float(config_value("llm_provider_max_backoff_wait_seconds", 20.0))
    if wait_seconds > max_wait:
        _log_failure(provider.upper(), 1, RuntimeError(f"provider in backoff for {wait_seconds:.1f}s"))
        return False
    time.sleep(wait_seconds)
    return True


def _respect_provider_min_interval(provider: str) -> None:
    min_interval = float(_provider_config_value("llm_provider_min_interval_seconds", provider, 0.0))
    if min_interval <= 0:
        return
    provider = _canonical_provider(provider)
    with _PROVIDER_LOCK:
        now = time.monotonic()
        wait_seconds = max(0.0, _PROVIDER_LAST_START.get(provider, 0.0) + min_interval - now)
        if wait_seconds <= 0:
            _PROVIDER_LAST_START[provider] = now
            return
    time.sleep(wait_seconds)
    with _PROVIDER_LOCK:
        _PROVIDER_LAST_START[provider] = time.monotonic()


def _record_provider_success(provider: str) -> None:
    provider = _canonical_provider(provider)
    with _PROVIDER_LOCK:
        _PROVIDER_FAILURE_STREAK[provider] = 0
        _PROVIDER_BACKOFF_UNTIL.pop(provider, None)


def _record_provider_failure(provider: str, exc: Exception) -> None:
    if not bool(config_value("llm_provider_limits_enabled", False)):
        return
    if not _looks_rate_or_capacity_limited(exc):
        return
    provider = _canonical_provider(provider)
    base = float(_provider_config_value("llm_provider_backoff_seconds", provider, 8.0))
    maximum = float(config_value("llm_provider_backoff_max_seconds", 60.0))
    with _PROVIDER_LOCK:
        streak = int(_PROVIDER_FAILURE_STREAK.get(provider, 0)) + 1
        _PROVIDER_FAILURE_STREAK[provider] = streak
        _PROVIDER_BACKOFF_UNTIL[provider] = time.monotonic() + min(maximum, base * (2 ** max(0, streak - 1)))


def _looks_rate_or_capacity_limited(exc: Exception) -> bool:
    response = getattr(exc, "response", None)
    status = int(getattr(response, "status_code", 0) or 0)
    if status in {408, 409, 425, 429, 500, 502, 503, 504, 529}:
        return True
    text = f"{exc.__class__.__name__} {exc}".lower()
    return any(marker in text for marker in ("rate", "quota", "capacity", "overload", "too many", "timeout", "temporarily"))


def _ask_anthropic(messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None, retries: int = 3) -> Any | None:
    if client is None:
        configure_client()
    if client is None:
        _log_call("missing-client", 0, 0, 0.0, "none")
        return None

    active_tools = TOOL_DEFINITIONS if tools is None else tools
    last_error = "unknown"
    model = str(config_value("anthropic_model", DEFAULT_MODEL))
    for attempt in range(retries):
        start = time.perf_counter()
        try:
            kwargs: dict[str, Any] = {
                "model": model,
                "max_tokens": 1024,
                "system": _system_prompt(),
                "messages": messages,
            }
            if active_tools:
                kwargs["tools"] = active_tools
            response = client.messages.create(**kwargs)
            latency_ms = (time.perf_counter() - start) * 1000
            input_tokens, output_tokens = _usage_counts(response)
            _log_call(model, input_tokens, output_tokens, latency_ms, _tool_used(response))
            _record_provider_success("anthropic")
            return response
        except Exception as exc:
            last_error = exc.__class__.__name__
            _record_provider_failure("anthropic", exc)
            if _is_auth_error(exc):
                _log_failure("AUTH", attempt + 1, exc)
                return None
            if not _is_retryable(exc) or attempt == retries - 1:
                _log_failure("CRITICAL", attempt + 1, exc)
                return None
            _log_failure(last_error, attempt + 1, exc)
            time.sleep(2**attempt)
    _log_failure("CRITICAL", retries, RuntimeError(last_error))
    return None


def _ask_ollama(messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None, retries: int = 3) -> Any | None:
    if requests is None:
        _log_failure("OLLAMA", 1, RuntimeError("requests is not installed"))
        return None

    active_tools = TOOL_DEFINITIONS if tools is None else tools
    model = str(config_value("ollama_model", "qwen3:8b"))
    base_url = str(config_value("ollama_base_url", "http://localhost:11434")).rstrip("/")
    timeout = int(config_value("ollama_timeout", 60))
    if os.getenv("JARVIS_FAST_VOICE") == "1":
        timeout = min(timeout, int(config_value("voice_ollama_timeout", 18)))
    payload: dict[str, Any] = {
        "model": model,
        "messages": _to_ollama_messages(messages),
        "stream": False,
        "think": False,
        "keep_alive": str(config_value("ollama_keep_alive", "30m")),
        "options": {
            "num_predict": int(config_value("ollama_num_predict", 120)),
            "num_ctx": int(config_value("ollama_num_ctx", 2048)),
            "temperature": float(config_value("ollama_temperature", 0.2)),
        },
    }
    if active_tools:
        payload["tools"] = _to_ollama_tools(active_tools)

    for attempt in range(retries):
        start = time.perf_counter()
        try:
            response = requests.post(f"{base_url}/api/chat", json=payload, timeout=timeout)
            response.raise_for_status()
            data = response.json()
            wrapped = _from_ollama_response(data)
            latency_ms = (time.perf_counter() - start) * 1000
            input_tokens, output_tokens = _usage_counts(wrapped)
            _log_call(f"ollama:{model}", input_tokens, output_tokens, latency_ms, _tool_used(wrapped))
            _record_provider_success("ollama")
            return wrapped
        except Exception as exc:
            _record_provider_failure("ollama", exc)
            if attempt == retries - 1:
                _log_failure("OLLAMA", attempt + 1, exc)
                return None
            _log_failure("OLLAMA", attempt + 1, exc)
            time.sleep(2**attempt)
    return None


def _ask_gemini(messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None, retries: int = 3) -> Any | None:
    if requests is None:
        _log_failure("GEMINI", 1, RuntimeError("requests is not installed"))
        return None
    api_key = os.getenv(str(config_value("gemini_api_key_env", "GEMINI_API_KEY")))
    if not api_key or _is_placeholder_key(api_key):
        _log_failure("GEMINI", 1, RuntimeError("GEMINI_API_KEY is missing"))
        return None
    model = str(config_value("gemini_model", "gemini-2.0-flash-lite"))
    base_url = str(config_value("gemini_base_url", "https://generativelanguage.googleapis.com/v1beta")).rstrip("/")
    timeout = int(config_value("gemini_timeout", 60))
    payload = {
        "systemInstruction": {"parts": [{"text": _system_prompt()}]},
        "contents": _to_gemini_contents(messages),
        "generationConfig": {
            "temperature": float(config_value("gemini_temperature", 0.2)),
            "maxOutputTokens": int(config_value("gemini_max_output_tokens", 512)),
        },
    }
    for attempt in range(retries):
        start = time.perf_counter()
        try:
            response = requests.post(f"{base_url}/models/{model}:generateContent?key={api_key}", json=payload, timeout=timeout)
            response.raise_for_status()
            data = response.json()
            text = _extract_gemini_text(data)
            wrapped = _text_response(text, raw=data)
            _log_call(f"gemini:{model}", 0, 0, (time.perf_counter() - start) * 1000, "text")
            _record_provider_success("gemini")
            return wrapped
        except Exception as exc:
            _record_provider_failure("gemini", exc)
            if attempt == retries - 1:
                _log_failure("GEMINI", attempt + 1, exc)
                return None
            _log_failure("GEMINI", attempt + 1, exc)
            time.sleep(2**attempt)
    return None


def _ask_openrouter(messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None, retries: int = 3) -> Any | None:
    if requests is None:
        _log_failure("OPENROUTER", 1, RuntimeError("requests is not installed"))
        return None
    api_key = os.getenv(str(config_value("openrouter_api_key_env", "OPENROUTER_API_KEY")))
    if not api_key or _is_placeholder_key(api_key):
        _log_failure("OPENROUTER", 1, RuntimeError("OPENROUTER_API_KEY is missing"))
        return None
    active_tools = TOOL_DEFINITIONS if tools is None else tools
    model = str(config_value("openrouter_model", "meta-llama/llama-3.2-3b-instruct:free"))
    base_url = str(config_value("openrouter_base_url", "https://openrouter.ai/api/v1")).rstrip("/")
    timeout = int(config_value("openrouter_timeout", 60))
    payload: dict[str, Any] = {
        "model": model,
        "messages": _to_openai_messages(messages),
        "temperature": float(config_value("openrouter_temperature", 0.2)),
        "max_tokens": int(config_value("openrouter_max_tokens", 512)),
    }
    if active_tools:
        payload["tools"] = _to_openai_tools(active_tools)
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "http://localhost",
        "X-Title": "Friday Personal AI Agent",
    }
    for attempt in range(retries):
        start = time.perf_counter()
        try:
            response = requests.post(f"{base_url}/chat/completions", json=payload, headers=headers, timeout=timeout)
            response.raise_for_status()
            data = response.json()
            wrapped = _from_openai_response(data)
            _log_call(f"openrouter:{model}", *_usage_counts(wrapped), (time.perf_counter() - start) * 1000, _tool_used(wrapped))
            _record_provider_success("openrouter")
            return wrapped
        except Exception as exc:
            _record_provider_failure("openrouter", exc)
            if attempt == retries - 1:
                _log_failure("OPENROUTER", attempt + 1, exc)
                return None
            _log_failure("OPENROUTER", attempt + 1, exc)
            time.sleep(2**attempt)
    return None


def _ask_nvidia(messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None, retries: int = 3) -> Any | None:
    if requests is None:
        _log_failure("NVIDIA", 1, RuntimeError("requests is not installed"))
        return None
    api_key = os.getenv(str(config_value("nvidia_api_key_env", "NVIDIA_API_KEY")))
    if not api_key or _is_placeholder_key(api_key):
        _log_failure("NVIDIA", 1, RuntimeError("NVIDIA_API_KEY is missing"))
        return None
    active_tools = TOOL_DEFINITIONS if tools is None else tools
    model = str(_request_config_value("nvidia_model", "meta/llama-3.3-70b-instruct"))
    base_url = str(_request_config_value("nvidia_base_url", "https://integrate.api.nvidia.com/v1")).rstrip("/")
    timeout = int(_request_config_value("nvidia_timeout", 60))
    payload: dict[str, Any] = {
        "model": model,
        "messages": _to_openai_messages(messages),
        "temperature": float(_request_config_value("nvidia_temperature", 0.2)),
        "max_tokens": int(_request_config_value("nvidia_max_tokens", 512)),
    }
    if active_tools:
        payload["tools"] = _to_openai_tools(active_tools)
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    for attempt in range(retries):
        start = time.perf_counter()
        try:
            response = requests.post(f"{base_url}/chat/completions", json=payload, headers=headers, timeout=timeout)
            response.raise_for_status()
            data = response.json()
            wrapped = _from_openai_response(data)
            _log_call(f"nvidia:{model}", *_usage_counts(wrapped), (time.perf_counter() - start) * 1000, _tool_used(wrapped))
            _record_provider_success("nvidia")
            return wrapped
        except Exception as exc:
            _record_provider_failure("nvidia", exc)
            if attempt == retries - 1:
                _log_failure("NVIDIA", attempt + 1, exc)
                return None
            _log_failure("NVIDIA", attempt + 1, exc)
            time.sleep(2**attempt)
    return None


def ask_simple(prompt: str, retries: int = 3) -> str | None:
    response = ask([{"role": "user", "content": prompt}], tools=[], retries=retries)
    if response is None:
        return None
    return extract_text(response)


def ask_simple_with_provider_chain(prompt: str, providers: str | list[str] | tuple[str, ...] | None, retries: int = 3) -> str | None:
    response = ask_with_provider_chain([{"role": "user", "content": prompt}], providers, tools=[], retries=retries)
    if response is None:
        return None
    return extract_text(response)


def ask_simple_with_provider(prompt: str, provider: str = "", fallback_provider: str = "", retries: int = 3) -> str | None:
    response = ask_with_provider([{"role": "user", "content": prompt}], provider=provider, fallback_provider=fallback_provider, tools=[], retries=retries)
    if response is None:
        return None
    return extract_text(response)


def extract_text(response: Any) -> str:
    parts: list[str] = []
    for block in getattr(response, "content", []) or []:
        block_type = getattr(block, "type", None) if not isinstance(block, dict) else block.get("type")
        if block_type == "text":
            parts.append(getattr(block, "text", None) if not isinstance(block, dict) else block.get("text", ""))
    return "\n".join(p for p in parts if p).strip()


def _to_ollama_tools(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    converted = []
    for tool in tools:
        converted.append(
            {
                "type": "function",
                "function": {
                    "name": tool["name"],
                    "description": tool.get("description", ""),
                    "parameters": tool.get("input_schema", {"type": "object", "properties": {}}),
                },
            }
        )
    return converted


def _to_openai_tools(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": tool["name"],
                "description": tool.get("description", ""),
                "parameters": tool.get("input_schema", {"type": "object", "properties": {}}),
            },
        }
        for tool in tools
    ]


def _to_openai_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    converted = [{"role": "system", "content": _system_prompt()}]
    for message in messages:
        content = message.get("content", "")
        if isinstance(content, list):
            content = "\n".join(str(item.get("content", "")) for item in content if isinstance(item, dict))
        converted.append({"role": message.get("role", "user"), "content": str(content)})
    return converted


def _to_gemini_contents(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    contents: list[dict[str, Any]] = []
    for message in messages:
        role = "model" if message.get("role") == "assistant" else "user"
        content = message.get("content", "")
        if isinstance(content, list):
            content = "\n".join(str(item.get("content", "")) for item in content if isinstance(item, dict))
        contents.append({"role": role, "parts": [{"text": str(content)}]})
    return contents or [{"role": "user", "parts": [{"text": ""}]}]


def _to_ollama_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    converted = [{"role": "system", "content": _system_prompt()}]
    for message in messages:
        role = message.get("role", "user")
        content = message.get("content", "")
        if isinstance(content, list):
            for item in content:
                if isinstance(item, dict) and item.get("type") == "tool_result":
                    converted.append(
                        {
                            "role": "tool",
                            "tool_name": item.get("tool_name") or item.get("tool_use_id", "tool"),
                            "content": str(item.get("content", "")),
                        }
                    )
            continue
        converted.append({"role": role, "content": str(content)})
    return converted


def _from_ollama_response(data: dict[str, Any]) -> Any:
    message = data.get("message", {})
    blocks = []
    for index, call in enumerate(message.get("tool_calls") or []):
        function = call.get("function", {})
        arguments = function.get("arguments") or {}
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments)
            except json.JSONDecodeError:
                arguments = {}
        blocks.append(
            SimpleNamespace(
                type="tool_use",
                name=function.get("name", ""),
                input=arguments,
                id=f"ollama_tool_{index}",
            )
        )
    content = str(message.get("content") or "").strip()
    if content and not blocks:
        blocks.append(SimpleNamespace(type="text", text=content))
    usage = SimpleNamespace(
        input_tokens=int(data.get("prompt_eval_count") or 0),
        output_tokens=int(data.get("eval_count") or 0),
    )
    return SimpleNamespace(content=blocks, usage=usage, raw=data)


def _from_openai_response(data: dict[str, Any]) -> Any:
    choice = (data.get("choices") or [{}])[0]
    message = choice.get("message") or {}
    blocks = []
    for index, call in enumerate(message.get("tool_calls") or []):
        function = call.get("function", {})
        arguments = function.get("arguments") or {}
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments)
            except json.JSONDecodeError:
                arguments = {}
        blocks.append(SimpleNamespace(type="tool_use", name=function.get("name", ""), input=arguments, id=call.get("id") or f"tool_{index}"))
    content = str(message.get("content") or "").strip()
    if content and not blocks:
        blocks.append(SimpleNamespace(type="text", text=content))
    usage_data = data.get("usage") or {}
    usage = SimpleNamespace(
        input_tokens=int(usage_data.get("prompt_tokens") or 0),
        output_tokens=int(usage_data.get("completion_tokens") or 0),
    )
    return SimpleNamespace(content=blocks, usage=usage, raw=data)


def _text_response(text: str, raw: dict[str, Any] | None = None) -> Any:
    return SimpleNamespace(content=[SimpleNamespace(type="text", text=str(text or "").strip())], usage=SimpleNamespace(input_tokens=0, output_tokens=0), raw=raw or {})


def _extract_gemini_text(data: dict[str, Any]) -> str:
    parts: list[str] = []
    for candidate in data.get("candidates") or []:
        for part in (candidate.get("content") or {}).get("parts") or []:
            if "text" in part:
                parts.append(str(part.get("text") or ""))
    return "\n".join(part for part in parts if part).strip()


def _usage_counts(response: Any) -> tuple[int, int]:
    usage = getattr(response, "usage", None)
    if usage is None and isinstance(response, dict):
        usage = response.get("usage")
    if usage is None:
        return 0, 0
    if isinstance(usage, dict):
        return int(usage.get("input_tokens", 0)), int(usage.get("output_tokens", 0))
    return int(getattr(usage, "input_tokens", 0)), int(getattr(usage, "output_tokens", 0))


def _tool_used(response: Any) -> str:
    for block in getattr(response, "content", []) or []:
        block_type = getattr(block, "type", None) if not isinstance(block, dict) else block.get("type")
        if block_type == "tool_use":
            return getattr(block, "name", None) if not isinstance(block, dict) else block.get("name", "tool")
    return "text"


def _is_retryable(exc: Exception) -> bool:
    if anthropic is None:
        return False
    retryable_names = {"RateLimitError", "APIStatusError", "APIConnectionError", "APIError"}
    return exc.__class__.__name__ in retryable_names


def _is_auth_error(exc: Exception) -> bool:
    return exc.__class__.__name__ == "AuthenticationError"


def _is_placeholder_key(value: str) -> bool:
    normalized = str(value or "").strip().lower()
    return not normalized or normalized.startswith("your_") or normalized in {"your_key_here", "sk-ant-placeholder", "xxxx-xxxx-xxxx-xxxx"}


def _log_call(model: str, input_tokens: int, output_tokens: int, latency_ms: float, tool_used: str) -> None:
    ensure_runtime_dirs()
    line = (
        f"{_dt.datetime.now().isoformat(timespec='seconds')} | model={model} | "
        f"input_tokens={input_tokens} | output_tokens={output_tokens} | "
        f"latency_ms={latency_ms:.0f} | tool_used={tool_used}"
    )
    with (LOG_DIR / "llm_calls.log").open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def _log_failure(kind: str, attempt: int, exc: Exception) -> None:
    ensure_runtime_dirs()
    line = f"{_dt.datetime.now().isoformat(timespec='seconds')} | failure={kind} | attempt={attempt} | error={exc}"
    with (LOG_DIR / "llm_calls.log").open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")
