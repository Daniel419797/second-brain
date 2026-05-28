"""Personal local wake-word templates built from openWakeWord speech embeddings."""

from __future__ import annotations

import datetime as _dt
import json
from pathlib import Path
from typing import Any

try:
    import numpy as np
    import openwakeword
    from openwakeword.utils import AudioFeatures, download_models
except Exception:  # pragma: no cover - optional in scaffold tests
    np = None
    openwakeword = None
    AudioFeatures = None
    download_models = None

from core.config import DATA_DIR, config_value, ensure_runtime_dirs

TEMPLATE_PATH = DATA_DIR / "wake_templates.json"
SAMPLE_RATE = 16000
MIN_AUDIO_SAMPLES = SAMPLE_RATE
FRAME_MS = 30
FRAME_SAMPLES = int(SAMPLE_RATE * FRAME_MS / 1000)
STORE_VERSION = 2


class PersonalWakeMatcher:
    def __init__(self) -> None:
        if np is None or AudioFeatures is None:
            raise RuntimeError("openWakeWord feature dependencies are not installed.")
        templates = _valid_templates(load_templates())
        if not templates:
            raise RuntimeError("No valid personal wake templates enrolled. Run: python jarvis.py --clear-wake-enrollment; python jarvis.py --enroll-wake 5")
        self.threshold = float(config_value("wake_personal_threshold", 0.72))
        self.templates = [
            {
                "features": np.asarray(item["features"], dtype=np.float32),
                "speech_ms": float(item["stats"]["speech_ms"]),
            }
            for item in templates
        ]
        self.features = AudioFeatures(inference_framework=str(config_value("wake_word_inference_framework", "onnx")))

    @classmethod
    def available(cls) -> bool:
        return bool(_valid_templates(load_templates()))

    def score(self, audio_bytes: bytes) -> float:
        if not audio_bytes:
            return 0.0
        prepared = _prepare_audio(audio_bytes)
        if prepared is None:
            return 0.0
        features = _features_from_audio(prepared["audio"], self.features)
        if features.size == 0:
            return 0.0
        return max(_template_score(features, prepared["stats"], template) for template in self.templates)

    def is_match(self, audio_bytes: bytes) -> tuple[bool, float]:
        score = self.score(audio_bytes)
        return score >= self.threshold, score


def add_template(audio_bytes: bytes, phrase: str = "hey friday") -> int:
    if np is None or AudioFeatures is None:
        raise RuntimeError("openWakeWord feature dependencies are not installed.")
    ensure_runtime_dirs()
    _ensure_feature_models()
    prepared = _prepare_audio(audio_bytes, strict=True)
    if prepared is None:
        raise RuntimeError("Wake sample was too quiet, too short, or too long. Say only 'Hey Friday' clearly.")
    extractor = AudioFeatures(inference_framework=str(config_value("wake_word_inference_framework", "onnx")))
    features = _features_from_audio(prepared["audio"], extractor)
    if features.size == 0:
        raise RuntimeError("Could not extract wake-word features.")
    data = _load_store()
    data["version"] = STORE_VERSION
    data["phrase"] = phrase
    data["updated_at"] = _dt.datetime.now().isoformat(timespec="seconds")
    data.setdefault("templates", []).append({"features": features.tolist(), "stats": prepared["stats"]})
    TEMPLATE_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return len(data["templates"])


def load_templates() -> list[dict[str, Any]]:
    return list(_load_store().get("templates", []))


def clear_templates() -> None:
    if TEMPLATE_PATH.exists():
        TEMPLATE_PATH.unlink()


def _load_store() -> dict[str, Any]:
    if not TEMPLATE_PATH.exists():
        return {"version": STORE_VERSION, "phrase": "hey friday", "templates": []}
    try:
        return json.loads(TEMPLATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"version": STORE_VERSION, "phrase": "hey friday", "templates": []}


def _valid_templates(templates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    valid = []
    for item in templates:
        stats = item.get("stats")
        features = item.get("features")
        if not isinstance(stats, dict) or not features:
            continue
        if float(stats.get("speech_ms", 0)) <= 0:
            continue
        valid.append(item)
    return valid


def _ensure_feature_models() -> None:
    if openwakeword is None or download_models is None:
        return
    try:
        missing = [
            details["model_path"].replace(".tflite", ".onnx")
            for details in openwakeword.FEATURE_MODELS.values()
            if not Path(details["model_path"].replace(".tflite", ".onnx")).exists()
        ]
    except Exception:
        missing = []
    if missing:
        download_models([str(config_value("wake_word_model", "hey_jarvis"))])


def _features_from_audio(audio_bytes: bytes, extractor: Any) -> Any:
    audio = np.frombuffer(audio_bytes, dtype=np.int16)
    if audio.size < MIN_AUDIO_SAMPLES:
        audio = np.pad(audio, (0, MIN_AUDIO_SAMPLES - audio.size))
    features = extractor._get_embeddings(audio)
    return _normalize_rows(np.asarray(features, dtype=np.float32))


def _normalize_rows(features: Any) -> Any:
    norms = np.linalg.norm(features, axis=1, keepdims=True)
    return features / np.maximum(norms, 1e-6)


def _prepare_audio(audio_bytes: bytes, strict: bool = False) -> dict[str, Any] | None:
    audio = np.frombuffer(audio_bytes, dtype=np.int16)
    if audio.size < FRAME_SAMPLES:
        return None

    frame_count = audio.size // FRAME_SAMPLES
    framed = audio[: frame_count * FRAME_SAMPLES].reshape(frame_count, FRAME_SAMPLES)
    energies = np.abs(framed.astype(np.int32)).mean(axis=1)
    if energies.size == 0:
        return None

    noise_floor = float(np.percentile(energies, 20))
    min_energy = float(config_value("wake_personal_min_energy", 180))
    min_peak = float(config_value("wake_personal_min_peak_energy", 350))
    noise_multiplier = float(config_value("wake_personal_noise_multiplier", 3.5))
    peak = float(energies.max())
    threshold = max(min_energy, min(noise_floor * noise_multiplier, peak * 0.45))
    active = energies >= threshold

    if peak < min_peak:
        return None
    if int(active.sum()) < int(config_value("wake_personal_min_active_frames", 4)):
        return None

    active_indices = np.flatnonzero(active)
    margin_frames = max(1, int(round(int(config_value("wake_personal_margin_ms", 120)) / FRAME_MS)))
    start_frame = max(0, int(active_indices[0]) - margin_frames)
    end_frame = min(frame_count, int(active_indices[-1]) + margin_frames + 1)
    speech_ms = (end_frame - start_frame) * FRAME_MS
    min_ms = float(config_value("wake_personal_min_ms", 350))
    max_ms = float(config_value("wake_personal_max_ms", 1800))
    if speech_ms < min_ms or speech_ms > max_ms:
        return None

    active_ratio = float(active[start_frame:end_frame].mean())
    min_ratio = float(config_value("wake_personal_min_active_ratio", 0.18 if strict else 0.12))
    if active_ratio < min_ratio:
        return None

    trimmed = audio[start_frame * FRAME_SAMPLES : end_frame * FRAME_SAMPLES]
    stats = {
        "speech_ms": speech_ms,
        "peak_energy": peak,
        "noise_floor": noise_floor,
        "active_threshold": float(threshold),
        "active_ratio": active_ratio,
    }
    return {"audio": trimmed.tobytes(), "stats": stats}


def _template_score(features: Any, stats: dict[str, Any], template: dict[str, Any]) -> float:
    raw = _dtw_similarity(features, template["features"])
    candidate_ms = max(float(stats.get("speech_ms", 0)), 1.0)
    template_ms = max(float(template.get("speech_ms", 0)), 1.0)
    duration_ratio = min(candidate_ms / template_ms, template_ms / candidate_ms)
    return raw * (0.7 + (0.3 * duration_ratio))


def _dtw_similarity(left: Any, right: Any) -> float:
    if left.size == 0 or right.size == 0:
        return 0.0
    distances = 1.0 - np.clip(left @ right.T, -1.0, 1.0)
    rows, cols = distances.shape
    dp = np.full((rows + 1, cols + 1), np.inf, dtype=np.float32)
    dp[0, 0] = 0.0
    for row in range(1, rows + 1):
        for col in range(1, cols + 1):
            dp[row, col] = distances[row - 1, col - 1] + min(dp[row - 1, col], dp[row, col - 1], dp[row - 1, col - 1])
    avg_distance = float(dp[rows, cols] / max(rows, cols))
    return max(0.0, min(1.0, 1.0 - avg_distance))
