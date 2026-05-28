"""Voice activity detection and local Whisper transcription."""

from __future__ import annotations

from collections import deque
import json
import os
from pathlib import Path
import re
import requests
import subprocess
import tempfile
import threading
import time
from typing import Any
from urllib.parse import urlencode
import wave

try:
    import numpy as np
    import sounddevice as sd
    import whisper
except Exception:  # pragma: no cover - optional in scaffold tests
    np = None
    sd = None
    whisper = None

try:
    from faster_whisper import WhisperModel as FasterWhisperModel
except Exception:  # pragma: no cover - optional when dependency is absent
    FasterWhisperModel = None

try:
    import websocket
except Exception:  # pragma: no cover - optional when dependency is absent
    websocket = None

from core.config import config_value

SAMPLE_RATE = 16000
FRAME_MS = 30
FRAME_SAMPLES = int(SAMPLE_RATE * FRAME_MS / 1000)
FRAME_BYTES = FRAME_SAMPLES * 2
SILENCE_THRESHOLD = 10
MAX_FRAMES = 300
ENERGY_THRESHOLD = 500

whisper_model = None
_model_name: str | None = None
_model_backend: str | None = None
_model_cache: dict[tuple[str, str, str, str, int], Any] = {}
_model_cache_source: Any = None
_last_transcribe_was_hallucination = False
_last_transcribe_confidence: float | None = None
_last_transcribe_grammar: str = ""
_last_transcribe_rejected_low_confidence = False
_last_transcribe_raw_text = ""


def load_model(name: str | None = None) -> Any:
    global whisper_model, _model_name, _model_backend, _model_cache_source
    backend = _preferred_backend()
    cache_source = (backend, whisper, FasterWhisperModel)
    if _model_cache_source != cache_source:
        _model_cache.clear()
        whisper_model = None
        _model_name = None
        _model_backend = None
        _model_cache_source = cache_source

    model_name = name or str(config_value("stt_model", "base.en"))
    backend_override, model_name = _split_backend_model(model_name)
    if backend_override:
        backend = backend_override
    if _is_windows_speech_name(model_name):
        backend = "windows-speech"
        model_name = "windows-speech"
    backend, model_name = _resolve_backend_and_model(backend, model_name)
    cache_key = _model_cache_key(backend, model_name)
    cached = _model_cache.get(cache_key)
    if cached is not None:
        whisper_model = cached
        _model_name = model_name
        _model_backend = backend
        return cached

    fallback_model = str(config_value("stt_fallback_model", "base.en"))
    start = time.perf_counter()
    try:
        whisper_model = _load_backend_model(backend, model_name)
    except Exception as exc:
        if fallback_model == model_name:
            raise
        _log("WARNING", f"[STT] Could not load {backend} STT model '{model_name}' ({exc}). Falling back to '{fallback_model}'.")
        fallback_backend, fallback_name = _split_backend_model(fallback_model)
        if fallback_backend:
            backend = fallback_backend
            model_name = fallback_name
        else:
            model_name = fallback_model
            if _is_windows_speech_name(model_name):
                backend = "windows-speech"
                model_name = "windows-speech"
        backend, model_name = _resolve_backend_and_model(backend, model_name)
        whisper_model = _load_backend_model(backend, model_name)
        cache_key = _model_cache_key(backend, model_name)
    _model_cache[cache_key] = whisper_model
    _model_name = model_name
    _model_backend = backend
    _log("DEBUG", f"[PERF] stt_model_load={(time.perf_counter() - start) * 1000:.0f}ms backend={backend} model={model_name}")
    return whisper_model


def _preferred_backend() -> str:
    backend = _canonical_backend(str(config_value("stt_backend", "openai")))
    return backend


def _canonical_backend(raw: str) -> str:
    backend = str(raw or "").strip().lower().replace("_", "-")
    if backend in {"groq", "groq-whisper", "groq-stt"}:
        backend = "groq"
    if backend in {"deepgram", "deepgram-stt", "deepgram-stream", "deepgram-streaming", "dg"}:
        backend = "deepgram"
    if backend in {"faster", "fasterwhisper"}:
        backend = "faster-whisper"
    if backend in {"whisper.cpp", "whispercpp", "whisper-cpp", "cpp", "ggml"}:
        backend = "whisper-cpp"
    if backend in {"windows", "windows-speech", "sapi", "system-speech", "native"}:
        backend = "windows-speech"
    if backend not in {"openai", "groq", "deepgram", "faster-whisper", "whisper-cpp", "windows-speech", "auto"}:
        backend = "openai"
    if backend == "auto":
        backend = "faster-whisper" if FasterWhisperModel is not None else "openai"
    return backend


def _split_backend_model(model_name: str) -> tuple[str | None, str]:
    raw = str(model_name or "").strip()
    prefix, sep, rest = raw.partition(":")
    if not sep:
        return None, raw
    backend = _canonical_backend(prefix)
    if prefix.strip().lower().replace("_", "-") in {
        "openai",
        "groq",
        "groq-whisper",
        "groq-stt",
        "deepgram",
        "deepgram-stt",
        "deepgram-stream",
        "deepgram-streaming",
        "dg",
        "faster",
        "fasterwhisper",
        "faster-whisper",
        "whisper.cpp",
        "whispercpp",
        "whisper-cpp",
        "cpp",
        "ggml",
        "windows",
        "windows-speech",
        "sapi",
        "system-speech",
        "native",
    }:
        return backend, rest.strip()
    return None, raw


def _is_windows_speech_name(model_name: str) -> bool:
    return str(model_name or "").strip().lower().replace("_", "-") in {"windows", "windows-speech", "sapi", "system-speech", "native"}


def _resolve_backend_and_model(backend: str, model_name: str) -> tuple[str, str]:
    if backend == "groq":
        return backend, model_name or "whisper-large-v3"
    if backend == "deepgram":
        return backend, model_name or _deepgram_default_model()
    if backend == "windows-speech":
        return backend, model_name or "windows-speech"
    if backend == "whisper-cpp":
        return backend, model_name or _whisper_cpp_default_model_name()
    if backend == "faster-whisper" and FasterWhisperModel is None:
        _log("WARNING", "[STT] faster-whisper is not installed; falling back to OpenAI Whisper.")
        backend = "openai"
    if backend == "openai" and whisper is None:
        if FasterWhisperModel is not None:
            _log("WARNING", "[STT] OpenAI Whisper is not installed; falling back to faster-whisper.")
            backend = "faster-whisper"
        else:
            raise RuntimeError("No Whisper backend is installed.")
    return backend, model_name


def _model_cache_key(backend: str, model_name: str) -> tuple[str, str, str, str, int]:
    if backend == "groq":
        return (
            backend,
            model_name,
            str(config_value("stt_groq_base_url", "https://api.groq.com/openai/v1")).rstrip("/"),
            str(config_value("stt_groq_api_key_env", "GROQ_API_KEY")),
            int(float(config_value("stt_groq_timeout_seconds", 20.0))),
        )
    if backend == "deepgram":
        return (
            backend,
            model_name,
            str(config_value("stt_deepgram_listen_url", "wss://api.deepgram.com/v1/listen")).strip(),
            str(config_value("stt_deepgram_api_key_env", "DEEPGRAM_API_KEY")),
            int(float(config_value("stt_deepgram_timeout_seconds", 15.0))),
        )
    if backend == "windows-speech":
        return (backend, model_name, "", "", 0)
    if backend == "whisper-cpp":
        return (
            backend,
            model_name,
            str(_whisper_cpp_cli_path()),
            str(_whisper_cpp_model_path(model_name)),
            _whisper_cpp_threads(),
        )
    if backend == "faster-whisper":
        return (
            backend,
            model_name,
            str(config_value("stt_device", "cpu")),
            str(config_value("stt_compute_type", "int8")),
            int(config_value("stt_cpu_threads", 0)),
        )
    return (backend, model_name, "", "", 0)


def _load_backend_model(backend: str, model_name: str) -> Any:
    if backend == "groq":
        if not _groq_api_key():
            raise RuntimeError(f"{_groq_api_key_env()} is missing or placeholder.")
        return {"backend": "groq", "name": model_name or "whisper-large-v3"}
    if backend == "deepgram":
        if websocket is None:
            raise RuntimeError("websocket-client is required for Deepgram streaming STT.")
        if not _deepgram_api_key():
            raise RuntimeError(f"{_deepgram_api_key_env()} is missing or placeholder.")
        return {"backend": "deepgram", "name": model_name or _deepgram_default_model()}
    if backend == "windows-speech":
        return {"backend": "windows-speech", "name": model_name or "windows-speech"}
    if backend == "whisper-cpp":
        cli_path = _whisper_cpp_cli_path()
        model_path = _whisper_cpp_model_path(model_name)
        if not cli_path.exists():
            raise RuntimeError(f"whisper.cpp CLI not found at {cli_path}")
        if not model_path.exists():
            raise RuntimeError(f"whisper.cpp model not found at {model_path}")
        return {
            "backend": "whisper-cpp",
            "name": model_name or model_path.name,
            "cli_path": cli_path,
            "model_path": model_path,
            "threads": _whisper_cpp_threads(),
        }
    if backend == "faster-whisper":
        if FasterWhisperModel is None:
            raise RuntimeError("faster-whisper is not installed.")
        return FasterWhisperModel(
            model_name,
            device=str(config_value("stt_device", "cpu")),
            compute_type=str(config_value("stt_compute_type", "int8")),
            cpu_threads=int(config_value("stt_cpu_threads", 0)),
            num_workers=int(config_value("stt_num_workers", 1)),
        )
    if whisper is None:
        raise RuntimeError("Whisper is not installed.")
    return _load_whisper_model_with_repair(model_name)


def record_until_silence(vad: Any, stream: Any) -> bytes:
    frames: list[bytes] = []
    silent_count = 0
    speech_started = False
    for _ in range(MAX_FRAMES):
        frame = stream.read(FRAME_SAMPLES, exception_on_overflow=False)
        is_speech = vad.is_speech(frame, SAMPLE_RATE)
        frames.append(frame)
        if is_speech:
            speech_started = True
            silent_count = 0
        elif speech_started:
            silent_count += 1
        if speech_started and silent_count >= SILENCE_THRESHOLD:
            break
    return b"".join(frames) if speech_started else b""


def record_until_silence_energy(stream: Any, initial_audio: bytes = b"") -> bytes:
    if np is None:
        raise RuntimeError("numpy is required for audio capture.")

    max_frames = _frames_for_seconds(float(config_value("stt_max_seconds", 8.0)))
    silence_frames = _frames_for_ms(int(config_value("stt_silence_ms", 700)))
    pre_roll_frames = _frames_for_ms(int(config_value("stt_pre_roll_ms", 240)))
    min_threshold = float(config_value("stt_min_energy_threshold", 180))
    noise_multiplier = float(config_value("stt_noise_multiplier", 3.0))

    frames: list[bytes] = [initial_audio] if initial_audio else []
    pre_roll: deque[bytes] = deque(maxlen=pre_roll_frames)
    silent_count = 0
    speech_started = bool(initial_audio)
    noise_floor = min_threshold / noise_multiplier
    active_threshold = min_threshold
    started_at = time.perf_counter()

    for _ in range(max_frames):
        frame, overflowed = stream.read(FRAME_SAMPLES)
        if overflowed:
            _log("WARNING", "[STT] input overflow; continuing")
        pcm = np.asarray(frame, dtype=np.int16).reshape(-1)
        energy = float(np.abs(pcm.astype(np.int32)).mean())
        frame_bytes = pcm.tobytes()
        active_threshold = max(min_threshold, noise_floor * noise_multiplier)

        if energy >= active_threshold:
            if not speech_started:
                frames.extend(pre_roll)
            speech_started = True
            silent_count = 0
            frames.append(frame_bytes)
        elif speech_started:
            silent_count += 1
            frames.append(frame_bytes)
        else:
            pre_roll.append(frame_bytes)
            noise_floor = (noise_floor * 0.95) + (energy * 0.05)

        if speech_started and silent_count >= silence_frames:
            break

    audio = b"".join(frame for frame in frames if frame)
    duration_ms = (time.perf_counter() - started_at) * 1000
    audio_seconds = len(audio) / (SAMPLE_RATE * 2) if audio else 0.0
    _log("DEBUG", f"[PERF] stt_record={duration_ms:.0f}ms audio={audio_seconds:.1f}s threshold={active_threshold:.0f}")
    return audio if speech_started else b""


def transcribe(audio_bytes: bytes, model: Any = None, model_name: str | None = None, strip_wake: bool = True) -> str:
    global _last_transcribe_was_hallucination, _last_transcribe_confidence, _last_transcribe_rejected_low_confidence, _last_transcribe_raw_text
    _last_transcribe_was_hallucination = False
    _last_transcribe_confidence = None
    _last_transcribe_rejected_low_confidence = False
    _last_transcribe_raw_text = ""
    if not audio_bytes:
        _log("DEBUG", "[STT] silence_detected")
        return ""
    if model_name:
        model = model or load_model(model_name)
    model = model or whisper_model
    if model is None:
        model = load_model()
    backend = _backend_for_model(model)
    start = time.perf_counter()
    audio_np = None
    try:
        if backend == "windows-speech":
            raw_text = _transcribe_with_windows_speech(audio_bytes)
        elif backend == "groq":
            raw_text = _transcribe_with_groq(audio_bytes, model)
        elif backend == "deepgram":
            raw_text = _transcribe_with_deepgram(audio_bytes, model)
        elif backend == "whisper-cpp":
            raw_text = _transcribe_with_whisper_cpp(audio_bytes, model)
        else:
            if np is None:
                raise RuntimeError("numpy is required for transcription.")
            audio_np = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32) / 32768.0
            raw_text = _transcribe_with_faster_whisper(model, audio_np) if backend == "faster-whisper" else _transcribe_with_openai(model, audio_np)
        return _finish_transcription(raw_text, audio_bytes, backend, strip_wake, start)
    finally:
        if audio_np is not None:
            del audio_np


def _finish_transcription(raw_text: str, audio_bytes: bytes, backend: str, strip_wake: bool, start: float) -> str:
    global _last_transcribe_was_hallucination, _last_transcribe_raw_text
    _last_transcribe_raw_text = str(raw_text or "").strip()
    if _looks_like_hallucination(raw_text):
        _last_transcribe_was_hallucination = True
        _log("WARNING", "[STT] discarded prompt-like hallucination")
        text = ""
    else:
        cleaned_text = strip_wake_phrase(raw_text) if strip_wake else raw_text
        text = clean_transcript(cleaned_text)
    _log("DEBUG", f"[PERF] stt_transcribe={(time.perf_counter() - start) * 1000:.0f}ms")
    confidence = f" confidence={_last_transcribe_confidence:.2f}" if _last_transcribe_confidence is not None else ""
    _log("DEBUG", f"[STT] backend={backend}{confidence} text='{text}'")
    _record_voice_reliability_sample(
        text,
        raw_text=raw_text,
        audio_seconds=len(audio_bytes) / (SAMPLE_RATE * 2) if audio_bytes else 0.0,
        backend=backend,
        accepted=bool(text) and not _last_transcribe_was_hallucination and not _last_transcribe_rejected_low_confidence,
    )
    return text


def _backend_for_model(model: Any) -> str:
    if isinstance(model, dict) and model.get("backend"):
        return str(model["backend"])
    if model is whisper_model:
        return _model_backend or _preferred_backend()
    return "openai"


def _record_voice_reliability_sample(
    heard_text: str,
    *,
    raw_text: str,
    audio_seconds: float,
    backend: str,
    accepted: bool,
) -> None:
    try:
        if not bool(config_value("voice_reliability_record_samples", True)):
            return
        from core import voice_reliability

        voice_reliability.record_sample(
            heard_text,
            raw_text=raw_text,
            audio_seconds=audio_seconds,
            backend=backend,
            confidence=_last_transcribe_confidence,
            accepted=accepted,
            correction_applied=_last_transcribe_was_hallucination or _last_transcribe_rejected_low_confidence,
            metadata={"strip_wake_applied": True},
        )
    except Exception:
        return


def transcribe_best_effort(audio_bytes: bytes, model: Any = None, strip_wake: bool = True) -> str:
    """Transcribe once, then optionally retry blanks with the fallback model."""
    text = transcribe(audio_bytes, model=model, strip_wake=strip_wake)
    if text or _last_transcribe_was_hallucination or not bool(config_value("stt_retry_on_blank", True)):
        return text
    active_backend = _model_backend or _preferred_backend()
    if active_backend == "groq" and not bool(config_value("stt_groq_fallback_on_blank", False)):
        return text
    if active_backend == "deepgram" and not bool(config_value("stt_deepgram_fallback_on_blank", False)):
        return text
    if active_backend == "windows-speech" and not _windows_whisper_fallback_should_run(audio_bytes):
        return text

    fallback_model = str(config_value("stt_fallback_model", "base.en"))
    active_name = _model_name or str(config_value("stt_model", "base.en"))
    if not fallback_model:
        return text
    fallback_backend, fallback_name = _split_backend_model(fallback_model)
    resolved_fallback_backend, resolved_fallback_name = _resolve_backend_and_model(
        fallback_backend or active_backend,
        fallback_name if fallback_backend else fallback_model,
    )
    if resolved_fallback_backend == active_backend and resolved_fallback_name == active_name:
        return text
    try:
        retry_text = transcribe(audio_bytes, model_name=fallback_model, strip_wake=strip_wake)
    except Exception as exc:
        _log("WARNING", f"[STT] fallback transcription failed ({exc}).")
        return text
    return retry_text or text


def _windows_whisper_fallback_should_run(audio_bytes: bytes) -> bool:
    if not bool(config_value("stt_windows_fallback_enabled", True)):
        return False
    policy = str(config_value("stt_windows_fallback_policy", "low_confidence")).strip().lower()
    if policy in {"off", "false", "disabled", "never"}:
        return False
    audio_seconds = len(audio_bytes) / (SAMPLE_RATE * 2) if audio_bytes else 0.0
    if audio_seconds < float(config_value("stt_windows_fallback_min_audio_seconds", 0.7)):
        return False
    if policy in {"always", "all"}:
        return True
    if policy in {"low_confidence", "reject", "rejected"}:
        return _last_transcribe_rejected_low_confidence
    if policy in {"addressed", "assistant", "name"}:
        return _last_transcribe_rejected_low_confidence and _windows_raw_text_looks_addressed(_last_transcribe_raw_text)
    return _last_transcribe_rejected_low_confidence


def _windows_raw_text_looks_addressed(text: str) -> bool:
    normalized = _normalize_repair_key(text)
    if not normalized:
        return False
    names = {name.lower() for name in _csv_config("attention_names", "friday,freddie,freddy,computer,jarvis")}
    if any(name and name in normalized for name in names):
        return True
    return _looks_like_how_are_you_miss(normalized)


def _transcribe_with_openai(model: Any, audio_np: Any) -> str:
    result = model.transcribe(
        audio_np,
        language=str(config_value("stt_language", "en")),
        fp16=False,
        temperature=float(config_value("stt_temperature", 0.0)),
        beam_size=int(config_value("stt_beam_size", 1)),
        best_of=int(config_value("stt_best_of", 1)),
        condition_on_previous_text=False,
        initial_prompt=str(config_value("stt_initial_prompt", "")) or None,
        no_speech_threshold=float(config_value("stt_no_speech_threshold", 0.6)),
    )
    return str(result.get("text", "")).strip()


def _transcribe_with_faster_whisper(model: Any, audio_np: Any) -> str:
    vad_parameters = {
        "min_silence_duration_ms": int(config_value("stt_vad_min_silence_ms", 500)),
        "speech_pad_ms": int(config_value("stt_vad_speech_pad_ms", 400)),
    }
    hotwords = str(config_value("stt_hotwords", "")).strip() or None
    segments, _info = model.transcribe(
        audio_np,
        language=str(config_value("stt_language", "en")),
        beam_size=int(config_value("stt_beam_size", 1)),
        best_of=int(config_value("stt_best_of", 1)),
        temperature=float(config_value("stt_temperature", 0.0)),
        condition_on_previous_text=False,
        initial_prompt=str(config_value("stt_initial_prompt", "")) or None,
        no_speech_threshold=float(config_value("stt_no_speech_threshold", 0.6)),
        vad_filter=bool(config_value("stt_vad_filter", True)),
        vad_parameters=vad_parameters,
        hotwords=hotwords,
        without_timestamps=bool(config_value("stt_without_timestamps", True)),
        max_new_tokens=int(config_value("stt_max_new_tokens", 96)),
        repetition_penalty=float(config_value("stt_repetition_penalty", 1.0)),
        no_repeat_ngram_size=int(config_value("stt_no_repeat_ngram_size", 0)),
    )
    return " ".join(str(segment.text).strip() for segment in segments if str(segment.text).strip()).strip()


def _transcribe_with_groq(audio_bytes: bytes, model: Any) -> str:
    if not isinstance(model, dict):
        raise RuntimeError("Groq backend requires a loaded API model descriptor.")

    api_key = _groq_api_key()
    if not api_key:
        _log("WARNING", f"[STT] Groq transcription skipped because {_groq_api_key_env()} is missing.")
        return ""

    wav_path = _write_temp_wav(audio_bytes)
    url = str(config_value("stt_groq_base_url", "https://api.groq.com/openai/v1")).rstrip("/") + "/audio/transcriptions"
    response_format = str(config_value("stt_groq_response_format", "text")).strip() or "text"
    data = {
        "model": str(model.get("name") or "whisper-large-v3"),
        "language": str(config_value("stt_language", "en")),
        "response_format": response_format,
        "temperature": str(float(config_value("stt_temperature", 0.0))),
    }
    prompt = str(
        config_value(
            "stt_groq_prompt",
            "",
        )
    ).strip()
    if prompt:
        data["prompt"] = prompt

    try:
        with wav_path.open("rb") as fh:
            response = requests.post(
                url,
                headers={"Authorization": f"Bearer {api_key}"},
                data=data,
                files={"file": ("audio.wav", fh, "audio/wav")},
                timeout=float(config_value("stt_groq_timeout_seconds", 20.0)),
            )
    except Exception as exc:
        _log("WARNING", f"[STT] Groq transcription failed ({exc}).")
        return ""
    finally:
        try:
            wav_path.unlink()
        except OSError:
            pass

    if response.status_code >= 400:
        detail = _last_nonempty_line(response.text)[:220]
        _log("WARNING", f"[STT] Groq transcription failed status={response.status_code} detail={detail}")
        return ""

    if response_format == "text":
        return response.text.strip()
    try:
        parsed = response.json()
    except Exception:
        return response.text.strip()
    return str(parsed.get("text") or "").strip()


def _groq_api_key() -> str:
    value = os.getenv(_groq_api_key_env(), "").strip()
    return "" if _is_placeholder_secret(value) else value


def _groq_api_key_env() -> str:
    return str(config_value("stt_groq_api_key_env", "GROQ_API_KEY")).strip() or "GROQ_API_KEY"


def _transcribe_with_deepgram(audio_bytes: bytes, model: Any) -> str:
    if not isinstance(model, dict):
        raise RuntimeError("Deepgram backend requires a loaded API model descriptor.")

    result = _deepgram_stream_audio(_deepgram_audio_chunks(audio_bytes), model)
    return str(result.get("text") or "").strip()


def _record_and_transcribe_deepgram_streaming(
    model: Any,
    *,
    initial_audio: bytes = b"",
    strip_wake: bool = True,
) -> tuple[str, bytes]:
    global _last_transcribe_was_hallucination, _last_transcribe_confidence, _last_transcribe_rejected_low_confidence, _last_transcribe_raw_text
    _last_transcribe_was_hallucination = False
    _last_transcribe_confidence = None
    _last_transcribe_rejected_low_confidence = False
    _last_transcribe_raw_text = ""

    if sd is None:
        raise RuntimeError("Audio capture dependency sounddevice is not installed.")
    if np is None:
        raise RuntimeError("numpy is required for audio capture.")
    if not isinstance(model, dict):
        raise RuntimeError("Deepgram backend requires a loaded API model descriptor.")

    start = time.perf_counter()
    audio_frames: list[bytes] = []
    capture_state: dict[str, float | bool] = {"record_ms": 0.0, "speech_started": bool(initial_audio)}
    chunks = _deepgram_live_mic_chunks(initial_audio, audio_frames, capture_state)
    result = _deepgram_stream_audio(chunks, model)
    audio = b"".join(audio_frames)
    if not audio or not bool(capture_state.get("speech_started")):
        _log("DEBUG", "[STT] silence_detected")
        return "", b""

    text = _finish_transcription(str(result.get("text") or ""), audio, "deepgram", strip_wake, start)
    record_ms = float(capture_state.get("record_ms") or 0.0)
    transcribe_ms = max(0.0, (time.perf_counter() - start) * 1000 - record_ms)
    audio_seconds = len(audio) / (SAMPLE_RATE * 2)
    _log(
        "INFO",
        f"[PERF] stt_total={(time.perf_counter() - start) * 1000:.0f}ms "
        f"record={record_ms:.0f}ms stream_wait={transcribe_ms:.0f}ms audio={audio_seconds:.1f}s backend=deepgram",
    )
    return text, audio


def _deepgram_live_mic_chunks(initial_audio: bytes, audio_frames: list[bytes], state: dict[str, float | bool]):
    max_frames = _frames_for_seconds(float(config_value("stt_max_seconds", 8.0)))
    silence_frames = _frames_for_ms(int(config_value("stt_silence_ms", 700)))
    pre_roll_frames = _frames_for_ms(int(config_value("stt_pre_roll_ms", 240)))
    min_threshold = float(config_value("stt_min_energy_threshold", 180))
    noise_multiplier = float(config_value("stt_noise_multiplier", 3.0))

    pre_roll: deque[bytes] = deque(maxlen=pre_roll_frames)
    silent_count = 0
    speech_started = bool(initial_audio)
    noise_floor = min_threshold / noise_multiplier
    active_threshold = min_threshold
    started_at = time.perf_counter()

    with sd.InputStream(
        device=_audio_device(),
        samplerate=SAMPLE_RATE,
        channels=1,
        dtype="int16",
        blocksize=FRAME_SAMPLES,
    ) as stream:
        if initial_audio:
            audio_frames.append(initial_audio)
            yield initial_audio

        for _ in range(max_frames):
            frame, overflowed = stream.read(FRAME_SAMPLES)
            if overflowed:
                _log("WARNING", "[STT] input overflow; continuing")
            pcm = np.asarray(frame, dtype=np.int16).reshape(-1)
            energy = float(np.abs(pcm.astype(np.int32)).mean())
            frame_bytes = pcm.tobytes()
            active_threshold = max(min_threshold, noise_floor * noise_multiplier)

            if energy >= active_threshold:
                if not speech_started:
                    for buffered_frame in pre_roll:
                        audio_frames.append(buffered_frame)
                        yield buffered_frame
                speech_started = True
                silent_count = 0
                audio_frames.append(frame_bytes)
                yield frame_bytes
            elif speech_started:
                silent_count += 1
                audio_frames.append(frame_bytes)
                yield frame_bytes
            else:
                pre_roll.append(frame_bytes)
                noise_floor = (noise_floor * 0.95) + (energy * 0.05)

            if speech_started and silent_count >= silence_frames:
                break

    state["record_ms"] = (time.perf_counter() - started_at) * 1000
    state["speech_started"] = speech_started
    audio_seconds = sum(len(frame) for frame in audio_frames) / (SAMPLE_RATE * 2) if audio_frames else 0.0
    _log("DEBUG", f"[PERF] stt_record_stream={float(state['record_ms']):.0f}ms audio={audio_seconds:.1f}s threshold={active_threshold:.0f}")


def _deepgram_stream_audio(chunks: Any, model: dict[str, Any]) -> dict[str, Any]:
    global _last_transcribe_confidence
    ws = _open_deepgram_socket(model)
    final_parts: list[str] = []
    latest_interim = ""
    errors: list[str] = []
    stop_event = threading.Event()
    final_event = threading.Event()

    def reader() -> None:
        global _last_transcribe_confidence
        nonlocal latest_interim
        while not stop_event.is_set():
            try:
                message = ws.recv()
            except Exception as exc:
                if _deepgram_is_timeout(exc):
                    time.sleep(0.01)
                    continue
                if not stop_event.is_set():
                    errors.append(str(exc))
                break
            payload = _deepgram_parse_message(message)
            if not payload:
                continue
            message_type = str(payload.get("type") or "")
            if message_type == "Results":
                transcript, confidence = _deepgram_result_transcript(payload)
                if confidence is not None:
                    _last_transcribe_confidence = confidence
                if transcript and bool(payload.get("is_final")):
                    _deepgram_append_final(final_parts, transcript)
                elif transcript:
                    latest_interim = transcript
                if bool(payload.get("speech_final")) or bool(payload.get("from_finalize")):
                    final_event.set()
            elif message_type == "Error":
                errors.append(str(payload.get("description") or payload.get("message") or payload))
                final_event.set()
            elif message_type in {"CloseStream", "Metadata"}:
                continue

    reader_thread = threading.Thread(target=reader, name="deepgram-stt-reader", daemon=True)
    reader_thread.start()
    sent_any = False
    try:
        for chunk in chunks:
            if not chunk:
                continue
            _deepgram_send_binary(ws, chunk)
            sent_any = True
        if sent_any:
            _deepgram_send_json(ws, {"type": "Finalize"})
            final_event.wait(float(config_value("stt_deepgram_finalize_timeout_seconds", 3.0)))
        _deepgram_send_json(ws, {"type": "CloseStream"})
    except Exception as exc:
        errors.append(str(exc))
    finally:
        stop_event.set()
        try:
            ws.close()
        except Exception:
            pass
        reader_thread.join(timeout=1.0)

    if errors:
        _log("WARNING", f"[STT] Deepgram streaming warning: {errors[0][:220]}")
    text = " ".join(final_parts).strip() or latest_interim.strip()
    return {"text": text, "errors": errors}


def _deepgram_audio_chunks(audio_bytes: bytes):
    chunk_size = _deepgram_chunk_bytes()
    for offset in range(0, len(audio_bytes), chunk_size):
        yield audio_bytes[offset : offset + chunk_size]


def _deepgram_chunk_bytes() -> int:
    chunk_ms = max(FRAME_MS, int(float(config_value("stt_deepgram_chunk_ms", 100))))
    return max(FRAME_BYTES, int(SAMPLE_RATE * 2 * (chunk_ms / 1000)))


def _open_deepgram_socket(model: dict[str, Any]) -> Any:
    if websocket is None:
        raise RuntimeError("websocket-client is required for Deepgram streaming STT.")
    api_key = _deepgram_api_key()
    if not api_key:
        raise RuntimeError(f"{_deepgram_api_key_env()} is missing or placeholder.")
    return websocket.create_connection(
        _deepgram_listen_url(model),
        header=[f"Authorization: Token {api_key}"],
        timeout=float(config_value("stt_deepgram_timeout_seconds", 15.0)),
    )


def _deepgram_listen_url(model: dict[str, Any]) -> str:
    base_url = str(config_value("stt_deepgram_listen_url", "wss://api.deepgram.com/v1/listen")).strip() or "wss://api.deepgram.com/v1/listen"
    params: list[tuple[str, str]] = [
        ("model", str(model.get("name") or _deepgram_default_model())),
        ("encoding", "linear16"),
        ("sample_rate", str(SAMPLE_RATE)),
        ("channels", "1"),
    ]
    language = str(config_value("stt_deepgram_language", config_value("stt_language", "en")) or "").strip()
    if language:
        params.append(("language", language))
    _deepgram_add_bool(params, "interim_results", "stt_deepgram_interim_results", True)
    _deepgram_add_bool(params, "smart_format", "stt_deepgram_smart_format", True)
    _deepgram_add_bool(params, "punctuate", "stt_deepgram_punctuate", True)
    _deepgram_add_bool(params, "vad_events", "stt_deepgram_vad_events", True)
    _deepgram_add_bool(params, "mip_opt_out", "stt_deepgram_mip_opt_out", False)
    endpointing = config_value("stt_deepgram_endpointing_ms", 350)
    if not _config_false(endpointing):
        params.append(("endpointing", str(int(float(endpointing)))))
    utterance_end_ms = config_value("stt_deepgram_utterance_end_ms", 1000)
    if not _config_false(utterance_end_ms):
        params.append(("utterance_end_ms", str(int(float(utterance_end_ms)))))
    for keyword in _deepgram_terms("stt_deepgram_keywords", ""):
        params.append(("keywords", keyword))
    keyterm_default = str(config_value("stt_hotwords", "") or "")
    for keyterm in _deepgram_terms("stt_deepgram_keyterms", keyterm_default):
        params.append(("keyterm", keyterm))
    separator = "&" if "?" in base_url else "?"
    return base_url + separator + urlencode(params)


def _deepgram_add_bool(params: list[tuple[str, str]], query_name: str, config_key: str, default: bool) -> None:
    params.append((query_name, "true" if bool(config_value(config_key, default)) else "false"))


def _deepgram_terms(config_key: str, default: str) -> list[str]:
    raw = config_value(config_key, default)
    if isinstance(raw, (list, tuple)):
        return [str(item).strip() for item in raw if str(item).strip()]
    return [item.strip() for item in str(raw or "").split(",") if item.strip()]


def _config_false(value: Any) -> bool:
    if isinstance(value, bool):
        return not value
    return str(value).strip().lower() in {"", "0", "false", "none", "null", "off", "disabled"}


def _deepgram_send_binary(ws: Any, chunk: bytes) -> None:
    if hasattr(ws, "send_binary"):
        ws.send_binary(chunk)
        return
    ws.send(chunk, opcode=websocket.ABNF.OPCODE_BINARY)


def _deepgram_send_json(ws: Any, payload: dict[str, Any]) -> None:
    ws.send(json.dumps(payload))


def _deepgram_parse_message(message: Any) -> dict[str, Any]:
    if isinstance(message, bytes):
        message = message.decode("utf-8", errors="replace")
    try:
        parsed = json.loads(str(message or ""))
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _deepgram_result_transcript(payload: dict[str, Any]) -> tuple[str, float | None]:
    alternatives = ((payload.get("channel") or {}).get("alternatives") or [])
    if not alternatives:
        return "", None
    first = alternatives[0] or {}
    transcript = str(first.get("transcript") or "").strip()
    confidence = first.get("confidence")
    try:
        parsed_confidence = float(confidence) if confidence is not None else None
    except (TypeError, ValueError):
        parsed_confidence = None
    return transcript, parsed_confidence


def _deepgram_append_final(parts: list[str], transcript: str) -> None:
    cleaned = re.sub(r"\s+", " ", transcript or "").strip()
    if not cleaned:
        return
    if parts and parts[-1] == cleaned:
        return
    if cleaned in parts:
        return
    parts.append(cleaned)


def _deepgram_is_timeout(exc: Exception) -> bool:
    if websocket is not None and hasattr(websocket, "WebSocketTimeoutException"):
        try:
            if isinstance(exc, websocket.WebSocketTimeoutException):
                return True
        except TypeError:
            pass
    return "timed out" in str(exc).lower() or "timeout" in exc.__class__.__name__.lower()


def _deepgram_api_key() -> str:
    value = os.getenv(_deepgram_api_key_env(), "").strip()
    return "" if _is_placeholder_secret(value) else value


def _deepgram_api_key_env() -> str:
    return str(config_value("stt_deepgram_api_key_env", "DEEPGRAM_API_KEY")).strip() or "DEEPGRAM_API_KEY"


def _deepgram_default_model() -> str:
    return str(config_value("stt_deepgram_model", "nova-3")).strip() or "nova-3"


def _is_placeholder_secret(value: str) -> bool:
    lowered = str(value or "").strip().lower()
    if not lowered:
        return True
    return lowered in {"none", "null", "placeholder", "your_key_here", "your_groq_key_here", "your_deepgram_key_here"} or "placeholder" in lowered or lowered.startswith("your_")


def _transcribe_with_whisper_cpp(audio_bytes: bytes, model: Any) -> str:
    if not isinstance(model, dict):
        raise RuntimeError("whisper.cpp backend requires a loaded CLI model descriptor.")

    wav_path = _write_temp_wav(audio_bytes)
    timeout_seconds = float(config_value("stt_whisper_cpp_timeout_seconds", 30.0))
    try:
        with tempfile.TemporaryDirectory(prefix="jarvis-whisper-cpp-") as temp_dir:
            output_base = Path(temp_dir) / "transcript"
            command = _whisper_cpp_command(model, wav_path, output_base)
            completed = subprocess.run(
                command,
                check=False,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
            )
            if completed.returncode != 0:
                detail = _last_nonempty_line(completed.stderr) or _last_nonempty_line(completed.stdout) or f"exit={completed.returncode}"
                _log("WARNING", f"[STT] whisper.cpp failed ({detail}).")
                return ""
            output_path = output_base.with_suffix(".txt")
            if output_path.exists():
                return _parse_whisper_cpp_text(output_path.read_text(encoding="utf-8", errors="replace"))
            return _parse_whisper_cpp_text(completed.stdout)
    except subprocess.TimeoutExpired:
        _log("WARNING", f"[STT] whisper.cpp timed out after {timeout_seconds:.1f}s.")
        return ""
    finally:
        try:
            wav_path.unlink()
        except OSError:
            pass


def _whisper_cpp_command(model: dict[str, Any], wav_path: Path, output_base: Path) -> list[str]:
    command = [
        str(model["cli_path"]),
        "-m",
        str(model["model_path"]),
        "-f",
        str(wav_path),
        "-l",
        str(config_value("stt_language", "en")),
        "-t",
        str(model.get("threads") or _whisper_cpp_threads()),
        "-bs",
        str(int(config_value("stt_beam_size", 1))),
        "-bo",
        str(int(config_value("stt_best_of", 1))),
        "-tp",
        str(float(config_value("stt_temperature", 0.0))),
        "-nth",
        str(float(config_value("stt_no_speech_threshold", 0.6))),
        "-otxt",
        "-of",
        str(output_base),
    ]
    if bool(config_value("stt_without_timestamps", True)):
        command.append("-nt")
    if bool(config_value("stt_whisper_cpp_no_prints", True)):
        command.append("-np")
    if bool(config_value("stt_whisper_cpp_no_gpu", True)):
        command.append("-ng")
    if bool(config_value("stt_whisper_cpp_suppress_non_speech", True)):
        command.append("-sns")
    initial_prompt = str(config_value("stt_initial_prompt", "")).strip()
    if initial_prompt:
        command.extend(["--prompt", initial_prompt])
    command.extend(_whisper_cpp_extra_args())
    return command


def _whisper_cpp_cli_path() -> Path:
    default_path = r"tools\whisper.cpp\Release\whisper-cli.exe"
    return _repo_path(str(config_value("stt_whisper_cpp_cli_path", default_path)))


def _whisper_cpp_model_path(model_name: str | None = None) -> Path:
    raw_model = str(model_name or "").strip()
    configured = str(config_value("stt_whisper_cpp_model_path", "")).strip()
    if raw_model:
        if configured and Path(configured).name.lower() == raw_model.lower():
            return _repo_path(configured)
        raw_path = Path(raw_model).expanduser()
        if raw_path.is_absolute() or "\\" in raw_model or "/" in raw_model:
            return _repo_path(raw_model)
        if raw_model.lower().endswith(".bin"):
            return _repo_path(str(Path(r"tools\whisper.cpp\models") / raw_model))

    if configured:
        return _repo_path(configured)
    return _repo_path(str(Path(r"tools\whisper.cpp\models") / _whisper_cpp_default_model_name()))


def _whisper_cpp_default_model_name() -> str:
    return "ggml-base.en-q5_1.bin"


def _whisper_cpp_threads() -> int:
    raw_threads = config_value("stt_whisper_cpp_threads", None)
    if raw_threads in {None, ""}:
        raw_threads = config_value("stt_cpu_threads", 4)
    try:
        return max(1, int(raw_threads))
    except (TypeError, ValueError):
        return 4


def _whisper_cpp_extra_args() -> list[str]:
    raw = config_value("stt_whisper_cpp_extra_args", "")
    if isinstance(raw, (list, tuple)):
        return [str(item).strip() for item in raw if str(item).strip()]
    return [item.strip() for item in str(raw or "").split(",") if item.strip()]


def _repo_path(raw_path: str) -> Path:
    path = Path(raw_path).expanduser()
    if path.is_absolute():
        return path
    return Path(__file__).resolve().parents[1] / path


def _parse_whisper_cpp_text(raw_text: str) -> str:
    lines: list[str] = []
    for raw_line in str(raw_text or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if _looks_like_whisper_cpp_log_line(line):
            continue
        line = re.sub(r"^\[[^\]]+\]\s*", "", line).strip()
        if line:
            lines.append(line)
    return re.sub(r"\s+", " ", " ".join(lines)).strip()


def _looks_like_whisper_cpp_log_line(line: str) -> bool:
    lowered = line.lower()
    return lowered.startswith(("whisper_", "ggml_", "system_info:", "main:", "error:"))


def _last_nonempty_line(text: str) -> str:
    for line in reversed(str(text or "").splitlines()):
        stripped = line.strip()
        if stripped:
            return stripped
    return ""


def _transcribe_with_windows_speech(audio_bytes: bytes) -> str:
    global _last_transcribe_confidence, _last_transcribe_grammar, _last_transcribe_rejected_low_confidence, _last_transcribe_raw_text
    wav_path = _write_temp_wav(audio_bytes)
    try:
        result = _run_windows_speech(wav_path)
    finally:
        try:
            wav_path.unlink()
        except OSError:
            pass
    _last_transcribe_confidence = result.get("confidence")
    _last_transcribe_grammar = str(result.get("grammar") or "")
    text = str(result.get("text") or "").strip()
    _last_transcribe_raw_text = text
    if _last_transcribe_confidence is not None:
        _log("DEBUG", f"[STT] windows_speech confidence={_last_transcribe_confidence:.2f} grammar={_last_transcribe_grammar} raw='{text}'")
    repaired_text = _repair_windows_transcript(text)
    if repaired_text != text:
        _log("INFO", f"[STT] windows_speech repaired text='{text}' -> '{repaired_text}'")
        return repaired_text
    if text and _windows_speech_below_confidence_floor(text, _last_transcribe_confidence, _last_transcribe_grammar):
        _last_transcribe_rejected_low_confidence = True
        _log("INFO", f"[STT] windows_speech discarded low-confidence text='{text}' confidence={_last_transcribe_confidence:.2f}")
        return ""
    return text


def _write_temp_wav(audio_bytes: bytes) -> Path:
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as fh:
        path = Path(fh.name)
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(SAMPLE_RATE)
        wav.writeframes(audio_bytes)
    return path


def _run_windows_speech(wav_path: Path) -> dict[str, Any]:
    timeout_seconds = float(config_value("stt_windows_timeout_seconds", 6.0))
    culture = str(config_value("stt_windows_culture", "en-US"))
    phrase_path = _write_windows_command_phrases()
    script = r"""
param([string]$WavePath, [string]$CultureName, [double]$TimeoutSeconds, [string]$PhrasePath)
$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Speech
$engine = $null
try {
    if ($CultureName) {
        try {
            $culture = [System.Globalization.CultureInfo]::GetCultureInfo($CultureName)
            $engine = New-Object System.Speech.Recognition.SpeechRecognitionEngine($culture)
        } catch {
            $engine = $null
        }
    }
    if ($null -eq $engine) {
        $engine = New-Object System.Speech.Recognition.SpeechRecognitionEngine
    }
    if ($PhrasePath -and (Test-Path -LiteralPath $PhrasePath)) {
        $phrases = @(Get-Content -LiteralPath $PhrasePath | Where-Object { $_ -and $_.Trim().Length -gt 0 })
        if ($phrases.Count -gt 0) {
            $choices = New-Object System.Speech.Recognition.Choices
            foreach ($phrase in $phrases) {
                [void]$choices.Add($phrase)
            }
            $builder = New-Object System.Speech.Recognition.GrammarBuilder
            $builder.Culture = $engine.RecognizerInfo.Culture
            $builder.Append($choices)
            $commandGrammar = New-Object System.Speech.Recognition.Grammar($builder)
            $commandGrammar.Name = "friday-command"
            $commandGrammar.Weight = 1.0
            $engine.LoadGrammar($commandGrammar)
        }
    }
    $grammar = New-Object System.Speech.Recognition.DictationGrammar
    $grammar.Name = "dictation"
    $grammar.Weight = 0.25
    $engine.LoadGrammar($grammar)
    $engine.SetInputToWaveFile($WavePath)
    $result = $engine.Recognize([TimeSpan]::FromSeconds($TimeoutSeconds))
    if ($null -eq $result) {
        @{ text = ""; confidence = 0.0; grammar = ""; culture = $engine.RecognizerInfo.Culture.Name; alternates = @() } | ConvertTo-Json -Compress -Depth 4
    } else {
        $alternates = @($result.Alternates | Select-Object -First 3 | ForEach-Object { @{ text = $_.Text; confidence = $_.Confidence } })
        @{ text = $result.Text; confidence = $result.Confidence; grammar = $result.Grammar.Name; culture = $engine.RecognizerInfo.Culture.Name; alternates = $alternates } | ConvertTo-Json -Compress -Depth 4
    }
} finally {
    if ($null -ne $engine) {
        $engine.Dispose()
    }
}
"""
    with tempfile.NamedTemporaryFile(suffix=".ps1", delete=False, mode="w", encoding="utf-8") as fh:
        script_path = Path(fh.name)
        fh.write(script)
    try:
        completed = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(script_path),
                str(wav_path),
                culture,
                str(timeout_seconds),
                str(phrase_path),
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_seconds + 5.0,
        )
    except Exception as exc:
        _log("WARNING", f"[STT] windows speech failed ({exc}).")
        return {"text": "", "confidence": 0.0}
    finally:
        try:
            script_path.unlink()
        except OSError:
            pass
        try:
            phrase_path.unlink()
        except OSError:
            pass
    if completed.returncode != 0:
        stderr = (completed.stderr or "").strip().splitlines()
        detail = stderr[-1] if stderr else f"exit={completed.returncode}"
        _log("WARNING", f"[STT] windows speech failed ({detail}).")
        return {"text": "", "confidence": 0.0}
    output = (completed.stdout or "").strip()
    if not output:
        return {"text": "", "confidence": 0.0}
    try:
        parsed = json.loads(output.splitlines()[-1])
    except json.JSONDecodeError as exc:
        _log("WARNING", f"[STT] windows speech returned invalid JSON ({exc}).")
        return {"text": "", "confidence": 0.0}
    confidence = parsed.get("confidence", 0.0)
    try:
        parsed["confidence"] = float(confidence)
    except (TypeError, ValueError):
        parsed["confidence"] = 0.0
    return parsed


def _write_windows_command_phrases() -> Path:
    phrases = _windows_command_phrases()
    with tempfile.NamedTemporaryFile(suffix=".txt", delete=False, mode="w", encoding="utf-8") as fh:
        path = Path(fh.name)
        for phrase in phrases:
            fh.write(phrase + "\n")
    return path


def _windows_command_phrases() -> list[str]:
    names = _csv_config("attention_names", "friday,hey friday,computer,jarvis")
    base_commands = _csv_config(
        "stt_windows_command_phrases",
        (
            "how are you,how are you doing,what time is it,what is the time,what date is it,what is the date,"
            "what day is it,what is your name,who are you,can you code,what can you do,"
            "can you see the file,can you see the file opened on my VS,can you see the file on my workspace,"
            "what does the file say,read the file,list files,show files,open Chrome,open Gmail,open VS Code,"
            "open Notepad,open Explorer,shutdown,stop listening"
        ),
    )
    phrases: list[str] = []
    for command in base_commands:
        phrases.append(command)
        for name in names:
            phrases.append(f"{name} {command}")
            phrases.append(f"hey {name} {command}")
    phrases.extend(names)
    return _unique_phrases(phrases)


def _csv_config(key: str, default: str) -> list[str]:
    return [item.strip() for item in str(config_value(key, default)).split(",") if item.strip()]


def _unique_phrases(phrases: list[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for phrase in phrases:
        cleaned = re.sub(r"\s+", " ", phrase).strip(" ,.!?:;")
        key = cleaned.lower()
        if not cleaned or key in seen:
            continue
        seen.add(key)
        unique.append(cleaned)
    return unique


def _windows_speech_below_confidence_floor(text: str, confidence: float | None, grammar: str) -> bool:
    if confidence is None:
        return False
    command_floor = float(config_value("stt_windows_command_min_confidence", 0.12))
    dictation_floor = float(config_value("stt_windows_min_confidence", 0.35))
    floor = command_floor if grammar == "friday-command" else dictation_floor
    if confidence >= floor:
        return False
    normalized = re.sub(r"[^\w\s]", "", text or "").strip().lower()
    return normalized not in {"friday", "hey friday"}


def _repair_windows_transcript(text: str) -> str:
    normalized = _normalize_repair_key(text)
    if not normalized:
        return text
    repairs = _windows_transcript_repairs()
    repaired = repairs.get(normalized)
    if repaired:
        return repaired
    return _fuzzy_windows_repair(normalized) or text


def _windows_transcript_repairs() -> dict[str, str]:
    raw = str(
        config_value(
            "stt_windows_transcript_repairs",
            (
                "friday how leading=Friday how are you doing;"
                "friday relating=Friday how are you doing;"
                "friday holly gore=Friday how are you doing;"
                "krygier leading=Friday how are you doing;"
                "craig holley in=Friday how are you doing;"
                "he cried while a game=Friday how are you doing"
            ),
        )
    )
    repairs: dict[str, str] = {}
    for item in raw.split(";"):
        wrong, sep, right = item.partition("=")
        if sep and wrong.strip() and right.strip():
            repairs[_normalize_repair_key(wrong)] = right.strip()
    return repairs


def _fuzzy_windows_repair(normalized: str) -> str:
    if not bool(config_value("stt_windows_fuzzy_repair_enabled", True)):
        return ""
    target = "friday how are you doing"
    if _looks_like_how_are_you_miss(normalized):
        return "Friday how are you doing"
    return ""


def _looks_like_how_are_you_miss(normalized: str) -> bool:
    tokens = normalized.split()
    if not tokens:
        return False
    first = tokens[0]
    friday_like = first in {"friday", "freddy", "freddie", "fridays", "krygier", "craig"} or first.startswith("fri")
    if not friday_like:
        friday_like = normalized.startswith("he cried") or normalized.startswith("hey cried")
    how_like = any(token in {"how", "holly", "holy", "while"} for token in tokens)
    doing_like = any(token in {"doing", "leading", "relating", "gore", "game", "in"} for token in tokens[1:])
    return friday_like and (how_like or doing_like) and len(normalized) <= 32


def _normalize_repair_key(text: str) -> str:
    cleaned = re.sub(r"[^\w\s]", " ", text or "").lower()
    return re.sub(r"\s+", " ", cleaned).strip()


def record_audio(initial_audio: bytes = b"") -> bytes:
    if sd is None:
        raise RuntimeError("Audio capture dependency sounddevice is not installed.")
    with sd.InputStream(
        device=_audio_device(),
        samplerate=SAMPLE_RATE,
        channels=1,
        dtype="int16",
        blocksize=FRAME_SAMPLES,
    ) as stream:
        return record_until_silence_energy(stream, initial_audio=initial_audio)


def record_and_transcribe(model: Any = None, initial_audio: bytes = b"", strip_wake: bool = True) -> str:
    text, _audio = record_and_transcribe_with_audio(model=model, initial_audio=initial_audio, strip_wake=strip_wake)
    return text


def record_and_transcribe_with_audio(model: Any = None, initial_audio: bytes = b"", strip_wake: bool = True) -> tuple[str, bytes]:
    model = model or whisper_model
    if model is None:
        model = load_model()
    if _backend_for_model(model) == "deepgram" and bool(config_value("stt_deepgram_realtime_enabled", True)):
        return _record_and_transcribe_deepgram_streaming(model, initial_audio=initial_audio, strip_wake=strip_wake)

    start = time.perf_counter()
    record_start = time.perf_counter()
    audio = record_audio(initial_audio=initial_audio)
    record_ms = (time.perf_counter() - record_start) * 1000
    if not audio:
        return "", b""
    transcribe_start = time.perf_counter()
    text = transcribe_best_effort(audio, model=model, strip_wake=strip_wake)
    transcribe_ms = (time.perf_counter() - transcribe_start) * 1000
    audio_seconds = len(audio) / (SAMPLE_RATE * 2)
    _log(
        "INFO",
        f"[PERF] stt_total={(time.perf_counter() - start) * 1000:.0f}ms "
        f"record={record_ms:.0f}ms transcribe={transcribe_ms:.0f}ms audio={audio_seconds:.1f}s",
    )
    return text, audio


def strip_wake_phrase(text: str) -> str:
    phrases = str(config_value("wake_word_strip_phrases", "hey friday,friday,fry day,hey freddie,freddie,hey freddy,freddy,hey jarvis,jarvis,hey jeff,jeff")).split(",")
    cleaned = _normalize_wake_transcript(text)
    for phrase in phrases:
        phrase = _normalize_wake_transcript(phrase)
        if not phrase:
            continue
        cleaned = re.sub(rf"^\s*{re.escape(phrase)}\b[\s,.:;-]*", "", cleaned, flags=re.IGNORECASE)
    return cleaned.strip()


def clean_transcript(text: str) -> str:
    cleaned = re.sub(r"\s+", " ", text or "").strip()
    if not cleaned:
        return ""
    if _looks_like_hallucination(cleaned):
        return ""
    if _is_ignored_transcript(cleaned):
        return ""
    cleaned = _apply_short_command_repairs(cleaned)
    cleaned = _apply_phrase_corrections(cleaned)
    cleaned = _normalize_common_command_words(cleaned)
    cleaned = _strip_trailing_junk(cleaned)
    return cleaned.strip()


def _looks_like_hallucination(text: str) -> bool:
    normalized = re.sub(r"[^\w\s]", " ", text or "").lower()
    normalized = re.sub(r"\s+", " ", normalized).strip()
    if not normalized:
        return False
    phrases = _hallucination_phrases()
    if any(phrase and phrase in normalized for phrase in phrases):
        return True
    words = normalized.split()
    if len(words) < 18:
        return False
    chunks = [" ".join(words[i : i + 4]) for i in range(0, max(0, len(words) - 3), 4)]
    repeated_chunks = len(chunks) - len(set(chunks))
    return repeated_chunks >= 3


def _hallucination_phrases() -> list[str]:
    built_in = (
        "audio is a short command for an ai assistant",
        "the audio is a short command for an ai assistant",
        "short command for an ai assistant named",
        "common words include",
        "thank you for watching",
        "thanks for watching",
        "do not forget to subscribe",
        "dont forget to subscribe",
        "i'm going to show you how to",
        "i am going to show you how to",
        "the ai assistant is a",
        "the ai assistant will then",
    )
    configured = tuple(
        item.strip().lower()
        for item in str(config_value("stt_hallucination_phrases", "")).split(",")
        if item.strip()
    )
    return list(built_in + configured)


def _apply_phrase_corrections(text: str) -> str:
    raw = str(config_value("stt_phrase_corrections", ""))
    cleaned = text
    for item in raw.split(";"):
        wrong, sep, right = item.partition("=")
        if not sep:
            continue
        wrong = wrong.strip()
        right = right.strip()
        if wrong and right:
            cleaned = re.sub(rf"\b{re.escape(wrong)}\b", right, cleaned, flags=re.IGNORECASE)
    return cleaned


def _apply_short_command_repairs(text: str) -> str:
    normalized = _normalize_short_command_key(text)
    repairs = _short_command_repairs()
    direct = repairs.get(normalized)
    if direct:
        return direct

    for phrase in _wake_repair_phrases():
        if normalized == phrase:
            return text
        prefix = f"{phrase} "
        if normalized.startswith(prefix):
            rest = normalized[len(prefix) :].strip()
            repaired = repairs.get(rest)
            if repaired:
                return f"{phrase} {repaired}"
    return text


def _short_command_repairs() -> dict[str, str]:
    raw = str(
        config_value(
            "stt_short_command_repairs",
            (
                "coyote=can you code;cayote=can you code;and you could=can you code;"
                "you could=can you code;can you could=can you code;can you coat=can you code;"
                "can you quote=can you code"
            ),
        )
    )
    repairs: dict[str, str] = {}
    for item in raw.split(";"):
        wrong, sep, right = item.partition("=")
        if sep and wrong.strip() and right.strip():
            repairs[_normalize_short_command_key(wrong)] = right.strip()
    return repairs


def _wake_repair_phrases() -> list[str]:
    raw_phrases = str(
        config_value(
            "wake_word_strip_phrases",
            "hey friday,friday,fry day,hey freddie,freddie,hey freddy,freddy,hey jarvis,jarvis",
        )
    ).split(",")
    names = str(config_value("attention_names", "friday,freddie,freddy,computer,jarvis")).split(",")
    phrases = [*raw_phrases, *names]
    normalized: list[str] = []
    seen: set[str] = set()
    for phrase in phrases:
        key = _normalize_short_command_key(phrase)
        if key and key not in seen:
            seen.add(key)
            normalized.append(key)
    return normalized


def _normalize_short_command_key(text: str) -> str:
    cleaned = re.sub(r"[^\w\s']", " ", text or "").lower()
    return re.sub(r"\s+", " ", cleaned).strip()


def _normalize_common_command_words(text: str) -> str:
    cleaned = text
    cleaned = re.sub(r"\b(?:v s|vs)\s+code\b", "VS Code", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bchrome\b", "Chrome", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bfriday\b", "Friday", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bjarvis\b", "Jarvis", cleaned, flags=re.IGNORECASE)
    return cleaned


def _strip_trailing_junk(text: str) -> str:
    junk = {item.strip().lower() for item in str(config_value("stt_trailing_junk_words", "")).split(",") if item.strip()}
    if not junk:
        return text
    words = text.split()
    if len(words) < 4:
        return text
    last = re.sub(r"[^\w']", "", words[-1]).lower()
    if last in junk:
        return " ".join(words[:-1]).rstrip(" ,.!?:;")
    return text


def _is_ignored_transcript(text: str) -> bool:
    normalized = re.sub(r"[^\w\s']", " ", text or "").lower()
    normalized = re.sub(r"\s+", " ", normalized).strip()
    if not normalized:
        return True
    ignored = {
        re.sub(r"\s+", " ", item.strip().lower())
        for item in str(config_value("stt_ignore_captures", "ok,okay,hey,in,you,thank you,thanks,credits,video")).split(",")
        if item.strip()
    }
    return normalized in ignored


def _normalize_wake_transcript(text: str) -> str:
    text = re.sub(r"[^\w\s]", " ", text or "", flags=re.UNICODE)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _frames_for_ms(ms: int) -> int:
    return max(1, int(round(ms / FRAME_MS)))


def _frames_for_seconds(seconds: float) -> int:
    return max(1, int(round((seconds * 1000) / FRAME_MS)))


def _audio_device() -> int | str | None:
    device = config_value("audio_input_device", None)
    if device in {"", "default", "none", None}:
        return None
    return device


def _load_whisper_model_with_repair(model_name: str) -> Any:
    try:
        return whisper.load_model(model_name)
    except Exception as exc:
        if not _is_checksum_failure(exc) or not bool(config_value("stt_retry_corrupt_download", True)):
            raise
        removed = _remove_model_cache(model_name)
        if removed is not None:
            _log("WARNING", f"[STT] Removed corrupt Whisper cache file: {removed}")
        _log("WARNING", f"[STT] Retrying Whisper model download/load for '{model_name}' after checksum failure.")
        return whisper.load_model(model_name)


def _is_checksum_failure(exc: Exception) -> bool:
    return "checksum" in str(exc).lower()


def _remove_model_cache(model_name: str) -> Path | None:
    cache_file = Path.home() / ".cache" / "whisper" / f"{model_name}.pt"
    if not cache_file.exists():
        return None
    cache_file.unlink()
    return cache_file


def _log(level: str, message: str) -> None:
    try:
        from output.display import log

        log(level, message)
    except Exception:
        return
