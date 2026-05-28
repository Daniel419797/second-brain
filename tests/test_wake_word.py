import threading

import numpy as np

from input import wake_word


class FakeOpenWakeWordModel:
    def __init__(self, **kwargs):
        self.calls = 0
        self.kwargs = kwargs

    def predict(self, pcm, **kwargs):
        self.calls += 1
        score = 0.9 if self.calls == 7 else 0.0
        return {"hey_jarvis": score}


class QuietOpenWakeWordModel:
    def __init__(self, **kwargs):
        self.kwargs = kwargs

    def predict(self, pcm, **kwargs):
        return {"hey_jarvis": 0.0}


class FakeStream:
    value = 0

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self, frames):
        return np.full((frames, 1), self.value, dtype=np.int16), False


class FakeSoundDevice:
    @staticmethod
    def InputStream(**kwargs):
        return FakeStream()


def test_wake_word_callback_fires_once_and_stops(monkeypatch):
    created = []

    def make_model(**kwargs):
        model = FakeOpenWakeWordModel(**kwargs)
        created.append(model)
        return model

    monkeypatch.setattr(wake_word, "sd", FakeSoundDevice)
    monkeypatch.setattr(wake_word, "Model", make_model)
    monkeypatch.setattr(wake_word, "download_models", lambda model_names: None)
    monkeypatch.setattr(wake_word, "_model_files_exist", lambda *args: True)
    monkeypatch.setattr(wake_word, "config_value", lambda key, default=None: "openwakeword" if key == "wake_word_backend" else default)
    fired = threading.Event()
    scores = []
    energies = []
    captured_audio = []

    sources = []

    def on_wake(initial_audio, source):
        captured_audio.append(initial_audio)
        sources.append(source)
        fired.set()

    listener = wake_word.WakeWordListener(callback=on_wake, score_callback=lambda score, energy: (scores.append(score), energies.append(energy)))
    listener.start()
    assert fired.wait(1)
    listener.stop()

    assert created[0].calls >= 7
    assert max(scores) == 0.9
    assert max(energies) == 0.0
    assert captured_audio
    assert sources == ["wake_word"]
    assert created[0].kwargs["wakeword_models"] == ["hey_jarvis"]
    assert created[0].kwargs["inference_framework"] == "onnx"


def test_personal_wake_callback_fires_without_energy_fallback(monkeypatch):
    class FakePersonalMatcher:
        threshold = 0.7

        def score(self, audio):
            return 0.8 if audio else 0.0

    monkeypatch.setattr(wake_word, "sd", FakeSoundDevice)
    monkeypatch.setattr(wake_word, "Model", lambda **kwargs: QuietOpenWakeWordModel(**kwargs))
    monkeypatch.setattr(wake_word, "download_models", lambda model_names: None)
    monkeypatch.setattr(wake_word, "_model_files_exist", lambda *args: True)
    monkeypatch.setattr(wake_word, "_load_personal_matcher", lambda backend: FakePersonalMatcher())
    monkeypatch.setattr(
        wake_word,
        "config_value",
        lambda key, default=None: {
            "wake_word_backend": "personal",
            "wake_energy_fallback": False,
        }.get(key, default),
    )
    monkeypatch.setattr(FakeStream, "value", 100)
    fired = threading.Event()
    scores = []
    sources = []

    def on_wake(initial_audio, source):
        sources.append(source)
        fired.set()

    listener = wake_word.WakeWordListener(callback=on_wake, score_callback=lambda score, energy: scores.append(score))
    listener.start()
    assert fired.wait(1)
    listener.stop()

    assert sources == ["personal"]
    assert max(scores) == 0.8
    monkeypatch.setattr(FakeStream, "value", 0)


def test_energy_fallback_fires_when_model_score_stays_zero(monkeypatch):
    monkeypatch.setattr(wake_word, "sd", FakeSoundDevice)
    monkeypatch.setattr(wake_word, "Model", lambda **kwargs: QuietOpenWakeWordModel(**kwargs))
    monkeypatch.setattr(wake_word, "download_models", lambda model_names: None)
    monkeypatch.setattr(wake_word, "_model_files_exist", lambda *args: True)
    monkeypatch.setattr(wake_word, "config_value", lambda key, default=None: 1 if key == "wake_energy_patience" else 500 if key == "wake_energy_threshold" else default)
    monkeypatch.setattr(FakeStream, "value", 700)
    fired = threading.Event()

    sources = []

    def on_wake(initial_audio, source):
        sources.append(source)
        fired.set()

    listener = wake_word.WakeWordListener(callback=on_wake)
    listener.start()
    assert fired.wait(1)
    listener.stop()
    assert sources == ["energy"]
    monkeypatch.setattr(FakeStream, "value", 0)


def test_listener_can_pause_and_resume(monkeypatch):
    monkeypatch.setattr(wake_word, "sd", FakeSoundDevice)
    monkeypatch.setattr(wake_word, "Model", lambda **kwargs: QuietOpenWakeWordModel(**kwargs))
    monkeypatch.setattr(wake_word, "download_models", lambda model_names: None)
    monkeypatch.setattr(wake_word, "_model_files_exist", lambda *args: True)

    listener = wake_word.WakeWordListener(callback=lambda: None)
    listener.pause()
    assert listener._paused.is_set()
    listener.resume()
    assert not listener._paused.is_set()
