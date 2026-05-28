from output import voice


class FakeLocalVoice:
    def __init__(self, voice_id, name, languages=None, gender=""):
        self.id = voice_id
        self.name = name
        self.languages = languages or []
        self.gender = gender


def test_speak_uses_pyttsx3_when_offline(monkeypatch):
    calls = []
    monkeypatch.setattr(voice, "_is_online", lambda: False)
    monkeypatch.setattr(voice, "reload_config", lambda: {"voice_backend": "edge"})
    monkeypatch.setattr(voice, "_speak_pyttsx3", lambda text: calls.append(text))

    voice.speak("Hello")

    assert calls == ["Hello"]


def test_elevenlabs_failure_falls_back_to_pyttsx3(monkeypatch):
    calls = []
    monkeypatch.setattr(voice, "_is_online", lambda: True)
    monkeypatch.setattr(voice, "reload_config", lambda: {"voice_backend": "elevenlabs"})
    monkeypatch.setattr(voice, "_speak_elevenlabs", lambda text: (_ for _ in ()).throw(RuntimeError("boom")))
    monkeypatch.setattr(voice, "_speak_edge", lambda text, cfg=None: (_ for _ in ()).throw(RuntimeError("edge boom")))
    monkeypatch.setattr(voice, "_speak_pyttsx3", lambda text: calls.append(text))

    voice.speak("Hello")

    assert calls == ["Hello"]


def test_edge_backend_is_default_when_online(monkeypatch):
    calls = []
    monkeypatch.setattr(voice, "_is_online", lambda: True)
    monkeypatch.setattr(voice, "reload_config", lambda: {"voice_backend": "edge"})
    monkeypatch.setattr(voice, "_speak_edge", lambda text, cfg=None: calls.append((text, cfg)))
    monkeypatch.setattr(voice, "_speak_pyttsx3", lambda text: (_ for _ in ()).throw(AssertionError("fallback not expected")))

    voice.speak("Hello")

    assert calls == [("Hello", {"voice_backend": "edge"})]


def test_speak_starts_barge_in_monitor_when_enabled(monkeypatch):
    calls = []

    class Monitor:
        def stop(self):
            calls.append("stop")

    monkeypatch.setattr(voice, "_is_online", lambda: True)
    monkeypatch.setattr(voice, "reload_config", lambda: {"voice_backend": "edge", "barge_in_audio_monitor_enabled": True})
    monkeypatch.setattr(voice.barge_in, "start_audio_monitor", lambda text: calls.append(("monitor", text)) or Monitor())
    monkeypatch.setattr(voice, "_speak_edge", lambda text, cfg=None: calls.append(("edge", text)))

    voice.speak("Hello")

    assert calls == [("monitor", "Hello"), ("edge", "Hello"), "stop"]


def test_preview_edge_voices_uses_natural_free_samples(monkeypatch):
    calls = []
    monkeypatch.setattr(voice, "_is_online", lambda: True)
    monkeypatch.setattr(voice, "reload_config", lambda: {"edge_volume": "+0%"})
    monkeypatch.setattr(voice, "_speak_edge", lambda text, cfg=None: calls.append((text, cfg)))

    played = voice.preview_edge_voices("Ready when you are.")

    assert played[0] == "en-US-EmmaMultilingualNeural"
    assert "en-US-JennyNeural" in played
    assert calls[0][0] == "Emma. Ready when you are."
    assert calls[0][1]["edge_voice"] == "en-US-EmmaMultilingualNeural"
    assert calls[0][1]["edge_rate"] == "+0%"


def test_fast_voice_edge_uses_fast_rate(monkeypatch):
    captured = {}

    async def fake_edge_bytes(text, voice, rate, volume, pitch):
        captured.update({"text": text, "voice": voice, "rate": rate, "volume": volume, "pitch": pitch})
        return b"mp3"

    voice._cache.clear()
    monkeypatch.setenv("JARVIS_FAST_VOICE", "1")
    monkeypatch.setattr(voice, "edge_tts", object())
    monkeypatch.setattr(voice, "_edge_bytes", fake_edge_bytes)
    monkeypatch.setattr(voice, "_play_mp3", lambda audio: None)
    monkeypatch.setattr(voice, "_read_persistent_edge_cache", lambda cache_key, cfg: None)
    monkeypatch.setattr(voice, "_write_persistent_edge_cache", lambda cache_key, audio, cfg: None)

    voice._speak_edge(
        "Hello",
        {
            "edge_voice": "en-US-EmmaMultilingualNeural",
            "edge_rate": "+0%",
            "edge_volume": "+0%",
            "edge_pitch": "+0Hz",
            "fast_voice_edge_rate": "+18%",
        },
    )

    assert captured["rate"] == "+18%"


def test_edge_persistent_cache_reuses_audio_after_memory_cache_clear(monkeypatch, tmp_path):
    calls = []
    played = []

    async def fake_edge_bytes(text, voice, rate, volume, pitch):
        calls.append(text)
        return b"cached-mp3"

    monkeypatch.setattr(voice, "VOICE_CACHE_DIR", tmp_path)
    monkeypatch.setattr(voice, "edge_tts", object())
    monkeypatch.setattr(voice, "_edge_bytes", fake_edge_bytes)
    monkeypatch.setattr(voice, "_play_mp3", lambda audio: played.append(audio))
    monkeypatch.delenv("JARVIS_FAST_VOICE", raising=False)

    cfg = {
        "edge_voice": "en-US-EmmaMultilingualNeural",
        "edge_rate": "+0%",
        "edge_volume": "+0%",
        "edge_pitch": "+0Hz",
        "edge_persistent_cache_enabled": True,
    }
    voice._cache.clear()
    voice._speak_edge("Hello", cfg)
    voice._cache.clear()
    voice._speak_edge("Hello", cfg)

    assert calls == ["Hello"]
    assert played == [b"cached-mp3", b"cached-mp3"]


def test_warm_edge_voice_cache_generates_without_playing(monkeypatch):
    calls = []
    played = []

    def fake_edge_audio(text, cfg):
        calls.append((text, cfg))
        return b"mp3"

    monkeypatch.setattr(voice, "_is_online", lambda: True)
    monkeypatch.setattr(voice, "edge_tts", object())
    monkeypatch.setattr(voice, "reload_config", lambda: {"edge_voice": "en-US-EmmaMultilingualNeural"})
    monkeypatch.setattr(voice, "_edge_audio", fake_edge_audio)
    monkeypatch.setattr(voice, "_play_mp3", lambda audio: played.append(audio))

    warmed = voice.warm_edge_voice_cache(["Done.", "Okay."])

    assert warmed == ["Done.", "Okay."]
    assert [text for text, _cfg in calls] == ["Done.", "Okay."]
    assert played == []


def test_local_voice_options_lists_pyttsx3_voices(monkeypatch):
    class Engine:
        def getProperty(self, name):
            assert name == "voices"
            return [FakeLocalVoice("voice-id", "Zira", [b"\x05en_US"], "female")]

    monkeypatch.setattr(voice, "_get_engine", lambda: Engine())

    options = voice.local_voice_options()

    assert options == [
        {
            "index": "0",
            "id": "voice-id",
            "name": "Zira",
            "languages": "en_US",
            "gender": "female",
            "age": "",
        }
    ]


def test_pyttsx3_voice_id_can_match_name_fragment(monkeypatch):
    calls = []

    class Engine:
        def getProperty(self, name):
            assert name == "voices"
            return [
                FakeLocalVoice("voice-zira", "Microsoft Zira Desktop"),
                FakeLocalVoice("voice-david", "Microsoft David Desktop"),
            ]

        def setProperty(self, name, value):
            calls.append((name, value))

        def say(self, text):
            calls.append(("say", text))

        def runAndWait(self):
            calls.append(("run", True))

    monkeypatch.setattr(voice, "_get_engine", lambda: Engine())
    monkeypatch.setattr(voice, "reload_config", lambda: {"pyttsx3_voice_id": "david", "voice_rate": 200, "voice_volume": 0.7})

    voice._speak_pyttsx3("Hello")

    assert ("voice", "voice-david") in calls
    assert ("rate", 200) in calls
    assert ("volume", 0.7) in calls
