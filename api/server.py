"""FastAPI backend for the v2 dashboard and future Electron shell."""

from __future__ import annotations

import asyncio
import base64
import binascii
import datetime as dt
import json
import os
import re
import sys
import threading
import time
from pathlib import Path
from typing import Any

from fastapi import Body, Cookie, Depends, FastAPI, Header, HTTPException, Response, WebSocket, WebSocketDisconnect, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from pydantic import BaseModel, Field
try:
    from dotenv import load_dotenv
except Exception:  # pragma: no cover - optional in stripped runtime images
    def load_dotenv(*_args: Any, **_kwargs: Any) -> bool:
        return False

from core.config import DATA_DIR, LOG_DIR, config_value
from core.lazy_imports import lazy_module

def _load_runtime_env() -> None:
    if str(os.getenv("FRIDAY_LOAD_DOTENV", "1")).strip().lower() in {"0", "false", "no", "off"}:
        return
    if any("pytest" in str(arg).lower() for arg in sys.argv):
        return
    load_dotenv()


_load_runtime_env()


_CORE_MODULES = [
    "adaptive_attention", "agent_blackboard", "agent_memory", "agent_scheduler", "agent_thought_bus", "agents", "agent_office",
    "android_companion", "api_auth", "app_apprenticeship", "app_integrations", "app_operators", "app_operator_mastery",
    "app_state_memory", "approval_inbox", "audit_log", "autobiographical_memory", "automation_builder", "autonomous_coding",
    "autonomous_debugger", "autonomous_fix_loop", "autonomous_learning", "autonomous_qa_lab", "autonomous_release_engine",
    "autonomy_engine", "awareness_graph", "background_agents", "backup_recovery", "barge_in", "browser_extension_bridge",
    "browser_extension_pro", "browser_pc_copilot", "browser_playwright", "calendar_email_assistant", "capability_center",
    "certainty_brain", "cloud_sync", "cloud_worker_mode", "cognitive_cycle", "competence", "context_aware_silence",
    "context_fusion", "contextual_workspace", "continuity_brain", "conversation_continuity", "daily_companion",
    "decision_memory", "deep_project_autopilot", "deployment_brain", "desktop_tasks", "desktop_vision", "device_command_mesh",
    "emotion_tone", "environment_awareness", "episodic_store", "error_radar", "evaluation_lab", "event_nervous_system",
    "executive_capabilities", "focus_protection", "goal_manager", "goal_regulation", "google_workspace", "home_assistant",
    "identity", "image_generation", "knowledge_graph", "learning_coach", "learning_roadmap", "life_os_mode",
    "live_workspace_coach", "local_ai_search", "local_file_intelligence", "local_voice_brain", "llm", "long_term_learning",
    "meeting_study_companion", "memory_debate", "mission_control", "model_3d", "model_3d_studio",
    "model_benchmark_lab", "model_router_brain",
    "neo4j_migration", "notification_center", "notification_intelligence", "offline_survival", "operating_rhythm",
    "operator_skills", "orchestrator", "os_autopilot", "pc_awareness", "pc_timeline", "performance", "permissions",
    "personal_automation_daemon", "personal_command_memory", "personal_crm", "personal_data_timeline", "personal_finance",
    "personal_knowledge_vault", "personal_life_os", "personal_memory_review", "personal_safety_guardian", "phone_bridge",
    "phone_mesh", "private_embedding_memory", "privacy_firewall_pro", "privacy_vault", "project_autopilot", "project_cto",
    "project_memory", "project_watchdog", "proactive_guardian", "release_manager", "reliability_score", "research_briefings",
    "sandbox_simulation", "search_broker", "security_guardian_pro", "self_debugger", "self_model", "self_reflection",
    "self_testing_personality", "self_update", "semantic_search", "skill_evolution", "skill_improvement", "skill_library",
    "skill_marketplace", "skill_training_studio", "task_contracts", "task_queue", "test_build_monitor", "text_to_3d", "trust_dashboard",
    "trust_proof", "version_guardian", "vision_skill_learning", "visual_monitor", "voice_command_repair", "voice_reliability",
    "workspace_brain", "world_model", "agent_council", "agent_lifecycle", "agent_quality_manager", "agent_simulation_sandbox",
    "code_change_simulator", "codebase_standards", "command_graph", "dev_server_copilot", "do_not_forget", "emotional_timing",
    "failure_autopsy", "memory_constitution", "personal_taste_engine", "reality_check", "refactor_planner",
    "visual_skill_memory_v2",
]

globals().update({name: lazy_module(f"core.{name}") for name in _CORE_MODULES})
stt = lazy_module("input.speech_to_text")


class LoginRequest(BaseModel):
    username: str = Field(default="friday", max_length=80)
    password: str = Field(min_length=1, max_length=500)


class TaskCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    description: str = ""
    agent_id: str = ""
    priority: int = 5
    scheduled_at: str = ""


class TaskReassignRequest(BaseModel):
    agent_id: str = Field(min_length=1, max_length=120)
    status: str = Field(default="pending", max_length=40)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)


class ChatAttachmentRequest(BaseModel):
    filename: str = Field(default="attachment", max_length=300)
    content_type: str = Field(default="", max_length=160)
    data_url: str = Field(default="", max_length=30_000_000)
    base64: str = Field(default="", max_length=30_000_000)


class ImageGenerateRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=2000)
    negative_prompt: str = Field(default="", max_length=1000)
    provider: str = Field(default="auto", max_length=80)
    width: int = Field(default=768, ge=128, le=2048)
    height: int = Field(default=768, ge=128, le=2048)
    steps: int = Field(default=24, ge=1, le=100)


class DesktopTaskCreateRequest(BaseModel):
    instruction: str = Field(min_length=1, max_length=4000)
    max_steps: int = 0


class VisionMonitorRequest(BaseModel):
    source: str = Field(default="screen", max_length=20)
    analyze: bool | None = None
    realtime: bool = False


class IntegrationOpenRequest(BaseModel):
    target: str = Field(min_length=1, max_length=80)


class ContactRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    email: str = Field(default="", max_length=300)
    phone: str = Field(default="", max_length=80)
    notes: str = Field(default="", max_length=1000)


class ReminderRequest(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    due_at: str = Field(default="", max_length=200)
    notes: str = Field(default="", max_length=1000)


class CalendarEventRequest(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    start_at: str = Field(default="", max_length=200)
    end_at: str = Field(default="", max_length=200)
    location: str = Field(default="", max_length=300)
    notes: str = Field(default="", max_length=1000)


class DocumentRequest(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    body: str = Field(default="", max_length=20000)
    headers: list[str] = Field(default_factory=list)


class WorkspaceIndexRequest(BaseModel):
    root: str = Field(default="", max_length=1000)
    max_files: int = 0


class PhoneRegisterRequest(BaseModel):
    name: str = Field(default="Android Phone", max_length=200)
    adb_serial: str = Field(default="", max_length=200)
    ntfy_topic: str = Field(default="", max_length=300)
    phone_number: str = Field(default="", max_length=80)
    is_default: bool = True


class PhoneNotifyRequest(BaseModel):
    title: str = Field(default="Friday", max_length=200)
    message: str = Field(min_length=1, max_length=2000)
    priority: str = Field(default="high", max_length=40)
    tags: str = Field(default="iphone", max_length=120)


class PhoneRingRequest(BaseModel):
    message: str = Field(default="", max_length=2000)


class PhoneUrlRequest(BaseModel):
    url: str = Field(min_length=1, max_length=2000)


class PhoneDialRequest(BaseModel):
    number: str = Field(default="", max_length=80)
    contact: str = Field(default="", max_length=200)
    direct: bool = False


class PhoneSmsRequest(BaseModel):
    number: str = Field(min_length=1, max_length=80)
    message: str = Field(default="", max_length=2000)


class PhoneFileRequest(BaseModel):
    local_path: str = Field(default="", max_length=1000)
    phone_path: str = Field(default="", max_length=1000)
    local_dir: str = Field(default="", max_length=1000)
    limit: int = 50


class PhoneClipboardRequest(BaseModel):
    text: str = Field(min_length=1, max_length=4000)


class SecurityScopeRequest(BaseModel):
    target: str = Field(min_length=1, max_length=500)
    kind: str = Field(default="web", max_length=80)
    proof: str = Field(default="", max_length=2000)


class SecurityVerifyRequest(BaseModel):
    proof_url: str = Field(default="", max_length=2000)


class PortScanRequest(BaseModel):
    target: str = Field(default="127.0.0.1", max_length=500)
    ports: list[int] = Field(default_factory=list)


class CapabilityRootRequest(BaseModel):
    root: str = Field(default="", max_length=1000)


class CodebaseStandardsScanRequest(BaseModel):
    root: str = Field(default="", max_length=1000)
    focus: str = Field(default="", max_length=500)
    max_files: int = Field(default=250, ge=1, le=2000)


class TestWatchRequest(BaseModel):
    command: str = Field(default="", max_length=1000)


class AutomationRecipeRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    trigger_type: str = Field(default="manual", max_length=80)
    trigger: dict[str, Any] = Field(default_factory=dict)
    action_type: str = Field(default="notify_phone", max_length=80)
    action: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True


class HomeDeviceControlRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    action: str = Field(min_length=1, max_length=80)
    params: dict[str, Any] = Field(default_factory=dict)


class SkillInstallRequest(BaseModel):
    key: str = Field(default="all", max_length=120)


class SkillToggleRequest(BaseModel):
    enabled: bool = True


class WorkspaceQuestionRequest(BaseModel):
    question: str = Field(min_length=1, max_length=1000)
    root: str = Field(default="", max_length=1000)


class AppOperatorRequest(BaseModel):
    app: str = Field(min_length=1, max_length=120)
    instruction: str = Field(default="", max_length=4000)
    max_steps: int = 0


class AutonomousCodingRequest(BaseModel):
    request: str = Field(min_length=1, max_length=4000)
    root: str = Field(default="", max_length=1000)
    risk_level: str = Field(default="medium", max_length=80)


class RoutineRequest(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    cadence: str = Field(default="daily", max_length=80)
    next_due_at: str = Field(default="", max_length=200)
    notes: str = Field(default="", max_length=1000)


class MoodRequest(BaseModel):
    mood: str = Field(default="neutral", max_length=120)
    energy: int = 5
    notes: str = Field(default="", max_length=1000)


class HomeAssistantServiceRequest(BaseModel):
    domain: str = Field(min_length=1, max_length=100)
    service: str = Field(min_length=1, max_length=100)
    data: dict[str, Any] = Field(default_factory=dict)


class BackupFileRequest(BaseModel):
    path: str = Field(default="", max_length=1000)
    label: str = Field(default="", max_length=200)


class RestoreBackupRequest(BaseModel):
    confirm: bool = False


class NotificationMarkRequest(BaseModel):
    status: str = Field(default="read", max_length=40)


class VaultItemRequest(BaseModel):
    kind: str = Field(default="fact", max_length=80)
    title: str = Field(min_length=1, max_length=300)
    content: str = Field(default="", max_length=5000)
    confidence: float = 0.7
    tags: list[str] | str | None = None


class VoiceRepairRequest(BaseModel):
    expected_text: str = Field(min_length=1, max_length=1000)
    heard_text: str = Field(default="", max_length=1000)
    context: str = Field(default="", max_length=1000)


class ProjectAutopilotRequest(BaseModel):
    root: str = Field(default="", max_length=1000)
    run_tests: bool = False
    issue_query: str = Field(default="", max_length=500)


class GoalPlanRequest(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    description: str = Field(default="", max_length=2000)
    deadline_at: str = Field(default="", max_length=200)
    priority: int = 3


class LocalFileIndexRequest(BaseModel):
    paths: list[str] = Field(default_factory=list)
    max_files: int = 0


class LocalFileQueryRequest(BaseModel):
    query: str = Field(default="", max_length=1000)
    path: str = Field(default="", max_length=1000)
    limit: int = 20


class StudySessionRequest(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    kind: str = Field(default="meeting", max_length=80)
    source: str = Field(default="", max_length=300)
    transcript: str = Field(default="", max_length=40000)


class StudyTranscriptRequest(BaseModel):
    transcript: str = Field(min_length=1, max_length=40000)
    append: bool = True


class AutomationTextRequest(BaseModel):
    text: str = Field(min_length=1, max_length=1000)


class PermissionRuleRequest(BaseModel):
    mode: str = Field(pattern="^(allow|ask|block)$")


class GoalCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    description: str = Field(default="", max_length=2000)
    priority: int = 5
    source: str = Field(default="dashboard", max_length=80)
    deadline_at: str = Field(default="", max_length=200)


class GoalUpdateRequest(BaseModel):
    status: str | None = Field(default=None, max_length=40)
    progress: float | None = None
    note: str = Field(default="", max_length=1000)


class AttentionCorrectionRequest(BaseModel):
    expected_text: str = Field(min_length=1, max_length=1000)
    heard_text: str = Field(default="", max_length=1000)


class BlackboardItemRequest(BaseModel):
    agent_id: str = Field(default="friday", max_length=120)
    item_type: str = Field(default="finding", max_length=40)
    title: str = Field(min_length=1, max_length=300)
    content: str = Field(default="", max_length=5000)
    task_id: int | None = None
    confidence: float = 0.5
    target_agent_id: str = Field(default="", max_length=120)
    status: str = Field(default="open", max_length=40)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ThoughtPacketRequest(BaseModel):
    source_agent_id: str = Field(default="friday", max_length=120)
    packet_type: str = Field(default="context", max_length=60)
    summary: str = Field(min_length=1, max_length=500)
    content: dict[str, Any] | str | None = None
    target_agent_id: str = Field(default="", max_length=120)
    task_id: int | None = None
    confidence: float = 0.5
    priority: int = 5
    status: str = Field(default="open", max_length=40)
    visibility: str = Field(default="silent", max_length=40)
    ttl_seconds: int | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ResolveRequest(BaseModel):
    note: str = Field(default="", max_length=1000)


class VoiceCorrectionRequest(BaseModel):
    expected_text: str = Field(min_length=1, max_length=1000)
    heard_text: str = Field(default="", max_length=1000)


class VoiceSampleRequest(BaseModel):
    heard_text: str = Field(min_length=1, max_length=1000)
    expected_text: str = Field(default="", max_length=1000)
    backend: str = Field(default="browser-web-speech", max_length=80)
    confidence: float | None = None
    accepted: bool = True


class PlaywrightInspectRequest(BaseModel):
    url: str = Field(min_length=1, max_length=2000)
    limit: int = 40


class PlaywrightRunRequest(BaseModel):
    url: str = Field(min_length=1, max_length=2000)
    steps: list[dict[str, Any]] = Field(default_factory=list)


class SelfUpdateProposalRequest(BaseModel):
    request: str = Field(min_length=1, max_length=4000)


class SelfUpdateApprovalRequest(BaseModel):
    confirmation: str = Field(min_length=1, max_length=500)


class SelfUpdateStageRequest(BaseModel):
    path: str = Field(min_length=1, max_length=1000)
    find_text: str = Field(default="", max_length=120000)
    replace_text: str = Field(default="", max_length=120000)
    summary: str = Field(default="", max_length=1000)


class SelfUpdateApplyRequest(BaseModel):
    confirmation: str = Field(min_length=1, max_length=500)
    run_tests: bool | None = None


class FinanceExpenseRequest(BaseModel):
    amount: float
    category: str = Field(default="general", max_length=120)
    merchant: str = Field(default="", max_length=200)
    notes: str = Field(default="", max_length=1000)
    currency: str = Field(default="NGN", max_length=20)


class FinanceBudgetRequest(BaseModel):
    category: str = Field(default="general", max_length=120)
    amount: float
    period: str = Field(default="monthly", max_length=80)
    currency: str = Field(default="NGN", max_length=20)
    notes: str = Field(default="", max_length=1000)


class FinanceSubscriptionRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    amount: float
    cadence: str = Field(default="monthly", max_length=80)
    next_due_at: str = Field(default="", max_length=200)
    currency: str = Field(default="NGN", max_length=20)
    notes: str = Field(default="", max_length=1000)


class PrivateMemoryIndexRequest(BaseModel):
    title: str = Field(default="", max_length=300)
    text: str = Field(default="", max_length=40000)
    path: str = Field(default="", max_length=1000)
    source: str = Field(default="dashboard", max_length=300)
    sensitive: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=1000)
    limit: int = 10
    include_sensitive: bool = False


class WebSearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=1000)
    limit: int = Field(default=5, ge=1, le=20)
    providers: str = Field(default="", max_length=200)
    use_cache: bool = True
    mode: str = Field(default="", max_length=40)


class SimulationRequest(BaseModel):
    kind: str = Field(default="", max_length=80)
    instruction: str = Field(min_length=1, max_length=4000)
    context: dict[str, Any] = Field(default_factory=dict)


class PrivacyVaultRequest(BaseModel):
    kind: str = Field(default="private", max_length=80)
    title: str = Field(min_length=1, max_length=300)
    content: str = Field(default="", max_length=10000)
    sensitivity: str = Field(default="private", max_length=40)
    tags: list[str] | str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ModelRouteRequest(BaseModel):
    task_type: str = Field(default="general", max_length=80)
    text: str = Field(default="", max_length=4000)
    online: bool = True


class SelfDebugReportRequest(BaseModel):
    source: str = Field(default="dashboard", max_length=120)
    summary: str = Field(min_length=1, max_length=2000)
    metadata: dict[str, Any] = Field(default_factory=dict)


class AndroidVoiceRequest(BaseModel):
    text: str = Field(min_length=1, max_length=2000)


class AndroidAppRegisterRequest(BaseModel):
    name: str = Field(default="Android companion", max_length=200)
    device_id: str = Field(default="", max_length=200)
    capabilities: list[str] = Field(default_factory=list)
    status: dict[str, Any] = Field(default_factory=dict)


class AndroidAppEventRequest(BaseModel):
    device_id: str = Field(default="", max_length=200)
    name: str = Field(default="", max_length=200)
    text: str = Field(default="", max_length=5000)
    payload: dict[str, Any] = Field(default_factory=dict)


class ToneAnalyzeRequest(BaseModel):
    text: str = Field(min_length=1, max_length=2000)


class CRMPersonRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    relationship: str = Field(default="", max_length=200)
    birthday: str = Field(default="", max_length=80)
    contact: str = Field(default="", max_length=300)
    notes: str = Field(default="", max_length=2000)
    tags: list[str] = Field(default_factory=list)


class CRMInteractionRequest(BaseModel):
    person_name: str = Field(min_length=1, max_length=200)
    summary: str = Field(min_length=1, max_length=3000)
    sentiment: str = Field(default="", max_length=120)
    follow_up_at: str = Field(default="", max_length=200)
    promise: str = Field(default="", max_length=1000)
    metadata: dict[str, Any] = Field(default_factory=dict)


class LearningTopicRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    goal: str = Field(default="", max_length=1000)
    level: str = Field(default="beginner", max_length=80)


class LearningCardRequest(BaseModel):
    topic: str = Field(default="general", max_length=200)
    prompt: str = Field(min_length=1, max_length=2000)
    answer: str = Field(min_length=1, max_length=4000)


class LearningAnswerRequest(BaseModel):
    user_answer: str = Field(default="", max_length=4000)
    correct: bool = False
    notes: str = Field(default="", max_length=1000)


class ResearchBriefingRequest(BaseModel):
    topic: str = Field(min_length=1, max_length=500)
    cadence: str = Field(default="daily", max_length=80)
    target_agent_id: str = Field(default="research_analyst", max_length=120)
    create_task: bool = False


class TimelineNoteRequest(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    details: str = Field(default="", max_length=4000)
    event_type: str = Field(default="note", max_length=80)
    metadata: dict[str, Any] = Field(default_factory=dict)


class SkillWorkflowRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=2000)
    agent_id: str = Field(default="jarvis", max_length=120)
    tags: list[str] = Field(default_factory=list)


class SkillWorkflowStepRequest(BaseModel):
    instruction: str = Field(min_length=1, max_length=2000)
    expected_result: str = Field(default="", max_length=2000)


class MemoryReviewResolveRequest(BaseModel):
    decision: str = Field(min_length=1, max_length=40)
    note: str = Field(default="", max_length=1000)


class AutopilotStartRequest(BaseModel):
    goal: str = Field(min_length=1, max_length=4000)
    sphere: str = Field(default="", max_length=80)
    root: str = Field(default="", max_length=1000)
    priority: int = Field(default=2, ge=0, le=9)


class PersonalityProfileRequest(BaseModel):
    profile: str = Field(min_length=1, max_length=80)
    reason: str = Field(default="dashboard", max_length=300)


class SkillRecordingStartRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class SkillRecordingStepRequest(BaseModel):
    narration: str = Field(min_length=1, max_length=4000)
    expected_result: str = Field(default="", max_length=2000)


class DocumentationBrainRequest(BaseModel):
    root: str = Field(default="", max_length=1000)


class PersonalSearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=1000)
    limit: int = Field(default=8, ge=1, le=50)


class TrustAssessmentRequest(BaseModel):
    instruction: str = Field(min_length=1, max_length=3000)
    domain: str = Field(default="general", max_length=100)


class DeploymentInspectRequest(BaseModel):
    target: str = Field(default="", max_length=1000)
    root: str = Field(default="", max_length=1000)


class PrivacyFirewallRequest(BaseModel):
    instruction: str = Field(min_length=1, max_length=3000)
    context: str = Field(default="", max_length=1000)


class MissionCreateRequest(BaseModel):
    goal: str = Field(min_length=1, max_length=4000)
    root: str = Field(default="", max_length=1000)
    mission_type: str = Field(default="", max_length=120)
    authority_mode: str = Field(default="approval_gated", max_length=80)
    deploy_policy: str = Field(default="approve_step", max_length=80)
    priority: int = Field(default=2, ge=0, le=20)
    metadata: dict[str, Any] = Field(default_factory=dict)


class MissionApprovalRequest(BaseModel):
    kind: str = Field(default="next_step", max_length=80)
    note: str = Field(default="", max_length=1000)


class QALabRunRequest(BaseModel):
    root: str = Field(default="", max_length=1000)
    mission_id: int | None = None
    run_tests: bool | None = None


class AppStateMemoryRequest(BaseModel):
    app: str = Field(min_length=1, max_length=120)
    element_label: str = Field(default="", max_length=300)
    action: str = Field(default="observe", max_length=120)
    outcome: str = Field(default="success", max_length=120)
    selector: str = Field(default="", max_length=500)
    context: str = Field(default="", max_length=1000)
    confidence: float = 0.7
    notes: str = Field(default="", max_length=2000)
    metadata: dict[str, Any] = Field(default_factory=dict)


class BrowserExtensionContextRequest(BaseModel):
    browser: str = Field(default="extension", max_length=80)
    url: str = Field(default="", max_length=2000)
    title: str = Field(default="", max_length=300)
    selected_text: str = Field(default="", max_length=5000)
    headings: list[Any] = Field(default_factory=list)
    buttons: list[Any] = Field(default_factory=list)
    links: list[Any] = Field(default_factory=list)
    inputs: list[Any] = Field(default_factory=list)
    landmarks: list[Any] = Field(default_factory=list)
    forms: list[Any] = Field(default_factory=list)
    performance: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class BrowserConsoleRequest(BaseModel):
    browser: str = Field(default="extension", max_length=80)
    url: str = Field(default="", max_length=2000)
    level: str = Field(default="log", max_length=40)
    message: str = Field(default="", max_length=5000)
    source: str = Field(default="console", max_length=200)
    metadata: dict[str, Any] = Field(default_factory=dict)


class BrowserActionRequest(BaseModel):
    action: str = Field(min_length=1, max_length=80)
    url: str = Field(default="", max_length=2000)
    selector: str = Field(default="", max_length=500)
    value: str = Field(default="", max_length=2000)
    reason: str = Field(default="", max_length=1000)
    metadata: dict[str, Any] = Field(default_factory=dict)


class BrowserActionCompleteRequest(BaseModel):
    status: str = Field(default="done", max_length=40)
    result: str = Field(default="", max_length=2000)


class ReleasePrepareRequest(BaseModel):
    root: str = Field(default="", max_length=1000)
    mission_id: int | None = None
    version: str = Field(default="", max_length=80)


class SemanticIndexRequest(BaseModel):
    path: str = Field(default="", max_length=1000)
    include_private: bool = False
    limit: int = Field(default=500, ge=1, le=5000)


class SemanticTextIndexRequest(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    text: str = Field(min_length=1, max_length=40000)
    source: str = Field(default="dashboard", max_length=500)
    kind: str = Field(default="note", max_length=80)
    sensitive: bool = False
    tags: str = Field(default="", max_length=500)


class SemanticSearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=1000)
    limit: int = Field(default=10, ge=1, le=50)
    include_sensitive: bool = False


class OperatingRhythmEnergyRequest(BaseModel):
    mood: str = Field(default="neutral", max_length=120)
    energy: int = Field(default=5, ge=1, le=10)
    focus: int = Field(default=5, ge=1, le=10)
    notes: str = Field(default="", max_length=1000)


class ErrorRadarWatchRequest(BaseModel):
    root: str = Field(default="", max_length=1000)
    sources: list[str] = Field(default_factory=list)


class DebuggerAnalyzeRequest(BaseModel):
    text: str = Field(default="", max_length=50000)
    path: str = Field(default="", max_length=1000)
    command: str = Field(default="", max_length=1000)
    root: str = Field(default="", max_length=1000)
    source: str = Field(default="dashboard", max_length=200)
    run_command: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


class CommandMemoryLearnRequest(BaseModel):
    heard_phrase: str = Field(min_length=1, max_length=500)
    canonical_command: str = Field(min_length=1, max_length=1000)
    notes: str = Field(default="", max_length=1000)


class CalendarEmailDraftRequest(BaseModel):
    to: str = Field(default="", max_length=300)
    subject: str = Field(default="", max_length=500)
    context: str = Field(default="", max_length=4000)
    intent: str = Field(default="", max_length=1000)


class AutonomousLearningRequest(BaseModel):
    goal: str = Field(default="", max_length=2000)
    create_tasks: bool = True


class ContinuityThreadRequest(BaseModel):
    topic: str = Field(min_length=1, max_length=300)
    summary: str = Field(min_length=1, max_length=2000)
    source: str = Field(default="dashboard", max_length=120)
    status: str = Field(default="open", max_length=40)
    priority: int = Field(default=3, ge=1, le=5)
    metadata: dict[str, Any] = Field(default_factory=dict)


class DeepAutopilotRequest(BaseModel):
    root: str = Field(default="", max_length=1000)
    run_tests: bool = False
    log_text: str = Field(default="", max_length=50000)
    prepare_fix: bool = False


class SilenceModeRequest(BaseModel):
    mode: str = Field(default="normal", max_length=80)
    reason: str = Field(default="dashboard", max_length=300)
    metadata: dict[str, Any] = Field(default_factory=dict)


class SkillEvolutionObserveRequest(BaseModel):
    signature: str = Field(min_length=1, max_length=500)
    description: str = Field(default="", max_length=1000)
    metadata: dict[str, Any] = Field(default_factory=dict)


class SafetyPreflightRequest(BaseModel):
    instruction: str = Field(default="", max_length=2000)
    path: str = Field(default="", max_length=1000)


class PhoneHandoffRequest(BaseModel):
    device_id: str = Field(default="", max_length=200)
    title: str = Field(min_length=1, max_length=300)
    payload: dict[str, Any] = Field(default_factory=dict)
    direction: str = Field(default="phone_to_pc", max_length=40)
    kind: str = Field(default="command", max_length=80)


class GraphConnectRequest(BaseModel):
    subject: str = Field(min_length=1, max_length=300)
    predicate: str = Field(default="RELATED_TO", max_length=80)
    object: str = Field(min_length=1, max_length=300)
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentSchedulerPlanRequest(BaseModel):
    mode: str = Field(default="auto", max_length=80)
    voice_active: bool = False
    apply: bool = False


class AgentSchedulerRetryRequest(BaseModel):
    limit: int = Field(default=3, ge=1, le=25)


class AgentSchedulerResearchRequest(BaseModel):
    topic: str = Field(default="", max_length=1000)
    priority: int = Field(default=9, ge=1, le=20)


class TestBuildMonitorRequest(BaseModel):
    root: str = Field(default="", max_length=1000)
    command: str = Field(default="", max_length=1000)
    kind: str = Field(default="auto", max_length=80)
    create_proof: bool = True


class ModelBenchmarkRequest(BaseModel):
    task_types: list[str] = Field(default_factory=list)
    run_live: bool = False


class DeploymentInspectRequest(BaseModel):
    target: str = Field(default="", max_length=2000)
    root: str = Field(default="", max_length=1000)
    create_proof: bool = True


class OsAutopilotSignalRequest(BaseModel):
    kind: str = Field(default="manual", max_length=120)
    summary: str = Field(default="", max_length=1000)
    metadata: dict[str, Any] = Field(default_factory=dict)


class VersionGuardianSnapshotRequest(BaseModel):
    paths: list[str] = Field(default_factory=list)
    label: str = Field(default="dashboard snapshot", max_length=200)
    mission_id: int | None = None


class VersionGuardianPreflightRequest(BaseModel):
    instruction: str = Field(default="", max_length=2000)
    paths: list[str] = Field(default_factory=list)


class VersionGuardianRollbackRequest(BaseModel):
    mission_id: int | None = None
    root: str = Field(default="", max_length=1000)
    notes: str = Field(default="", max_length=2000)


class AwarenessAnswerRequest(BaseModel):
    question: str = Field(default="what is happening right now", max_length=1000)
    force: bool = False


class FixLoopRunRequest(BaseModel):
    root: str = Field(default="", max_length=1000)
    command: str = Field(default="", max_length=1000)
    log_text: str = Field(default="", max_length=50000)
    source: str = Field(default="dashboard", max_length=120)
    run_tests: bool = True
    create_patch: bool = True


class FixLoopApprovalRequest(BaseModel):
    confirmation: str = Field(default="", max_length=300)


class BrowserNetworkEventRequest(BaseModel):
    browser: str = Field(default="extension", max_length=80)
    url: str = Field(default="", max_length=2000)
    event_type: str = Field(default="network", max_length=80)
    error: str = Field(default="", max_length=1000)
    status: str = Field(default="", max_length=80)
    method: str = Field(default="", max_length=20)
    type: str = Field(default="", max_length=80)
    tab_id: int | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class BrowserPageChangeRequest(BaseModel):
    browser: str = Field(default="extension", max_length=80)
    url: str = Field(default="", max_length=2000)
    summary: str = Field(default="Browser page changed.", max_length=1000)
    metadata: dict[str, Any] = Field(default_factory=dict)


class BrowserGuidanceRequest(BaseModel):
    question: str = Field(default="what should I click", max_length=1000)


class BrowserSafeFillRequest(BaseModel):
    selector: str = Field(min_length=1, max_length=500)
    value: str = Field(default="", max_length=2000)
    reason: str = Field(default="", max_length=1000)


class AppMasteryRequest(BaseModel):
    app: str = Field(min_length=1, max_length=120)
    instruction: str = Field(default="", max_length=4000)
    max_steps: int = 0


class LocalAiSearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=1000)
    limit: int = Field(default=10, ge=1, le=50)
    include_sensitive: bool = False


class LocalAiIndexRequest(BaseModel):
    paths: list[str] = Field(default_factory=list)
    include_private: bool = False
    limit: int = Field(default=500, ge=1, le=5000)


class CloudWorkerSubmitRequest(BaseModel):
    job_type: str = Field(default="research", max_length=80)
    title: str = Field(min_length=1, max_length=300)
    payload: dict[str, Any] = Field(default_factory=dict)
    prefer_cloud: bool = True


class AutonomyStartRequest(BaseModel):
    goal: str = Field(default="", max_length=4000)
    root: str = Field(default="", max_length=1000)
    max_steps: int = Field(default=5, ge=1, le=25)


class CertaintyRecordRequest(BaseModel):
    kind: str = Field(default="known", max_length=40)
    topic: str = Field(default="general", max_length=200)
    statement: str = Field(default="", max_length=4000)
    confidence: float = Field(default=0.75, ge=0.0, le=1.0)
    evidence: list[str] = Field(default_factory=list)
    source: str = Field(default="dashboard", max_length=120)
    stale_after: str = Field(default="", max_length=80)
    metadata: dict[str, Any] = Field(default_factory=dict)


class CertaintyQueryRequest(BaseModel):
    query: str = Field(default="", max_length=1000)
    kind: str = Field(default="", max_length=40)
    limit: int = Field(default=20, ge=1, le=100)


class VisionSkillPatternRequest(BaseModel):
    app: str = Field(default="", max_length=120)
    label: str = Field(default="", max_length=300)
    pattern_type: str = Field(default="ui_element", max_length=80)
    visual_cues: list[str] = Field(default_factory=list)
    dom_cues: list[str] = Field(default_factory=list)
    accessibility_cues: list[str] = Field(default_factory=list)
    meaning: str = Field(default="", max_length=1000)
    action_hint: str = Field(default="", max_length=1000)
    confidence: float = Field(default=0.7, ge=0.0, le=1.0)
    metadata: dict[str, Any] = Field(default_factory=dict)


class VisionSkillObserveRequest(BaseModel):
    app: str = Field(default="", max_length=120)
    context: dict[str, Any] = Field(default_factory=dict)


class VisionSkillRecognizeRequest(BaseModel):
    app: str = Field(default="", max_length=120)
    query: str = Field(default="", max_length=1000)
    limit: int = Field(default=10, ge=1, le=50)


class NotificationRankRequest(BaseModel):
    limit: int = Field(default=50, ge=1, le=200)


class ProjectMemoryProfileRequest(BaseModel):
    root: str = Field(default="", max_length=1000)
    refresh: bool = False


class ProjectMemoryNoteRequest(BaseModel):
    root: str = Field(default="", max_length=1000)
    kind: str = Field(default="note", max_length=80)
    title: str = Field(default="", max_length=300)
    content: str = Field(default="", max_length=8000)
    confidence: float = Field(default=0.75, ge=0.0, le=1.0)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ProjectMemorySearchRequest(BaseModel):
    root: str = Field(default="", max_length=1000)
    query: str = Field(default="", max_length=1000)
    limit: int = Field(default=20, ge=1, le=100)


class ProjectMemoryReferenceImageRequest(BaseModel):
    root: str = Field(default="", max_length=1000)
    title: str = Field(default="", max_length=300)
    note: str = Field(default="", max_length=2000)
    filename: str = Field(default="reference.png", max_length=300)
    content_type: str = Field(default="", max_length=120)
    data_url: str = Field(default="", max_length=20_000_000)
    base64: str = Field(default="", max_length=20_000_000)
    metadata: dict[str, Any] = Field(default_factory=dict)


class OperatorSkillRequest(BaseModel):
    app: str = Field(default="", max_length=120)
    instruction: str = Field(default="", max_length=4000)
    max_steps: int = Field(default=12, ge=1, le=50)
    root: str = Field(default="", max_length=1000)


class LearningRoadmapRequest(BaseModel):
    topic: str = Field(default="", max_length=300)
    goal: str = Field(default="", max_length=1000)
    weeks: int = Field(default=4, ge=1, le=52)


class PrivacyFirewallProRequest(BaseModel):
    instruction: str = Field(default="", max_length=4000)
    context: str = Field(default="", max_length=8000)
    paths: list[str] = Field(default_factory=list)
    purpose: str = Field(default="", max_length=1000)


class DeviceMeshCommandRequest(BaseModel):
    command_type: str = Field(default="handoff", max_length=80)
    title: str = Field(default="", max_length=300)
    source_device: str = Field(default="laptop", max_length=120)
    target_device: str = Field(default="laptop", max_length=120)
    payload: dict[str, Any] = Field(default_factory=dict)


class ReleaseEngineerRequest(BaseModel):
    root: str = Field(default="", max_length=1000)
    build_command: str = Field(default="", max_length=1000)
    target_url: str = Field(default="", max_length=2000)
    run_tests: bool = False


class DecisionMemoryRequest(BaseModel):
    category: str = Field(default="communication", max_length=120)
    preference: str = Field(default="", max_length=1000)
    threshold: str = Field(default="", max_length=500)
    evidence: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.75, ge=0.0, le=1.0)
    source: str = Field(default="dashboard", max_length=120)
    text: str = Field(default="", max_length=4000)
    metadata: dict[str, Any] = Field(default_factory=dict)


class DecisionQueryRequest(BaseModel):
    query: str = Field(default="", max_length=1000)
    category: str = Field(default="", max_length=120)
    context: str = Field(default="", max_length=4000)
    limit: int = Field(default=20, ge=1, le=100)


class SkillFailureRequest(BaseModel):
    skill: str = Field(default="", max_length=160)
    failure: str = Field(default="", max_length=2000)
    evidence: list[str] = Field(default_factory=list)
    context: dict[str, Any] = Field(default_factory=dict)


class WorkspaceCoachRequest(BaseModel):
    root: str = Field(default="", max_length=1000)
    log_text: str = Field(default="", max_length=12000)
    current_file: str = Field(default="", max_length=1000)
    run_tests: bool = False
    notify: bool = True


class MemoryDebateRequest(BaseModel):
    topic: str = Field(default="", max_length=1000)
    limit: int = Field(default=8, ge=1, le=50)


class FocusProtectionRequest(BaseModel):
    mode: str = Field(default="focus", max_length=80)
    reason: str = Field(default="", max_length=500)
    title: str = Field(default="", max_length=300)
    message: str = Field(default="", max_length=2000)
    severity: int = Field(default=2, ge=1, le=5)
    category: str = Field(default="general", max_length=120)
    explicit: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


class AppApprenticeshipStartRequest(BaseModel):
    app: str = Field(default="", max_length=120)
    workflow: str = Field(default="", max_length=300)
    goal: str = Field(default="", max_length=1000)
    metadata: dict[str, Any] = Field(default_factory=dict)


class AppApprenticeshipStepRequest(BaseModel):
    session_id: int = Field(default=0, ge=0)
    narration: str = Field(default="", max_length=1000)
    action: str = Field(default="", max_length=1000)
    observation: str = Field(default="", max_length=1000)
    selector: str = Field(default="", max_length=500)
    screenshot: str = Field(default="", max_length=1000)
    success: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)


class ProjectCtoRequest(BaseModel):
    root: str = Field(default="", max_length=1000)
    refresh: bool = True


class ConversationThreadRequest(BaseModel):
    title: str = Field(default="", max_length=300)
    summary: str = Field(default="", max_length=2000)
    blocker: str = Field(default="", max_length=1000)
    evidence: list[str] = Field(default_factory=list)
    source: str = Field(default="dashboard", max_length=120)
    metadata: dict[str, Any] = Field(default_factory=dict)


class LocalVoiceBrainRequest(BaseModel):
    heard: str = Field(default="", max_length=1000)
    expected: str = Field(default="", max_length=1000)
    alias: str = Field(default="", max_length=120)
    source: str = Field(default="dashboard", max_length=120)


class ProofReportRequest(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    changed: list[str] = Field(default_factory=list)
    tested: list[str] = Field(default_factory=list)
    failed: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    mission_id: int | None = None
    task_id: int | None = None
    confidence: float = 0.7
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentQualityRequest(BaseModel):
    agent_id: str = Field(default="", max_length=120)
    task_id: int | None = None
    task_type: str = Field(default="general", max_length=120)
    accuracy: float = Field(default=0.7, ge=0.0, le=1.0)
    usefulness: float = Field(default=0.7, ge=0.0, le=1.0)
    speed: float = Field(default=0.7, ge=0.0, le=1.0)
    evidence: float = Field(default=0.7, ge=0.0, le=1.0)
    mistakes: float = Field(default=0.0, ge=0.0, le=1.0)
    fixed_by_agent: str = Field(default="", max_length=120)
    notes: str = Field(default="", max_length=2000)
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentLifecycleRequest(BaseModel):
    agent_id: str = Field(default="", max_length=120)
    name: str = Field(default="", max_length=200)
    purpose: str = Field(default="", max_length=1000)
    keywords: list[str] | str = Field(default_factory=list)
    reason: str = Field(default="", max_length=1000)
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentCouncilRequest(BaseModel):
    question: str = Field(default="", max_length=3000)
    agent_ids: list[str] = Field(default_factory=list)
    context: str = Field(default="", max_length=8000)
    metadata: dict[str, Any] = Field(default_factory=dict)


class DoNotForgetRequest(BaseModel):
    content: str = Field(default="", max_length=4000)
    source: str = Field(default="dashboard", max_length=120)
    context: dict[str, Any] = Field(default_factory=dict)


class DevServerCopilotRequest(BaseModel):
    root: str = Field(default="", max_length=1000)
    log_text: str = Field(default="", max_length=12000)
    current_file: str = Field(default="", max_length=1000)
    source: str = Field(default="dashboard", max_length=120)


class CodeChangeSimulationRequest(BaseModel):
    instruction: str = Field(default="", max_length=4000)
    root: str = Field(default="", max_length=1000)
    metadata: dict[str, Any] = Field(default_factory=dict)


class RefactorPlanRequest(BaseModel):
    root: str = Field(default="", max_length=1000)
    focus: str = Field(default="", max_length=500)
    max_files: int = Field(default=80, ge=1, le=500)


class TasteEngineRequest(BaseModel):
    correction: str = Field(default="", max_length=2000)
    domain: str = Field(default="general", max_length=120)
    context: str = Field(default="", max_length=2000)
    evidence: list[str] = Field(default_factory=list)


class MemoryConstitutionRequest(BaseModel):
    kind: str = Field(default="", max_length=120)
    content: str = Field(default="", max_length=4000)
    sensitivity: str = Field(default="normal", max_length=80)
    mode: str = Field(default="ask", max_length=20)
    retention: str = Field(default="review", max_length=120)
    private: str = Field(default="maybe", max_length=20)
    description: str = Field(default="", max_length=1000)


class RealityCheckRequest(BaseModel):
    claim: str = Field(default="", max_length=3000)
    evidence: str = Field(default="", max_length=3000)
    tool_result: Any = None
    domain: str = Field(default="general", max_length=120)
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentSimulationRequest(BaseModel):
    goal: str = Field(default="", max_length=3000)
    agent_ids: list[str] = Field(default_factory=list)
    root: str = Field(default="", max_length=1000)
    risk_level: str = Field(default="medium", max_length=80)


class CommandGraphRequest(BaseModel):
    phrase: str = Field(default="", max_length=300)
    intent: str = Field(default="", max_length=300)
    steps: list[str] | str = Field(default_factory=list)
    confidence: float = Field(default=0.72, ge=0.0, le=1.0)
    metadata: dict[str, Any] = Field(default_factory=dict)


class EmotionalTimingRequest(BaseModel):
    text: str = Field(default="", max_length=2000)
    explicit_tone: str = Field(default="", max_length=120)


class VisualSkillMemoryRequest(BaseModel):
    app: str = Field(default="", max_length=120)
    screen_label: str = Field(default="", max_length=300)
    cues: list[str] | str = Field(default_factory=list)
    meaning: str = Field(default="", max_length=1000)
    action_hint: str = Field(default="", max_length=1000)
    source: str = Field(default="dashboard", max_length=120)
    query: str = Field(default="", max_length=1000)
    limit: int = Field(default=10, ge=1, le=100)


class FailureAutopsyRequest(BaseModel):
    title: str = Field(default="", max_length=300)
    what_happened: str = Field(default="", max_length=3000)
    root_cause: str = Field(default="", max_length=1500)
    next_time: str = Field(default="", max_length=1500)
    evidence: list[str] | str = Field(default_factory=list)
    code_change_needed: bool = False
    source: str = Field(default="dashboard", max_length=120)
    metadata: dict[str, Any] = Field(default_factory=dict)


def create_app() -> FastAPI:
    app = FastAPI(title="Friday v2 Local API", version="0.2.0")
    origins = _cors_origins()
    if origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
    from api.routers import register_domain_routers

    register_domain_routers(app, sys.modules[__name__])

    @app.get("/desktop/tasks")
    def list_desktop_tasks(limit: int = 20, _user: str = Depends(require_user)) -> list[dict[str, Any]]:
        return [_decorate_desktop_session(session) for session in desktop_tasks.list_sessions(limit=max(1, min(int(limit), 100)))]

    @app.post("/desktop/tasks")
    def create_desktop_task(request: DesktopTaskCreateRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        max_steps = max(1, min(50, int(request.max_steps or config_value("desktop_task_max_steps", 5))))
        session_id = desktop_tasks.create_session(request.instruction, max_steps=max_steps)
        _start_desktop_task_thread(session_id, request.instruction, max_steps)
        session = desktop_tasks.get_session(session_id, include_steps=True)
        payload = _decorate_desktop_session(session, include_steps=True) if session else {"id": session_id}
        payload["reply"] = f"Desktop task #{session_id} started."
        return payload

    @app.get("/desktop/tasks/{session_id}")
    def get_desktop_task(session_id: int, _user: str = Depends(require_user)) -> dict[str, Any]:
        session = desktop_tasks.get_session(session_id, include_steps=True)
        if not session:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Desktop task not found.")
        return _decorate_desktop_session(session, include_steps=True)

    @app.post("/desktop/tasks/{session_id}/pause")
    def pause_desktop_task(session_id: int, _user: str = Depends(require_user)) -> dict[str, Any]:
        reply = desktop_vision.pause_desktop_task(session_id)
        return _desktop_task_action_payload(session_id, reply)

    @app.post("/desktop/tasks/{session_id}/resume")
    def resume_desktop_task(session_id: int, _user: str = Depends(require_user)) -> dict[str, Any]:
        reply = desktop_vision.resume_desktop_task(session_id)
        return _desktop_task_action_payload(session_id, reply)

    @app.post("/desktop/tasks/{session_id}/confirm")
    def confirm_desktop_task(session_id: int, _user: str = Depends(require_user)) -> dict[str, Any]:
        reply = desktop_vision.confirm_desktop_task(session_id)
        return _desktop_task_action_payload(session_id, reply)

    @app.post("/desktop/tasks/{session_id}/cancel")
    def cancel_desktop_task(session_id: int, _user: str = Depends(require_user)) -> dict[str, Any]:
        reply = desktop_vision.cancel_desktop_task(session_id)
        return _desktop_task_action_payload(session_id, reply)

    @app.get("/desktop/screenshots/{filename}")
    def desktop_screenshot(
        filename: str,
        token: str = "",
        authorization: str = Header(default=""),
    ) -> FileResponse:
        _require_user_from_header_or_token(authorization, token)
        path = _safe_screenshot_path(filename)
        if not path.exists() or not path.is_file():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Screenshot not found.")
        return FileResponse(str(path))

    @app.get("/vision/monitor")
    def vision_monitor_status(_user: str = Depends(require_user)) -> dict[str, Any]:
        return _decorate_visual_status(visual_monitor.status())

    @app.post("/vision/monitor/start")
    def vision_monitor_start(request: VisionMonitorRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return _decorate_visual_status(visual_monitor.start_monitor(request.source, realtime=request.realtime))

    @app.post("/vision/monitor/stop")
    def vision_monitor_stop(_user: str = Depends(require_user)) -> dict[str, Any]:
        return _decorate_visual_status(visual_monitor.stop_monitor())

    @app.post("/vision/monitor/capture")
    def vision_monitor_capture(request: VisionMonitorRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        events = visual_monitor.capture_once(request.source, analyze=request.analyze)
        return {"events": [_decorate_visual_event(event) for event in events], "status": _decorate_visual_status(visual_monitor.status())}

    @app.get("/vision/events")
    def vision_events(limit: int = 20, source: str = "", _user: str = Depends(require_user)) -> list[dict[str, Any]]:
        return [
            _decorate_visual_event(event)
            for event in visual_monitor.recent_events(limit=max(1, min(int(limit), 100)), source=source.strip().lower())
        ]

    @app.get("/vision/frames/{source}/{filename}")
    def vision_frame(
        source: str,
        filename: str,
        token: str = "",
        authorization: str = Header(default=""),
    ) -> FileResponse:
        _require_user_from_header_or_token(authorization, token)
        path = _safe_visual_frame_path(source, filename)
        if not path.exists() or not path.is_file():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Visual frame not found.")
        return FileResponse(str(path))

    @app.get("/vision/live/{source}")
    def vision_live_stream(
        source: str,
        token: str = "",
        authorization: str = Header(default=""),
    ) -> StreamingResponse:
        _require_user_from_header_or_token(authorization, token)
        if source not in {"screen", "camera", "both"}:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Visual source not found.")
        live_source = "screen" if source == "both" else source
        return StreamingResponse(
            visual_monitor.mjpeg_stream(live_source),
            media_type="multipart/x-mixed-replace; boundary=frame",
            headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
        )

    @app.get("/pc/awareness")
    def pc_awareness_snapshot(_user: str = Depends(require_user)) -> dict[str, Any]:
        return pc_awareness.snapshot()

    @app.post("/pc/awareness/refresh")
    def pc_awareness_refresh(_user: str = Depends(require_user)) -> dict[str, Any]:
        return pc_awareness.refresh()

    @app.get("/pc/apps/running")
    def pc_running_apps(limit: int = 80, _user: str = Depends(require_user)) -> list[dict[str, Any]]:
        return pc_awareness.running_apps(limit=limit)

    @app.get("/pc/apps/installed")
    def pc_installed_apps(limit: int = 200, _user: str = Depends(require_user)) -> list[dict[str, Any]]:
        return pc_awareness.installed_apps(limit=limit)

    @app.get("/pc/apps/desktop")
    def pc_desktop_apps(limit: int = 200, _user: str = Depends(require_user)) -> list[dict[str, Any]]:
        return pc_awareness.desktop_apps(limit=limit)

    @app.get("/pc/apps/find")
    def pc_find_app(query: str, _user: str = Depends(require_user)) -> dict[str, Any]:
        return pc_awareness.find_app(query)

    @app.get("/phone/status")
    def phone_status(_user: str = Depends(require_user)) -> dict[str, Any]:
        return phone_bridge.status()

    @app.get("/phone/devices")
    def phone_devices(_user: str = Depends(require_user)) -> list[dict[str, Any]]:
        return phone_bridge.list_devices()

    @app.post("/phone/devices")
    def phone_register(request: PhoneRegisterRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return phone_bridge.register_device(
            request.name,
            adb_serial=request.adb_serial,
            ntfy_topic=request.ntfy_topic,
            phone_number=request.phone_number,
            is_default=request.is_default,
        )

    @app.get("/phone/battery")
    def phone_battery(_user: str = Depends(require_user)) -> dict[str, Any]:
        return phone_bridge.battery_status()

    @app.post("/phone/notify")
    def phone_notify(request: PhoneNotifyRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return phone_bridge.send_notification(request.title, request.message, priority=request.priority, tags=request.tags)

    @app.post("/phone/ring")
    def phone_ring(request: PhoneRingRequest | None = Body(default=None), _user: str = Depends(require_user)) -> dict[str, Any]:
        message = request.message if request else ""
        return phone_bridge.ring_phone(message)

    @app.post("/phone/open-url")
    def phone_open_url(request: PhoneUrlRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return phone_bridge.open_url(request.url)

    @app.post("/phone/dial")
    def phone_dial(request: PhoneDialRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        if request.contact:
            return phone_bridge.call_contact(request.contact, direct=request.direct)
        return phone_bridge.dial_number(request.number, direct=request.direct)

    @app.post("/phone/sms-draft")
    def phone_sms_draft(request: PhoneSmsRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return phone_bridge.sms_draft(request.number, request.message)

    @app.post("/phone/files/push")
    def phone_push_file(request: PhoneFileRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return phone_bridge.push_file_to_phone(request.local_path, request.phone_path)

    @app.post("/phone/files/pull")
    def phone_pull_file(request: PhoneFileRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return phone_bridge.pull_file_from_phone(request.phone_path, request.local_dir)

    @app.post("/phone/clipboard")
    def phone_clipboard(request: PhoneClipboardRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return phone_bridge.set_clipboard(request.text)

    @app.post("/phone/photos/import")
    def phone_import_photos(request: PhoneFileRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return phone_bridge.import_photos(request.local_dir, limit=request.limit)

    @app.get("/phone/events")
    def phone_events(limit: int = 20, _user: str = Depends(require_user)) -> list[dict[str, Any]]:
        return phone_bridge.recent_events(limit=limit)

    @app.get("/capabilities/overview")
    def capabilities_overview(_user: str = Depends(require_user)) -> dict[str, Any]:
        return capability_center.overview()

    @app.get("/home/status")
    def home_status(_user: str = Depends(require_user)) -> dict[str, Any]:
        return capability_center.home_status()

    @app.post("/home/devices/control")
    def home_device_control(request: HomeDeviceControlRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return capability_center.control_smart_device(request.name, request.action, params=request.params)

    @app.get("/home/router")
    def home_router(_user: str = Depends(require_user)) -> dict[str, Any]:
        return capability_center.router_status()

    @app.get("/home/network/devices")
    def home_network_devices(limit: int = 80, _user: str = Depends(require_user)) -> list[dict[str, Any]]:
        return capability_center.local_network_devices(limit=limit)

    @app.get("/home/printers")
    def home_printers(_user: str = Depends(require_user)) -> list[dict[str, Any]]:
        return capability_center.list_printers()

    @app.get("/home/bluetooth")
    def home_bluetooth(_user: str = Depends(require_user)) -> list[dict[str, Any]]:
        return capability_center.list_bluetooth_devices()

    @app.get("/home/connection-quality")
    def home_connection_quality(host: str = "1.1.1.1", _user: str = Depends(require_user)) -> dict[str, Any]:
        return capability_center.connection_quality(host)

    @app.get("/personal/daily-brief")
    def personal_daily_brief(_user: str = Depends(require_user)) -> dict[str, Any]:
        return capability_center.personal_brief()

    @app.get("/personal/next-action")
    def personal_next_action(_user: str = Depends(require_user)) -> dict[str, Any]:
        return capability_center.personal_next_action()

    @app.get("/personal/plan-day")
    def personal_plan_day(_user: str = Depends(require_user)) -> dict[str, Any]:
        return capability_center.plan_day()

    @app.get("/personal/os/plan")
    def personal_os_plan(_user: str = Depends(require_user)) -> dict[str, Any]:
        return personal_life_os.daily_plan()

    @app.get("/personal/os/next")
    def personal_os_next(_user: str = Depends(require_user)) -> dict[str, Any]:
        return personal_life_os.what_should_i_do_next()

    @app.get("/personal/os/end-of-day")
    def personal_os_end_of_day(_user: str = Depends(require_user)) -> dict[str, Any]:
        return personal_life_os.end_of_day_summary()

    @app.post("/personal/os/routines")
    def personal_os_create_routine(request: RoutineRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return personal_life_os.create_routine(request.title, cadence=request.cadence, next_due_at=request.next_due_at, notes=request.notes)

    @app.get("/personal/os/routines/due")
    def personal_os_due_routines(limit: int = 20, _user: str = Depends(require_user)) -> list[dict[str, Any]]:
        return personal_life_os.due_routines(limit=limit)

    @app.post("/personal/os/routines/{routine_id}/complete")
    def personal_os_complete_routine(routine_id: int, _user: str = Depends(require_user)) -> dict[str, Any]:
        routine = personal_life_os.complete_routine(routine_id)
        if not routine:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Routine not found.")
        return routine

    @app.post("/personal/os/mood")
    def personal_os_mood(request: MoodRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return personal_life_os.set_mood(request.mood, energy=request.energy, notes=request.notes)

    @app.get("/home-assistant/status")
    def home_assistant_status(_user: str = Depends(require_user)) -> dict[str, Any]:
        return home_assistant.status()

    @app.get("/home-assistant/states")
    def home_assistant_states(_user: str = Depends(require_user)) -> dict[str, Any]:
        return home_assistant.list_states()

    @app.post("/home-assistant/service")
    def home_assistant_service(request: HomeAssistantServiceRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return home_assistant.call_service(request.domain, request.service, request.data)

    @app.post("/home-assistant/focus-mode")
    def home_assistant_focus(on: bool = True, _user: str = Depends(require_user)) -> dict[str, Any]:
        return home_assistant.focus_mode(on=on)

    @app.post("/workspace/project-map")
    def workspace_project_map(request: CapabilityRootRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return capability_center.workspace_project_map(request.root)

    @app.post("/workspace/dependency-health")
    def workspace_dependency_health(request: CapabilityRootRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return capability_center.workspace_dependency_health(request.root)

    @app.post("/workspace/auto-docs")
    def workspace_auto_docs(request: CapabilityRootRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return capability_center.workspace_auto_docs(request.root)

    @app.post("/workspace/test-watch")
    def workspace_test_watch(request: TestWatchRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return capability_center.test_failure_watcher(request.command)

    @app.get("/maintenance/report")
    def maintenance_report(light: bool = False, _user: str = Depends(require_user)) -> dict[str, Any]:
        return capability_center.maintenance_report(light=light)

    @app.get("/security/overview")
    def security_overview(light: bool = False, _user: str = Depends(require_user)) -> dict[str, Any]:
        return capability_center.security_overview(light=light)

    @app.get("/security/scopes")
    def security_scopes(limit: int = 50, _user: str = Depends(require_user)) -> list[dict[str, Any]]:
        return capability_center.list_security_scopes(limit=limit)

    @app.post("/security/scopes")
    def security_create_scope(request: SecurityScopeRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return capability_center.create_security_scope(request.target, kind=request.kind, proof=request.proof)

    @app.post("/security/scopes/{scope_id}/verify")
    def security_verify_scope(scope_id: int, request: SecurityVerifyRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return capability_center.verify_security_scope(scope_id, proof_url=request.proof_url)

    @app.post("/security/open-ports")
    def security_open_ports(request: PortScanRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return capability_center.scan_open_ports(request.target, ports=request.ports or None)

    @app.post("/security/dependency-scan")
    def security_dependency_scan(request: CapabilityRootRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return capability_center.dependency_security_scan(request.root)

    @app.post("/security/web-headers")
    def security_web_headers(request: PortScanRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return capability_center.web_security_headers(request.target)

    @app.post("/security/secret-scan")
    def security_secret_scan(request: CapabilityRootRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return capability_center.project_secret_scan(request.root)

    @app.post("/security/report")
    def security_report(request: PortScanRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return capability_center.generate_security_report(request.target)

    @app.post("/security/hardening-plan")
    def security_hardening_plan(request: CapabilityRootRequest, target: str = "", _user: str = Depends(require_user)) -> dict[str, Any]:
        return capability_center.hardening_plan(target, root=request.root)

    @app.get("/automation/recipes")
    def automation_recipes(limit: int = 50, _user: str = Depends(require_user)) -> list[dict[str, Any]]:
        return capability_center.list_recipes(limit=limit)

    @app.post("/automation/recipes")
    def automation_create_recipe(request: AutomationRecipeRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return capability_center.create_recipe(request.name, request.trigger_type, request.trigger, request.action_type, request.action, enabled=request.enabled)

    @app.post("/automation/recipes/{recipe_id}/run")
    def automation_run_recipe(recipe_id: int, _user: str = Depends(require_user)) -> dict[str, Any]:
        return capability_center.run_recipe(recipe_id)

    @app.get("/capabilities/events")
    def capability_events(limit: int = 30, area: str = "", _user: str = Depends(require_user)) -> list[dict[str, Any]]:
        return capability_center.recent_events(limit=limit, area=area)

    @app.get("/guardian/status")
    def guardian_status(_user: str = Depends(require_user)) -> dict[str, Any]:
        return proactive_guardian.status()

    @app.post("/guardian/scan")
    def guardian_scan(light: bool = True, _user: str = Depends(require_user)) -> dict[str, Any]:
        return proactive_guardian.run_scan(light=light)

    @app.get("/guardian/runs")
    def guardian_runs(limit: int = 20, _user: str = Depends(require_user)) -> list[dict[str, Any]]:
        return proactive_guardian.recent_runs(limit=limit)

    @app.get("/events/status")
    def events_status(_user: str = Depends(require_user)) -> dict[str, Any]:
        return event_nervous_system.status()

    @app.get("/events")
    def events_recent(limit: int = 50, event_type: str = "", status_filter: str = "", _user: str = Depends(require_user)) -> list[dict[str, Any]]:
        return event_nervous_system.recent_events(limit=limit, event_type=event_type, status=status_filter)

    @app.post("/events/run-once")
    def events_run_once(_user: str = Depends(require_user)) -> dict[str, Any]:
        return event_nervous_system.run_once()

    @app.get("/barge-in/status")
    def barge_in_status(_user: str = Depends(require_user)) -> dict[str, Any]:
        return barge_in.status()

    @app.post("/barge-in/stop")
    def barge_in_stop(_user: str = Depends(require_user)) -> dict[str, Any]:
        return barge_in.request_stop("dashboard stop")

    @app.get("/daily-companion/status")
    def daily_companion_status(_user: str = Depends(require_user)) -> dict[str, Any]:
        return daily_companion.status()

    @app.post("/daily-companion/brief")
    def daily_companion_brief(_user: str = Depends(require_user)) -> dict[str, Any]:
        return daily_companion.morning_brief()

    @app.post("/daily-companion/check-in")
    def daily_companion_check_in(_user: str = Depends(require_user)) -> dict[str, Any]:
        return daily_companion.check_in()

    @app.get("/skills/marketplace")
    def skills_marketplace(_user: str = Depends(require_user)) -> dict[str, Any]:
        return skill_marketplace.catalog()

    @app.post("/skills/marketplace/install")
    def skills_marketplace_install(request: SkillInstallRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return skill_marketplace.install(request.key)

    @app.get("/finance/summary")
    def finance_summary(_user: str = Depends(require_user)) -> dict[str, Any]:
        return personal_finance.summary()

    @app.get("/finance/expenses")
    def finance_expenses(category: str = "", limit: int = 50, _user: str = Depends(require_user)) -> list[dict[str, Any]]:
        return personal_finance.list_expenses(category=category, limit=limit)

    @app.post("/finance/expenses")
    def finance_add_expense(request: FinanceExpenseRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return personal_finance.add_expense(request.amount, category=request.category, merchant=request.merchant, notes=request.notes, currency=request.currency)

    @app.get("/finance/budgets")
    def finance_budgets(_user: str = Depends(require_user)) -> list[dict[str, Any]]:
        return personal_finance.list_budgets()

    @app.post("/finance/budgets")
    def finance_set_budget(request: FinanceBudgetRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return personal_finance.set_budget(request.category, request.amount, period=request.period, currency=request.currency, notes=request.notes)

    @app.post("/finance/can-afford")
    def finance_can_afford(request: FinanceExpenseRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return personal_finance.can_i_afford(request.amount, category=request.category, currency=request.currency)

    @app.get("/finance/subscriptions")
    def finance_subscriptions(_user: str = Depends(require_user)) -> list[dict[str, Any]]:
        return personal_finance.list_subscriptions()

    @app.post("/finance/subscriptions")
    def finance_add_subscription(request: FinanceSubscriptionRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return personal_finance.add_subscription(request.name, request.amount, cadence=request.cadence, next_due_at=request.next_due_at, currency=request.currency, notes=request.notes)

    @app.get("/private-memory/summary")
    def private_memory_summary(_user: str = Depends(require_user)) -> dict[str, Any]:
        return private_embedding_memory.summary()

    @app.post("/private-memory/index")
    def private_memory_index(request: PrivateMemoryIndexRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        if request.path:
            return private_embedding_memory.index_file(request.path, sensitive=request.sensitive)
        return private_embedding_memory.index_text(request.title or "Private note", request.text, source=request.source, metadata=request.metadata, sensitive=request.sensitive)

    @app.post("/private-memory/search")
    def private_memory_search(request: SearchRequest, _user: str = Depends(require_user)) -> list[dict[str, Any]]:
        return private_embedding_memory.search(request.query, limit=request.limit, include_sensitive=request.include_sensitive)

    @app.get("/android-companion/status")
    def android_companion_status(_user: str = Depends(require_user)) -> dict[str, Any]:
        return android_companion.status()

    @app.get("/android/device-mesh")
    def android_device_mesh(_user: str = Depends(require_user)) -> dict[str, Any]:
        return _android_device_mesh_dashboard()

    @app.post("/android/device-mesh/sync")
    def android_device_mesh_sync(_user: str = Depends(require_user)) -> dict[str, Any]:
        sync = android_companion.force_global_sync()
        _invalidate_dashboard_snapshot_cache()
        return _android_device_mesh_dashboard(sync=sync)

    @app.post("/android-companion/voice")
    def android_companion_voice(request: AndroidVoiceRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return android_companion.voice_to_friday(request.text)

    @app.post("/android-companion/app/register")
    def android_app_register(request: AndroidAppRegisterRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return android_companion.register_app_device(request.name, request.device_id, capabilities=request.capabilities, status_payload=request.status or request.model_dump())

    @app.get("/android-companion/app/devices")
    def android_app_devices(limit: int = 20, _user: str = Depends(require_user)) -> list[dict[str, Any]]:
        return android_companion.list_app_devices(limit=limit)

    @app.post("/android-companion/app/status")
    def android_app_status(request: AndroidAppEventRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        payload = request.payload or request.model_dump()
        return android_companion.ingest_app_status(request.device_id, payload)

    @app.post("/android-companion/app/notification")
    def android_app_notification(request: AndroidAppEventRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        payload = request.payload or request.model_dump()
        return android_companion.ingest_notification(request.device_id, payload)

    @app.post("/android-companion/app/clipboard")
    def android_app_clipboard(request: AndroidAppEventRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return android_companion.ingest_clipboard(request.device_id, request.text or str((request.payload or {}).get("text") or ""))

    @app.post("/android-companion/app/location")
    def android_app_location(request: AndroidAppEventRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        payload = request.payload or request.model_dump()
        return android_companion.ingest_location(request.device_id, payload)

    @app.post("/android-companion/app/file")
    def android_app_file(request: AndroidAppEventRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        payload = request.payload or request.model_dump()
        return android_companion.ingest_file_event(request.device_id, payload)

    @app.post("/android-companion/app/camera-frame")
    def android_app_camera_frame(request: AndroidAppEventRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        payload = request.payload or request.model_dump()
        return android_companion.ingest_camera_frame(request.device_id, payload)

    @app.get("/project-watchdog/status")
    def project_watchdog_status(_user: str = Depends(require_user)) -> dict[str, Any]:
        return project_watchdog.status()

    @app.post("/project-watchdog/run")
    def project_watchdog_run(request: CapabilityRootRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return project_watchdog.run_once(request.root)

    @app.get("/project-watchdog/reports")
    def project_watchdog_reports(limit: int = 20, _user: str = Depends(require_user)) -> list[dict[str, Any]]:
        return project_watchdog.recent_reports(limit=limit)

    @app.get("/codebase-standards/status")
    def codebase_standards_status(_user: str = Depends(require_user)) -> dict[str, Any]:
        return codebase_standards.status()

    @app.get("/codebase-standards/rules")
    def codebase_standards_rules(_user: str = Depends(require_user)) -> dict[str, Any]:
        return codebase_standards.standards()

    @app.post("/codebase-standards/scan")
    def codebase_standards_scan(request: CodebaseStandardsScanRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return codebase_standards.scan(request.root, focus=request.focus, max_files=request.max_files)

    @app.get("/codebase-standards/reports")
    def codebase_standards_reports(limit: int = 20, _user: str = Depends(require_user)) -> list[dict[str, Any]]:
        return codebase_standards.recent(limit=limit)

    @app.post("/sandbox/simulate")
    def sandbox_simulate(request: SimulationRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return sandbox_simulation.simulate_action(request.kind, request.instruction, context=request.context)

    @app.get("/sandbox/simulations")
    def sandbox_simulations(limit: int = 20, _user: str = Depends(require_user)) -> list[dict[str, Any]]:
        return sandbox_simulation.list_simulations(limit=limit)

    @app.get("/privacy-vault/summary")
    def privacy_vault_summary(_user: str = Depends(require_user)) -> dict[str, Any]:
        return privacy_vault.summary()

    @app.get("/privacy-vault/items")
    def privacy_vault_items(kind: str = "", limit: int = 50, _user: str = Depends(require_user)) -> list[dict[str, Any]]:
        return privacy_vault.list_items(kind=kind, limit=limit)

    @app.post("/privacy-vault/items")
    def privacy_vault_store(request: PrivacyVaultRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return privacy_vault.store_item(request.kind, request.title, request.content, sensitivity=request.sensitivity, tags=request.tags, metadata=request.metadata)

    @app.get("/privacy-vault/items/{item_id}")
    def privacy_vault_get(item_id: int, reveal: bool = False, _user: str = Depends(require_user)) -> dict[str, Any]:
        item = privacy_vault.get_item(item_id, reveal=reveal)
        if not item:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Privacy item not found.")
        return item

    @app.get("/model-router/summary")
    def model_router_summary(_user: str = Depends(require_user)) -> dict[str, Any]:
        return model_router_brain.summary()

    @app.post("/model-router/choose")
    def model_router_choose(request: ModelRouteRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return model_router_brain.choose_provider(request.task_type, request.text, online=request.online)

    @app.get("/self-debugger/reports")
    def self_debugger_reports(limit: int = 20, _user: str = Depends(require_user)) -> list[dict[str, Any]]:
        return self_debugger.recent_reports(limit=limit)

    @app.post("/self-debugger/report")
    def self_debugger_report(request: SelfDebugReportRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return self_debugger.record_failure(request.source, request.summary, metadata=request.metadata)

    @app.post("/self-debugger/propose-fix")
    def self_debugger_propose_fix(report_id: int = 0, _user: str = Depends(require_user)) -> dict[str, Any]:
        return self_debugger.create_fix_proposal(report_id)

    @app.get("/autonomous-debugger/status")
    def autonomous_debugger_status(_user: str = Depends(require_user)) -> dict[str, Any]:
        return autonomous_debugger.status()

    @app.get("/autonomous-debugger/reports")
    def autonomous_debugger_reports(limit: int = 20, _user: str = Depends(require_user)) -> list[dict[str, Any]]:
        return autonomous_debugger.recent(limit=limit)

    @app.post("/autonomous-debugger/analyze")
    def autonomous_debugger_analyze(request: DebuggerAnalyzeRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        if request.run_command or request.command:
            return autonomous_debugger.run_check(request.command, cwd=request.root)
        if request.path:
            return autonomous_debugger.analyze_file(request.path)
        return autonomous_debugger.analyze_text(request.text, source=request.source, metadata=request.metadata)

    @app.post("/autonomous-debugger/watch")
    def autonomous_debugger_watch(request: CapabilityRootRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return autonomous_debugger.watch(request.root)

    @app.get("/emotion/status")
    def emotion_status(_user: str = Depends(require_user)) -> dict[str, Any]:
        return emotion_tone.summary()

    @app.post("/emotion/analyze")
    def emotion_analyze(request: ToneAnalyzeRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return emotion_tone.analyze_text(request.text)

    @app.get("/emotion/events")
    def emotion_events(limit: int = 30, _user: str = Depends(require_user)) -> list[dict[str, Any]]:
        return emotion_tone.recent(limit=limit)

    @app.get("/crm/summary")
    def crm_summary(_user: str = Depends(require_user)) -> dict[str, Any]:
        return personal_crm.summary()

    @app.get("/crm/people")
    def crm_people(query: str = "", limit: int = 50, _user: str = Depends(require_user)) -> list[dict[str, Any]]:
        return personal_crm.search_people(query, limit=limit)

    @app.post("/crm/people")
    def crm_remember_person(request: CRMPersonRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return personal_crm.remember_person(request.name, relationship=request.relationship, birthday=request.birthday, contact=request.contact, notes=request.notes, tags=request.tags)

    @app.get("/crm/interactions")
    def crm_interactions(person: str = "", limit: int = 50, _user: str = Depends(require_user)) -> list[dict[str, Any]]:
        return personal_crm.recent_interactions(person, limit=limit)

    @app.post("/crm/interactions")
    def crm_record_interaction(request: CRMInteractionRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return personal_crm.record_interaction(request.person_name, request.summary, sentiment=request.sentiment, follow_up_at=request.follow_up_at, promise=request.promise, metadata=request.metadata)

    @app.get("/crm/followups")
    def crm_followups(limit: int = 50, _user: str = Depends(require_user)) -> list[dict[str, Any]]:
        return personal_crm.upcoming_followups(limit=limit)

    @app.get("/learning-coach/progress")
    def learning_progress(_user: str = Depends(require_user)) -> dict[str, Any]:
        return learning_coach.progress()

    @app.post("/learning-coach/topics")
    def learning_topic(request: LearningTopicRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return learning_coach.create_topic(request.name, goal=request.goal, level=request.level)

    @app.post("/learning-coach/cards")
    def learning_card(request: LearningCardRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return learning_coach.add_card(request.topic, request.prompt, request.answer)

    @app.get("/learning-coach/quiz")
    def learning_quiz(topic: str = "", limit: int = 3, _user: str = Depends(require_user)) -> dict[str, Any]:
        return learning_coach.quiz(topic=topic, limit=limit)

    @app.post("/learning-coach/cards/{card_id}/answer")
    def learning_answer(card_id: int, request: LearningAnswerRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return learning_coach.record_answer(card_id, request.user_answer, correct=request.correct, notes=request.notes)

    @app.get("/research-briefings/summary")
    def research_briefings_summary(_user: str = Depends(require_user)) -> dict[str, Any]:
        return research_briefings.summary()

    @app.get("/research-briefings/topics")
    def research_briefing_topics(limit: int = 50, _user: str = Depends(require_user)) -> list[dict[str, Any]]:
        return research_briefings.topics(limit=limit)

    @app.post("/research-briefings/topics")
    def research_briefing_subscribe(request: ResearchBriefingRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return research_briefings.subscribe(request.topic, cadence=request.cadence, target_agent_id=request.target_agent_id)

    @app.post("/research-briefings/generate")
    def research_briefing_generate(request: ResearchBriefingRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return research_briefings.generate(request.topic, create_task=request.create_task)

    @app.get("/research-briefings/recent")
    def research_briefings_recent(limit: int = 20, topic: str = "", _user: str = Depends(require_user)) -> list[dict[str, Any]]:
        return research_briefings.recent(limit=limit, topic=topic)

    @app.get("/workspace-context/status")
    def workspace_context_status(_user: str = Depends(require_user)) -> dict[str, Any]:
        return contextual_workspace.summary()

    @app.post("/workspace-context/prepare")
    def workspace_context_prepare(request: CapabilityRootRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return contextual_workspace.prepare_context(request.root)

    @app.get("/offline-survival/status")
    def offline_survival_status(_user: str = Depends(require_user)) -> dict[str, Any]:
        return offline_survival.status()

    @app.post("/offline-survival/activate")
    def offline_survival_activate(reason: str = "dashboard", _user: str = Depends(require_user)) -> dict[str, Any]:
        return offline_survival.activate(reason)

    @app.post("/offline-survival/deactivate")
    def offline_survival_deactivate(reason: str = "dashboard", _user: str = Depends(require_user)) -> dict[str, Any]:
        return offline_survival.deactivate(reason)

    @app.get("/personal-timeline/summary")
    def personal_timeline_summary(_user: str = Depends(require_user)) -> dict[str, Any]:
        return personal_data_timeline.summary()

    @app.get("/personal-timeline/query")
    def personal_timeline_query(q: str = "today", limit: int = 20, _user: str = Depends(require_user)) -> dict[str, Any]:
        return personal_data_timeline.query(q, limit=limit)

    @app.post("/personal-timeline/notes")
    def personal_timeline_note(request: TimelineNoteRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return personal_data_timeline.record_note(request.title, request.details, event_type=request.event_type, metadata=request.metadata)

    @app.get("/skill-training/summary")
    def skill_training_summary(_user: str = Depends(require_user)) -> dict[str, Any]:
        return skill_training_studio.summary()

    @app.get("/skill-training/workflows")
    def skill_training_workflows(limit: int = 30, _user: str = Depends(require_user)) -> list[dict[str, Any]]:
        return skill_training_studio.list_workflows(limit=limit)

    @app.post("/skill-training/workflows")
    def skill_training_start(request: SkillWorkflowRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return skill_training_studio.start_workflow(request.name, description=request.description, agent_id=request.agent_id, tags=request.tags)

    @app.post("/skill-training/workflows/{workflow_id}/steps")
    def skill_training_add_step(workflow_id: int, request: SkillWorkflowStepRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return skill_training_studio.add_step(workflow_id, request.instruction, expected_result=request.expected_result)

    @app.post("/skill-training/workflows/{workflow_id}/publish")
    def skill_training_publish(workflow_id: int, _user: str = Depends(require_user)) -> dict[str, Any]:
        return skill_training_studio.finish_workflow(workflow_id)

    @app.get("/executive/summary")
    def executive_summary(_user: str = Depends(require_user)) -> dict[str, Any]:
        return executive_capabilities.summary()

    @app.post("/memory-review/generate")
    def memory_review_generate(_user: str = Depends(require_user)) -> dict[str, Any]:
        return executive_capabilities.generate_memory_reviews()

    @app.get("/memory-review/items")
    def memory_review_items(status: str = "pending", limit: int = 20, _user: str = Depends(require_user)) -> list[dict[str, Any]]:
        return executive_capabilities.list_memory_reviews(status=status, limit=limit)

    @app.post("/memory-review/items/{review_id}/resolve")
    def memory_review_resolve(review_id: int, request: MemoryReviewResolveRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return executive_capabilities.resolve_memory_review(review_id, request.decision, note=request.note)

    @app.post("/task-autopilot/start")
    def task_autopilot_start(request: AutopilotStartRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return executive_capabilities.start_task_autopilot(request.goal, sphere=request.sphere, root=request.root, priority=request.priority)

    @app.get("/task-autopilot/runs")
    def task_autopilot_runs(status: str = "", limit: int = 20, _user: str = Depends(require_user)) -> list[dict[str, Any]]:
        return executive_capabilities.list_task_autopilots(status=status, limit=limit)

    @app.post("/task-autopilot/refresh")
    def task_autopilot_refresh(_user: str = Depends(require_user)) -> dict[str, Any]:
        return executive_capabilities.refresh_task_autopilot()

    @app.get("/task-autopilot/runs/{run_id}")
    def task_autopilot_get(run_id: int, _user: str = Depends(require_user)) -> dict[str, Any]:
        run = executive_capabilities.get_task_autopilot(run_id)
        if not run:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Autopilot run not found.")
        return run

    @app.get("/personality/profile")
    def personality_profile_get(_user: str = Depends(require_user)) -> dict[str, Any]:
        return executive_capabilities.current_personality_profile()

    @app.post("/personality/profile")
    def personality_profile_set(request: PersonalityProfileRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return executive_capabilities.set_personality_profile(request.profile, reason=request.reason)

    @app.get("/life-dashboard")
    def life_dashboard(_user: str = Depends(require_user)) -> dict[str, Any]:
        return executive_capabilities.life_dashboard()

    @app.post("/skill-recorder/start")
    def skill_recorder_start(request: SkillRecordingStartRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return executive_capabilities.start_skill_recording(request.name)

    @app.post("/skill-recorder/{recording_id}/step")
    def skill_recorder_step(recording_id: int, request: SkillRecordingStepRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return executive_capabilities.add_skill_recording_step(recording_id, request.narration, expected_result=request.expected_result)

    @app.post("/skill-recorder/{recording_id}/finish")
    def skill_recorder_finish(recording_id: int, _user: str = Depends(require_user)) -> dict[str, Any]:
        return executive_capabilities.finish_skill_recording(recording_id)

    @app.get("/skill-recorder/recordings")
    def skill_recorder_list(limit: int = 20, _user: str = Depends(require_user)) -> list[dict[str, Any]]:
        return executive_capabilities.list_skill_recordings(limit=limit)

    @app.post("/documentation-brain/update")
    def documentation_brain_update(request: DocumentationBrainRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return executive_capabilities.update_documentation(request.root)

    @app.post("/personal-search")
    def personal_search(request: PersonalSearchRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return executive_capabilities.personal_search(request.query, limit=request.limit)

    @app.post("/trust-meter/assess")
    def trust_meter_assess(request: TrustAssessmentRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return executive_capabilities.trust_assessment(request.instruction, domain=request.domain)

    @app.get("/learning-twin")
    def learning_twin(_user: str = Depends(require_user)) -> dict[str, Any]:
        return executive_capabilities.learning_twin()

    @app.get("/relationship-assistant")
    def relationship_assistant(_user: str = Depends(require_user)) -> dict[str, Any]:
        return executive_capabilities.relationship_assistant()

    @app.post("/deployment/inspect")
    def deployment_inspect(request: DeploymentInspectRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return executive_capabilities.deployment_inspect(request.target, root=request.root)

    @app.post("/privacy-firewall/check")
    def privacy_firewall_check(request: PrivacyFirewallRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return executive_capabilities.privacy_firewall_check(request.instruction, context=request.context)

    @app.post("/missions")
    def create_mission(request: MissionCreateRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return mission_control.create_mission(
            request.goal,
            root=request.root,
            mission_type=request.mission_type,
            authority_mode=request.authority_mode,
            deploy_policy=request.deploy_policy,
            priority=request.priority,
            metadata=request.metadata,
        )

    @app.get("/missions")
    def list_missions(status_filter: str = "", status: str = "", limit: int = 20, _user: str = Depends(require_user)) -> list[dict[str, Any]]:
        mission_control.refresh_mission()
        return mission_control.list_missions(status=status or status_filter, limit=limit)

    @app.get("/missions/status")
    def missions_status(_user: str = Depends(require_user)) -> dict[str, Any]:
        mission_control.refresh_mission()
        return mission_control.status()

    @app.get("/missions/{mission_id}")
    def get_mission(mission_id: int, _user: str = Depends(require_user)) -> dict[str, Any]:
        mission_control.refresh_mission(mission_id)
        mission = mission_control.get_mission(mission_id)
        if not mission:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Mission not found.")
        return mission

    @app.post("/missions/{mission_id}/pause")
    def pause_mission(mission_id: int, request: MissionApprovalRequest = Body(default_factory=MissionApprovalRequest), _user: str = Depends(require_user)) -> dict[str, Any]:
        return mission_control.pause_mission(mission_id, note=request.note)

    @app.post("/missions/{mission_id}/resume")
    def resume_mission(mission_id: int, request: MissionApprovalRequest = Body(default_factory=MissionApprovalRequest), _user: str = Depends(require_user)) -> dict[str, Any]:
        return mission_control.resume_mission(mission_id, note=request.note)

    @app.post("/missions/{mission_id}/stop")
    def stop_mission(mission_id: int, request: MissionApprovalRequest = Body(default_factory=MissionApprovalRequest), _user: str = Depends(require_user)) -> dict[str, Any]:
        return mission_control.stop_mission(mission_id, note=request.note)

    @app.post("/missions/{mission_id}/approve")
    def approve_mission(mission_id: int, request: MissionApprovalRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return mission_control.approve_mission(mission_id, kind=request.kind, note=request.note)

    @app.post("/missions/{mission_id}/approve-deploy")
    def approve_mission_deploy(mission_id: int, request: MissionApprovalRequest = Body(default_factory=MissionApprovalRequest), _user: str = Depends(require_user)) -> dict[str, Any]:
        return mission_control.approve_deploy(mission_id, note=request.note)

    @app.get("/missions/{mission_id}/events")
    def mission_events(mission_id: int, limit: int = 100, _user: str = Depends(require_user)) -> list[dict[str, Any]]:
        return mission_control.events(mission_id, limit=limit)

    @app.get("/missions/{mission_id}/evidence")
    def mission_evidence(mission_id: int, limit: int = 100, _user: str = Depends(require_user)) -> list[dict[str, Any]]:
        return mission_control.evidence(mission_id, limit=limit)

    @app.post("/qa-lab/run")
    def run_qa_lab(request: QALabRunRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return autonomous_qa_lab.run_qa(request.root, mission_id=request.mission_id, run_tests=request.run_tests)

    @app.get("/qa-lab/reports")
    def qa_lab_reports(limit: int = 20, root: str = "", _user: str = Depends(require_user)) -> list[dict[str, Any]]:
        return autonomous_qa_lab.recent_reports(limit=limit, root=root)

    @app.get("/app-state/memory")
    def app_state_memory_items(app: str = "", query: str = "", limit: int = 20, _user: str = Depends(require_user)) -> list[dict[str, Any]]:
        return app_state_memory.search_patterns(app=app, query=query, limit=limit)

    @app.post("/app-state/memory")
    def app_state_memory_record(request: AppStateMemoryRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return app_state_memory.record_pattern(
            request.app,
            request.element_label,
            request.action,
            request.outcome,
            selector=request.selector,
            context=request.context,
            confidence=request.confidence,
            notes=request.notes,
            metadata=request.metadata,
        )

    @app.post("/release/prepare")
    def release_prepare(request: ReleasePrepareRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return release_manager.prepare_release(request.root, mission_id=request.mission_id, version=request.version)

    @app.get("/release/runs")
    def release_runs(limit: int = 20, _user: str = Depends(require_user)) -> list[dict[str, Any]]:
        return release_manager.recent_releases(limit=limit)

    @app.post("/release/{release_id}/approve-deploy")
    def release_approve_deploy(release_id: int, request: MissionApprovalRequest = Body(default_factory=MissionApprovalRequest), _user: str = Depends(require_user)) -> dict[str, Any]:
        return release_manager.approve_deploy(release_id, note=request.note)

    @app.post("/semantic/index")
    def semantic_index(request: SemanticIndexRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return semantic_search.index_path(request.path, include_private=request.include_private, limit=request.limit)

    @app.post("/semantic/index-text")
    def semantic_index_text(request: SemanticTextIndexRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return semantic_search.index_text(request.title, request.text, source=request.source, kind=request.kind, sensitive=request.sensitive, tags=request.tags)

    @app.post("/semantic/search")
    def semantic_search_endpoint(request: SemanticSearchRequest, _user: str = Depends(require_user)) -> list[dict[str, Any]]:
        return semantic_search.search(request.query, limit=request.limit, include_sensitive=request.include_sensitive)

    @app.get("/semantic/status")
    def semantic_status(_user: str = Depends(require_user)) -> dict[str, Any]:
        return semantic_search.status()

    @app.get("/operating-rhythm/summary")
    def operating_rhythm_summary(_user: str = Depends(require_user)) -> dict[str, Any]:
        operating_rhythm.learn_from_timeline()
        return operating_rhythm.summary()

    @app.post("/operating-rhythm/energy")
    def operating_rhythm_energy(request: OperatingRhythmEnergyRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        note = operating_rhythm.record_energy(request.mood, energy=request.energy, focus=request.focus, notes=request.notes)
        return {"energy": note, "summary": operating_rhythm.summary()}

    @app.post("/error-radar/watch")
    def error_radar_watch(request: ErrorRadarWatchRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return error_radar.watch(request.root, sources=request.sources)

    @app.get("/error-radar/events")
    def error_radar_events(limit: int = 50, status_filter: str = "", status: str = "", _user: str = Depends(require_user)) -> list[dict[str, Any]]:
        return error_radar.recent_events(limit=limit, status=status or status_filter)

    @app.post("/browser-extension/context")
    def browser_extension_context(request: BrowserExtensionContextRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return browser_extension_bridge.ingest_context(request.model_dump())

    @app.post("/browser-extension/console")
    def browser_extension_console(request: BrowserConsoleRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return browser_extension_bridge.ingest_console(request.model_dump())

    @app.post("/browser-extension/network")
    def browser_extension_network(request: BrowserNetworkEventRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return browser_extension_pro.ingest_network_event(request.model_dump())

    @app.post("/browser-extension/page-change")
    def browser_extension_page_change(request: BrowserPageChangeRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return browser_extension_pro.ingest_page_change(request.model_dump())

    @app.get("/browser-extension/status")
    def browser_extension_status(_user: str = Depends(require_user)) -> dict[str, Any]:
        return browser_extension_bridge.status()

    @app.get("/browser-extension/insight")
    def browser_extension_insight(_user: str = Depends(require_user)) -> dict[str, Any]:
        return browser_extension_bridge.latest_page_insight()

    @app.post("/browser-extension/action")
    def browser_extension_action(request: BrowserActionRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return browser_extension_bridge.queue_action(request.action, url=request.url, selector=request.selector, value=request.value, reason=request.reason, metadata=request.metadata)

    @app.get("/browser-extension/actions")
    def browser_extension_actions(url: str = "", limit: int = 5, _user: str = Depends(require_user)) -> list[dict[str, Any]]:
        return browser_extension_bridge.pending_actions(url=url, limit=limit)

    @app.post("/browser-extension/actions/{action_id}/complete")
    def browser_extension_action_complete(action_id: int, request: BrowserActionCompleteRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return browser_extension_bridge.complete_action(action_id, status=request.status, result=request.result)

    @app.get("/command-memory")
    def command_memory(limit: int = 50, _user: str = Depends(require_user)) -> dict[str, Any]:
        return {"summary": personal_command_memory.summary(limit=limit), "items": personal_command_memory.list_commands(limit=limit)}

    @app.post("/command-memory/learn")
    def command_memory_learn(request: CommandMemoryLearnRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return personal_command_memory.learn(request.heard_phrase, request.canonical_command, notes=request.notes)

    @app.post("/command-memory/resolve")
    def command_memory_resolve(request: ChatRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return personal_command_memory.resolve(request.message) or {"ok": False, "summary": "No learned command matched."}

    @app.post("/command-memory/defaults")
    def command_memory_defaults(_user: str = Depends(require_user)) -> dict[str, Any]:
        return personal_command_memory.install_default_language()

    @app.get("/calendar-email/brief")
    def calendar_email_brief(_user: str = Depends(require_user)) -> dict[str, Any]:
        return calendar_email_assistant.daily_brief()

    @app.post("/calendar-email/draft-reply")
    def calendar_email_draft(request: CalendarEmailDraftRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return calendar_email_assistant.draft_reply(request.to, request.subject, context=request.context, intent=request.intent)

    @app.get("/calendar-email/followups")
    def calendar_email_followups(limit: int = 10, _user: str = Depends(require_user)) -> dict[str, Any]:
        return calendar_email_assistant.followup_review(limit=limit)

    @app.get("/autonomous-learning")
    def autonomous_learning_status(_user: str = Depends(require_user)) -> dict[str, Any]:
        return autonomous_learning.summary()

    @app.post("/autonomous-learning/run")
    def autonomous_learning_run(request: AutonomousLearningRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return autonomous_learning.run_cycle(request.goal, create_tasks=request.create_tasks)

    @app.get("/knowledge-graph/summary")
    def knowledge_graph_summary(_user: str = Depends(require_user)) -> dict[str, Any]:
        return knowledge_graph.summary()

    @app.get("/knowledge-graph/query")
    def knowledge_graph_query(q: str = "", limit: int = 12, _user: str = Depends(require_user)) -> dict[str, Any]:
        return knowledge_graph.query(q, limit=limit)

    @app.post("/knowledge-graph/connect")
    def knowledge_graph_connect(request: GraphConnectRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return knowledge_graph.connect(request.subject, request.predicate, request.object, **request.metadata)

    @app.get("/environment/status")
    def environment_status(_user: str = Depends(require_user)) -> dict[str, Any]:
        return environment_awareness.status()

    @app.post("/environment/snapshot")
    def environment_snapshot(_user: str = Depends(require_user)) -> dict[str, Any]:
        return environment_awareness.snapshot(force_refresh=True)

    @app.get("/proof-reports")
    def proof_reports(limit: int = 20, _user: str = Depends(require_user)) -> list[dict[str, Any]]:
        return trust_proof.recent(limit=limit)

    @app.post("/proof-reports")
    def proof_report_create(request: ProofReportRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return trust_proof.create_report(
            request.title,
            changed=request.changed,
            tested=request.tested,
            failed=request.failed,
            evidence=request.evidence,
            risks=request.risks,
            mission_id=request.mission_id,
            task_id=request.task_id,
            confidence=request.confidence,
            metadata=request.metadata,
        )

    @app.post("/proof-reports/from-mission/{mission_id}")
    def proof_report_from_mission(mission_id: int, _user: str = Depends(require_user)) -> dict[str, Any]:
        return trust_proof.from_mission(mission_id)

    @app.get("/continuity/status")
    def continuity_status(_user: str = Depends(require_user)) -> dict[str, Any]:
        return continuity_brain.status()

    @app.get("/continuity/threads")
    def continuity_threads(limit: int = 20, _user: str = Depends(require_user)) -> list[dict[str, Any]]:
        return continuity_brain.open_threads(limit=limit)

    @app.post("/continuity/threads")
    def continuity_thread_create(request: ContinuityThreadRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return continuity_brain.remember_thread(request.topic, request.summary, source=request.source, status=request.status, priority=request.priority, metadata=request.metadata)

    @app.post("/continuity/capture")
    def continuity_capture(_user: str = Depends(require_user)) -> dict[str, Any]:
        return continuity_brain.capture_current_state()

    @app.get("/context-fusion/status")
    def context_fusion_status(_user: str = Depends(require_user)) -> dict[str, Any]:
        return context_fusion.status()

    @app.post("/context-fusion/snapshot")
    def context_fusion_snapshot(_user: str = Depends(require_user)) -> dict[str, Any]:
        return context_fusion.snapshot(force_refresh=True)

    @app.get("/deep-project-autopilot/reports")
    def deep_project_autopilot_reports(limit: int = 20, _user: str = Depends(require_user)) -> list[dict[str, Any]]:
        return deep_project_autopilot.recent(limit=limit)

    @app.post("/deep-project-autopilot/run")
    def deep_project_autopilot_run(request: DeepAutopilotRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return deep_project_autopilot.run(request.root, run_tests=request.run_tests, log_text=request.log_text, prepare_fix=request.prepare_fix)

    @app.get("/silence/mode")
    def silence_mode(_user: str = Depends(require_user)) -> dict[str, Any]:
        return context_aware_silence.summary()

    @app.post("/silence/mode")
    def silence_mode_set(request: SilenceModeRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return context_aware_silence.set_mode(request.mode, reason=request.reason, metadata=request.metadata)

    @app.get("/browser-pc-copilot/status")
    def browser_pc_copilot_status(_user: str = Depends(require_user)) -> dict[str, Any]:
        return browser_pc_copilot.status()

    @app.get("/browser-pc-copilot/summary")
    def browser_pc_copilot_summary(_user: str = Depends(require_user)) -> dict[str, Any]:
        return browser_pc_copilot.summarize_current_tab()

    @app.get("/browser-pc-copilot/debug")
    def browser_pc_copilot_debug(_user: str = Depends(require_user)) -> dict[str, Any]:
        return browser_pc_copilot.debug_current_page()

    @app.get("/skill-evolution/status")
    def skill_evolution_status(_user: str = Depends(require_user)) -> dict[str, Any]:
        return skill_evolution.status()

    @app.get("/skill-evolution/suggestions")
    def skill_evolution_suggestions(limit: int = 20, _user: str = Depends(require_user)) -> list[dict[str, Any]]:
        return skill_evolution.suggestions(limit=limit)

    @app.post("/skill-evolution/observe")
    def skill_evolution_observe(request: SkillEvolutionObserveRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return skill_evolution.observe_workflow(request.signature, request.description, metadata=request.metadata)

    @app.post("/skill-evolution/refresh")
    def skill_evolution_refresh(_user: str = Depends(require_user)) -> dict[str, Any]:
        return skill_evolution.suggest_from_patterns()

    @app.get("/safety-guardian/status")
    def safety_guardian_status(_user: str = Depends(require_user)) -> dict[str, Any]:
        return personal_safety_guardian.status()

    @app.get("/safety-guardian/reports")
    def safety_guardian_reports(limit: int = 20, _user: str = Depends(require_user)) -> list[dict[str, Any]]:
        return personal_safety_guardian.recent(limit=limit)

    @app.post("/safety-guardian/scan")
    def safety_guardian_scan(request: CapabilityRootRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return personal_safety_guardian.scan(request.root)

    @app.post("/safety-guardian/preflight")
    def safety_guardian_preflight(request: SafetyPreflightRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return personal_safety_guardian.preflight_action(request.instruction, path=request.path)

    @app.get("/phone-mesh/status")
    def phone_mesh_status(_user: str = Depends(require_user)) -> dict[str, Any]:
        return phone_mesh.status()

    @app.get("/phone-mesh/handoffs")
    def phone_mesh_handoffs(limit: int = 20, _user: str = Depends(require_user)) -> list[dict[str, Any]]:
        return phone_mesh.recent(limit=limit)

    @app.post("/phone-mesh/handoff")
    def phone_mesh_handoff(request: PhoneHandoffRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return phone_mesh.create_handoff(request.device_id, request.title, request.payload, direction=request.direction, kind=request.kind)

    @app.post("/phone-mesh/handoff/{handoff_id}/complete")
    def phone_mesh_handoff_complete(handoff_id: int, request: BrowserActionCompleteRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return phone_mesh.complete(handoff_id, status=request.status, result=request.result)

    @app.get("/agent-scheduler/status")
    def agent_scheduler_status(_user: str = Depends(require_user)) -> dict[str, Any]:
        return agent_scheduler.status()

    @app.post("/agent-scheduler/plan")
    def agent_scheduler_plan(request: AgentSchedulerPlanRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return agent_scheduler.plan(request.mode, voice_active=request.voice_active, apply=request.apply)

    @app.post("/agent-scheduler/apply")
    def agent_scheduler_apply(request: AgentSchedulerPlanRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        plan_payload = agent_scheduler.plan(request.mode, voice_active=request.voice_active, apply=False)
        return agent_scheduler.apply_plan(plan_payload)

    @app.post("/agent-scheduler/retry-failed")
    def agent_scheduler_retry_failed(request: AgentSchedulerRetryRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return agent_scheduler.retry_failed_tasks(limit=request.limit)

    @app.post("/agent-scheduler/schedule-research")
    def agent_scheduler_schedule_research(request: AgentSchedulerResearchRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return agent_scheduler.schedule_overnight_research(request.topic, priority=request.priority)

    @app.get("/test-build-monitor/status")
    def test_build_monitor_status(_user: str = Depends(require_user)) -> dict[str, Any]:
        return test_build_monitor.status()

    @app.post("/test-build-monitor/run")
    def test_build_monitor_run(request: TestBuildMonitorRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return test_build_monitor.run_check(request.root, request.command, kind=request.kind, create_proof=request.create_proof)

    @app.get("/test-build-monitor/reports")
    def test_build_monitor_reports(limit: int = 20, _user: str = Depends(require_user)) -> list[dict[str, Any]]:
        return test_build_monitor.recent_reports(limit=limit)

    @app.get("/reliability-score/status")
    def reliability_score_status(_user: str = Depends(require_user)) -> dict[str, Any]:
        return reliability_score.status()

    @app.get("/reliability/dashboard")
    def reliability_dashboard(_user: str = Depends(require_user)) -> dict[str, Any]:
        return _reliability_dashboard()

    @app.post("/reliability/dashboard/refresh")
    def reliability_dashboard_refresh(_user: str = Depends(require_user)) -> dict[str, Any]:
        score = reliability_score.snapshot()
        benchmark = model_benchmark_lab.run_benchmark(run_live=False)
        _invalidate_dashboard_snapshot_cache()
        return _reliability_dashboard(score=score, benchmark_refresh=benchmark)

    @app.post("/reliability-score/snapshot")
    def reliability_score_snapshot(_user: str = Depends(require_user)) -> dict[str, Any]:
        return reliability_score.snapshot()

    @app.get("/model-benchmark/status")
    def model_benchmark_status(_user: str = Depends(require_user)) -> dict[str, Any]:
        return model_benchmark_lab.status()

    @app.post("/model-benchmark/run")
    def model_benchmark_run(request: ModelBenchmarkRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return model_benchmark_lab.run_benchmark(request.task_types or None, run_live=request.run_live)

    @app.get("/deployment-brain/status")
    def deployment_brain_status(_user: str = Depends(require_user)) -> dict[str, Any]:
        return deployment_brain.status()

    @app.post("/deployment-brain/inspect")
    def deployment_brain_inspect(request: DeploymentInspectRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return deployment_brain.inspect(request.target, root=request.root, create_proof=request.create_proof)

    @app.get("/os-autopilot/status")
    def os_autopilot_status(_user: str = Depends(require_user)) -> dict[str, Any]:
        return os_autopilot.status()

    @app.post("/os-autopilot/recommend")
    def os_autopilot_recommend(_user: str = Depends(require_user)) -> dict[str, Any]:
        return os_autopilot.recommendation()

    @app.post("/os-autopilot/signal")
    def os_autopilot_signal(request: OsAutopilotSignalRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return os_autopilot.record_signal(request.kind, request.summary, request.metadata)

    @app.get("/version-guardian/status")
    def version_guardian_status(_user: str = Depends(require_user)) -> dict[str, Any]:
        return version_guardian.status()

    @app.post("/version-guardian/snapshot")
    def version_guardian_snapshot(request: VersionGuardianSnapshotRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return version_guardian.snapshot_files(request.paths, label=request.label, mission_id=request.mission_id)

    @app.post("/version-guardian/preflight")
    def version_guardian_preflight(request: VersionGuardianPreflightRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return version_guardian.preflight(request.instruction, request.paths)

    @app.post("/version-guardian/rollback-notes")
    def version_guardian_rollback(request: VersionGuardianRollbackRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return version_guardian.rollback_notes(request.mission_id, root=request.root, notes=request.notes)

    @app.get("/awareness-graph/status")
    def awareness_graph_status(_user: str = Depends(require_user)) -> dict[str, Any]:
        return awareness_graph.status()

    @app.post("/awareness-graph/refresh")
    def awareness_graph_refresh(request: AwarenessAnswerRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return awareness_graph.refresh(force=request.force)

    @app.post("/awareness-graph/answer")
    def awareness_graph_answer(request: AwarenessAnswerRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        if request.force:
            awareness_graph.refresh(force=True)
        return awareness_graph.answer(request.question)

    @app.get("/fix-loop/status")
    def fix_loop_status(_user: str = Depends(require_user)) -> dict[str, Any]:
        return autonomous_fix_loop.status()

    @app.get("/fix-loop/runs")
    def fix_loop_runs(limit: int = 20, _user: str = Depends(require_user)) -> list[dict[str, Any]]:
        return autonomous_fix_loop.recent(limit=limit)

    @app.post("/fix-loop/run")
    def fix_loop_run(request: FixLoopRunRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return autonomous_fix_loop.run(root=request.root, command=request.command, log_text=request.log_text, source=request.source, run_tests=request.run_tests, create_patch=request.create_patch)

    @app.post("/fix-loop/runs/{run_id}/approve")
    def fix_loop_approve(run_id: int, request: FixLoopApprovalRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return autonomous_fix_loop.approve(run_id, request.confirmation)

    @app.get("/browser-pro/status")
    def browser_pro_status(_user: str = Depends(require_user)) -> dict[str, Any]:
        return browser_extension_pro.status()

    @app.post("/browser-pro/guidance")
    def browser_pro_guidance(request: BrowserGuidanceRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return browser_extension_pro.guidance(request.question)

    @app.post("/browser-pro/safe-fill")
    def browser_pro_safe_fill(request: BrowserSafeFillRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return browser_extension_pro.safe_fill(request.selector, request.value, reason=request.reason)

    @app.post("/browser-pro/watch")
    def browser_pro_watch(_user: str = Depends(require_user)) -> dict[str, Any]:
        return browser_extension_pro.watch_page()

    @app.get("/android-companion/pro/status")
    def android_companion_pro_status(_user: str = Depends(require_user)) -> dict[str, Any]:
        return android_companion.status()

    @app.get("/android-companion/app/files")
    def android_companion_files(limit: int = 20, _user: str = Depends(require_user)) -> list[dict[str, Any]]:
        return _decorate_android_files(android_companion.recent_files(limit=limit))

    @app.get("/android-companion/app/files/{file_id}")
    def android_companion_file(
        file_id: int,
        token: str = "",
        authorization: str = Header(default=""),
    ) -> FileResponse:
        _require_user_from_header_or_token(authorization, token)
        item = android_companion.get_file(file_id)
        if not item:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Android companion file not found.")
        path = Path(str(item.get("stored_path") or "")).expanduser().resolve()
        base = android_companion.FILE_DIR.resolve()
        try:
            path.relative_to(base)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Android companion file is outside the capture store.") from exc
        if not path.exists() or not path.is_file():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Android companion file is missing from disk.")
        media_type = str(item.get("mime_type") or "application/octet-stream")
        return FileResponse(str(path), media_type=media_type, filename=str(item.get("name") or path.name))

    @app.get("/memory-review/pro/status")
    def memory_review_pro_status(_user: str = Depends(require_user)) -> dict[str, Any]:
        return personal_memory_review.status()

    @app.post("/memory-review/pro/generate")
    def memory_review_pro_generate(limit: int = 12, _user: str = Depends(require_user)) -> dict[str, Any]:
        return personal_memory_review.generate(limit=limit)

    @app.get("/app-mastery/status")
    def app_mastery_status(_user: str = Depends(require_user)) -> dict[str, Any]:
        return app_operator_mastery.status()

    @app.post("/app-mastery/plan")
    def app_mastery_plan(request: AppMasteryRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return app_operator_mastery.plan(request.app, request.instruction)

    @app.post("/app-mastery/start")
    def app_mastery_start(request: AppMasteryRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return app_operator_mastery.start(request.app, request.instruction, max_steps=request.max_steps)

    @app.get("/local-ai-search/status")
    def local_ai_search_status(_user: str = Depends(require_user)) -> dict[str, Any]:
        return local_ai_search.status()

    @app.post("/local-ai-search/index")
    def local_ai_search_index(request: LocalAiIndexRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return local_ai_search.index(request.paths, include_private=request.include_private, limit=request.limit)

    @app.post("/local-ai-search/search")
    def local_ai_search_search(request: LocalAiSearchRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return local_ai_search.search(request.query, limit=request.limit, include_sensitive=request.include_sensitive)

    @app.post("/local-ai-search/answer")
    def local_ai_search_answer(request: LocalAiSearchRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return local_ai_search.answer(request.query, limit=request.limit)

    @app.get("/life-os/status")
    def life_os_status(_user: str = Depends(require_user)) -> dict[str, Any]:
        return life_os_mode.status()

    @app.post("/life-os/brief")
    def life_os_brief(_user: str = Depends(require_user)) -> dict[str, Any]:
        return life_os_mode.daily_brief()

    @app.post("/life-os/next")
    def life_os_next(_user: str = Depends(require_user)) -> dict[str, Any]:
        return life_os_mode.next_action()

    @app.post("/life-os/end-of-day")
    def life_os_end(_user: str = Depends(require_user)) -> dict[str, Any]:
        return life_os_mode.end_of_day()

    @app.get("/security-guardian-pro/status")
    def security_guardian_pro_status(_user: str = Depends(require_user)) -> dict[str, Any]:
        return security_guardian_pro.status()

    @app.post("/security-guardian-pro/scan")
    def security_guardian_pro_scan(request: CapabilityRootRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return security_guardian_pro.scan(request.root, light=True)

    @app.get("/autonomy-engine/status")
    def autonomy_engine_status(_user: str = Depends(require_user)) -> dict[str, Any]:
        return autonomy_engine.status()

    @app.get("/autonomy-engine/runs")
    def autonomy_engine_runs(limit: int = 20, _user: str = Depends(require_user)) -> list[dict[str, Any]]:
        return autonomy_engine.recent(limit=limit)

    @app.post("/autonomy-engine/start")
    def autonomy_engine_start(request: AutonomyStartRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return autonomy_engine.run_until_blocked(request.goal, root=request.root, max_steps=request.max_steps)

    @app.post("/autonomy-engine/runs/{run_id}/step")
    def autonomy_engine_step(run_id: int, _user: str = Depends(require_user)) -> dict[str, Any]:
        return autonomy_engine.step(run_id)

    @app.get("/autonomy-engine/runs/{run_id}/events")
    def autonomy_engine_events(run_id: int, limit: int = 50, _user: str = Depends(require_user)) -> list[dict[str, Any]]:
        return autonomy_engine.events(run_id, limit=limit)

    @app.get("/certainty/status")
    def certainty_status(_user: str = Depends(require_user)) -> dict[str, Any]:
        return certainty_brain.summary()

    @app.post("/certainty/record")
    def certainty_record(request: CertaintyRecordRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return certainty_brain.record(
            request.kind,
            request.topic,
            request.statement,
            evidence=request.evidence,
            confidence=request.confidence,
            source=request.source,
            stale_after=request.stale_after,
            metadata=request.metadata,
        )

    @app.post("/certainty/known")
    def certainty_known(request: CertaintyRecordRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return certainty_brain.record_known(request.topic, request.statement, evidence=request.evidence, confidence=request.confidence, source=request.source)

    @app.post("/certainty/guess")
    def certainty_guess(request: CertaintyRecordRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return certainty_brain.record_guess(request.topic, request.statement, evidence=request.evidence, confidence=request.confidence, source=request.source)

    @app.post("/certainty/missing")
    def certainty_missing(request: CertaintyRecordRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return certainty_brain.record_missing(request.topic, request.statement, source=request.source)

    @app.post("/certainty/search")
    def certainty_search(request: CertaintyQueryRequest, _user: str = Depends(require_user)) -> list[dict[str, Any]]:
        return certainty_brain.search(request.query, kind=request.kind, limit=request.limit)

    @app.post("/certainty/answer")
    def certainty_answer(request: CertaintyQueryRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return certainty_brain.answer(request.query or "what do you know and not know")

    @app.get("/vision-skills/status")
    def vision_skills_status(_user: str = Depends(require_user)) -> dict[str, Any]:
        return vision_skill_learning.summary()

    @app.post("/vision-skills/learn")
    def vision_skills_learn(request: VisionSkillPatternRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return vision_skill_learning.learn_pattern(
            app=request.app,
            label=request.label,
            pattern_type=request.pattern_type,
            visual_cues=request.visual_cues,
            dom_cues=request.dom_cues,
            accessibility_cues=request.accessibility_cues,
            meaning=request.meaning,
            action_hint=request.action_hint,
            confidence=request.confidence,
            metadata=request.metadata,
        )

    @app.post("/vision-skills/observe")
    def vision_skills_observe(request: VisionSkillObserveRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return vision_skill_learning.observe_from_context(request.app, request.context)

    @app.post("/vision-skills/recognize")
    def vision_skills_recognize(request: VisionSkillRecognizeRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return vision_skill_learning.recognize(request.app, request.query, limit=request.limit)

    @app.get("/automation-daemon/status")
    def automation_daemon_status(_user: str = Depends(require_user)) -> dict[str, Any]:
        return personal_automation_daemon.status()

    @app.post("/automation-daemon/install-defaults")
    def automation_daemon_install_defaults(_user: str = Depends(require_user)) -> dict[str, Any]:
        return personal_automation_daemon.install_defaults()

    @app.post("/automation-daemon/run")
    def automation_daemon_run(run_actions: bool = True, _user: str = Depends(require_user)) -> dict[str, Any]:
        return personal_automation_daemon.run_once(run_actions=run_actions)

    @app.get("/notification-intelligence/status")
    def notification_intelligence_status(_user: str = Depends(require_user)) -> dict[str, Any]:
        return notification_intelligence.status()

    @app.post("/notification-intelligence/rank")
    def notification_intelligence_rank(request: NotificationRankRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return notification_intelligence.rank_pending(limit=request.limit)

    @app.get("/self-tests/status")
    def self_tests_status(_user: str = Depends(require_user)) -> dict[str, Any]:
        return self_testing_personality.status()

    @app.post("/self-tests/run")
    def self_tests_run(_user: str = Depends(require_user)) -> dict[str, Any]:
        return self_testing_personality.run()

    @app.get("/project-memory/status")
    def project_memory_status(_user: str = Depends(require_user)) -> dict[str, Any]:
        return project_memory.status()

    @app.post("/project-memory/profile")
    def project_memory_profile(request: ProjectMemoryProfileRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return project_memory.profile(request.root, refresh=request.refresh)

    @app.post("/project-memory/remember")
    def project_memory_remember(request: ProjectMemoryNoteRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return project_memory.remember(request.root, request.kind, request.title, request.content, confidence=request.confidence, metadata=request.metadata)

    @app.post("/project-memory/search")
    def project_memory_search(request: ProjectMemorySearchRequest, _user: str = Depends(require_user)) -> list[dict[str, Any]]:
        return project_memory.search(request.query, root=request.root, limit=request.limit)

    @app.get("/project-memory/reference-images")
    def project_memory_reference_images(root: str = "", limit: int = 30, _user: str = Depends(require_user)) -> list[dict[str, Any]]:
        return project_memory.list_reference_images(root=root, limit=limit)

    @app.post("/project-memory/reference-images")
    def project_memory_add_reference_image(request: ProjectMemoryReferenceImageRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        content, content_type = _decode_reference_image_data(request)
        try:
            created = project_memory.add_reference_image(
                request.root,
                title=request.title or request.filename,
                note=request.note,
                filename=request.filename,
                content=content,
                content_type=content_type,
                metadata={**request.metadata, "source": request.metadata.get("source", "dashboard")},
            )
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        _invalidate_dashboard_snapshot_cache()
        return created

    @app.get("/project-memory/reference-images/{root_hash}/{filename}")
    def project_memory_reference_image(
        root_hash: str,
        filename: str,
        token: str = "",
        authorization: str = Header(default=""),
    ) -> FileResponse:
        _require_user_from_header_or_token(authorization, token)
        try:
            path = project_memory.reference_image_path(root_hash, filename)
        except ValueError:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project reference image not found.")
        if not path.exists() or not path.is_file():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project reference image not found.")
        return FileResponse(str(path))

    @app.get("/operator-skills/status")
    def operator_skills_status(_user: str = Depends(require_user)) -> dict[str, Any]:
        return operator_skills.status()

    @app.get("/operator-skills")
    def operator_skills_list(_user: str = Depends(require_user)) -> list[dict[str, Any]]:
        return operator_skills.list_operators()

    @app.post("/operator-skills/plan")
    def operator_skills_plan(request: OperatorSkillRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return operator_skills.plan(request.app, request.instruction, root=request.root)

    @app.post("/operator-skills/start")
    def operator_skills_start(request: OperatorSkillRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return operator_skills.start(request.app, request.instruction, max_steps=request.max_steps, root=request.root)

    @app.get("/learning-roadmap/status")
    def learning_roadmap_status(_user: str = Depends(require_user)) -> dict[str, Any]:
        return learning_roadmap.status()

    @app.post("/learning-roadmap")
    def learning_roadmap_create(request: LearningRoadmapRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return learning_roadmap.create(request.topic, request.goal, weeks=request.weeks)

    @app.post("/learning-roadmap/quiz")
    def learning_roadmap_quiz(request: LearningRoadmapRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return learning_roadmap.next_quiz(request.topic)

    @app.get("/privacy-firewall-pro/status")
    def privacy_firewall_pro_status(_user: str = Depends(require_user)) -> dict[str, Any]:
        return privacy_firewall_pro.status()

    @app.post("/privacy-firewall-pro/check")
    def privacy_firewall_pro_check(request: PrivacyFirewallProRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return privacy_firewall_pro.check(request.instruction, context=request.context, paths=request.paths, purpose=request.purpose)

    @app.get("/device-mesh/status")
    def device_mesh_status(_user: str = Depends(require_user)) -> dict[str, Any]:
        return device_command_mesh.status()

    @app.get("/device-mesh/commands")
    def device_mesh_commands(limit: int = 20, _user: str = Depends(require_user)) -> list[dict[str, Any]]:
        return device_command_mesh.recent(limit=limit)

    @app.post("/device-mesh/command")
    def device_mesh_command(request: DeviceMeshCommandRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return device_command_mesh.create_command(
            request.command_type,
            request.title,
            source_device=request.source_device,
            target_device=request.target_device,
            payload=request.payload,
        )

    @app.post("/device-mesh/continue-on-laptop")
    def device_mesh_continue_on_laptop(request: DeviceMeshCommandRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return device_command_mesh.continue_on_laptop(request.title, request.payload, source_device=request.source_device)

    @app.post("/device-mesh/browser-page")
    def device_mesh_browser_page(request: DeviceMeshCommandRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return device_command_mesh.send_browser_page_to_friday(str(request.payload.get("note") or request.title or ""))

    @app.post("/device-mesh/phone-camera")
    def device_mesh_phone_camera(request: DeviceMeshCommandRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return device_command_mesh.phone_camera_to_friday(str(request.payload.get("device_id") or request.source_device or ""), note=request.title)

    @app.get("/release-engine/status")
    def release_engine_status(_user: str = Depends(require_user)) -> dict[str, Any]:
        return autonomous_release_engine.status()

    @app.get("/release-engine/runs")
    def release_engine_runs(limit: int = 20, _user: str = Depends(require_user)) -> list[dict[str, Any]]:
        return autonomous_release_engine.recent(limit=limit)

    @app.post("/release-engine/prepare")
    def release_engine_prepare(request: ReleaseEngineerRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return autonomous_release_engine.prepare(request.root, build_command=request.build_command, target_url=request.target_url, run_tests=request.run_tests)

    @app.get("/decision-memory/status")
    def decision_memory_status(_user: str = Depends(require_user)) -> dict[str, Any]:
        return decision_memory.status()

    @app.post("/decision-memory/remember")
    def decision_memory_remember(request: DecisionMemoryRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return decision_memory.remember(request.category, request.preference, threshold=request.threshold, evidence=request.evidence, confidence=request.confidence, source=request.source, metadata=request.metadata)

    @app.post("/decision-memory/infer")
    def decision_memory_infer(request: DecisionMemoryRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return decision_memory.learn_from_text(request.text or request.preference, source=request.source)

    @app.post("/decision-memory/choose")
    def decision_memory_choose(request: DecisionQueryRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return decision_memory.choose(request.query, category=request.category, context=request.context)

    @app.get("/skill-improvement/status")
    def skill_improvement_status(_user: str = Depends(require_user)) -> dict[str, Any]:
        return skill_improvement.status()

    @app.post("/skill-improvement/failure")
    def skill_improvement_failure(request: SkillFailureRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return skill_improvement.record_failure(request.skill, request.failure, evidence=request.evidence, context=request.context)

    @app.get("/skill-improvement/proposals")
    def skill_improvement_proposals(limit: int = 20, _user: str = Depends(require_user)) -> list[dict[str, Any]]:
        return skill_improvement.proposals(limit=limit)

    @app.get("/workspace-coach/status")
    def workspace_coach_status(_user: str = Depends(require_user)) -> dict[str, Any]:
        return live_workspace_coach.status()

    @app.post("/workspace-coach/observe")
    def workspace_coach_observe(request: WorkspaceCoachRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return live_workspace_coach.observe(request.root, log_text=request.log_text, current_file=request.current_file, run_tests=request.run_tests, notify=request.notify)

    @app.get("/memory-debate/status")
    def memory_debate_status(_user: str = Depends(require_user)) -> dict[str, Any]:
        return memory_debate.status()

    @app.post("/memory-debate")
    def memory_debate_run(request: MemoryDebateRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return memory_debate.debate(request.topic, limit=request.limit)

    @app.post("/memory-debate/review")
    def memory_debate_review(request: MemoryDebateRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return memory_debate.review(limit=request.limit)

    @app.get("/focus-protection/status")
    def focus_protection_status(_user: str = Depends(require_user)) -> dict[str, Any]:
        return focus_protection.status()

    @app.post("/focus-protection/mode")
    def focus_protection_mode(request: FocusProtectionRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return focus_protection.set_mode(request.mode, reason=request.reason or "dashboard", metadata=request.metadata)

    @app.post("/focus-protection/evaluate")
    def focus_protection_evaluate(request: FocusProtectionRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return focus_protection.evaluate_notification(title=request.title, message=request.message, severity=request.severity, category=request.category, explicit=request.explicit, metadata=request.metadata)

    @app.post("/focus-protection/flush")
    def focus_protection_flush(_user: str = Depends(require_user)) -> dict[str, Any]:
        return focus_protection.flush()

    @app.get("/app-apprenticeship/status")
    def app_apprenticeship_status(_user: str = Depends(require_user)) -> dict[str, Any]:
        return app_apprenticeship.status()

    @app.post("/app-apprenticeship/start")
    def app_apprenticeship_start(request: AppApprenticeshipStartRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return app_apprenticeship.start(request.app, request.workflow, goal=request.goal, metadata=request.metadata)

    @app.post("/app-apprenticeship/step")
    def app_apprenticeship_step(request: AppApprenticeshipStepRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return app_apprenticeship.record_step(request.session_id, request.narration, action=request.action, observation=request.observation, selector=request.selector, screenshot=request.screenshot, success=request.success, metadata=request.metadata)

    @app.post("/app-apprenticeship/{session_id}/finish")
    def app_apprenticeship_finish(session_id: int, _user: str = Depends(require_user)) -> dict[str, Any]:
        return app_apprenticeship.finish(session_id)

    @app.get("/project-cto/status")
    def project_cto_status(_user: str = Depends(require_user)) -> dict[str, Any]:
        return project_cto.status()

    @app.post("/project-cto/report")
    def project_cto_report(request: ProjectCtoRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return project_cto.report(request.root, refresh=request.refresh)

    @app.get("/conversation-continuity/status")
    def conversation_continuity_status(_user: str = Depends(require_user)) -> dict[str, Any]:
        return conversation_continuity.status()

    @app.get("/conversation-continuity/threads")
    def conversation_continuity_threads(limit: int = 20, _user: str = Depends(require_user)) -> list[dict[str, Any]]:
        return conversation_continuity.open_threads(limit=limit)

    @app.post("/conversation-continuity/capture")
    def conversation_continuity_capture(request: ConversationThreadRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return conversation_continuity.capture(request.title, summary=request.summary, blocker=request.blocker, evidence=request.evidence, source=request.source, metadata=request.metadata)

    @app.post("/conversation-continuity/{thread_id}/resolve")
    def conversation_continuity_resolve(thread_id: int, request: ConversationThreadRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return conversation_continuity.resolve(thread_id, note=request.summary or request.blocker)

    @app.get("/local-voice-brain/status")
    def local_voice_brain_status(_user: str = Depends(require_user)) -> dict[str, Any]:
        return local_voice_brain.status()

    @app.post("/local-voice-brain/defaults")
    def local_voice_brain_defaults(_user: str = Depends(require_user)) -> dict[str, Any]:
        return local_voice_brain.install_defaults()

    @app.post("/local-voice-brain/repair")
    def local_voice_brain_repair(request: LocalVoiceBrainRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return local_voice_brain.repair(request.heard, request.expected, source=request.source)

    @app.post("/local-voice-brain/wake-alias")
    def local_voice_brain_wake_alias(request: LocalVoiceBrainRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return local_voice_brain.tune_wake_name(request.alias or request.heard)

    @app.get("/trust-dashboard/status")
    def trust_dashboard_status(_user: str = Depends(require_user)) -> dict[str, Any]:
        return trust_dashboard.status()

    @app.get("/agent-quality/status")
    def agent_quality_status(_user: str = Depends(require_user)) -> dict[str, Any]:
        return agent_quality_manager.status()

    @app.get("/agent-quality/leaderboard")
    def agent_quality_leaderboard(task_type: str = "", limit: int = 20, _user: str = Depends(require_user)) -> list[dict[str, Any]]:
        return agent_quality_manager.leaderboard(task_type=task_type, limit=limit)

    @app.post("/agent-quality/record")
    def agent_quality_record(request: AgentQualityRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return agent_quality_manager.record_evaluation(
            request.agent_id,
            task_id=request.task_id,
            task_type=request.task_type,
            accuracy=request.accuracy,
            usefulness=request.usefulness,
            speed=request.speed,
            evidence=request.evidence,
            mistakes=request.mistakes,
            fixed_by_agent=request.fixed_by_agent,
            notes=request.notes,
            metadata=request.metadata,
        )

    @app.get("/agent-lifecycle/status")
    def agent_lifecycle_status(_user: str = Depends(require_user)) -> dict[str, Any]:
        return agent_lifecycle.status()

    @app.post("/agent-lifecycle/hire")
    def agent_lifecycle_hire(request: AgentLifecycleRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return agent_lifecycle.hire_specialist(request.name, request.purpose, keywords=request.keywords, agent_id=request.agent_id, metadata=request.metadata)

    @app.post("/agent-lifecycle/{agent_id}/retire")
    def agent_lifecycle_retire(agent_id: str, request: AgentLifecycleRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return agent_lifecycle.retire_agent(agent_id, reason=request.reason)

    @app.post("/agent-lifecycle/{agent_id}/promote")
    def agent_lifecycle_promote(agent_id: str, request: AgentLifecycleRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return agent_lifecycle.promote_agent(agent_id, reason=request.reason)

    @app.post("/agent-lifecycle/{agent_id}/role")
    def agent_lifecycle_role(agent_id: str, request: AgentLifecycleRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return agent_lifecycle.rewrite_role(agent_id, name=request.name, purpose=request.purpose, keywords=request.keywords)

    @app.get("/agent-council/status")
    def agent_council_status(_user: str = Depends(require_user)) -> dict[str, Any]:
        return agent_council.status()

    @app.post("/agent-council/convene")
    def agent_council_convene(request: AgentCouncilRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return agent_council.convene(request.question, agent_ids=request.agent_ids, context=request.context, metadata=request.metadata)

    @app.get("/do-not-forget/status")
    def do_not_forget_status(_user: str = Depends(require_user)) -> dict[str, Any]:
        return do_not_forget.status()

    @app.post("/do-not-forget/classify")
    def do_not_forget_classify(request: DoNotForgetRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return do_not_forget.classify(request.content, source=request.source, context=request.context)

    @app.get("/dev-server-copilot/status")
    def dev_server_copilot_status(_user: str = Depends(require_user)) -> dict[str, Any]:
        return dev_server_copilot.status()

    @app.post("/dev-server-copilot/observe")
    def dev_server_copilot_observe(request: DevServerCopilotRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return dev_server_copilot.observe(request.root, log_text=request.log_text, current_file=request.current_file, source=request.source)

    @app.get("/code-change-simulator/status")
    def code_change_simulator_status(_user: str = Depends(require_user)) -> dict[str, Any]:
        return code_change_simulator.status()

    @app.post("/code-change-simulator/simulate")
    def code_change_simulator_run(request: CodeChangeSimulationRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return code_change_simulator.simulate(request.instruction, root=request.root, metadata=request.metadata)

    @app.get("/refactor-planner/status")
    def refactor_planner_status(_user: str = Depends(require_user)) -> dict[str, Any]:
        return refactor_planner.status()

    @app.post("/refactor-planner/plan")
    def refactor_planner_plan(request: RefactorPlanRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return refactor_planner.plan(request.root, focus=request.focus, max_files=request.max_files)

    @app.get("/taste-engine/status")
    def taste_engine_status(_user: str = Depends(require_user)) -> dict[str, Any]:
        return personal_taste_engine.status()

    @app.post("/taste-engine/learn")
    def taste_engine_learn(request: TasteEngineRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return personal_taste_engine.learn_from_correction(request.correction, domain=request.domain, evidence=request.evidence)

    @app.post("/taste-engine/guidance")
    def taste_engine_guidance(request: TasteEngineRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return personal_taste_engine.guidance(request.domain, context=request.context or request.correction)

    @app.get("/memory-constitution/status")
    def memory_constitution_status(_user: str = Depends(require_user)) -> dict[str, Any]:
        return memory_constitution.status()

    @app.post("/memory-constitution/evaluate")
    def memory_constitution_evaluate(request: MemoryConstitutionRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return memory_constitution.evaluate(request.kind, request.content, sensitivity=request.sensitivity)

    @app.post("/memory-constitution/rule")
    def memory_constitution_rule(request: MemoryConstitutionRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return memory_constitution.set_policy(request.kind, mode=request.mode, retention=request.retention, private=request.private, description=request.description)

    @app.get("/reality-check/status")
    def reality_check_status(_user: str = Depends(require_user)) -> dict[str, Any]:
        return reality_check.status()

    @app.post("/reality-check/check")
    def reality_check_run(request: RealityCheckRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return reality_check.check(request.claim, evidence=request.evidence, tool_result=request.tool_result, domain=request.domain, metadata=request.metadata)

    @app.get("/agent-simulation/status")
    def agent_simulation_status(_user: str = Depends(require_user)) -> dict[str, Any]:
        return agent_simulation_sandbox.status()

    @app.post("/agent-simulation/simulate")
    def agent_simulation_run(request: AgentSimulationRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return agent_simulation_sandbox.simulate(request.goal, agent_ids=request.agent_ids, root=request.root, risk_level=request.risk_level)

    @app.get("/command-graph/status")
    def command_graph_status(_user: str = Depends(require_user)) -> dict[str, Any]:
        return command_graph.status()

    @app.post("/command-graph/defaults")
    def command_graph_defaults(_user: str = Depends(require_user)) -> dict[str, Any]:
        return command_graph.install_defaults()

    @app.post("/command-graph/learn")
    def command_graph_learn(request: CommandGraphRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return command_graph.learn_phrase(request.phrase, request.intent, steps=request.steps, confidence=request.confidence, metadata=request.metadata)

    @app.post("/command-graph/resolve")
    def command_graph_resolve(request: CommandGraphRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return command_graph.resolve(request.phrase)

    @app.get("/emotional-timing/status")
    def emotional_timing_status(_user: str = Depends(require_user)) -> dict[str, Any]:
        return emotional_timing.status()

    @app.post("/emotional-timing/advise")
    def emotional_timing_advise(request: EmotionalTimingRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return emotional_timing.advise(request.text, explicit_tone=request.explicit_tone)

    @app.get("/visual-skill-memory/status")
    def visual_skill_memory_status(_user: str = Depends(require_user)) -> dict[str, Any]:
        return visual_skill_memory_v2.status()

    @app.post("/visual-skill-memory/screen")
    def visual_skill_memory_screen(request: VisualSkillMemoryRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return visual_skill_memory_v2.learn_screen(request.app, request.screen_label, cues=request.cues, meaning=request.meaning, action_hint=request.action_hint, source=request.source)

    @app.post("/visual-skill-memory/recognize")
    def visual_skill_memory_recognize(request: VisualSkillMemoryRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return visual_skill_memory_v2.recognize(app=request.app, query=request.query or request.screen_label, limit=request.limit)

    @app.get("/failure-autopsy/status")
    def failure_autopsy_status(_user: str = Depends(require_user)) -> dict[str, Any]:
        return failure_autopsy.status()

    @app.post("/failure-autopsy/create")
    def failure_autopsy_create(request: FailureAutopsyRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return failure_autopsy.create(
            request.title,
            request.what_happened,
            root_cause=request.root_cause,
            next_time=request.next_time,
            evidence=request.evidence,
            code_change_needed=request.code_change_needed,
            source=request.source,
            metadata=request.metadata,
        )

    @app.get("/notifications")
    def notifications(status_filter: str = "", min_severity: int = 0, limit: int = 50, _user: str = Depends(require_user)) -> list[dict[str, Any]]:
        return notification_center.list_notifications(status_filter, min_severity=min_severity, limit=limit)

    @app.get("/notifications/summary")
    def notifications_summary(_user: str = Depends(require_user)) -> dict[str, Any]:
        return notification_center.summary()

    @app.post("/notifications/{notification_id}/mark")
    def notifications_mark(notification_id: int, request: NotificationMarkRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        item = notification_center.mark(notification_id, request.status)
        if not item:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found.")
        return item

    @app.post("/notifications/mark-all-read")
    def notifications_mark_all_read(_user: str = Depends(require_user)) -> dict[str, int]:
        return notification_center.mark_all_read()

    @app.get("/knowledge-vault/summary")
    def vault_summary(_user: str = Depends(require_user)) -> dict[str, Any]:
        return personal_knowledge_vault.summary()

    @app.get("/knowledge-vault/items")
    def vault_items(kind: str = "", query: str = "", limit: int = 50, _user: str = Depends(require_user)) -> list[dict[str, Any]]:
        if query:
            return personal_knowledge_vault.search(query, kind=kind, limit=limit)
        return personal_knowledge_vault.list_items(kind=kind, limit=limit)

    @app.post("/knowledge-vault/items")
    def vault_remember(request: VaultItemRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return personal_knowledge_vault.remember(
            request.kind,
            request.title,
            request.content,
            confidence=request.confidence,
            tags=request.tags,
        )

    @app.get("/knowledge-vault/week")
    def vault_week(_user: str = Depends(require_user)) -> dict[str, Any]:
        return personal_knowledge_vault.what_matters_this_week()

    @app.post("/voice/repair")
    def voice_repair(request: VoiceRepairRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return voice_command_repair.record_repair(request.expected_text, request.heard_text, context=request.context)

    @app.get("/voice/repair/suggestions")
    def voice_repair_suggestions(_user: str = Depends(require_user)) -> dict[str, Any]:
        return voice_command_repair.suggestions()

    @app.post("/project-autopilot/inspect")
    def project_autopilot_inspect(request: ProjectAutopilotRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return project_autopilot.inspect_project(request.root, run_tests=request.run_tests)

    @app.post("/project-autopilot/prepare-fixes")
    def project_autopilot_prepare(request: ProjectAutopilotRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return project_autopilot.prepare_fixes(request.root, issue_query=request.issue_query)

    @app.get("/project-autopilot/reports")
    def project_autopilot_reports(limit: int = 20, root: str = "", _user: str = Depends(require_user)) -> list[dict[str, Any]]:
        return project_autopilot.recent_reports(limit=limit, root=root)

    @app.get("/pc/timeline")
    def pc_timeline_events(limit: int = 50, event_type: str = "", _user: str = Depends(require_user)) -> list[dict[str, Any]]:
        return pc_timeline.recent_events(limit=limit, event_type=event_type)

    @app.get("/pc/timeline/summary")
    def pc_timeline_summary(_user: str = Depends(require_user)) -> dict[str, Any]:
        return pc_timeline.summary()

    @app.post("/pc/timeline/capture")
    def pc_timeline_capture(_user: str = Depends(require_user)) -> dict[str, Any]:
        return pc_timeline.capture_snapshot()

    @app.post("/pc/timeline/sync-audit")
    def pc_timeline_sync_audit(_user: str = Depends(require_user)) -> dict[str, Any]:
        return pc_timeline.sync_audit_events()

    @app.post("/goals/plan")
    def goals_plan(request: GoalPlanRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return goal_manager.create_goal_plan(request.title, request.description, deadline_at=request.deadline_at, priority=request.priority)

    @app.get("/goals/weekly-plan")
    def goals_weekly_plan(_user: str = Depends(require_user)) -> dict[str, Any]:
        return goal_manager.weekly_plan()

    @app.get("/goals/next-action")
    def goals_next_action(_user: str = Depends(require_user)) -> dict[str, Any]:
        return goal_manager.next_goal_action()

    @app.get("/goals/progress")
    def goals_progress(limit: int = 10, _user: str = Depends(require_user)) -> dict[str, Any]:
        return goal_manager.progress_summary(limit=limit)

    @app.post("/files/local/index")
    def local_files_index(request: LocalFileIndexRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return local_file_intelligence.index_locations(request.paths or None, max_files=request.max_files or None)

    @app.get("/files/local/search")
    def local_files_search(query: str, limit: int = 20, _user: str = Depends(require_user)) -> list[dict[str, Any]]:
        return local_file_intelligence.search(query, limit=limit)

    @app.post("/files/local/answer")
    def local_files_answer(request: LocalFileQueryRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return local_file_intelligence.answer(request.query)

    @app.post("/files/local/folder-summary")
    def local_files_folder_summary(request: LocalFileQueryRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return local_file_intelligence.summarize_folder(request.path)

    @app.get("/study/sessions")
    def study_sessions(limit: int = 20, _user: str = Depends(require_user)) -> list[dict[str, Any]]:
        return meeting_study_companion.list_sessions(limit=limit)

    @app.post("/study/sessions")
    def study_create_session(request: StudySessionRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return meeting_study_companion.create_session(request.title, kind=request.kind, source=request.source, transcript=request.transcript)

    @app.get("/study/sessions/{session_id}")
    def study_get_session(session_id: int, _user: str = Depends(require_user)) -> dict[str, Any]:
        session = meeting_study_companion.get_session(session_id)
        if not session:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Study session not found.")
        return session

    @app.post("/study/sessions/{session_id}/transcript")
    def study_add_transcript(session_id: int, request: StudyTranscriptRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return meeting_study_companion.add_transcript(session_id, request.transcript, append=request.append)

    @app.post("/study/sessions/{session_id}/followups")
    def study_create_followups(session_id: int, due_at: str = "tomorrow", _user: str = Depends(require_user)) -> dict[str, Any]:
        return meeting_study_companion.create_followup_reminders(session_id, due_at=due_at)

    @app.post("/automation/from-text")
    def automation_from_text(request: AutomationTextRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return automation_builder.create_from_text(request.text)

    @app.post("/automation/evaluate")
    def automation_evaluate(run: bool = True, _user: str = Depends(require_user)) -> dict[str, Any]:
        return automation_builder.evaluate_triggers(run=run)

    @app.get("/integrations/dashboard")
    def integrations_dashboard(_user: str = Depends(require_user)) -> dict[str, Any]:
        return _integrations_dashboard()

    @app.post("/integrations/dashboard/refresh")
    def integrations_dashboard_refresh(_user: str = Depends(require_user)) -> dict[str, Any]:
        refresh_result = event_nervous_system.run_once(notify=False)
        _invalidate_dashboard_snapshot_cache()
        return _integrations_dashboard(refresh=refresh_result)

    @app.get("/integrations/apps")
    def integration_apps(_user: str = Depends(require_user)) -> dict[str, str]:
        return dict(app_integrations.APP_LINKS)

    @app.get("/integrations/google/status")
    def google_status(_user: str = Depends(require_user)) -> dict[str, Any]:
        return google_workspace.status()

    @app.post("/integrations/google/oauth/start")
    def google_oauth_start(_user: str = Depends(require_user)) -> dict[str, Any]:
        try:
            return google_workspace.start_auth()
        except RuntimeError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        except ImportError as exc:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=f"Google OAuth dependencies are missing: {exc}") from exc

    @app.post("/integrations/google/disconnect")
    def google_disconnect(_user: str = Depends(require_user)) -> dict[str, Any]:
        return google_workspace.disconnect()

    @app.get("/oauth/google/callback")
    def google_oauth_callback(code: str = "", state: str = "") -> HTMLResponse:
        try:
            google_workspace.finish_auth(code, state)
        except Exception as exc:
            return HTMLResponse(
                f"<html><body><h1>Friday Google connection failed</h1><p>{str(exc)}</p></body></html>",
                status_code=400,
            )
        return HTMLResponse(
            "<html><body><h1>Friday is connected to Google Workspace.</h1><p>You can close this tab and return to the dashboard.</p></body></html>"
        )

    @app.get("/integrations/google/gmail/messages")
    def google_gmail_messages(limit: int = 10, _user: str = Depends(require_user)) -> list[dict[str, Any]]:
        return google_workspace.recent_gmail_messages(limit=limit)

    @app.get("/integrations/google/calendar/events")
    def google_calendar_events(limit: int = 10, _user: str = Depends(require_user)) -> list[dict[str, Any]]:
        return google_workspace.list_calendar_events(limit=limit)

    @app.post("/integrations/google/calendar/events")
    def google_create_calendar_event(request: CalendarEventRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return google_workspace.create_calendar_event(
            request.title,
            start_at=request.start_at,
            end_at=request.end_at,
            location=request.location,
            notes=request.notes,
        )

    @app.post("/integrations/google/docs")
    def google_create_document(request: DocumentRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return google_workspace.create_document(request.title, body=request.body)

    @app.post("/integrations/google/sheets")
    def google_create_sheet(request: DocumentRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return google_workspace.create_sheet(request.title, headers=request.headers or None)

    @app.post("/integrations/open")
    def integration_open(request: IntegrationOpenRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        link = app_integrations.app_link(request.target)
        if not link:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No deep link configured for that app.")
        from tools import pc_control

        return {"target": request.target, "url": link, "reply": pc_control.execute({"action": "open_path", "target": link})}

    @app.post("/integrations/contacts")
    def create_contact(request: ContactRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return app_integrations.create_contact(request.name, email=request.email, phone=request.phone, notes=request.notes)

    @app.get("/integrations/contacts")
    def search_contacts(query: str = "", limit: int = 20, _user: str = Depends(require_user)) -> list[dict[str, Any]]:
        return app_integrations.search_contacts(query, limit=limit)

    @app.post("/integrations/reminders")
    def create_reminder(request: ReminderRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return app_integrations.create_reminder(request.title, due_at=request.due_at, notes=request.notes)

    @app.get("/integrations/reminders")
    def reminders(include_done: bool = False, limit: int = 20, _user: str = Depends(require_user)) -> list[dict[str, Any]]:
        return app_integrations.list_reminders(include_done=include_done, limit=limit)

    @app.post("/integrations/reminders/{reminder_id}/complete")
    def complete_reminder(reminder_id: int, _user: str = Depends(require_user)) -> dict[str, Any]:
        reminder = app_integrations.complete_reminder(reminder_id)
        if not reminder:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Reminder not found.")
        return reminder

    @app.post("/integrations/calendar/events")
    def create_calendar_event(request: CalendarEventRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return app_integrations.create_calendar_event(
            request.title,
            start_at=request.start_at,
            end_at=request.end_at,
            location=request.location,
            notes=request.notes,
        )

    @app.get("/integrations/calendar/events")
    def calendar_events(limit: int = 20, _user: str = Depends(require_user)) -> list[dict[str, Any]]:
        return app_integrations.list_calendar_events(limit=limit)

    @app.post("/integrations/docs")
    def create_document(request: DocumentRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return app_integrations.create_document(request.title, body=request.body)

    @app.post("/integrations/sheets")
    def create_sheet(request: DocumentRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return app_integrations.create_sheet(request.title, headers=request.headers or None)

    @app.post("/integrations/workspace/index")
    def index_workspace(request: WorkspaceIndexRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return app_integrations.index_workspace(request.root, max_files=request.max_files or None)

    @app.get("/integrations/workspace/search")
    def workspace_search(query: str, limit: int = 20, _user: str = Depends(require_user)) -> list[dict[str, Any]]:
        return app_integrations.search_workspace(query, limit=limit)

    @app.get("/integrations/workspace/overview")
    def workspace_overview(_user: str = Depends(require_user)) -> dict[str, Any]:
        return app_integrations.workspace_overview()

    @app.get("/agents/roster")
    def roster(_user: str = Depends(require_user)) -> list[dict[str, str]]:
        return agents.roster()

    @app.get("/agents/status")
    def agent_status(_user: str = Depends(require_user)) -> dict[str, Any]:
        return background_agents.worker_status()

    @app.get("/agents/offices")
    def agent_offices(_user: str = Depends(require_user)) -> list[dict[str, Any]]:
        return agent_office.all_offices()

    @app.get("/agents/{agent_id}/office")
    def single_agent_office(agent_id: str, _user: str = Depends(require_user)) -> dict[str, Any]:
        return agent_office.office(agent_id)

    @app.get("/blackboard/summary")
    def blackboard_summary(_user: str = Depends(require_user)) -> dict[str, Any]:
        return agent_blackboard.summary()

    @app.get("/blackboard/items")
    def blackboard_items(
        status_filter: str = "",
        item_type: str = "",
        agent_id: str = "",
        task_id: int | None = None,
        limit: int = 50,
        _user: str = Depends(require_user),
    ) -> list[dict[str, Any]]:
        return agent_blackboard.list_items(
            status=status_filter,
            item_type=item_type,
            agent_id=agent_id,
            task_id=task_id,
            limit=limit,
        )

    @app.post("/blackboard/items")
    def blackboard_post_item(request: BlackboardItemRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return agent_blackboard.post_item(
            request.agent_id,
            request.item_type,
            request.title,
            request.content,
            task_id=request.task_id,
            confidence=request.confidence,
            target_agent_id=request.target_agent_id,
            status=request.status,
            metadata=request.metadata,
        )

    @app.post("/blackboard/items/{item_id}/resolve")
    def blackboard_resolve_item(item_id: int, request: ResolveRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        item = agent_blackboard.resolve_item(item_id, note=request.note)
        if not item:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Blackboard item not found.")
        return item

    @app.get("/agent-memory/summary")
    def agent_memory_summary(_user: str = Depends(require_user)) -> dict[str, Any]:
        return agent_memory.summary()

    @app.get("/agent-memory/{agent_id}")
    def agent_memory_notebook(agent_id: str, query: str = "", limit: int = 30, _user: str = Depends(require_user)) -> dict[str, Any]:
        if query:
            return {"agent_id": agent_id, "items": agent_memory.search(agent_id, query, limit=limit)}
        return agent_memory.notebook(agent_id, limit=limit)

    @app.get("/thoughts/summary")
    def thought_summary(_user: str = Depends(require_user)) -> dict[str, Any]:
        return agent_thought_bus.summary()

    @app.get("/thoughts")
    def thought_packets(
        status_filter: str = "",
        packet_type: str = "",
        source_agent_id: str = "",
        target_agent_id: str = "",
        task_id: int | None = None,
        limit: int = 50,
        _user: str = Depends(require_user),
    ) -> list[dict[str, Any]]:
        return agent_thought_bus.list_thoughts(
            status=status_filter,
            packet_type=packet_type,
            source_agent_id=source_agent_id,
            target_agent_id=target_agent_id,
            task_id=task_id,
            limit=limit,
        )

    @app.get("/thoughts/context/{agent_id}")
    def thought_context(agent_id: str, query: str = "", task_id: int | None = None, limit: int = 6, _user: str = Depends(require_user)) -> dict[str, Any]:
        return {"agent_id": agent_id, "context": agent_thought_bus.context_for_agent(agent_id, query, task_id=task_id, limit=limit)}

    @app.post("/thoughts")
    def thought_post(request: ThoughtPacketRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return agent_thought_bus.post_thought(
            request.source_agent_id,
            request.packet_type,
            request.summary,
            request.content,
            target_agent_id=request.target_agent_id,
            task_id=request.task_id,
            confidence=request.confidence,
            priority=request.priority,
            status=request.status,
            visibility=request.visibility,
            ttl_seconds=request.ttl_seconds,
            metadata=request.metadata,
        )

    @app.post("/thoughts/{packet_id}/seen")
    def thought_mark_seen(packet_id: int, _user: str = Depends(require_user)) -> dict[str, Any]:
        packet = agent_thought_bus.mark_seen(packet_id, "dashboard")
        if not packet:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Thought packet not found.")
        return packet

    @app.post("/thoughts/{packet_id}/resolve")
    def thought_resolve(packet_id: int, request: ResolveRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        packet = agent_thought_bus.resolve_thought(packet_id, note=request.note)
        if not packet:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Thought packet not found.")
        return packet

    @app.post("/workers/start")
    def start_workers(count: int = 0, _user: str = Depends(require_user)) -> dict[str, Any]:
        worker_count = max(1, min(int(count), 10)) if count else None
        return {"workers": background_agents.start_workers(worker_count)}

    @app.post("/workers/stop")
    def stop_workers(_user: str = Depends(require_user)) -> dict[str, str]:
        background_agents.stop_workers()
        return {"status": "stopped"}

    @app.post("/workers/run-one")
    def run_one(_user: str = Depends(require_user)) -> dict[str, Any]:
        task = background_agents.run_one_task()
        return {"task": task}

    @app.get("/tasks")
    def list_tasks(
        status_filter: str = "",
        agent_id: str = "",
        limit: int = 50,
        _user: str = Depends(require_user),
    ) -> list[dict[str, Any]]:
        return [_decorate_task(task) for task in task_queue.list_tasks(status=status_filter or None, agent_id=agent_id or None, limit=limit)]

    @app.post("/tasks")
    def create_task(request: TaskCreateRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        task_id = agents.create_task(
            request.title,
            description=request.description,
            agent_id=request.agent_id,
            priority=request.priority,
            scheduled_at=request.scheduled_at,
        )
        return task_queue.get_task(task_id) or {"id": task_id}

    @app.get("/tasks/{task_id}")
    def get_task(task_id: int, _user: str = Depends(require_user)) -> dict[str, Any]:
        task = task_queue.get_task(task_id)
        if not task:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found.")
        task["messages"] = task_queue.get_messages(task_id, limit=20)
        return _decorate_task(task)

    @app.post("/tasks/{task_id}/cancel")
    def cancel_task(task_id: int, _user: str = Depends(require_user)) -> dict[str, Any]:
        return {"cancelled": task_queue.cancel_task(task_id), "task_id": task_id}

    @app.post("/tasks/{task_id}/reassign")
    def reassign_task(task_id: int, request: TaskReassignRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        agent_id = agents.normalize_agent_id(request.agent_id)
        if agent_id not in {agent["id"] for agent in agents.roster()}:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unknown agent.")
        if not task_queue.reassign_task(task_id, agent_id, status=request.status or "pending"):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found or cannot be reassigned.")
        task = task_queue.get_task(task_id)
        return _decorate_task(task) if task else {"id": task_id, "agent_id": agent_id}

    @app.get("/contracts")
    def contracts(status_filter: str = "", limit: int = 50, _user: str = Depends(require_user)) -> list[dict[str, Any]]:
        return task_contracts.list_contracts(status=status_filter, limit=limit)

    @app.get("/contracts/summary")
    def contracts_summary(_user: str = Depends(require_user)) -> dict[str, Any]:
        return task_contracts.summary()

    @app.get("/contracts/{task_id}")
    def contract_for_task(task_id: int, _user: str = Depends(require_user)) -> dict[str, Any]:
        contract = task_contracts.get_contract(task_id)
        if not contract:
            task = task_queue.get_task(task_id)
            if not task:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found.")
            contract = task_contracts.ensure_contract(task)
        return contract

    @app.get("/memory/episodic")
    def episodic(limit: int = 50, agent_id: str = "", _user: str = Depends(require_user)) -> list[dict[str, Any]]:
        return episodic_store.query_events(agent_id=agent_id or None, limit=limit)

    @app.get("/memory/skills")
    def skills(_user: str = Depends(require_user)) -> list[dict[str, Any]]:
        return skill_library.all_skills()

    @app.get("/memory/skills/summary")
    def skills_summary(_user: str = Depends(require_user)) -> dict[str, Any]:
        return skill_library.skill_summary()

    @app.post("/memory/skills/install")
    def skills_install(request: SkillInstallRequest, _user: str = Depends(require_user)) -> list[dict[str, Any]]:
        return skill_library.install_builtin(request.key)

    @app.post("/memory/skills/{skill_id}/toggle")
    def skills_toggle(skill_id: str, request: SkillToggleRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        skill = skill_library.enable_skill(skill_id, request.enabled)
        if not skill:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Skill not found.")
        return skill

    @app.get("/workspace-brain/repos")
    def workspace_brain_repos(root: str = "", _user: str = Depends(require_user)) -> dict[str, Any]:
        return workspace_brain.map_repos(root)

    @app.post("/workspace-brain/analyze")
    def workspace_brain_analyze(request: CapabilityRootRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return workspace_brain.analyze_project(request.root)

    @app.post("/workspace-brain/question")
    def workspace_brain_question(request: WorkspaceQuestionRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return workspace_brain.answer_workspace_question(request.question, request.root)

    @app.post("/workspace-brain/docs")
    def workspace_brain_docs(request: CapabilityRootRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return workspace_brain.generate_docs(request.root)

    @app.get("/app-operators")
    def app_operator_list(_user: str = Depends(require_user)) -> list[dict[str, Any]]:
        return app_operators.list_operators()

    @app.get("/app-operators/{app}/context")
    def app_operator_context(app: str, _user: str = Depends(require_user)) -> dict[str, Any]:
        return app_operators.operator_context(app)

    @app.post("/app-operators/open")
    def app_operator_open(request: AppOperatorRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return app_operators.open_app(request.app)

    @app.post("/app-operators/operate")
    def app_operator_operate(request: AppOperatorRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        if not request.instruction:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Instruction is required.")
        return app_operators.operate(request.app, request.instruction, max_steps=request.max_steps)

    @app.post("/coding/autonomous/start")
    def autonomous_coding_start(request: AutonomousCodingRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return autonomous_coding.start(request.request, root=request.root, risk_level=request.risk_level)

    @app.get("/memory/competence")
    def competence_maps(_user: str = Depends(require_user)) -> dict[str, Any]:
        return competence.all_maps()

    @app.get("/cognition/status")
    def cognition_status(_user: str = Depends(require_user)) -> dict[str, Any]:
        return {
            "cycle": cognitive_cycle.status(),
            "world": world_model.current_context(),
            "regulation": goal_regulation.current_regulation(),
            "attention": adaptive_attention.current_profile(),
            "recent_reflections": self_reflection.recent_findings(limit=5),
            "recent_learning": long_term_learning.recent_items(limit=5),
        }

    @app.post("/cognition/run-once")
    def cognition_run_once(_user: str = Depends(require_user)) -> dict[str, Any]:
        return cognitive_cycle.run_once("api", light_mode=True)

    @app.get("/cognition/world")
    def cognition_world(_user: str = Depends(require_user)) -> dict[str, Any]:
        return world_model.current_context()

    @app.get("/cognition/world/snapshots")
    def cognition_world_snapshots(limit: int = 20, _user: str = Depends(require_user)) -> list[dict[str, Any]]:
        return world_model.recent_snapshots(limit=limit)

    @app.get("/cognition/reflections")
    def cognition_reflections(limit: int = 20, _user: str = Depends(require_user)) -> list[dict[str, Any]]:
        return self_reflection.recent_findings(limit=limit)

    @app.post("/cognition/reflections/run")
    def cognition_reflection_run(_user: str = Depends(require_user)) -> dict[str, Any]:
        return self_reflection.run_reflection(trigger="api")

    @app.get("/cognition/learning")
    def cognition_learning(limit: int = 20, _user: str = Depends(require_user)) -> list[dict[str, Any]]:
        return long_term_learning.recent_items(limit=limit)

    @app.post("/cognition/learning/review")
    def cognition_learning_review(_user: str = Depends(require_user)) -> dict[str, Any]:
        return long_term_learning.run_reviews(limit=10)

    @app.get("/cognition/goals")
    def cognition_goals(status_filter: str = "", limit: int = 20, _user: str = Depends(require_user)) -> list[dict[str, Any]]:
        return goal_regulation.list_goals(status=status_filter, limit=limit)

    @app.post("/cognition/goals")
    def cognition_goal_create(request: GoalCreateRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        goal_id = goal_regulation.create_goal(
            request.title,
            description=request.description,
            priority=request.priority,
            source=request.source,
            deadline_at=request.deadline_at,
        )
        return goal_regulation.get_goal(goal_id) or {"id": goal_id}

    @app.patch("/cognition/goals/{goal_id}")
    def cognition_goal_update(goal_id: int, request: GoalUpdateRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return goal_regulation.update_goal(goal_id, status=request.status, progress=request.progress, note=request.note)

    @app.get("/cognition/attention")
    def cognition_attention(_user: str = Depends(require_user)) -> dict[str, Any]:
        return {
            "profile": adaptive_attention.current_profile(),
            "recommended_config": adaptive_attention.recommended_attention_config(),
            "events": adaptive_attention.recent_events(limit=20),
        }

    @app.post("/cognition/attention/correction")
    def cognition_attention_correction(request: AttentionCorrectionRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return adaptive_attention.record_user_correction(request.expected_text, request.heard_text)

    @app.get("/evaluation/summary")
    def evaluation_summary(_user: str = Depends(require_user)) -> dict[str, Any]:
        return evaluation_lab.summary()

    @app.get("/evaluation/events")
    def evaluation_events(category: str = "", limit: int = 80, _user: str = Depends(require_user)) -> list[dict[str, Any]]:
        return evaluation_lab.recent_events(category=category, limit=limit)

    @app.get("/approvals/inbox")
    def approvals_inbox(limit: int = 50, _user: str = Depends(require_user)) -> list[dict[str, Any]]:
        return approval_inbox.items(limit=limit)

    @app.get("/approvals/summary")
    def approvals_summary(_user: str = Depends(require_user)) -> dict[str, Any]:
        return approval_inbox.summary()

    @app.post("/approvals/{kind}/{item_id}/resolve")
    def approvals_resolve(kind: str, item_id: int, request: ResolveRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return approval_inbox.resolve(kind, item_id, note=request.note)

    @app.get("/voice/reliability/summary")
    def voice_reliability_summary(_user: str = Depends(require_user)) -> dict[str, Any]:
        return voice_reliability.summary()

    @app.get("/voice/reliability/samples")
    def voice_reliability_samples(limit: int = 80, mistakes_only: bool = False, _user: str = Depends(require_user)) -> list[dict[str, Any]]:
        return voice_reliability.recent_samples(limit=limit, mistakes_only=mistakes_only)

    @app.post("/voice/reliability/correction")
    def voice_reliability_correction(request: VoiceCorrectionRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        sample_id = voice_reliability.record_correction(request.expected_text, request.heard_text, backend="dashboard")
        return {"sample_id": sample_id, "summary": voice_reliability.summary()}

    @app.post("/voice/reliability/sample")
    def voice_reliability_sample(request: VoiceSampleRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        sample_id = voice_reliability.record_sample(
            request.heard_text,
            expected_text=request.expected_text,
            backend=request.backend,
            confidence=request.confidence,
            accepted=request.accepted,
            metadata={"source": "dashboard_streaming_stt"},
        )
        return {"sample_id": sample_id, "summary": voice_reliability.summary()}

    @app.get("/browser/playwright/status")
    def browser_playwright_status(_user: str = Depends(require_user)) -> dict[str, Any]:
        return browser_playwright.available()

    @app.post("/browser/playwright/inspect")
    def browser_playwright_inspect(request: PlaywrightInspectRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return browser_playwright.inspect_url(request.url, limit=request.limit)

    @app.post("/browser/playwright/run")
    def browser_playwright_run(request: PlaywrightRunRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return browser_playwright.run_steps(request.url, request.steps)

    @app.get("/self/status")
    def self_status(_user: str = Depends(require_user)) -> dict[str, Any]:
        return self_model.status(light=True)

    @app.get("/self/capabilities")
    def self_capabilities(_user: str = Depends(require_user)) -> dict[str, Any]:
        return {"summary": self_model.capability_summary(), "tools": self_model.tool_inventory(), "modules": self_model.module_inventory()}

    @app.get("/self/access")
    def self_access(_user: str = Depends(require_user)) -> dict[str, Any]:
        return {"summary": self_model.access_summary(), "access": self_model.access_report(light=True)}

    @app.get("/self/uncertainty")
    def self_uncertainty(_user: str = Depends(require_user)) -> dict[str, Any]:
        return {"summary": self_model.uncertainty_summary(), **self_model.uncertainty_report()}

    @app.get("/self/failures")
    def self_failures(limit: int = 20, _user: str = Depends(require_user)) -> dict[str, Any]:
        failures = self_model.recent_failures(limit=limit)
        return {"summary": self_model.failure_summary(), "failures": failures}

    @app.get("/self/autobiography")
    def self_autobiography(limit: int = 30, event_type: str = "", _user: str = Depends(require_user)) -> dict[str, Any]:
        return {
            "summary": autobiographical_memory.timeline_summary(limit=6),
            "events": autobiographical_memory.recent_events(limit=limit, event_type=event_type),
            "important": autobiographical_memory.important_events(limit=10),
        }

    @app.get("/self/identity")
    def self_identity(_user: str = Depends(require_user)) -> dict[str, Any]:
        return identity.identity_summary()

    @app.get("/self/why-last-action")
    def self_why_last_action(_user: str = Depends(require_user)) -> dict[str, Any]:
        return {"summary": self_model.why_last_action_summary()}

    @app.get("/self-updates")
    def self_updates(limit: int = 20, _user: str = Depends(require_user)) -> list[dict[str, Any]]:
        return self_update.list_updates(limit=limit)

    @app.post("/self-updates")
    def self_update_propose(request: SelfUpdateProposalRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return self_update.create_proposal(request.request)

    @app.get("/self-updates/{update_id}")
    def self_update_get(update_id: int, _user: str = Depends(require_user)) -> dict[str, Any]:
        update = self_update.get_update(update_id)
        if not update:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Self-update not found.")
        return update

    @app.post("/self-updates/{update_id}/approve")
    def self_update_approve(update_id: int, request: SelfUpdateApprovalRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return self_update.approve_update(update_id, request.confirmation)

    @app.post("/self-updates/{update_id}/stage")
    def self_update_stage(update_id: int, request: SelfUpdateStageRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return self_update.stage_change(update_id, request.path, request.find_text, request.replace_text, request.summary)

    @app.post("/self-updates/{update_id}/apply")
    def self_update_apply(update_id: int, request: SelfUpdateApplyRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return self_update.apply_update(update_id, request.confirmation, run_tests=request.run_tests)

    @app.post("/self-updates/{update_id}/cancel")
    def self_update_cancel(update_id: int, _user: str = Depends(require_user)) -> dict[str, Any]:
        return self_update.cancel_update(update_id)

    @app.get("/logs/recent")
    def recent_logs(lines: int = 100, _user: str = Depends(require_user)) -> dict[str, Any]:
        return _recent_logs(max(1, min(int(lines), 500)))

    @app.get("/audit/recent")
    def recent_audit(limit: int = 100, category: str = "", _user: str = Depends(require_user)) -> list[dict[str, Any]]:
        return audit_log.recent(limit=max(1, min(int(limit), 500)), category=category or None)

    @app.get("/permissions/rules")
    def permission_rules(_user: str = Depends(require_user)) -> list[dict[str, Any]]:
        return permissions.list_rules()

    @app.put("/permissions/rules/{rule_key:path}")
    def update_permission_rule(rule_key: str, request: PermissionRuleRequest, _user: str = Depends(require_user)) -> dict[str, Any]:
        return permissions.set_rule(rule_key, request.mode)

    @app.post("/permissions/reset")
    def reset_permission_rules(_user: str = Depends(require_user)) -> list[dict[str, Any]]:
        return permissions.reset_defaults()

    @app.get("/permissions/events")
    def permission_events(limit: int = 50, _user: str = Depends(require_user)) -> list[dict[str, Any]]:
        return permissions.recent_events(limit=limit)

    @app.post("/graph/neo4j/export")
    def export_neo4j(_user: str = Depends(require_user)) -> dict[str, Any]:
        return neo4j_migration.export_cypher()

    @app.websocket("/ws/logs")
    async def log_stream(websocket: WebSocket, token: str = "") -> None:
        try:
            api_auth.decode_token(token, token_type="access")
        except api_auth.AuthError:
            await websocket.close(code=1008)
            return
        await websocket.accept()
        last_payload = ""
        try:
            while True:
                payload = _recent_logs(100)
                text = "\n".join(payload.get("lines") or [])
                if text != last_payload:
                    last_payload = text
                    await websocket.send_json(payload)
                await asyncio.sleep(2.0)
        except WebSocketDisconnect:
            return

    @app.websocket("/ws/dashboard")
    async def dashboard_stream(websocket: WebSocket, token: str = "") -> None:
        try:
            api_auth.decode_token(token, token_type="access")
        except api_auth.AuthError:
            await websocket.close(code=1008)
            return
        await websocket.accept()
        last_payload = ""
        try:
            while True:
                payload = await asyncio.to_thread(_dashboard_snapshot)
                text = _stream_payload_signature(payload)
                if text != last_payload:
                    last_payload = text
                    await websocket.send_json(payload)
                await asyncio.sleep(float(config_value("dashboard_stream_interval_seconds", 2.0)))
        except WebSocketDisconnect:
            return

    @app.websocket("/ws/integrations")
    async def integrations_stream(websocket: WebSocket, token: str = "") -> None:
        await _stream_snapshot_payload(
            websocket,
            token,
            _integrations_dashboard,
            "integrations_stream_interval_seconds",
            10.0,
        )

    @app.websocket("/ws/reliability")
    async def reliability_stream(websocket: WebSocket, token: str = "") -> None:
        await _stream_snapshot_payload(
            websocket,
            token,
            _reliability_dashboard,
            "reliability_stream_interval_seconds",
            10.0,
        )

    @app.websocket("/ws/notifications")
    async def notification_stream(websocket: WebSocket, token: str = "") -> None:
        try:
            api_auth.decode_token(token, token_type="access")
        except api_auth.AuthError:
            await websocket.close(code=1008)
            return
        await websocket.accept()
        last_payload = ""
        try:
            while True:
                payload = await asyncio.to_thread(_notification_stream_payload)
                text = _stream_payload_signature(payload)
                if text != last_payload:
                    last_payload = text
                    await websocket.send_json(payload)
                await asyncio.sleep(float(config_value("notification_stream_interval_seconds", 1.0)))
        except WebSocketDisconnect:
            return

    @app.websocket("/ws/voice/deepgram")
    async def voice_deepgram_stream(websocket: WebSocket, token: str = "") -> None:
        try:
            api_auth.decode_token(token, token_type="access")
        except api_auth.AuthError:
            await websocket.accept()
            try:
                await websocket.send_json({"type": "error", "message": "Voice session expired. Log in again."})
            except Exception:
                pass
            await websocket.close(code=1008)
            return
        await websocket.accept()
        dg_socket = None
        loop = asyncio.get_running_loop()
        stop_event = threading.Event()

        def send_client(payload: dict[str, Any]) -> None:
            if stop_event.is_set():
                return
            try:
                future = asyncio.run_coroutine_threadsafe(websocket.send_json(payload), loop)

                def mark_failed(done: Any) -> None:
                    try:
                        done.result()
                    except Exception:
                        stop_event.set()

                future.add_done_callback(mark_failed)
            except Exception:
                stop_event.set()

        async def send_client_now(payload: dict[str, Any]) -> bool:
            if stop_event.is_set():
                return False
            try:
                await websocket.send_json(payload)
                return True
            except Exception:
                stop_event.set()
                return False

        try:
            model = stt.load_model(f"deepgram:{config_value('stt_deepgram_model', 'nova-3')}")
            dg_socket = await asyncio.to_thread(stt._open_deepgram_socket, model)
        except Exception as exc:
            await send_client_now({"type": "error", "message": f"Deepgram STT unavailable: {exc}"})
            await websocket.close(code=1011)
            return

        def deepgram_reader() -> None:
            while not stop_event.is_set():
                try:
                    message = dg_socket.recv()
                except Exception as exc:
                    if stt._deepgram_is_timeout(exc):
                        time.sleep(0.01)
                        continue
                    if not stop_event.is_set():
                        send_client({"type": "error", "message": str(exc)})
                    break
                payload = stt._deepgram_parse_message(message)
                if not payload:
                    continue
                message_type = str(payload.get("type") or "")
                if message_type == "Results":
                    transcript, confidence = stt._deepgram_result_transcript(payload)
                    if transcript:
                        send_client(
                            {
                                "type": "transcript",
                                "text": transcript,
                                "is_final": bool(payload.get("is_final")),
                                "speech_final": bool(payload.get("speech_final")) or bool(payload.get("from_finalize")),
                                "confidence": confidence,
                            }
                        )
                elif message_type == "SpeechStarted":
                    send_client({"type": "speech_started"})
                elif message_type == "UtteranceEnd":
                    send_client({"type": "utterance_end"})
                elif message_type == "Error":
                    send_client({"type": "error", "message": str(payload.get("description") or payload.get("message") or payload)})

        reader_thread = threading.Thread(target=deepgram_reader, name="dashboard-deepgram-reader", daemon=True)
        reader_thread.start()
        try:
            ready_sent = await send_client_now(
                {
                    "type": "ready",
                    "backend": "deepgram",
                    "model": str(config_value("stt_deepgram_model", "nova-3")),
                    "sample_rate": stt.SAMPLE_RATE,
                }
            )
            if not ready_sent:
                return
            while True:
                message = await websocket.receive()
                if message.get("type") == "websocket.disconnect":
                    break
                if "bytes" in message and message["bytes"]:
                    stt._deepgram_send_binary(dg_socket, message["bytes"])
                    continue
                text = str(message.get("text") or "").strip()
                if not text:
                    continue
                try:
                    payload = json.loads(text)
                except json.JSONDecodeError:
                    payload = {"type": text}
                payload_type = str(payload.get("type") or "")
                if payload_type == "finalize":
                    stt._deepgram_send_json(dg_socket, {"type": "Finalize"})
                elif payload_type == "close":
                    break
        except WebSocketDisconnect:
            return
        finally:
            stop_event.set()
            try:
                if dg_socket is not None:
                    stt._deepgram_send_json(dg_socket, {"type": "CloseStream"})
            except Exception:
                pass
            try:
                if dg_socket is not None:
                    dg_socket.close()
            except Exception:
                pass

    @app.websocket("/ws/chat")
    async def chat_stream(websocket: WebSocket, token: str = "") -> None:
        try:
            api_auth.decode_token(token, token_type="access")
        except api_auth.AuthError:
            await websocket.close(code=1008)
            return
        await websocket.accept()
        try:
            while True:
                payload = await websocket.receive_json()
                request_id = str(payload.get("id") or "")
                message = " ".join(str(payload.get("message") or "").split())
                timestamp = dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds")
                if not message:
                    await websocket.send_json({"type": "error", "id": request_id, "message": "Message is empty.", "timestamp": timestamp})
                    continue
                if len(message) > 4000:
                    await websocket.send_json({"type": "error", "id": request_id, "message": "Message is too long.", "timestamp": timestamp})
                    continue
                await websocket.send_json({"type": "ack", "id": request_id, "message": message, "timestamp": timestamp})
                try:
                    reply = await asyncio.to_thread(orchestrator.handle_command, message)
                except Exception as exc:
                    await websocket.send_json(
                        {
                            "type": "error",
                            "id": request_id,
                            "message": f"Friday chat failed: {exc}",
                            "timestamp": dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds"),
                        }
                    )
                    continue
                await websocket.send_json(
                    {
                        "type": "reply",
                        "id": request_id,
                        "message": message,
                        "reply": reply,
                        "timestamp": dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds"),
                    }
                )
        except WebSocketDisconnect:
            return

    @app.get("/v2/status")
    def v2_status(_user: str = Depends(require_user)) -> dict[str, Any]:
        return {
            "source_pdf": r"C:\Users\HomePC\Desktop\second-brain\JARVIS_v2_Phase_Planning_v3.pdf",
            "ui_stack": {"desktop": "Electron", "web": "Next.js"},
            "phase": "v2 foundation + local API",
            "workers": background_agents.worker_status(),
            "implemented": [
                "task_queue",
                "background_agents",
                "episodic_store",
                "knowledge_graph",
                "procedural_memory",
                "competence_maps",
                "jwt_local_api",
                "audit_log",
                "permission_control_center",
                "postgres_sync",
                "neo4j_cypher_export",
                "desktop_vision",
                "desktop_task_sessions",
                "continuous_visual_monitor",
                "pc_awareness_inventory",
                "deep_app_integrations",
                "agent_virtual_offices",
                "brain_inspired_world_model",
                "self_reflection_journal",
                "long_term_learning_store",
                "goal_regulation",
                "adaptive_attention_profile",
                "cognitive_cycle",
                "self_model",
                "autobiographical_memory",
                "identity_values_file",
                "evidence_gate",
                "agent_blackboard",
                "silent_agent_thought_bus",
                "task_contracts",
                "evaluation_lab",
                "shared_agent_memory",
                "approval_inbox",
                "playwright_browser_automation",
                "voice_reliability_lab",
                "electron_packaging_tray_autostart",
                "self_update_dashboard_panel",
                "browser_streaming_stt",
                "google_workspace_oauth",
                "complex_app_operator_context",
                "android_phone_control_v2",
                "capability_center",
                "home_device_status",
                "configured_smart_device_control",
                "personal_ops_briefings",
                "workspace_intelligence",
                "computer_maintenance_reports",
                "ethical_security_lab",
                "owned_web_header_checks",
                "project_secret_scan",
                "automation_recipes",
                "local_network_awareness",
                "skill_plugin_library",
                "true_workspace_brain",
                "app_specific_operators",
                "personal_life_os",
                "device_mesh_android",
                "home_assistant_integration",
                "autonomous_coding_mode",
                "backup_recovery_brain",
                "proactive_guardian_mode",
                "personal_knowledge_vault",
                "voice_command_repair",
                "notification_center",
                "project_autopilot",
                "pc_awareness_timeline",
                "goal_manager",
                "local_file_intelligence",
                "meeting_study_companion",
                "automation_builder",
                "event_driven_nervous_system",
                "barge_in_voice_signal",
                "true_daily_companion_mode",
                "friday_skill_marketplace",
                "personal_finance_helper",
                "private_embedding_memory",
                "android_companion_layer",
                "project_watchdog",
                "codebase_standards_guard",
                "sandbox_simulation_mode",
                "privacy_vault",
                "model_router_brain",
                "self_debugger",
                "emotion_tone_awareness",
                "personal_crm",
                "learning_coach_mode",
                "autonomous_research_briefings",
                "contextual_workspace_autopilot",
                "offline_survival_mode",
                "personal_data_timeline",
                "skill_training_studio",
                "real_memory_review",
                "task_autopilot_checkpoints",
                "voice_personality_profiles",
                "local_life_dashboard",
                "friday_skill_recorder",
                "autonomous_documentation_brain",
                "personal_search_engine",
                "trust_meter",
                "learning_twin",
                "relationship_assistant",
                "deployment_commander",
                "privacy_firewall",
                "mission_control_mode",
                "autonomy_control_room",
                "non_interrupting_work_mode",
                "autonomous_project_builder_template",
                "autonomous_qa_lab",
                "app_state_memory",
                "browser_extension_bridge",
                "release_manager",
                "error_radar",
                "local_semantic_search_everywhere",
                "personal_operating_rhythm",
                "native_android_companion_app",
                "browser_extension_v2_dom_actions",
                "autonomous_debugger_mode",
                "personal_command_memory",
                "calendar_email_assistant",
                "autonomous_learning_mode",
                "local_knowledge_graph_query",
                "environment_awareness",
                "trust_proof_reports",
                "continuity_brain",
                "real_time_context_fusion",
                "deep_project_autopilot",
                "personal_command_language_defaults",
                "memory_approval_review",
                "context_aware_silence",
                "local_browser_pc_copilot",
                "skill_evolution",
                "personal_safety_guardian",
                "phone_to_pc_mesh",
                "real_agent_scheduler",
                "autonomous_test_build_monitor",
                "reliability_score_system",
                "local_model_benchmark_lab",
                "project_deployment_brain",
                "personal_os_autopilot",
                "real_backup_version_guardian",
                "real_time_awareness_graph",
                "autonomous_fix_loop",
                "browser_extension_pro_mode",
                "android_companion_file_camera_uploads",
                "personal_memory_review_pro",
                "app_operator_mastery",
                "local_ai_search_engine",
                "life_os_mode",
                "security_guardian_pro",
                "cloud_worker_mode",
                "real_time_task_autonomy_engine",
                "agent_quality_manager",
                "agent_hiring_firing_promotion",
                "agent_council_mode",
                "do_not_forget_memory_router",
                "dev_server_copilot",
                "code_change_simulator",
                "autonomous_refactor_planner",
                "personal_taste_engine",
                "memory_constitution",
                "reality_check_mode",
                "agent_simulation_sandbox",
                "personal_command_graph",
                "emotional_timing",
                "visual_skill_memory_v2",
                "failure_autopsy_reports",
                "certainty_brain",
                "computer_vision_skill_learning",
                "personal_automation_daemon",
                "notification_intelligence",
                "self_testing_personality",
                "project_memory_per_repo",
                "operator_skill_drivers",
                "personal_learning_roadmap",
                "privacy_firewall_pro",
                "multi_device_command_mesh",
                "autonomous_release_engine",
                "decision_memory",
                "autonomous_skill_improvement",
                "live_workspace_coach",
                "personal_memory_debate",
                "focus_protection_mode",
                "real_app_apprenticeship",
                "personal_project_cto",
                "conversation_continuity",
                "local_voice_brain",
                "trust_dashboard",
            ],
        }

    return app


def require_user(authorization: str = Header(default="")) -> str:
    if not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token.")
    token = authorization.split(" ", 1)[1].strip()
    payload = _decode_or_401(token, token_type="access")
    return str(payload["sub"])


def _require_user_from_header_or_token(authorization: str, token: str) -> str:
    raw = token.strip()
    if not raw and authorization.lower().startswith("bearer "):
        raw = authorization.split(" ", 1)[1].strip()
    if not raw:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token.")
    payload = _decode_or_401(raw, token_type="access")
    return str(payload["sub"])


def _decode_or_401(token: str, *, token_type: str) -> dict[str, Any]:
    try:
        return api_auth.decode_token(token, token_type=token_type)
    except api_auth.AuthError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc


def _decode_reference_image_data(request: ProjectMemoryReferenceImageRequest) -> tuple[bytes, str]:
    raw = (request.data_url or request.base64 or "").strip()
    if not raw:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Reference image data is required.")
    content_type = request.content_type
    encoded = raw
    if raw.startswith("data:"):
        if "," not in raw:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Reference image data URL is invalid.")
        header, encoded = raw.split(",", 1)
        media_type = header.removeprefix("data:").split(";", 1)[0].strip()
        if media_type and not content_type:
            content_type = media_type
    try:
        return base64.b64decode(encoded, validate=True), content_type
    except (binascii.Error, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Reference image data is not valid base64.") from exc


CHAT_UPLOAD_DIR = DATA_DIR / "chat_uploads"
MAX_CHAT_ATTACHMENT_BYTES = 20 * 1024 * 1024
ALLOWED_CHAT_ATTACHMENT_SUFFIXES = {
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
    ".gif",
    ".pdf",
    ".doc",
    ".docx",
    ".txt",
    ".md",
    ".csv",
    ".xls",
    ".xlsx",
    ".ppt",
    ".pptx",
}


def _store_chat_attachment(request: ChatAttachmentRequest) -> dict[str, Any]:
    raw = (request.data_url or request.base64 or "").strip()
    if not raw:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Attachment data is empty.")
    content_type = _clean_content_type(request.content_type)
    encoded = raw
    if raw.startswith("data:"):
        if "," not in raw:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Attachment data URL is invalid.")
        header, encoded = raw.split(",", 1)
        if ";base64" not in header:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Attachment data URL must be base64.")
        media_type = header.removeprefix("data:").split(";", 1)[0].strip()
        content_type = _clean_content_type(media_type) or content_type
    try:
        content = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Attachment data is not valid base64.") from exc
    if len(content) > MAX_CHAT_ATTACHMENT_BYTES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Attachment is larger than 20MB.")
    original_name = Path(str(request.filename or "attachment")).name or "attachment"
    suffix = Path(original_name).suffix.lower()
    if suffix not in ALLOWED_CHAT_ATTACHMENT_SUFFIXES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Attachment file type is not allowed.")
    CHAT_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now(dt.timezone.utc).astimezone().strftime("%Y%m%d_%H%M%S_%f")
    stored_name = f"{stamp}_{_slug_filename(Path(original_name).stem)}{suffix}"
    path = (CHAT_UPLOAD_DIR / stored_name).resolve()
    root = CHAT_UPLOAD_DIR.resolve()
    if not str(path).lower().startswith(str(root).lower()):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid attachment filename.")
    path.write_bytes(content)
    is_image = content_type.startswith("image/") or suffix in {".png", ".jpg", ".jpeg", ".webp", ".gif"}
    return {
        "filename": original_name,
        "stored_filename": stored_name,
        "path": str(path),
        "content_type": content_type,
        "size_bytes": len(content),
        "kind": "image" if is_image else "document",
    }


def _slug_filename(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9._-]+", "-", str(value or "attachment")).strip("-._")
    return (slug or "attachment")[:80]


def _clean_content_type(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9.+/;-]", "", str(value or ""))[:160]


def _cors_origins() -> list[str]:
    raw = str(config_value("api_cors_origins", "http://localhost:3000,http://127.0.0.1:3000,http://localhost:5173"))
    origins = {origin.strip() for origin in raw.split(",") if origin.strip()}
    for port in range(3000, 3006):
        origins.add(f"http://localhost:{port}")
        origins.add(f"http://127.0.0.1:{port}")
    return sorted(origins)


def _recent_logs(lines: int) -> dict[str, Any]:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    files = sorted(LOG_DIR.glob("*.log"), key=lambda path: path.stat().st_mtime, reverse=True)
    if not files:
        return {"file": "", "lines": []}
    latest = files[0]
    return {"file": str(latest), "lines": _tail(latest, lines)}


_PC_AWARENESS_REFRESH_LOCK = threading.Lock()
_PC_AWARENESS_REFRESHING = False
_DASHBOARD_SNAPSHOT_LOCK = threading.Lock()
_DASHBOARD_SNAPSHOT_CACHE: dict[str, Any] | None = None
_DASHBOARD_SNAPSHOT_CACHE_TIME = 0.0


def _invalidate_dashboard_snapshot_cache() -> None:
    global _DASHBOARD_SNAPSHOT_CACHE, _DASHBOARD_SNAPSHOT_CACHE_TIME
    with _DASHBOARD_SNAPSHOT_LOCK:
        _DASHBOARD_SNAPSHOT_CACHE = None
        _DASHBOARD_SNAPSHOT_CACHE_TIME = 0.0


def _android_device_mesh_dashboard(sync: dict[str, Any] | None = None) -> dict[str, Any]:
    android_status = _snapshot_value(android_companion.status, {})
    phone_status = _snapshot_value(phone_bridge.status, {})
    phone_devices = _snapshot_value(phone_bridge.list_devices, [])
    phone_events = _snapshot_value(lambda: phone_bridge.recent_events(limit=16), [])
    mesh_status = _snapshot_value(phone_mesh.status, {})
    handoffs = _snapshot_value(lambda: phone_mesh.recent(limit=16), [])
    command_status = _snapshot_value(device_command_mesh.status, {})
    commands = _snapshot_value(lambda: device_command_mesh.recent(limit=16), [])
    notifications = _snapshot_value(lambda: notification_center.list_notifications(limit=30), [])
    phone_notifications = [
        item
        for item in notifications
        if any(term in str(item.get("category") or item.get("source") or "").lower() for term in ("phone", "android", "handoff", "notification"))
    ][:8]
    app_devices = android_status.get("app_devices") or []
    bridge_devices = phone_devices or ([phone_status.get("default_device")] if phone_status.get("default_device") else [])
    captures = _decorate_android_files(android_status.get("recent_files") or _snapshot_value(lambda: android_companion.recent_files(limit=12), []))
    adb_devices = phone_status.get("adb_devices") or []
    active_nodes = 1 + len(app_devices) + len(bridge_devices) + len(adb_devices)
    ready = bool(app_devices or bridge_devices or phone_status.get("adb_connected") or phone_status.get("ntfy_configured"))
    summary = android_status.get("summary") or phone_status.get("setup_hint") or "Android mesh is standing by."
    return {
        "timestamp": dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds"),
        "ready": ready,
        "active_nodes": active_nodes,
        "summary": summary,
        "android": android_status,
        "phone": phone_status,
        "phone_devices": phone_devices,
        "phone_events": phone_events,
        "phone_notifications": phone_notifications,
        "phone_mesh": mesh_status,
        "handoffs": handoffs,
        "device_mesh": command_status,
        "commands": commands,
        "captures": captures,
        "sync": sync or {},
    }


def _decorate_android_files(files: list[dict[str, Any]]) -> list[dict[str, Any]]:
    decorated: list[dict[str, Any]] = []
    for item in files or []:
        row = dict(item)
        file_id = row.get("id")
        if file_id:
            url = f"/android-companion/app/files/{file_id}"
            row["url"] = url
            if str(row.get("mime_type") or "").lower().startswith("image/"):
                row["image_url"] = url
        decorated.append(row)
    return decorated


def _integrations_dashboard(refresh: dict[str, Any] | None = None) -> dict[str, Any]:
    google_status = _snapshot_value(google_workspace.status, {})
    app_links = dict(app_integrations.APP_LINKS)
    local_calendar = _snapshot_value(lambda: app_integrations.list_calendar_events(limit=20), [])
    reminders = _snapshot_value(lambda: app_integrations.list_reminders(include_done=False, limit=20), [])
    workspace = _snapshot_value(app_integrations.workspace_overview, {})
    home_status = _snapshot_value(home_assistant.status, {})
    home_states = _snapshot_value(home_assistant.list_states, {"devices": []}) if home_status.get("configured") else {"devices": []}
    browser = _snapshot_value(lambda: browser_extension_bridge.status(limit=8), {})
    events = _snapshot_value(lambda: event_nervous_system.recent_events(limit=16), [])
    notifications = _snapshot_value(lambda: notification_center.list_notifications(limit=16), [])
    recent_logs = _snapshot_value(lambda: _recent_logs(80), {"lines": []})
    app_launch = _integration_app_launch(app_links)
    google_modules = _integration_google_modules(google_status, local_calendar, workspace)
    home_cards = _integration_home_cards(home_status, home_states)
    operations = _integration_operation_rows(google_status, home_status, browser, events, notifications, recent_logs)
    connected_systems = int(bool(google_status.get("authorized"))) + int(bool(home_status.get("reachable"))) + int(bool((browser.get("contexts") or [])))
    return {
        "timestamp": dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds"),
        "summary": f"{connected_systems} connected external system(s); {len(app_launch)} launch target(s) available.",
        "google": {
            "status": google_status,
            "modules": google_modules,
            "connected": bool(google_status.get("authorized")),
            "configured": bool(google_status.get("configured")),
            "mode": google_status.get("mode") or ("oauth" if google_status.get("authorized") else "not_connected"),
        },
        "app_launch": {
            "total": len(app_launch),
            "items": app_launch,
        },
        "home_assistant": {
            "status": home_status,
            "cards": home_cards,
            "configured": bool(home_status.get("configured")),
            "reachable": bool(home_status.get("reachable")),
        },
        "operations_log": operations,
        "browser": browser,
        "reminders": reminders,
        "refresh": refresh or {},
        "thought_summary": _integration_thought_summary(google_status, home_status, browser, operations),
    }


def _integration_google_modules(google_status: dict[str, Any], local_calendar: list[dict[str, Any]], workspace: dict[str, Any]) -> list[dict[str, Any]]:
    scopes = {str(scope).lower() for scope in google_status.get("scopes") or []}
    authorized = bool(google_status.get("authorized"))
    configured = bool(google_status.get("configured"))
    deps = google_status.get("dependencies") or {}
    setup_label = "CONFIGURE" if not configured else "INSTALL DEPS" if not deps.get("installed", True) else "CONNECT"
    setup_detail = "OAuth ready" if configured and deps.get("installed", True) else "Missing OAuth setup"
    module_specs = [
        ("gmail", "Gmail", "gmail", "Syncing every 5m", "UP_TO_DATE"),
        ("calendar", "Calendar", "calendar", "Next: Daily Sync", f"{len(local_calendar)} EVENTS"),
        ("docs", "Docs", "documents", f"{int(workspace.get('total_files') or 0)} local files indexed", "READ_ONLY"),
        ("sheets", "Sheets", "spreadsheets", "Workspace sheet actions", "ACTIVE"),
    ]
    rows: list[dict[str, Any]] = []
    for key, label, scope_hint, detail, status_label in module_specs:
        scope_present = any(scope_hint in scope for scope in scopes)
        active = bool(authorized and scope_present)
        rows.append(
            {
                "id": key,
                "label": label,
                "detail": detail if active else setup_detail,
                "active": active,
                "status": status_label if active else setup_label,
                "toggle_enabled": active,
            }
        )
    return rows


def _integration_app_launch(app_links: dict[str, str]) -> list[dict[str, Any]]:
    labels = {
        "figma": "Figma",
        "vscode": "VS Code",
        "discord": "Discord",
        "whatsapp": "WhatsApp",
        "notion": "Notion",
        "slack": "Slack",
        "calendar": "Calendar",
        "spotify": "Spotify",
        "postman": "Postman",
        "linear": "Linear",
        "zoom": "Zoom",
        "github": "GitHub",
        "gmail": "Gmail",
        "docs": "Docs",
    }
    order = ["figma", "vscode", "discord", "whatsapp", "notion", "slack", "calendar", "spotify", "postman", "linear", "zoom", "github", "gmail", "docs"]
    return [
        {
            "id": key,
            "label": labels.get(key, key.title()),
            "url": app_links.get(key, ""),
            "available": bool(app_links.get(key)),
        }
        for key in order
        if key in app_links
    ]


def _integration_home_cards(home_status: dict[str, Any], home_states: dict[str, Any]) -> list[dict[str, Any]]:
    devices = home_states.get("devices") or []
    cards: list[dict[str, Any]] = []
    preferred = [item for item in devices if str(item.get("domain") or "").lower() in {"light", "switch", "sensor", "binary_sensor"}]
    for item in preferred[:2]:
        attrs = item.get("attributes") or {}
        domain = str(item.get("domain") or "").lower()
        state = str(item.get("state") or "unknown")
        title = str(item.get("friendly_name") or item.get("entity_id") or "Home entity")
        value = ""
        level = None
        if "current_power_w" in attrs:
            value = f"{attrs.get('current_power_w')} W"
        elif "temperature" in attrs:
            value = f"{attrs.get('temperature')}{attrs.get('unit_of_measurement') or ''}"
        elif "brightness" in attrs:
            try:
                level = round((float(attrs.get("brightness") or 0) / 255) * 100)
            except Exception:
                level = None
        if level is None and domain == "light" and state == "on":
            level = 100
        cards.append(
            {
                "id": item.get("entity_id") or title,
                "title": title,
                "subtitle": item.get("entity_id") or domain,
                "domain": domain,
                "state": state,
                "state_label": "ON" if state == "on" else state.upper(),
                "value": value,
                "level": level,
            }
        )
    if cards:
        return cards
    if home_status.get("configured"):
        return [
            {
                "id": "home-assistant",
                "title": "Home Assistant",
                "subtitle": home_status.get("url") or "Local controller",
                "domain": "home",
                "state": "reachable" if home_status.get("reachable") else "offline",
                "state_label": "ACTIVE" if home_status.get("reachable") else "OFFLINE",
                "value": home_status.get("summary") or "",
                "level": None,
            }
        ]
    return [
        {
            "id": "home-assistant-setup",
            "title": "Home Assistant",
            "subtitle": "Set HOME_ASSISTANT_URL",
            "domain": "home",
            "state": "not_configured",
            "state_label": "SETUP",
            "value": "Token not configured",
            "level": None,
        }
    ]


def _integration_operation_rows(
    google_status: dict[str, Any],
    home_status: dict[str, Any],
    browser: dict[str, Any],
    events: list[dict[str, Any]],
    notifications: list[dict[str, Any]],
    logs: dict[str, Any],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    rows.append(
        {
            "id": "google-status",
            "timestamp": dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="milliseconds"),
            "system": "Google Workspace",
            "event": "OAuth status checked",
            "status": "SUCCESS" if google_status.get("authorized") else "SETUP",
            "payload": {"configured": google_status.get("configured"), "authorized": google_status.get("authorized")},
        }
    )
    rows.append(
        {
            "id": "home-status",
            "timestamp": dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="milliseconds"),
            "system": "Home Assistant",
            "event": home_status.get("summary") or "Controller status checked",
            "status": "ACTIVE" if home_status.get("reachable") else "OFFLINE",
            "payload": {"configured": home_status.get("configured"), "url": home_status.get("url", "")},
        }
    )
    for item in browser.get("console") or []:
        level = str(item.get("level") or "log").upper()
        rows.append(
            {
                "id": f"browser-console-{item.get('id')}",
                "timestamp": item.get("timestamp") or "",
                "system": "Browser Ext",
                "event": item.get("message") or "Console event",
                "status": "ERROR" if level in {"ERROR", "WARN", "WARNING"} else "INFO",
                "payload": {"level": level, "url": item.get("url", "")},
            }
        )
    for item in events[:8]:
        rows.append(
            {
                "id": f"event-{item.get('id')}",
                "timestamp": item.get("timestamp") or "",
                "system": item.get("source") or "Event System",
                "event": item.get("title") or item.get("summary") or item.get("event_type") or "System event",
                "status": "TRIGGER" if item.get("status") == "open" else str(item.get("status") or "EVENT").upper(),
                "payload": item.get("metadata") or {},
            }
        )
    for item in notifications[:5]:
        rows.append(
            {
                "id": f"notification-{item.get('id')}",
                "timestamp": item.get("updated_at") or item.get("timestamp") or "",
                "system": item.get("source") or "Notification Center",
                "event": item.get("title") or item.get("message") or "Notification",
                "status": str(item.get("status") or "unread").upper(),
                "payload": {"category": item.get("category"), "severity": item.get("severity")},
            }
        )
    for index, line in enumerate((logs.get("lines") or [])[-6:]):
        rows.append(
            {
                "id": f"log-{index}",
                "timestamp": "",
                "system": "Runtime Log",
                "event": str(line)[-180:],
                "status": "INFO",
                "payload": {"file": logs.get("file", "")},
            }
        )
    return sorted(rows, key=lambda item: str(item.get("timestamp") or ""), reverse=True)[:12]


def _integration_thought_summary(google_status: dict[str, Any], home_status: dict[str, Any], browser: dict[str, Any], operations: list[dict[str, Any]]) -> str:
    error_count = len([row for row in operations if str(row.get("status") or "").lower() in {"error", "offline"}])
    if not google_status.get("authorized"):
        return "Google Workspace is not authenticated yet. Connect OAuth to unlock Gmail, Calendar, Docs, and Sheets streams."
    if home_status.get("configured") and not home_status.get("reachable"):
        return "Home Assistant is configured but unreachable. Check the local URL or long-lived token before running device actions."
    queued = len([item for item in browser.get("actions") or [] if item.get("status") == "queued"])
    if queued:
        return f"Browser extension has {queued} queued action(s). Keep the extension open to complete pending web tasks."
    if error_count:
        return f"Integration monitor found {error_count} issue signal(s). Review the operations log before high-trust automation."
    return "Integration streams are stable. App launch links and local controllers are ready for supervised actions."


def _reliability_dashboard(score: dict[str, Any] | None = None, benchmark_refresh: dict[str, Any] | None = None) -> dict[str, Any]:
    evaluation = _snapshot_value(lambda: evaluation_lab.summary(limit=30), {})
    events = _snapshot_value(lambda: evaluation_lab.recent_events(limit=40), [])
    voice = _snapshot_value(lambda: voice_reliability.summary(limit=12), {})
    voice_samples = _snapshot_value(lambda: voice_reliability.recent_samples(limit=12), [])
    score_status = {"latest": score} if score else _snapshot_value(reliability_score.status, {})
    benchmark = _snapshot_value(model_benchmark_lab.status, {})
    agent_quality = _snapshot_value(agent_quality_manager.status, {})
    task_counts = _snapshot_value(task_queue.counts, {})
    latest_score = score_status.get("latest") or {}
    scores = latest_score.get("scores") or {}
    counts = evaluation.get("counts") or {}
    failed_commands = int(counts.get("failed_tool") or 0) + int(counts.get("agent_failure") or 0) + int(task_counts.get("failed") or 0)
    completed = int((evaluation.get("tasks") or {}).get("completed") or task_counts.get("done") or 0)
    tool_success = _percent(completed, completed + failed_commands)
    latency_ms = _reliability_latency_ms(evaluation, benchmark)
    stt_accuracy = _reliability_stt_accuracy(voice, scores)
    false_claims = int(counts.get("unsupported_claim") or 0)
    slow = int(counts.get("slow_response") or 0)
    stuck = int(counts.get("task_stuck") or 0)
    metrics = [
        {"id": "stt_accuracy", "label": "STT Accuracy", "value": stt_accuracy, "unit": "%", "delta": _stt_delta_label(voice), "tone": "blue"},
        {"id": "avg_latency", "label": "Avg Latency", "value": latency_ms, "unit": "ms", "tone": "blue"},
        {"id": "tool_success", "label": "Tool Success", "value": tool_success, "unit": "%", "tone": "blue"},
        {"id": "false_claims", "label": "False Claims", "value": false_claims, "unit": "", "badge": "SAFE" if false_claims == 0 else "REVIEW", "tone": "danger" if false_claims else "neutral"},
        {"id": "failed_commands", "label": "Failed Cmds", "value": failed_commands, "unit": "", "tone": "danger" if failed_commands else "neutral"},
        {"id": "slow_responses", "label": "Slow Resp", "value": slow, "unit": "", "tone": "warn" if slow else "neutral"},
        {"id": "agent_stuck", "label": "Agent Stuck", "value": stuck, "unit": "", "tone": "danger" if stuck else "neutral"},
    ]
    benchmark_rows = _reliability_benchmark_rows(benchmark, scores, agent_quality)
    return {
        "timestamp": dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds"),
        "metrics": metrics,
        "score": latest_score,
        "voice": {
            "summary": voice,
            "samples": voice_samples,
            "backend_active": _reliability_active_backend(voice_samples, voice),
            "accuracy": stt_accuracy,
        },
        "evaluation": {
            "summary": evaluation,
            "events": _reliability_event_rows(events),
        },
        "benchmark": {
            "rows": benchmark_rows,
            "recent": benchmark.get("recent") or [],
            "summary": benchmark.get("summary") or "Model benchmark lab is ready.",
            "refresh": benchmark_refresh or {},
        },
        "thought_summary": _reliability_thought_summary(counts, stt_accuracy, tool_success, latency_ms),
        "active_monitors": _reliability_monitors(events, voice_samples, agent_quality),
    }


def _reliability_stt_accuracy(voice: dict[str, Any], scores: dict[str, Any]) -> float:
    backends = voice.get("backends") or {}
    total = 0
    mistakes = 0
    for item in backends.values():
        total += int(item.get("samples") or 0)
        mistakes += int(item.get("mistakes") or 0)
    if total:
        return round(max(0.0, min(100.0, ((total - mistakes) / total) * 100)), 1)
    return round(float(scores.get("stt_accuracy") or 0), 1)


def _reliability_latency_ms(evaluation: dict[str, Any], benchmark: dict[str, Any]) -> int | None:
    averages = evaluation.get("averages") or {}
    for key in ("e2e_latency_ms_from_logs", "latency", "slow_response"):
        value = averages.get(key)
        if value:
            return int(round(float(value)))
    recent = benchmark.get("recent") or []
    latencies = [int(item.get("latency_ms") or 0) for item in recent if int(item.get("latency_ms") or 0) > 0]
    if latencies:
        return int(round(sum(latencies) / len(latencies)))
    return None


def _reliability_active_backend(samples: list[dict[str, Any]], voice: dict[str, Any]) -> str:
    if samples:
        return str(samples[0].get("backend") or "voice").replace("_", "-")
    backends = voice.get("backends") or {}
    if not backends:
        return "voice"
    return max(backends.items(), key=lambda item: int((item[1] or {}).get("samples") or 0))[0]


def _reliability_event_rows(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    priority = {"failed_tool": 0, "unsupported_claim": 1, "agent_failure": 2, "slow_response": 3, "task_stuck": 4, "stt_mistake": 5, "task_completed": 6, "latency": 7}
    rows = sorted(events or [], key=lambda item: (priority.get(str(item.get("category") or ""), 8), -int(item.get("id") or 0)))
    return rows[:12]


def _reliability_benchmark_rows(benchmark: dict[str, Any], scores: dict[str, Any], agent_quality: dict[str, Any]) -> list[dict[str, Any]]:
    labels = {
        "coding": "Coding Proficiency",
        "writing": "Writing & Synthesis",
        "math": "Mathematical Reasoning",
        "fast_reply": "Latency Optimization",
        "tool_planning": "Tool Use Planning",
    }
    latest_by_task: dict[str, dict[str, Any]] = {}
    for item in benchmark.get("recent") or []:
        latest_by_task.setdefault(str(item.get("task_type") or ""), item)
    quality_by_task: dict[str, float] = {}
    for item in agent_quality.get("leaderboard") or []:
        task_type = str(item.get("task_type") or "")
        quality_by_task[task_type] = max(float(item.get("avg_score") or 0), quality_by_task.get(task_type, 0.0))
    fallbacks = {
        "coding": scores.get("task_completion") or scores.get("tool_success") or 0,
        "writing": scores.get("sample_count") or scores.get("honesty") or 0,
        "math": scores.get("honesty") or 0,
        "fast_reply": scores.get("latency") or 0,
        "tool_planning": scores.get("tool_success") or 0,
    }
    rows: list[dict[str, Any]] = []
    for task_type, label in labels.items():
        item = latest_by_task.get(task_type) or {}
        if item:
            score = round(float(item.get("quality") or 0) * 100)
            source = str(item.get("provider") or item.get("status") or "benchmark")
        elif quality_by_task.get(task_type):
            score = round(quality_by_task[task_type] * 100)
            source = "agent_quality"
        else:
            score = round(float(fallbacks.get(task_type) or 0))
            source = "reliability_score"
        rows.append({"id": task_type, "label": label, "score": max(0, min(100, int(score))), "source": source})
    return rows


def _reliability_thought_summary(counts: dict[str, Any], stt_accuracy: float, tool_success: float, latency_ms: int | None) -> str:
    failed = int(counts.get("failed_tool") or 0) + int(counts.get("agent_failure") or 0)
    unsupported = int(counts.get("unsupported_claim") or 0)
    slow = int(counts.get("slow_response") or 0)
    if failed:
        return f"Observation: tool reliability has {failed} recent failure signal(s). Review tool schemas and auth before high-risk automation."
    if unsupported:
        return f"Observation: evidence gate caught {unsupported} unsupported claim signal(s). Keep success language tied to tool results."
    if slow or (latency_ms and latency_ms > 3000):
        return "Observation: response latency is elevated. Prefer fast routes for voice replies and defer heavier model calls to agents."
    if stt_accuracy < 95:
        return f"Observation: STT accuracy is {stt_accuracy:.1f}%. Continue using Deepgram realtime and record corrections when Friday mishears you."
    return f"Observation: reliability is stable. Tool success is {tool_success:.1f}% and no unsupported claims are currently flagged."


def _reliability_monitors(events: list[dict[str, Any]], samples: list[dict[str, Any]], agent_quality: dict[str, Any]) -> dict[str, Any]:
    sources = {str(item.get("source") or "").strip() for item in events or [] if item.get("source")}
    if samples:
        sources.add("voice_reliability")
    if agent_quality.get("leaderboard"):
        sources.add("agent_quality")
    active = sorted(source for source in sources if source)[:6]
    return {"count": len(active), "sources": active}


def _stt_delta_label(voice: dict[str, Any]) -> str:
    aliases = len(voice.get("learned_aliases") or [])
    return f"+{aliases} alias" if aliases == 1 else f"+{aliases} aliases" if aliases else ""


def _percent(numerator: int | float, denominator: int | float) -> float:
    try:
        den = float(denominator)
        if den <= 0:
            return 100.0
        return round(max(0.0, min(100.0, (float(numerator) / den) * 100)), 1)
    except Exception:
        return 0.0


def _dashboard_snapshot() -> dict[str, Any]:
    global _DASHBOARD_SNAPSHOT_CACHE, _DASHBOARD_SNAPSHOT_CACHE_TIME
    ttl = max(0.5, float(config_value("dashboard_snapshot_cache_seconds", 3.0)))
    now = time.time()
    with _DASHBOARD_SNAPSHOT_LOCK:
        if _DASHBOARD_SNAPSHOT_CACHE and now - _DASHBOARD_SNAPSHOT_CACHE_TIME <= ttl:
            return dict(_DASHBOARD_SNAPSHOT_CACHE)
    project_memory_status = _snapshot_value(lambda: project_memory.status(limit=8), None)
    payload = {
        "timestamp": dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds"),
        "status": _snapshot_value(background_agents.worker_status, None),
        "tasks": _snapshot_value(lambda: [_decorate_task(task) for task in task_queue.list_tasks(limit=80)], []),
        "agents": _snapshot_value(agents.roster, []),
        "offices": _snapshot_value(agent_office.all_offices, []),
        "missions": _snapshot_value(lambda: mission_control.list_missions(limit=8), []),
        "missionStatus": _snapshot_value(mission_control.status, None),
        "projects": project_memory_status.get("projects", []) if isinstance(project_memory_status, dict) else [],
        "projectMemory": project_memory_status,
        "projectReferences": _snapshot_value(lambda: project_memory.list_reference_images(limit=12), []),
        "approvals": _snapshot_value(lambda: approval_inbox.items(limit=10), []),
        "approvalSummary": _snapshot_value(lambda: approval_inbox.summary(limit=8), None),
        "thoughts": _snapshot_value(lambda: agent_thought_bus.summary(limit=8), None),
        "pcAwareness": _snapshot_value(_dashboard_pc_awareness, None),
        "notifications": _snapshot_value(lambda: notification_center.summary(limit=8), None),
        "logs": _snapshot_value(lambda: _recent_logs(80), {"lines": []}),
        "audit": _snapshot_value(lambda: audit_log.recent(limit=8), []),
        "contextFusion": _snapshot_value(context_fusion.status, None),
        "conversationContinuity": _snapshot_value(conversation_continuity.status, None),
        "android": _snapshot_value(_android_device_mesh_dashboard, None),
        "reliability": _snapshot_value(_reliability_dashboard, None),
        "integrations": _snapshot_value(_integrations_dashboard, None),
        "codebaseStandards": _snapshot_value(codebase_standards.status, None),
        "agentQuality": _snapshot_value(agent_quality_manager.status, None),
        "evaluation": _snapshot_value(lambda: evaluation_lab.summary(limit=6), None),
        "blackboard": _snapshot_value(lambda: agent_blackboard.summary(limit=8), None),
        "contractsSummary": _snapshot_value(task_contracts.summary, None),
        "skillsSummary": _snapshot_value(skill_library.skill_summary, None),
    }
    with _DASHBOARD_SNAPSHOT_LOCK:
        _DASHBOARD_SNAPSHOT_CACHE = dict(payload)
        _DASHBOARD_SNAPSHOT_CACHE_TIME = time.time()
    return payload


def _snapshot_value(fn: Any, default: Any) -> Any:
    try:
        return fn()
    except Exception:
        return default


def _dashboard_pc_awareness() -> dict[str, Any]:
    cached = getattr(pc_awareness, "_CACHE", None)
    if isinstance(cached, dict) and cached:
        return dict(cached)
    latest = pc_awareness.latest_snapshot()
    _start_pc_awareness_refresh()
    if latest:
        return latest
    return {
        "available": False,
        "summary": "PC awareness is warming a fresh snapshot.",
        "running_apps": [],
        "installed_apps": [],
        "shortcuts": [],
        "desktop_apps": [],
        "home_screen_apps": [],
        "stats": {},
    }


def _start_pc_awareness_refresh() -> None:
    global _PC_AWARENESS_REFRESHING
    with _PC_AWARENESS_REFRESH_LOCK:
        if _PC_AWARENESS_REFRESHING:
            return
        _PC_AWARENESS_REFRESHING = True
    thread = threading.Thread(target=_refresh_pc_awareness_snapshot, daemon=True, name="dashboard-pc-awareness-refresh")
    thread.start()


def _refresh_pc_awareness_snapshot() -> None:
    global _PC_AWARENESS_REFRESHING
    try:
        pc_awareness.snapshot(force_refresh=True)
    finally:
        with _PC_AWARENESS_REFRESH_LOCK:
            _PC_AWARENESS_REFRESHING = False


def _stream_payload_signature(payload: dict[str, Any]) -> str:
    comparable = _strip_stream_volatiles(payload)
    return json.dumps(comparable, sort_keys=True, ensure_ascii=True, default=str)


def _strip_stream_volatiles(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _strip_stream_volatiles(item) for key, item in value.items() if key != "timestamp"}
    if isinstance(value, list):
        return [_strip_stream_volatiles(item) for item in value]
    return value


async def _stream_snapshot_payload(websocket: WebSocket, token: str, builder: Any, interval_key: str, default_interval: float) -> None:
    try:
        api_auth.decode_token(token, token_type="access")
    except api_auth.AuthError:
        await websocket.close(code=1008)
        return
    await websocket.accept()
    last_payload = ""
    try:
        while True:
            payload = await asyncio.to_thread(builder)
            text = _stream_payload_signature(payload)
            if text != last_payload:
                last_payload = text
                await websocket.send_json(payload)
            await asyncio.sleep(float(config_value(interval_key, default_interval)))
    except WebSocketDisconnect:
        return


def _notification_stream_payload() -> dict[str, Any]:
    payload = notification_center.summary(limit=12)
    payload["timestamp"] = dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds")
    return payload


def _task_stream_payload() -> dict[str, Any]:
    return {
        "timestamp": dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds"),
        "status": background_agents.worker_status(),
        "tasks": [_decorate_task(task) for task in task_queue.list_tasks(limit=80)],
        "offices": agent_office.all_offices(),
        "blackboard": agent_blackboard.summary(limit=8),
        "thoughts": agent_thought_bus.summary(limit=8),
        "approvals": approval_inbox.summary(limit=8),
        "evaluation": evaluation_lab.summary(limit=6),
        "guardian": proactive_guardian.status(),
        "notifications": notification_center.summary(limit=8),
        "goals": goal_manager.progress_summary(limit=5),
        "pc_timeline": pc_timeline.summary(),
        "events": event_nervous_system.summary(limit=8),
        "daily_companion": daily_companion.status(),
        "finance": personal_finance.summary(),
        "project_watchdog": project_watchdog.status(),
        "codebase_standards": codebase_standards.status(),
        "model_router": model_router_brain.summary(),
        "self_debugger": self_debugger.analyze_recent(limit=6),
        "emotion": emotion_tone.summary(),
        "crm": personal_crm.summary(),
        "learning_coach": learning_coach.progress(),
        "research_briefings": research_briefings.summary(),
        "workspace_context": contextual_workspace.summary(),
        "offline_survival": offline_survival.status(),
        "personal_timeline": personal_data_timeline.summary(),
        "skill_training": skill_training_studio.summary(),
        "executive": executive_capabilities.summary(),
        "missions": mission_control.status(),
        "qa_lab": autonomous_qa_lab.status(),
        "error_radar": error_radar.status(),
        "release_manager": release_manager.status(),
        "semantic_search": semantic_search.status(),
        "operating_rhythm": operating_rhythm.summary(),
        "browser_extension": browser_extension_bridge.status(limit=4),
        "app_state_memory": app_state_memory.summary(limit=4),
        "android_companion_app": android_companion.status(),
        "autonomous_debugger": autonomous_debugger.status(),
        "command_memory": personal_command_memory.summary(limit=4),
        "calendar_email": calendar_email_assistant.status(),
        "autonomous_learning": autonomous_learning.summary(),
        "knowledge_graph": knowledge_graph.summary(),
        "environment": environment_awareness.status(),
        "proof_reports": trust_proof.summary(),
        "continuity": continuity_brain.status(),
        "context_fusion": context_fusion.status(),
        "deep_project_autopilot": deep_project_autopilot.status(),
        "silence": context_aware_silence.summary(),
        "browser_pc_copilot": browser_pc_copilot.status(),
        "skill_evolution": skill_evolution.status(),
        "safety_guardian": personal_safety_guardian.status(),
        "phone_mesh": phone_mesh.status(),
        "agent_scheduler": agent_scheduler.status(),
        "test_build_monitor": test_build_monitor.status(),
        "reliability_score": reliability_score.status(),
        "model_benchmark": model_benchmark_lab.status(),
        "deployment_brain": deployment_brain.status(),
        "os_autopilot": os_autopilot.status(),
        "version_guardian": version_guardian.status(),
        "awareness_graph": awareness_graph.status(),
        "fix_loop": autonomous_fix_loop.status(),
        "browser_pro": browser_extension_pro.status(),
        "memory_review_pro": personal_memory_review.status(),
        "app_mastery": app_operator_mastery.status(),
        "local_ai_search": local_ai_search.status(),
        "life_os": life_os_mode.status(),
        "security_guardian_pro": security_guardian_pro.status(),
        "cloud_worker": cloud_worker_mode.status(),
        "autonomy_engine": autonomy_engine.status(),
        "certainty_brain": certainty_brain.summary(),
        "vision_skill_learning": vision_skill_learning.summary(),
        "automation_daemon": personal_automation_daemon.status(),
        "notification_intelligence": notification_intelligence.status(),
        "self_testing": self_testing_personality.status(),
        "project_memory": project_memory.status(),
        "operator_skills": operator_skills.status(),
        "learning_roadmap": learning_roadmap.status(),
        "privacy_firewall_pro": privacy_firewall_pro.status(),
        "device_command_mesh": device_command_mesh.status(),
        "release_engine": autonomous_release_engine.status(),
        "decision_memory": decision_memory.status(),
        "skill_improvement": skill_improvement.status(),
        "workspace_coach": live_workspace_coach.status(),
        "memory_debate": memory_debate.status(),
        "focus_protection": focus_protection.status(),
        "app_apprenticeship": app_apprenticeship.status(),
        "project_cto": project_cto.status(),
        "conversation_continuity": conversation_continuity.status(),
        "local_voice_brain": local_voice_brain.status(),
        "trust_dashboard": trust_dashboard.status(),
        "agent_quality": agent_quality_manager.status(),
        "agent_lifecycle": agent_lifecycle.status(),
        "agent_council": agent_council.status(),
        "do_not_forget": do_not_forget.status(),
        "dev_server_copilot": dev_server_copilot.status(),
        "code_change_simulator": code_change_simulator.status(),
        "refactor_planner": refactor_planner.status(),
        "taste_engine": personal_taste_engine.status(),
        "memory_constitution": memory_constitution.status(),
        "reality_check": reality_check.status(),
        "agent_simulation": agent_simulation_sandbox.status(),
        "command_graph": command_graph.status(),
        "emotional_timing": emotional_timing.status(),
        "visual_skill_memory": visual_skill_memory_v2.status(),
        "failure_autopsy": failure_autopsy.status(),
    }


def _decorate_task(task: dict[str, Any] | None) -> dict[str, Any]:
    if not task:
        return {}
    item = dict(task)
    task_id = int(item.get("id") or 0)
    item["progress_percent"] = task_queue.task_progress(task_id, str(item.get("status") or "")) if task_id else 0
    item["is_question"] = isinstance(item.get("input"), dict) and item["input"].get("source") == "agent_question"
    item["from_agent"] = item["input"].get("from_agent", "") if isinstance(item.get("input"), dict) else ""
    if task_id:
        item["contract"] = task_contracts.get_contract(task_id)
    return item


def _tail(path: Path, lines: int) -> list[str]:
    try:
        return path.read_text(encoding="utf-8", errors="ignore").splitlines()[-lines:]
    except Exception:
        return []


def _desktop_task_action_payload(session_id: int, reply: str) -> dict[str, Any]:
    session = desktop_tasks.get_session(session_id, include_steps=True)
    payload = _decorate_desktop_session(session, include_steps=True) if session else {"id": session_id}
    payload["reply"] = reply
    return payload


def _start_desktop_task_thread(session_id: int, instruction: str, max_steps: int) -> None:
    def worker() -> None:
        try:
            desktop_vision.run_desktop_task(instruction, session_id=session_id, max_steps=max_steps)
        except Exception as exc:
            desktop_tasks.append_step(
                session_id,
                step_number=0,
                status="failed",
                progress=f"Desktop task worker failed: {exc}",
                details={"error": str(exc)},
            )
            desktop_tasks.finish_session(session_id, "stopped")

    thread = threading.Thread(target=worker, name=f"friday-desktop-task-{session_id}", daemon=True)
    thread.start()


def _decorate_desktop_session(session: dict[str, Any] | None, *, include_steps: bool = False) -> dict[str, Any]:
    if not session:
        return {}
    item = dict(session)
    if include_steps:
        item["steps"] = [_decorate_desktop_step(step) for step in item.get("steps", [])]
    return item


def _decorate_desktop_step(step: dict[str, Any]) -> dict[str, Any]:
    item = dict(step)
    screenshot = str(item.get("screenshot") or "")
    if screenshot:
        item["screenshot_name"] = Path(screenshot).name
        item["screenshot_url"] = f"/desktop/screenshots/{Path(screenshot).name}"
    else:
        item["screenshot_name"] = ""
        item["screenshot_url"] = ""
    return item


def _decorate_visual_status(payload: dict[str, Any]) -> dict[str, Any]:
    item = dict(payload or {})
    latest = item.get("latest_event")
    item["latest_event"] = _decorate_visual_event(latest) if isinstance(latest, dict) else None
    source = str(item.get("source") or "screen")
    live_source = "screen" if source == "both" else source
    item["live_stream_url"] = f"/vision/live/{live_source}" if live_source in {"screen", "camera"} else ""
    return item


def _decorate_visual_event(event: dict[str, Any] | None) -> dict[str, Any]:
    if not event:
        return {}
    item = dict(event)
    source = str(item.get("source") or "").strip().lower()
    frame_name = str(item.get("frame_name") or Path(str(item.get("frame_path") or "")).name)
    item["frame_name"] = frame_name
    item["frame_url"] = f"/vision/frames/{source}/{frame_name}" if source and frame_name else ""
    return item


def _safe_screenshot_path(filename: str) -> Path:
    name = Path(str(filename or "")).name
    if not name:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Screenshot not found.")
    configured = str(config_value("desktop_screenshot_dir", "") or "").strip()
    root = Path(configured).expanduser() if configured else DATA_DIR / "screenshots"
    root = root.resolve()
    target = (root / name).resolve()
    if not str(target).lower().startswith(str(root).lower()):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Screenshot path denied.")
    return target


def _safe_visual_frame_path(source: str, filename: str) -> Path:
    source_name = Path(str(source or "")).name.lower()
    if source_name not in {"screen", "camera"}:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Visual frame not found.")
    name = Path(str(filename or "")).name
    if not name:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Visual frame not found.")
    root = (visual_monitor.frame_root() / source_name).resolve()
    target = (root / name).resolve()
    if not str(target).lower().startswith(str(root).lower()):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Visual frame path denied.")
    return target


app = create_app()
