# Friday v2 Status Tracker

Source of truth: `C:\Users\HomePC\Desktop\second-brain\JARVIS_v2_Phase_Planning_v3.pdf`

Chosen UI stack:

- Desktop app: Electron
- Web app/dashboard: Next.js
- Electron desktop shell now includes tray behavior, single-instance handling, hide-to-tray, startup-hidden support, Windows login autostart toggling, and electron-builder NSIS packaging metadata.

Free-first intelligence routing:

- Default online reasoning: NVIDIA Build/NIM API when `NVIDIA_API_KEY` is configured
- Office/design/content agents: Gemini first when `GEMINI_API_KEY` is configured
- Offline fallback: Ollama local model for all agents
- API-backed agent mode: when an online provider key is configured, background agents can scale to 10 workers while each hosted provider is protected by concurrency, spacing, and rate-limit backoff guards
- Offline/local mode: Ollama remains the fallback and is limited to one local inference worker so Junior Developer/QA work does not overwhelm the laptop CPU

Virtual office layer:

- Each agent has an API-backed office snapshot with room name, status, current focus, progress, provider chain, task counts, and recent messages.
- The Next.js/Electron dashboard includes an Office Floor so the user and Friday/CEO can inspect what every agent is doing.
- Existing tasks can be reassigned between virtual offices; stale active tasks can be returned to pending so the right specialist can pick them up.
- Agents receive an agent directory in their task context, can ask other specialists questions, and those questions become routed child tasks with parent/child traceability.
- The research analyst hands off fresh research notes into the target agent's task messages, procedural memory, and long-term learning so the receiving agent can reuse what was found.
- `core/search_broker.py` gives Friday a dedicated search backend with Brave, Google Programmable Search, Tavily, and SerpAPI adapters, short-lived cache, dedupe, reranking, and normalized citation objects. The older chat/search and autonomous research paths now route through this broker.
- `core/agent_thought_bus.py` adds a silent internal channel where agents pass context, research handoffs, questions, risks, decisions, delegations, and result summaries without speaking everything aloud.
- Dashboard task/offices progress is streamed over `/ws/tasks` so task cards and progress bars update live instead of waiting only on polling.

Human-like desktop sessions:

- Desktop task sessions persist to SQLite with step-by-step screenshots, actions, results, risk notes, and pause/resume/confirm/cancel controls.
- Web tasks can use Chrome DevTools DOM context, and native apps can use Windows UI Automation context when available.
- CAPTCHA/login screens pause for human handoff instead of pretending Friday can bypass verification or type private credentials.
- The dashboard includes a Desktop Sessions panel so the user and Friday/CEO can inspect app-control progress and screenshots while a task is running.

Continuous vision layer:

- `core/visual_monitor.py` can continuously watch the screen, camera, or both with low-CPU change detection and persisted frame/event history.
- Realtime mode exposes MJPEG live streams through `/vision/live/{source}` and the dashboard Live Vision panel can show a live screen/camera feed while monitoring is active.
- Recent visual-change events feed into the desktop planner context so multi-step UI workflows can use what changed over time, not only the current screenshot.
- Camera monitoring is optional and uses `opencv-python` if installed; missing camera support produces an explicit monitor error instead of pretending a camera frame was seen.
- The dashboard includes a Live Vision panel for start/stop/capture controls and recent frame thumbnails.

PC awareness layer:

- `core/pc_awareness.py` inventories the active window, running processes, installed app entries, Start Menu shortcuts, and Desktop/Home-screen shortcuts with bounded SQLite-backed snapshot history.
- `tools/pc_control.py` can list running/installed/Desktop apps and resolve arbitrary app names through the PC inventory before falling back to static aliases.
- Desktop task planning now receives PC awareness context so Friday can reason about which apps are open, installed, or launchable before operating complex tools like Figma.
- The dashboard includes a PC Awareness panel for inventory refresh and compact running/Desktop/installed app lists.

Android phone bridge:

- `core/phone_bridge.py` gives Friday a free-first Android bridge using ntfy for wireless phone alerts/ringing and ADB for local battery/status, URL handoff, attention signals, guarded dialer launch, SMS drafts, phone file transfer, clipboard sync, and photo import.
- `tools/phone_bridge.py`, direct voice/chat commands, and protected `/phone/*` API endpoints expose status, registered devices, battery, notification, ring/find-phone, open-link, dial, SMS draft, file push/pull, clipboard, photo import, and event history actions.
- The dashboard includes an Android Phone panel for registering a phone, ringing it, testing notifications, opening links, opening the Android dialer, creating SMS drafts, syncing clipboard text, pushing/pulling files, importing photos, and reviewing recent phone events.
- Friday does not pretend it can place carrier calls for free; without a paid telephony provider, "call me" means urgent phone alert, and Android calling uses the connected phone/dialer when ADB is available.

Creative/image generation layer:

- `core/image_generation.py` adds honest text-to-image generation through a configured local Stable Diffusion/AUTOMATIC1111 server first, with optional Hugging Face image API fallback when `HF_TOKEN`/`HUGGINGFACE_API_TOKEN` is configured.
- Direct voice/chat commands like "generate an image of a cat" route to `tools/image_generation.py` instead of app-control/paint. If no image backend is available, Friday records the request and explains the missing setup instead of pretending it generated an image.
- Protected API endpoints expose `/images/status`, `/images/generate`, `/images`, and `/images/{filename}` for dashboard or future UI use.

Capability center and ethical security lab:

- `core/capability_center.py` centralizes home/device status, configured local smart-device control, local network awareness, daily briefs, next-action planning, workspace project maps, dependency health, auto docs, test watching, computer maintenance, automation recipes, and defensive security checks.
- The security lab supports local/private open-port checks, deployed-site security header checks, project secret-pattern scans, suspicious process review, startup persistence checks, browser extension audit, dependency scans, security reports, and hardening plans.
- External/public targets are scope-locked: Friday creates a security scope and requires local/private status or ownership proof before running even low-impact scans. It does not run exploit payloads, credential attacks, stealth, evasion, or unauthorized testing.
- The dashboard includes a Capability Center panel for briefs, home status, configured smart-device control, workspace docs, maintenance, security scopes, scoped port checks, secret scans, security reports, and automation recipes.

Power center layer:

- `core/skill_library.py` now supports built-in reusable skills/plugins with install, enable, disable, and retrieval flows for Figma operator, VS Code debugger, research writer, security auditor, YouTube summarizer, and React app builder.
- `core/workspace_brain.py` adds deeper project intelligence: repo mapping, architecture hints, file roles, TODO/bug tracking, test discovery, dependency context, workspace Q&A, and generated `docs/friday_workspace_brain.md`.
- `core/app_operators.py` registers specialist operators for VS Code, Chrome, Figma, Gmail, WhatsApp Web, Discord, and File Explorer; app operator sessions create guarded desktop task sessions with app-specific instructions.
- `core/personal_life_os.py` adds daily planning, missed follow-ups, routines, mood/energy-aware advice, next-action mode, and end-of-day summaries.
- `core/home_assistant.py` adds optional free/local Home Assistant REST integration for bulbs, plugs, sensors, TVs, focus mode, and automations when a local Home Assistant URL/token are configured.
- `core/backup_recovery.py` adds config snapshots, file backups, restore guardrails, protected `.env` handling, and risky-delete warnings.
- `core/git_integration.py` adds guarded Git/GitHub CLI actions for status, diffs, logs, clone, checkout, pull, add, commit, push, PRs, and issues. Coding-project destinations resolve under Desktop by default.
- `core/model_3d.py` generates procedural mesh assets and exports real `.obj`, `.stl`, `.gltf`, and `.glb` files under `data/3d_models`. It now supports composed multi-part scenes such as city blocks, houses with roofs/windows/garage details, and low-poly human characters, with material-aware OBJ/glTF/GLB output.
- `core/model_3d_studio.py` adds a Blender-backed studio pipeline for photorealistic/PBR targets: it generates a `.blend` scene script, uses Cycles/soft lighting/materials when Blender is configured, exports `.blend`/`.glb`/`.obj`/preview renders, and falls back honestly to procedural assets plus setup hints when Blender is not installed.
- `core/text_to_3d.py` adds real text-to-3D provider backends for Meshy, Tripo, and a configurable local generator command. Studio-quality model requests can now submit provider jobs, poll progress, download generated meshes/textures/previews, then pass the result into Blender for cleanup/export.
- `core/search_broker.py`, `/search/status`, and `/search/query` expose the dedicated search API layer for dashboard use, agent research, and direct web-search commands without relying on one brittle scraper.
- `tools/power_center.py`, protected API endpoints, direct commands, and the dashboard Power Center panel expose these features.

Hardening sprint:

- `core/lazy_imports.py` now keeps the API server, orchestrator, and self-model from eagerly importing the whole system on startup. Local import timing improved from roughly 29s to under 5s for `api.server`, and from roughly 24s to under 1s for `core.orchestrator`.
- `core/command_runner.py` centralizes managed command execution with argument-array parsing, `shell=False`, executable allowlisting, and shell metacharacter rejection. The previous `shell=True` test/build/debugger callsites now use this runner.
- `.env.example`, `.gitignore`, `.dockerignore`, `.pre-commit-config.yaml`, `scripts/validate_repo.py`, pytest markers, performance smoke tests, and `.github/workflows/ci.yml` add safer secrets hygiene, CI smoke coverage, and import-time performance budgets.
- `docs/production_readiness.md` captures the remaining provider, deployment, HTTPS, database sync, and GitHub readiness checks that require real credentials or external infrastructure.
- `api/routers/` now contains extracted domain routers for `core`, `media`, `ops`, and `realtime`, beginning the split away from the large `api/server.py` route registry.
- `/providers/readiness`, `/production/readiness`, `/github/status`, `/models/3d/status`, and `/text-to-3d/status` expose live setup checks for cloud, GitHub, search, image, and 3D provider readiness.
- `scripts/run_tests.py` adds smoke/fast/integration/slow/full pytest profiles, and `scripts/verify_production.py` verifies HTTPS API deployment plus `/ws/tasks`.

Command center expansion:

- `core/agent_scheduler.py` decides when agents should run now, later, or overnight, pauses heavy workers during live voice mode, retries failed work, schedules low-priority research, and respects model-provider quota/backoff signals.
- `core/test_build_monitor.py` gives Friday an autonomous build/test watcher that can run focused commands, analyze crashes or failing output, and create proof reports without pretending a fix was applied.
- `core/reliability_score.py` scores STT accuracy, tool success, false-success risk, latency, and task health so Friday can track where it is getting better or worse.
- `core/model_benchmark_lab.py` benchmarks local and API-backed models by task type, records routing results, and keeps live benchmarking opt-in so free API quota is not wasted.
- `core/deployment_brain.py` passively checks deployed projects for uptime, DNS/SSL hints, security headers, release readiness, rollback notes, and deployment proof evidence.
- `core/os_autopilot.py` combines work rhythm, active tasks, goals, and PC timeline hints into a personal operating-system recommendation such as coding/admin/focus mode and what to do next.
- `core/version_guardian.py` adds preflight risk checks, `.env`/secret protection, config snapshots, rollback notes, and mission-aware backup metadata before risky edits.
- The dashboard Mission Control area now streams command-center state over `/ws/tasks` and exposes scheduler, build monitor, reliability, model benchmark, deployment, OS autopilot, and version-guardian actions.

Advanced power layer:

- `core/awareness_graph.py` persists a realtime situation graph from active app/project, PC health, Android companion status, browser page/console/network context, missions, approvals, tone, task queue, and recent errors so Friday can answer "what is happening right now" with evidence.
- `core/autonomous_fix_loop.py` implements an approval-gated detect/diagnose/patch-plan/verify/proof loop. It creates fix-prep tasks and self-update proposals after approval, but does not silently apply risky edits or claim fixes before tool proof.
- `core/browser_extension_pro.py` upgrades the Chrome/Edge bridge with network error events, page-change events, guidance for "what should I click?", safe form-fill queueing, and page-watch actions. The extension now reports `window.error`, unhandled promise rejections, `webRequest` failures, and redacted DOM changes.
- `apps/android-companion` now sends real small file/photo/camera bytes when allowed, not only metadata; `core/android_companion.py` stores uploaded Android files under `data/android_companion_files` with secret/token redaction and size limits.
- `core/personal_memory_review.py` coordinates periodic review of remembered preferences, goals, people, shortcuts, and corrections using the existing executive memory review queue.
- `core/app_operator_mastery.py` combines specialist app operators, app-state memory, browser/PC copilot context, and recovery rules for Figma, VS Code, Chrome, Gmail, WhatsApp, Discord, and File Explorer workflows.
- `core/local_ai_search.py` federates private local search across semantic chunks, file intelligence, personal vault memories, timeline events, and browser context while keeping sensitive chunks behind explicit permission.
- `core/life_os_mode.py` groups daily briefs, next-action planning, study progress, operating rhythm, and end-of-day summaries into one personal operating-system mode.
- `core/security_guardian_pro.py` remains defensive-only and combines suspicious process checks, open ports, dependency/security scans, browser extension risk, secret scans, startup persistence, and project watchdog findings.
- `core/cloud_worker_mode.py` queues safe heavy jobs such as research, long tests, deployment checks, document indexing, and scheduled missions to a configured worker, or falls back to background local tasks without spending money or sending secrets by default.

Autonomy brain expansion:

- `core/autonomy_control.py` centralizes autonomy policy. `autonomy_mode=full` pre-approves trusted Desktop/project coding, Git, release, deployment, and self-update workflows while keeping hard-stop actions approval-gated.
- `core/autonomy_engine.py` adds a realtime choose-act-verify loop: detect the current goal, choose a tool/agent, run one safe step, verify evidence, retry if incomplete, and escalate to the approval inbox when blocked.
- The autonomy engine now has an always-on supervisor that can start background workers, refresh task autopilot and missions, continue active autonomy runs, and start low-risk autonomy passes when trusted work is queued.
- `core/certainty_brain.py` tracks what Friday knows, guesses, lacks evidence for, and should reconfirm later, so answers can expose confidence and missing proof instead of pretending.
- `core/vision_skill_learning.py` stores learned UI patterns such as app toolbars, deploy buttons, expired-login modals, crash screens, DOM anchors, accessibility labels, and recovery hints.
- `core/personal_automation_daemon.py` evaluates background automations from environment, battery, project, test, and phone signals while keeping action execution permission-gated.
- `core/notification_intelligence.py` ranks notifications as urgent, action-needed, current-project related, can-wait, or noise.
- `core/self_testing_personality.py` lets Friday audit itself for unsupported claims, slowness, interruption behavior, weak tool choice, and shallow self-reflection.
- `core/project_memory.py` gives each repository its own memory for architecture, commands, env var names only, deployment steps, common bugs, preferred style, and past fixes.
- `core/operator_skills.py` exposes specialist operator drivers for Figma, VS Code, Chrome, Render, Vercel, Gmail, Calendar, and File Explorer.
- `core/learning_roadmap.py` creates personal learning roadmaps, weak-area plans, weekly study focus, and quiz handoff into the learning coach.
- `core/privacy_firewall_pro.py` detects requests involving `.env`, private files, private memories, messages, phone data, credentials, and protected paths, then creates explicit approval items with purpose/evidence.
- `core/device_command_mesh.py` coordinates laptop, Android companion, and browser-extension command handoffs such as continue-on-laptop, page-to-Friday, phone-camera, clipboard, and file handoff.
- `core/autonomous_release_engine.py` prepares build/test/dependency/security-header/deployment-checklist/rollback/proof reports without running deploys until explicitly approved.
- The protected API and `/ws/tasks` stream now expose these modules for dashboard panels, voice commands, and future Electron surfaces.

Human preference, coaching, and trust layer:

- `core/decision_memory.py` stores how the user makes tradeoffs: free-first tools, speed vs quality, ask-first boundaries, coding/design taste, and good-enough thresholds.
- `core/skill_improvement.py` records repeated tool/operator failures and creates safe self-improvement proposals for the right agent.
- `core/live_workspace_coach.py` observes current files, terminal logs, browser console context, project watchdog output, and test/build status, then stays quiet unless the suggestion is useful.
- `core/memory_debate.py` lets Friday explain beliefs with evidence, confidence, and stale-memory review prompts.
- `core/focus_protection.py` batches non-urgent alerts and coordinates with context-aware silence modes.
- `core/app_apprenticeship.py` records demonstrated Figma/VS Code/Render/Gmail-style workflows into reusable operator skills and UI-pattern memory.
- `core/project_cto.py` keeps each project’s roadmap, risk, technical debt, release status, security posture, and next best engineering task.
- `core/conversation_continuity.py` remembers unfinished threads across days.
- `core/local_voice_brain.py` installs free/offline wake aliases, transcript repairs, command shortcuts, and voice reliability links.
- `core/trust_dashboard.py` aggregates what Friday verified, guessed, failed, needs approval for, and is doing now.

Agent governance and reliability layer:

- `core/agent_quality_manager.py` scores each agent by usefulness, speed, evidence, mistakes, and whether another agent had to repair its work.
- `core/agent_lifecycle.py` lets Friday hire, retire, promote, and rewrite dynamic specialist agents; dynamic agents are included in the live roster and task/question routing.
- `core/agent_council.py` supports private multi-agent council decisions with confidence and disagreement notes.
- `core/do_not_forget.py`, `core/memory_constitution.py`, and `core/personal_taste_engine.py` route important lessons into the right memory tier while respecting what Friday may remember.
- `core/reality_check.py` and `core/failure_autopsy.py` strengthen the honesty gate by recording unsupported claims and root-cause reports after serious failures.
- `core/dev_server_copilot.py`, `core/code_change_simulator.py`, `core/refactor_planner.py`, and `core/agent_simulation_sandbox.py` add pre-action simulation, dev-server diagnosis, and refactor planning before risky work.
- `core/command_graph.py`, `core/emotional_timing.py`, and `core/visual_skill_memory_v2.py` improve command understanding, behavior timing, and app-screen memory.
- The dashboard includes an Agent Governance panel for quality, lifecycle, council, simulations, memory policy, taste, reality checks, and autopsies.

Dashboard conversation:

- Protected `POST /chat` sends dashboard messages through the same Friday orchestrator used by voice/text mode.
- Dashboard includes a Friday Chat panel for direct conversation and commands.
- The dashboard includes a free browser-native streaming STT panel using Chrome/Edge Web Speech APIs for live interim transcripts and optional auto-send to Friday. It stores final browser transcripts in the Voice Reliability Lab.

Proactive speech layer:

- `core/proactive_speech.py` lets Friday speak first during voice sessions for due reminders, upcoming calendar events, blocked tasks needing approval, failed high-priority tasks, and completed high-priority tasks.
- Proactive speech has quiet hours, a maximum announcements-per-hour limit, startup delay, source filters, and a SQLite spoken-event log so the same reminder, task update, or notification is not repeated forever.
- Proactive speech is enabled for normal and `--fast-voice` voice sessions, but it is intentionally disabled for terminal/API-only runs.

Guardian OS layer:

- `core/proactive_guardian.py` quietly scans important signals such as battery, disk space, security signals, failed/stuck tasks, overdue reminders, phone battery, slow responses, and voice reliability, then only raises meaningful alerts.
- `core/notification_center.py` is the unified notification inbox for guardian alerts, agent questions, security findings, reminders, approvals, failed tasks, phone events, and daily briefings.
- `core/personal_knowledge_vault.py` stores private goals, projects, habits, people, preferences, repeated corrections, weekly priorities, and what matters now.
- `core/voice_command_repair.py` lets the user correct bad transcripts with phrases like "No, I said reduce volume to 40", then stores the repair in the Voice Reliability Lab and vault.
- `core/project_autopilot.py` inspects codebases for TODOs, stale docs, missing tests, dependency health, optional test failures, and safe fix preparation.
- `core/pc_timeline.py` records active-window changes, new app entries, Friday actions/failures, and PC snapshots as an awareness timeline.
- `core/goal_manager.py` turns big goals into step goals, weekly plans, reminders, and next-action suggestions.
- `core/local_file_intelligence.py` indexes Desktop, Documents, Downloads, projects, PDFs, and image metadata for local file search and folder summaries.
- `core/meeting_study_companion.py` stores meeting/class transcripts, summaries, action items, flashcards, and follow-up reminders.
- `core/automation_builder.py` creates natural-language automations such as battery-low brightness changes or VS Code startup recipes.
- The dashboard includes a Guardian OS panel for guardian scans, notifications, vault saves, voice repairs, project autopilot, PC timeline, goals, file intelligence, study sessions, and automation builder actions.

Awake Friday layer:

- `core/event_nervous_system.py` watches local events such as active-app changes, new downloads, due reminders, phone connection changes, low battery, and stuck agents, then emits notifications only when the event matters.
- `core/barge_in.py` provides a speech interrupt signal for dashboard/API stop commands and correction phrases such as "Friday stop" and "No, that's wrong." During spoken replies, an audio monitor listens in parallel, stops TTS as soon as human speech is detected, transcribes the interruption, and queues replacement instructions like "reduce volume to 40" for the main voice loop.
- `core/daily_companion.py` creates morning briefs and check-ins with tasks, goals, reminders, project state, and PC health.
- `core/skill_marketplace.py` makes the local skill/plugin library user-facing with installable skills such as Figma designer, Gmail operator, PDF analyst, and video summarizer.
- `core/personal_finance.py`, `core/private_embedding_memory.py`, `core/privacy_vault.py`, `core/model_router_brain.py`, `core/sandbox_simulation.py`, `core/project_watchdog.py`, `core/android_companion.py`, and `core/self_debugger.py` add finance organization, private local search memory, sensitive vaulting, model routing, dry-run simulation, continuous project health, Android companion hooks, and automatic failure reports.
- The dashboard includes an Awake Friday panel for these controls, and `/ws/tasks` streams their summary state in near real time.

Companion growth layer:

- `core/emotion_tone.py` detects frustration, confusion, tiredness, rushing, worry, excitement, calm, and neutral tone from text with weighted evidence, confidence, intensity, secondary tones, and non-diagnostic reply-style guidance. It avoids common false positives such as "what is going on right now" and does not prefix short factual tool results.
- `core/personal_crm.py` stores people, relationships, birthdays, promises, conversation notes, and pending follow-ups, including overdue follow-ups instead of hiding them.
- `core/learning_coach.py` adds study topics, validated spaced-repetition cards, quizzes, answer tracking, simple answer grading, and progress summaries.
- `core/research_briefings.py` stores watched research topics, creates background research tasks, and keeps recent briefing summaries for reuse.
- `core/contextual_workspace.py` prepares active-project context by combining workspace maps, project health, TODOs, and dev hints, with graceful fallback when one scanner fails.
- `core/offline_survival.py` exposes a local-first survival mode when internet/API providers fail and checks multiple configurable connectivity endpoints before deciding online/offline status.
- `core/personal_data_timeline.py` answers timeline questions by combining notes, PC awareness events, and Friday event history.
- `core/skill_training_studio.py` lets the user teach a workflow once and publish it into the reusable skill library.
- The orchestrator, `tools/power_center.py`, protected API endpoints, self-model, `/ws/tasks`, and the dashboard Companion Growth panel expose these abilities.

Executive autonomy layer:

- `core/executive_capabilities.py` coordinates real memory review, checkpointed task autopilot, voice personality profiles, the local life dashboard, Friday Skill Recorder, autonomous documentation updates, personal search, trust meter, learning twin, relationship assistant, deployment commander, and privacy firewall.
- Task Autopilot creates persistent checkpoint tasks with success criteria, quality priorities, task contracts, agent assignments, and "ask only when blocked/risky" instructions so Friday can keep working on large goals over longer spans without pretending completion.
- Programming autopilot checkpoints explicitly prioritize security, correctness, speed/performance, maintainability, reliability, readability, scalability, testability, documentation, and rollback safety.
- Memory Review periodically turns saved preferences, people, corrections, and project facts into review prompts such as "is this still true?" and records keep/update/forget decisions.
- The Trust Meter and Privacy Firewall expose confidence, risk, evidence, fallback plan, private-data triggers, and approval requirements before Friday touches sensitive data, deployments, code edits, security scans, or money-adjacent workflows.
- The dashboard includes an Executive Autonomy panel, and `/ws/tasks` streams its latest summary so memory-review counts, autopilot runs, recorded skills, personality profile, learning, and relationship prompts update live.

Mission autonomy layer:

- `core/mission_control.py` adds SQLite-backed mission runs, deterministic phases, events, evidence, blockers, approvals, desktop locks, pause/resume/stop controls, deploy approval gates when configured, and final-proof enforcement.
- In full autonomy mode, trusted project missions skip design-preview and deploy approval gates by default, but still retain pause/resume/stop controls and final QA proof requirements.
- Long missions use fixed phases: intake, research, architecture, design, implementation, autonomous QA, documentation, release prep, deployment approval, deployment/runbook, and final proof.
- Non-interrupting work mode separates conversation, background missions, PC control, agent questions, and urgent alerts. Voice/chat status checks do not cancel missions; explicit pause/stop commands do.
- `core/autonomous_qa_lab.py` records QA evidence for test discovery, optional test execution, docs, project health, dependency/security hints, performance smoke checks, accessibility checklist, and secret scans before a mission can claim completion.
- `core/app_state_memory.py` stores app-specific muscle memory for selectors, menus, anchors, successful actions, failed interactions, recovery hints, and confidence across Chrome, VS Code, Figma, Gmail, Discord, WhatsApp, and File Explorer style workflows.
- `apps/browser-extension` contains a Chrome/Edge Manifest V3 local bridge that sends redacted page context and console errors to Friday's local API without sending passwords, hidden values, token-like strings, or private form values.
- `core/release_manager.py` prepares changelogs, version plans, build/test/deploy checklists, rollback notes, known risks, and deployment approval gates.
- `core/error_radar.py` watches local logs, browser-extension console events, failed tasks, project watchdog output, and stuck mission signals, then creates self-debug reports and fix-prep events rather than making silent risky edits.
- `core/semantic_search.py` indexes safe files, code, notes, task history, browser page context, and memory text with a private-data boundary; `.env` values are never indexed, only variable names.
- `core/operating_rhythm.py` tracks energy notes, productive-hour signals, missed-task hints, and coding/admin day recommendations.
- The dashboard includes a Mission Control panel inside the Executive/Power area for starting missions, approving deploys, viewing QA/radar/release/search state, running semantic search, and seeing live `/ws/tasks` mission status.

Companion intelligence layer:

- `apps/android-companion` adds a native Android companion app scaffold with microphone command capture, notification sync, clipboard sync, battery/status reporting, optional location, file/photo/camera event hooks, and local Friday API registration.
- `core/android_companion.py` now supports app-registered Android devices in addition to ADB/ntfy, with protected API endpoints for app status, notifications, clipboard, location, file/photo events, and camera-frame metadata.
- `apps/browser-extension` v2 can send redacted URL/title/headings/buttons/forms/links/landmarks/performance/console context to Friday and can poll a safe local action queue for DOM actions such as click, focus, fill, select, scroll, and summarize.
- `core/browser_extension_bridge.py` stores browser page insights, console errors, and queued browser actions while refusing password/hidden/secret-like form values.
- `core/autonomous_debugger.py` analyzes terminal logs, stack traces, failed commands, browser console errors, and watched files into probable cause, fix plan, test plan, and evidence-backed reports.
- `core/personal_command_memory.py` learns the user's command style, such as "reduce volume" meaning a specific canonical command, and the orchestrator resolves learned shortcuts before falling back to generic reasoning.
- `core/calendar_email_assistant.py` adds safe OAuth-backed briefings, follow-up detection, and draft-only reply preparation; it still requires explicit approval before anything is sent.
- `core/autonomous_learning.py` chooses learning topics from the user's goals, creates background learning tasks, and updates agent notebooks/long-term lessons.
- `core/knowledge_graph.py` can now query and connect local entities across people, files, projects, goals, memories, tasks, apps, and events for personal questions like "what was I trying to fix last week?"
- `core/environment_awareness.py` captures active app/window, battery, network hint, open project, and contextual recommendation so Friday can react to the environment without pretending certainty.
- `core/trust_proof.py` produces proof reports for big tasks with what changed, what was tested, what failed, evidence, remaining risks, and confidence.
- The dashboard includes a Companion Intelligence panel for Android app devices, browser insights/actions, autonomous debugger status, learned command shortcuts, calendar/email briefings, autonomous learning, environment snapshots, knowledge-graph summary, and proof reports.

Continuity and fused-context layer:

- `core/continuity_brain.py` stores unfinished threads across days, including stopped tasks, blocked missions, open debugger reports, and proof reports with remaining risk.
- `core/context_fusion.py` merges PC/window context, browser-extension page context, Android app status, task counts, mission status, notifications, tone, project watchdog, calendar/email status, and continuity into one ranked live situation summary.
- `core/deep_project_autopilot.py` coordinates project inspection, autonomous debugger evidence, browser console context, optional safe fix-prep tasks, and a final trust/proof report without silently applying risky edits.
- `core/context_aware_silence.py` adds modes such as normal, coding, debugging, study, silent operator, gaming, and movie so Friday knows when to stay quiet and when interruption is justified.
- `core/browser_pc_copilot.py` combines local browser extension DOM/console context with PC awareness to summarize tabs, detect buttons/forms, debug current-page errors, and refuse password/token/secret form actions.
- `core/skill_evolution.py` notices repeated workflows and learned command patterns, then suggests saving them as reusable skills.
- `core/personal_safety_guardian.py` protects `.env`, checks for secret-like values in safe project files, and preflights destructive actions with approval/backup guidance.
- `core/phone_mesh.py` adds Android-to-PC and PC-to-Android handoff queues; the Android companion app now has a "Handoff To PC" command button.
- `core/personal_command_memory.py` now includes default personal command language such as "start work", "check Friday", "check project", "ship it", and "reduce volume".
- Protected API endpoints and `/ws/tasks` expose continuity, context fusion, deep project autopilot, silence mode, browser/PC copilot, skill evolution, safety guardian, and phone mesh state.

Deep app integrations:

- `core/app_integrations.py` provides free/local contacts, reminders, calendar events, document/sheet creation, and workspace indexing/search in SQLite.
- Calendar, Docs, Sheets, WhatsApp, Discord, and Gmail are available through official web-app deep links, then controlled through browser/desktop automation when a task requires UI interaction.
- `core/google_workspace.py` adds real Google OAuth for Gmail read access, Calendar event listing/creation, Docs creation, and Sheets creation when `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` are configured and the user completes consent.
- The dashboard includes an Integrations panel for app launch, local reminders/events/contacts, and workspace indexing status.
- Account-bound APIs are intentionally not faked; without Google OAuth consent, Friday opens and operates the web UI rather than claiming private Google cloud-data access. WhatsApp/Discord still use web UI control unless official connectors are added later.

Safety control center:

- `core/permissions.py` stores allow/ask/block policies in SQLite for sensitive tools and device/app actions.
- The orchestrator and lower-level PC/app/email tools enforce permission decisions before running actions.
- The dashboard includes a Safety Center for changing permissions and inspecting recent permission decisions.
- Defaults allow low-risk device controls like volume and phone ringing while keeping send-email/messages, Android dialing, SMS drafts, phone file transfer, automation recipes, security scopes/scans, future file deletion, and shell commands ask-first.

Self-update layer:

- `core/self_update.py` lets Friday propose improvements to its own codebase, stage exact file replacements, apply them only after explicit approval, run tests, and roll back on failure.
- Self-update cannot touch `.env`, `.venv`, `data`, dependency folders, hidden runtime folders, or files outside this project.
- `tools/self_update.py` and direct voice/chat commands expose the flow: propose, list/get, approve, stage, apply, cancel, and explain Friday's current brain architecture.
- Staging and applying self-update changes are ask-first in the Safety Center.
- The dashboard now includes a dedicated Self Updates panel for proposal creation, approval, staging exact changes, applying, cancelling, and inspecting staged changes.

Brain-inspired cognition layer:

- `core/world_model.py` maintains local snapshots, entities, and expected outcomes so Friday can answer what is happening now and compare expectations against observations.
- `core/self_reflection.py` records findings from corrections, failures, slow responses, and permission blocks, with optional LLM-assisted reflection when `self_reflection_use_llm` is enabled.
- `core/long_term_learning.py` stores durable lessons with evidence counts, confidence, review scheduling, and guarded self-update proposal promotion for repeated high-confidence implementation lessons.
- `core/goal_regulation.py` tracks active goals and operational states such as calm, focused, uncertain, blocked, overloaded, recovering, and waiting for user.
- `core/adaptive_attention.py` learns from accepted/ignored speech and user corrections to adjust runtime attention hints and wake-name aliases.
- `core/cognitive_cycle.py` coordinates the loop in light mode during voice sessions, desktop task sessions feed expected/observed outcomes into the world model, and the dashboard exposes a Cognition panel with run/review controls through protected `/cognition/*` API endpoints.

Self-model and honesty layer:

- `docs/friday_identity.md` is Friday's stable identity and values file: name, role, tone, relationship to the user, safety boundaries, priorities, and what Friday must never pretend.
- `core/self_model.py` lets Friday inspect its modules, tools, providers, local models, STT/TTS, permissions, memory stores, worker state, access, limitations, uncertainty, and recent failures.
- `core/autobiographical_memory.py` stores a timeline of important events such as user corrections, tool failures, successful fixes, goals, safety changes, remembered preferences, and self-update events.
- `core/evidence_gate.py` prevents unsupported success claims for action requests, so Friday does not say "done" unless a tool result or other evidence supports it.
- Voice/chat commands now answer introspection questions like "what tools do you have?", "what are you unsure about?", "what can you access?", "what failed recently?", "why did you say that?", and "show your autobiography."
- The dashboard includes a Self Model panel backed by protected `/self/*` API endpoints.

Operational reliability layer:

- `core/agent_blackboard.py` gives agents a shared structured workspace for findings, questions, evidence, blockers, decisions, confidence levels, and next needs.
- `core/task_contracts.py` creates a goal, success criteria, expected output, risk level, tools-needed list, and verification method before background work is marked complete.
- `core/evaluation_lab.py` tracks STT mistakes, slow responses, failed tools, completed/stuck tasks, unsupported claims, and latency signals.
- `core/agent_memory.py` gives every specialist a notebook so Research, Developer, QA, UI/UX, and Security agents retrieve relevant lessons before answering.
- `core/approval_inbox.py` aggregates risky actions, blocked tasks, agent questions, desktop confirmations, and self-update proposals so Friday can say how many decisions are waiting.
- `core/browser_playwright.py` adds an optional Playwright DOM-control layer for websites; it gracefully reports the install hint if the Python package or browser binaries are missing.
- `core/voice_reliability.py` stores transcript mistakes, expected text, backend, audio duration, confidence, and learned wake-name aliases such as Friady/Freddie/Fryday.
- The dashboard exposes Approval Inbox, Agent Blackboard, Evaluation Lab, Agent Memory, task contract details, Playwright status, and voice reliability summaries.

## Functional Requirements

| ID | Requirement | Status | Local evidence |
| --- | --- | --- | --- |
| FR-V2-01 | Background agents run while voice loop remains responsive | Implemented | `core/background_agents.py` runs daemon workers outside the voice loop with idle/backoff sleeps and CPU guard. This uses Windows-safe worker threads rather than rewriting the whole voice process around asyncio. |
| FR-V2-02 | CEO decomposes goals into tasks without further user input | Implemented | Deterministic delegation remains, and `core/agents.py` now supports dynamic LLM JSON decomposition with safe agent-id filtering and fallback plans. |
| FR-V2-03 | Agents post status to task queue and user can query team work | Implemented | `tools/agent_team.py`, `core/task_queue.py`, `core/agent_office.py`, `core/agent_blackboard.py`, `core/agent_thought_bus.py`, direct commands in `core/orchestrator.py`, task reassignment, agent question board, silent thought bus, `/ws/tasks`, and dashboard Office Floor/Blackboard/Thought Bus/Approval Inbox. |
| FR-V2-04 | Background agents do not interrupt voice unless critical decision needed | Implemented | Workers log to queue/episodic store and do not speak directly into the voice loop. `core/proactive_speech.py` is the controlled exception for due reminders, calendar heads-up messages, and important agent/task decisions, with quiet hours and rate limits. |
| FR-V2-05 | In-progress work persists to SQLite and resumes after restart | Implemented | `data/task_queue.sqlite3`, WAL task queue. |
| FR-V2-06 | CEO takes screenshots, analyzes with vision LLM, acts with pyautogui | Implemented | `core/desktop_vision.py` captures screenshots, uses Gemini vision when `GEMINI_API_KEY` is configured, falls back to local screen metadata, reads Chrome DOM, Windows UI Automation, PC awareness inventory, and recent `core/visual_monitor.py` visual-change context when available, executes safe PyAutoGUI/DOM/UIA actions, and supports persisted multi-step `desktop_task` sessions with screenshots, progress checks, pause/resume, recovery actions, UI element memory, CAPTCHA/login handoff, step auto-extension, risky-action confirmation, and world-model expected/observed outcome tracking through `core/desktop_tasks.py`. `core/browser_playwright.py` adds optional Playwright DOM automation for websites. |
| FR-V2-07 | Agents browse web, read PDFs, fetch YouTube transcripts autonomously | Implemented | `core/search_broker.py` provides the dedicated API-backed search layer with provider fallback, normalized results, cache, dedupe, and reranking. `core/research.py` supports brokered web snippets, page text, PDF extraction, and YouTube transcripts. `core/app_integrations.py` adds workspace indexing/search, `core/capability_center.py` adds project maps/dependency health/auto docs/test watching, `core/semantic_search.py` indexes safe local context, `core/knowledge_graph.py` connects files/projects/goals/tasks/events, and `core/context_fusion.py` combines current browser/PC/phone/task signals. `core/google_workspace.py` and `core/calendar_email_assistant.py` add real OAuth-backed Google briefings/data access when connected. Research findings are handed off into target-agent task messages, procedural memory, agent notebooks, and long-term learning. |
| FR-V2-08 | FastAPI server on localhost:8000 for dashboard/cloud sync | Implemented | `api/server.py`, `python jarvis.py --api`. |
| FR-V2-09 | FastAPI deployable to Railway/Render and dashboard accessible online | Partial | Dockerfiles, Docker Compose, and `render.yaml` exist. Needs real deployment credentials/domains to verify online access. |
| FR-V2-10 | SQLite syncs to PostgreSQL every 5 minutes | Partial | Optional `core/cloud_sync.py` syncs tasks/messages/audit rows to PostgreSQL when `DATABASE_URL` and `cloud_sync_enabled` are set. Needs real cloud database verification. |
| FR-V2-11 | All API endpoints require JWT authentication | Implemented for local API | Data endpoints require Bearer JWT; refresh uses httpOnly cookie. Login endpoint is the only credential entrypoint. Permission rules, permission events, cognition, self-model, blackboard, contracts, evaluation, approval inbox, agent memory, Playwright, voice reliability, mission control, QA Lab, app-state memory, release manager, semantic search, operating rhythm, error radar, browser-extension bridge, Android app companion, command memory, autonomous debugger/learning, environment awareness, continuity, context fusion, deep project autopilot, silence mode, browser/PC copilot, skill evolution, safety guardian, phone mesh, knowledge graph, calendar/email assistant, and proof-report endpoints are also behind JWT auth. |
| FR-V2-12 | Task queue fields: ID, agent, status, priority, input, output | Implemented | `core/task_queue.py`. |
| FR-V2-13 | Agents spawn sub-tasks and assign other agents | Implemented | CEO/Senior/Junior delegation creates child tasks with `parent_id` and persisted messages. Agents also receive a peer directory and can route explicit questions to other specialists as child tasks. |
| FR-V2-14 | Senior Dev reviews Junior Dev and stores feedback in graph | Implemented | Junior tasks spawn Senior review tasks; structured review feedback is extracted, stored as graph edges, and promoted into procedural lessons. |
| FR-V2-15 | All agent actions logged to episodic store | Implemented for background task execution | `core/background_agents.py` writes `agent_task` events. |
| FR-V2-16 | Nightly consolidation: episodic to semantic, forgetting curve, archive | Implemented | `core/consolidation.py`, `core/memory.py`, plus `core/long_term_learning.py` review scheduling for durable lessons. |
| FR-V2-17 | Per-agent competence map; low scores trigger research | Implemented | `core/competence.py` tracks topic scores; weak topics trigger pre-task research context before agent execution. `core/self_reflection.py` and `core/goal_regulation.py` add metacognitive findings and operational state. |
| FR-V2-18 | Neo4j graph migration and Cypher | Implemented | `core/neo4j_migration.py` exports the local graph to idempotent Cypher, and `POST /graph/neo4j/export` exposes the migration behind JWT auth. |
| FR-V2-19 | React dashboard: status, Kanban, live log stream, output viewer | Implemented | Next.js dashboard exists in `apps/web`: App Router now lives in `apps/web/src/app`, every sidebar destination has its own thin `page.tsx` route under `(dashboard)`, Tailwind CSS is configured, and the frontend is organized under `apps/web/src` with `components`, `hooks`, `services`, `lib`, and `ui`; the dashboard includes JWT login, Stitch-inspired Command Center shell, Friday Chat, agent status, Office Floor, Mission Control, task board, approvals, realtime task progress over `/ws/tasks`, and system intelligence rail. |
| FR-V2-20 | Designer learns UI/UX from YouTube; Dev reads official docs | Implemented | Low-priority scheduled learning tasks seed UI/UX, official-doc, and security learning work; research ingestion and procedural memory store reusable lessons. |

## Non-Functional Requirements

| ID | Requirement | Status | Notes |
| --- | --- | --- | --- |
| NFR-V2-01 | Background agents consume under 40% CPU | Partial | CPU guard pauses workers above configured `v2_max_cpu_percent`; `--fast-voice` now pauses background workers by default to protect live conversation. Real long-running measurement on target hardware still needed. |
| NFR-V2-02 | Dashboard API responses under 500ms excluding LLM | Implemented | `/metrics/api-benchmark` checks core local API operations against `api_response_target_ms`. |
| NFR-V2-03 | Inter-agent messages persisted with no loss on restart | Implemented | `task_messages` table, SQLite WAL. |
| NFR-V2-04 | JWT expires after 24h; refresh token httpOnly cookie only | Implemented | `core/api_auth.py`, `api/server.py`. |
| NFR-V2-05 | Ethical hacker double confirmation | Implemented | Ethical hacker tasks are created as `blocked`; CEO approval is recorded by the coordinator path, and user approval requires the explicit phrase `I authorize task <id>`. |
| NFR-V2-06 | Filesystem/network/UI modifying actions logged | Implemented | SQLite audit log covers PC control, file reads/listing, desktop/screen actions, web search/URL opens, sent email, and code review file reads. `core/permissions.py` separately logs allow/ask/block decisions for tool execution. `core/capability_center.py` logs capability events, automation recipes, verified security scopes, and security findings to `data/capability_center.sqlite3`. Self-update sessions and staged changes persist to `data/self_updates.sqlite3`, with file backups under `data/self_updates/backups`. |
| NFR-V2-07 | 10 concurrent agents on 16GB RAM | Implemented for API-backed mode | `core/agents.py` enables API-agent mode when NVIDIA/Gemini/OpenRouter/Anthropic credentials exist, `core/background_agents.py` scales default workers to `v2_api_background_worker_count=10`, and `core/llm.py` enforces per-provider concurrency, spacing, queue timeout, and rate-limit backoff. Local/Ollama fallback remains one-worker CPU-safe; live free-tier quota testing is still provider-dependent. |
| NFR-V2-08 | Self-learning tasks lowest priority | Implemented | `core/learning_scheduler.py` seeds self-learning tasks at configurable low priority with future `scheduled_at`. |
| NFR-V2-09 | Dashboard responsive at 375px | Implemented | Verified with Chrome headless at 375x812; screenshot saved to `data/screenshots/web_mobile_375_next_fixed.png`. |
| NFR-V2-10 | Cloud sync HTTPS end-to-end | Partial | Docker/Render deploy path and PostgreSQL sync exist; end-to-end HTTPS verification needs an actual domain/cloud deployment. |
