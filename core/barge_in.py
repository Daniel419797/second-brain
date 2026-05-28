"""Interrupt signal for Friday speech and corrections."""

from __future__ import annotations

import datetime as dt
import json
import sqlite3
import threading
import time
from collections import deque
from pathlib import Path
from typing import Any, Callable

from core.config import DATA_DIR, config_value, ensure_runtime_dirs

DB_PATH = DATA_DIR / "barge_in.sqlite3"
STOP_FLAG_PATH = DATA_DIR / "barge_in_stop.flag"
_LOCK = threading.Lock()
_INTERRUPT = threading.Event()
_CALLBACKS: list[Callable[[str], None]] = []


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
            CREATE TABLE IF NOT EXISTS barge_in_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                phrase TEXT NOT NULL,
                reason TEXT NOT NULL,
                metadata_json TEXT NOT NULL
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_barge_in_time ON barge_in_events(timestamp)")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS pending_commands (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                command TEXT NOT NULL,
                heard_text TEXT NOT NULL,
                metadata_json TEXT NOT NULL,
                consumed INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_barge_pending_consumed ON pending_commands(consumed, id)")


def register_stop_callback(callback: Callable[[str], None]) -> None:
    if callback not in _CALLBACKS:
        _CALLBACKS.append(callback)


def request_stop(reason: str = "user interrupt", *, phrase: str = "", metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    """Signal all speech backends that current speech should stop."""

    init_db()
    _INTERRUPT.set()
    try:
        STOP_FLAG_PATH.parent.mkdir(parents=True, exist_ok=True)
        STOP_FLAG_PATH.write_text(_now(), encoding="utf-8")
    except OSError:
        pass
    for callback in list(_CALLBACKS):
        try:
            callback(reason)
        except Exception:
            continue
    event_id = _record_event(phrase or reason, reason, metadata or {})
    return {"ok": True, "id": event_id, "summary": "Speech interruption requested.", "reason": reason}


def clear() -> None:
    _INTERRUPT.clear()
    try:
        if STOP_FLAG_PATH.exists():
            STOP_FLAG_PATH.unlink()
    except OSError:
        pass


def is_requested() -> bool:
    return _INTERRUPT.is_set() or STOP_FLAG_PATH.exists()


def should_barge_in(text: str) -> bool:
    lowered = " ".join(str(text or "").strip().lower().split())
    if not lowered:
        return False
    phrases = _phrases()
    return any(lowered == phrase or lowered.startswith(phrase + " ") for phrase in phrases)


def handle_if_interrupt(text: str) -> str:
    if not bool(config_value("barge_in_enabled", True)) or not should_barge_in(text):
        return ""
    request_stop("user barge-in", phrase=text, metadata={"heard_text": text})
    command = extract_followup_command(text)
    if command:
        enqueue_command(command, heard_text=text, metadata={"source": "direct_interrupt"})
    return "Stopping."


def start_audio_monitor(spoken_text: str = "") -> "BargeInAudioMonitor":
    """Listen for human speech while Friday is talking and request a stop quickly.

    The monitor intentionally uses a cheap energy gate first so the response stops
    immediately, then it transcribes the captured utterance in the background and
    queues any replacement instruction for the main voice loop.
    """

    monitor = BargeInAudioMonitor(spoken_text=spoken_text)
    monitor.start()
    return monitor


class BargeInAudioMonitor:
    def __init__(self, spoken_text: str = ""):
        self.spoken_text = str(spoken_text or "")
        self.enabled = bool(config_value("barge_in_audio_monitor_enabled", True)) and bool(config_value("barge_in_enabled", True))
        self.started = False
        self.error = ""
        self._stop_requested = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if not self.enabled:
            return
        try:
            from input import speech_to_text as stt

            if stt.sd is None or stt.np is None:
                self.error = "audio dependencies unavailable"
                return
        except Exception as exc:
            self.error = str(exc)
            return
        self._thread = threading.Thread(target=self._run, name="FridayBargeIn", daemon=True)
        self._thread.start()
        self.started = True

    def stop(self, wait_seconds: float | None = None) -> None:
        self._stop_requested.set()
        if self._thread and self._thread.is_alive():
            timeout = wait_seconds
            if timeout is None:
                timeout = float(config_value("barge_in_monitor_join_seconds", 0.25))
            self._thread.join(timeout=max(0.0, float(timeout)))

    def _run(self) -> None:
        try:
            self._listen()
        except Exception as exc:
            self.error = str(exc)
            _record_event("audio_monitor_error", "barge-in monitor error", {"error": self.error})

    def _listen(self) -> None:
        from input import speech_to_text as stt

        sample_rate = stt.SAMPLE_RATE
        frame_samples = stt.FRAME_SAMPLES
        np = stt.np
        if np is None or stt.sd is None:
            return

        min_threshold = float(config_value("barge_in_min_energy_threshold", 520))
        noise_multiplier = float(config_value("barge_in_noise_multiplier", 4.5))
        max_seconds = float(config_value("barge_in_max_seconds", 3.5))
        silence_frames = _frames_for_ms(int(config_value("barge_in_silence_ms", 420)), frame_samples, sample_rate)
        pre_roll_frames = _frames_for_ms(int(config_value("barge_in_pre_roll_ms", 180)), frame_samples, sample_rate)
        min_active_frames = _frames_for_ms(int(config_value("barge_in_min_active_ms", 120)), frame_samples, sample_rate)
        grace_seconds = max(0.0, float(config_value("barge_in_echo_grace_ms", 220)) / 1000.0)
        min_audio_seconds = float(config_value("barge_in_min_audio_seconds", 0.25))
        interrupt_on_speech = bool(config_value("barge_in_interrupt_on_speech", True))

        frames: list[bytes] = []
        pre_roll: deque[bytes] = deque(maxlen=pre_roll_frames)
        active_count = 0
        silent_count = 0
        speech_started = False
        stop_sent = False
        started_at = time.perf_counter()
        noise_floor = min_threshold / max(1.0, noise_multiplier)

        with stt.sd.InputStream(
            device=stt._audio_device(),
            samplerate=sample_rate,
            channels=1,
            dtype="int16",
            blocksize=frame_samples,
        ) as stream:
            while (time.perf_counter() - started_at) < max_seconds:
                if self._stop_requested.is_set() and not speech_started:
                    break
                frame, _overflowed = stream.read(frame_samples)
                pcm = np.asarray(frame, dtype=np.int16).reshape(-1)
                frame_bytes = pcm.tobytes()
                energy = float(np.abs(pcm.astype(np.int32)).mean())
                threshold = max(min_threshold, noise_floor * noise_multiplier)

                if (time.perf_counter() - started_at) < grace_seconds and not speech_started:
                    pre_roll.append(frame_bytes)
                    noise_floor = (noise_floor * 0.95) + (energy * 0.05)
                    continue

                if energy >= threshold:
                    active_count += 1
                    silent_count = 0
                    if active_count >= min_active_frames:
                        if not speech_started:
                            speech_started = True
                            frames.extend(pre_roll)
                        frames.append(frame_bytes)
                        if interrupt_on_speech and not stop_sent:
                            request_stop(
                                "user speech detected during TTS",
                                phrase="audio_barge_in",
                                metadata={"energy": energy, "threshold": threshold, "spoken_text": self.spoken_text[:300]},
                            )
                            stop_sent = True
                    elif speech_started:
                        frames.append(frame_bytes)
                elif speech_started:
                    frames.append(frame_bytes)
                    silent_count += 1
                    if silent_count >= silence_frames:
                        break
                else:
                    active_count = 0
                    pre_roll.append(frame_bytes)
                    noise_floor = (noise_floor * 0.95) + (energy * 0.05)

        audio = b"".join(frames)
        if not audio or len(audio) / (sample_rate * 2) < min_audio_seconds:
            return
        text = _transcribe_interrupt_audio(audio)
        if not text:
            _record_event("audio_barge_in", "speech interrupted TTS", {"audio_seconds": len(audio) / (sample_rate * 2)})
            return
        request_stop("user barge-in", phrase=text, metadata={"heard_text": text, "source": "audio_monitor"})
        command = extract_followup_command(text)
        if command and bool(config_value("barge_in_capture_followup_commands", True)):
            enqueue_command(command, heard_text=text, metadata={"source": "audio_monitor", "audio_seconds": len(audio) / (sample_rate * 2)})


def enqueue_command(command: str, *, heard_text: str = "", metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    cleaned = _clean(command)
    if not cleaned:
        return {"ok": False, "summary": "No barge-in command to queue."}
    init_db()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        cursor = conn.execute(
            "INSERT INTO pending_commands(timestamp, command, heard_text, metadata_json) VALUES (?, ?, ?, ?)",
            (_now(), cleaned[:1000], _clean(heard_text)[:1000], _json_dumps(metadata or {})),
        )
        command_id = int(cursor.lastrowid)
    return {"ok": True, "id": command_id, "command": cleaned, "summary": f"Queued interrupt command: {cleaned}"}


def pop_pending_command() -> dict[str, Any] | None:
    init_db()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM pending_commands WHERE consumed = 0 ORDER BY id ASC LIMIT 1",
        ).fetchone()
        if row is None:
            return None
        conn.execute("UPDATE pending_commands SET consumed = 1 WHERE id = ?", (int(row["id"]),))
    return _pending_row(row)


def pending_commands(limit: int = 20, include_consumed: bool = False) -> list[dict[str, Any]]:
    init_db()
    where = "" if include_consumed else "WHERE consumed = 0"
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            f"SELECT * FROM pending_commands {where} ORDER BY id DESC LIMIT ?",
            (max(1, min(100, int(limit))),),
        ).fetchall()
    return [_pending_row(row) for row in rows]


def extract_followup_command(text: str) -> str:
    """Remove barge-in control words, leaving an optional replacement command."""

    cleaned = _clean(text)
    lowered = cleaned.lower()
    if not lowered:
        return ""
    phrases = sorted(_phrases(), key=len, reverse=True)
    for phrase in phrases:
        if lowered == phrase:
            return ""
        if lowered.startswith(phrase + " "):
            return cleaned[len(phrase) :].strip(" ,.!?:;-")
    soft_prefixes = (
        "no that's wrong",
        "no thats wrong",
        "that's wrong",
        "thats wrong",
        "wait",
        "hold on",
        "stop",
        "friday stop",
    )
    for prefix in sorted(soft_prefixes, key=len, reverse=True):
        if lowered == prefix:
            return ""
        if lowered.startswith(prefix + " "):
            return cleaned[len(prefix) :].strip(" ,.!?:;-")
    return ""


def status() -> dict[str, Any]:
    return {
        "enabled": bool(config_value("barge_in_enabled", True)),
        "audio_monitor_enabled": bool(config_value("barge_in_audio_monitor_enabled", True)),
        "requested": is_requested(),
        "stop_flag": str(STOP_FLAG_PATH),
        "last_event": recent_events(limit=1)[0] if recent_events(limit=1) else None,
        "phrases": _phrases(),
        "pending_commands": pending_commands(limit=5),
    }


def recent_events(limit: int = 20) -> list[dict[str, Any]]:
    init_db()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM barge_in_events ORDER BY id DESC LIMIT ?", (max(1, min(100, int(limit))),)).fetchall()
    return [_row(row) for row in rows]


def wipe_all() -> None:
    init_db()
    clear()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.execute("DELETE FROM barge_in_events")
        conn.execute("DELETE FROM pending_commands")


def _record_event(phrase: str, reason: str, metadata: dict[str, Any]) -> int:
    init_db()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        cursor = conn.execute(
            "INSERT INTO barge_in_events(timestamp, phrase, reason, metadata_json) VALUES (?, ?, ?, ?)",
            (_now(), _clean(phrase)[:300], _clean(reason)[:300], _json_dumps(metadata)),
        )
        return int(cursor.lastrowid)


def _transcribe_interrupt_audio(audio: bytes) -> str:
    model_name = str(config_value("barge_in_stt_model", "windows-speech")).strip()
    try:
        from input import speech_to_text as stt

        if model_name:
            return stt.transcribe_best_effort(audio, model=stt.load_model(model_name), strip_wake=False)
        return stt.transcribe_best_effort(audio, strip_wake=False)
    except Exception as exc:
        _record_event("audio_transcribe_error", "barge-in transcription error", {"error": str(exc)})
        return ""


def _pending_row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "timestamp": str(row["timestamp"]),
        "command": str(row["command"]),
        "heard_text": str(row["heard_text"]),
        "metadata": _json_loads(row["metadata_json"], {}),
        "consumed": bool(row["consumed"]),
    }


def _frames_for_ms(ms: int, frame_samples: int, sample_rate: int) -> int:
    seconds = max(0.0, float(ms) / 1000.0)
    return max(1, int(round((seconds * sample_rate) / frame_samples)))


def _phrases() -> list[str]:
    raw = str(config_value("barge_in_phrases", "friday stop,stop,stop talking,no that's wrong,that's wrong,wait,hold on"))
    return [_clean(part).lower() for part in raw.split(",") if _clean(part)]


def _row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "timestamp": str(row["timestamp"]),
        "phrase": str(row["phrase"]),
        "reason": str(row["reason"]),
        "metadata": _json_loads(row["metadata_json"], {}),
    }


def _clean(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _json_dumps(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=True, sort_keys=True, default=str)
    except TypeError:
        return json.dumps(str(value), ensure_ascii=True)


def _json_loads(value: str, default: Any) -> Any:
    try:
        return json.loads(value or "")
    except Exception:
        return default


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds")
