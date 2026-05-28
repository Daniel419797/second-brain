# Friday Brain-Inspired Architecture Implementation Plan

Status: implemented foundation plus second-pass depth wiring  
Scope: implement deeper continuous world modeling, richer self-reflection, stronger long-term learning, emotional and goal regulation, and adaptive attention over time.  
Important boundary: this plan does not make Friday conscious or human-equivalent. It builds a practical brain-inspired cognitive architecture with observable state, learning loops, safety controls, and testable behavior.

## 1. Current Baseline

Friday already has several brain-like building blocks:

- Perception: speech-to-text, attention name gate, screen screenshots, optional continuous screen/camera monitor, Chrome DOM inspection, Windows UI Automation inspection.
- Executive function: `core/orchestrator.py`, tool routing, direct commands, safety permissions, background agents, task queue.
- Memory: rolling conversation memory, semantic memory, episodic SQLite store, knowledge graph, procedural skill library, competence maps, nightly consolidation.
- Action: PC control, app integrations, desktop task sessions, web search, email, coding assistance, agent team.
- Regulation: CPU guard, proactive speech limits, quiet hours, permission rules, blocked high-risk tasks.
- Self-update: guarded self-update proposal, staging, approval, test, and rollback workflow.

The missing layer is a unified cognitive loop that keeps state over time, compares expected vs observed outcomes, reflects on failures, updates goals, learns durable lessons, and adjusts attention thresholds based on context.

## 2. Target Architecture

The new system should add five cooperating subsystems:

1. Continuous World Model
   - Maintains a lightweight model of the user's environment, current task context, open apps, visible screen state, recent visual/audio changes, active goals, and expected next observations.

2. Self-Reflection
   - Periodically reviews recent actions, failures, confusion, repeated corrections, permission denials, and successful outcomes.
   - Produces concise lessons and self-critiques that can update procedural memory, competence scores, and future behavior.

3. Long-Term Learning
   - Converts repeated patterns into durable skills, app memories, user preferences, and domain knowledge.
   - Uses spaced reinforcement, evidence counts, and confidence levels to avoid learning one-off mistakes.

4. Emotional and Goal Regulation
   - Tracks operational states such as calm, uncertain, focused, overloaded, blocked, and waiting for user.
   - Uses these states to change verbosity, proactivity, risk tolerance, task switching, and whether to ask clarifying questions.

5. Adaptive Attention
   - Learns when to listen more strictly or more permissively.
   - Adjusts wake-name handling, follow-up windows, false-positive suppression, command confidence thresholds, and proactive interruptions based on context.

## Implementation Status

Implemented:

- `core/cognitive_state.py`
- `core/world_model.py`
- `core/self_reflection.py`
- `core/long_term_learning.py`
- `core/goal_regulation.py`
- `core/adaptive_attention.py`
- `core/cognitive_cycle.py`
- Direct commands in `core/orchestrator.py`
- Voice attention event recording in `jarvis.py`
- JWT-protected cognition API endpoints in `api/server.py`
- Dashboard Cognition panel in `apps/web`
- Tests in `tests/test_cognition_modules.py` plus API/orchestrator coverage
- Optional LLM-assisted reflection when `self_reflection_use_llm` is enabled.
- Desktop task sessions create world expectations and feed step observations back into the world model.
- Adaptive attention learned aliases feed the live wake-name list, and runtime strictness can tighten or soften smart-mode listening.
- Repeated high-confidence learning items can create guarded self-update proposals through `core/self_update.py`.
- Dashboard Cognition panel now exposes run/review controls, expectations, entities, goals, reflections, learning, and attention memory.
- `docs/friday_identity.md`, `core/self_model.py`, `core/autobiographical_memory.py`, and `core/evidence_gate.py` add a functional self-model, identity/values file, autobiographical timeline, introspection commands, and an honesty gate that blocks unsupported success claims.
- Protected `/self/*` API endpoints and the dashboard Self Model panel expose Friday's tools, access, limitations, uncertainty, recent failures, and autobiography.

Still future work:

- Full separate dashboard drill-down pages for every cognition table instead of one dense panel.
- STT-provider confidence integration when the active STT backend exposes reliable token/utterance confidence.
- More advanced causal modeling across tasks, tools, screen changes, and user corrections.
- Stronger "why" explanations that connect exact prompts, selected tools, permission decisions, and world observations into a causal trace.

## 3. New Modules

### `core/cognitive_state.py`

Purpose: shared typed state model for all cognition subsystems.

Responsibilities:

- Define dataclasses for:
  - `CognitiveSnapshot`
  - `WorldEntity`
  - `ActiveGoal`
  - `AttentionState`
  - `AffectiveState`
  - `ReflectionRecord`
  - `LearningRecord`
- Normalize timestamps and confidence values.
- Provide JSON-safe serialization helpers.

Persistence:

- No direct database ownership.
- Used by other modules for consistent data contracts.

### `core/world_model.py`

Purpose: maintain a continuous but lightweight understanding of what is happening.

Inputs:

- Recent `episodic_store` events.
- `core/visual_monitor.py` frame events.
- `desktop_task` sessions and screenshots.
- `task_queue` active/pending tasks.
- Current active window and browser/app context from `pc_control`.
- Recent user commands and Friday replies from `memory`.

Data store:

- `data/world_model.sqlite3`

Tables:

- `world_snapshots`
  - `id`
  - `timestamp`
  - `source`
  - `summary`
  - `active_app`
  - `active_window`
  - `visible_state_json`
  - `user_state_json`
  - `confidence`
- `world_entities`
  - `id`
  - `entity_type`
  - `name`
  - `last_seen_at`
  - `state_json`
  - `confidence`
- `world_expectations`
  - `id`
  - `created_at`
  - `expires_at`
  - `goal_id`
  - `expected_observation`
  - `actual_observation`
  - `status`
  - `confidence`

Core functions:

- `capture_snapshot(source: str = "auto") -> dict`
- `recent_snapshots(limit: int = 20) -> list[dict]`
- `current_context() -> dict`
- `upsert_entity(entity_type, name, state, confidence) -> dict`
- `create_expectation(goal_id, expected_observation, ttl_seconds) -> int`
- `resolve_expectations(observation_text) -> list[dict]`
- `planner_context() -> str`

Acceptance criteria:

- Can produce a current context summary without calling a paid API.
- Does not run expensive vision analysis every loop.
- Can answer "what is going on right now?" using recent local observations.
- Stores enough state to compare what Friday expected after an action with what actually happened.

### `core/self_reflection.py`

Purpose: make Friday review itself after work, confusion, and failures.

Inputs:

- Episodic events.
- Permission events.
- Desktop task failures.
- STT ignored-side-speech patterns.
- User corrections such as "you lied", "that did not work", "I said X".
- Task queue results.
- Self-update sessions.

Data store:

- `data/self_reflection.sqlite3`

Tables:

- `reflection_runs`
  - `id`
  - `started_at`
  - `completed_at`
  - `window_start`
  - `window_end`
  - `trigger`
  - `summary`
  - `status`
- `reflection_findings`
  - `id`
  - `run_id`
  - `category`
  - `finding`
  - `evidence_json`
  - `severity`
  - `recommended_change`
  - `promoted`

Core functions:

- `run_reflection(trigger: str = "scheduled") -> dict`
- `reflect_on_command(user_text, reply, success_score) -> dict`
- `recent_findings(limit: int = 20) -> list[dict]`
- `promote_finding(finding_id) -> dict`
- `reflection_context() -> str`

Reflection categories:

- `misheard_command`
- `false_positive`
- `unverified_claim`
- `tool_failure`
- `slow_response`
- `permission_block`
- `user_frustration`
- `successful_pattern`
- `self_update_needed`

Acceptance criteria:

- When the user says an action failed, Friday records a reflection finding.
- Repeated findings become procedural lessons or self-update proposals.
- Reflection is rate-limited and never interrupts voice unless the issue is critical.

### `core/long_term_learning.py`

Purpose: strengthen durable learning beyond one-off memory writes.

Inputs:

- `self_reflection` findings.
- `skill_library` examples.
- `competence` topic scores.
- `memory` facts.
- `knowledge_graph` edges.
- User corrections and preferences.

Data store:

- `data/long_term_learning.sqlite3`

Tables:

- `learning_items`
  - `id`
  - `kind`
  - `topic`
  - `content`
  - `source`
  - `evidence_count`
  - `confidence`
  - `last_reinforced_at`
  - `next_review_at`
  - `status`
- `learning_reviews`
  - `id`
  - `item_id`
  - `reviewed_at`
  - `result`
  - `confidence_delta`

Core functions:

- `record_learning(kind, topic, content, source, confidence=0.5) -> int`
- `reinforce_learning(item_id, evidence) -> dict`
- `due_reviews(limit: int = 10) -> list[dict]`
- `run_reviews() -> dict`
- `learning_context(topic: str) -> str`
- `promote_to_skill(item_id) -> dict`

Learning rules:

- One-off claims start with low confidence.
- Repeated user corrections increase confidence faster than model-generated conclusions.
- Failed actions can lower confidence in a procedure.
- Learned facts can expire or be archived if not reinforced.

Acceptance criteria:

- Friday can learn "when volume says success, verify actual volume first" from repeated failures.
- Friday can prefer successful app-control strategies in future desktop tasks.
- Friday can explain what it learned recently.

### `core/goal_regulation.py`

Purpose: track goals, drives, blockers, uncertainty, and operational mood.

Data store:

- `data/goal_regulation.sqlite3`

Tables:

- `goals`
  - `id`
  - `title`
  - `description`
  - `status`
  - `priority`
  - `source`
  - `created_at`
  - `updated_at`
  - `deadline_at`
  - `progress`
  - `parent_id`
- `goal_events`
  - `id`
  - `goal_id`
  - `timestamp`
  - `event_type`
  - `details_json`
- `affective_state`
  - `id`
  - `timestamp`
  - `state`
  - `arousal`
  - `confidence`
  - `frustration`
  - `focus`
  - `reason`

Operational states:

- `calm`
- `focused`
- `uncertain`
- `blocked`
- `overloaded`
- `recovering`
- `waiting_for_user`

Core functions:

- `create_goal(title, description="", priority=5, source="user") -> int`
- `update_goal(goal_id, status=None, progress=None, note="") -> dict`
- `active_goals(limit: int = 10) -> list[dict]`
- `set_affective_state(state, reason, confidence=0.5) -> dict`
- `current_regulation() -> dict`
- `regulation_prompt_context() -> str`

Behavior changes by state:

- `calm`: normal concise replies.
- `focused`: fewer proactive interruptions, prioritize current task.
- `uncertain`: ask more clarifying questions, avoid claiming success without verification.
- `blocked`: ask user or CEO/agent for missing decision.
- `overloaded`: pause background work, shorten answers, avoid multi-step tasks.
- `recovering`: inspect last failure before retrying.
- `waiting_for_user`: proactive speech can remind gently after cooldown.

Acceptance criteria:

- Friday can say what goal it is currently pursuing.
- Friday can avoid starting low-priority background work while the voice loop is active.
- User frustration or repeated failures increases uncertainty and verification behavior.

### `core/adaptive_attention.py`

Purpose: learn how strict Friday should be about hearing its name and commands.

Inputs:

- STT text, confidence if available, audio duration.
- Attention gate decisions.
- User corrections.
- Accepted vs ignored commands.
- Current active state from `goal_regulation`.
- Background audio false positives.

Data store:

- `data/adaptive_attention.sqlite3`

Tables:

- `attention_events`
  - `id`
  - `timestamp`
  - `transcript`
  - `decision`
  - `reason`
  - `audio_seconds`
  - `accepted`
  - `user_corrected`
  - `context_json`
- `attention_profile`
  - `id`
  - `updated_at`
  - `name_strictness`
  - `followup_window_seconds`
  - `false_positive_rate`
  - `false_negative_rate`
  - `background_noise_score`
  - `profile_json`

Core functions:

- `record_attention_event(transcript, decision, reason, context) -> int`
- `record_user_correction(expected_text, heard_text) -> dict`
- `current_profile() -> dict`
- `recommended_attention_config() -> dict`
- `apply_runtime_attention_hints() -> dict`

Adaptive rules:

- If many false positives happen while user is quiet, make name gate stricter and shorten follow-up window.
- If user repeatedly says "Friday" but it is transcribed as "Friady" or "Freddie", reinforce alias handling.
- If user is in an active follow-up conversation, allow safer pronoun/direct commands briefly.
- If TTS just spoke, suppress known hallucination captures like "thank you for watching".
- If a command would modify system state, require stronger attention confidence.

Acceptance criteria:

- Reduces accidental responses to background video audio.
- Improves recovery from repeated "Friday" mishearings.
- Produces a visible attention profile in the dashboard/API.

### `core/cognitive_cycle.py`

Purpose: coordinate the new brain-inspired loops.

Responsibilities:

- Run low-frequency background cycles.
- Decide when to refresh world model.
- Trigger reflection after failures or scheduled windows.
- Trigger learning review.
- Update goal regulation and attention profile.

Core functions:

- `start() -> None`
- `stop() -> None`
- `run_once(trigger="manual") -> dict`
- `status() -> dict`

Cycle intervals:

- World snapshot: every 30 to 90 seconds when active.
- Reflection: after notable failure or every 30 minutes while running.
- Learning review: every 2 to 6 hours.
- Attention profile update: every 10 to 30 minutes or after correction.

CPU rules:

- In `--fast-voice`, run the cycle in light mode.
- If CPU guard reports high CPU, skip visual analysis and learning review.
- Never run heavy LLM reflection while the user is actively speaking.

## 4. Orchestrator Integration

Update `core/orchestrator.py`:

- Add direct commands:
  - `what is going on right now`
  - `what are you focused on`
  - `what did you learn recently`
  - `why did you do that`
  - `reflect on that`
  - `what are your current goals`
  - `be stricter about listening`
  - `listen more carefully for Friday`
- Feed `world_model.planner_context()`, `goal_regulation.regulation_prompt_context()`, and selected reflection findings into LLM context only when relevant.
- When tool claims are made, create world expectations for verification.
- When user reports failure, call `self_reflection.reflect_on_command(...)`.
- When direct action succeeds with verification, reinforce long-term learning.

## 5. Voice Loop Integration

Update `jarvis.py` and the attention pipeline:

- Start `cognitive_cycle` in voice sessions if `cognitive_cycle_enabled=true`.
- Stop it cleanly during shutdown.
- Send attention decisions to `adaptive_attention.record_attention_event`.
- Send user corrections to `adaptive_attention.record_user_correction`.
- Use `adaptive_attention.recommended_attention_config()` as runtime hints without rewriting config files during a session.
- Use `goal_regulation.current_regulation()` to decide whether proactive speech should speak now.

## 6. Desktop and Vision Integration

Update `core/desktop_vision.py` and `core/visual_monitor.py`:

- Every desktop step writes:
  - expected outcome
  - observed outcome
  - confidence
  - whether progress happened
- Visual changes update `world_model`.
- Desktop task failure triggers `self_reflection`.
- Repeated UI element success updates long-term app memory.

## 7. API Endpoints

Update `api/server.py` with JWT-protected endpoints:

- `GET /cognition/status`
- `POST /cognition/run-once`
- `GET /cognition/world`
- `GET /cognition/world/snapshots`
- `GET /cognition/reflections`
- `POST /cognition/reflections/run`
- `GET /cognition/learning`
- `POST /cognition/learning/review`
- `GET /cognition/goals`
- `POST /cognition/goals`
- `PATCH /cognition/goals/{goal_id}`
- `GET /cognition/attention`
- `POST /cognition/attention/correction`

All endpoints must:

- Require JWT auth.
- Avoid exposing secrets.
- Return under 500ms unless explicitly running a reflection or learning review.
- Log sensitive state-changing actions to audit/permission logs when appropriate.

## 8. Dashboard UI

Update `apps/web` with a Cognition page or panels:

- World Model panel:
  - current active app/window
  - recent observations
  - open expectations
  - confidence indicators
- Reflection Journal:
  - recent findings
  - severity
  - promoted/not promoted
  - source evidence
- Learning panel:
  - durable lessons
  - confidence
  - next review date
  - promote to skill button
- Goals and Regulation panel:
  - active goals
  - current operational state
  - blockers
  - progress
- Adaptive Attention panel:
  - false positive/negative trend
  - learned aliases
  - current strictness
  - correction form

Design rules:

- Dense, operational dashboard style.
- No marketing hero.
- Keep mobile responsive at 375px.
- Use status chips, compact tables, and timeline rows.

## 9. Configuration Keys

Add to `config.json`:

```json
{
  "cognitive_cycle_enabled": true,
  "cognitive_cycle_light_mode_in_fast_voice": true,
  "world_model_enabled": true,
  "world_model_snapshot_interval_seconds": 60,
  "world_model_max_snapshots": 1000,
  "world_model_use_vision_llm": false,
  "self_reflection_enabled": true,
  "self_reflection_interval_minutes": 30,
  "self_reflection_failure_trigger_enabled": true,
  "self_reflection_use_llm": false,
  "long_term_learning_enabled": true,
  "long_term_learning_review_interval_hours": 4,
  "long_term_learning_min_evidence": 2,
  "goal_regulation_enabled": true,
  "goal_regulation_default_state": "calm",
  "adaptive_attention_enabled": true,
  "adaptive_attention_update_interval_minutes": 15,
  "adaptive_attention_min_events": 8,
  "adaptive_attention_runtime_hints_only": true
}
```

Free-first defaults:

- Reflection should use deterministic local heuristics by default.
- LLM-based reflection can be enabled later with NVIDIA/Gemini/Ollama routes.
- World model should summarize mostly from existing local events and screenshots metadata.

## 10. Testing Plan

Add tests:

- `tests/test_cognitive_state.py`
- `tests/test_world_model.py`
- `tests/test_self_reflection.py`
- `tests/test_long_term_learning.py`
- `tests/test_goal_regulation.py`
- `tests/test_adaptive_attention.py`
- `tests/test_cognitive_cycle.py`
- `tests/test_api_cognition.py`
- `tests/test_dashboard_cognition_smoke.py`

Required coverage:

- Dataclass serialization round trips.
- SQLite schema creation and migration safety.
- World snapshot capture without camera or browser.
- Reflection finding created from failed command.
- Learning item reinforcement and review scheduling.
- Goal state transitions.
- Attention profile changes after false positives and corrections.
- Cognitive cycle starts and stops cleanly.
- API endpoints require JWT.
- Dashboard loads cognition panels without layout overflow at 375px.

## 11. Safety Constraints

- Do not let emotional/regulation state override permissions.
- Do not infer sensitive user emotions as facts. Use operational state labels only.
- Do not store passwords, API keys, or private message contents in learning items.
- Do not let adaptive attention silently disable name gating.
- Do not let world model claim it sees camera/screen data unless a capture actually happened.
- Do not let self-reflection automatically apply self-updates without explicit user approval.
- Do not use cloud APIs for private screen/camera analysis unless the user enables that provider and feature.

## 12. Implementation Phases

### Phase 1: Cognitive State Foundation

Files:

- `core/cognitive_state.py`
- `tests/test_cognitive_state.py`
- `config.json`
- `tests/test_setup.py`

Tasks:

- Add shared dataclasses and serialization helpers.
- Add config flags.
- Add tests.

Acceptance:

- Dataclasses serialize to JSON-safe dictionaries.
- Config tests pass.

### Phase 2: World Model

Files:

- `core/world_model.py`
- `tests/test_world_model.py`
- Update `core/visual_monitor.py`
- Update `core/desktop_vision.py`

Tasks:

- Store world snapshots and entities.
- Capture current context from local sources.
- Create and resolve expectations.
- Feed recent visual monitor events into world context.

Acceptance:

- `world_model.current_context()` returns useful context offline.
- Desktop task steps can write expectations and observations.

### Phase 3: Self-Reflection

Files:

- `core/self_reflection.py`
- `tests/test_self_reflection.py`
- Update `core/orchestrator.py`
- Update `core/self_update.py`

Tasks:

- Store reflection runs and findings.
- Detect user corrections and tool failures.
- Promote repeated findings to learning items or self-update proposals.

Acceptance:

- Saying "that did not work" after a tool claim creates a finding.
- Repeated verified issue can propose a guarded self-update.

### Phase 4: Long-Term Learning

Files:

- `core/long_term_learning.py`
- `tests/test_long_term_learning.py`
- Update `core/skill_library.py`
- Update `core/competence.py`
- Update `core/consolidation.py`

Tasks:

- Store learning items with confidence and evidence counts.
- Add review scheduling.
- Promote strong repeated lessons to procedural skills.

Acceptance:

- Repeated successful app-control patterns become retrievable lessons.
- Stale unreinforced lessons decay or archive.

### Phase 5: Goal and Regulation System

Files:

- `core/goal_regulation.py`
- `tests/test_goal_regulation.py`
- Update `core/orchestrator.py`
- Update `core/background_agents.py`
- Update `core/proactive_speech.py`

Tasks:

- Store active goals and operational state.
- Use state to adjust proactivity, verification, and background work.
- Add direct commands for goals and focus.

Acceptance:

- Friday can report active goals.
- High uncertainty makes Friday verify more and claim less.
- Overloaded state pauses or slows background agents.

### Phase 6: Adaptive Attention

Files:

- `core/adaptive_attention.py`
- `tests/test_adaptive_attention.py`
- Update attention/wake handling in `jarvis.py` and STT gate code.

Tasks:

- Record accepted/ignored transcripts.
- Track false positives and user corrections.
- Produce runtime attention hints.

Acceptance:

- Repeated background false positives increase strictness.
- Repeated name mishearings improve alias handling.
- Hints are runtime-only unless the user explicitly asks to save them.

### Phase 7: Cognitive Cycle

Files:

- `core/cognitive_cycle.py`
- `tests/test_cognitive_cycle.py`
- Update `jarvis.py`

Tasks:

- Start/stop cycle in voice sessions.
- Run light mode during fast voice.
- Coordinate world model, reflection, learning review, goals, and attention.

Acceptance:

- Cycle starts and stops cleanly.
- CPU guard prevents heavy work during active conversation.

### Phase 8: API and Dashboard

Files:

- `api/server.py`
- `tests/test_api_cognition.py`
- `apps/web`

Tasks:

- Add cognition endpoints.
- Add dashboard panels.
- Add mobile smoke tests.

Acceptance:

- Dashboard shows world model, reflections, learning, goals, and attention.
- All endpoints are JWT protected.

## 13. First Milestone To Build

The first practical milestone should be:

1. `core/cognitive_state.py`
2. `core/world_model.py`
3. `core/self_reflection.py`
4. Direct commands:
   - `what is going on right now`
   - `reflect on that`
   - `what did you learn from that`
5. Tests for all three modules.

Reason:

- World modeling and reflection give immediate value.
- They reduce false success claims.
- They create evidence for stronger long-term learning.
- They do not require paid APIs or high CPU.

## 14. Definition Of Done

This brain-inspired upgrade is complete when:

- Friday can maintain a current context model from local observations.
- Friday can compare expected vs actual outcomes after actions.
- Friday records and explains self-reflection findings.
- Friday learns durable lessons from repeated evidence.
- Friday tracks active goals and operational state.
- Friday adapts attention behavior based on false positives, false negatives, and corrections.
- Dashboard exposes these states clearly.
- All new data stores are local, test-covered, and safe by default.
- Full test suite passes.
