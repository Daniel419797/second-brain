import numpy as np

from input import speaker_id


def _config(key, default=None):
    values = {
        "speaker_feature_backend": "mfcc",
        "speaker_min_energy": 10,
        "speaker_min_peak_energy": 10,
        "speaker_noise_multiplier": 1.2,
        "speaker_min_active_frames": 1,
        "speaker_min_ms": 100,
        "speaker_max_ms": 7000,
        "speaker_min_active_ratio": 0.05,
        "speaker_verification_threshold": 0.65,
        "speaker_negative_margin": 0.04,
    }
    return values.get(key, default)


def _tone(freq: float, seconds: float = 1.4) -> bytes:
    t = np.arange(int(speaker_id.SAMPLE_RATE * seconds), dtype=np.float32) / speaker_id.SAMPLE_RATE
    audio = (np.sin(2 * np.pi * freq * t) * 12000).astype(np.int16)
    return audio.tobytes()


def test_speaker_profile_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(speaker_id, "PROFILE_PATH", tmp_path / "speaker_profile.json")
    monkeypatch.setattr(speaker_id, "config_value", _config)

    audio = _tone(160)

    assert speaker_id.add_voice_sample(audio, label="Daniel") == 1

    verifier = speaker_id.SpeakerVerifier()
    matched, score = verifier.is_match(audio)

    assert matched is True
    assert score >= verifier.threshold


def test_negative_speaker_sample_rejects_comparison_voice(tmp_path, monkeypatch):
    monkeypatch.setattr(speaker_id, "PROFILE_PATH", tmp_path / "speaker_profile.json")
    monkeypatch.setattr(speaker_id, "config_value", _config)

    daniel = _tone(150)
    roommate = _tone(260)

    speaker_id.add_voice_sample(daniel, label="Daniel")
    speaker_id.add_voice_sample(roommate, label="Daniel", kind="negative")

    verifier = speaker_id.SpeakerVerifier()

    assert verifier.score_details(daniel)["match"] is True
    assert verifier.score_details(roommate)["match"] is False
