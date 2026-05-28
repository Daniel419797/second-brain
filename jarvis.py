"""Friday single-process entry point."""

from __future__ import annotations

import argparse
import getpass
import os
import queue
import random
import sys
import threading
import time
try:
    import winsound
except Exception:  # pragma: no cover - non-Windows fallback
    winsound = None
from pathlib import Path

try:
    from dotenv import load_dotenv
except Exception:  # pragma: no cover - optional in scaffold tests
    def load_dotenv(*args, **kwargs):
        env_path = Path(__file__).resolve().parent / ".env"
        if not env_path.exists():
            return False
        for raw_line in env_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip())
        return True

from core import adaptive_attention, autonomy_engine, background_agents, barge_in, cloud_sync, cognitive_cycle, consolidation, daily_companion, event_nervous_system, learning_scheduler, memory, orchestrator, project_watchdog, proactive_guardian, proactive_speech
from core.config import ensure_runtime_dirs, load_config
from input import speech_to_text as stt
from input.personal_wake import add_template, clear_templates, load_templates
from input.speech_to_text import load_model as load_whisper_model
from input.speech_to_text import record_and_transcribe_with_audio
from input.speech_to_text import transcribe
from input.speaker_id import SpeakerVerifier, add_voice_sample, clear_voice_profile, load_voice_samples
from input.wake_word import WakeWordListener
from output.display import log, print_banner, set_log_level
from output.voice import local_voice_options, preview_edge_voices, speak, warm_edge_voice_cache

command_ready = threading.Event()
command_audio: "queue.Queue[tuple[bytes, str]]" = queue.Queue()
speaker_verifier: SpeakerVerifier | None = None
speaker_warning_shown = False
last_voice_challenge_at = 0.0
consolidation_scheduler = None
proactive_speech_started = False
cognitive_cycle_started = False

REQUIRED_ENV = {
    "ANTHROPIC_API_KEY": "https://console.anthropic.com/",
    "ELEVENLABS_API_KEY": "https://elevenlabs.io/",
    "ELEVENLABS_VOICE_ID": "https://api.elevenlabs.io/v1/voices",
    "ALPHA_VANTAGE_KEY": "https://www.alphavantage.co/support/#api-key",
    "GMAIL_ADDRESS": "https://myaccount.google.com/apppasswords",
    "GMAIL_APP_PASSWORD": "https://myaccount.google.com/apppasswords",
    "GROQ_API_KEY": "https://console.groq.com/keys",
    "DEEPGRAM_API_KEY": "https://console.deepgram.com/",
    "GEMINI_API_KEY": "https://aistudio.google.com/app/apikey",
    "OPENROUTER_API_KEY": "https://openrouter.ai/keys",
    "NVIDIA_API_KEY": "https://build.nvidia.com/",
    "JARVIS_API_PASSWORD": "set this locally in .env before running --api",
    "JARVIS_API_SECRET": "optional; Friday creates a local secret if omitted",
}

TEST_STUBS = [
    "test_setup.py",
    "test_llm.py",
    "test_wake_word.py",
    "test_stt.py",
    "test_voice.py",
    "test_display.py",
    "test_orchestrator.py",
    "test_pc_control.py",
    "test_web_search.py",
    "test_trading.py",
    "test_coding.py",
    "test_email.py",
    "test_memory.py",
    "test_knowledge_graph.py",
    "test_neo4j_migration.py",
    "test_desktop_vision.py",
    "test_episodic_store.py",
    "test_context_budget.py",
    "test_consolidation.py",
    "test_task_queue.py",
    "test_agents.py",
    "test_background_agents.py",
    "test_agent_team.py",
    "test_api_auth.py",
    "test_api_server.py",
    "test_audit_log.py",
    "test_research.py",
    "test_learning_scheduler.py",
    "test_performance.py",
    "test_cloud_sync.py",
    "test_speaker_id.py",
    "test_proactive_speech.py",
    "test_self_update.py",
    "test_cognition_modules.py",
]


def main() -> int:
    args = _parse_args()
    load_dotenv()
    ensure_runtime_dirs()
    config = load_config()
    if args.debug:
        set_log_level("DEBUG")
    else:
        set_log_level(str(config.get("log_level", "INFO")))
    if args.fast_voice:
        if bool(config.get("fast_voice_use_local_tts", False)):
            os.environ["JARVIS_VOICE_BACKEND"] = "pyttsx3"
        os.environ["JARVIS_FAST_VOICE"] = "1"
    if args.audio_devices:
        _print_audio_devices()
        return 0
    if args.mic_test:
        return _mic_test_loop()
    if getattr(args, "local_voices", False):
        return _print_local_voices()
    if getattr(args, "voice_preview", False):
        return _voice_preview(str(getattr(args, "voice_preview_text", "")))
    if getattr(args, "voice_warmup", False):
        return _voice_warmup()
    _validate_env(args)
    _check_test_stubs()
    _run_health_check()
    _start_consolidation_scheduler()
    _start_cloud_sync_scheduler()
    _seed_learning_tasks()
    _start_background_agents(args)
    _start_autonomy_supervisor(args)
    _start_awake_services(args)
    _start_proactive_guardian(args)
    if args.api:
        print_banner()
        return _run_api_server(args, config)
    memory.clear_session()
    activation_mode = _voice_activation_mode(args, config)

    if args.stt_benchmark:
        print_banner()
        return _stt_benchmark(
            models=_stt_benchmark_models(args.stt_benchmark_models, config),
            expected=args.stt_benchmark_expected,
        )

    if args.clear_wake_enrollment:
        clear_templates()
        log("SUCCESS", "Personal wake-word enrollment cleared.")
        return 0
    if args.enroll_wake:
        return _enroll_wake(args.enroll_wake)
    if args.clear_speaker_enrollment:
        clear_voice_profile()
        log("SUCCESS", "Speaker profile cleared.")
        return 0
    if args.enroll_speaker:
        return _enroll_speaker(args.enroll_speaker, kind="positive")
    if args.enroll_speaker_negative:
        return _enroll_speaker(args.enroll_speaker_negative, kind="negative")
    if args.speaker_test:
        print_banner()
        return _speaker_test_loop()

    listener = None
    if args.wake_test:
        print_banner()
        return _wake_test_loop()
    if args.listen_once or args.listen_loop:
        try:
            load_whisper_model()
            if args.listen_loop:
                _preload_fast_stt_model(config)
        except Exception as exc:
            log("ERROR", f"Voice recording mode unavailable ({exc}).")
            return 1
    elif not args.text and activation_mode == "continuous":
        try:
            load_whisper_model()
            _preload_fast_stt_model(config)
        except Exception as exc:
            log("WARNING", f"Voice mode unavailable ({exc}). {_voice_dependency_hint(exc)} Falling back to terminal input.")
            args.text = True
    elif not args.text:
        try:
            load_whisper_model()
            listener = WakeWordListener(callback=_queue_command, score_callback=_wake_score_logger() if args.debug else None)
        except Exception as exc:
            log("WARNING", f"Voice mode unavailable ({exc}). {_voice_dependency_hint(exc)} Falling back to terminal input.")
            args.text = True

    print_banner()
    continuous_session = not args.text and not args.listen_once and (args.listen_loop or activation_mode == "continuous")
    assistant_name = str(config.get("jarvis_name", "J.A.R.V.I.S."))
    if args.speak or (not args.text and not args.listen_once and not args.listen_loop and bool(config.get("startup_speech", False))):
        speak(f"{assistant_name} is online and ready.")
    elif not args.text and not args.listen_once:
        _ready_ack()
    if args.listen_once:
        log("SUCCESS", "Ready. Recording one voice command...")
    elif continuous_session:
        log("SUCCESS", f"Ready. Continuous name-listening mode. Say {assistant_name}, then your command; say shutdown to exit.")
    else:
        log(
            "SUCCESS",
            f"Ready. Listening for wake word. Say 'Hey {assistant_name}', then speak your command."
            if not args.text
            else "Ready. Terminal input mode.",
        )
    if listener is not None:
        listener.start()
    _start_proactive_speech(args, voice_enabled=not args.text and not args.listen_once, speak_replies=not args.no_speak)
    _start_cognitive_cycle(args, voice_enabled=not args.text and not args.listen_once)

    try:
        if args.text:
            _terminal_loop(speak_replies=args.speak)
        elif args.listen_once:
            _listen_once(speak_reply=not args.no_speak)
        elif continuous_session:
            _listen_loop(
                speak_replies=not args.no_speak,
                ready_beep=bool(config.get("continuous_ready_beep", False)),
            )
        else:
            _voice_loop(listener, speak_replies=not args.no_speak)
    except KeyboardInterrupt:
        _shutdown(listener)
        return 0
    return 0


def _voice_loop(listener: WakeWordListener | None, speak_replies: bool = True) -> None:
    while True:
        command_ready.wait()
        command_ready.clear()
        initial_audio, trigger_source = _drain_command_audio()
        t0 = time.perf_counter()
        if listener is not None:
            listener.pause()
            time.sleep(0.15)
        try:
            if trigger_source == "wake_word":
                _wake_ack()
                log("SUCCESS", "Wake word detected. Listening for command...")
            elif trigger_source == "personal":
                log("SUCCESS", "Personal wake word detected. Listening for command...")
            else:
                log("SUCCESS", "Speech detected by fallback. Transcribing captured utterance...")
            capture_audio = initial_audio if trigger_source == "energy" else b""
            user_text = _capture_command(
                initial_audio=capture_audio,
                beep_on_retry=trigger_source == "wake_word",
                initial_audio_is_utterance=trigger_source == "energy",
            )
            if not user_text:
                continue
            reply = _handle_text(user_text, t0, speak_reply=speak_replies, secure_voice=True)
            reply = _drain_barge_in_commands(speak_replies=speak_replies) or reply
            _followup_loop(reply, speak_replies=speak_replies)
        finally:
            _clear_command_audio()
            command_ready.clear()
            if listener is not None:
                listener.resume()


def _listen_once(speak_reply: bool = True) -> None:
    t0 = time.perf_counter()
    user_text, audio = record_and_transcribe_with_audio()
    if not user_text:
        log("WARNING", "No speech detected.")
        return
    if not _speaker_allowed(audio):
        return
    _handle_text(user_text, t0, speak_reply=speak_reply, secure_voice=True)
    _drain_barge_in_commands(speak_replies=speak_reply)


def _voice_activation_mode(args: argparse.Namespace, config: dict) -> str:
    if getattr(args, "continuous", False) or getattr(args, "listen_loop", False):
        return "continuous"
    if getattr(args, "wake_word", False):
        return "wake_word"
    raw_mode = str(config.get("voice_activation_mode", "continuous")).strip().lower().replace("-", "_")
    aliases = {
        "always_on": "continuous",
        "always_listen": "continuous",
        "open_mic": "continuous",
        "listen_loop": "continuous",
        "wake": "wake_word",
        "wakeword": "wake_word",
    }
    return aliases.get(raw_mode, raw_mode) if aliases.get(raw_mode, raw_mode) in {"continuous", "wake_word"} else "continuous"


def _preload_fast_stt_model(config: dict) -> None:
    if not bool(config.get("stt_fast_path_enabled", False)):
        return
    fast_model = str(config.get("stt_fast_path_model") or config.get("stt_fallback_model", "")).strip()
    primary_model = str(config.get("stt_model", "base.en")).strip()
    if not fast_model or fast_model == primary_model:
        return
    try:
        stt.load_model(fast_model)
        _restore_primary_stt_model(primary_model)
        log("INFO", f"[STT] fast path ready model={fast_model} primary={primary_model}")
    except Exception as exc:
        _restore_primary_stt_model(primary_model)
        log("WARNING", f"[STT] fast path unavailable ({exc}); using primary model only.")


def _stt_benchmark_models(raw: str | None, config: dict) -> list[str]:
    if raw:
        models = _csv(raw)
    else:
        models = _csv(
            str(
                config.get(
                    "stt_benchmark_models",
                    "medium.en,large-v3-turbo,distil-medium.en,distil-large-v3.5",
                )
            )
        )
        current = str(config.get("stt_model", "")).strip()
        if current:
            models = [current] + models
    return _unique_preserving_order(models)


def _csv(raw: str) -> list[str]:
    return [item.strip() for item in str(raw).split(",") if item.strip()]


def _unique_preserving_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for item in items:
        key = item.lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique


def _stt_benchmark(models: list[str], expected: str = "") -> int:
    if stt.sd is None:
        log("ERROR", "Audio capture dependency sounddevice is not installed.")
        return 1
    if not models:
        log("ERROR", "No STT benchmark models configured.")
        return 1

    log("SUCCESS", "STT benchmark ready. Say one representative Friday command after the beep.")
    log("INFO", "Tip: first run may download uncached models; load time is reported separately from decode time.")
    _ready_ack()
    record_start = time.perf_counter()
    audio = stt.record_audio()
    record_ms = (time.perf_counter() - record_start) * 1000
    if not audio:
        log("WARNING", "No speech detected.")
        return 1

    audio_seconds = len(audio) / (stt.SAMPLE_RATE * 2)
    log("INFO", f"[BENCH] captured audio={audio_seconds:.1f}s record={record_ms:.0f}ms models={', '.join(models)}")

    results: list[dict[str, float | str]] = []
    for model_name in models:
        load_start = time.perf_counter()
        try:
            model = stt.load_model(model_name)
            load_ms = (time.perf_counter() - load_start) * 1000
            decode_start = time.perf_counter()
            text = stt.transcribe(audio, model=model, strip_wake=False)
            decode_ms = (time.perf_counter() - decode_start) * 1000
        except Exception as exc:
            log("ERROR", f"[BENCH] model={model_name} failed: {exc}")
            continue

        realtime = audio_seconds / (decode_ms / 1000) if decode_ms > 0 else 0.0
        wer = _word_error_rate(text, expected)
        wer_part = f" wer={wer * 100:.1f}%" if wer is not None else ""
        log(
            "SUCCESS",
            f"[BENCH] model={model_name} load={load_ms:.0f}ms decode={decode_ms:.0f}ms "
            f"total={load_ms + decode_ms:.0f}ms speed={realtime:.2f}x{wer_part} text='{text}'",
        )
        results.append(
            {
                "model": model_name,
                "load_ms": load_ms,
                "decode_ms": decode_ms,
                "realtime": realtime,
                "wer": wer if wer is not None else -1.0,
                "text": text,
            }
        )

    if not results:
        return 1

    fastest = min(results, key=lambda result: float(result["decode_ms"]))
    log(
        "INFO",
        f"[BENCH] fastest_decode={fastest['model']} decode={float(fastest['decode_ms']):.0f}ms "
        f"speed={float(fastest['realtime']):.2f}x",
    )
    if expected:
        most_accurate = min(results, key=lambda result: float(result["wer"]) if float(result["wer"]) >= 0 else 999.0)
        log("INFO", f"[BENCH] lowest_wer={most_accurate['model']} wer={float(most_accurate['wer']) * 100:.1f}%")
    return 0


def _word_error_rate(text: str, expected: str) -> float | None:
    expected_words = _normalize_benchmark_text(expected).split()
    if not expected_words:
        return None
    heard_words = _normalize_benchmark_text(text).split()
    distance = _word_distance(heard_words, expected_words)
    return distance / len(expected_words)


def _normalize_benchmark_text(text: str) -> str:
    normalized = _normalize_for_attention(text)
    normalized = re_sub_attention(r"\bwhat is the time\b", "what time is it", normalized)
    normalized = re_sub_attention(r"\bwhat the time is\b", "what time is it", normalized)
    normalized = re_sub_attention(r"\bwhat is the date\b", "what date is it", normalized)
    normalized = re_sub_attention(r"\bwhat the date is\b", "what date is it", normalized)
    return normalized


def _word_distance(left: list[str], right: list[str]) -> int:
    previous = list(range(len(right) + 1))
    for i, left_word in enumerate(left, start=1):
        current = [i]
        for j, right_word in enumerate(right, start=1):
            current.append(
                min(
                    previous[j] + 1,
                    current[j - 1] + 1,
                    previous[j - 1] + (0 if left_word == right_word else 1),
                )
            )
        previous = current
    return previous[-1]


def _listen_loop(speak_replies: bool = True, ready_beep: bool = False) -> None:
    while True:
        if ready_beep:
            _ready_ack()
        log("INFO", "Listening for speech...")
        t0 = time.perf_counter()
        user_text, reason = _capture_attended_text(expect_reply=False)
        if not user_text:
            if reason == "empty":
                log("WARNING", "No speech detected.")
            continue
        if _is_shutdown_phrase(user_text):
            raise KeyboardInterrupt
        reply = _handle_text(user_text, t0, speak_reply=speak_replies, secure_voice=True)
        reply = _drain_barge_in_commands(speak_replies=speak_replies) or reply
        _followup_loop(reply, speak_replies=speak_replies)


def _capture_attended_text(expect_reply: bool = False) -> tuple[str, str]:
    config = load_config()
    if _fast_stt_path_enabled(config, expect_reply):
        return _capture_attended_text_fast_path(config, expect_reply=expect_reply)

    user_text, audio = record_and_transcribe_with_audio(strip_wake=False)
    if not user_text:
        return "", "empty"
    if not _speaker_allowed(audio):
        return "", "speaker"
    accepted, cleaned, reason = _attention_decision(user_text, expect_reply=expect_reply)
    _record_attention_event(user_text, accepted, reason, audio_seconds=len(audio) / (stt.SAMPLE_RATE * 2), expect_reply=expect_reply)
    if not accepted:
        log("INFO", f"[ATTENTION] ignored side speech reason={reason} text='{user_text}'")
        return "", "attention"
    return cleaned, "accepted"


def _fast_stt_path_enabled(config: dict, expect_reply: bool) -> bool:
    if expect_reply:
        return False
    return bool(config.get("stt_fast_path_enabled", False))


def _capture_attended_text_fast_path(config: dict, expect_reply: bool = False) -> tuple[str, str]:
    start = time.perf_counter()
    record_start = time.perf_counter()
    audio = stt.record_audio()
    record_ms = (time.perf_counter() - record_start) * 1000
    if not audio:
        return "", "empty"
    if not _speaker_allowed(audio):
        return "", "speaker"

    audio_seconds = len(audio) / (stt.SAMPLE_RATE * 2)
    fast_model = str(config.get("stt_fast_path_model") or config.get("stt_fallback_model", "")).strip()
    primary_model = str(config.get("stt_model", "base.en")).strip()
    fast_ms = 0.0
    fast_text = ""
    if fast_model and fast_model != primary_model:
        fast_start = time.perf_counter()
        try:
            fast_text = stt.transcribe(audio, model_name=fast_model, strip_wake=False)
        except Exception as exc:
            log("WARNING", f"[STT] fast path failed ({exc}); using primary model.")
        fast_ms = (time.perf_counter() - fast_start) * 1000
        if fast_text:
            accepted, cleaned, reason = _attention_decision(fast_text, expect_reply=expect_reply)
            _record_attention_event(fast_text, accepted, reason, audio_seconds=audio_seconds, expect_reply=expect_reply, mode="fast")
            if accepted and _fast_stt_text_is_safe(cleaned):
                _restore_primary_stt_model(primary_model)
                _log_fast_path_stt(start, record_ms, fast_ms, 0.0, audio_seconds, "fast")
                log("INFO", f"[STT] fast path accepted reason={reason} text='{cleaned}'")
                return cleaned, "accepted"
            if not accepted and _fast_stt_rejection_is_final(fast_text, reason):
                _restore_primary_stt_model(primary_model)
                _log_fast_path_stt(start, record_ms, fast_ms, 0.0, audio_seconds, "fast_reject")
                log("INFO", f"[ATTENTION] ignored side speech reason={reason} text='{fast_text}'")
                return "", "attention"

    primary_start = time.perf_counter()
    user_text = stt.transcribe(audio, model_name=primary_model or None, strip_wake=False)
    primary_ms = (time.perf_counter() - primary_start) * 1000
    _log_fast_path_stt(start, record_ms, fast_ms, primary_ms, audio_seconds, "primary")
    if not user_text:
        return "", "empty"
    accepted, cleaned, reason = _attention_decision(user_text, expect_reply=expect_reply)
    _record_attention_event(user_text, accepted, reason, audio_seconds=audio_seconds, expect_reply=expect_reply, mode="primary")
    if not accepted:
        log("INFO", f"[ATTENTION] ignored side speech reason={reason} text='{user_text}'")
        return "", "attention"
    return cleaned, "accepted"


def _record_attention_event(text: str, accepted: bool, reason: str, *, audio_seconds: float = 0.0, expect_reply: bool = False, mode: str = "primary") -> None:
    try:
        if not bool(load_config().get("adaptive_attention_enabled", True)):
            return
        adaptive_attention.record_attention_event(
            text,
            "accepted" if accepted else "ignored",
            reason,
            {"expect_reply": expect_reply, "mode": mode},
            audio_seconds=audio_seconds,
            accepted=accepted,
        )
    except Exception as exc:
        log("DEBUG", f"[ATTENTION] adaptive record skipped ({exc})")


def _log_fast_path_stt(start: float, record_ms: float, fast_ms: float, primary_ms: float, audio_seconds: float, mode: str) -> None:
    if primary_ms:
        transcribe_part = f"fast={fast_ms:.0f}ms transcribe={primary_ms:.0f}ms"
    else:
        transcribe_part = f"transcribe={fast_ms:.0f}ms"
    log(
        "INFO",
        f"[PERF] stt_total={(time.perf_counter() - start) * 1000:.0f}ms "
        f"record={record_ms:.0f}ms {transcribe_part} audio={audio_seconds:.1f}s mode={mode}",
    )


def _restore_primary_stt_model(primary_model: str) -> None:
    if not primary_model:
        return
    try:
        stt.load_model(primary_model)
    except Exception as exc:
        log("WARNING", f"[STT] could not restore primary model '{primary_model}' ({exc}).")


def _fast_stt_text_is_safe(text: str) -> bool:
    normalized = _normalize_for_attention(text)
    if not normalized:
        return False
    safe_patterns = [
        r"(?:hello|hi|hey)",
        r"(?:thanks|thank you|thank you very much|appreciate it)",
        r"(?:how are you|how are you doing|how are you doing today|how's it going)",
        r"(?:what is your name|what's your name|who are you)",
        r"(?:can you code|do you code|can you help me code|do you know how to code)",
        r"(?:what can you do|what are your abilities)",
        r"(?:what time is it|what the time is|what is the time|what's the time|the time|current time)",
        r"(?:what date is it|what the date is|what is the date|what's the date|the date|current date|today's date)",
        r"(?:(?:what|which) day(?: is it| is today)?)",
    ]
    return any(re_search_attention(rf"^{pattern}$", normalized) for pattern in safe_patterns)


def _fast_stt_rejection_is_final(text: str, reason: str) -> bool:
    normalized = _normalize_for_attention(text)
    if reason == "name_required" and _fast_stt_text_is_definitely_unaddressed(normalized):
        return True
    return reason in {"side_cue", "not_addressed"} and _fast_stt_text_is_low_value(normalized)


def _fast_stt_text_is_definitely_unaddressed(normalized: str) -> bool:
    if not normalized:
        return True
    patterns = [
        r"[\W_]*",
        r"(?:you|i|i'm|im|i am|i was|i'm good|im good|i am good)",
        r"(?:yeah|okay|ok|uh|um|hmm|mm|oh)",
        r"(?:can you code|how are you(?: doing)?|what time is it|what is the time)",
        r"(?:can you see the file(?: opened)?(?: on my (?:workspace|vs|v s|visual studio code))?)",
    ]
    return any(re_search_attention(rf"^{pattern}$", normalized) for pattern in patterns)


def _fast_stt_text_is_low_value(normalized: str) -> bool:
    return len(normalized) <= 3 or normalized in {"you", "i", "ok", "okay", "yeah"}


def _capture_command(initial_audio: bytes = b"", beep_on_retry: bool = True, initial_audio_is_utterance: bool = False) -> str:
    config = load_config()
    retries = int(config.get("stt_command_retries", 2)) if bool(config.get("stt_retry_on_blank", True)) else 0
    for attempt in range(retries + 1):
        if attempt == 0 and initial_audio_is_utterance and initial_audio:
            user_text = transcribe(initial_audio)
            audio = initial_audio
        else:
            user_text, audio = record_and_transcribe_with_audio(initial_audio=initial_audio if attempt == 0 else b"")
        reason = "no speech"
        if user_text and not _is_ignorable_capture(user_text):
            if _speaker_allowed(audio):
                return user_text
            reason = "non-profile voice"
        elif user_text:
            reason = "filler/wake-only audio"
        if attempt < retries:
            log("WARNING", f"{reason.capitalize()} detected after trigger. Listening again for the actual command...")
            if beep_on_retry:
                _wake_ack()
        else:
            log("WARNING", "No command detected after trigger.")
    return ""


def _is_ignorable_capture(text: str) -> bool:
    normalized = " ".join(text.lower().strip(" .,!?:;").split())
    if not normalized:
        return True
    min_chars = int(load_config().get("stt_min_command_chars", 4))
    if len(normalized) < min_chars:
        return True
    ignore = {item.strip().lower() for item in str(load_config().get("stt_ignore_captures", "ok,okay,hey")).split(",")}
    return normalized in ignore


def _speaker_allowed(audio: bytes) -> bool:
    return _speaker_allowed_with_policy(audio, fail_open=True)


def _speaker_allowed_with_policy(audio: bytes, fail_open: bool) -> bool:
    global speaker_verifier, speaker_warning_shown
    config = load_config()
    if not bool(config.get("speaker_verification_enabled", True)):
        return True
    try:
        if speaker_verifier is None:
            speaker_verifier = SpeakerVerifier()
        details = speaker_verifier.score_details(audio)
        match = bool(details["match"])
        score = float(details["positive_score"])
    except Exception as exc:
        if not speaker_warning_shown:
            policy = "Allowing speech" if fail_open else "Denying protected action"
            log("WARNING", f"[SPEAKER] verification unavailable ({exc}). {policy} until you enroll a profile.")
            speaker_warning_shown = True
        return fail_open
    level = "DEBUG" if match else "INFO"
    status = "accepted" if match else "ignored"
    log(
        level,
        f"[SPEAKER] {status} score={score:.2f} centroid={float(details['centroid_score']):.2f} "
        f"threshold={speaker_verifier.threshold:.2f}/{speaker_verifier.centroid_threshold:.2f} backend={details['backend']}",
    )
    return match


def _requires_voice_challenge(text: str) -> bool:
    config = load_config()
    if not bool(config.get("voice_challenge_enabled", True)):
        return False
    mode = str(config.get("voice_challenge_mode", "protected")).strip().lower()
    if mode in {"off", "false", "disabled"}:
        return False
    if mode in {"always", "all"}:
        return True
    normalized = _normalize_for_attention(text)
    keywords = _config_csv(
        "voice_challenge_protected_keywords",
        "send email,email,mail,delete,remove,open,close,launch,run,start app,read file,list files,folder,browser,url,http,remember,forget,password,credential,shutdown,stop listening",
    )
    return any(keyword and keyword in normalized for keyword in keywords)


def _voice_liveness_challenge() -> bool:
    global last_voice_challenge_at
    config = load_config()
    if bool(config.get("speaker_verification_enabled", True)) and not SpeakerVerifier.available():
        log("WARNING", "[SECURITY] speaker profile is missing for the current speaker backend; protected action cancelled.")
        speak("I need your speaker profile before protected actions. Please run speaker enrollment first.")
        return False
    cache_seconds = float(config.get("voice_challenge_cache_seconds", 0))
    if cache_seconds > 0 and (time.perf_counter() - last_voice_challenge_at) <= cache_seconds:
        return True
    attempts = max(1, int(config.get("voice_challenge_attempts", 2)))
    for attempt in range(attempts):
        phrase = _make_challenge_phrase()
        speak(f"For security, say: {phrase}")
        log("INFO", f"[SECURITY] liveness challenge phrase='{phrase}'")
        text, audio = record_and_transcribe_with_audio()
        if not text:
            log("WARNING", "[SECURITY] no challenge response detected")
        elif not _speaker_allowed_with_policy(audio, fail_open=False):
            log("WARNING", "[SECURITY] challenge rejected by speaker verification")
        elif _challenge_matches(text, phrase):
            last_voice_challenge_at = time.perf_counter()
            log("SUCCESS", "[SECURITY] liveness challenge passed")
            return True
        else:
            log("WARNING", f"[SECURITY] challenge phrase mismatch heard='{text}'")
        if attempt < attempts - 1:
            speak("I did not verify that. Try once more.")
    return False


def _make_challenge_phrase() -> str:
    words = _config_csv(
        "voice_challenge_words",
        "blue,red,white,water,coffee,music,table,phone,window,market,paper,camera,river,cloud",
    )
    count = max(1, int(load_config().get("voice_challenge_word_count", 2)))
    if len(words) <= count:
        chosen = words
    else:
        chosen = random.SystemRandom().sample(words, count)
    return " ".join(chosen)


def _challenge_matches(heard: str, expected: str) -> bool:
    heard_tokens = _normalize_for_attention(heard).split()
    expected_tokens = _normalize_for_attention(expected).split()
    if not expected_tokens:
        return False
    pos = 0
    for token in heard_tokens:
        if token == expected_tokens[pos]:
            pos += 1
            if pos == len(expected_tokens):
                return True
    return False


def _attention_decision(text: str, expect_reply: bool = False) -> tuple[bool, str, str]:
    config = load_config()
    cleaned = _strip_attention_name(text)
    normalized = _normalize_for_attention(text)
    attention_hints = _attention_runtime_hints(config)
    if _looks_like_stt_prompt_leak(normalized):
        return False, cleaned, "stt_prompt"
    if not bool(config.get("attention_gate_enabled", True)):
        return True, cleaned, "disabled"
    if _is_shutdown_phrase(normalized):
        return True, cleaned, "shutdown"
    if expect_reply:
        return True, cleaned, "followup"
    if _mentions_assistant(normalized):
        return True, cleaned, "name"
    mode = str(config.get("attention_mode", "smart")).strip().lower()
    if mode in {"name", "name_only", "strict"}:
        if bool(config.get("attention_action_recovery_enabled", False)) and _looks_like_low_risk_action(normalized):
            return True, cleaned, "action_recovery"
        if bool(config.get("attention_safe_request_recovery_enabled", False)) and _looks_like_safe_voice_request(normalized):
            return True, cleaned, "safe_request_recovery"
        return False, cleaned, "name_required"
    if float(attention_hints.get("name_strictness") or 0.0) >= 0.75:
        return False, cleaned, "adaptive_strict"
    if _looks_like_side_conversation(normalized):
        return False, cleaned, "side_cue"
    if _looks_like_assistant_request(normalized):
        return True, cleaned, "request"
    if float(attention_hints.get("name_strictness") or 1.0) <= 0.3 and _looks_like_safe_voice_request(normalized):
        return True, cleaned, "adaptive_safe_request"
    return False, cleaned, "not_addressed"


def _strip_attention_name(text: str) -> str:
    cleaned = text.strip()
    for name in _attention_names():
        pattern = name.replace(" ", r"\s+")
        cleaned = re_sub_attention(rf"^\s*(hey|okay|ok)?\s*{pattern}\b[\s,.:;-]*", "", cleaned)
        cleaned = re_sub_attention(rf"^\s*this\s+is\s+{pattern}\b[\s,.:;-]*", "", cleaned)
        cleaned = re_sub_attention(rf"\b{pattern}\b", "", cleaned)
    cleaned = re_sub_attention(r"\b(yeah|please)\b\s*$", "", cleaned)
    cleaned = re_sub_attention(r"\s+", " ", cleaned).strip(" ,.!?:;")
    return cleaned or text.strip()


def _mentions_assistant(normalized: str) -> bool:
    return any(re_search_attention(rf"\b{name}\b", normalized) for name in _attention_names())


def _looks_like_side_conversation(normalized: str) -> bool:
    phrases = _config_csv(
        "attention_side_conversation_phrases",
        "i said,he said,she said,they said,tell him,tell her,ask him,ask her,look at him,look at her",
    )
    return any(phrase and phrase in normalized for phrase in phrases)


def _looks_like_assistant_request(normalized: str) -> bool:
    prefixes = _config_csv(
        "attention_request_prefixes",
        "can you,could you,would you,will you,do you,are you,what is,what's,who is,who are,where is,when is,why is,how do,how can,how are,tell me,explain,define,search,open,launch,close,remember,write,code,build,create,find,look up",
    )
    return any(normalized.startswith(prefix) for prefix in prefixes if prefix)


def _looks_like_low_risk_action(normalized: str) -> bool:
    return bool(
        re_search_attention(
            r"^(open|launch|start|close)\s+(chrome|gmail|notepad|vscode|vs code|visual studio code|explorer|spotify|camera|windows camera|webcam)\b",
            normalized,
        )
        or re_search_attention(r"^(search|google|look up)\s+\S+", normalized)
    )


def _looks_like_safe_voice_request(normalized: str) -> bool:
    safe_patterns = [
        r"(?:hello|hi|hey)",
        r"(?:how are you|how are you doing|how are you doing today|how's it going)",
        r"(?:what time is it|what the time is|what is the time|what's the time|current time)",
        r"(?:what date is it|what the date is|what is the date|what's the date|current date|today's date)",
        r"(?:(?:what|which) day(?: is it| is today)?)",
        r"(?:what is your name|what's your name|who are you)",
        r"(?:can you code|do you code|can you help me code|do you know how to code)",
        r"(?:what can you do|what are your abilities)",
    ]
    return any(re_search_attention(rf"^{pattern}$", normalized) for pattern in safe_patterns)


def _attention_names() -> list[str]:
    names = set(_config_csv("attention_names", "friday,friiday,friady,friyday,fry day,freiday,freddie,freddy,fred,fridays,computer,jarvis,jervis"))
    try:
        if bool(load_config().get("adaptive_attention_enabled", True)):
            profile = adaptive_attention.current_profile()
            aliases = profile.get("profile", {}).get("learned_aliases", [])
            names.update(str(alias).strip().lower() for alias in aliases if str(alias).strip())
    except Exception:
        pass
    return sorted(names, key=lambda item: (-len(item), item))


def _attention_runtime_hints(config: dict | None = None) -> dict:
    cfg = config or load_config()
    if not bool(cfg.get("adaptive_attention_enabled", True)):
        return {}
    try:
        return adaptive_attention.recommended_attention_config()
    except Exception:
        return {}


def _looks_like_stt_prompt_leak(normalized: str) -> bool:
    prompt_leak_phrases = (
        "audio is a short command for an ai assistant",
        "the audio is a short command for an ai assistant",
        "short command for an ai assistant named",
        "common words include",
    )
    return any(phrase in normalized for phrase in prompt_leak_phrases)


def _is_shutdown_phrase(text: str) -> bool:
    normalized = _normalize_for_attention(text)
    return normalized in {"exit", "quit", "shutdown", "shut down", "stop listening"}


def _config_csv(key: str, default: str) -> list[str]:
    return [item.strip().lower() for item in str(load_config().get(key, default)).split(",") if item.strip()]


def _normalize_for_attention(text: str) -> str:
    import re

    cleaned = re.sub(r"[^\w\s']", " ", text or "").lower()
    return re.sub(r"\s+", " ", cleaned).strip()


def re_sub_attention(pattern: str, repl: str, text: str) -> str:
    import re

    return re.sub(pattern, repl, text, flags=re.IGNORECASE)


def re_search_attention(pattern: str, text: str) -> bool:
    import re

    return re.search(pattern, text, flags=re.IGNORECASE) is not None


def _wake_test_loop() -> int:
    fired = threading.Event()
    state = {"max_score": 0.0, "last_log": 0.0}

    def on_score(score: float, energy: float) -> None:
        state["max_score"] = max(state["max_score"], score)
        now = time.perf_counter()
        if now - state["last_log"] >= 1.0:
            log("INFO", f"[WAKE] score={score:.2f} max={state['max_score']:.2f} energy={energy:.0f}")
            state["last_log"] = now

    def on_wake() -> None:
        fired.set()
        log("SUCCESS", f"[WAKE] detected; max_score={state['max_score']:.2f}")

    listener = WakeWordListener(callback=on_wake, score_callback=on_score)
    assistant_name = str(load_config().get("jarvis_name", "Friday"))
    log("SUCCESS", f"Wake-word test running. Say 'Hey {assistant_name}'. Press Ctrl+C to stop.")
    listener.start()
    try:
        while True:
            time.sleep(0.2)
            if fired.is_set():
                fired.clear()
                state["max_score"] = 0.0
    except KeyboardInterrupt:
        listener.stop()
        log("INFO", "Wake-word test stopped.")
    return 0


def _queue_command(initial_audio: bytes = b"", source: str = "wake_word") -> None:
    command_audio.put((initial_audio or b"", source))
    command_ready.set()


def _drain_command_audio() -> tuple[bytes, str]:
    latest = (b"", "wake_word")
    while True:
        try:
            latest = command_audio.get_nowait()
        except queue.Empty:
            return latest


def _clear_command_audio() -> None:
    while True:
        try:
            command_audio.get_nowait()
        except queue.Empty:
            return


def _wake_score_logger():
    state = {"max_score": 0.0, "last_log": 0.0}

    def on_score(score: float, energy: float) -> None:
        state["max_score"] = max(state["max_score"], score)
        now = time.perf_counter()
        if now - state["last_log"] >= 1.0:
            log("DEBUG", f"[WAKE] score={score:.2f} max={state['max_score']:.2f} energy={energy:.0f}")
            state["last_log"] = now
        if score >= float(load_config().get("wake_word_threshold", 0.35)):
            state["max_score"] = 0.0

    return on_score


def _mic_test_loop() -> int:
    try:
        import numpy as np
        import sounddevice as sd
    except Exception as exc:
        print(f"Could not run mic test: {exc}")
        return 1

    config = load_config()
    device = config.get("audio_input_device", None)
    if device in {"", "default", "none"}:
        device = None
    seconds = float(config.get("mic_test_seconds", 10.0))
    frame_samples = 1600
    sample_rate = 16000
    max_energy = 0.0
    print(f"Mic test running for {seconds:.0f}s. Speak normally. Device: {device or 'default'}")
    try:
        with sd.InputStream(device=device, samplerate=sample_rate, channels=1, dtype="int16", blocksize=frame_samples) as stream:
            end_at = time.perf_counter() + seconds
            while time.perf_counter() < end_at:
                frame, overflowed = stream.read(frame_samples)
                pcm = np.asarray(frame).reshape(-1).astype(np.int16)
                energy = float(np.abs(pcm.astype(np.int32)).mean())
                max_energy = max(max_energy, energy)
                marker_count = min(40, int(energy / 100))
                marker = "#" * marker_count
                print(f"energy={energy:7.1f} max={max_energy:7.1f} {marker}")
                if overflowed:
                    print("input overflow")
    except KeyboardInterrupt:
        pass
    except Exception as exc:
        print(f"Mic test failed: {exc}")
        return 1
    if max_energy < 50:
        print("Result: almost silence. Try another audio_input_device.")
    elif max_energy < 250:
        print("Result: very quiet. Move closer, raise mic gain, or try another device.")
    else:
        print("Result: mic input detected.")
    return 0


def _enroll_wake(samples: int) -> int:
    if stt.sd is None:
        log("ERROR", "Audio capture dependency sounddevice is not installed.")
        return 1
    samples = max(3, int(samples))
    existing = len(load_templates())
    assistant_name = str(load_config().get("jarvis_name", "Friday"))
    log("INFO", f"Personal wake enrollment: recording {samples} samples. Existing templates: {existing}.")
    log("INFO", f"For each sample, say only: Hey {assistant_name}")
    recorded = 0
    attempts = 0
    while recorded < samples and attempts < samples * 3:
        attempts += 1
        input(f"Press Enter, then say 'Hey {assistant_name}' for sample {recorded + 1}/{samples}...")
        _ready_ack()
        try:
            with stt.sd.InputStream(device=stt._audio_device(), samplerate=stt.SAMPLE_RATE, channels=1, dtype="int16", blocksize=stt.FRAME_SAMPLES) as stream:
                audio = stt.record_until_silence_energy(stream)
        except Exception as exc:
            log("ERROR", f"Could not record wake sample: {exc}")
            return 1
        if not audio:
            log("WARNING", "No speech detected. Try again, closer to the microphone.")
            continue
        try:
            total = add_template(audio)
        except Exception as exc:
            log("ERROR", f"Could not save wake template: {exc}")
            return 1
        recorded += 1
        log("SUCCESS", f"Saved wake sample {recorded}/{samples}. Total templates: {total}.")
    if recorded < samples:
        log("WARNING", f"Only recorded {recorded}/{samples} samples.")
        return 1
    log("SUCCESS", "Personal wake-word enrollment complete. Run: python jarvis.py --wake-test")
    return 0


def _enroll_speaker(samples: int, kind: str = "positive") -> int:
    if stt.sd is None:
        log("ERROR", "Audio capture dependency sounddevice is not installed.")
        return 1
    samples = max(3, int(samples))
    kind = "negative" if kind == "negative" else "positive"
    existing = len([sample for sample in load_voice_samples() if sample.get("kind", "positive") == kind])
    label = str(load_config().get("user_name", "user"))
    positive_prompts = [
        "My name is Daniel, and this is my Friday voice profile.",
        "Friday, this device should respond to my voice.",
        "Can you hear me clearly from this microphone?",
        "Today I am testing speaker recognition on Windows.",
        "The quick brown fox jumps over the lazy dog.",
        "Please remember this as my normal speaking voice.",
    ]
    negative_prompts = [
        "This is not Daniel speaking to Friday.",
        "Friday should not respond to this voice.",
        "Can you hear this different person clearly?",
        "This is a roommate testing speaker rejection.",
        "The quick brown fox jumps over the lazy dog.",
        "Please remember this as a blocked comparison voice.",
    ]
    prompts = negative_prompts if kind == "negative" else positive_prompts
    title = "Negative speaker enrollment" if kind == "negative" else "Speaker enrollment"
    log("INFO", f"{title}: recording {samples} samples. Existing {kind} samples: {existing}.")
    if kind == "negative":
        log("INFO", "Have your roommate speak these lines. Friday will learn this as a comparison voice, not as you.")
    else:
        log("INFO", "Use your normal voice. Vary the sentence a little; do not whisper or shout.")
    recorded = 0
    attempts = 0
    while recorded < samples and attempts < samples * 3:
        attempts += 1
        prompt = prompts[recorded % len(prompts)]
        input(f"Press Enter, then say: \"{prompt}\" ({recorded + 1}/{samples})...")
        _ready_ack()
        try:
            audio = stt.record_audio()
        except Exception as exc:
            log("ERROR", f"Could not record speaker sample: {exc}")
            return 1
        if not audio:
            log("WARNING", "No speech detected. Try again, closer to the microphone.")
            continue
        try:
            total = add_voice_sample(audio, label=label, kind=kind)
        except Exception as exc:
            log("ERROR", f"Could not save speaker sample: {exc}")
            return 1
        recorded += 1
        log("SUCCESS", f"Saved {kind} speaker sample {recorded}/{samples}. Total {kind} samples: {total}.")
    if recorded < samples:
        log("WARNING", f"Only recorded {recorded}/{samples} samples.")
        return 1
    log("SUCCESS", "Speaker enrollment complete. Run: python jarvis.py --speaker-test")
    return 0


def _speaker_test_loop() -> int:
    if stt.sd is None:
        log("ERROR", "Audio capture dependency sounddevice is not installed.")
        return 1
    try:
        verifier = SpeakerVerifier()
    except Exception as exc:
        log("ERROR", f"Speaker test unavailable ({exc}).")
        return 1
    log("SUCCESS", "Speaker test running. Speak short sentences. Press Ctrl+C to stop.")
    try:
        while True:
            audio = stt.record_audio()
            if not audio:
                log("WARNING", "No speech detected.")
                continue
            details = verifier.score_details(audio)
            match = bool(details["match"])
            level = "SUCCESS" if match else "INFO"
            status = "matched profile" if match else "rejected"
            log(
                level,
                f"[SPEAKER] {status}; score={float(details['positive_score']):.2f} "
                f"centroid={float(details['centroid_score']):.2f} neg={float(details['negative_score']):.2f} "
                f"margin={float(details['margin']):.2f} threshold={verifier.threshold:.2f}/{verifier.centroid_threshold:.2f} "
                f"backend={details['backend']}",
            )
    except KeyboardInterrupt:
        log("INFO", "Speaker test stopped.")
    return 0


def _terminal_loop(speak_replies: bool = False) -> None:
    while True:
        user_text = input("You: ").strip()
        if _is_shutdown_phrase(user_text):
            raise KeyboardInterrupt
        if user_text:
            _handle_text(user_text, time.perf_counter(), speak_reply=speak_replies)


def _followup_loop(reply: str, speak_replies: bool = True) -> None:
    config = load_config()
    if not bool(config.get("conversation_followup_enabled", True)):
        return
    turns = int(config.get("conversation_followup_turns", 1))
    for _ in range(max(0, turns)):
        if not _reply_expects_answer(reply):
            return
        log("SUCCESS", "Listening for your reply...")
        t0 = time.perf_counter()
        user_text, reason = _capture_attended_text(expect_reply=True)
        if not user_text:
            if reason == "empty":
                log("WARNING", "No follow-up reply detected.")
            return
        if _is_shutdown_phrase(user_text):
            raise KeyboardInterrupt
        reply = _handle_text(user_text, t0, speak_reply=speak_replies, secure_voice=True)
        reply = _drain_barge_in_commands(speak_replies=speak_replies) or reply


def _reply_expects_answer(reply: str) -> bool:
    text = reply.strip()
    if not text:
        return False
    return text.endswith("?")


def _drain_barge_in_commands(speak_replies: bool = True, max_commands: int = 2) -> str:
    """Run replacement commands captured while Friday was speaking."""

    deadline = time.perf_counter() + max(0.0, float(load_config().get("barge_in_command_drain_timeout_seconds", 0.4)))
    handled = 0
    last_reply = ""
    while handled < max_commands:
        item = barge_in.pop_pending_command()
        if item is None:
            if time.perf_counter() >= deadline:
                break
            time.sleep(0.05)
            continue
        command = str(item.get("command") or "").strip()
        if not command:
            continue
        log("INFO", f"[BARGE-IN] handling interrupt command='{command}'")
        if _is_shutdown_phrase(command):
            raise KeyboardInterrupt
        last_reply = _handle_text(command, time.perf_counter(), speak_reply=speak_replies, secure_voice=True)
        handled += 1
    return last_reply


def _handle_text(user_text: str, start: float, speak_reply: bool = True, secure_voice: bool = False) -> str:
    assistant_log = str(load_config().get("jarvis_name", "Friday")).upper()
    log("YOU", user_text)
    if secure_voice and _requires_voice_challenge(user_text) and not _voice_liveness_challenge():
        reply = "I could not verify you. Action cancelled."
        log(assistant_log, reply)
        if speak_reply:
            speak(reply)
        return reply
    brain_start = time.perf_counter()
    reply = orchestrator.handle_command(user_text)
    if not reply.strip():
        reply = "I heard you, but I do not have a useful answer yet."
    log("INFO", f"[PERF] brain={(time.perf_counter() - brain_start) * 1000:.0f}ms")
    log(assistant_log, reply)
    if speak_reply:
        speech_start = time.perf_counter()
        speak(reply)
        log("INFO", f"[PERF] tts={(time.perf_counter() - speech_start) * 1000:.0f}ms")
    e2e = (time.perf_counter() - start) * 1000
    log("INFO", f"[PERF] e2e={e2e:.0f}ms")
    if e2e > 5000:
        log("WARNING", f"NFR-02 BREACH: e2e={e2e:.0f}ms > 5000ms target")
    return reply


def _wake_ack() -> None:
    config = load_config()
    if not bool(config.get("wake_ack_beep", True)):
        return
    _beep(int(config.get("wake_ack_frequency", 880)), int(config.get("wake_ack_duration_ms", 90)))


def _ready_ack() -> None:
    config = load_config()
    if not bool(config.get("startup_ready_beep", True)):
        return
    _beep(int(config.get("startup_ready_frequency", 660)), int(config.get("startup_ready_duration_ms", 80)))


def _beep(frequency: int, duration_ms: int) -> None:
    if winsound is None:
        return
    try:
        winsound.Beep(frequency, duration_ms)
    except Exception:
        return


def _print_audio_devices() -> None:
    try:
        import sounddevice as sd

        print(sd.query_devices())
        print(f"\nDefault input/output: {sd.default.device}")
    except Exception as exc:
        print(f"Could not list audio devices: {exc}")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Friday personal AI agent.")
    parser.add_argument("--debug", action="store_true", help="Enable verbose logging.")
    parser.add_argument("--text", action="store_true", help="Use terminal input instead of voice mode.")
    parser.add_argument("--listen-once", action="store_true", help="Record one spoken command immediately without wake word.")
    parser.add_argument("--listen-loop", action="store_true", help="Continuously record spoken commands without wake word.")
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument("--continuous", action="store_true", help="Keep listening without a wake word while the app is running.")
    mode_group.add_argument("--wake-word", action="store_true", help="Require the wake word before each command.")
    parser.add_argument("--wake-test", action="store_true", help="Show wake-word scores without STT or LLM.")
    parser.add_argument("--enroll-wake", nargs="?", const=5, type=int, help="Record personal Hey Friday wake templates.")
    parser.add_argument("--clear-wake-enrollment", action="store_true", help="Delete personal wake-word templates.")
    parser.add_argument("--enroll-speaker", nargs="?", const=6, type=int, help="Record your voice profile for speaker verification.")
    parser.add_argument("--enroll-speaker-negative", nargs="?", const=4, type=int, help="Record another person's voice as a rejection example.")
    parser.add_argument("--clear-speaker-enrollment", action="store_true", help="Delete the enrolled speaker profile.")
    parser.add_argument("--speaker-test", action="store_true", help="Show speaker verification scores without STT or LLM.")
    parser.add_argument("--stt-benchmark", action="store_true", help="Record one phrase and compare local STT model latency/accuracy.")
    parser.add_argument("--stt-benchmark-models", help="Comma-separated STT models to benchmark.")
    parser.add_argument("--stt-benchmark-expected", default="", help="Optional expected transcript for WER scoring.")
    parser.add_argument("--audio-devices", action="store_true", help="List audio devices and exit.")
    parser.add_argument("--mic-test", action="store_true", help="Show live microphone energy for the configured input device.")
    parser.add_argument("--local-voices", action="store_true", help="List local pyttsx3/Windows voices and exit.")
    parser.add_argument("--fast-voice", action="store_true", help="Use low-latency voice/session settings for this run.")
    parser.add_argument("--voice-preview", action="store_true", help="Play free Edge neural voice samples and exit.")
    parser.add_argument(
        "--voice-preview-text",
        default="Hello, I am Friday. Ready when you are.",
        help="Text to use with --voice-preview.",
    )
    parser.add_argument("--voice-warmup", action="store_true", help="Pre-generate common Edge voice replies and exit.")
    parser.add_argument("--no-speak", action="store_true", help="Do not speak replies in voice/listen-once modes.")
    parser.add_argument("--speak", action="store_true", help="Speak replies in terminal input mode.")
    parser.add_argument("--api", action="store_true", help="Run the protected local FastAPI server for v2 dashboard clients.")
    parser.add_argument("--api-host", help="Host for --api. Defaults to config api_host.")
    parser.add_argument("--api-port", type=int, help="Port for --api. Defaults to config api_port.")
    return parser.parse_args()


def _voice_preview(text: str) -> int:
    try:
        voices = preview_edge_voices(text or "Hello, I am Friday. Ready when you are.")
    except Exception as exc:
        log("ERROR", f"Voice preview unavailable ({exc}).")
        return 1
    log("SUCCESS", "Previewed Edge voices: " + ", ".join(voices))
    return 0


def _print_local_voices() -> int:
    voices = local_voice_options()
    if not voices:
        print("No local pyttsx3 voices found.")
        return 1
    for option in voices:
        print(f"[{option['index']}] {option['name']}")
        print(f"    id: {option['id']}")
        if option.get("languages"):
            print(f"    languages: {option['languages']}")
        if option.get("gender"):
            print(f"    gender: {option['gender']}")
        if option.get("age"):
            print(f"    age: {option['age']}")
    print("\nTo use one, set pyttsx3_voice_id in config.json to its id, name, or a unique name fragment.")
    return 0


def _voice_warmup() -> int:
    try:
        warmed = warm_edge_voice_cache()
    except Exception as exc:
        log("ERROR", f"Voice warmup unavailable ({exc}).")
        return 1
    log("SUCCESS", f"Warmed {len(warmed)} Edge voice replies.")
    return 0


def _voice_dependency_hint(exc: Exception) -> str:
    message = str(exc).lower()
    if "whisper is not installed" not in message:
        return ""
    venv_python = Path(__file__).resolve().parent / ".venv" / "Scripts" / "python.exe"
    if venv_python.exists() and Path(sys.executable).resolve() != venv_python.resolve():
        return "You are using system Python; run .\\.venv\\Scripts\\Activate.ps1 or .\\.venv\\Scripts\\python.exe jarvis.py --debug --fast-voice."
    return "Install voice dependencies with: python -m pip install -r requirements.txt."


def _validate_env(args: argparse.Namespace | None = None) -> None:
    if args is not None and getattr(args, "stt_benchmark", False):
        return
    if args is not None and getattr(args, "api", False):
        _ensure_api_password_for_interactive_run()
    required = _required_env()
    if args is not None and getattr(args, "api", False):
        required["JARVIS_API_PASSWORD"] = REQUIRED_ENV["JARVIS_API_PASSWORD"]
    missing = [key for key in required if _is_placeholder_env(os.getenv(key))]
    if not missing:
        return
    for key in missing:
        print(f"Missing {key}. Get it from {required[key]}")
    sys.exit(1)


def _ensure_api_password_for_interactive_run() -> None:
    if not _is_placeholder_env(os.getenv("JARVIS_API_PASSWORD")):
        return
    if not sys.stdin.isatty():
        return
    print("JARVIS_API_PASSWORD is missing or still placeholder.")
    try:
        password = getpass.getpass("Enter a local dashboard/API password: ").strip()
    except (EOFError, KeyboardInterrupt):
        return
    if _is_placeholder_env(password):
        return
    os.environ["JARVIS_API_PASSWORD"] = password
    try:
        save = input("Save this password to .env for next time? [y/N]: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        save = ""
    if save in {"y", "yes"}:
        _upsert_env_value("JARVIS_API_PASSWORD", password)
        print("Saved JARVIS_API_PASSWORD to .env.")


def _upsert_env_value(key: str, value: str) -> None:
    env_path = Path(__file__).resolve().parent / ".env"
    lines = env_path.read_text(encoding="utf-8").splitlines() if env_path.exists() else []
    updated = False
    output: list[str] = []
    for line in lines:
        if line.strip().startswith("#") or "=" not in line:
            output.append(line)
            continue
        existing_key, _existing_value = line.split("=", 1)
        if existing_key.strip() == key:
            output.append(f"{key}={value}")
            updated = True
        else:
            output.append(line)
    if not updated:
        output.append(f"{key}={value}")
    env_path.write_text("\n".join(output).rstrip() + "\n", encoding="utf-8")


def _run_health_check() -> None:
    required = _required_env()
    for key in REQUIRED_ENV:
        configured = not _is_placeholder_env(os.getenv(key))
        if configured:
            status = "configured"
            level = "SUCCESS"
        elif key in required:
            status = "missing/placeholder"
            level = "WARNING"
        else:
            status = "optional missing/placeholder"
            level = "INFO"
        log(level, f"[HEALTH] {key} {status}")
    log(
        "INFO",
        f"[BUILD] router={orchestrator.ROUTER_BUILD} orchestrator={Path(orchestrator.__file__).resolve()}",
    )


def _required_env() -> dict[str, str]:
    config = load_config()
    required: dict[str, str] = {}
    provider = str(config.get("llm_provider", "anthropic")).lower()
    fallback = str(config.get("llm_fallback_provider", "none")).lower()
    if provider == "anthropic" or fallback == "anthropic":
        required["ANTHROPIC_API_KEY"] = REQUIRED_ENV["ANTHROPIC_API_KEY"]
    if provider == "gemini" or fallback == "gemini":
        required["GEMINI_API_KEY"] = REQUIRED_ENV["GEMINI_API_KEY"]
    if provider == "openrouter" or fallback == "openrouter":
        required["OPENROUTER_API_KEY"] = REQUIRED_ENV["OPENROUTER_API_KEY"]
    if str(config.get("voice_backend", "edge")).lower() == "elevenlabs":
        required["ELEVENLABS_API_KEY"] = REQUIRED_ENV["ELEVENLABS_API_KEY"]
        required["ELEVENLABS_VOICE_ID"] = REQUIRED_ENV["ELEVENLABS_VOICE_ID"]
    return required


def _run_api_server(args: argparse.Namespace, config: dict) -> int:
    try:
        import uvicorn
    except Exception as exc:
        log("ERROR", f"API server unavailable because uvicorn is not installed ({exc}).")
        return 1
    host = str(args.api_host or config.get("api_host", "127.0.0.1"))
    port = int(args.api_port or config.get("api_port", 8000))
    log("SUCCESS", f"[API] protected local server starting at http://{host}:{port}")
    log("INFO", "[API] Login with JARVIS_API_USERNAME/JARVIS_API_PASSWORD, then use Bearer JWT for endpoints.")
    uvicorn.run("api.server:app", host=host, port=port, log_level=str(config.get("api_log_level", "info")))
    return 0


def _check_test_stubs() -> None:
    tests_dir = Path(__file__).resolve().parent / "tests"
    for name in TEST_STUBS:
        if not (tests_dir / name).exists():
            log("WARNING", f"[TEST] missing tests/{name}")


def _start_consolidation_scheduler() -> None:
    global consolidation_scheduler
    try:
        consolidation_scheduler = consolidation.start_scheduler()
    except Exception as exc:
        log("WARNING", f"[CONSOLIDATION] scheduler unavailable ({exc})")


def _start_cloud_sync_scheduler() -> None:
    try:
        scheduler = cloud_sync.start_scheduler()
        if scheduler is not None:
            log("INFO", "[SYNC] cloud sync scheduled")
    except Exception as exc:
        log("WARNING", f"[SYNC] scheduler unavailable ({exc})")


def _seed_learning_tasks() -> None:
    try:
        created = learning_scheduler.seed_learning_tasks()
        if created:
            log("INFO", f"[LEARNING] seeded_tasks={len(created)}")
    except Exception as exc:
        log("WARNING", f"[LEARNING] scheduler unavailable ({exc})")


def _start_background_agents(args: argparse.Namespace | None = None) -> None:
    try:
        if (
            args is not None
            and getattr(args, "fast_voice", False)
            and not bool(load_config().get("v2_start_background_workers_in_fast_voice", False))
        ):
            log("INFO", "[AGENTS] background workers paused for fast voice; say 'start agents' when you want them.")
            return
        count = background_agents.start_workers()
        if count:
            log("INFO", f"[AGENTS] background_workers={count}")
    except Exception as exc:
        log("WARNING", f"[AGENTS] background workers unavailable ({exc})")


def _start_autonomy_supervisor(args: argparse.Namespace | None = None) -> None:
    try:
        if (
            args is not None
            and getattr(args, "fast_voice", False)
            and not bool(load_config().get("autonomy_supervisor_in_fast_voice", True))
        ):
            log("INFO", "[AUTONOMY] supervisor paused for fast voice.")
            return
        state = autonomy_engine.start_supervisor()
        if state.get("running"):
            log("INFO", "[AUTONOMY] supervisor started")
    except Exception as exc:
        log("WARNING", f"[AUTONOMY] supervisor unavailable ({exc})")


def _start_proactive_speech(args: argparse.Namespace | None, *, voice_enabled: bool, speak_replies: bool) -> None:
    global proactive_speech_started
    if not voice_enabled or not speak_replies:
        return
    if args is not None and getattr(args, "fast_voice", False) and not bool(load_config().get("proactive_speech_in_fast_voice", False)):
        log("INFO", "[PROACTIVE] speech paused for fast voice; enable proactive_speech_in_fast_voice to allow it.")
        return
    try:
        proactive_speech_started = proactive_speech.start_service(speak, log)
        if proactive_speech_started:
            log("INFO", "[PROACTIVE] speech monitor started")
    except Exception as exc:
        log("WARNING", f"[PROACTIVE] speech monitor unavailable ({exc})")


def _start_proactive_guardian(args: argparse.Namespace | None = None) -> None:
    try:
        if (
            args is not None
            and getattr(args, "fast_voice", False)
            and not bool(load_config().get("proactive_guardian_in_fast_voice", True))
        ):
            log("INFO", "[GUARDIAN] paused for fast voice; enable proactive_guardian_in_fast_voice to allow it.")
            return
        if proactive_guardian.start_service(log):
            log("INFO", "[GUARDIAN] proactive guardian started")
    except Exception as exc:
        log("WARNING", f"[GUARDIAN] unavailable ({exc})")


def _start_awake_services(args: argparse.Namespace | None = None) -> None:
    try:
        if event_nervous_system.start_service(log):
            log("INFO", "[EVENTS] nervous system started")
    except Exception as exc:
        log("WARNING", f"[EVENTS] nervous system unavailable ({exc})")
    try:
        if daily_companion.start_service(log):
            log("INFO", "[COMPANION] daily companion started")
    except Exception as exc:
        log("WARNING", f"[COMPANION] daily companion unavailable ({exc})")
    try:
        if args is not None and getattr(args, "fast_voice", False) and not bool(load_config().get("project_watchdog_in_fast_voice", False)):
            log("INFO", "[PROJECT] watchdog paused for fast voice; enable project_watchdog_in_fast_voice to allow it.")
            return
        if project_watchdog.start_service(log):
            log("INFO", "[PROJECT] watchdog started")
    except Exception as exc:
        log("WARNING", f"[PROJECT] watchdog unavailable ({exc})")


def _start_cognitive_cycle(args: argparse.Namespace | None, *, voice_enabled: bool) -> None:
    global cognitive_cycle_started
    if not voice_enabled:
        return
    try:
        light_mode = bool(args is not None and getattr(args, "fast_voice", False) and load_config().get("cognitive_cycle_light_mode_in_fast_voice", True))
        cognitive_cycle_started = cognitive_cycle.start(light_mode=light_mode)
        if cognitive_cycle_started:
            mode = "light" if light_mode else "full"
            log("INFO", f"[COG] cognitive cycle started mode={mode}")
    except Exception as exc:
        log("WARNING", f"[COG] cognitive cycle unavailable ({exc})")


def _shutdown(listener: WakeWordListener | None) -> None:
    if listener is not None:
        listener.stop()
    try:
        consolidation.stop_scheduler()
    except Exception:
        pass
    try:
        cloud_sync.stop_scheduler()
    except Exception:
        pass
    try:
        background_agents.stop_workers()
    except Exception:
        pass
    try:
        proactive_speech.stop_service()
    except Exception:
        pass
    try:
        proactive_guardian.stop_service()
    except Exception:
        pass
    try:
        event_nervous_system.stop_service()
    except Exception:
        pass
    try:
        daily_companion.stop_service()
    except Exception:
        pass
    try:
        project_watchdog.stop_service()
    except Exception:
        pass
    try:
        cognitive_cycle.stop()
    except Exception:
        pass
    if bool(load_config().get("memory_consolidation_on_shutdown", False)):
        try:
            consolidation.consolidate()
        except Exception as exc:
            log("WARNING", f"[CONSOLIDATION] final run failed ({exc})")
    if bool(load_config().get("shutdown_speech", False)):
        speak("Shutting down. Goodbye.")
    else:
        _beep(440, 70)
    memory.clear_session()
    log("INFO", "Shutdown complete.")
    sys.exit(0)


def _is_placeholder_env(value: str | None) -> bool:
    if not value:
        return True
    normalized = value.strip().lower()
    return normalized in {
        "your_key_here",
        "sk-ant-placeholder",
        "sk-ant-your-key",
        "your_picovoice_key",
        "your_elevenlabs_key",
        "your_alpha_vantage_key",
        "your_gemini_key_here",
        "your_openrouter_key_here",
        "your_api_password_here",
        "your_api_secret_here",
        "yourname@gmail.com",
        "xxxx-xxxx-xxxx-xxxx",
    }


if __name__ == "__main__":
    raise SystemExit(main())
