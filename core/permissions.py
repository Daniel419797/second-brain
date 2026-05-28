"""User-controlled safety policies for Friday tools."""

from __future__ import annotations

import datetime as dt
import json
import sqlite3
import threading
from pathlib import Path
from typing import Any

from core.config import DATA_DIR, ensure_runtime_dirs

DB_PATH = DATA_DIR / "permissions.sqlite3"
VALID_MODES = {"allow", "ask", "block"}
_LOCK = threading.Lock()

DEFAULT_RULES: list[dict[str, str]] = [
    {"key": "pc_control.open_app", "label": "Open apps", "category": "Apps", "mode": "allow", "description": "Launch allowed or resolved apps."},
    {"key": "pc_control.open_path", "label": "Open files, folders, and URLs", "category": "Apps", "mode": "allow", "description": "Open local paths and web app links."},
    {"key": "pc_control.close_app", "label": "Close apps", "category": "Apps", "mode": "allow", "description": "Close running processes."},
    {"key": "pc_control.action", "label": "Generic PC action", "category": "Apps", "mode": "allow", "description": "Fallback for unclassified PC tool calls."},
    {"key": "pc_control.set_volume", "label": "Set volume", "category": "Device", "mode": "allow", "description": "Change speaker volume."},
    {"key": "pc_control.adjust_volume", "label": "Adjust volume", "category": "Device", "mode": "allow", "description": "Raise or lower speaker volume."},
    {"key": "pc_control.mute_volume", "label": "Mute volume", "category": "Device", "mode": "allow", "description": "Mute or unmute speakers."},
    {"key": "pc_control.get_volume", "label": "Read volume", "category": "Device", "mode": "allow", "description": "Read current speaker volume."},
    {"key": "pc_control.set_brightness", "label": "Set brightness", "category": "Device", "mode": "allow", "description": "Change display brightness."},
    {"key": "pc_control.adjust_brightness", "label": "Adjust brightness", "category": "Device", "mode": "allow", "description": "Raise or lower display brightness."},
    {"key": "pc_control.get_brightness", "label": "Read brightness", "category": "Device", "mode": "allow", "description": "Read current display brightness."},
    {"key": "pc_control.mouse_keyboard", "label": "Mouse and keyboard control", "category": "Desktop", "mode": "allow", "description": "Click, type, press keys, scroll, or drag."},
    {"key": "pc_control.focus_window", "label": "Focus windows", "category": "Desktop", "mode": "allow", "description": "Bring an existing window to the front."},
    {"key": "pc_control.active_window", "label": "Read active window", "category": "Desktop", "mode": "allow", "description": "Read the active window title."},
    {"key": "pc_control.pc_awareness", "label": "PC awareness inventory", "category": "Desktop", "mode": "allow", "description": "Read running apps, installed app entries, and Desktop/Start Menu shortcuts."},
    {"key": "pc_control.screen_size", "label": "Read screen size", "category": "Desktop", "mode": "allow", "description": "Read the screen dimensions."},
    {"key": "pc_control.mouse_position", "label": "Read mouse position", "category": "Desktop", "mode": "allow", "description": "Read cursor position."},
    {"key": "pc_control.screenshot", "label": "Screenshots", "category": "Desktop", "mode": "allow", "description": "Capture the visible screen."},
    {"key": "pc_control.inspect_screen", "label": "Inspect screen", "category": "Desktop", "mode": "allow", "description": "Analyze the visible screen."},
    {"key": "pc_control.screen_step", "label": "One-step screen action", "category": "Desktop", "mode": "allow", "description": "Run one vision-planned screen action."},
    {"key": "pc_control.inspect_browser", "label": "Inspect browser DOM", "category": "Desktop", "mode": "allow", "description": "Read visible browser DOM context."},
    {"key": "pc_control.playwright", "label": "Playwright browser control", "category": "Desktop", "mode": "allow", "description": "Control websites through Playwright DOM actions."},
    {"key": "pc_control.inspect_accessibility", "label": "Inspect app accessibility", "category": "Desktop", "mode": "allow", "description": "Read visible Windows UI Automation context."},
    {"key": "pc_control.open_browser_debug", "label": "Open browser debug mode", "category": "Desktop", "mode": "allow", "description": "Launch Chrome with local DevTools access for reliable automation."},
    {"key": "pc_control.desktop_task", "label": "Multi-step app control", "category": "Desktop", "mode": "allow", "description": "Operate apps through multi-step screen/browser control."},
    {"key": "pc_control.desktop_task_control", "label": "Desktop session controls", "category": "Desktop", "mode": "allow", "description": "Pause, resume, confirm, or cancel desktop sessions."},
    {"key": "pc_control.visual_monitor", "label": "Live vision monitor", "category": "Desktop", "mode": "allow", "description": "Start, stop, inspect, or capture live vision frames."},
    {"key": "pc_control.run_command", "label": "Run shell commands", "category": "System", "mode": "ask", "description": "Run PowerShell commands."},
    {"key": "pc_control.list_files", "label": "List files", "category": "Files", "mode": "allow", "description": "List folder contents."},
    {"key": "pc_control.read_file", "label": "Read files", "category": "Files", "mode": "allow", "description": "Read file contents."},
    {"key": "pc_control.delete_file", "label": "Delete files", "category": "Files", "mode": "ask", "description": "Delete or remove files if implemented later."},
    {"key": "send_email.send_email", "label": "Send email/messages", "category": "Messages", "mode": "ask", "description": "Send email or outbound messages."},
    {"key": "image_generation.generate", "label": "Generate images", "category": "Creative", "mode": "allow", "description": "Create images through configured local Stable Diffusion or optional hosted image APIs."},
    {"key": "image_generation.status", "label": "Image generation status", "category": "Creative", "mode": "allow", "description": "Read image generation provider setup and status."},
    {"key": "image_generation.list", "label": "List generated images", "category": "Creative", "mode": "allow", "description": "List local generated image records and paths."},
    {"key": "app_integrations.open_app", "label": "Open web apps", "category": "Integrations", "mode": "allow", "description": "Open Calendar, Docs, Sheets, WhatsApp, Discord, or Gmail."},
    {"key": "app_integrations.create_contact", "label": "Create contacts", "category": "Integrations", "mode": "allow", "description": "Save local contacts."},
    {"key": "app_integrations.create_reminder", "label": "Create reminders", "category": "Integrations", "mode": "allow", "description": "Save local reminders."},
    {"key": "app_integrations.create_calendar_event", "label": "Create calendar events", "category": "Integrations", "mode": "allow", "description": "Save local calendar events."},
    {"key": "app_integrations.create_doc", "label": "Create local docs", "category": "Integrations", "mode": "allow", "description": "Create local markdown documents."},
    {"key": "app_integrations.create_sheet", "label": "Create local sheets", "category": "Integrations", "mode": "allow", "description": "Create local CSV sheets."},
    {"key": "app_integrations.index_workspace", "label": "Index workspace", "category": "Workspace", "mode": "allow", "description": "Scan project files into the local workspace index."},
    {"key": "app_integrations.search_workspace", "label": "Search workspace", "category": "Workspace", "mode": "allow", "description": "Search the local workspace index."},
    {"key": "phone_bridge.status", "label": "Read phone bridge status", "category": "Phone", "mode": "allow", "description": "Read Android bridge status, registered devices, ADB state, and battery."},
    {"key": "phone_bridge.notify", "label": "Notify phone", "category": "Phone", "mode": "allow", "description": "Send ntfy push notifications to the Android phone."},
    {"key": "phone_bridge.ring", "label": "Ring/find phone", "category": "Phone", "mode": "allow", "description": "Send urgent phone alerts or ADB attention signals."},
    {"key": "phone_bridge.open_url", "label": "Open links on phone", "category": "Phone", "mode": "allow", "description": "Open URLs on Android through ADB or send a clickable phone notification."},
    {"key": "phone_bridge.dial", "label": "Dial phone calls", "category": "Phone", "mode": "ask", "description": "Open the Android dialer or place calls through the connected phone."},
    {"key": "phone_bridge.register_device", "label": "Register phone devices", "category": "Phone", "mode": "ask", "description": "Save Android phone bridge details such as ADB serial, ntfy topic, or phone number."},
    {"key": "phone_bridge.sms_draft", "label": "Draft phone SMS", "category": "Phone", "mode": "ask", "description": "Open an SMS draft on the connected Android phone."},
    {"key": "phone_bridge.file_transfer", "label": "Phone file transfer", "category": "Phone", "mode": "ask", "description": "Push or pull files between the PC and Android phone."},
    {"key": "phone_bridge.clipboard", "label": "Phone clipboard sync", "category": "Phone", "mode": "allow", "description": "Copy text to Android clipboard or send it as a copy notification."},
    {"key": "capability_center.status", "label": "Capability status and reports", "category": "Capabilities", "mode": "allow", "description": "Read home, personal ops, workspace, maintenance, and security summaries."},
    {"key": "capability_center.device_control", "label": "Smart/home device control", "category": "Capabilities", "mode": "ask", "description": "Control configured local smart bulbs, plugs, or other home devices."},
    {"key": "capability_center.automation", "label": "Automation recipes", "category": "Capabilities", "mode": "ask", "description": "Create or run automation recipes."},
    {"key": "capability_center.security_scope", "label": "Manage security scopes", "category": "Security Lab", "mode": "ask", "description": "Create or verify authorized security scopes."},
    {"key": "capability_center.security_scan", "label": "Defensive security scans", "category": "Security Lab", "mode": "ask", "description": "Run scoped local/owned defensive security checks such as port and dependency scans."},
    {"key": "capability_center.hardening", "label": "Security hardening plans", "category": "Security Lab", "mode": "allow", "description": "Generate defensive hardening recommendations and reports."},
    {"key": "power_center.skills", "label": "Skill/plugin library", "category": "Power Center", "mode": "allow", "description": "Install, enable, disable, and read local reusable skills."},
    {"key": "power_center.workspace", "label": "Workspace brain", "category": "Power Center", "mode": "allow", "description": "Analyze local code/project structure, TODOs, tests, dependencies, and docs."},
    {"key": "power_center.app_operator", "label": "App-specific operators", "category": "Power Center", "mode": "allow", "description": "Start specialist app operation sessions for VS Code, Chrome, Figma, Gmail, WhatsApp, Discord, and File Explorer."},
    {"key": "power_center.autonomous_coding", "label": "Autonomous coding mode", "category": "Power Center", "mode": "ask", "description": "Create guarded coding tasks with contracts, tests, approval, and rollback requirements."},
    {"key": "power_center.git_read", "label": "Git repository reads", "category": "Developer Tools", "mode": "allow", "description": "Read Git status, branches, logs, diffs, and GitHub CLI status."},
    {"key": "power_center.git_write", "label": "Git repository changes", "category": "Developer Tools", "mode": "ask", "description": "Clone repositories, pull changes, checkout branches, stage files, and create commits."},
    {"key": "power_center.git_push", "label": "Git push", "category": "Developer Tools", "mode": "ask", "description": "Push local commits to a configured remote repository."},
    {"key": "power_center.github", "label": "GitHub writes", "category": "Developer Tools", "mode": "ask", "description": "Create GitHub pull requests and issues through the GitHub CLI."},
    {"key": "power_center.model_3d", "label": "3D model generation", "category": "Creative", "mode": "allow", "description": "Generate local OBJ, STL, glTF, and GLB mesh files."},
    {"key": "power_center.personal_os", "label": "Personal Life OS", "category": "Power Center", "mode": "allow", "description": "Read/create routines, plans, follow-ups, mood/energy notes, and summaries."},
    {"key": "power_center.home_assistant", "label": "Home Assistant control", "category": "Power Center", "mode": "ask", "description": "Call Home Assistant services for smart-home control."},
    {"key": "power_center.backup", "label": "Backup and recovery", "category": "Power Center", "mode": "ask", "description": "Create backups, restore files, and guard risky deletes."},
    {"key": "power_center.guardian", "label": "Proactive guardian", "category": "Power Center", "mode": "allow", "description": "Scan important local health, security, reminder, and reliability signals."},
    {"key": "power_center.notifications", "label": "Notification center", "category": "Power Center", "mode": "allow", "description": "Read and mark Friday notifications."},
    {"key": "power_center.knowledge_vault", "label": "Personal knowledge vault", "category": "Power Center", "mode": "allow", "description": "Store and retrieve user preferences, corrections, people, projects, and priorities."},
    {"key": "power_center.voice_repair", "label": "Voice command repair", "category": "Power Center", "mode": "allow", "description": "Learn corrected transcripts and wake-name aliases."},
    {"key": "power_center.project_autopilot", "label": "Project autopilot", "category": "Power Center", "mode": "ask", "description": "Inspect projects, prepare safe fix tasks, and optionally run tests."},
    {"key": "power_center.pc_timeline", "label": "PC awareness timeline", "category": "Power Center", "mode": "allow", "description": "Record app/window changes and Friday action history."},
    {"key": "power_center.goal_manager", "label": "Goal manager", "category": "Power Center", "mode": "allow", "description": "Create and track larger goals, weekly plans, and next actions."},
    {"key": "power_center.local_files", "label": "Local file intelligence", "category": "Power Center", "mode": "allow", "description": "Index and search local folders, PDFs, and image metadata."},
    {"key": "power_center.study", "label": "Meeting and study companion", "category": "Power Center", "mode": "allow", "description": "Summarize transcripts, extract action items, flashcards, and follow-ups."},
    {"key": "power_center.automation_builder", "label": "Automation builder", "category": "Power Center", "mode": "ask", "description": "Create natural-language automations and run matching recipes."},
    {"key": "power_center.event_nervous_system", "label": "Event nervous system", "category": "Power Center", "mode": "allow", "description": "Watch local events such as app focus, reminders, downloads, phone connection, battery, and stuck agents."},
    {"key": "power_center.daily_companion", "label": "Daily companion", "category": "Power Center", "mode": "allow", "description": "Create daily briefings and low-noise check-ins."},
    {"key": "power_center.skill_marketplace", "label": "Skill marketplace", "category": "Power Center", "mode": "allow", "description": "Install, enable, disable, and inspect local skills."},
    {"key": "power_center.personal_finance", "label": "Personal finance helper", "category": "Power Center", "mode": "allow", "description": "Track local expenses, budgets, subscriptions, and affordability organization."},
    {"key": "power_center.private_memory", "label": "Private embedding memory", "category": "Power Center", "mode": "allow", "description": "Index and search local private memories with local-only embeddings or lexical fallback."},
    {"key": "power_center.android_companion", "label": "Android companion", "category": "Power Center", "mode": "ask", "description": "Use Android companion features such as notification sync, phone voice commands, and ring/call handoffs."},
    {"key": "power_center.project_watchdog", "label": "Project watchdog", "category": "Power Center", "mode": "ask", "description": "Continuously inspect projects for failing tests, stale docs, TODOs, dependencies, and secrets."},
    {"key": "power_center.codebase_standards", "label": "Codebase standards guard", "category": "Power Center", "mode": "allow", "description": "Scan code for security, performance, maintainability, reliability, and portability standards."},
    {"key": "power_center.sandbox_simulation", "label": "Sandbox simulation", "category": "Power Center", "mode": "allow", "description": "Simulate risky actions before controlling apps or changing code."},
    {"key": "power_center.privacy_vault", "label": "Privacy vault", "category": "Power Center", "mode": "ask", "description": "Store or reveal sensitive facts, documents, and credential references."},
    {"key": "power_center.model_router", "label": "Model router brain", "category": "Power Center", "mode": "allow", "description": "Choose the best local or online model route per task and track performance."},
    {"key": "power_center.self_debugger", "label": "Self-debugger", "category": "Power Center", "mode": "allow", "description": "Record failures, probable causes, test plans, and guarded self-update proposals."},
    {"key": "power_center.emotion_tone", "label": "Emotion and tone awareness", "category": "Power Center", "mode": "allow", "description": "Detect user tone and adjust reply style gently."},
    {"key": "power_center.personal_crm", "label": "Personal CRM", "category": "Power Center", "mode": "allow", "description": "Remember people, relationships, conversations, birthdays, promises, and follow-ups."},
    {"key": "power_center.learning_coach", "label": "Learning coach", "category": "Power Center", "mode": "allow", "description": "Manage study topics, spaced repetition cards, quizzes, and progress."},
    {"key": "power_center.research_briefings", "label": "Research briefings", "category": "Power Center", "mode": "allow", "description": "Create or subscribe to autonomous background research briefings."},
    {"key": "power_center.contextual_workspace", "label": "Contextual workspace autopilot", "category": "Power Center", "mode": "allow", "description": "Prepare project context from the active workspace, repo map, TODOs, and dev hints."},
    {"key": "power_center.offline_survival", "label": "Offline survival mode", "category": "Power Center", "mode": "allow", "description": "Switch or inspect reduced local-only operation for internet/provider failures."},
    {"key": "power_center.personal_data_timeline", "label": "Personal data timeline", "category": "Power Center", "mode": "allow", "description": "Search a timeline of PC events, Friday actions, downloads, and personal notes."},
    {"key": "power_center.skill_training_studio", "label": "Skill training studio", "category": "Power Center", "mode": "allow", "description": "Teach Friday workflows and publish them into the reusable skill library."},
    {"key": "power_center.executive", "label": "Executive capability summary", "category": "Power Center", "mode": "allow", "description": "Read Friday's high-level autonomy, memory, personality, and dashboard summary."},
    {"key": "power_center.memory_review", "label": "Real memory review", "category": "Power Center", "mode": "allow", "description": "Ask whether saved memories and preferences are still true, and record your review decisions."},
    {"key": "power_center.task_autopilot", "label": "Task autopilot checkpoints", "category": "Power Center", "mode": "ask", "description": "Decompose a big goal into persistent checkpoint tasks and run until completion unless blocked."},
    {"key": "power_center.personality_profile", "label": "Voice personality profiles", "category": "Power Center", "mode": "allow", "description": "Switch Friday's response style between focused, gentle, teacher, big brother, silent operator, and debugger modes."},
    {"key": "power_center.life_dashboard", "label": "Local life dashboard", "category": "Power Center", "mode": "allow", "description": "Read today's priorities, reminders, goals, PC health, projects, finances, relationships, and learning status."},
    {"key": "power_center.skill_recorder", "label": "Friday skill recorder", "category": "Power Center", "mode": "allow", "description": "Record narrated workflows and publish them as reusable local skills."},
    {"key": "power_center.documentation_brain", "label": "Autonomous documentation brain", "category": "Power Center", "mode": "ask", "description": "Inspect project structure and update generated architecture, setup, deployment, and known-issue notes."},
    {"key": "power_center.personal_search", "label": "Personal search engine", "category": "Power Center", "mode": "allow", "description": "Search files, memories, timelines, notes, project history, and redacted private-memory references."},
    {"key": "power_center.trust_meter", "label": "Trust meter", "category": "Power Center", "mode": "allow", "description": "Estimate confidence, risk, evidence, privacy triggers, and fallback plans before acting."},
    {"key": "power_center.learning_twin", "label": "Learning twin", "category": "Power Center", "mode": "allow", "description": "Summarize learning strengths, weak areas, next quiz, and recommended teaching style."},
    {"key": "power_center.relationship_assistant", "label": "Relationship assistant", "category": "Power Center", "mode": "allow", "description": "Surface birthdays, promises, follow-ups, and people to check in with."},
    {"key": "power_center.deployment_commander", "label": "Deployment commander", "category": "Power Center", "mode": "ask", "description": "Inspect owned app deployment status, logs hints, DNS, security headers, environment references, and rollback notes."},
    {"key": "power_center.privacy_firewall", "label": "Privacy firewall", "category": "Power Center", "mode": "allow", "description": "Detect when an action would use private memory, personal files, .env data, or secrets and require consent."},
    {"key": "power_center.mission_control", "label": "Mission control", "category": "Autonomy", "mode": "allow", "description": "Create, inspect, pause, resume, stop, and refresh approval-gated autonomous missions."},
    {"key": "power_center.mission_deploy", "label": "Mission deployment approval", "category": "Autonomy", "mode": "ask", "description": "Approve deployment/runbook steps for a mission or release."},
    {"key": "power_center.qa_lab", "label": "Autonomous QA lab", "category": "Autonomy", "mode": "allow", "description": "Generate QA evidence, test plans, and verification reports."},
    {"key": "power_center.release_manager", "label": "Release manager", "category": "Autonomy", "mode": "ask", "description": "Prepare releases, changelogs, rollback plans, and deploy approval gates."},
    {"key": "power_center.error_radar", "label": "Error radar", "category": "Autonomy", "mode": "allow", "description": "Watch logs, console events, failed tasks, crashed processes, and stuck missions."},
    {"key": "power_center.semantic_search", "label": "Local semantic search", "category": "Autonomy", "mode": "allow", "description": "Index and search safe local files, memory, task history, page snapshots, and project context."},
    {"key": "power_center.browser_extension", "label": "Browser extension bridge", "category": "Autonomy", "mode": "allow", "description": "Receive redacted DOM context and console events from the local Chrome/Edge extension."},
    {"key": "power_center.app_state_memory", "label": "App state memory", "category": "Autonomy", "mode": "allow", "description": "Remember successful and failed UI selectors, menus, and app interaction patterns."},
    {"key": "power_center.operating_rhythm", "label": "Operating rhythm", "category": "Autonomy", "mode": "allow", "description": "Track energy, focus, productive windows, and day-shape recommendations."},
    {"key": "power_center.autonomous_debugger", "label": "Autonomous debugger", "category": "Autonomy", "mode": "allow", "description": "Analyze logs, tests, browser console errors, and stack traces, then create fix-prep reports."},
    {"key": "power_center.command_memory", "label": "Personal command memory", "category": "Autonomy", "mode": "allow", "description": "Learn and use your personal command shortcuts."},
    {"key": "power_center.calendar_email_assistant", "label": "Calendar/email assistant", "category": "Autonomy", "mode": "allow", "description": "Read OAuth-backed calendar/email summaries and draft replies without sending."},
    {"key": "power_center.autonomous_learning", "label": "Autonomous learning mode", "category": "Autonomy", "mode": "allow", "description": "Create background learning plans and agent notebook lessons from your goals."},
    {"key": "power_center.environment_awareness", "label": "Environment awareness", "category": "Autonomy", "mode": "allow", "description": "Read active app, battery, network, open project, and useful context hints."},
    {"key": "power_center.proof_reports", "label": "Trust and proof reports", "category": "Autonomy", "mode": "allow", "description": "Create evidence reports listing changes, tests, failures, proof, and remaining risks."},
    {"key": "power_center.continuity", "label": "Continuity brain", "category": "Autonomy", "mode": "allow", "description": "Remember unfinished threads and capture stopped work across days."},
    {"key": "power_center.context_fusion", "label": "Real-time context fusion", "category": "Autonomy", "mode": "allow", "description": "Fuse PC, browser, phone, tasks, memory, tone, and calendar signals."},
    {"key": "power_center.deep_project_autopilot", "label": "Deep project autopilot", "category": "Autonomy", "mode": "ask", "description": "Coordinate project checks, debugger evidence, browser console, fix preparation, and proof reports."},
    {"key": "power_center.silence_mode", "label": "Context-aware silence", "category": "Autonomy", "mode": "allow", "description": "Switch when Friday should stay quiet or interrupt."},
    {"key": "power_center.browser_pc_copilot", "label": "Browser and PC copilot", "category": "Autonomy", "mode": "allow", "description": "Use local extension and PC awareness to summarize pages, debug console errors, and plan safe form actions."},
    {"key": "power_center.skill_evolution", "label": "Skill evolution", "category": "Autonomy", "mode": "allow", "description": "Notice repeated workflows and suggest reusable skills."},
    {"key": "power_center.personal_safety_guardian", "label": "Personal safety guardian", "category": "Safety", "mode": "allow", "description": "Scan for protected files, secret-like values, suspicious risky actions, and backup needs."},
    {"key": "power_center.phone_mesh", "label": "Phone-to-PC mesh", "category": "Phone", "mode": "allow", "description": "Create and inspect Android-to-PC handoffs and satellite-device context."},
    {"key": "power_center.agent_scheduler", "label": "Agent scheduler planning", "category": "Autonomy", "mode": "allow", "description": "Preview worker timing, quota-safe schedules, overnight research, and current agent queue state."},
    {"key": "power_center.agent_scheduler_apply", "label": "Agent scheduler changes", "category": "Autonomy", "mode": "ask", "description": "Start/stop background workers or retry failed tasks from scheduler recommendations."},
    {"key": "power_center.test_build_monitor", "label": "Autonomous test/build monitor", "category": "Autonomy", "mode": "ask", "description": "Run local build/test commands, inspect failures, and create proof reports."},
    {"key": "power_center.reliability_score", "label": "Reliability score system", "category": "Autonomy", "mode": "allow", "description": "Rate STT, tool success, false success claims, latency, and task completion."},
    {"key": "power_center.model_benchmark", "label": "Local model benchmark lab", "category": "Autonomy", "mode": "allow", "description": "Benchmark or estimate local/online model routes without live calls unless explicitly requested."},
    {"key": "power_center.deployment_brain", "label": "Project deployment brain", "category": "Autonomy", "mode": "allow", "description": "Passively inspect owned deployment uptime, DNS/SSL hints, security headers, release plans, and rollback notes."},
    {"key": "power_center.os_autopilot", "label": "Personal OS autopilot", "category": "Autonomy", "mode": "allow", "description": "Recommend what to do next based on rhythm, tasks, goals, and active context."},
    {"key": "power_center.version_guardian", "label": "Backup/version guardian", "category": "Safety", "mode": "ask", "description": "Snapshot important files, protect .env/configs, and record rollback notes before risky changes."},
    {"key": "power_center.awareness_graph", "label": "Realtime awareness graph", "category": "Autonomy", "mode": "allow", "description": "Read Friday's fused live map of PC, phone, browser, missions, approvals, tone, and errors."},
    {"key": "power_center.fix_loop", "label": "Autonomous fix loop", "category": "Autonomy", "mode": "ask", "description": "Detect errors, diagnose causes, prepare patch plans, and create approval-gated fix tasks."},
    {"key": "power_center.browser_pro", "label": "Browser extension pro mode", "category": "Autonomy", "mode": "allow", "description": "Use redacted DOM, console, network, page-change context, and safe browser actions."},
    {"key": "power_center.android_pro", "label": "Android companion app pro", "category": "Phone", "mode": "allow", "description": "Read Android app status, files, camera snapshots, clipboard, notifications, and voice-to-Friday events."},
    {"key": "power_center.memory_review_pro", "label": "Personal memory review pro", "category": "Power Center", "mode": "allow", "description": "Review saved preferences, goals, projects, people, shortcuts, and corrections."},
    {"key": "power_center.app_mastery", "label": "App operator mastery", "category": "Power Center", "mode": "allow", "description": "Plan specialist workflows with app-specific memory for Figma, VS Code, Chrome, Gmail, and file tools."},
    {"key": "power_center.local_ai_search", "label": "Local AI search engine", "category": "Power Center", "mode": "allow", "description": "Search safe local files, PDFs, code, memory, browser context, and timelines."},
    {"key": "power_center.life_os", "label": "Life OS mode", "category": "Power Center", "mode": "allow", "description": "Create daily plans, next action suggestions, study streaks, energy-aware scheduling, and summaries."},
    {"key": "power_center.security_guardian_pro", "label": "Security Guardian Pro", "category": "Safety", "mode": "ask", "description": "Run defensive local security checks for processes, ports, secrets, dependencies, startup, and extensions."},
    {"key": "power_center.cloud_worker", "label": "Cloud worker mode", "category": "Autonomy", "mode": "allow", "description": "Queue safe heavy jobs to configured cloud workers or local fallback tasks."},
    {"key": "power_center.autonomy_engine", "label": "Realtime autonomy engine", "category": "Autonomy", "mode": "ask", "description": "Let Friday choose, act, verify, retry, and escalate against the current goal."},
    {"key": "power_center.certainty_brain", "label": "What Friday knows", "category": "Autonomy", "mode": "allow", "description": "Track known facts, guesses, missing evidence, stale memories, and uncertainty."},
    {"key": "power_center.vision_skill_learning", "label": "Computer vision skill learning", "category": "Desktop", "mode": "allow", "description": "Learn reusable UI patterns, app screens, buttons, and recovery hints."},
    {"key": "power_center.automation_daemon", "label": "Personal automation daemon", "category": "Autonomy", "mode": "ask", "description": "Run background automations from PC, project, battery, test, and phone signals."},
    {"key": "power_center.notification_intelligence", "label": "Notification intelligence", "category": "Autonomy", "mode": "allow", "description": "Rank notifications by urgency, noise, action need, and current-project relevance."},
    {"key": "power_center.self_testing", "label": "Self-testing personality", "category": "Autonomy", "mode": "allow", "description": "Check whether Friday was too slow, unsupported, interruptive, or using weak tools."},
    {"key": "power_center.project_memory", "label": "Project memory per repo", "category": "Workspace", "mode": "allow", "description": "Remember architecture, commands, env var names, deploy steps, bugs, style, and fixes per repository."},
    {"key": "power_center.operator_skills", "label": "Operator skill drivers", "category": "Desktop", "mode": "allow", "description": "Use specialist drivers for Figma, VS Code, Chrome, Render, Vercel, Gmail, Calendar, and File Explorer."},
    {"key": "power_center.learning_roadmap", "label": "Personal learning roadmap", "category": "Learning", "mode": "allow", "description": "Build learning plans, weak-area reviews, quizzes, and weekly study guidance."},
    {"key": "power_center.privacy_firewall_pro", "label": "Privacy Firewall Pro", "category": "Safety", "mode": "ask", "description": "Require explicit explanation and approval before using .env, private files, personal memories, messages, or phone data."},
    {"key": "power_center.device_mesh", "label": "Multi-device command mesh", "category": "Phone", "mode": "allow", "description": "Create command handoffs between laptop, Android companion, and browser extension."},
    {"key": "power_center.release_engine", "label": "Autonomous release engineer", "category": "Autonomy", "mode": "ask", "description": "Prepare release build, QA, dependency, security-header, checklist, rollback, and proof reports."},
    {"key": "power_center.decision_memory", "label": "Decision memory", "category": "Autonomy", "mode": "allow", "description": "Learn and review how the user makes tradeoff decisions."},
    {"key": "power_center.skill_improvement", "label": "Autonomous skill improvement", "category": "Autonomy", "mode": "allow", "description": "Record repeated failures and create safe improvement proposals."},
    {"key": "power_center.workspace_coach", "label": "Live workspace coach", "category": "Autonomy", "mode": "allow", "description": "Observe local workspace signals and suggest useful fixes without noisy interruption."},
    {"key": "power_center.memory_debate", "label": "Personal memory debate", "category": "Memory", "mode": "allow", "description": "Show beliefs, evidence, confidence, and stale-memory review prompts."},
    {"key": "power_center.focus_protection", "label": "Focus protection", "category": "Autonomy", "mode": "allow", "description": "Batch low-priority alerts and switch quiet/focus modes."},
    {"key": "power_center.app_apprenticeship", "label": "Real app apprenticeship", "category": "Desktop", "mode": "allow", "description": "Record demonstrated app workflows and promote them into reusable operator skills."},
    {"key": "power_center.project_cto", "label": "Personal project CTO", "category": "Workspace", "mode": "allow", "description": "Summarize architecture, roadmap, risks, debt, release state, security posture, and next engineering task."},
    {"key": "power_center.conversation_continuity", "label": "Conversation continuity", "category": "Memory", "mode": "allow", "description": "Remember unfinished threads across days and summarize what is still open."},
    {"key": "power_center.local_voice_brain", "label": "Local voice brain", "category": "Voice", "mode": "allow", "description": "Install wake aliases, repair transcripts, and learn speaker-specific command shortcuts."},
    {"key": "power_center.trust_dashboard", "label": "Trust dashboard", "category": "Safety", "mode": "allow", "description": "Show what Friday knows, guessed, verified, failed, needs approval for, and is doing now."},
    {"key": "power_center.agent_quality", "label": "Agent quality manager", "category": "Agent Governance", "mode": "allow", "description": "Read and record agent quality, speed, evidence, and mistake scores."},
    {"key": "power_center.agent_lifecycle", "label": "Agent hiring, firing, and promotion", "category": "Agent Governance", "mode": "ask", "description": "Create, retire, promote, or rewrite dynamic specialist agents."},
    {"key": "power_center.agent_council", "label": "Agent council", "category": "Agent Governance", "mode": "allow", "description": "Ask several agents privately and compare their recommendations."},
    {"key": "power_center.do_not_forget", "label": "Do-not-forget memory router", "category": "Memory", "mode": "allow", "description": "Route important learned facts into temporary, project, user, identity, or skill memory."},
    {"key": "power_center.dev_server_copilot", "label": "Dev server copilot", "category": "Workspace", "mode": "allow", "description": "Analyze dev server logs and source context for likely causes."},
    {"key": "power_center.code_change_simulator", "label": "Code change simulator", "category": "Workspace", "mode": "allow", "description": "Predict affected files, tests, risks, and rollback before code edits."},
    {"key": "power_center.refactor_planner", "label": "Refactor planner", "category": "Workspace", "mode": "allow", "description": "Scan code for refactor candidates without modifying files."},
    {"key": "power_center.taste_engine", "label": "Personal taste engine", "category": "Memory", "mode": "allow", "description": "Learn user taste from corrections and apply guidance."},
    {"key": "power_center.memory_constitution", "label": "Memory constitution", "category": "Memory", "mode": "allow", "description": "Evaluate what Friday may remember, ask about, expire, or keep private."},
    {"key": "power_center.reality_check", "label": "Reality check mode", "category": "Safety", "mode": "allow", "description": "Check whether a claim is verified, partial, guessed, or unsupported."},
    {"key": "power_center.agent_simulation", "label": "Agent simulation sandbox", "category": "Agent Governance", "mode": "allow", "description": "Dry-run mission plans and failure cases before touching apps/files."},
    {"key": "power_center.command_graph", "label": "Personal command graph", "category": "Memory", "mode": "allow", "description": "Resolve and learn user command phrases as connected workflows."},
    {"key": "power_center.emotional_timing", "label": "Emotional timing", "category": "Voice", "mode": "allow", "description": "Adjust behavior timing based on frustration, focus, tiredness, or urgency."},
    {"key": "power_center.visual_skill_memory", "label": "Visual skill memory v2", "category": "Desktop", "mode": "allow", "description": "Learn named app screens and recurring visual UI patterns."},
    {"key": "power_center.failure_autopsy", "label": "Failure autopsy reports", "category": "Safety", "mode": "allow", "description": "Write short root-cause reports after serious failures."},
    {"key": "self_update.propose", "label": "Propose self-updates", "category": "Self Update", "mode": "allow", "description": "Plan improvements to Friday's own codebase without modifying files."},
    {"key": "self_update.list", "label": "List self-updates", "category": "Self Update", "mode": "allow", "description": "Inspect self-update proposals and state."},
    {"key": "self_update.get", "label": "Read self-updates", "category": "Self Update", "mode": "allow", "description": "Read one self-update proposal and its staged changes."},
    {"key": "self_update.stage_change", "label": "Stage self-update changes", "category": "Self Update", "mode": "ask", "description": "Stage exact code replacements before applying them."},
    {"key": "self_update.approve", "label": "Approve self-update planning", "category": "Self Update", "mode": "ask", "description": "Approve a self-update for implementation planning."},
    {"key": "self_update.apply", "label": "Apply self-update code changes", "category": "Self Update", "mode": "ask", "description": "Modify Friday's own codebase, run tests, and roll back on failure."},
    {"key": "self_update.cancel", "label": "Cancel self-updates", "category": "Self Update", "mode": "allow", "description": "Cancel a proposed or approved self-update."},
    {"key": "self_update.brain", "label": "Explain Friday brain", "category": "Self Update", "mode": "allow", "description": "Explain Friday's current cognitive architecture."},
]

MOUSE_KEYBOARD_ACTIONS = {"move_mouse", "click", "double_click", "right_click", "drag_mouse", "scroll", "type_text", "press_key", "hotkey"}
DESKTOP_TASK_ACTIONS = {"desktop_task"}
DESKTOP_TASK_CONTROL_ACTIONS = {"desktop_task_pause", "desktop_task_resume", "desktop_task_confirm", "desktop_task_cancel"}
VISUAL_MONITOR_ACTIONS = {"visual_monitor_start", "visual_monitor_stop", "visual_monitor_status", "visual_capture_once"}
PLAYWRIGHT_ACTIONS = {"playwright_inspect", "playwright_open", "playwright_run"}
PC_AWARENESS_ACTIONS = {"pc_awareness_snapshot", "list_running_apps", "list_installed_apps", "list_desktop_apps", "find_app"}


def init_db(path: Path | None = None) -> None:
    ensure_runtime_dirs()
    db_path = path or DB_PATH
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path, timeout=10) as conn:
        try:
            conn.execute("PRAGMA journal_mode=WAL")
        except sqlite3.OperationalError:
            pass
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS permission_rules (
                key TEXT PRIMARY KEY,
                label TEXT NOT NULL,
                category TEXT NOT NULL,
                mode TEXT NOT NULL,
                description TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS permission_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                key TEXT NOT NULL,
                tool_name TEXT NOT NULL,
                action TEXT NOT NULL,
                mode TEXT NOT NULL,
                decision TEXT NOT NULL,
                target TEXT NOT NULL,
                details_json TEXT NOT NULL
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_permission_events_time ON permission_events(timestamp)")
        _seed_defaults(conn)


def list_rules() -> list[dict[str, Any]]:
    init_db()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM permission_rules ORDER BY category, label").fetchall()
    return [_rule_from_row(row) for row in rows]


def get_rule(key: str) -> dict[str, Any]:
    init_db()
    canonical = _canonical_key(key)
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM permission_rules WHERE key=?", (canonical,)).fetchone()
    if row:
        return _rule_from_row(row)
    fallback = next((item for item in DEFAULT_RULES if item["key"] == canonical), None)
    if fallback:
        return dict(fallback)
    return {"key": canonical, "label": canonical, "category": "Other", "mode": "ask", "description": "Unclassified action."}


def set_rule(key: str, mode: str) -> dict[str, Any]:
    init_db()
    canonical = _canonical_key(key)
    normalized_mode = _normalize_mode(mode)
    existing = get_rule(canonical)
    now = _now()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.execute(
            """
            INSERT INTO permission_rules(key, label, category, mode, description, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET mode=excluded.mode, updated_at=excluded.updated_at
            """,
            (
                canonical,
                str(existing.get("label") or canonical),
                str(existing.get("category") or "Other"),
                normalized_mode,
                str(existing.get("description") or ""),
                now,
            ),
        )
    return get_rule(canonical)


def reset_defaults() -> list[dict[str, Any]]:
    init_db()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.execute("DELETE FROM permission_rules")
        _seed_defaults(conn)
    return list_rules()


def evaluate(tool_name: str, tool_input: dict[str, Any] | None = None) -> dict[str, Any]:
    tool_input = tool_input or {}
    key = key_for_tool(tool_name, tool_input)
    rule = get_rule(key)
    mode = _normalize_mode(str(rule.get("mode") or "ask"))
    decision = {
        "key": key,
        "mode": mode,
        "label": rule.get("label") or key,
        "category": rule.get("category") or "Other",
        "description": rule.get("description") or "",
        "target": _target_from_input(tool_input),
        "allowed": mode == "allow",
        "requires_confirmation": mode == "ask",
        "blocked": mode == "block",
    }
    try:
        from core import autonomy_control

        override = autonomy_control.override_decision(tool_name, tool_input, key=key, mode=mode)
    except Exception:
        override = None
    if override:
        decision["original_mode"] = mode
        decision.update(override)
    return decision


def key_for_tool(tool_name: str, tool_input: dict[str, Any] | None = None) -> str:
    tool_input = tool_input or {}
    name = str(tool_name or "").strip().lower()
    action = str(tool_input.get("action") or "").strip().lower()
    if name == "send_email":
        return "send_email.send_email"
    if name == "pc_control":
        if action in MOUSE_KEYBOARD_ACTIONS:
            return "pc_control.mouse_keyboard"
        if action in DESKTOP_TASK_ACTIONS:
            return "pc_control.desktop_task"
        if action in DESKTOP_TASK_CONTROL_ACTIONS:
            return "pc_control.desktop_task_control"
        if action in VISUAL_MONITOR_ACTIONS:
            return "pc_control.visual_monitor"
        if action in PLAYWRIGHT_ACTIONS:
            return "pc_control.playwright"
        if action in PC_AWARENESS_ACTIONS:
            return "pc_control.pc_awareness"
        return _canonical_key(f"pc_control.{action or 'action'}")
    if name == "app_integrations":
        return _canonical_key(f"app_integrations.{action or 'action'}")
    if name == "phone_bridge":
        if action in {"status", "list_devices", "battery", "battery_status", "events"}:
            return "phone_bridge.status"
        if action in {"notify", "send_notification", "send_to_phone"}:
            return "phone_bridge.notify"
        if action in {"ring", "call_me", "find_phone"}:
            return "phone_bridge.ring"
        if action == "open_url":
            return "phone_bridge.open_url"
        if action in {"dial", "call_number", "call_contact"}:
            return "phone_bridge.dial"
        if action == "register_device":
            return "phone_bridge.register_device"
        if action in {"sms_draft", "draft_sms"}:
            return "phone_bridge.sms_draft"
        if action in {"push_file", "send_file", "pull_file", "import_file", "import_photos", "photo_import"}:
            return "phone_bridge.file_transfer"
        if action in {"set_clipboard", "clipboard"}:
            return "phone_bridge.clipboard"
        return _canonical_key(f"phone_bridge.{action or 'action'}")
    if name == "capability_center":
        if action in {"overview", "home_status", "home_devices", "router_status", "local_network", "connection_quality", "daily_brief", "next_action", "plan_day", "workspace_map", "dependency_health", "maintenance_report", "security_overview", "list_security_scopes", "list_recipes"}:
            return "capability_center.status"
        if action in {"control_smart_device"}:
            return "capability_center.device_control"
        if action in {"create_recipe", "run_recipe"}:
            return "capability_center.automation"
        if action in {"create_security_scope", "verify_security_scope"}:
            return "capability_center.security_scope"
        if action in {"open_port_scan", "dependency_security_scan", "web_security_check", "secret_scan", "test_watch", "security_report"}:
            return "capability_center.security_scan"
        if action in {"hardening_plan", "auto_docs"}:
            return "capability_center.hardening"
        return _canonical_key(f"capability_center.{action or 'action'}")
    if name == "power_center":
        if action in {"install_builtin_skills", "list_skills"}:
            return "power_center.skills"
        if action in {"workspace_analyze", "workspace_question", "workspace_docs"}:
            return "power_center.workspace"
        if action in {"list_app_operators", "operate_app"}:
            return "power_center.app_operator"
        if action in {"autonomous_coding"}:
            return "power_center.autonomous_coding"
        if action in {"git_status", "git_branches", "git_log", "git_diff", "github_status", "github_pr_list"}:
            return "power_center.git_read"
        if action in {"git_clone", "git_checkout", "git_pull", "git_add", "git_commit"}:
            return "power_center.git_write"
        if action in {"git_push"}:
            return "power_center.git_push"
        if action in {"github_pr_create", "github_issue_create"}:
            return "power_center.github"
        if action in {"model3d_create"}:
            return "power_center.model_3d"
        if action in {"daily_plan", "next_action", "end_of_day"}:
            return "power_center.personal_os"
        if action in {"home_assistant_status", "home_assistant_focus"}:
            return "power_center.home_assistant"
        if action in {"backup_config", "backup_file", "list_backups", "delete_guard"}:
            return "power_center.backup"
        if action in {"guardian_scan", "guardian_status"}:
            return "power_center.guardian"
        if action in {"notifications"}:
            return "power_center.notifications"
        if action in {"remember_vault", "vault_search", "weekly_priorities"}:
            return "power_center.knowledge_vault"
        if action in {"voice_repair"}:
            return "power_center.voice_repair"
        if action in {"project_autopilot", "project_prepare_fixes"}:
            return "power_center.project_autopilot"
        if action in {"pc_timeline", "pc_timeline_summary"}:
            return "power_center.pc_timeline"
        if action in {"goal_plan", "goal_next"}:
            return "power_center.goal_manager"
        if action in {"file_index", "file_search", "folder_summary"}:
            return "power_center.local_files"
        if action in {"study_session"}:
            return "power_center.study"
        if action in {"automation_from_text", "automation_run_matches"}:
            return "power_center.automation_builder"
        if action in {"event_status", "event_scan"}:
            return "power_center.event_nervous_system"
        if action in {"daily_companion_brief", "daily_companion_checkin"}:
            return "power_center.daily_companion"
        if action in {"skill_marketplace", "skill_marketplace_install"}:
            return "power_center.skill_marketplace"
        if action in {"finance_summary", "add_expense", "can_afford"}:
            return "power_center.personal_finance"
        if action in {"private_memory_summary", "private_memory_search"}:
            return "power_center.private_memory"
        if action in {"android_companion_status"}:
            return "power_center.android_companion"
        if action in {"project_watchdog_status", "project_watchdog_run"}:
            return "power_center.project_watchdog"
        if action in {"codebase_standards", "codebase_standards_rules"}:
            return "power_center.codebase_standards"
        if action in {"simulate_action"}:
            return "power_center.sandbox_simulation"
        if action in {"privacy_vault_summary", "privacy_vault_store"}:
            return "power_center.privacy_vault"
        if action in {"model_router_status", "model_router_choose"}:
            return "power_center.model_router"
        if action in {"self_debugger_status", "self_debugger_report"}:
            return "power_center.self_debugger"
        if action in {"tone_status", "tone_analyze"}:
            return "power_center.emotion_tone"
        if action in {"crm_summary", "crm_remember_person", "crm_followups"}:
            return "power_center.personal_crm"
        if action in {"learning_progress", "learning_add_card", "learning_quiz"}:
            return "power_center.learning_coach"
        if action in {"research_briefings", "research_brief", "research_subscribe"}:
            return "power_center.research_briefings"
        if action in {"workspace_context", "workspace_context_status"}:
            return "power_center.contextual_workspace"
        if action in {"offline_status", "offline_activate", "offline_deactivate"}:
            return "power_center.offline_survival"
        if action in {"data_timeline", "data_timeline_note"}:
            return "power_center.personal_data_timeline"
        if action in {"skill_training_summary", "skill_training_start", "skill_training_add_step", "skill_training_finish"}:
            return "power_center.skill_training_studio"
        if action in {"executive_summary"}:
            return "power_center.executive"
        if action in {"memory_review", "memory_review_resolve"}:
            return "power_center.memory_review"
        if action in {"task_autopilot", "task_autopilot_status"}:
            return "power_center.task_autopilot"
        if action in {"personality_profile"}:
            return "power_center.personality_profile"
        if action in {"life_dashboard"}:
            return "power_center.life_dashboard"
        if action in {"skill_record_start", "skill_record_step", "skill_record_finish"}:
            return "power_center.skill_recorder"
        if action in {"documentation_brain"}:
            return "power_center.documentation_brain"
        if action in {"personal_search"}:
            return "power_center.personal_search"
        if action in {"trust_meter"}:
            return "power_center.trust_meter"
        if action in {"learning_twin"}:
            return "power_center.learning_twin"
        if action in {"relationship_assistant"}:
            return "power_center.relationship_assistant"
        if action in {"deployment_commander"}:
            return "power_center.deployment_commander"
        if action in {"privacy_firewall"}:
            return "power_center.privacy_firewall"
        if action in {"mission_start", "mission_status", "mission_pause", "mission_resume", "mission_stop", "mission_approve", "mission_evidence"}:
            return "power_center.mission_control"
        if action in {"mission_approve_deploy", "release_approve_deploy"}:
            return "power_center.mission_deploy"
        if action in {"qa_lab", "qa_lab_reports"}:
            return "power_center.qa_lab"
        if action in {"release_prepare", "release_status"}:
            return "power_center.release_manager"
        if action in {"error_radar", "error_radar_status"}:
            return "power_center.error_radar"
        if action in {"semantic_index", "semantic_search", "semantic_status"}:
            return "power_center.semantic_search"
        if action in {"browser_extension_status", "browser_extension_insight"}:
            return "power_center.browser_extension"
        if action in {"app_state_memory", "app_state_search"}:
            return "power_center.app_state_memory"
        if action in {"rhythm_summary", "energy_note"}:
            return "power_center.operating_rhythm"
        if action in {"autonomous_debugger", "autonomous_debugger_analyze"}:
            return "power_center.autonomous_debugger"
        if action in {"command_memory", "command_memory_learn", "command_memory_defaults"}:
            return "power_center.command_memory"
        if action in {"calendar_email_brief", "calendar_email_followups"}:
            return "power_center.calendar_email_assistant"
        if action in {"autonomous_learning"}:
            return "power_center.autonomous_learning"
        if action in {"environment_status", "environment_snapshot"}:
            return "power_center.environment_awareness"
        if action in {"proof_report"}:
            return "power_center.proof_reports"
        if action in {"continuity_status", "continuity_capture"}:
            return "power_center.continuity"
        if action in {"context_fusion"}:
            return "power_center.context_fusion"
        if action in {"deep_project_autopilot"}:
            return "power_center.deep_project_autopilot"
        if action in {"silence_mode"}:
            return "power_center.silence_mode"
        if action in {"browser_pc_copilot", "browser_pc_debug"}:
            return "power_center.browser_pc_copilot"
        if action in {"skill_evolution", "skill_evolution_observe"}:
            return "power_center.skill_evolution"
        if action in {"safety_guardian", "safety_preflight"}:
            return "power_center.personal_safety_guardian"
        if action in {"phone_mesh", "phone_handoff"}:
            return "power_center.phone_mesh"
        if action in {"agent_scheduler_status", "agent_scheduler_plan", "schedule_overnight_research"}:
            return "power_center.agent_scheduler"
        if action in {"agent_scheduler_apply", "retry_failed_tasks"}:
            return "power_center.agent_scheduler_apply"
        if action in {"test_build_monitor", "test_build_monitor_status"}:
            return "power_center.test_build_monitor"
        if action in {"reliability_score", "reliability_score_status"}:
            return "power_center.reliability_score"
        if action in {"model_benchmark", "model_benchmark_status"}:
            return "power_center.model_benchmark"
        if action in {"deployment_brain", "deployment_brain_status"}:
            return "power_center.deployment_brain"
        if action in {"os_autopilot", "os_autopilot_status"}:
            return "power_center.os_autopilot"
        if action in {"version_guardian_snapshot", "version_guardian_preflight"}:
            return "power_center.version_guardian"
        if action in {"awareness_graph", "awareness_graph_status"}:
            return "power_center.awareness_graph"
        if action in {"fix_loop", "fix_loop_status"}:
            return "power_center.fix_loop"
        if action in {"browser_pro", "browser_pro_watch", "browser_pro_fill"}:
            return "power_center.browser_pro"
        if action in {"android_pro"}:
            return "power_center.android_pro"
        if action in {"memory_review_pro"}:
            return "power_center.memory_review_pro"
        if action in {"app_mastery"}:
            return "power_center.app_mastery"
        if action in {"local_ai_search", "local_ai_index"}:
            return "power_center.local_ai_search"
        if action in {"life_os", "life_os_next"}:
            return "power_center.life_os"
        if action in {"security_guardian_pro"}:
            return "power_center.security_guardian_pro"
        if action in {"cloud_worker", "cloud_worker_submit"}:
            return "power_center.cloud_worker"
        if action in {"autonomy_engine", "autonomy_status"}:
            return "power_center.autonomy_engine"
        if action in {"certainty_brain", "certainty_record"}:
            return "power_center.certainty_brain"
        if action in {"vision_skill_learn", "vision_skill_recognize"}:
            return "power_center.vision_skill_learning"
        if action in {"automation_daemon", "automation_daemon_status"}:
            return "power_center.automation_daemon"
        if action in {"notification_intelligence"}:
            return "power_center.notification_intelligence"
        if action in {"self_test_personality"}:
            return "power_center.self_testing"
        if action in {"project_memory", "project_memory_remember"}:
            return "power_center.project_memory"
        if action in {"operator_skills", "operator_skill_start"}:
            return "power_center.operator_skills"
        if action in {"learning_roadmap", "learning_roadmap_quiz"}:
            return "power_center.learning_roadmap"
        if action in {"privacy_firewall_pro"}:
            return "power_center.privacy_firewall_pro"
        if action in {"device_mesh", "device_mesh_handoff"}:
            return "power_center.device_mesh"
        if action in {"release_engine", "release_engine_status"}:
            return "power_center.release_engine"
        if action in {"decision_memory", "decision_memory_infer"}:
            return "power_center.decision_memory"
        if action in {"skill_improvement", "skill_failure"}:
            return "power_center.skill_improvement"
        if action in {"workspace_coach"}:
            return "power_center.workspace_coach"
        if action in {"memory_debate", "memory_review_debate"}:
            return "power_center.memory_debate"
        if action in {"focus_protection", "focus_mode"}:
            return "power_center.focus_protection"
        if action in {"app_apprenticeship_start", "app_apprenticeship_step", "app_apprenticeship_finish"}:
            return "power_center.app_apprenticeship"
        if action in {"project_cto"}:
            return "power_center.project_cto"
        if action in {"conversation_continuity", "conversation_capture"}:
            return "power_center.conversation_continuity"
        if action in {"local_voice_brain", "local_voice_defaults", "voice_brain_repair"}:
            return "power_center.local_voice_brain"
        if action in {"trust_dashboard"}:
            return "power_center.trust_dashboard"
        if action in {"agent_quality", "agent_leaderboard"}:
            return "power_center.agent_quality"
        if action in {"agent_hire", "agent_retire", "agent_promote", "agent_rewrite_role"}:
            return "power_center.agent_lifecycle"
        if action in {"agent_council"}:
            return "power_center.agent_council"
        if action in {"do_not_forget"}:
            return "power_center.do_not_forget"
        if action in {"dev_server_copilot"}:
            return "power_center.dev_server_copilot"
        if action in {"code_change_simulator"}:
            return "power_center.code_change_simulator"
        if action in {"refactor_planner"}:
            return "power_center.refactor_planner"
        if action in {"taste_engine", "taste_guidance"}:
            return "power_center.taste_engine"
        if action in {"memory_constitution"}:
            return "power_center.memory_constitution"
        if action in {"reality_check"}:
            return "power_center.reality_check"
        if action in {"agent_simulation"}:
            return "power_center.agent_simulation"
        if action in {"command_graph", "command_graph_defaults"}:
            return "power_center.command_graph"
        if action in {"emotional_timing"}:
            return "power_center.emotional_timing"
        if action in {"visual_skill_memory"}:
            return "power_center.visual_skill_memory"
        if action in {"failure_autopsy"}:
            return "power_center.failure_autopsy"
        return _canonical_key(f"power_center.{action or 'action'}")
    if name == "self_update":
        return _canonical_key(f"self_update.{action or 'action'}")
    return _canonical_key(f"{name}.{action or name}")


def record_decision(
    tool_name: str,
    tool_input: dict[str, Any] | None,
    *,
    decision: str,
    mode: str | None = None,
    key: str | None = None,
    details: dict[str, Any] | None = None,
) -> int:
    init_db()
    tool_input = tool_input or {}
    action = str(tool_input.get("action") or "")
    canonical = key or key_for_tool(tool_name, tool_input)
    normalized_mode = _normalize_mode(mode or str(get_rule(canonical).get("mode") or "ask"))
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        cursor = conn.execute(
            """
            INSERT INTO permission_events(timestamp, key, tool_name, action, mode, decision, target, details_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                _now(),
                canonical,
                str(tool_name or ""),
                action,
                normalized_mode,
                str(decision or ""),
                _target_from_input(tool_input),
                json.dumps(details or {}, ensure_ascii=True, sort_keys=True, default=str),
            ),
        )
        return int(cursor.lastrowid)


def recent_events(limit: int = 50) -> list[dict[str, Any]]:
    init_db()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM permission_events ORDER BY id DESC LIMIT ?",
            (max(1, min(200, int(limit))),),
        ).fetchall()
    return [
        {
            "id": int(row["id"]),
            "timestamp": row["timestamp"],
            "key": row["key"],
            "tool_name": row["tool_name"],
            "action": row["action"],
            "mode": row["mode"],
            "decision": row["decision"],
            "target": row["target"],
            "details": _json_loads(row["details_json"]),
        }
        for row in rows
    ]


def set_category(category: str, mode: str) -> list[dict[str, Any]]:
    normalized = str(category or "").strip().lower()
    changed = []
    for rule in list_rules():
        if str(rule.get("category") or "").strip().lower() == normalized:
            changed.append(set_rule(str(rule["key"]), mode))
    return changed


def set_named_policy(name: str, mode: str) -> list[dict[str, Any]]:
    lowered = str(name or "").strip().lower()
    aliases = {
        "volume": ["pc_control.set_volume", "pc_control.adjust_volume", "pc_control.mute_volume", "pc_control.get_volume"],
        "audio": ["pc_control.set_volume", "pc_control.adjust_volume", "pc_control.mute_volume", "pc_control.get_volume"],
        "brightness": ["pc_control.set_brightness", "pc_control.adjust_brightness", "pc_control.get_brightness"],
        "files": ["pc_control.list_files", "pc_control.read_file", "pc_control.delete_file"],
        "deleting files": ["pc_control.delete_file"],
        "delete files": ["pc_control.delete_file"],
        "messages": ["send_email.send_email"],
        "email": ["send_email.send_email"],
        "sending messages": ["send_email.send_email"],
        "mouse": ["pc_control.mouse_keyboard"],
        "keyboard": ["pc_control.mouse_keyboard"],
        "desktop": ["pc_control.desktop_task", "pc_control.mouse_keyboard"],
        "pc awareness": ["pc_control.pc_awareness", "pc_control.active_window"],
        "installed apps": ["pc_control.pc_awareness"],
        "running apps": ["pc_control.pc_awareness", "pc_control.active_window"],
        "phone": [
            "phone_bridge.status",
            "phone_bridge.notify",
            "phone_bridge.ring",
            "phone_bridge.open_url",
            "phone_bridge.dial",
            "phone_bridge.sms_draft",
            "phone_bridge.file_transfer",
            "phone_bridge.clipboard",
        ],
        "phone calls": ["phone_bridge.dial"],
        "ring phone": ["phone_bridge.ring"],
        "phone sms": ["phone_bridge.sms_draft"],
        "sms": ["phone_bridge.sms_draft"],
        "phone files": ["phone_bridge.file_transfer"],
        "file transfer": ["phone_bridge.file_transfer"],
        "phone clipboard": ["phone_bridge.clipboard"],
        "playwright": ["pc_control.playwright"],
        "browser automation": ["pc_control.playwright", "pc_control.inspect_browser", "pc_control.open_browser_debug"],
        "shell": ["pc_control.run_command"],
        "commands": ["pc_control.run_command"],
        "capability center": ["capability_center.status", "capability_center.device_control", "capability_center.automation", "capability_center.security_scope", "capability_center.security_scan", "capability_center.hardening"],
        "home devices": ["capability_center.device_control"],
        "smart devices": ["capability_center.device_control"],
        "smart bulbs": ["capability_center.device_control"],
        "smart plugs": ["capability_center.device_control"],
        "automation recipes": ["capability_center.automation"],
        "security lab": ["capability_center.security_scope", "capability_center.security_scan", "capability_center.hardening"],
        "security scopes": ["capability_center.security_scope"],
        "security scans": ["capability_center.security_scan"],
        "hardening": ["capability_center.hardening"],
        "skill library": ["power_center.skills"],
        "plugin system": ["power_center.skills"],
        "workspace brain": ["power_center.workspace"],
        "app operators": ["power_center.app_operator"],
        "autonomous coding": ["power_center.autonomous_coding"],
        "git": ["power_center.git_read", "power_center.git_write", "power_center.git_push"],
        "git status": ["power_center.git_read"],
        "git commit": ["power_center.git_write"],
        "git push": ["power_center.git_push"],
        "github": ["power_center.git_read", "power_center.github"],
        "github pr": ["power_center.github"],
        "3d model": ["power_center.model_3d"],
        "model generation": ["power_center.model_3d"],
        "personal life os": ["power_center.personal_os"],
        "home assistant": ["power_center.home_assistant"],
        "backup": ["power_center.backup"],
        "recovery": ["power_center.backup"],
        "guardian": ["power_center.guardian"],
        "proactive guardian": ["power_center.guardian"],
        "notifications": ["power_center.notifications"],
        "notification center": ["power_center.notifications"],
        "knowledge vault": ["power_center.knowledge_vault"],
        "personal knowledge": ["power_center.knowledge_vault"],
        "voice repair": ["power_center.voice_repair"],
        "voice command repair": ["power_center.voice_repair"],
        "project autopilot": ["power_center.project_autopilot"],
        "pc timeline": ["power_center.pc_timeline"],
        "awareness timeline": ["power_center.pc_timeline"],
        "goal manager": ["power_center.goal_manager"],
        "local files": ["power_center.local_files"],
        "file intelligence": ["power_center.local_files"],
        "study companion": ["power_center.study"],
        "meeting companion": ["power_center.study"],
        "automation builder": ["power_center.automation_builder"],
        "nervous system": ["power_center.event_nervous_system"],
        "event system": ["power_center.event_nervous_system"],
        "daily companion": ["power_center.daily_companion"],
        "skill marketplace": ["power_center.skill_marketplace"],
        "finance": ["power_center.personal_finance"],
        "personal finance": ["power_center.personal_finance"],
        "private memory": ["power_center.private_memory"],
        "android companion": ["power_center.android_companion"],
        "project watchdog": ["power_center.project_watchdog"],
        "codebase standards": ["power_center.codebase_standards"],
        "programmer laws": ["power_center.codebase_standards"],
        "coding standards": ["power_center.codebase_standards"],
        "sandbox": ["power_center.sandbox_simulation"],
        "simulation": ["power_center.sandbox_simulation"],
        "privacy vault": ["power_center.privacy_vault"],
        "model router": ["power_center.model_router"],
        "self debugger": ["power_center.self_debugger"],
        "tone awareness": ["power_center.emotion_tone"],
        "emotion awareness": ["power_center.emotion_tone"],
        "personal crm": ["power_center.personal_crm"],
        "learning coach": ["power_center.learning_coach"],
        "research briefings": ["power_center.research_briefings"],
        "contextual workspace": ["power_center.contextual_workspace"],
        "workspace autopilot": ["power_center.contextual_workspace"],
        "offline survival": ["power_center.offline_survival"],
        "data timeline": ["power_center.personal_data_timeline"],
        "personal timeline": ["power_center.personal_data_timeline"],
        "skill training": ["power_center.skill_training_studio"],
        "training studio": ["power_center.skill_training_studio"],
        "executive": ["power_center.executive"],
        "executive summary": ["power_center.executive"],
        "memory review": ["power_center.memory_review"],
        "real memory review": ["power_center.memory_review"],
        "task autopilot": ["power_center.task_autopilot"],
        "autopilot checkpoints": ["power_center.task_autopilot"],
        "voice personality": ["power_center.personality_profile"],
        "personality profile": ["power_center.personality_profile"],
        "life dashboard": ["power_center.life_dashboard"],
        "skill recorder": ["power_center.skill_recorder"],
        "friday skill recorder": ["power_center.skill_recorder"],
        "documentation brain": ["power_center.documentation_brain"],
        "autonomous documentation": ["power_center.documentation_brain"],
        "personal search": ["power_center.personal_search"],
        "personal search engine": ["power_center.personal_search"],
        "trust meter": ["power_center.trust_meter"],
        "learning twin": ["power_center.learning_twin"],
        "relationship assistant": ["power_center.relationship_assistant"],
        "deployment commander": ["power_center.deployment_commander"],
        "privacy firewall": ["power_center.privacy_firewall"],
        "agent scheduler": ["power_center.agent_scheduler", "power_center.agent_scheduler_apply"],
        "test monitor": ["power_center.test_build_monitor"],
        "build monitor": ["power_center.test_build_monitor"],
        "reliability score": ["power_center.reliability_score"],
        "model benchmark": ["power_center.model_benchmark"],
        "deployment brain": ["power_center.deployment_brain"],
        "os autopilot": ["power_center.os_autopilot"],
        "version guardian": ["power_center.version_guardian"],
        "awareness graph": ["power_center.awareness_graph"],
        "what is happening": ["power_center.awareness_graph"],
        "fix loop": ["power_center.fix_loop"],
        "autonomous fix loop": ["power_center.fix_loop"],
        "browser pro": ["power_center.browser_pro"],
        "browser extension pro": ["power_center.browser_pro"],
        "android pro": ["power_center.android_pro"],
        "android companion pro": ["power_center.android_pro"],
        "memory review pro": ["power_center.memory_review_pro"],
        "app mastery": ["power_center.app_mastery"],
        "operator mastery": ["power_center.app_mastery"],
        "local ai search": ["power_center.local_ai_search"],
        "life os": ["power_center.life_os"],
        "security guardian pro": ["power_center.security_guardian_pro"],
        "cloud worker": ["power_center.cloud_worker"],
        "cloud worker mode": ["power_center.cloud_worker"],
        "self update": ["self_update.propose", "self_update.stage_change", "self_update.approve", "self_update.apply", "self_update.cancel"],
        "self updates": ["self_update.propose", "self_update.stage_change", "self_update.approve", "self_update.apply", "self_update.cancel"],
        "codebase updates": ["self_update.stage_change", "self_update.apply"],
    }
    keys = aliases.get(lowered, [lowered] if "." in lowered else [])
    return [set_rule(key, mode) for key in keys]


def _seed_defaults(conn: sqlite3.Connection) -> None:
    now = _now()
    for rule in DEFAULT_RULES:
        conn.execute(
            """
            INSERT OR IGNORE INTO permission_rules(key, label, category, mode, description, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (rule["key"], rule["label"], rule["category"], rule["mode"], rule["description"], now),
        )


def _rule_from_row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "key": str(row["key"]),
        "label": str(row["label"]),
        "category": str(row["category"]),
        "mode": _normalize_mode(str(row["mode"])),
        "description": str(row["description"]),
        "updated_at": str(row["updated_at"]),
    }


def _canonical_key(key: str) -> str:
    return ".".join(part for part in str(key or "").strip().lower().replace(" ", "_").split(".") if part) or "unknown.action"


def _normalize_mode(mode: str) -> str:
    value = str(mode or "ask").strip().lower()
    return value if value in VALID_MODES else "ask"


def _target_from_input(tool_input: dict[str, Any]) -> str:
    for key in ("target", "path", "url", "to", "name", "title", "query"):
        value = tool_input.get(key)
        if value:
            return " ".join(str(value).split())[:300]
    return ""


def _json_loads(value: str) -> Any:
    try:
        return json.loads(value or "{}")
    except Exception:
        return {}


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds")
