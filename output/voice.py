"""Voice synthesis with ElevenLabs online mode and pyttsx3 fallback."""

from __future__ import annotations

import os
import socket
import subprocess
import tempfile
import threading
from pathlib import Path
import asyncio
import hashlib

try:
    import pyttsx3
except Exception:  # pragma: no cover - optional in scaffold tests
    pyttsx3 = None

try:
    import requests
except Exception:  # pragma: no cover - optional in scaffold tests
    requests = None

try:
    import edge_tts
except Exception:  # pragma: no cover - optional in scaffold tests
    edge_tts = None

from core.config import DATA_DIR, config_value, reload_config
from core import barge_in

_lock = threading.Lock()
_engine = None
_cache: dict[str, bytes] = {}
CACHE_MAX = 10
VOICE_CACHE_DIR = DATA_DIR / "voice_cache"
DEFAULT_EDGE_VOICE = "en-US-EmmaMultilingualNeural"
DEFAULT_PREVIEW_TEXT = "Hello, I am Friday. Ready when you are."
DEFAULT_WARMUP_TEXTS: tuple[str, ...] = (
    "I'm doing well. Ready when you are.",
    "It is ready.",
    "Chrome opened successfully.",
    "Gmail opened successfully.",
    "Calculator opened successfully.",
    "Done.",
    "Okay.",
)
RECOMMENDED_EDGE_VOICES: tuple[dict[str, str], ...] = (
    {
        "label": "Emma",
        "voice": "en-US-EmmaMultilingualNeural",
        "rate": "+0%",
        "pitch": "+0Hz",
        "description": "warm, natural assistant voice",
    },
    {
        "label": "Jenny",
        "voice": "en-US-JennyNeural",
        "rate": "+0%",
        "pitch": "+0Hz",
        "description": "clear assistant-style voice",
    },
    {
        "label": "Aria",
        "voice": "en-US-AriaNeural",
        "rate": "+0%",
        "pitch": "+0Hz",
        "description": "expressive conversational voice",
    },
    {
        "label": "Brian",
        "voice": "en-US-BrianMultilingualNeural",
        "rate": "+0%",
        "pitch": "+0Hz",
        "description": "calm male voice",
    },
    {
        "label": "Andrew",
        "voice": "en-US-AndrewMultilingualNeural",
        "rate": "+0%",
        "pitch": "+0Hz",
        "description": "natural male voice",
    },
)


def _get_engine():
    global _engine
    if pyttsx3 is None:
        return None
    if _engine is None:
        _engine = pyttsx3.init()
    return _engine


def local_voice_options() -> list[dict[str, str]]:
    """Return voices exposed by the local OS speech engine."""
    engine = _get_engine()
    if engine is None:
        return []
    voices = engine.getProperty("voices") or []
    return [_local_voice_to_dict(index, option) for index, option in enumerate(voices)]


def _local_voice_to_dict(index: int, option) -> dict[str, str]:
    return {
        "index": str(index),
        "id": str(getattr(option, "id", "")),
        "name": str(getattr(option, "name", "")),
        "languages": _format_voice_languages(getattr(option, "languages", "")),
        "gender": str(getattr(option, "gender", "")),
        "age": str(getattr(option, "age", "")),
    }


def _format_voice_languages(raw) -> str:
    if not raw:
        return ""
    if isinstance(raw, (str, bytes)):
        values = [raw]
    else:
        values = list(raw)
    formatted: list[str] = []
    for value in values:
        if isinstance(value, bytes):
            text = value.decode("utf-8", errors="ignore")
        else:
            text = str(value)
        text = text.replace("\x05", "").strip()
        if text:
            formatted.append(text)
    return ",".join(formatted)


def _is_online() -> bool:
    try:
        with socket.create_connection(("8.8.8.8", 53), timeout=1):
            return True
    except OSError:
        return False


def speak(text: str) -> None:
    if not text:
        return
    with _lock:
        barge_in.clear()
        cfg = reload_config()
        monitor = barge_in.start_audio_monitor(text) if bool(cfg.get("barge_in_audio_monitor_enabled", False)) else None
        backend = str(os.getenv("JARVIS_VOICE_BACKEND") or cfg.get("voice_backend", "edge")).lower()
        try:
            if backend == "pyttsx3":
                _speak_pyttsx3(text)
                return
            if backend == "elevenlabs" and _is_online():
                try:
                    _speak_elevenlabs(text)
                    return
                except Exception:
                    pass
            if _is_online():
                try:
                    _speak_edge(text, cfg)
                    return
                except Exception:
                    pass
            _speak_pyttsx3(text)
        finally:
            if monitor is not None:
                monitor.stop()


def _speak_edge(text: str, cfg: dict | None = None) -> None:
    if edge_tts is None:
        raise RuntimeError("edge-tts is not installed.")
    audio = _edge_audio(text, cfg or reload_config())
    if barge_in.is_requested():
        return
    _play_mp3(audio)


def _edge_audio(text: str, cfg: dict) -> bytes:
    cfg = _edge_runtime_config(cfg or reload_config())
    voice = str(cfg.get("edge_voice", DEFAULT_EDGE_VOICE))
    rate = str(cfg.get("edge_rate", "+0%"))
    volume = str(cfg.get("edge_volume", "+0%"))
    pitch = str(cfg.get("edge_pitch", "+0Hz"))
    cache_key = f"edge|{voice}|{rate}|{volume}|{pitch}|{text}"
    if cache_key in _cache:
        audio = _cache[cache_key]
    else:
        audio = _read_persistent_edge_cache(cache_key, cfg)
    if audio is None:
        audio = asyncio.run(_edge_bytes(text, voice=voice, rate=rate, volume=volume, pitch=pitch))
        _write_persistent_edge_cache(cache_key, audio, cfg)
    if cache_key not in _cache:
        if len(_cache) >= CACHE_MAX:
            _cache.pop(next(iter(_cache)))
        _cache[cache_key] = audio
    return audio


def _edge_runtime_config(cfg: dict) -> dict:
    runtime = dict(cfg)
    if os.getenv("JARVIS_FAST_VOICE") == "1":
        runtime["edge_rate"] = str(runtime.get("fast_voice_edge_rate", runtime.get("edge_rate", "+0%")))
        runtime["edge_pitch"] = str(runtime.get("fast_voice_edge_pitch", runtime.get("edge_pitch", "+0Hz")))
        fast_voice = runtime.get("fast_voice_edge_voice")
        if fast_voice:
            runtime["edge_voice"] = str(fast_voice)
    return runtime


def _read_persistent_edge_cache(cache_key: str, cfg: dict) -> bytes | None:
    if not bool(cfg.get("edge_persistent_cache_enabled", True)):
        return None
    path = _persistent_edge_cache_path(cache_key)
    try:
        if path.exists():
            return path.read_bytes()
    except OSError:
        return None
    return None


def _write_persistent_edge_cache(cache_key: str, audio: bytes, cfg: dict) -> None:
    if not audio or not bool(cfg.get("edge_persistent_cache_enabled", True)):
        return
    try:
        VOICE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        _persistent_edge_cache_path(cache_key).write_bytes(audio)
        _prune_persistent_edge_cache(int(cfg.get("edge_persistent_cache_max_files", 80)))
    except OSError:
        return


def _persistent_edge_cache_path(cache_key: str) -> Path:
    digest = hashlib.sha256(cache_key.encode("utf-8")).hexdigest()
    return VOICE_CACHE_DIR / f"{digest}.mp3"


def _prune_persistent_edge_cache(max_files: int) -> None:
    if max_files <= 0 or not VOICE_CACHE_DIR.exists():
        return
    files = sorted(
        (path for path in VOICE_CACHE_DIR.glob("*.mp3") if path.is_file()),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    for path in files[max_files:]:
        try:
            path.unlink()
        except OSError:
            pass


def preview_edge_voices(text: str = DEFAULT_PREVIEW_TEXT) -> list[str]:
    """Play a short sample through the free Edge neural voices."""
    if edge_tts is None:
        raise RuntimeError("edge-tts is not installed.")
    if not _is_online():
        raise RuntimeError("Edge neural voice preview needs internet access.")
    cfg = dict(reload_config())
    played: list[str] = []
    for option in RECOMMENDED_EDGE_VOICES:
        voice_cfg = dict(cfg)
        voice_cfg["edge_voice"] = option["voice"]
        voice_cfg["edge_rate"] = option["rate"]
        voice_cfg["edge_pitch"] = option["pitch"]
        voice_cfg.setdefault("edge_volume", "+0%")
        _speak_edge(f"{option['label']}. {text}", voice_cfg)
        played.append(option["voice"])
    return played


def warm_edge_voice_cache(texts: tuple[str, ...] | list[str] | None = None) -> list[str]:
    """Pre-generate common free Edge voice replies without playing audio."""
    if edge_tts is None:
        raise RuntimeError("edge-tts is not installed.")
    if not _is_online():
        raise RuntimeError("Edge neural voice warmup needs internet access.")
    cfg = dict(reload_config())
    warmed: list[str] = []
    for text in texts or DEFAULT_WARMUP_TEXTS:
        if not text.strip():
            continue
        _edge_audio(text, cfg)
        warmed.append(text)
    return warmed


async def _edge_bytes(text: str, voice: str, rate: str, volume: str, pitch: str) -> bytes:
    communicate = edge_tts.Communicate(text=text, voice=voice, rate=rate, volume=volume, pitch=pitch)
    chunks: list[bytes] = []
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            chunks.append(chunk["data"])
    return b"".join(chunks)


def _speak_elevenlabs(text: str) -> None:
    if requests is None:
        raise RuntimeError("requests is not installed.")
    api_key = os.getenv("ELEVENLABS_API_KEY")
    voice_id = os.getenv("ELEVENLABS_VOICE_ID") or str(config_value("elevenlabs_voice_id", "21m00Tcm4TlvDq8ikWAM"))
    if not api_key:
        raise RuntimeError("ElevenLabs API key is missing.")
    if text in _cache:
        mp3 = _cache[text]
    else:
        response = requests.post(
            f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
            headers={"xi-api-key": api_key},
            json={"text": text, "model_id": "eleven_monolingual_v1"},
            timeout=8,
        )
        response.raise_for_status()
        mp3 = response.content
        if len(_cache) >= CACHE_MAX:
            _cache.pop(next(iter(_cache)))
        _cache[text] = mp3
    if barge_in.is_requested():
        return
    _play_mp3(mp3)


def _play_mp3(mp3: bytes) -> None:
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as fh:
        fh.write(mp3)
        fname = fh.name
    try:
        _play_mp3_windows(fname)
    finally:
        try:
            Path(fname).unlink()
        except OSError:
            pass


def _play_mp3_windows(path: str) -> None:
    uri = Path(path).resolve().as_uri()
    stop_path = str(barge_in.STOP_FLAG_PATH.resolve()).replace("'", "''")
    script = (
        "Add-Type -AssemblyName PresentationCore; "
        "$p=New-Object System.Windows.Media.MediaPlayer; "
        f"$p.Open([Uri]'{uri}'); "
        "$p.Volume=1.0; $p.Play(); "
        f"while((-not $p.NaturalDuration.HasTimeSpan) -and (-not (Test-Path -LiteralPath '{stop_path}'))){{ Start-Sleep -Milliseconds 50 }}; "
        "$ms=[int]$p.NaturalDuration.TimeSpan.TotalMilliseconds + 150; "
        "$elapsed=0; "
        f"while(($elapsed -lt $ms) -and (-not (Test-Path -LiteralPath '{stop_path}'))){{ Start-Sleep -Milliseconds 60; $elapsed += 60 }}; "
        "$p.Stop(); $p.Close();"
    )
    subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _speak_pyttsx3(text: str) -> None:
    engine = _get_engine()
    if engine is None:
        return
    barge_in.register_stop_callback(lambda _reason: engine.stop())
    cfg = reload_config()
    voice_id = _resolve_pyttsx3_voice_id(engine, cfg)
    if voice_id:
        engine.setProperty("voice", voice_id)
    engine.setProperty("rate", int(cfg.get("voice_rate", 175)))
    engine.setProperty("volume", float(cfg.get("voice_volume", 1.0)))
    if barge_in.is_requested():
        return
    engine.say(text)
    engine.runAndWait()


def _resolve_pyttsx3_voice_id(engine, cfg: dict) -> str:
    requested = str(cfg.get("pyttsx3_voice_id", "")).strip()
    if not requested:
        return ""
    voices = engine.getProperty("voices") or []
    for option in voices:
        option_id = str(getattr(option, "id", ""))
        if option_id == requested:
            return option_id
    lowered = requested.lower()
    for option in voices:
        option_id = str(getattr(option, "id", ""))
        option_name = str(getattr(option, "name", ""))
        if lowered in option_id.lower() or lowered in option_name.lower():
            return option_id
    return ""
