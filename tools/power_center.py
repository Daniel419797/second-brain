"""Tool wrapper for Friday's extended power modules."""

from __future__ import annotations

from typing import Any

from core import (
    ad_campaigns,
    agent_council,
    agent_lifecycle,
    agent_quality_manager,
    agent_simulation_sandbox,
    agent_scheduler,
    academic_projects,
    agency_mode,
    app_apprenticeship,
    app_operators,
    app_operator_mastery,
    app_state_memory,
    android_companion,
    automation_builder,
    autonomous_coding,
    autonomous_debugger,
    autonomous_fix_loop,
    autonomous_learning,
    autonomous_qa_lab,
    autonomous_release_engine,
    autonomy_engine,
    awareness_graph,
    backup_recovery,
    browser_extension_bridge,
    browser_extension_pro,
    browser_pc_copilot,
    calendar_email_assistant,
    certainty_brain,
    cloud_worker_mode,
    codebase_standards,
    code_change_simulator,
    command_graph,
    company_runtime,
    competitive_benchmark,
    connector_runtime,
    contextual_workspace,
    context_aware_silence,
    context_fusion,
    continuity_brain,
    conversation_continuity,
    daily_companion,
    decision_memory,
    deep_project_autopilot,
    deployment_brain,
    device_command_mesh,
    dev_server_copilot,
    do_not_forget,
    emotion_tone,
    environment_awareness,
    emotional_timing,
    error_radar,
    event_nervous_system,
    executive_capabilities,
    focus_protection,
    failure_autopsy,
    friday_gateway,
    git_integration,
    goal_manager,
    home_assistant,
    learning_roadmap,
    learning_coach,
    life_os_mode,
    live_workspace_coach,
    local_ai_search,
    local_file_intelligence,
    local_voice_brain,
    meeting_study_companion,
    memory_debate,
    memory_constitution,
    memory_governance,
    mission_control,
    model_3d,
    model_benchmark_lab,
    model_router_brain,
    notification_center,
    notification_intelligence,
    offline_survival,
    operator_skills,
    operating_rhythm,
    os_autopilot,
    pc_timeline,
    personal_automation_daemon,
    personal_command_memory,
    personal_crm,
    personal_data_timeline,
    personal_knowledge_vault,
    personal_finance,
    personal_life_os,
    personal_memory_review,
    personal_safety_guardian,
    personal_taste_engine,
    phone_mesh,
    private_embedding_memory,
    privacy_firewall_pro,
    privacy_vault,
    production_coding_autonomy,
    project_cto,
    project_ideation,
    project_memory,
    project_autopilot,
    project_watchdog,
    proactive_guardian,
    reality_check,
    release_manager,
    reliability_score,
    research_briefings,
    refactor_planner,
    sandbox_simulation,
    security_guardian_pro,
    self_debugger,
    self_testing_personality,
    semantic_search,
    skill_marketplace,
    skill_evolution,
    skill_improvement,
    skill_library,
    skill_training_studio,
    test_build_monitor,
    trust_dashboard,
    trust_proof,
    version_guardian,
    vision_skill_learning,
    visual_skill_memory_v2,
    voice_command_repair,
    workspace_brain,
)


def execute(inputs: dict[str, Any]) -> str:
    action = str(inputs.get("action") or "overview").strip().lower()
    permission_reply = _permission_reply(inputs)
    if permission_reply:
        return permission_reply
    try:
        if action == "install_builtin_skills":
            installed = skill_library.install_builtin(str(inputs.get("key") or "all"))
            return f"Installed {len(installed)} built-in skills."
        if action == "list_skills":
            summary = skill_library.skill_summary()
            return f"Skills: {summary['enabled']} enabled, {summary['disabled']} disabled."
        if action == "workspace_analyze":
            return workspace_brain.analyze_project(str(inputs.get("root") or "")).get("summary", "Workspace analysis unavailable.")
        if action == "workspace_question":
            return workspace_brain.answer_workspace_question(str(inputs.get("question") or inputs.get("target") or ""), str(inputs.get("root") or "")).get("summary", "No answer.")
        if action == "workspace_docs":
            return workspace_brain.generate_docs(str(inputs.get("root") or "")).get("summary", "Docs unavailable.")
        if action == "list_app_operators":
            return "\n".join(f"{item['id']}: {item['name']}" for item in app_operators.list_operators())
        if action == "operate_app":
            result = app_operators.operate(str(inputs.get("app") or inputs.get("target") or ""), str(inputs.get("instruction") or inputs.get("goal") or ""), max_steps=_int(inputs.get("max_steps"), 0))
            return result.get("summary", "Operator unavailable.")
        if action == "autonomous_coding":
            return autonomous_coding.start(
                str(inputs.get("request") or inputs.get("instruction") or inputs.get("target") or ""),
                root=str(inputs.get("root") or ""),
                risk_level=str(inputs.get("risk_level") or "medium"),
            ).get("summary", "Autonomous coding unavailable.")
        if action == "project_ideas_research":
            return _project_ideas_summary(
                project_ideation.research_project_ideas(
                    str(inputs.get("context") or inputs.get("request") or inputs.get("query") or ""),
                    audience=str(inputs.get("audience") or "individuals, small teams, and SMBs"),
                    root=str(inputs.get("root") or ""),
                    limit=_int(inputs.get("limit"), 5),
                    max_sources=_int(inputs.get("max_sources"), 8),
                )
            )
        if action == "daily_plan":
            return personal_life_os.daily_plan().get("summary", "No plan.")
        if action == "next_action":
            return personal_life_os.what_should_i_do_next().get("summary", "No next action.")
        if action == "end_of_day":
            return personal_life_os.end_of_day_summary().get("summary", "No summary.")
        if action == "home_assistant_status":
            return home_assistant.status().get("summary", "Home Assistant unavailable.")
        if action == "home_assistant_focus":
            return home_assistant.focus_mode(on=bool(inputs.get("on", True))).get("summary", "Focus mode unavailable.")
        if action == "backup_config":
            return backup_recovery.snapshot_config(str(inputs.get("label") or "config snapshot")).get("summary", "Backup unavailable.")
        if action == "backup_file":
            return backup_recovery.backup_file(str(inputs.get("path") or inputs.get("target") or ""), label=str(inputs.get("label") or "")).get("summary", "Backup unavailable.")
        if action == "list_backups":
            return f"{len(backup_recovery.list_backups(limit=_int(inputs.get('limit'), 10)))} backups found."
        if action == "delete_guard":
            return backup_recovery.risky_delete_guard(str(inputs.get("path") or inputs.get("target") or "")).get("summary", "Delete guard unavailable.")
        if action == "guardian_scan":
            return proactive_guardian.run_scan().get("summary", "Guardian scan unavailable.")
        if action == "guardian_status":
            status = proactive_guardian.status()
            last = status.get("last_run") if isinstance(status.get("last_run"), dict) else {}
            return last.get("summary") or str(status.get("status") or "Guardian unavailable.")
        if action == "event_status":
            return event_nervous_system.summary().get("voice_summary", "Nervous system unavailable.")
        if action == "event_scan":
            return event_nervous_system.run_once().get("summary", "Event scan unavailable.")
        if action == "daily_companion_brief":
            return daily_companion.morning_brief().get("summary", "Daily brief unavailable.")
        if action == "daily_companion_checkin":
            return daily_companion.check_in().get("summary", "Check-in unavailable.")
        if action == "notifications":
            return notification_center.summary().get("voice_summary", "No notifications.")
        if action == "ad_campaign_draft":
            return ad_campaigns.draft(
                str(inputs.get("product") or inputs.get("name") or inputs.get("target") or inputs.get("title") or ""),
                audience=str(inputs.get("audience") or ""),
                offer=str(inputs.get("offer") or inputs.get("body") or inputs.get("content") or ""),
                objective=str(inputs.get("objective") or "conversions"),
                platform=str(inputs.get("platform") or inputs.get("connector") or "social"),
                tone=str(inputs.get("tone") or "direct"),
                metadata=inputs.get("metadata") if isinstance(inputs.get("metadata"), dict) else {},
            ).get("summary", "Ad campaign draft unavailable.")
        if action == "ad_campaign_post":
            return ad_campaigns.queue_post(
                _int(inputs.get("campaign_id") or inputs.get("target_id"), 0),
                connector=str(inputs.get("connector") or inputs.get("platform") or ""),
                target=str(inputs.get("target") or inputs.get("to") or inputs.get("channel") or ""),
                variant_index=_int(inputs.get("variant_index"), 0),
                product=str(inputs.get("product") or inputs.get("name") or inputs.get("title") or ""),
                audience=str(inputs.get("audience") or ""),
                offer=str(inputs.get("offer") or inputs.get("body") or inputs.get("content") or ""),
                platform=str(inputs.get("platform") or inputs.get("connector") or ""),
                tone=str(inputs.get("tone") or "direct"),
            ).get("summary", "Ad campaign post unavailable.")
        if action == "skill_marketplace":
            return skill_marketplace.summary().get("summary", "Skill marketplace unavailable.")
        if action == "skill_marketplace_install":
            return skill_marketplace.install(str(inputs.get("key") or "all")).get("summary", "Skill install unavailable.")
        if action == "gateway_status":
            return friday_gateway.status().get("summary", "Friday Gateway unavailable.")
        if action == "gateway_connectors":
            connectors = friday_gateway.connector_status()
            configured = len([item for item in connectors if item.get("configured")])
            enabled = len([item for item in connectors if item.get("enabled")])
            return f"Friday Gateway has {enabled} enabled connector(s) and {configured} configured connector(s)."
        if action == "gateway_configure_connector":
            return friday_gateway.configure_connector(
                str(inputs.get("connector") or inputs.get("target") or ""),
                enabled=inputs.get("enabled") if "enabled" in inputs else None,
                mode=str(inputs.get("mode") or ""),
                trust_level=str(inputs.get("trust_level") or ""),
                metadata=inputs.get("metadata") if isinstance(inputs.get("metadata"), dict) else {},
            ).get("summary", "Connector updated.")
        if action == "gateway_ingest_event":
            return friday_gateway.ingest_event(
                str(inputs.get("connector") or "web"),
                str(inputs.get("event_type") or inputs.get("kind") or "message"),
                str(inputs.get("title") or inputs.get("target") or "Gateway event"),
                str(inputs.get("content") or inputs.get("description") or inputs.get("message") or ""),
                actor=str(inputs.get("actor") or ""),
                source="power_center",
                payload=inputs.get("payload") if isinstance(inputs.get("payload"), dict) else {},
                route=bool(inputs.get("route", True)),
            ).get("summary", "Gateway event received.")
        if action == "control_room":
            return friday_gateway.control_room().get("summary", "Control room unavailable.")
        if action == "benchmark_status":
            return competitive_benchmark.status().get("summary", "Benchmark unavailable.")
        if action == "benchmark_run":
            return competitive_benchmark.run_suite(
                str(inputs.get("candidate") or "friday"),
                str(inputs.get("baseline") or "openclaw"),
                run_live=bool(inputs.get("run_live", False)),
            ).get("summary", "Benchmark run unavailable.")
        if action == "connector_runtime_status":
            return connector_runtime.status().get("summary", "Connector runtime unavailable.")
        if action == "connector_send":
            return connector_runtime.queue_message(
                str(inputs.get("connector") or inputs.get("channel") or "gmail"),
                str(inputs.get("target") or inputs.get("to") or ""),
                str(inputs.get("body") or inputs.get("message") or inputs.get("content") or ""),
                subject=str(inputs.get("subject") or inputs.get("title") or ""),
                action=str(inputs.get("connector_action") or inputs.get("kind") or "message"),
                payload=inputs.get("payload") if isinstance(inputs.get("payload"), dict) else {},
                require_approval=inputs.get("require_approval") if "require_approval" in inputs else None,
            ).get("summary", "Connector send queued.")
        if action == "connector_approve":
            return connector_runtime.approve_outbox(
                _int(inputs.get("outbox_id") or inputs.get("target"), 0),
                note=str(inputs.get("note") or inputs.get("reason") or ""),
                dispatch=bool(inputs.get("dispatch", False)),
            ).get("summary", "Connector outbox approved.")
        if action == "connector_dispatch":
            return connector_runtime.dispatch_outbox(_int(inputs.get("outbox_id") or inputs.get("target"), 0)).get("summary", "Connector dispatch unavailable.")
        if action == "company_runtime_status":
            return company_runtime.status().get("summary", "Company runtime unavailable.")
        if action == "company_worker_state":
            return company_runtime.set_worker_state(
                str(inputs.get("agent_id") or inputs.get("target") or ""),
                str(inputs.get("state") or "working"),
                task_id=_int(inputs.get("task_id"), 0),
                blocker=str(inputs.get("blocker") or ""),
                progress=_float(inputs.get("progress"), 0.0),
                metadata=inputs.get("metadata") if isinstance(inputs.get("metadata"), dict) else {},
            ).get("summary", "Worker state unavailable.")
        if action == "company_handoff":
            return company_runtime.handoff(
                str(inputs.get("from_agent") or inputs.get("agent_id") or "ceo"),
                str(inputs.get("to_agent") or inputs.get("target") or ""),
                str(inputs.get("title") or "Agent handoff"),
                str(inputs.get("summary") or inputs.get("content") or inputs.get("description") or ""),
                task_id=_int(inputs.get("task_id"), 0),
                evidence=inputs.get("evidence") or [],
            ).get("summary", "Company handoff unavailable.")
        if action == "production_coding_prepare":
            return production_coding_autonomy.prepare_project(
                str(inputs.get("root") or ""),
                request=str(inputs.get("request") or inputs.get("instruction") or inputs.get("target") or ""),
                create_files=bool(inputs.get("create_files", True)),
                run_scans=bool(inputs.get("run_scans", True)),
            ).get("summary", "Production coding prep unavailable.")
        if action == "memory_governance_status":
            return memory_governance.status().get("summary", "Memory governance unavailable.")
        if action == "memory_governance_remember":
            return memory_governance.remember(
                str(inputs.get("kind") or "reusable_decision"),
                str(inputs.get("title") or inputs.get("target") or "Governed memory"),
                str(inputs.get("content") or inputs.get("description") or ""),
                confidence=_float(inputs.get("confidence"), 0.75),
                review_after_days=_int(inputs.get("review_after_days"), 30),
                metadata=inputs.get("metadata") if isinstance(inputs.get("metadata"), dict) else {},
            ).get("summary", "Governed memory unavailable.")
        if action == "gateway_business_memory":
            return friday_gateway.business_memory(limit=_int(inputs.get("limit"), 30)).get("summary", "Business memory unavailable.")
        if action == "gateway_remember_business":
            return friday_gateway.remember_business_context(
                str(inputs.get("kind") or "reusable_decision"),
                str(inputs.get("title") or inputs.get("target") or "Business memory"),
                str(inputs.get("content") or inputs.get("description") or ""),
                confidence=_float(inputs.get("confidence"), 0.8),
                metadata=inputs.get("metadata") if isinstance(inputs.get("metadata"), dict) else {},
            ).get("summary", "Business memory saved.")
        if action == "gateway_emergency_stop":
            return friday_gateway.emergency_stop(str(inputs.get("reason") or inputs.get("description") or "Power Center emergency stop")).get("summary", "Emergency stop requested.")
        if action == "finance_summary":
            return personal_finance.summary().get("summary", "Finance summary unavailable.")
        if action == "add_expense":
            item = personal_finance.add_expense(_float(inputs.get("amount"), 0.0), category=str(inputs.get("category") or inputs.get("target") or "general"))
            return f"Recorded {item['amount']:.2f} {item['currency']} under {item['category']}."
        if action == "can_afford":
            return personal_finance.can_i_afford(_float(inputs.get("amount"), 0.0), category=str(inputs.get("category") or inputs.get("target") or "general")).get("summary", "Affordability check unavailable.")
        if action == "agency_status":
            return agency_mode.status().get("summary", "Agency Mode unavailable.")
        if action == "agency_lead_search":
            return agency_mode.search_leads(str(inputs.get("query") or inputs.get("target") or ""), niche=str(inputs.get("niche") or inputs.get("category") or ""), location=str(inputs.get("location") or ""), limit=_int(inputs.get("limit"), 5)).get("summary", "Lead search unavailable.")
        if action == "agency_add_lead":
            lead = agency_mode.add_lead(str(inputs.get("name") or inputs.get("company") or inputs.get("target") or ""), company=str(inputs.get("company") or ""), email=str(inputs.get("email") or ""), website=str(inputs.get("website") or ""), niche=str(inputs.get("niche") or ""), need=str(inputs.get("need") or inputs.get("description") or ""))
            return f"Agency lead #{lead['id']} saved for {lead['company']}."
        if action == "agency_score_leads":
            return agency_mode.score_all_leads(limit=_int(inputs.get("limit"), 50)).get("summary", "Lead scoring unavailable.")
        if action == "agency_draft_outreach":
            draft = agency_mode.draft_outreach(_int(inputs.get("lead_id") or inputs.get("target"), 0), service_offer=str(inputs.get("service_offer") or inputs.get("description") or ""), tone=str(inputs.get("tone") or "professional"), portfolio_url=str(inputs.get("portfolio_url") or ""), call_to_action=str(inputs.get("call_to_action") or ""))
            return draft.get("summary", "Outreach draft unavailable.")
        if action == "agency_approve_outreach":
            ids = inputs.get("ids") or inputs.get("outreach_ids") or inputs.get("outreach_id") or inputs.get("target") or 0
            return agency_mode.approve_outreach(ids if isinstance(ids, list) else _int(ids, 0), note=str(inputs.get("note") or inputs.get("reason") or "")).get("summary", "Outreach approval unavailable.")
        if action == "agency_send_outreach":
            ids = inputs.get("ids") or inputs.get("outreach_ids") or inputs.get("outreach_id") or inputs.get("target") or 0
            return agency_mode.send_outreach(ids if isinstance(ids, list) else _int(ids, 0)).get("summary", "Outreach send unavailable.")
        if action == "agency_draft_proposal":
            return agency_mode.draft_proposal(_int(inputs.get("lead_id") or inputs.get("target"), 0), scope=str(inputs.get("scope") or inputs.get("description") or ""), price=_float(inputs.get("amount") or inputs.get("price"), 0.0), currency=str(inputs.get("currency") or "")).get("summary", "Proposal draft unavailable.")
        if action == "agency_draft_contract":
            return agency_mode.draft_contract(_int(inputs.get("lead_id") or inputs.get("target"), 0), scope=str(inputs.get("scope") or inputs.get("description") or ""), price=_float(inputs.get("amount") or inputs.get("price"), 0.0), currency=str(inputs.get("currency") or "")).get("summary", "Contract draft unavailable.")
        if action == "agency_project_plan":
            return agency_mode.draft_project_plan(_int(inputs.get("lead_id") or inputs.get("target"), 0), scope=str(inputs.get("scope") or inputs.get("description") or ""), timeline=str(inputs.get("timeline") or "")).get("summary", "Project plan unavailable.")
        if action == "agency_start_project":
            return agency_mode.start_client_project(_int(inputs.get("lead_id"), 0), name=str(inputs.get("name") or inputs.get("title") or inputs.get("target") or ""), brief=str(inputs.get("brief") or inputs.get("description") or inputs.get("content") or ""), budget=_float(inputs.get("amount") or inputs.get("budget"), 0.0), currency=str(inputs.get("currency") or "")).get("summary", "Client project start unavailable.")
        if action == "agency_project_workflow":
            return agency_mode.run_project_workflow(
                _int(inputs.get("project_id") or inputs.get("target"), 0),
                commit=bool(inputs.get("commit", False)),
                push=bool(inputs.get("push", False)),
                deploy=bool(inputs.get("deploy", False)),
                deploy_command=str(inputs.get("deploy_command") or inputs.get("command") or ""),
                target_url=str(inputs.get("target_url") or inputs.get("url") or ""),
            ).get("summary", "Client project workflow unavailable.")
        if action == "agency_invoice":
            return agency_mode.create_invoice(_int(inputs.get("project_id"), 0), client_name=str(inputs.get("client_name") or inputs.get("name") or ""), client_email=str(inputs.get("client_email") or inputs.get("email") or ""), amount=_float(inputs.get("amount"), 0.0), currency=str(inputs.get("currency") or "")).get("summary", "Invoice unavailable.")
        if action == "agency_profit":
            return agency_mode.profit_summary(currency=str(inputs.get("currency") or "")).get("summary", "Profit summary unavailable.")
        if action == "agency_recommend_payment":
            return agency_mode.recommend_payment(str(inputs.get("provider") or inputs.get("target") or ""), _float(inputs.get("amount"), 0.0), reason=str(inputs.get("reason") or inputs.get("description") or ""), currency=str(inputs.get("currency") or "")).get("summary", "Payment recommendation unavailable.")
        if action == "agency_approve_payment":
            return agency_mode.approve_payment(_int(inputs.get("recommendation_id") or inputs.get("ledger_id") or inputs.get("target"), 0), note=str(inputs.get("note") or inputs.get("reason") or "")).get("summary", "Payment approval unavailable.")
        if action == "agency_trigger_payment":
            return agency_mode.trigger_approved_payment(_int(inputs.get("recommendation_id") or inputs.get("ledger_id") or inputs.get("target"), 0)).get("summary", "Payment trigger unavailable.")
        if action == "agency_pipeline":
            return agency_mode.pipeline_summary().get("summary", "Agency pipeline unavailable.")
        if action == "agency_api_budget":
            return agency_mode.api_budget_status(currency=str(inputs.get("currency") or "")).get("summary", "Agency API budget unavailable.")
        if action == "agency_business_layer":
            return agency_mode.generate_business_layer(
                business_name=str(inputs.get("business_name") or inputs.get("name") or "Friday Agency"),
                tagline=str(inputs.get("tagline") or inputs.get("description") or ""),
                owner_email=str(inputs.get("owner_email") or inputs.get("email") or ""),
            ).get("summary", "Business layer generation unavailable.")
        if action == "private_memory_summary":
            return private_embedding_memory.summary().get("summary", "Private memory unavailable.")
        if action == "private_memory_search":
            results = private_embedding_memory.search(str(inputs.get("query") or inputs.get("target") or ""), limit=_int(inputs.get("limit"), 5))
            return f"{len(results)} private memory result(s) found."
        if action == "android_companion_status":
            return android_companion.companion_summary().get("summary", "Android companion unavailable.")
        if action == "android_app_devices":
            return f"{len(android_companion.list_app_devices(limit=_int(inputs.get('limit'), 8)))} Android companion app device(s) registered."
        if action == "project_watchdog_status":
            status = project_watchdog.status()
            latest = status.get("latest") or {}
            return latest.get("summary") or str(status.get("status") or "Project watchdog unavailable.")
        if action == "project_watchdog_run":
            return project_watchdog.run_once(str(inputs.get("root") or ""), notify=True).get("summary", "Project watchdog unavailable.")
        if action == "codebase_standards":
            return codebase_standards.scan(str(inputs.get("root") or ""), focus=str(inputs.get("focus") or inputs.get("target") or ""), max_files=_int(inputs.get("max_files"), 250)).get("summary", "Codebase standards unavailable.")
        if action == "codebase_standards_rules":
            data = codebase_standards.standards()
            thresholds = data.get("thresholds") or {}
            order = ", ".join("speed/performance" if item == "performance" else str(item) for item in (data.get("priority_order") or []))
            return f"Friday priorities: {order}. Preferred limits: {thresholds.get('max_file_lines', 300)} lines/file, {thresholds.get('max_function_lines', 60)} lines/function."
        if action == "simulate_action":
            return sandbox_simulation.simulate_action(str(inputs.get("kind") or ""), str(inputs.get("instruction") or inputs.get("target") or "")).get("summary", "Simulation unavailable.")
        if action == "privacy_vault_summary":
            return privacy_vault.summary().get("summary", "Privacy vault unavailable.")
        if action == "privacy_vault_store":
            item = privacy_vault.store_item(str(inputs.get("kind") or "private"), str(inputs.get("title") or inputs.get("target") or "Private item"), str(inputs.get("content") or ""))
            return f"Stored private vault item #{item['id']}."
        if action == "model_router_status":
            return model_router_brain.summary().get("summary", "Model router unavailable.")
        if action == "model_router_choose":
            return model_router_brain.choose_provider(str(inputs.get("task_type") or ""), str(inputs.get("text") or inputs.get("target") or "")).get("summary", "Model route unavailable.")
        if action == "self_debugger_status":
            return self_debugger.analyze_recent().get("summary", "Self-debugger unavailable.")
        if action == "self_debugger_report":
            report = self_debugger.record_failure(str(inputs.get("source") or "voice"), str(inputs.get("summary") or inputs.get("target") or "Unspecified failure"))
            return f"Self-debug report #{report['id']} created: {report['probable_cause']}."
        if action == "autonomous_debugger":
            return autonomous_debugger.watch(str(inputs.get("root") or "")).get("summary", "Autonomous debugger unavailable.")
        if action == "autonomous_debugger_analyze":
            return autonomous_debugger.analyze_text(str(inputs.get("text") or inputs.get("target") or ""), source=str(inputs.get("source") or "voice")).get("summary", "Debugger analysis unavailable.")
        if action == "command_memory":
            return personal_command_memory.summary().get("summary", "Command memory unavailable.")
        if action == "command_memory_learn":
            item = personal_command_memory.learn(str(inputs.get("heard_phrase") or inputs.get("target") or ""), str(inputs.get("canonical_command") or inputs.get("command") or inputs.get("content") or ""))
            return item.get("summary", "Command memory unavailable.")
        if action == "command_memory_defaults":
            return personal_command_memory.install_default_language().get("summary", "Default command language unavailable.")
        if action == "tone_status":
            return emotion_tone.summary().get("summary", "Tone awareness unavailable.")
        if action == "tone_analyze":
            return emotion_tone.analyze_text(str(inputs.get("text") or inputs.get("target") or "")).get("summary", "Tone analysis unavailable.")
        if action == "crm_summary":
            return personal_crm.summary().get("summary", "Personal CRM unavailable.")
        if action == "crm_remember_person":
            person = personal_crm.remember_person(str(inputs.get("name") or inputs.get("target") or ""), relationship=str(inputs.get("relationship") or inputs.get("kind") or ""), notes=str(inputs.get("notes") or inputs.get("content") or ""))
            return f"Remembered {person['name']}."
        if action == "crm_followups":
            return f"{len(personal_crm.upcoming_followups(limit=_int(inputs.get('limit'), 10)))} CRM follow-up(s) queued."
        if action == "learning_progress":
            return learning_coach.progress().get("summary", "Learning coach unavailable.")
        if action == "learning_add_card":
            card = learning_coach.add_card(str(inputs.get("topic") or inputs.get("category") or "general"), str(inputs.get("question") or inputs.get("target") or ""), str(inputs.get("answer") or inputs.get("content") or ""))
            return f"Added learning card #{card['id']}."
        if action == "learning_quiz":
            return learning_coach.quiz(str(inputs.get("topic") or inputs.get("category") or "")).get("summary", "No quiz.")
        if action == "autonomous_learning":
            return autonomous_learning.run_cycle(str(inputs.get("goal") or inputs.get("target") or ""), create_tasks=bool(inputs.get("create_tasks", True))).get("summary", "Autonomous learning unavailable.")
        if action == "calendar_email_brief":
            return calendar_email_assistant.daily_brief().get("summary", "Calendar/email assistant unavailable.")
        if action == "calendar_email_followups":
            return calendar_email_assistant.followup_review().get("summary", "Calendar/email follow-up review unavailable.")
        if action == "research_briefings":
            return research_briefings.summary().get("summary", "Research briefings unavailable.")
        if action == "research_brief":
            return research_briefings.generate(str(inputs.get("topic") or inputs.get("target") or ""), create_task=bool(inputs.get("create_task", False))).get("summary", "Research briefing unavailable.")
        if action == "research_subscribe":
            return research_briefings.subscribe(str(inputs.get("topic") or inputs.get("target") or ""), cadence=str(inputs.get("cadence") or "daily")).get("summary", "Research subscription unavailable.")
        if action == "academic_project":
            project = academic_projects.create_project(
                str(inputs.get("topic") or inputs.get("title") or inputs.get("target") or inputs.get("request") or ""),
                kind=str(inputs.get("kind") or "final_year_project"),
                citation_style=str(inputs.get("citation_style") or inputs.get("style") or "APA"),
                formats=inputs.get("formats") or inputs.get("format") or "",
                max_sources=_int(inputs.get("max_sources") or inputs.get("limit"), 0) or None,
                extra_requirements=str(inputs.get("requirements") or inputs.get("notes") or inputs.get("description") or ""),
            )
            return project.get("summary", "Academic project unavailable.")
        if action == "academic_export":
            exported = academic_projects.export_project(str(inputs.get("path") or inputs.get("target") or ""), formats=inputs.get("formats") or inputs.get("format") or "")
            return exported.get("summary", "Academic export unavailable.")
        if action == "git_status":
            return git_integration.status(str(inputs.get("root") or "")).get("summary", "Git status unavailable.")
        if action == "git_branches":
            return git_integration.branches(str(inputs.get("root") or "")).get("summary", "Git branches unavailable.")
        if action == "git_log":
            return git_integration.log(str(inputs.get("root") or ""), limit=_int(inputs.get("limit"), 5)).get("summary", "Git log unavailable.")
        if action == "git_diff":
            return git_integration.diff(
                str(inputs.get("root") or ""),
                staged=bool(inputs.get("staged", False)),
                path=str(inputs.get("path") or inputs.get("target") or ""),
            ).get("summary", "Git diff unavailable.")
        if action == "git_clone":
            return git_integration.clone(
                str(inputs.get("repo") or inputs.get("target") or ""),
                destination=str(inputs.get("destination") or inputs.get("path") or ""),
            ).get("summary", "Git clone unavailable.")
        if action == "git_checkout":
            return git_integration.checkout(
                str(inputs.get("root") or ""),
                branch=str(inputs.get("branch") or inputs.get("target") or ""),
                create=bool(inputs.get("create", False)),
            ).get("summary", "Git checkout unavailable.")
        if action == "git_pull":
            return git_integration.pull(
                str(inputs.get("root") or ""),
                remote=str(inputs.get("remote") or ""),
                branch=str(inputs.get("branch") or ""),
            ).get("summary", "Git pull unavailable.")
        if action == "git_add":
            return git_integration.add(str(inputs.get("root") or ""), paths=inputs.get("paths") or inputs.get("path") or inputs.get("target") or ".").get("summary", "Git add unavailable.")
        if action == "git_commit":
            return git_integration.commit(str(inputs.get("root") or ""), message=str(inputs.get("message") or inputs.get("content") or inputs.get("target") or "")).get("summary", "Git commit unavailable.")
        if action == "git_push":
            return git_integration.push(
                str(inputs.get("root") or ""),
                remote=str(inputs.get("remote") or ""),
                branch=str(inputs.get("branch") or ""),
                set_upstream=bool(inputs.get("set_upstream", False)),
            ).get("summary", "Git push unavailable.")
        if action == "github_status":
            return git_integration.github_status(str(inputs.get("root") or "")).get("summary", "GitHub status unavailable.")
        if action == "github_pr_create":
            return git_integration.create_pr(
                str(inputs.get("root") or ""),
                title=str(inputs.get("title") or inputs.get("target") or ""),
                body=str(inputs.get("body") or inputs.get("content") or ""),
                base=str(inputs.get("base") or ""),
                head=str(inputs.get("head") or ""),
            ).get("summary", "GitHub PR unavailable.")
        if action == "github_pr_list":
            return git_integration.list_prs(
                str(inputs.get("root") or ""),
                state=str(inputs.get("state") or "open"),
                limit=_int(inputs.get("limit"), 10),
            ).get("summary", "GitHub PR list unavailable.")
        if action == "github_issue_create":
            return git_integration.create_issue(
                str(inputs.get("root") or ""),
                title=str(inputs.get("title") or inputs.get("target") or ""),
                body=str(inputs.get("body") or inputs.get("content") or ""),
            ).get("summary", "GitHub issue unavailable.")
        if action == "model3d_create":
            model = model_3d.create_model(
                str(inputs.get("prompt") or inputs.get("description") or inputs.get("target") or inputs.get("request") or ""),
                shape=str(inputs.get("shape") or inputs.get("kind") or ""),
                formats=inputs.get("formats") or inputs.get("format") or "",
                name=str(inputs.get("name") or inputs.get("title") or ""),
                quality=str(inputs.get("quality") or inputs.get("mode") or ""),
                backend=str(inputs.get("backend") or inputs.get("provider") or ""),
            )
            return model.get("summary", "3D model unavailable.")
        if action == "workspace_context":
            return contextual_workspace.prepare_context(str(inputs.get("root") or "")).get("summary", "Workspace context unavailable.")
        if action == "workspace_context_status":
            return contextual_workspace.summary().get("summary", "No workspace context.")
        if action == "offline_status":
            return offline_survival.status().get("summary", "Offline survival unavailable.")
        if action == "offline_activate":
            return offline_survival.activate(str(inputs.get("reason") or inputs.get("target") or "manual")).get("summary", "Offline mode unavailable.")
        if action == "offline_deactivate":
            return offline_survival.deactivate(str(inputs.get("reason") or inputs.get("target") or "manual")).get("summary", "Online mode unavailable.")
        if action == "data_timeline":
            return personal_data_timeline.query(str(inputs.get("query") or inputs.get("target") or "today")).get("summary", "Timeline unavailable.")
        if action == "data_timeline_note":
            item = personal_data_timeline.record_note(str(inputs.get("title") or inputs.get("target") or "Timeline note"), str(inputs.get("content") or inputs.get("notes") or ""))
            return f"Timeline note #{item['id']} saved."
        if action == "skill_training_summary":
            return skill_training_studio.summary().get("summary", "Skill training unavailable.")
        if action == "skill_training_start":
            workflow = skill_training_studio.start_workflow(str(inputs.get("title") or inputs.get("target") or "Untitled workflow"), description=str(inputs.get("description") or inputs.get("content") or ""), agent_id=str(inputs.get("agent_id") or "jarvis"))
            return f"Started workflow #{workflow['id']}: {workflow['name']}."
        if action == "skill_training_add_step":
            workflow = skill_training_studio.add_step(_int(inputs.get("workflow_id"), 0), str(inputs.get("instruction") or inputs.get("target") or ""), expected_result=str(inputs.get("expected_result") or inputs.get("content") or ""))
            return f"Workflow #{workflow['id']} now has {len(workflow['steps'])} step(s)."
        if action == "skill_training_finish":
            workflow = skill_training_studio.finish_workflow(_int(inputs.get("workflow_id"), 0))
            return f"Published workflow as skill {workflow['skill_id']}."
        if action == "remember_vault":
            item = personal_knowledge_vault.remember(
                str(inputs.get("kind") or "fact"),
                str(inputs.get("title") or inputs.get("target") or ""),
                str(inputs.get("content") or inputs.get("notes") or ""),
            )
            return f"Saved {item['kind']}: {item['title']}."
        if action == "vault_search":
            results = personal_knowledge_vault.search(str(inputs.get("query") or inputs.get("target") or ""))
            return f"{len(results)} vault item(s) matched."
        if action == "weekly_priorities":
            return personal_knowledge_vault.what_matters_this_week().get("summary", "No weekly priorities.")
        if action == "voice_repair":
            return voice_command_repair.record_repair(str(inputs.get("expected_text") or inputs.get("target") or ""), str(inputs.get("heard_text") or "")).get("summary", "Voice repair unavailable.")
        if action == "project_autopilot":
            return project_autopilot.inspect_project(str(inputs.get("root") or ""), run_tests=bool(inputs.get("run_tests", False))).get("summary", "Project autopilot unavailable.")
        if action == "project_prepare_fixes":
            return project_autopilot.prepare_fixes(str(inputs.get("root") or ""), issue_query=str(inputs.get("query") or "")).get("summary", "Project fix prep unavailable.")
        if action == "pc_timeline":
            return pc_timeline.capture_snapshot().get("summary", "PC timeline unavailable.")
        if action == "pc_timeline_summary":
            return pc_timeline.summary().get("summary", "No PC timeline.")
        if action == "goal_plan":
            return goal_manager.create_goal_plan(str(inputs.get("title") or inputs.get("target") or ""), str(inputs.get("description") or "")).get("summary", "Goal plan unavailable.")
        if action == "goal_next":
            return goal_manager.next_goal_action().get("summary", "No next goal action.")
        if action == "file_index":
            paths = inputs.get("paths")
            if isinstance(paths, str):
                paths = [paths]
            return local_file_intelligence.index_locations(paths if isinstance(paths, list) else None).get("summary", "File index unavailable.")
        if action == "file_search":
            return local_file_intelligence.answer(str(inputs.get("query") or inputs.get("target") or "")).get("answer", "No file answer.")
        if action == "folder_summary":
            return local_file_intelligence.summarize_folder(str(inputs.get("path") or inputs.get("target") or "")).get("summary", "Folder summary unavailable.")
        if action == "study_session":
            session = meeting_study_companion.create_session(
                str(inputs.get("title") or "Study session"),
                kind=str(inputs.get("kind") or "study"),
                transcript=str(inputs.get("transcript") or inputs.get("content") or ""),
            )
            return f"Study session #{session['id']} ready: {session.get('summary') or 'No summary yet.'}"
        if action == "automation_from_text":
            return automation_builder.create_from_text(str(inputs.get("text") or inputs.get("target") or "")).get("summary", "Automation unavailable.")
        if action == "automation_run_matches":
            return automation_builder.evaluate_triggers().get("summary", "Automation trigger check unavailable.")
        if action == "executive_summary":
            return executive_capabilities.summary().get("summary", "Executive capabilities unavailable.")
        if action == "memory_review":
            return executive_capabilities.generate_memory_reviews(limit=_int(inputs.get("limit"), 12)).get("summary", "Memory review unavailable.")
        if action == "memory_review_resolve":
            item = executive_capabilities.resolve_memory_review(_int(inputs.get("review_id") or inputs.get("target"), 0), str(inputs.get("decision") or "skip"), note=str(inputs.get("note") or inputs.get("content") or ""))
            return f"Memory review #{item['id']} marked {item['decision']}."
        if action == "task_autopilot":
            run = executive_capabilities.start_task_autopilot(str(inputs.get("goal") or inputs.get("target") or ""), sphere=str(inputs.get("sphere") or ""), root=str(inputs.get("root") or ""))
            return run.get("summary", "Task autopilot unavailable.")
        if action == "task_autopilot_status":
            return executive_capabilities.refresh_task_autopilot().get("summary", "Task autopilot unavailable.")
        if action == "personality_profile":
            profile = executive_capabilities.set_personality_profile(str(inputs.get("profile") or inputs.get("target") or "focused"), reason=str(inputs.get("reason") or "voice"))
            return profile.get("summary", "Personality profile unavailable.")
        if action == "life_dashboard":
            return executive_capabilities.life_dashboard().get("summary", "Life dashboard unavailable.")
        if action == "skill_record_start":
            recording = executive_capabilities.start_skill_recording(str(inputs.get("name") or inputs.get("title") or inputs.get("target") or "Untitled workflow"))
            return f"Started skill recording #{recording['id']}: {recording['name']}."
        if action == "skill_record_step":
            recording = executive_capabilities.add_skill_recording_step(_int(inputs.get("recording_id") or inputs.get("target"), 0), str(inputs.get("narration") or inputs.get("instruction") or inputs.get("content") or ""), expected_result=str(inputs.get("expected_result") or ""))
            return f"Skill recording #{recording['id']} has {len(recording.get('steps') or [])} step(s)."
        if action == "skill_record_finish":
            recording = executive_capabilities.finish_skill_recording(_int(inputs.get("recording_id") or inputs.get("target"), 0))
            return f"Published recorded skill from recording #{recording['id']}."
        if action == "documentation_brain":
            return executive_capabilities.update_documentation(str(inputs.get("root") or "")).get("summary", "Documentation brain unavailable.")
        if action == "personal_search":
            return executive_capabilities.personal_search(str(inputs.get("query") or inputs.get("target") or "")).get("summary", "Personal search unavailable.")
        if action == "trust_meter":
            return executive_capabilities.trust_assessment(str(inputs.get("instruction") or inputs.get("target") or ""), domain=str(inputs.get("domain") or inputs.get("kind") or "general")).get("summary", "Trust meter unavailable.")
        if action == "learning_twin":
            return executive_capabilities.learning_twin().get("summary", "Learning twin unavailable.")
        if action == "relationship_assistant":
            return executive_capabilities.relationship_assistant().get("summary", "Relationship assistant unavailable.")
        if action == "deployment_commander":
            return executive_capabilities.deployment_inspect(str(inputs.get("target") or ""), root=str(inputs.get("root") or "")).get("summary", "Deployment commander unavailable.")
        if action == "privacy_firewall":
            return executive_capabilities.privacy_firewall_check(str(inputs.get("instruction") or inputs.get("target") or ""), context=str(inputs.get("context") or "")).get("summary", "Privacy firewall unavailable.")
        if action == "mission_start":
            mission = mission_control.create_mission(str(inputs.get("goal") or inputs.get("target") or ""), root=str(inputs.get("root") or ""), mission_type=str(inputs.get("mission_type") or ""), priority=_int(inputs.get("priority"), 2))
            return f"Mission #{mission['id']} started in {mission['current_phase'].replace('_', ' ')}."
        if action == "mission_status":
            return mission_control.voice_status()
        if action == "mission_pause":
            mission = mission_control.pause_mission(_mission_id(inputs))
            return f"Mission #{mission.get('id')} paused."
        if action == "mission_resume":
            mission = mission_control.resume_mission(_mission_id(inputs))
            return f"Mission #{mission.get('id')} resumed."
        if action == "mission_stop":
            mission = mission_control.stop_mission(_mission_id(inputs))
            return f"Mission #{mission.get('id')} stopped."
        if action == "mission_approve":
            mission = mission_control.approve_mission(_int(inputs.get("mission_id") or inputs.get("target"), 0), kind=str(inputs.get("kind") or "next_step"), note=str(inputs.get("note") or "voice approval"))
            return f"Mission #{mission.get('id')} approval recorded."
        if action == "mission_approve_deploy":
            mission = mission_control.approve_deploy(_int(inputs.get("mission_id") or inputs.get("target"), 0), note=str(inputs.get("note") or "voice deploy approval"))
            return f"Deploy approval recorded for mission #{mission.get('id')}."
        if action == "mission_evidence":
            mission_id = _int(inputs.get("mission_id") or inputs.get("target"), 0)
            items = mission_control.evidence(mission_id, limit=_int(inputs.get("limit"), 5)) if mission_id else []
            return f"{len(items)} evidence item(s) found." if items else mission_control.voice_status()
        if action == "proof_report":
            report = trust_proof.from_mission(_int(inputs.get("mission_id") or inputs.get("target"), 0)) if inputs.get("mission_id") or inputs.get("target") else trust_proof.create_report(str(inputs.get("title") or "Manual proof report"), evidence=[str(inputs.get("evidence") or inputs.get("content") or "")])
            return report.get("summary", "Proof report unavailable.")
        if action == "qa_lab":
            report = autonomous_qa_lab.run_qa(str(inputs.get("root") or ""), mission_id=_optional_int(inputs.get("mission_id")), run_tests=bool(inputs.get("run_tests", False)))
            return report.get("summary", "QA Lab unavailable.")
        if action == "qa_lab_reports":
            return autonomous_qa_lab.status().get("summary", "QA Lab unavailable.")
        if action == "release_prepare":
            release = release_manager.prepare_release(str(inputs.get("root") or ""), mission_id=_optional_int(inputs.get("mission_id")), version=str(inputs.get("version") or ""))
            return release.get("summary", "Release manager unavailable.")
        if action == "release_status":
            return release_manager.status().get("summary", "Release manager unavailable.")
        if action == "release_approve_deploy":
            release = release_manager.approve_deploy(_int(inputs.get("release_id") or inputs.get("target"), 0), note=str(inputs.get("note") or "voice approval"))
            return f"Release #{release.get('id')} deploy approved."
        if action == "error_radar":
            return error_radar.watch(str(inputs.get("root") or "")).get("summary", "Error radar unavailable.")
        if action == "error_radar_status":
            return error_radar.status().get("summary", "Error radar unavailable.")
        if action == "semantic_index":
            return semantic_search.index_path(str(inputs.get("path") or inputs.get("root") or ""), include_private=bool(inputs.get("include_private", False))).get("summary", "Semantic index unavailable.")
        if action == "semantic_search":
            results = semantic_search.search(str(inputs.get("query") or inputs.get("target") or ""), limit=_int(inputs.get("limit"), 8), include_sensitive=bool(inputs.get("include_sensitive", False)))
            return f"{len(results)} search result(s) found."
        if action == "semantic_status":
            return semantic_search.status().get("summary", "Semantic search unavailable.")
        if action == "browser_extension_status":
            return browser_extension_bridge.status().get("summary", "Browser extension bridge unavailable.")
        if action == "browser_extension_insight":
            return browser_extension_bridge.latest_page_insight().get("summary", "No browser insight available.")
        if action == "browser_pc_copilot":
            return browser_pc_copilot.current_page_help().get("summary", "Browser/PC copilot unavailable.")
        if action == "browser_pc_debug":
            return browser_pc_copilot.debug_current_page().get("summary", "Browser/PC debug unavailable.")
        if action == "app_state_memory":
            return app_state_memory.summary().get("summary", "App state memory unavailable.")
        if action == "app_state_search":
            results = app_state_memory.search_patterns(str(inputs.get("app") or ""), str(inputs.get("query") or inputs.get("target") or ""), limit=_int(inputs.get("limit"), 8))
            return f"{len(results)} app memory pattern(s) matched."
        if action == "rhythm_summary":
            return operating_rhythm.summary().get("summary", "Operating rhythm unavailable.")
        if action == "energy_note":
            note = operating_rhythm.record_energy(str(inputs.get("mood") or inputs.get("target") or "neutral"), energy=_int(inputs.get("energy"), 5), focus=_int(inputs.get("focus"), 5), notes=str(inputs.get("notes") or ""))
            return f"Energy note saved: {note['mood']}, energy {note['energy']}, focus {note['focus']}."
        if action == "environment_status":
            return environment_awareness.status().get("summary", "Environment awareness unavailable.")
        if action == "environment_snapshot":
            return environment_awareness.snapshot(force_refresh=True).get("summary", "Environment snapshot unavailable.")
        if action == "continuity_status":
            return continuity_brain.status().get("summary", "Continuity brain unavailable.")
        if action == "continuity_capture":
            return continuity_brain.capture_current_state().get("summary", "Continuity capture unavailable.")
        if action == "context_fusion":
            return context_fusion.snapshot(force_refresh=bool(inputs.get("force_refresh", False))).get("summary", "Context fusion unavailable.")
        if action == "deep_project_autopilot":
            return deep_project_autopilot.run(str(inputs.get("root") or ""), run_tests=bool(inputs.get("run_tests", False)), log_text=str(inputs.get("log_text") or inputs.get("text") or ""), prepare_fix=bool(inputs.get("prepare_fix", False))).get("summary", "Deep project autopilot unavailable.")
        if action == "silence_mode":
            if inputs.get("mode") or inputs.get("target"):
                return context_aware_silence.set_mode(str(inputs.get("mode") or inputs.get("target")), reason=str(inputs.get("reason") or "voice")).get("summary", "Silence mode unavailable.")
            return context_aware_silence.summary().get("summary", "Silence mode unavailable.")
        if action == "skill_evolution":
            return skill_evolution.suggest_from_patterns().get("summary", "Skill evolution unavailable.")
        if action == "skill_evolution_observe":
            return skill_evolution.observe_workflow(str(inputs.get("signature") or inputs.get("target") or ""), str(inputs.get("description") or inputs.get("content") or "")).get("summary", "Skill observation unavailable.")
        if action == "safety_guardian":
            return personal_safety_guardian.scan(str(inputs.get("root") or "")).get("summary", "Safety guardian unavailable.")
        if action == "safety_preflight":
            return personal_safety_guardian.preflight_action(str(inputs.get("instruction") or inputs.get("target") or ""), path=str(inputs.get("path") or "")).get("summary", "Safety preflight unavailable.")
        if action == "phone_mesh":
            return phone_mesh.status().get("summary", "Phone mesh unavailable.")
        if action == "phone_handoff":
            return phone_mesh.create_handoff(str(inputs.get("device_id") or ""), str(inputs.get("title") or inputs.get("target") or "Phone handoff"), payload={"command": str(inputs.get("command") or inputs.get("content") or "")}).get("summary", "Phone handoff unavailable.")
        if action == "agent_scheduler_status":
            return agent_scheduler.status().get("summary", "Agent scheduler unavailable.")
        if action == "agent_scheduler_plan":
            return agent_scheduler.plan(str(inputs.get("mode") or "auto"), voice_active=bool(inputs.get("voice_active", False))).get("summary", "Agent scheduler unavailable.")
        if action == "agent_scheduler_apply":
            return agent_scheduler.plan(str(inputs.get("mode") or "auto"), voice_active=bool(inputs.get("voice_active", False)), apply=True).get("summary", "Agent scheduler unavailable.")
        if action == "retry_failed_tasks":
            return agent_scheduler.retry_failed_tasks(limit=_int(inputs.get("limit"), 3)).get("summary", "Retry unavailable.")
        if action == "schedule_overnight_research":
            return agent_scheduler.schedule_overnight_research(str(inputs.get("topic") or inputs.get("target") or ""), priority=_int(inputs.get("priority"), 9)).get("summary", "Research schedule unavailable.")
        if action == "test_build_monitor":
            return test_build_monitor.run_check(str(inputs.get("root") or ""), str(inputs.get("command") or inputs.get("target") or ""), create_proof=bool(inputs.get("create_proof", True))).get("summary", "Test/build monitor unavailable.")
        if action == "test_build_monitor_status":
            return test_build_monitor.status().get("summary", "Test/build monitor unavailable.")
        if action == "reliability_score":
            return reliability_score.snapshot().get("summary", "Reliability score unavailable.")
        if action == "reliability_score_status":
            return reliability_score.status().get("summary", "Reliability score unavailable.")
        if action == "model_benchmark":
            raw_types = inputs.get("task_types") or inputs.get("target") or []
            if isinstance(raw_types, str):
                raw_types = [item.strip() for item in raw_types.split(",") if item.strip()]
            return model_benchmark_lab.run_benchmark(raw_types if isinstance(raw_types, list) else None, run_live=bool(inputs.get("run_live", False))).get("summary", "Model benchmark unavailable.")
        if action == "model_benchmark_status":
            return model_benchmark_lab.status().get("summary", "Model benchmark unavailable.")
        if action == "deployment_brain":
            return deployment_brain.inspect(str(inputs.get("target") or ""), root=str(inputs.get("root") or ""), create_proof=bool(inputs.get("create_proof", True))).get("summary", "Deployment brain unavailable.")
        if action == "deployment_brain_status":
            return deployment_brain.status().get("summary", "Deployment brain unavailable.")
        if action == "os_autopilot":
            return os_autopilot.recommendation().get("recommendation", "OS autopilot unavailable.")
        if action == "os_autopilot_status":
            return os_autopilot.status().get("summary", "OS autopilot unavailable.")
        if action == "version_guardian_snapshot":
            paths = inputs.get("paths") or inputs.get("path") or inputs.get("target") or []
            if isinstance(paths, str):
                paths = [paths]
            return version_guardian.snapshot_files(paths if isinstance(paths, list) else [], label=str(inputs.get("label") or "voice snapshot"), mission_id=_optional_int(inputs.get("mission_id"))).get("summary", "Version snapshot unavailable.")
        if action == "version_guardian_preflight":
            paths = inputs.get("paths") or inputs.get("path") or []
            if isinstance(paths, str):
                paths = [paths]
            return version_guardian.preflight(str(inputs.get("instruction") or inputs.get("target") or ""), paths if isinstance(paths, list) else []).get("summary", "Version preflight unavailable.")
        if action == "awareness_graph":
            if inputs.get("force") or inputs.get("force_refresh"):
                awareness_graph.refresh(force=True)
            return awareness_graph.answer(str(inputs.get("question") or inputs.get("target") or "what is happening right now")).get("answer", "Awareness graph unavailable.")
        if action == "awareness_graph_status":
            return awareness_graph.status().get("summary", "Awareness graph unavailable.")
        if action == "fix_loop":
            return autonomous_fix_loop.run(
                root=str(inputs.get("root") or ""),
                command=str(inputs.get("command") or ""),
                log_text=str(inputs.get("log_text") or inputs.get("text") or ""),
                source=str(inputs.get("source") or "power_center"),
                run_tests=bool(inputs.get("run_tests", True)),
            ).get("summary", "Fix loop unavailable.")
        if action == "fix_loop_status":
            return autonomous_fix_loop.status().get("summary", "Fix loop unavailable.")
        if action == "browser_pro":
            return browser_extension_pro.guidance(str(inputs.get("question") or inputs.get("target") or "what should I click")).get("summary", "Browser Pro unavailable.")
        if action == "browser_pro_watch":
            return browser_extension_pro.watch_page().get("summary", "Browser watch unavailable.")
        if action == "browser_pro_fill":
            return browser_extension_pro.safe_fill(str(inputs.get("selector") or inputs.get("target") or ""), str(inputs.get("value") or inputs.get("content") or ""), reason=str(inputs.get("reason") or "")).get("summary", "Browser fill unavailable.")
        if action == "android_pro":
            status = android_companion.status()
            return f"{status.get('summary', 'Android companion unavailable.')} {len(status.get('recent_files') or [])} recent phone file(s)."
        if action == "memory_review_pro":
            return personal_memory_review.generate(limit=_int(inputs.get("limit"), 12)).get("summary", "Memory review unavailable.")
        if action == "app_mastery":
            return app_operator_mastery.plan(str(inputs.get("app") or inputs.get("target") or "chrome"), str(inputs.get("instruction") or inputs.get("goal") or "")).get("summary", "App mastery unavailable.")
        if action == "local_ai_search":
            return local_ai_search.answer(str(inputs.get("query") or inputs.get("target") or ""), limit=_int(inputs.get("limit"), 8)).get("answer", "Local AI search unavailable.")
        if action == "local_ai_index":
            paths = inputs.get("paths") or inputs.get("path") or inputs.get("root") or []
            if isinstance(paths, str):
                paths = [paths]
            return local_ai_search.index(paths if isinstance(paths, list) else [], include_private=bool(inputs.get("include_private", False))).get("summary", "Local AI index unavailable.")
        if action == "life_os":
            return life_os_mode.daily_brief().get("summary", "Life OS unavailable.")
        if action == "life_os_next":
            return life_os_mode.next_action().get("summary", "Life OS next action unavailable.")
        if action == "security_guardian_pro":
            return security_guardian_pro.scan(str(inputs.get("root") or ""), light=True).get("summary", "Security Guardian Pro unavailable.")
        if action == "cloud_worker":
            return cloud_worker_mode.status().get("summary", "Cloud worker mode unavailable.")
        if action == "cloud_worker_submit":
            return cloud_worker_mode.submit(str(inputs.get("job_type") or inputs.get("kind") or "research"), str(inputs.get("title") or inputs.get("target") or "Background job"), payload={"instruction": str(inputs.get("instruction") or inputs.get("content") or "")}, prefer_cloud=bool(inputs.get("prefer_cloud", True))).get("summary", "Cloud worker submit unavailable.")
        if action == "autonomy_engine":
            run = autonomy_engine.run_until_blocked(
                str(inputs.get("goal") or inputs.get("target") or ""),
                root=str(inputs.get("root") or ""),
                max_steps=_int(inputs.get("max_steps"), 5),
            )
            return run.get("summary", "Autonomy engine unavailable.")
        if action == "autonomy_status":
            return autonomy_engine.status().get("summary", "Autonomy engine unavailable.")
        if action == "certainty_brain":
            return certainty_brain.answer(str(inputs.get("query") or inputs.get("question") or inputs.get("target") or "")).get("answer", "Certainty brain unavailable.")
        if action == "certainty_record":
            item = certainty_brain.record(
                str(inputs.get("kind") or "known"),
                str(inputs.get("topic") or inputs.get("category") or "general"),
                str(inputs.get("statement") or inputs.get("content") or inputs.get("target") or ""),
                evidence=inputs.get("evidence") or [],
                confidence=_float(inputs.get("confidence"), 0.75),
                source=str(inputs.get("source") or "voice"),
            )
            return f"Recorded {item['kind']} certainty for {item['topic']}."
        if action == "vision_skill_learn":
            item = vision_skill_learning.learn_pattern(
                app=str(inputs.get("app") or inputs.get("target") or ""),
                label=str(inputs.get("label") or inputs.get("title") or "UI pattern"),
                pattern_type=str(inputs.get("pattern_type") or inputs.get("kind") or "ui_element"),
                visual_cues=inputs.get("visual_cues") or [],
                dom_cues=inputs.get("dom_cues") or [],
                accessibility_cues=inputs.get("accessibility_cues") or [],
                meaning=str(inputs.get("meaning") or inputs.get("content") or ""),
                action_hint=str(inputs.get("action_hint") or inputs.get("instruction") or ""),
                confidence=_float(inputs.get("confidence"), 0.7),
            )
            return f"Learned {item['app']} UI pattern: {item['label']}."
        if action == "vision_skill_recognize":
            result = vision_skill_learning.recognize(str(inputs.get("app") or ""), str(inputs.get("query") or inputs.get("target") or ""), limit=_int(inputs.get("limit"), 8))
            return result.get("summary", "No vision skill pattern matched.")
        if action == "automation_daemon":
            return personal_automation_daemon.run_once(run_actions=bool(inputs.get("run_actions", True))).get("summary", "Automation daemon unavailable.")
        if action == "automation_daemon_status":
            return personal_automation_daemon.status().get("summary", "Automation daemon unavailable.")
        if action == "notification_intelligence":
            return notification_intelligence.rank_pending(limit=_int(inputs.get("limit"), 50)).get("summary", "Notification intelligence unavailable.")
        if action == "self_test_personality":
            return self_testing_personality.run().get("summary", "Self-test unavailable.")
        if action == "project_memory":
            return project_memory.profile(str(inputs.get("root") or ""), refresh=bool(inputs.get("refresh", False))).get("summary", "Project memory unavailable.")
        if action == "project_memory_remember":
            note = project_memory.remember(
                str(inputs.get("root") or ""),
                str(inputs.get("kind") or "note"),
                str(inputs.get("title") or inputs.get("target") or "Project note"),
                str(inputs.get("content") or inputs.get("notes") or ""),
                confidence=_float(inputs.get("confidence"), 0.75),
            )
            return f"Saved project memory note #{note['id']}: {note['title']}."
        if action == "operator_skills":
            if inputs.get("app") or inputs.get("target"):
                return operator_skills.plan(str(inputs.get("app") or inputs.get("target") or ""), str(inputs.get("instruction") or inputs.get("goal") or ""), root=str(inputs.get("root") or "")).get("summary", "Operator skill unavailable.")
            return operator_skills.status().get("summary", "Operator skills unavailable.")
        if action == "operator_skill_start":
            return operator_skills.start(str(inputs.get("app") or inputs.get("target") or ""), str(inputs.get("instruction") or inputs.get("goal") or ""), max_steps=_int(inputs.get("max_steps"), 12), root=str(inputs.get("root") or "")).get("summary", "Operator skill unavailable.")
        if action == "learning_roadmap":
            return learning_roadmap.create(str(inputs.get("topic") or inputs.get("target") or "learning"), str(inputs.get("goal") or ""), weeks=_int(inputs.get("weeks"), 4)).get("summary", "Learning roadmap unavailable.")
        if action == "learning_roadmap_quiz":
            return learning_roadmap.next_quiz(str(inputs.get("topic") or inputs.get("target") or "")).get("summary", "Learning roadmap quiz unavailable.")
        if action == "privacy_firewall_pro":
            return privacy_firewall_pro.check(
                str(inputs.get("instruction") or inputs.get("target") or ""),
                context=str(inputs.get("context") or ""),
                paths=inputs.get("paths") or inputs.get("path") or [],
                purpose=str(inputs.get("purpose") or ""),
            ).get("summary", "Privacy Firewall Pro unavailable.")
        if action == "device_mesh":
            return device_command_mesh.status().get("summary", "Device mesh unavailable.")
        if action == "device_mesh_handoff":
            return device_command_mesh.create_command(
                str(inputs.get("command_type") or "handoff"),
                str(inputs.get("title") or inputs.get("target") or "Device handoff"),
                source_device=str(inputs.get("source_device") or "laptop"),
                target_device=str(inputs.get("target_device") or "laptop"),
                payload={"instruction": str(inputs.get("instruction") or inputs.get("content") or "")},
            ).get("summary", "Device mesh handoff unavailable.")
        if action == "release_engine":
            return autonomous_release_engine.prepare(
                str(inputs.get("root") or ""),
                build_command=str(inputs.get("build_command") or inputs.get("command") or ""),
                target_url=str(inputs.get("target_url") or inputs.get("url") or ""),
                run_tests=bool(inputs.get("run_tests", False)),
            ).get("summary", "Release engine unavailable.")
        if action == "release_engine_status":
            return autonomous_release_engine.status().get("summary", "Release engine unavailable.")
        if action == "decision_memory":
            if inputs.get("preference") or inputs.get("content"):
                item = decision_memory.remember(
                    str(inputs.get("category") or "communication"),
                    str(inputs.get("preference") or inputs.get("content") or inputs.get("target") or ""),
                    threshold=str(inputs.get("threshold") or ""),
                    evidence=inputs.get("evidence") or [],
                    confidence=_float(inputs.get("confidence"), 0.75),
                    source=str(inputs.get("source") or "power_center"),
                )
                return f"Saved decision preference: {item['preference']}"
            return decision_memory.status().get("summary", "Decision memory unavailable.")
        if action == "decision_memory_infer":
            return decision_memory.learn_from_text(str(inputs.get("text") or inputs.get("content") or inputs.get("target") or ""), source=str(inputs.get("source") or "power_center")).get("summary", "Decision inference unavailable.")
        if action == "skill_improvement":
            return skill_improvement.status().get("summary", "Skill improvement unavailable.")
        if action == "skill_failure":
            return skill_improvement.record_failure(
                str(inputs.get("skill") or inputs.get("target") or "unknown_skill"),
                str(inputs.get("failure") or inputs.get("summary") or inputs.get("content") or ""),
                evidence=inputs.get("evidence") or [],
                context={"source": "power_center", "app": inputs.get("app"), "selector": inputs.get("selector")},
            ).get("summary", "Skill failure recorded.")
        if action == "workspace_coach":
            return live_workspace_coach.observe(
                str(inputs.get("root") or ""),
                log_text=str(inputs.get("log_text") or inputs.get("content") or ""),
                current_file=str(inputs.get("current_file") or inputs.get("path") or ""),
                run_tests=bool(inputs.get("run_tests", False)),
                notify=bool(inputs.get("notify", True)),
            ).get("summary", "Workspace coach unavailable.")
        if action == "memory_debate":
            return memory_debate.debate(str(inputs.get("topic") or inputs.get("query") or inputs.get("target") or ""), limit=_int(inputs.get("limit"), 8)).get("summary", "Memory debate unavailable.")
        if action == "memory_review_debate":
            return memory_debate.review(limit=_int(inputs.get("limit"), 8)).get("summary", "Memory debate unavailable.")
        if action == "focus_protection":
            return focus_protection.status().get("summary", "Focus protection unavailable.")
        if action == "focus_mode":
            return focus_protection.set_mode(str(inputs.get("mode") or inputs.get("target") or "focus"), reason=str(inputs.get("reason") or "power_center")).get("summary", "Focus mode unavailable.")
        if action == "app_apprenticeship_start":
            return app_apprenticeship.start(str(inputs.get("app") or inputs.get("target") or ""), str(inputs.get("workflow") or inputs.get("name") or inputs.get("instruction") or "workflow"), goal=str(inputs.get("goal") or "")).get("summary", "App apprenticeship unavailable.")
        if action == "app_apprenticeship_step":
            return app_apprenticeship.record_step(
                _int(inputs.get("session_id") or inputs.get("recording_id"), 0),
                str(inputs.get("narration") or inputs.get("instruction") or ""),
                action=str(inputs.get("action_taken") or inputs.get("command") or inputs.get("action_detail") or ""),
                observation=str(inputs.get("observation") or inputs.get("expected_result") or ""),
                selector=str(inputs.get("selector") or ""),
                screenshot=str(inputs.get("screenshot") or ""),
                success=bool(inputs.get("success", True)),
            ).get("summary", "App apprenticeship step unavailable.")
        if action == "app_apprenticeship_finish":
            return app_apprenticeship.finish(_int(inputs.get("session_id") or inputs.get("recording_id"), 0)).get("summary", "App apprenticeship unavailable.")
        if action == "project_cto":
            return project_cto.report(str(inputs.get("root") or ""), refresh=bool(inputs.get("refresh", True))).get("summary", "Project CTO unavailable.")
        if action == "conversation_continuity":
            return conversation_continuity.status().get("summary", "Conversation continuity unavailable.")
        if action == "conversation_capture":
            return conversation_continuity.capture(
                str(inputs.get("title") or inputs.get("target") or "Open thread"),
                summary=str(inputs.get("summary") or inputs.get("content") or ""),
                blocker=str(inputs.get("blocker") or ""),
                evidence=inputs.get("evidence") or [],
                source=str(inputs.get("source") or "power_center"),
            ).get("summary", "Conversation thread captured.")
        if action == "local_voice_brain":
            return local_voice_brain.status().get("summary", "Local voice brain unavailable.")
        if action == "local_voice_defaults":
            return local_voice_brain.install_defaults().get("summary", "Local voice defaults unavailable.")
        if action == "voice_brain_repair":
            return local_voice_brain.repair(str(inputs.get("heard") or inputs.get("heard_text") or ""), str(inputs.get("expected") or inputs.get("expected_text") or ""), source=str(inputs.get("source") or "power_center")).get("summary", "Voice repair unavailable.")
        if action == "trust_dashboard":
            return trust_dashboard.status().get("summary", "Trust dashboard unavailable.")
        if action == "agent_quality":
            return agent_quality_manager.status().get("summary", "Agent quality unavailable.")
        if action == "agent_leaderboard":
            rows = agent_quality_manager.leaderboard(task_type=str(inputs.get("task_type") or ""), limit=_int(inputs.get("limit"), 10))
            if not rows:
                return "No agent quality samples yet."
            return "Agent leaderboard: " + "; ".join(f"{row['agent_id']} {round(row['avg_score'] * 100)}%" for row in rows[:5])
        if action == "agent_hire":
            item = agent_lifecycle.hire_specialist(
                str(inputs.get("name") or inputs.get("target") or ""),
                str(inputs.get("purpose") or inputs.get("description") or inputs.get("instruction") or ""),
                keywords=inputs.get("keywords") or inputs.get("topic") or "",
                agent_id=str(inputs.get("agent_id") or ""),
            )
            return f"Hired {item.get('name')} as {item.get('id')}."
        if action == "agent_retire":
            return agent_lifecycle.retire_agent(str(inputs.get("agent_id") or inputs.get("target") or ""), reason=str(inputs.get("reason") or "")).get("summary", "Agent retired.")
        if action == "agent_promote":
            item = agent_lifecycle.promote_agent(str(inputs.get("agent_id") or inputs.get("target") or ""), reason=str(inputs.get("reason") or ""))
            return f"Promoted {item.get('name') or item.get('id') or 'agent'}."
        if action == "agent_rewrite_role":
            item = agent_lifecycle.rewrite_role(
                str(inputs.get("agent_id") or inputs.get("target") or ""),
                name=str(inputs.get("name") or ""),
                purpose=str(inputs.get("purpose") or inputs.get("description") or ""),
                keywords=inputs.get("keywords") or "",
            )
            return f"Updated role for {item.get('name') or item.get('id') or 'agent'}."
        if action == "agent_council":
            return agent_council.convene(
                str(inputs.get("question") or inputs.get("target") or inputs.get("instruction") or ""),
                agent_ids=inputs.get("agent_ids") or [],
                context=str(inputs.get("context") or ""),
            ).get("summary", "Agent council unavailable.")
        if action == "do_not_forget":
            return do_not_forget.classify(str(inputs.get("content") or inputs.get("text") or inputs.get("target") or ""), source=str(inputs.get("source") or "power_center")).get("summary", "Memory router unavailable.")
        if action == "dev_server_copilot":
            return dev_server_copilot.observe(str(inputs.get("root") or ""), log_text=str(inputs.get("log_text") or inputs.get("content") or ""), current_file=str(inputs.get("current_file") or inputs.get("path") or ""), source="power_center").get("summary", "Dev server copilot unavailable.")
        if action == "code_change_simulator":
            return code_change_simulator.simulate(str(inputs.get("instruction") or inputs.get("target") or inputs.get("content") or ""), root=str(inputs.get("root") or "")).get("summary", "Code change simulator unavailable.")
        if action == "refactor_planner":
            return refactor_planner.plan(str(inputs.get("root") or ""), focus=str(inputs.get("focus") or inputs.get("target") or "")).get("summary", "Refactor planner unavailable.")
        if action == "taste_engine":
            return personal_taste_engine.learn_from_correction(str(inputs.get("correction") or inputs.get("content") or inputs.get("target") or ""), domain=str(inputs.get("domain") or "general")).get("summary", "Taste engine unavailable.")
        if action == "taste_guidance":
            return personal_taste_engine.guidance(str(inputs.get("domain") or "general"), context=str(inputs.get("context") or inputs.get("target") or "")).get("summary", "Taste guidance unavailable.")
        if action == "memory_constitution":
            return memory_constitution.evaluate(str(inputs.get("kind") or ""), str(inputs.get("content") or inputs.get("target") or ""), sensitivity=str(inputs.get("sensitivity") or "normal")).get("summary", "Memory constitution unavailable.")
        if action == "reality_check":
            return reality_check.check(str(inputs.get("claim") or inputs.get("target") or ""), evidence=inputs.get("evidence") or inputs.get("content") or "", tool_result=inputs.get("tool_result"), domain=str(inputs.get("domain") or "general")).get("summary", "Reality check unavailable.")
        if action == "agent_simulation":
            return agent_simulation_sandbox.simulate(str(inputs.get("goal") or inputs.get("target") or inputs.get("instruction") or ""), agent_ids=inputs.get("agent_ids") or [], root=str(inputs.get("root") or ""), risk_level=str(inputs.get("risk_level") or "medium")).get("summary", "Agent simulation unavailable.")
        if action == "command_graph_defaults":
            return command_graph.install_defaults().get("summary", "Command graph defaults unavailable.")
        if action == "command_graph":
            phrase = str(inputs.get("phrase") or inputs.get("heard_phrase") or inputs.get("target") or "")
            if inputs.get("intent") or inputs.get("canonical_command"):
                return command_graph.learn_phrase(phrase, str(inputs.get("intent") or inputs.get("canonical_command") or ""), steps=inputs.get("steps") or inputs.get("content") or "").get("summary", "Command graph unavailable.")
            return command_graph.resolve(phrase).get("summary", "Command graph unavailable.")
        if action == "emotional_timing":
            return emotional_timing.advise(str(inputs.get("text") or inputs.get("content") or inputs.get("target") or ""), explicit_tone=str(inputs.get("tone") or "")).get("summary", "Emotional timing unavailable.")
        if action == "visual_skill_memory":
            return visual_skill_memory_v2.learn_screen(
                str(inputs.get("app") or ""),
                str(inputs.get("screen_label") or inputs.get("label") or inputs.get("target") or ""),
                cues=inputs.get("cues") or inputs.get("content") or "",
                meaning=str(inputs.get("meaning") or inputs.get("description") or ""),
                action_hint=str(inputs.get("action_hint") or inputs.get("instruction") or ""),
                source="power_center",
            ).get("summary", "Visual skill memory unavailable.")
        if action == "failure_autopsy":
            return failure_autopsy.create(
                str(inputs.get("title") or inputs.get("target") or "Friday failure"),
                str(inputs.get("what_happened") or inputs.get("summary") or inputs.get("content") or ""),
                root_cause=str(inputs.get("root_cause") or ""),
                next_time=str(inputs.get("next_time") or ""),
                evidence=inputs.get("evidence") or [],
                code_change_needed=bool(inputs.get("code_change_needed", False)),
                source=str(inputs.get("source") or "power_center"),
            ).get("summary", "Failure autopsy unavailable.")
    except Exception as exc:
        return f"Power center action failed: {exc}"
    return "Unknown power center action."


def _project_ideas_summary(result: dict[str, Any]) -> str:
    ideas = result.get("ideas") if isinstance(result.get("ideas"), list) else []
    artifacts = result.get("artifacts") if isinstance(result.get("artifacts"), list) else []
    sufficient = bool(result.get("research_sufficient"))
    summary = str(result.get("summary") or "").strip()
    if not sufficient or not ideas:
        packet = artifacts[0] if artifacts else ""
        suffix = f" Research packet: {packet}" if packet else ""
        return (summary or "I could not recommend a project yet because the research evidence was not strong enough.") + suffix
    top = ideas[0]
    title = str(top.get("title") or "Recommended project").strip()
    problem = str(top.get("problem") or "").strip()
    wedge = str(top.get("product_wedge") or "").strip()
    evidence_count = _int(top.get("evidence_count"), 0)
    packet = artifacts[0] if artifacts else ""
    parts = [
        f"Research-backed idea: {title}.",
        f"Problem: {problem}" if problem else "",
        f"Build wedge: {wedge}" if wedge else "",
        f"Evidence: {evidence_count} source signal(s) across the research run.",
        f"Research packet: {packet}" if packet else "",
    ]
    return " ".join(part for part in parts if part)


def _permission_reply(inputs: dict[str, Any]) -> str:
    try:
        from core import permissions

        decision = permissions.evaluate("power_center", inputs)
        if decision["blocked"]:
            return f"Permission blocked: {decision['label']} is set to block."
        if decision["requires_confirmation"] and not inputs.get("_permission_confirmed"):
            return f"Permission required: {decision['label']} is set to ask first."
    except Exception:
        return ""
    return ""


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _float(value: Any, default: float = 0.0) -> float:
    try:
        return float(str(value).replace(",", ""))
    except Exception:
        return default


def _optional_int(value: Any) -> int | None:
    try:
        number = int(value)
        return number if number > 0 else None
    except Exception:
        return None


def _mission_id(inputs: dict[str, Any]) -> int:
    mission_id = _int(inputs.get("mission_id") or inputs.get("target"), 0)
    if mission_id > 0:
        return mission_id
    active = mission_control.list_missions(status="running", limit=1) or mission_control.list_missions(status="blocked", limit=1) or mission_control.list_missions(status="paused", limit=1)
    return int(active[0]["id"]) if active else 0
