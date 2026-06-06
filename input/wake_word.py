"""Wake-word listener running in a daemon thread."""

from __future__ import annotations

import threading
import time
from collections import deque
from pathlib import Path
from typing import Callable

try:
    import numpy as np
except Exception:  # pragma: no cover - optional in scaffold tests
    np = None

try:
    import sounddevice as sd
except Exception:  # pragma: no cover - optional in scaffold tests
    sd = None

try:
    import openwakeword
    from openwakeword import Model
    from openwakeword.utils import download_models
except Exception:  # pragma: no cover - optional in scaffold tests
    openwakeword = None
    Model = None
    download_models = None

from core.config import config_value
from input.personal_wake import PersonalWakeMatcher

SAMPLE_RATE = 16000
DEFAULT_FRAME_SAMPLES = 1280


class WakeWordListener:
    def __init__(self, callback: Callable[..., None], score_callback: Callable[[float, float], None] | None = None):
        if np is None or sd is None or Model is None:
            raise RuntimeError("openWakeWord dependencies are not installed.")

        self._model_name = str(config_value("wake_word_model", "hey_jarvis"))
        self._threshold = float(config_value("wake_word_threshold", 0.5))
        self._patience = int(config_value("wake_word_patience", 2))
        self._debounce_seconds = float(config_value("wake_word_debounce_seconds", 1.0))
        self._frame_samples = int(config_value("wake_word_frame_samples", DEFAULT_FRAME_SAMPLES))
        self._energy_fallback = bool(config_value("wake_energy_fallback", True))
        self._energy_threshold = float(config_value("wake_energy_threshold", 500))
        self._energy_patience = int(config_value("wake_energy_patience", 2))
        self._energy_silence_frames = _frames_for_ms(int(config_value("wake_energy_silence_ms", 700)), self._frame_samples)
        self._energy_max_frames = _frames_for_seconds(float(config_value("wake_energy_max_seconds", 6.0)), self._frame_samples)
        inference_framework = str(config_value("wake_word_inference_framework", "onnx"))
        frame_ms = (self._frame_samples / SAMPLE_RATE) * 1000
        pre_roll_frames = max(1, int(round(float(config_value("wake_trigger_pre_roll_ms", 900)) / frame_ms)))
        self._backend = str(config_value("wake_word_backend", "personal")).lower()
        self._personal_matcher = _load_personal_matcher(self._backend)

        _ensure_models(self._model_name, inference_framework)
        self._model = Model(wakeword_models=[self._model_name], inference_framework=inference_framework)
        self._callback = callback
        self._score_callback = score_callback
        self._stop = threading.Event()
        self._paused = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._started = False
        self._stream = None
        self._last_fire = 0.0
        self._energy_hits = 0
        self._pre_roll: deque[bytes] = deque(maxlen=pre_roll_frames)

    def start(self) -> None:
        self._started = True
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._started:
            self._thread.join(timeout=2.0)

    def pause(self) -> None:
        self._paused.set()

    def resume(self) -> None:
        self._paused.clear()

    def _run(self) -> None:
        while not self._stop.is_set():
            if self._paused.is_set():
                time.sleep(0.05)
                continue
            try:
                with sd.InputStream(
                    device=_audio_device(),
                    samplerate=SAMPLE_RATE,
                    channels=1,
                    dtype="int16",
                    blocksize=self._frame_samples,
                ) as self._stream:
                    while not self._stop.is_set() and not self._paused.is_set():
                        t0 = time.perf_counter()
                        frame, overflowed = self._stream.read(self._frame_samples)
                        if overflowed:
                            _log_warning(RuntimeError("input overflow"))
                        pcm = np.asarray(frame).reshape(-1).astype(np.int16)
                        self._pre_roll.append(pcm.tobytes())
                        predictions = self._model.predict(
                            pcm,
                            patience={self._model_name: self._patience},
                            threshold={self._model_name: self._threshold},
                        )
                        score = float(predictions.get(self._model_name, 0.0))
                        energy = float(np.abs(pcm.astype(np.int32)).mean())
                        personal_score = self._personal_score()
                        if self._score_callback is not None:
                            self._score_callback(max(score, personal_score), energy)
                        if self._should_fire_personal(personal_score):
                            self._last_fire = time.perf_counter()
                            self._fire("personal")
                            _log_personal(personal_score)
                        elif self._should_fire(score):
                            self._last_fire = time.perf_counter()
                            self._fire("wake_word")
                            _log_latency(t0, score)
                        elif self._should_fire_energy(energy):
                            self._last_fire = time.perf_counter()
                            utterance = self._capture_energy_utterance()
                            self._fire("energy", initial_audio=utterance)
                            _log_energy_fallback(energy)
            except Exception as exc:
                _log_warning(exc)
                time.sleep(0.1)

    def _should_fire(self, score: float) -> bool:
        if self._backend == "personal":
            return False
        if score < self._threshold:
            return False
        return time.perf_counter() - self._last_fire >= self._debounce_seconds

    def _should_fire_personal(self, score: float) -> bool:
        if self._personal_matcher is None:
            return False
        if score < self._personal_matcher.threshold:
            return False
        return time.perf_counter() - self._last_fire >= self._debounce_seconds

    def _should_fire_energy(self, energy: float) -> bool:
        if not self._energy_fallback:
            return False
        if energy >= self._energy_threshold:
            self._energy_hits += 1
        else:
            self._energy_hits = 0
        if self._energy_hits < self._energy_patience:
            return False
        self._energy_hits = 0
        return time.perf_counter() - self._last_fire >= self._debounce_seconds

    def _personal_score(self) -> float:
        if self._personal_matcher is None:
            return 0.0
        try:
            return self._personal_matcher.score(b"".join(self._pre_roll))
        except Exception:
            return 0.0

    def _capture_energy_utterance(self) -> bytes:
        chunks = list(self._pre_roll)
        silent_count = 0
        for _ in range(self._energy_max_frames):
            if self._stop.is_set() or self._paused.is_set() or self._stream is None:
                break
            frame, overflowed = self._stream.read(self._frame_samples)
            if overflowed:
                _log_warning(RuntimeError("input overflow"))
            pcm = np.asarray(frame).reshape(-1).astype(np.int16)
            energy = float(np.abs(pcm.astype(np.int32)).mean())
            chunks.append(pcm.tobytes())
            if energy >= self._energy_threshold:
                silent_count = 0
            else:
                silent_count += 1
            if silent_count >= self._energy_silence_frames:
                break
        return b"".join(chunks)

    def _fire(self, source: str, initial_audio: bytes | None = None) -> None:
        initial_audio = initial_audio if initial_audio is not None else b"".join(self._pre_roll)
        try:
            self._callback(initial_audio, source)
        except TypeError:
            try:
                self._callback(initial_audio)
            except TypeError:
                self._callback()
        finally:
            self._pre_roll.clear()
            self._energy_hits = 0


def _ensure_models(model_name: str, inference_framework: str) -> None:
    if openwakeword is None or download_models is None:
        return
    if _model_files_exist(model_name, inference_framework):
        return
    download_models([model_name])


def _load_personal_matcher(backend: str) -> PersonalWakeMatcher | None:
    if backend not in {"personal", "hybrid"}:
        return None
    try:
        return PersonalWakeMatcher()
    except Exception as exc:
        _log_personal_unavailable(exc)
        return None


def _audio_device() -> int | str | None:
    device = config_value("audio_input_device", None)
    if device in {"", "default", "none", None}:
        return None
    return device


def _frames_for_ms(ms: int, frame_samples: int) -> int:
    frame_ms = (frame_samples / SAMPLE_RATE) * 1000
    return max(1, int(round(ms / frame_ms)))


def _frames_for_seconds(seconds: float, frame_samples: int) -> int:
    frame_ms = (frame_samples / SAMPLE_RATE) * 1000
    return max(1, int(round((seconds * 1000) / frame_ms)))


def _model_files_exist(model_name: str, inference_framework: str) -> bool:
    if openwakeword is None:
        return False
    try:
        paths = openwakeword.get_pretrained_model_paths(inference_framework)
        feature_paths = [
            details["model_path"] if inference_framework == "tflite" else details["model_path"].replace(".tflite", ".onnx")
            for details in openwakeword.FEATURE_MODELS.values()
        ]
    except Exception:
        return False
    normalized = model_name.replace(" ", "_")
    wake_model_exists = any(normalized in str(path) and Path(path).exists() for path in paths)
    return wake_model_exists and all(Path(path).exists() for path in feature_paths)


def _log_latency(start: float, score: float) -> None:
    try:
        from output.display import log

        log("DEBUG", f"[PERF] wake_word_latency={(time.perf_counter() - start) * 1000:.0f}ms score={score:.2f}")
    except Exception:
        return


def _log_energy_fallback(energy: float) -> None:
    try:
        from output.display import log

        log("INFO", f"[WAKE] energy fallback triggered energy={energy:.0f}")
    except Exception:
        return


def _log_personal(score: float) -> None:
    try:
        from output.display import log

        log("INFO", f"[WAKE] personal wake matched score={score:.2f}")
    except Exception:
        return


def _log_personal_unavailable(exc: Exception) -> None:
    try:
        from output.display import log

        log("WARNING", f"[WAKE] personal wake unavailable: {exc}")
    except Exception:
        return


def _log_warning(exc: Exception) -> None:
    try:
        from output.display import log

        log("WARNING", f"[WAKE] stream recovery after {exc.__class__.__name__}")
    except Exception:
        return
