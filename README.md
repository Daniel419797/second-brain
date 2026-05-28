# Friday Personal AI Agent

Friday is a Windows-first Python modular monolith for a voice-activated personal AI assistant.

## Prerequisites

- Windows 10 or 11
- Python 3.14.5, the latest stable Python 3 release as of May 14, 2026
- A microphone
- Internet access for cloud LLMs, Edge/ElevenLabs voice, market data, email, and web search
- API keys only for the providers/features you enable. Wake-word detection is local with openWakeWord; local Ollama mode does not need Anthropic.

The project targets Python `>=3.14,<3.15`. The current machine has Python 3.14 installed, and `.python-version` records `3.14.5` as the recommended exact maintenance release.

## Virtual Environment Setup

```powershell
py -3.14 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

The original Phase 4 PDF used `pyaudio` and `webrtcvad`. For Python 3.14 compatibility this implementation uses `sounddevice` plus local energy-based silence detection, avoiding native extension builds. Raw audio is not written to disk. If `stt_backend` is set to `deepgram`, command audio is streamed to Deepgram over WebSocket for realtime transcription. If `stt_backend` is set to `groq`, the captured command audio is sent to Groq for transcription; set `stt_backend` to `whisper-cpp` for fully local transcription.

## API Key Setup

Create a `.env` file in the project root. This workspace includes placeholder values, and `.env.example` is provided as the shareable template; replace the real `.env` values before running voice mode.

```dotenv
ANTHROPIC_API_KEY=sk-ant-your-key
ELEVENLABS_API_KEY=your_elevenlabs_key
ELEVENLABS_VOICE_ID=21m00Tcm4TlvDq8ikWAM
ALPHA_VANTAGE_KEY=your_alpha_vantage_key
GMAIL_ADDRESS=yourname@gmail.com
GMAIL_APP_PASSWORD=xxxx-xxxx-xxxx-xxxx
GROQ_API_KEY=your_groq_key_here
DEEPGRAM_API_KEY=your_deepgram_key_here
GEMINI_API_KEY=your_gemini_key_here
OPENROUTER_API_KEY=your_openrouter_key_here
NVIDIA_API_KEY=your_nvidia_key_here
MESHY_API_KEY=your_meshy_key_here
TRIPO_API_KEY=your_tripo_key_here
BRAVE_SEARCH_API_KEY=your_brave_search_key_here
GOOGLE_SEARCH_API_KEY=your_google_search_key_here
GOOGLE_SEARCH_CX=your_google_search_engine_id_here
TAVILY_API_KEY=your_tavily_key_here
SERPAPI_API_KEY=your_serpapi_key_here
JARVIS_API_USERNAME=friday
JARVIS_API_PASSWORD=your_api_password_here
JARVIS_API_SECRET=your_api_secret_here
```

Service URLs:

- Anthropic: https://console.anthropic.com/
- ElevenLabs: https://elevenlabs.io/
- Alpha Vantage: https://www.alphavantage.co/support/#api-key
- Gmail App Passwords: https://myaccount.google.com/apppasswords
- Groq speech-to-text: https://console.groq.com/keys
- Deepgram realtime speech-to-text: https://console.deepgram.com/
- Gemini API: https://aistudio.google.com/app/apikey
- OpenRouter: https://openrouter.ai/keys
- NVIDIA Build/NIM API: https://build.nvidia.com/
- Meshy and Tripo: optional text-to-3D providers
- Brave Search, Google Programmable Search, Tavily, or SerpAPI: optional dedicated web-search providers

## Local Brain With Ollama

Friday can use Ollama for a local/offline LLM. This workspace is configured for Ollama by default.

Install Ollama from https://ollama.com/download, then pull the fast CPU model:

```powershell
ollama pull qwen3:0.6b
```

Switch `config.json` to local mode:

```json
"llm_provider": "ollama",
"ollama_base_url": "http://localhost:11434",
"ollama_model": "qwen3:0.6b"
```

`qwen3:0.6b` is the fastest local starter model for CPU-only machines. `qwen3:1.7b` gives better answers but is slower, and `qwen3:8b` is much slower on CPU.

You can also keep Claude primary and use local fallback:

```json
"llm_provider": "anthropic",
"llm_fallback_provider": "ollama"
```

Ollama mode does not require `ANTHROPIC_API_KEY`, but it does require the Ollama desktop/server process to be running.

## Free API Strategy

Friday is configured to stay free-first: NVIDIA Build/NIM API as the preferred online intelligence when `NVIDIA_API_KEY` is present, local Ollama as the offline fallback, Deepgram realtime STT when you provide `DEEPGRAM_API_KEY`, Groq Whisper as the STT fallback when you provide `GROQ_API_KEY`, whisper.cpp as the local STT fallback, Edge neural voices for free natural TTS when online, and `pyttsx3` as the offline voice fallback.

Free/cheap provider options are wired in behind config flags:

- `ollama`: fully local and free to run on your CPU, best for background agents and short voice replies.
- `nvidia`: NVIDIA Build/NIM API through `https://integrate.api.nvidia.com/v1`, best for harder online coding, writing, math, and reasoning.
- `gemini`: uses the Gemini Developer API free tier when `GEMINI_API_KEY` is present.
- `openrouter`: can use `:free` models when `OPENROUTER_API_KEY` is present.
- `groq`: currently used for STT only, because Whisper Large v3 accuracy is much better than the CPU-local models on this microphone.

Example fallback setup that stays free-first:

```json
"llm_provider": "nvidia",
"llm_fallback_provider": "ollama",
"nvidia_model": "meta/llama-3.3-70b-instruct",
"ollama_model": "qwen3:1.7b",
"gemini_model": "gemini-2.0-flash-lite",
"openrouter_model": "meta-llama/llama-3.2-3b-instruct:free"
```

Add your NVIDIA key locally when you want online intelligence:

```dotenv
NVIDIA_API_KEY=your_nvidia_key_here
```

Rate limits change, so treat free cloud APIs as burst capacity rather than guaranteed always-on compute. If NVIDIA is offline, rate-limited, or missing a key, Friday falls back to Ollama automatically. The v2 background agents are intentionally rate-limited and can run on local fallback output if a free cloud provider is unavailable.

When an online provider key is configured, Friday can run the office agents in API-backed mode: up to 10 task workers can be active while actual LLM calls are throttled per provider. This keeps the laptop mostly in orchestration mode instead of trying to run 10 local models on the CPU.

```json
"v2_api_agent_mode_enabled": true,
"v2_api_background_worker_count": 10,
"v2_api_agent_force_online_first": true,
"v2_api_agent_online_providers": "nvidia>gemini>openrouter>anthropic",
"llm_provider_max_concurrency": {
  "nvidia": 3,
  "gemini": 2,
  "openrouter": 2,
  "anthropic": 2,
  "ollama": 1
}
```

The worker count and provider concurrency are intentionally separate. Ten workers may claim and coordinate tasks, but only a few calls hit NVIDIA/Gemini/OpenRouter at once; if a provider starts returning rate-limit or capacity errors, Friday backs off and tries the next provider in the agent's route.

V2 agents can also route by role. The default config uses NVIDIA first for harder reasoning/coding agents, Gemini first for lighter office/design/content agents when `GEMINI_API_KEY` is available, and Ollama first for cheaper local QA/junior work:

```json
"v2_agent_provider_routes": {
  "default": "nvidia>ollama",
  "product_manager": "gemini>nvidia>ollama",
  "project_manager": "gemini>nvidia>ollama",
  "ui_ux_designer": "gemini>nvidia>ollama",
  "brand_content_designer": "gemini>nvidia>ollama",
  "research_analyst": "gemini>nvidia>ollama",
  "data_scientist": "nvidia>gemini>ollama",
  "junior_developer": "ollama>nvidia",
  "qa_engineer": "ollama>nvidia"
}
```

Routes are ordered fallbacks. If a provider key is missing, still a placeholder, rate-limited, or offline, Friday tries the next provider in the chain.

## Local Cognitive Memory

Friday includes a free local cognitive memory stack. It does not require Mem0 cloud services or paid storage:

- Short-term working memory: rolling conversation buffer in `core/memory.py`
- Semantic memory: local JSON by default, with optional ChromaDB vector mode
- Episodic memory: SQLite event log in `data/episodic_store.sqlite3`
- Knowledge graph: NetworkX graph persisted to `data/knowledge_graph.json`
- Procedural memory: reusable agent skills in `data/skill_library.json`, learned from repeated task patterns
- Metacognitive memory: per-agent competence maps in `data/competence_map.json`
- Context budget: token counting through `tiktoken`, with deterministic compaction
- Consolidation: APScheduler runs a nightly 2 AM job that extracts durable facts, reinforces useful memories, decays stale activation scores, and archives low-score memories

Relevant config keys:

```json
"memory_backend": "json",
"memory_consolidation_enabled": true,
"memory_consolidation_hour": 2,
"memory_activation_decay_rate": 0.05,
"memory_activation_reinforcement": 0.3,
"memory_activation_prune_threshold": 0.1,
"context_budget_max_tokens": 180000,
"competence_research_threshold": 0.5,
"competence_learning_rate": 0.1,
"procedural_skill_min_examples": 5
```

By default, consolidation uses a local heuristic so it does not require a paid LLM call. Set `"consolidation_use_llm": true` only if you want the configured LLM, such as local Ollama, to extract richer facts.

## Guarded Self-Update Workflow

Friday can now work on its own codebase through a guarded self-update lane. This is intentionally not silent self-rewriting:

- `propose`: creates a self-update plan, risk level, likely files, and approval phrase
- `approve`: requires the exact phrase `I authorize self update <id>` and queues an implementation-planning task
- `stage_change`: stores exact file replacements, matching existing text exactly once
- `apply`: requires `I authorize applying self update <id>`, modifies only safe repo files, backs them up, runs tests, and rolls back if tests fail

Protected paths such as `.env`, `.venv`, `data`, `node_modules`, and hidden build/runtime folders are blocked. File deletion is not part of self-update. The safety center also exposes self-update permissions, with staging and applying changes set to ask-first by default.

Example voice or chat flow:

```text
Friday, update your codebase to add safer retry handling
Friday, I authorize self update 3
Friday, show self update 3
Friday, I authorize applying self update 3
```

## Brain-Inspired Cognition Layer

Friday now has a local cognition layer that makes it more stateful and self-correcting without pretending to be conscious:

- `world_model`: tracks current context, active app/window, recent visual/task state, entities, and expected outcomes.
- `self_reflection`: records findings when actions fail, the user corrects Friday, permissions block something, or a response path is slow.
- `long_term_learning`: stores durable lessons with evidence counts, confidence, and review scheduling.
- `goal_regulation`: tracks active goals and operational state, such as calm, focused, uncertain, blocked, overloaded, recovering, or waiting for user.
- `adaptive_attention`: records accepted/ignored speech and corrections so Friday can tune runtime listening strictness over time.
- `cognitive_cycle`: coordinates those modules in a low-frequency background loop during voice sessions.

Useful commands:

```text
Friday, what is going on right now
Friday, what are your current goals
Friday, create goal improve voice reliability
Friday, reflect on that
Friday, what did you learn recently
Friday, attention status
Friday, be stricter about listening
Friday, listen more carefully for Friday
```

The protected dashboard also exposes a Cognition panel and `/cognition/*` API endpoints for world model, reflection, learning, goals, and attention state.

## V2 Local Agent Team

The v2 foundation is local-first. Friday now has a persistent SQLite task queue, background workers, the 14-agent roster from the v2 PDF, episodic logging, procedural skill learning, competence maps, and voice/direct commands for checking the team.

The source-of-truth completion tracker is [docs/v2_status.md](docs/v2_status.md), which is mapped directly to `JARVIS_v2_Phase_Planning_v3.pdf`.

UI decision for later phases:

- Desktop app: Electron
- Web/dashboard app: Next.js

Implemented local v2 commands:

- `team status`
- `list agents`
- `show agent offices`
- `show QA office`
- `start agents`
- `stop agents`
- `queue task research free speech APIs`
- `assign write tests for memory to QA`
- `run next task`
- `what is the team working on`
- `show task 1`
- `cancel task 1`

Task data lives in `data/task_queue.sqlite3`. Tasks include `pending`, `active`, `blocked`, `done`, `failed`, and `cancelled` states, plus persisted inter-agent messages. A task can also have a future `scheduled_at` timestamp; workers will skip it until that time.

Each agent also has a virtual office, exposed through `GET /agents/offices` and the dashboard Office Floor. An office shows the agent's room, status, current focus, progress, provider chain, recent task messages, and task counts, so you and Friday/CEO can see what the team is doing without opening every task one by one.

Relevant v2 config:

```json
"v2_background_agents_enabled": true,
"v2_background_worker_count": 1,
"v2_api_agent_mode_enabled": true,
"v2_api_background_worker_count": 10,
"v2_worker_idle_sleep_seconds": 2.0,
"v2_worker_between_tasks_sleep_seconds": 0.5,
"v2_agent_use_llm": true,
"v2_agent_default_mode": "safe_planning",
"v2_authorized_targets": []
```

The workers are CPU-safe by default when offline: local/Ollama mode keeps one inference worker and sleeps between tasks. When `v2_api_agent_mode_enabled` is on and a hosted provider key exists, Friday can scale to 10 background task workers while `core/llm.py` enforces provider concurrency, spacing, queue timeouts, and rate-limit backoff. For now, agents produce plans and summaries; real-world deployment, destructive file changes, external pentesting, and cloud sync still need explicit tool support and human approval.

When you launch with `--fast-voice`, background workers stay paused by default so Ollama/background learning does not compete with live conversation. Say `start agents` when you want the team to work during that session, or set `"v2_start_background_workers_in_fast_voice": true` in `config.json`.

Delegation is enabled locally. CEO tasks that look like build/project goals spawn Product, Research, Senior Developer, and QA child tasks, and dynamic LLM decomposition can add safe JSON-defined child tasks when the configured LLM is available. Senior Developer implementation tasks can spawn Research and QA child tasks. Junior Developer tasks spawn a Senior Developer review task so structured feedback can be written back into the knowledge graph and procedural skill library.

### Proactive Speech

Friday can speak first during voice sessions without waiting for you to say her name. This is intentionally limited to useful, bounded moments: due reminders, calendar heads-up messages, blocked tasks that need approval, failed high-priority tasks, and completed high-priority tasks.

```json
"proactive_speech_enabled": true,
"proactive_speech_in_fast_voice": true,
"proactive_speech_sources": "reminders,calendar,agent_tasks",
"proactive_speech_max_per_hour": 3,
"proactive_speech_quiet_hours_start": "22:00",
"proactive_speech_quiet_hours_end": "08:00"
```

Spoken proactive events are stored in `data/proactive_speech.sqlite3`, so the same reminder or task update is announced once instead of looping forever. Proactive speech only starts in voice mode; terminal mode and API-only dashboard mode stay silent unless you explicitly send a message.

Guarded Ethical Hacker tasks are blocked by default. To approve one, use the exact confirmation phrase:

```text
I authorize task 4
```

That approval moves the task back to pending. Without it, the worker will not claim the task.

Research-oriented agents can use free sources before they answer or plan. `core/research.py` supports DuckDuckGo snippets, page text extraction, PDF text extraction, and YouTube transcripts. This is controlled by:

```json
"v2_agent_autonomous_research_enabled": true,
"research_max_sources": 2,
"research_fetch_pages": false
```

`research_fetch_pages` is off by default to keep background agents fast and polite. Turn it on when you want deeper page/PDF reading during assigned research tasks.

## V2 Local API

Friday includes a protected local FastAPI backend for the future Next.js dashboard and Electron desktop shell. It defaults to `127.0.0.1:8000` and requires JWT authentication for data endpoints.

Add a local API password before running it:

```dotenv
JARVIS_API_USERNAME=friday
JARVIS_API_PASSWORD=choose-a-long-local-password
```

If `JARVIS_API_PASSWORD` is missing or still a placeholder, `python jarvis.py --api` now prompts for a password and can save it back to `.env`.

Then start the API:

```powershell
python jarvis.py --api
```

Useful protected endpoints:

- `POST /auth/login`
- `POST /auth/refresh`
- `GET /v2/status`
- `GET /agents/roster`
- `GET /agents/status`
- `GET /agents/offices`
- `GET /agents/{agent_id}/office`
- `POST /chat`
- `GET /desktop/tasks`
- `POST /desktop/tasks`
- `GET /desktop/tasks/{session_id}`
- `POST /desktop/tasks/{session_id}/pause`
- `POST /desktop/tasks/{session_id}/resume`
- `POST /desktop/tasks/{session_id}/confirm`
- `POST /desktop/tasks/{session_id}/cancel`
- `GET /desktop/screenshots/{filename}`
- `GET /vision/monitor`
- `POST /vision/monitor/start`
- `POST /vision/monitor/stop`
- `POST /vision/monitor/capture`
- `GET /vision/events`
- `GET /vision/frames/{source}/{filename}`
- `GET /integrations/apps`
- `POST /integrations/open`
- `POST /integrations/contacts`
- `GET /integrations/contacts`
- `POST /integrations/reminders`
- `GET /integrations/reminders`
- `POST /integrations/reminders/{reminder_id}/complete`
- `POST /integrations/calendar/events`
- `GET /integrations/calendar/events`
- `POST /integrations/docs`
- `POST /integrations/sheets`
- `POST /integrations/workspace/index`
- `GET /integrations/workspace/search`
- `GET /integrations/workspace/overview`
- `GET /tasks`
- `POST /tasks`
- `GET /tasks/{task_id}`
- `GET /memory/episodic`
- `GET /memory/skills`
- `GET /memory/competence`
- `GET /logs/recent`
- `GET /audit/recent`
- `GET /permissions/rules`
- `PUT /permissions/rules/{rule_key}`
- `POST /permissions/reset`
- `GET /permissions/events`
- `POST /sync/run`
- `POST /graph/neo4j/export`

The access JWT expires after 24 hours. Refresh uses an httpOnly cookie. For local development, CORS allows `http://localhost:3000` for the future Next.js app.

## V2 Dashboard Apps

The web dashboard is a Next.js app in `apps/web`. It connects to the local FastAPI backend, logs in with the API password, and shows worker status, a Kanban task board, task creation, agent roster, desktop task sessions, live logs, and an audit trail for real-machine actions.

The dashboard also includes Friday Chat, backed by the protected `POST /chat` endpoint. Messages go through the same orchestrator as voice/text commands, so dashboard chat can answer, create tasks, inspect agent offices, and use enabled tools under the same safety gates.

The Desktop Sessions panel can start a human-like app-control session, then show every persisted step with status, action JSON, result text, risk confirmation notes, and the screenshot captured at that point. Active sessions can be paused, resumed, confirmed for risky clicks, or cancelled from the dashboard.

The Live Vision panel can start or stop low-CPU monitoring for the screen, camera, or both, capture a frame on demand, and show recent visual-change events with frame thumbnails. Camera monitoring uses optional `opencv-python`; screen monitoring works through the existing screenshot path.

The Integrations panel exposes free/local deep integrations: open Calendar, Docs, Sheets, WhatsApp, Discord, or Gmail; view local reminders, calendar events, and contacts; and index the workspace so Friday can search and summarize the project without reading files blindly every time.

The Safety Center panel lets you set tool policies to `allow`, `ask`, or `block`. For example, volume controls are allowed by default, while sending email/messages, deleting files if that capability is added later, and shell commands are ask-first by default. Recent permission decisions are logged separately and sensitive real-machine actions still go to the audit trail.

Run the API first:

```powershell
$env:JARVIS_API_PASSWORD="choose-a-long-local-password"
.\.venv\Scripts\python.exe jarvis.py --api
```

In another terminal, run the web dashboard:

```powershell
npm run web:dev
```

Open:

```text
http://localhost:3000
```

The Electron desktop wrapper lives in `apps/desktop` and loads the same dashboard URL:

```powershell
npm run desktop:dev
```

Set a different dashboard URL if needed:

```powershell
$env:FRIDAY_DASHBOARD_URL="http://localhost:3000"
npm run desktop:dev
```

## Cloud Or VPS Deployment

If your PC is too slow for always-on background work, move the API and dashboard to cloud while keeping voice/STT local on your laptop. The repo includes:

- `deploy/Dockerfile.api` for the protected FastAPI backend
- `deploy/Dockerfile.web` for the Next.js dashboard
- `deploy/docker-compose.yml` for a low-cost VPS
- `render.yaml` for Render Blueprints

For the cheapest always-on route, use a small VPS and Docker Compose:

```powershell
cd deploy
$env:JARVIS_API_PASSWORD="choose-a-long-password"
$env:JARVIS_API_SECRET="choose-a-long-random-secret"
$env:FRIDAY_API_CORS_ORIGINS="https://your-web-domain.example"
$env:NEXT_PUBLIC_FRIDAY_API_URL="https://your-api-domain.example"
docker compose up -d --build
```

For Vercel, set `NEXT_PUBLIC_FRIDAY_API_URL` in the web project's Environment Variables before building. For the API host, set `FRIDAY_API_CORS_ORIGINS` to the exact web origin, for example `https://your-app.vercel.app`, with no trailing slash.

Render is simpler because it handles HTTPS and deploys from Git, but an always-on Render Starter web service is more expensive than a tiny VPS. Render's free services are useful for testing, but free instances have limits and are not the best place for an always-on agent.

For a VPS, DigitalOcean Droplets officially start at $4/month, with the 1 GB tier around $6/month. A $4/512 MB VPS is enough for the API/dashboard only; use 1 GB or more if you want background workers, Next.js, and database work on the same box. Keep expensive STT or local PC-control actions on your laptop unless you intentionally move those workloads.

Official references:

- Render pricing: https://render.com/pricing
- Render Blueprint spec: https://render.com/docs/blueprint-spec
- DigitalOcean Droplets: https://www.digitalocean.com/products/droplets

Optional PostgreSQL sync is available for cloud deployments. Set:

```json
"cloud_sync_enabled": true,
"cloud_sync_interval_minutes": 5,
"cloud_sync_database_url_env": "DATABASE_URL"
```

Then provide `DATABASE_URL` in the cloud environment. The sync currently mirrors tasks, task messages, and audit events into PostgreSQL. It does not replace the local SQLite runtime database yet; it is a cloud copy for dashboard/backup workflows.

Neo4j is optional and does not need to run on your laptop. `core/neo4j_migration.py` exports the local NetworkX graph to `data/knowledge_graph.cypher`; import that file into Neo4j Community Edition, Neo4j Desktop, or Aura when you have a free/cheap graph DB available.

The default voice backend is `edge` for a more natural no-cost voice. Microsoft Edge neural voices through `edge-tts` are free and expressive, but require internet access. If Edge TTS is unavailable, Friday falls back to `pyttsx3` offline speech.

Recommended free Edge voices:

- `en-US-EmmaMultilingualNeural` - default, warm natural assistant voice
- `en-US-JennyNeural` - clear assistant-style female voice
- `en-US-AriaNeural` - expressive conversational female voice
- `en-US-AndrewMultilingualNeural` - natural male voice
- `en-US-BrianMultilingualNeural` - calm male voice
- `en-US-AvaMultilingualNeural` - polished female voice

Preview the no-cost voices before choosing:

```powershell
.\.venv\Scripts\python.exe jarvis.py --voice-preview
```

Pre-generate common fast-voice replies so repeated lines do not wait on Edge synthesis:

```powershell
.\.venv\Scripts\python.exe jarvis.py --fast-voice --voice-warmup
```

Set your preference in `config.json` using `voice_backend`, `voice_rate`, `edge_voice`, `edge_rate`, `edge_pitch`, and `edge_volume`. `--fast-voice` keeps the free Edge neural voice, but applies `fast_voice_edge_rate` and stores repeated lines in `data/voice_cache` so common replies get quicker after the first time. For the absolute lowest latency, set `"fast_voice_use_local_tts": true` to use the robotic offline pyttsx3 voice again.

To inspect the offline Windows voices available to `pyttsx3`:

```powershell
.\.venv\Scripts\python.exe jarvis.py --local-voices
```

Set `pyttsx3_voice_id` in `config.json` to the printed voice ID, voice name, or a unique name fragment. This cannot clone your voice, but it lets Friday use the best local Windows voice installed on your laptop.

ElevenLabs remains available as an optional paid/credit-based backend. Free ElevenLabs voice IDs:

- `21m00Tcm4TlvDq8ikWAM` - Rachel
- `AZnzlk1XvdvUeBnXmlld` - Domi
- `EXAVITQu4vr4xnSDxMaL` - Bella
- `ErXwobaYiN019PkySvjV` - Antoni
- `MF3mGyEYCl7XYWbV9V6O` - Elli

Update `ELEVENLABS_VOICE_ID` in `.env` or `elevenlabs_voice_id` in `config.json`.

## Gmail App Password Walkthrough

1. Go to https://myaccount.google.com and enable 2-Step Verification.
2. Go to https://myaccount.google.com/apppasswords.
3. Select `Mail` as the app and `Windows Computer` as the device.
4. Copy the 16-character password.
5. Add it to `.env` as `GMAIL_APP_PASSWORD=xxxx-xxxx-xxxx-xxxx`.
6. Never share this password. Revoke it from the same page if needed.

Friday reads email credentials only from `.env`, enforces a daily send limit, and asks for confirmation before sending.

## How To Run

```powershell
python jarvis.py
```

Debug logging:

```powershell
python jarvis.py --debug
```

Terminal fallback mode, useful when microphone or wake-word dependencies are unavailable:

```powershell
python jarvis.py --text
```

Terminal mode is keyboard-only and does not listen to your microphone. By default it also does not speak replies, which keeps local-model testing faster. To speak replies while typing, use:

```powershell
python jarvis.py --text --speak
```

Voice mode:

```powershell
python jarvis.py
```

By default, voice mode is a continuous session: once Friday is running, it listens for speech, answers, then listens again. The attention gate is strict, so address it as `Friday` before commands. Say `shutdown`, `exit`, or `stop listening` to end it.

```json
"voice_activation_mode": "continuous",
"continuous_ready_beep": false,
"attention_gate_enabled": true,
"attention_mode": "name",
"attention_action_recovery_enabled": false,
"attention_safe_request_recovery_enabled": false,
"conversation_followup_enabled": true,
"conversation_followup_turns": 2,
"speaker_verification_enabled": false,
"speaker_feature_backend": "mfcc",
"speaker_verification_threshold": "auto",
"speaker_centroid_threshold": "auto",
"speaker_negative_margin": 0.06,
"voice_challenge_enabled": false,
"voice_challenge_mode": "protected"
```

Continuous mode answers without requiring the wake phrase. By default it uses strict attention filtering, so side conversation is ignored unless the text mentions Friday or is a direct reply to a question Friday just asked.

For lower latency, common requests are handled locally before the LLM:

- `open Chrome`, `close Spotify`, `list files in Desktop`, `read file README.md`
- `search for Python decorators`
- `remember that my preferred IDE is VS Code`
- simple conversation like `what is your name`, `what can you do`, and `what is my name`

Speaker verification is available as an experimental local gate, but it is disabled by default because MFCC matching is not reliable enough to call bank-grade security. If you want to keep experimenting with it, enable `speaker_verification_enabled`, then enroll your voice profile:

```powershell
python jarvis.py --clear-speaker-enrollment
python jarvis.py --enroll-speaker 6
python jarvis.py --speaker-test
```

Use your normal voice for `--enroll-speaker`. The profile is stored locally in `data/speaker_profile.json` and uses free local MFCC voice fingerprints. It calibrates thresholds from your enrolled samples, so other people do not need to enroll. In `--speaker-test`, your lines should show high `score` and `centroid`; other voices should fall below one of the two thresholds.

If it rejects you, add more samples or lower `speaker_auto_threshold_margin` slightly. If it accepts another person, raise `speaker_auto_threshold_margin` or `speaker_centroid_margin`. The optional `--enroll-speaker-negative` command is only for lab-style hardening against one known voice; it is not required for normal use.

For higher-risk voice commands, Friday can also use challenge-response liveness. Before protected commands such as opening apps, sending email, reading files, or changing memory, it speaks a fresh random phrase and requires the same voice to repeat that phrase. This requires a current speaker profile; if you change `speaker_feature_backend`, clear and enroll again. This helps block simple replay attacks, but it is still not certified bank-grade biometric security. Treat it as experimental local verification, not a replacement for audited security controls.

Wake-word mode remains available when you want the assistant gated behind `Hey Friday`:

```powershell
python jarvis.py --wake-word
```

In wake-word mode Friday plays a short low ready beep and listens locally for the enrolled `Hey Friday` wake phrase. It is not constantly transcribing everything you say.

For a free true wake-word experience, enroll your own local templates first:

```powershell
python jarvis.py --clear-wake-enrollment
python jarvis.py --enroll-wake 5
```

Say only `Hey Friday` for each sample. The templates are stored locally in `data/wake_templates.json`, use openWakeWord audio embeddings, and do not need an API key. After enrollment, test the trigger:

```powershell
python jarvis.py --wake-test --debug
```

The default `wake_word_backend` is `personal`, and `wake_energy_fallback` is disabled so normal speech will not wake the assistant. The personal matcher trims each sample to the spoken phrase and rejects silence, short beeps, and low-energy room noise. If it misses your wake phrase, add more samples with `--enroll-wake 8` or lower `wake_personal_threshold` slightly, for example from `0.78` to `0.72`. If it wakes too easily, raise the threshold.

The built-in openWakeWord `hey_jarvis` model remains available by setting `wake_word_backend` to `openwakeword` or `hybrid`, but the personal backend is recommended on this microphone because the generic model was scoring `0.00` for your voice. During command capture the wake listener is paused, so it should not trigger on Friday's own voice output.

For best transcription in wake-word mode, say `Hey Friday`, then speak the command after a tiny pause. In continuous mode, address Friday by name and speak the command clearly. This workspace is configured for Deepgram Nova-3 realtime streaming STT, with Groq Whisper Large v3 as fallback. To avoid sending command audio to cloud STT providers, switch `stt_backend` to `whisper-cpp`.

```json
"stt_backend": "deepgram",
"stt_model": "nova-3",
"stt_fallback_model": "groq:whisper-large-v3",
"stt_groq_base_url": "https://api.groq.com/openai/v1",
"stt_deepgram_api_key_env": "DEEPGRAM_API_KEY",
"stt_deepgram_realtime_enabled": true,
"stt_deepgram_endpointing_ms": 350,
"stt_whisper_cpp_model_path": "tools\\whisper.cpp\\models\\ggml-base.en-q5_1.bin",
"stt_compute_type": "int8",
"stt_cpu_threads": 4,
"stt_vad_filter": false,
"stt_vad_min_silence_ms": 350,
"stt_vad_speech_pad_ms": 350,
"stt_without_timestamps": true,
"stt_max_new_tokens": 48,
"stt_repetition_penalty": 1.05,
"stt_no_repeat_ngram_size": 3,
"stt_hotwords": "Friday Computer Gmail Chrome open close search email VS Code Python Ollama",
"stt_retry_corrupt_download": true
```

When Friday asks a question, it listens for up to two follow-up answers without requiring another wake phrase. Recent turns are also sent to the LLM for continuity. Tune this with `conversation_followup_enabled`, `conversation_followup_turns`, and `conversation_context_messages`.

The recorder keeps a small pre-roll and waits through short pauses. You can tune `stt_silence_ms`, `stt_pre_roll_ms`, `stt_min_energy_threshold`, `stt_noise_multiplier`, `stt_beam_size`, `stt_best_of`, `stt_vad_min_silence_ms`, `stt_vad_speech_pad_ms`, `stt_trailing_junk_words`, and `stt_phrase_corrections` in `config.json`.

If the wake phrase is mis-transcribed as filler such as `Okay` or a short fragment, Friday ignores it and retries command capture. Tune this with `stt_ignore_captures`, `stt_min_command_chars`, and `stt_command_retries`.

If continuous mode responds to side conversations, set `"attention_mode": "name"` so it only answers when you address it by name, except during follow-up replies.

Microphone/STT test without wake word:

```powershell
python jarvis.py --listen-once
```

Use `--listen-once` when you want to confirm the microphone and Whisper transcription work separately from wake-word detection.

Force continuous voice mode without wake word:

```powershell
python jarvis.py --continuous --debug --fast-voice
```

This repeatedly records spoken commands without waiting for `Hey Friday`. It is the default mode, but the flag is useful if `voice_activation_mode` is changed to `wake_word` in `config.json`.

For timing diagnostics, run:

```powershell
python jarvis.py --debug
```

The log prints separate `stt_total`, `brain`, `tts`, and `e2e` timings.
With `--debug`, normal voice mode also prints `[WAKE] score=...` once per second so you can tell whether the microphone is producing wake-word signal.

Latency checks:

```powershell
python jarvis.py --listen-once --debug --no-speak
```

This measures microphone, transcription, and local brain without TTS. To use the lower-latency offline Windows voice for a run:

```powershell
python jarvis.py --listen-once --debug --fast-voice
```

Wake-word diagnostics:

```powershell
python jarvis.py --wake-test
```

This shows live wake-word scores once per second. Say `Hey Friday`; if the score never rises after enrollment, add more wake samples, lower `wake_personal_threshold`, or check that Windows is using the right microphone.

Microphone level test:

```powershell
python jarvis.py --mic-test
```

Speak while it runs. If energy stays near zero, set `audio_input_device` to another input device and test again.

List microphones:

```powershell
python jarvis.py --audio-devices
```

If the default input is wrong, set `audio_input_device` in `config.json` to the device index or name.

Apps are controlled through `config.json` using the `allowed_apps` mapping. Add friendly names and executable paths there; blocked system paths are also configured in `config.json`.

## Deep App Integrations

Friday now has a free-first integration layer in `core/app_integrations.py`. It does not require paid Google, WhatsApp, or Discord APIs. For account-bound services, Friday opens the official web app and can operate the visible UI through the desktop task system. For private structured data that Friday can truly own locally, she uses SQLite.

Implemented integration commands:

- `open calendar`, `open docs`, `open sheets`, `open WhatsApp`, `open Discord`
- `add contact Ada email ada@example.com`
- `search contacts Ada`
- `remind me to call Ada tomorrow`
- `list reminders`
- `complete reminder 3`
- `add calendar event planning tomorrow`
- `list calendar events`
- `create document Project Notes`
- `create sheet Budget`
- `index workspace`
- `workspace overview`
- `search workspace for visual monitor`
- `read my whole workspace intelligently`

Local data lives in `data/app_integrations.sqlite3`. Generated docs and sheets live in `data/office_docs` by default. The workspace index stores relative file paths, metadata, small snippets, and summaries; it skips heavy folders like `.venv`, `.git`, `node_modules`, `.next`, and whisper.cpp build files.

Tune this with `office_docs_dir`, `workspace_index_max_files`, `workspace_index_snippet_chars`, `workspace_index_extensions`, and `workspace_index_skip_dirs` in `config.json`.

## Safety Permissions

Friday has a SQLite-backed permission control center in `core/permissions.py`. Each policy has a mode:

- `allow`: run immediately.
- `ask`: require voice/user confirmation before running.
- `block`: refuse the action.

Useful voice commands:

- `Friday, show permissions`
- `Friday may control volume`
- `Friday, must ask before deleting files or sending messages`
- `Friday, block shell commands`
- `Friday, reset permissions`

The dashboard Safety Center exposes the same rules with dropdowns. Permission rules live in `data/permissions.sqlite3`, while decisions are available through `GET /permissions/events`.

Trusted desktop automation is enabled with `pc_allow_desktop_automation`. Friday can move/click/drag the mouse, type text, press keys and hotkeys, scroll, focus windows, and save screenshots. PyAutoGUI fail-safe is enabled; move the mouse to the top-left corner to abort runaway mouse movement.

Screen vision is available through `inspect_screen` and `screen_step`. With `GEMINI_API_KEY`, Friday can analyze the screenshot with Gemini vision; without it, she still captures the screen and reports local window metadata. `screen_step` runs only one safe UI action at a time.

Continuous vision is available through `visual_monitor_start`, `visual_monitor_stop`, `visual_monitor_status`, and `visual_capture_once`, or by voice with phrases like `Friday, start watching my screen`, `Friday, start camera monitor`, and `Friday, stop watching`. The monitor stores visual events in `data/visual_monitor.sqlite3` and frame files under `data/visual_frames`, then feeds recent change summaries into desktop task planning. Vision-model analysis is off by default to preserve free API quota; turn on `visual_monitor_analysis_enabled` only when you want periodic Gemini summaries.

For websites, Friday can also use Chrome DevTools Protocol to inspect page DOM controls when Chrome is opened in debug mode. `open Chrome` and `open Gmail` use this mode by default through `browser_dom_launch_chrome_debug`; you can also call `open_browser_debug`. This gives Friday selectors, page text, visible controls, and DOM actions like `dom_click` and `dom_type`, which are more reliable than coordinates for complex web pages.

For native Windows apps, Friday can read a bounded Windows UI Automation tree when `app_accessibility_enabled` is true. This gives names, automation IDs, control types, rectangles, and supported invoke/value patterns for controls that expose accessibility metadata.

For human-like app operation, use `desktop_task` or say something like `Friday, use the desktop to open the first email`. Friday will run a persisted screenshot-plan-act-check session: capture the screen, plan one safe action, execute it, wait, verify progress from the next screenshot, retry with recovery actions when useful, and stop if progress stalls or the action would be unsafe.

Desktop task sessions are stored in `data/desktop_tasks.sqlite3`, can run for longer bounded sessions, and support pause/resume/cancel plus confirmation before risky clicks such as send, delete, purchase, submit, or install. The dashboard shows each step and screenshot, while UI element memory helps Friday reuse known controls in repeated workflows.

CAPTCHA and login screens are treated as human handoff points. Friday pauses the session instead of trying to bypass human verification or type private credentials; after you handle it, resume the same desktop task.

Tune this with `desktop_task_max_steps`, `desktop_task_absolute_max_steps`, `desktop_task_auto_extend_steps`, `desktop_task_extend_by_steps`, `desktop_task_no_progress_limit`, `desktop_task_step_delay_seconds`, `desktop_task_recovery_enabled`, `desktop_task_recovery_limit`, `desktop_task_confirm_risky_actions`, `browser_dom_enabled`, `app_accessibility_enabled`, `visual_monitor_interval_seconds`, `visual_monitor_change_threshold`, `visual_monitor_analysis_enabled`, and `visual_monitor_planner_context_enabled` in `config.json`.
