"""Local speaker profile matching for continuous voice mode."""

from __future__ import annotations

import datetime as _dt
import json
from pathlib import Path
from typing import Any

try:
    import numpy as np
    from scipy.fftpack import dct as scipy_dct
except Exception:  # pragma: no cover - optional in scaffold tests
    np = None
    scipy_dct = None

try:
    import openwakeword
    from openwakeword.utils import AudioFeatures, download_models
except Exception:  # pragma: no cover - optional fallback backend
    openwakeword = None
    AudioFeatures = None
    download_models = None

from core.config import DATA_DIR, config_value, ensure_runtime_dirs

PROFILE_PATH = DATA_DIR / "speaker_profile.json"
SAMPLE_RATE = 16000
MIN_AUDIO_SAMPLES = SAMPLE_RATE
FRAME_MS = 30
FRAME_SAMPLES = int(SAMPLE_RATE * FRAME_MS / 1000)
STORE_VERSION = 2


class SpeakerVerifier:
    def __init__(self) -> None:
        if np is None:
            raise RuntimeError("numpy is required for speaker verification.")
        self.backend = _speaker_backend()
        samples = _valid_samples(load_voice_samples(), backend=self.backend, kind="positive")
        if not samples:
            raise RuntimeError(f"No {self.backend} speaker profile enrolled. Run: python jarvis.py --clear-speaker-enrollment; python jarvis.py --enroll-speaker 6")
        self.negative_margin = float(config_value("speaker_negative_margin", 0.06))
        self.voiceprints = [np.asarray(item["voiceprint"], dtype=np.float32) for item in samples]
        self.centroid = _mean_vector(self.voiceprints)
        self.template_self_scores = _template_self_scores(self.voiceprints, self.centroid)
        self.centroid_self_scores = [_cosine(template, self.centroid) for template in self.voiceprints]
        self.threshold = _resolve_threshold(
            "speaker_verification_threshold",
            self.template_self_scores,
            fallback=0.78,
            margin_key="speaker_auto_threshold_margin",
            margin_fallback=0.04,
            floor=0.62,
            ceiling=0.97,
        )
        self.centroid_threshold = _resolve_threshold(
            "speaker_centroid_threshold",
            self.centroid_self_scores,
            fallback=max(0.60, self.threshold - 0.05),
            margin_key="speaker_centroid_margin",
            margin_fallback=0.05,
            floor=0.55,
            ceiling=0.97,
        )
        self.negative_voiceprints = [
            np.asarray(item["voiceprint"], dtype=np.float32)
            for item in _valid_samples(load_voice_samples(), backend=self.backend, kind="negative")
        ]
        self.features = _openwakeword_features() if self.backend == "openwakeword" else None

    @classmethod
    def available(cls) -> bool:
        backend = _speaker_backend()
        return bool(_valid_samples(load_voice_samples(), backend=backend, kind="positive"))

    def score(self, audio_bytes: bytes) -> float:
        return float(self.score_details(audio_bytes)["positive_score"])

    def score_details(self, audio_bytes: bytes) -> dict[str, Any]:
        candidate = _extract_voiceprint(audio_bytes, backend=self.backend, extractor=self.features)
        if candidate is None:
            return _details(False, 0.0, 0.0, 0.0, self.threshold, self.centroid_threshold, self.negative_margin, self.backend)
        positive_score = max(_cosine(candidate, template) for template in self.voiceprints)
        centroid_score = _cosine(candidate, self.centroid)
        negative_score = max((_cosine(candidate, template) for template in self.negative_voiceprints), default=0.0)
        margin = positive_score - negative_score
        match = positive_score >= self.threshold and centroid_score >= self.centroid_threshold
        if self.negative_voiceprints:
            match = match and margin >= self.negative_margin
        return _details(
            match,
            positive_score,
            centroid_score,
            negative_score,
            self.threshold,
            self.centroid_threshold,
            self.negative_margin,
            self.backend,
        )

    def is_match(self, audio_bytes: bytes) -> tuple[bool, float]:
        details = self.score_details(audio_bytes)
        return bool(details["match"]), float(details["positive_score"])


def add_voice_sample(audio_bytes: bytes, label: str = "user", kind: str = "positive") -> int:
    if np is None:
        raise RuntimeError("numpy is required for speaker verification.")
    kind = "negative" if kind == "negative" else "positive"
    ensure_runtime_dirs()
    backend = _speaker_backend()
    extractor = _openwakeword_features() if backend == "openwakeword" else None
    voiceprint = _extract_voiceprint(audio_bytes, backend=backend, strict=True, extractor=extractor)
    if voiceprint is None:
        raise RuntimeError("Speaker sample was too quiet, too short, or too long. Speak a clear normal sentence.")
    prepared = _prepare_audio(audio_bytes, strict=True)
    data = _load_store()
    data["version"] = STORE_VERSION
    data["label"] = label
    data["updated_at"] = _dt.datetime.now().isoformat(timespec="seconds")
    data.setdefault("samples", []).append(
        {
            "backend": backend,
            "kind": kind,
            "voiceprint": voiceprint.tolist(),
            "stats": prepared["stats"] if prepared else {},
        }
    )
    PROFILE_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return len(_valid_samples(data["samples"], backend=backend, kind=kind))


def load_voice_samples() -> list[dict[str, Any]]:
    return list(_load_store().get("samples", []))


def clear_voice_profile() -> None:
    if PROFILE_PATH.exists():
        PROFILE_PATH.unlink()


def _details(
    match: bool,
    positive_score: float,
    centroid_score: float,
    negative_score: float,
    threshold: float,
    centroid_threshold: float,
    margin_threshold: float,
    backend: str,
) -> dict[str, Any]:
    return {
        "match": match,
        "positive_score": positive_score,
        "centroid_score": centroid_score,
        "negative_score": negative_score,
        "margin": positive_score - negative_score,
        "threshold": threshold,
        "centroid_threshold": centroid_threshold,
        "negative_margin": margin_threshold,
        "backend": backend,
    }


def _resolve_threshold(
    key: str,
    self_scores: list[float],
    fallback: float,
    margin_key: str,
    margin_fallback: float,
    floor: float,
    ceiling: float,
) -> float:
    raw = config_value(key, "auto")
    if not _is_auto(raw):
        return float(raw)
    if not self_scores:
        return fallback
    margin = float(config_value(margin_key, margin_fallback))
    baseline = float(np.percentile(np.asarray(self_scores, dtype=np.float32), 10))
    return max(floor, min(ceiling, baseline - margin))


def _is_auto(value: Any) -> bool:
    return isinstance(value, str) and value.strip().lower() in {"", "auto", "calibrate", "calibrated"}


def _mean_vector(vectors: list[Any]) -> Any:
    centroid = np.mean(np.stack(vectors), axis=0).astype(np.float32)
    return _normalize_vector(centroid)


def _template_self_scores(vectors: list[Any], centroid: Any) -> list[float]:
    if len(vectors) <= 1:
        return [_cosine(vectors[0], centroid)] if vectors else []
    scores = []
    for index, vector in enumerate(vectors):
        others = [template for other_index, template in enumerate(vectors) if other_index != index]
        scores.append(max(_cosine(vector, other) for other in others))
    return scores


def _speaker_backend() -> str:
    backend = str(config_value("speaker_feature_backend", "mfcc")).strip().lower()
    return backend if backend in {"mfcc", "openwakeword"} else "mfcc"


def _load_store() -> dict[str, Any]:
    if not PROFILE_PATH.exists():
        return {"version": STORE_VERSION, "label": "user", "samples": []}
    try:
        return json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"version": STORE_VERSION, "label": "user", "samples": []}


def _valid_samples(samples: list[dict[str, Any]], backend: str | None = None, kind: str | None = None) -> list[dict[str, Any]]:
    valid = []
    for item in samples:
        voiceprint = item.get("voiceprint")
        stats = item.get("stats")
        sample_backend = item.get("backend", "openwakeword")
        sample_kind = item.get("kind", "positive")
        if backend is not None and sample_backend != backend:
            continue
        if kind is not None and sample_kind != kind:
            continue
        if not voiceprint or not isinstance(stats, dict):
            continue
        if float(stats.get("speech_ms", 1)) <= 0:
            continue
        valid.append(item)
    return valid


def _extract_voiceprint(audio_bytes: bytes, backend: str, strict: bool = False, extractor: Any = None) -> Any | None:
    prepared = _prepare_audio(audio_bytes, strict=strict)
    if prepared is None:
        return None
    if backend == "openwakeword":
        return _openwakeword_voiceprint(prepared["audio"], extractor)
    return _mfcc_voiceprint(prepared["audio"])


def _openwakeword_features() -> Any:
    if AudioFeatures is None:
        raise RuntimeError("openWakeWord feature dependencies are not installed.")
    _ensure_openwakeword_feature_models()
    return AudioFeatures(inference_framework=str(config_value("wake_word_inference_framework", "onnx")))


def _openwakeword_voiceprint(audio_bytes: bytes, extractor: Any) -> Any:
    if extractor is None:
        extractor = _openwakeword_features()
    audio = np.frombuffer(audio_bytes, dtype=np.int16)
    if audio.size < MIN_AUDIO_SAMPLES:
        audio = np.pad(audio, (0, MIN_AUDIO_SAMPLES - audio.size))
    features = extractor._get_embeddings(audio)
    features = np.asarray(features, dtype=np.float32)
    norms = np.linalg.norm(features, axis=1, keepdims=True)
    features = features / np.maximum(norms, 1e-6)
    return _stats_voiceprint(features)


def _mfcc_voiceprint(audio_bytes: bytes) -> Any:
    if scipy_dct is None:
        raise RuntimeError("scipy is required for MFCC speaker verification.")
    audio = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32) / 32768.0
    if audio.size < int(0.5 * SAMPLE_RATE):
        return None
    emphasized = np.append(audio[0], audio[1:] - 0.97 * audio[:-1])
    frames = _frame_signal(emphasized)
    if frames.size == 0:
        return None
    frames *= np.hamming(frames.shape[1]).astype(np.float32)
    nfft = 512
    power = (np.abs(np.fft.rfft(frames, n=nfft)) ** 2) / nfft
    filters = _mel_filterbank(30, nfft)
    log_mel = np.log(np.maximum(power @ filters.T, 1e-10))
    mfcc = scipy_dct(log_mel, type=2, axis=1, norm="ortho")[:, 1:14]
    delta = np.gradient(mfcc, axis=0) if mfcc.shape[0] > 1 else np.zeros_like(mfcc)
    energy = np.log(np.maximum((frames**2).mean(axis=1, keepdims=True), 1e-10))
    zcr = _zero_crossing_rate(frames)
    centroid, bandwidth = _spectral_shape(power)
    pitch = _pitch_track(frames)
    features = np.concatenate([mfcc, delta, energy, zcr, centroid, bandwidth, pitch], axis=1)
    return _stats_voiceprint(features.astype(np.float32))


def _stats_voiceprint(features: Any) -> Any:
    vector = np.concatenate(
        [
            features.mean(axis=0),
            features.std(axis=0),
            np.percentile(features, 25, axis=0),
            np.percentile(features, 75, axis=0),
        ]
    ).astype(np.float32)
    return _normalize_vector(vector)


def _normalize_vector(vector: Any) -> Any:
    norm = float(np.linalg.norm(vector))
    if norm <= 1e-6:
        return vector
    return vector / norm


def _frame_signal(audio: Any) -> Any:
    frame_length = int(round(0.025 * SAMPLE_RATE))
    frame_step = int(round(0.010 * SAMPLE_RATE))
    if audio.size < frame_length:
        audio = np.pad(audio, (0, frame_length - audio.size))
    frame_count = 1 + int(np.ceil((audio.size - frame_length) / frame_step))
    pad_length = (frame_count - 1) * frame_step + frame_length
    padded = np.pad(audio, (0, max(0, pad_length - audio.size)))
    indices = np.tile(np.arange(frame_length), (frame_count, 1)) + np.tile(np.arange(frame_count) * frame_step, (frame_length, 1)).T
    return padded[indices]


def _mel_filterbank(filter_count: int, nfft: int) -> Any:
    low_mel = _hz_to_mel(50)
    high_mel = _hz_to_mel(SAMPLE_RATE / 2)
    mel_points = np.linspace(low_mel, high_mel, filter_count + 2)
    hz_points = _mel_to_hz(mel_points)
    bins = np.floor((nfft + 1) * hz_points / SAMPLE_RATE).astype(int)
    filters = np.zeros((filter_count, nfft // 2 + 1), dtype=np.float32)
    for idx in range(1, filter_count + 1):
        left, center, right = bins[idx - 1], bins[idx], bins[idx + 1]
        if center == left:
            center += 1
        if right == center:
            right += 1
        for bin_idx in range(left, center):
            filters[idx - 1, bin_idx] = (bin_idx - left) / max(center - left, 1)
        for bin_idx in range(center, min(right, filters.shape[1])):
            filters[idx - 1, bin_idx] = (right - bin_idx) / max(right - center, 1)
    return filters


def _hz_to_mel(hz: Any) -> Any:
    return 2595 * np.log10(1 + hz / 700)


def _mel_to_hz(mel: Any) -> Any:
    return 700 * (10 ** (mel / 2595) - 1)


def _zero_crossing_rate(frames: Any) -> Any:
    signs = np.signbit(frames)
    crossings = np.mean(signs[:, 1:] != signs[:, :-1], axis=1, keepdims=True).astype(np.float32)
    return crossings


def _spectral_shape(power: Any) -> tuple[Any, Any]:
    freqs = np.linspace(0, SAMPLE_RATE / 2, power.shape[1], dtype=np.float32)
    denom = np.maximum(power.sum(axis=1, keepdims=True), 1e-10)
    centroid_hz = (power @ freqs[:, None]) / denom
    spread = np.sqrt(((power * (freqs[None, :] - centroid_hz) ** 2).sum(axis=1, keepdims=True)) / denom)
    return centroid_hz / 4000.0, spread / 4000.0


def _pitch_track(frames: Any) -> Any:
    min_lag = int(SAMPLE_RATE / 350)
    max_lag = int(SAMPLE_RATE / 70)
    pitches = []
    for frame in frames:
        centered = frame - frame.mean()
        corr = np.correlate(centered, centered, mode="full")[centered.size - 1 :]
        if corr[0] <= 1e-8 or corr.size <= max_lag:
            pitches.append(0.0)
            continue
        segment = corr[min_lag:max_lag]
        lag = int(np.argmax(segment)) + min_lag
        strength = float(segment.max() / max(corr[0], 1e-8))
        pitches.append((SAMPLE_RATE / lag) / 300.0 if strength >= 0.25 else 0.0)
    return np.asarray(pitches, dtype=np.float32).reshape(-1, 1)


def _ensure_openwakeword_feature_models() -> None:
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
    min_energy = float(config_value("speaker_min_energy", 160))
    min_peak = float(config_value("speaker_min_peak_energy", 300))
    noise_multiplier = float(config_value("speaker_noise_multiplier", 3.0))
    peak = float(energies.max())
    threshold = max(min_energy, min(noise_floor * noise_multiplier, peak * 0.45))
    active = energies >= threshold

    if peak < min_peak:
        return None
    if int(active.sum()) < int(config_value("speaker_min_active_frames", 6)):
        return None

    active_indices = np.flatnonzero(active)
    margin_frames = max(1, int(round(int(config_value("speaker_margin_ms", 180)) / FRAME_MS)))
    start_frame = max(0, int(active_indices[0]) - margin_frames)
    end_frame = min(frame_count, int(active_indices[-1]) + margin_frames + 1)
    speech_ms = (end_frame - start_frame) * FRAME_MS
    min_ms = float(config_value("speaker_min_ms", 650 if strict else 450))
    max_ms = float(config_value("speaker_max_ms", 7000))
    if speech_ms < min_ms or speech_ms > max_ms:
        return None

    active_ratio = float(active[start_frame:end_frame].mean())
    min_ratio = float(config_value("speaker_min_active_ratio", 0.14 if strict else 0.10))
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


def _cosine(left: Any, right: Any) -> float:
    if left.shape != right.shape:
        return 0.0
    score = float(np.dot(left, right))
    return max(0.0, min(1.0, score))
