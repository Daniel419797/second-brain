from pathlib import Path
import json
from types import SimpleNamespace

from input import speech_to_text as stt


class FakeStream:
    def __init__(self, frames):
        self.frames = list(frames)

    def read(self, frames, exception_on_overflow=False):
        return self.frames.pop(0) if self.frames else b"\x00\x00" * frames


class FakeVad:
    def __init__(self, decisions):
        self.decisions = list(decisions)

    def is_speech(self, frame, sample_rate):
        return self.decisions.pop(0) if self.decisions else False


class FakeArray:
    def astype(self, dtype):
        return self

    def __truediv__(self, other):
        return self


class FakeNumpy:
    int16 = "int16"
    float32 = "float32"

    @staticmethod
    def frombuffer(audio_bytes, dtype):
        return FakeArray()


class FakeModel:
    def transcribe(self, audio, language, fp16, **kwargs):
        assert language == "en"
        assert fp16 is False
        return {"text": " Hello Jarvis "}


class FakeWakeNameModel:
    def transcribe(self, audio, language, fp16, **kwargs):
        return {"text": " Friday, how are you doing "}


class FakeFasterSegment:
    def __init__(self, text):
        self.text = text


class FakeFasterModel:
    def transcribe(self, audio, **kwargs):
        assert kwargs["vad_filter"] is True
        assert kwargs["hotwords"] == "Friday Gmail"
        assert kwargs["without_timestamps"] is True
        assert kwargs["max_new_tokens"] == 96
        assert kwargs["repetition_penalty"] == 1.05
        assert kwargs["no_repeat_ngram_size"] == 3
        return [FakeFasterSegment(" Friday open Gmail ")], object()


class FakeFasterWhisper:
    def __init__(self):
        self.calls = []

    def __call__(self, model_name, **kwargs):
        self.calls.append((model_name, kwargs))
        return FakeFasterModel()


class FlakyWhisper:
    def __init__(self):
        self.calls = []

    def load_model(self, name):
        self.calls.append(name)
        if len(self.calls) == 1:
            raise RuntimeError("SHA256 checksum does not match")
        return FakeModel()


class FailingThenFallbackWhisper:
    def __init__(self):
        self.calls = []

    def load_model(self, name):
        self.calls.append(name)
        if name == "small.en":
            raise RuntimeError("SHA256 checksum does not match")
        return FakeModel()


class FakeDeepgramTimeout(Exception):
    pass


class FakeDeepgramSocket:
    def __init__(self, messages):
        self.messages = list(messages)
        self.binary = []
        self.text = []
        self.closed = False
        self.url = ""
        self.headers = []

    def recv(self):
        if self.messages:
            return self.messages.pop(0)
        raise FakeDeepgramTimeout("timed out")

    def send_binary(self, chunk):
        self.binary.append(chunk)

    def send(self, payload, opcode=None):
        if opcode is not None:
            self.binary.append(payload)
        else:
            self.text.append(payload)

    def close(self):
        self.closed = True


class FakeDeepgramWebSocketModule:
    WebSocketTimeoutException = FakeDeepgramTimeout

    class ABNF:
        OPCODE_BINARY = 2

    def __init__(self, messages):
        self.messages = messages
        self.connections = []

    def create_connection(self, url, header, timeout):
        socket = FakeDeepgramSocket(self.messages)
        socket.url = url
        socket.headers = header
        socket.timeout = timeout
        self.connections.append(socket)
        return socket


def test_record_until_silence_returns_empty_for_no_speech():
    vad = FakeVad([False] * stt.MAX_FRAMES)
    stream = FakeStream([b"\x00\x00" * stt.FRAME_SAMPLES] * stt.MAX_FRAMES)

    assert stt.record_until_silence(vad, stream) == b""


def test_transcribe_returns_lowercase_text(monkeypatch):
    monkeypatch.setattr(stt, "np", FakeNumpy)

    assert stt.transcribe(b"\x01\x00" * 10, model=FakeModel()) == "Hello Jarvis"


def test_faster_whisper_backend_transcribes_with_vad_and_hotwords(monkeypatch):
    fake_faster = FakeFasterWhisper()

    def fake_config(key, default=None):
        values = {
            "stt_backend": "faster-whisper",
            "stt_model": "medium.en",
            "stt_device": "cpu",
            "stt_compute_type": "int8",
            "stt_cpu_threads": 4,
            "stt_num_workers": 1,
            "stt_vad_filter": True,
            "stt_vad_min_silence_ms": 500,
            "stt_vad_speech_pad_ms": 450,
            "stt_hotwords": "Friday Gmail",
            "stt_without_timestamps": True,
            "stt_max_new_tokens": 96,
            "stt_repetition_penalty": 1.05,
            "stt_no_repeat_ngram_size": 3,
        }
        return values.get(key, default)

    monkeypatch.setattr(stt, "np", FakeNumpy)
    monkeypatch.setattr(stt, "FasterWhisperModel", fake_faster)
    monkeypatch.setattr(stt, "config_value", fake_config)

    model = stt.load_model()

    assert isinstance(model, FakeFasterModel)
    assert stt.transcribe(b"\x01\x00" * 10) == "open Gmail"
    assert fake_faster.calls[0][0] == "medium.en"


def test_groq_backend_transcribes_via_api(monkeypatch):
    calls = []

    def fake_config(key, default=None):
        values = {
            "stt_groq_base_url": "https://api.groq.com/openai/v1",
            "stt_groq_api_key_env": "GROQ_API_KEY",
            "stt_groq_timeout_seconds": 12.0,
            "stt_groq_response_format": "text",
            "stt_groq_prompt": "Friday commands",
            "stt_language": "en",
            "stt_temperature": 0.0,
            "stt_ignore_captures": "ok,okay,hey,in,you",
            "stt_short_command_repairs": "",
            "stt_phrase_corrections": "",
            "stt_trailing_junk_words": "",
        }
        return values.get(key, default)

    def fake_post(url, headers, data, files, timeout):
        calls.append((url, headers, data, files["file"][0], timeout))
        return SimpleNamespace(status_code=200, text=" Friday can you code ", json=lambda: {"text": "Friday can you code"})

    monkeypatch.setenv("GROQ_API_KEY", "gsk_test")
    monkeypatch.setattr(stt, "config_value", fake_config)
    monkeypatch.setattr(stt.requests, "post", fake_post)

    model = {"backend": "groq", "name": "whisper-large-v3"}

    assert stt.transcribe(b"\x01\x00" * 10, model=model, strip_wake=False) == "Friday can you code"
    assert calls[0][0] == "https://api.groq.com/openai/v1/audio/transcriptions"
    assert calls[0][1]["Authorization"] == "Bearer gsk_test"
    assert calls[0][2]["model"] == "whisper-large-v3"
    assert calls[0][3] == "audio.wav"
    assert calls[0][4] == 12.0


def test_groq_prompt_is_omitted_when_unconfigured(monkeypatch):
    calls = []

    def fake_config(key, default=None):
        values = {
            "stt_groq_base_url": "https://api.groq.com/openai/v1",
            "stt_groq_api_key_env": "GROQ_API_KEY",
            "stt_groq_timeout_seconds": 12.0,
            "stt_groq_response_format": "text",
            "stt_groq_prompt": "",
            "stt_language": "en",
            "stt_temperature": 0.0,
            "stt_ignore_captures": "ok,okay,hey,in,you",
            "stt_short_command_repairs": "",
            "stt_phrase_corrections": "",
            "stt_trailing_junk_words": "",
        }
        return values.get(key, default)

    def fake_post(url, headers, data, files, timeout):
        calls.append(data)
        return SimpleNamespace(status_code=200, text=" Friday what time is it ", json=lambda: {"text": "Friday what time is it"})

    monkeypatch.setenv("GROQ_API_KEY", "gsk_test")
    monkeypatch.setattr(stt, "config_value", fake_config)
    monkeypatch.setattr(stt.requests, "post", fake_post)

    assert stt.transcribe(b"\x01\x00" * 10, model={"backend": "groq", "name": "whisper-large-v3"}, strip_wake=False) == "Friday what time is it"
    assert "prompt" not in calls[0]


def test_deepgram_backend_streams_audio_via_websocket(monkeypatch):
    messages = [
        json.dumps(
            {
                "type": "Results",
                "is_final": True,
                "speech_final": True,
                "channel": {
                    "alternatives": [
                        {"transcript": "Friday open Chrome", "confidence": 0.91}
                    ]
                },
            }
        )
    ]
    fake_websocket = FakeDeepgramWebSocketModule(messages)

    def fake_config(key, default=None):
        values = {
            "stt_deepgram_listen_url": "wss://api.deepgram.com/v1/listen",
            "stt_deepgram_api_key_env": "DEEPGRAM_API_KEY",
            "stt_deepgram_timeout_seconds": 12.0,
            "stt_deepgram_finalize_timeout_seconds": 0.2,
            "stt_deepgram_chunk_ms": 100,
            "stt_deepgram_interim_results": True,
            "stt_deepgram_smart_format": True,
            "stt_deepgram_punctuate": True,
            "stt_deepgram_vad_events": True,
            "stt_deepgram_mip_opt_out": False,
            "stt_deepgram_endpointing_ms": 350,
            "stt_deepgram_utterance_end_ms": 1000,
            "stt_deepgram_keywords": "",
            "stt_deepgram_keyterms": "Friday,Chrome",
            "stt_language": "en",
            "stt_ignore_captures": "ok,okay,hey,in,you",
            "stt_short_command_repairs": "",
            "stt_phrase_corrections": "",
            "stt_trailing_junk_words": "",
        }
        return values.get(key, default)

    monkeypatch.setenv("DEEPGRAM_API_KEY", "dg_test")
    monkeypatch.setattr(stt, "websocket", fake_websocket)
    monkeypatch.setattr(stt, "config_value", fake_config)

    text = stt.transcribe(b"\x01\x00" * stt.SAMPLE_RATE, model={"backend": "deepgram", "name": "nova-3"}, strip_wake=False)

    socket = fake_websocket.connections[0]
    assert text == "Friday open Chrome"
    assert socket.headers == ["Authorization: Token dg_test"]
    assert "model=nova-3" in socket.url
    assert "encoding=linear16" in socket.url
    assert "interim_results=true" in socket.url
    assert "keyterm=Friday" in socket.url
    assert socket.binary
    assert any('"Finalize"' in message for message in socket.text)
    assert socket.closed is True
    assert stt._last_transcribe_confidence == 0.91


def test_deepgram_backend_uses_realtime_recording_path(monkeypatch):
    calls = []

    def fake_streaming(model, *, initial_audio=b"", strip_wake=True):
        calls.append((model, initial_audio, strip_wake))
        return "Friday hello", b"audio"

    monkeypatch.setattr(stt, "_record_and_transcribe_deepgram_streaming", fake_streaming)
    monkeypatch.setattr(stt, "config_value", lambda key, default=None: True if key == "stt_deepgram_realtime_enabled" else default)

    assert stt.record_and_transcribe_with_audio(model={"backend": "deepgram", "name": "nova-3"}, initial_audio=b"seed", strip_wake=False) == ("Friday hello", b"audio")
    assert calls == [({"backend": "deepgram", "name": "nova-3"}, b"seed", False)]


def test_load_model_fallback_can_switch_backend_prefix(monkeypatch):
    calls = []

    def fake_config(key, default=None):
        values = {
            "stt_backend": "groq",
            "stt_model": "whisper-large-v3",
            "stt_fallback_model": "windows-speech",
        }
        return values.get(key, default)

    def fake_load_backend(backend, model_name):
        calls.append((backend, model_name))
        if backend == "groq":
            raise RuntimeError("missing key")
        return {"backend": backend, "name": model_name}

    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.setattr(stt, "config_value", fake_config)
    monkeypatch.setattr(stt, "_load_backend_model", fake_load_backend)

    model = stt.load_model()

    assert model == {"backend": "windows-speech", "name": "windows-speech"}
    assert calls == [("groq", "whisper-large-v3"), ("windows-speech", "windows-speech")]


def test_windows_speech_backend_transcribes_with_system_speech(monkeypatch):
    def fake_run(*args, **kwargs):
        return SimpleNamespace(returncode=0, stdout='{"text":"Friday what time is it","confidence":0.82}', stderr="")

    monkeypatch.setattr(stt.subprocess, "run", fake_run)
    monkeypatch.setattr(stt, "config_value", lambda key, default=None: default)

    assert stt.transcribe(b"\x01\x00" * 10, model={"backend": "windows-speech"}) == "what time is it"
    assert stt._last_transcribe_confidence == 0.82


def test_windows_speech_backend_discards_low_confidence_dictation(monkeypatch):
    def fake_run(*args, **kwargs):
        return SimpleNamespace(returncode=0, stdout='{"text":"to leading","confidence":0.12,"grammar":"dictation"}', stderr="")

    def fake_config(key, default=None):
        if key == "stt_windows_min_confidence":
            return 0.35
        return default

    monkeypatch.setattr(stt.subprocess, "run", fake_run)
    monkeypatch.setattr(stt, "config_value", fake_config)

    assert stt.transcribe(b"\x01\x00" * 10, model={"backend": "windows-speech"}, strip_wake=False) == ""


def test_windows_speech_backend_repairs_common_friday_miss(monkeypatch):
    def fake_run(*args, **kwargs):
        return SimpleNamespace(returncode=0, stdout='{"text":"Friday how leading","confidence":0.17,"grammar":"dictation"}', stderr="")

    def fake_config(key, default=None):
        if key == "stt_windows_min_confidence":
            return 0.35
        return default

    monkeypatch.setattr(stt.subprocess, "run", fake_run)
    monkeypatch.setattr(stt, "config_value", fake_config)

    assert stt.transcribe(b"\x01\x00" * 10, model={"backend": "windows-speech"}, strip_wake=False) == "Friday how are you doing"


def test_windows_speech_low_confidence_can_fallback_to_whisper(monkeypatch):
    calls = []

    def fake_transcribe(audio, model=None, model_name=None, strip_wake=True):
        calls.append(model_name or "primary")
        if model_name == "faster-whisper:distil-medium.en":
            return "Friday how are you doing"
        stt._last_transcribe_rejected_low_confidence = True
        stt._last_transcribe_raw_text = "Friday how leading"
        return ""

    def fake_config(key, default=None):
        values = {
            "stt_retry_on_blank": True,
            "stt_windows_fallback_enabled": True,
            "stt_windows_fallback_policy": "low_confidence",
            "stt_windows_fallback_min_audio_seconds": 0.1,
            "stt_fallback_model": "faster-whisper:distil-medium.en",
            "stt_model": "windows-speech",
        }
        return values.get(key, default)

    monkeypatch.setattr(stt, "transcribe", fake_transcribe)
    monkeypatch.setattr(stt, "config_value", fake_config)
    monkeypatch.setattr(stt, "_model_backend", "windows-speech")

    assert stt.transcribe_best_effort(b"\x01\x00" * stt.SAMPLE_RATE) == "Friday how are you doing"
    assert calls == ["primary", "faster-whisper:distil-medium.en"]


def test_groq_blank_does_not_retry_local_fallback_by_default(monkeypatch):
    calls = []

    def fake_transcribe(audio, model=None, model_name=None, strip_wake=True):
        calls.append(model_name or "primary")
        return ""

    def fake_config(key, default=None):
        values = {
            "stt_retry_on_blank": True,
            "stt_groq_fallback_on_blank": False,
            "stt_fallback_model": "whisper-cpp:ggml-base.en-q5_1.bin",
        }
        return values.get(key, default)

    monkeypatch.setattr(stt, "transcribe", fake_transcribe)
    monkeypatch.setattr(stt, "config_value", fake_config)
    monkeypatch.setattr(stt, "_model_backend", "groq")

    assert stt.transcribe_best_effort(b"\x01\x00" * 10) == ""
    assert calls == ["primary"]


def test_blank_retry_skips_same_resolved_fallback_model(monkeypatch):
    calls = []

    def fake_transcribe(audio, model=None, model_name=None, strip_wake=True):
        calls.append(model_name or "primary")
        return ""

    def fake_config(key, default=None):
        values = {
            "stt_retry_on_blank": True,
            "stt_fallback_model": "whisper-cpp:ggml-base.en-q5_1.bin",
        }
        return values.get(key, default)

    monkeypatch.setattr(stt, "transcribe", fake_transcribe)
    monkeypatch.setattr(stt, "config_value", fake_config)
    monkeypatch.setattr(stt, "_model_backend", "whisper-cpp")
    monkeypatch.setattr(stt, "_model_name", "ggml-base.en-q5_1.bin")

    assert stt.transcribe_best_effort(b"\x01\x00" * 10) == ""
    assert calls == ["primary"]


def test_windows_speech_fallback_can_be_limited_to_addressed(monkeypatch):
    def fake_config(key, default=None):
        values = {
            "stt_windows_fallback_enabled": True,
            "stt_windows_fallback_policy": "addressed",
            "attention_names": "friday,computer",
        }
        return values.get(key, default)

    monkeypatch.setattr(stt, "config_value", fake_config)
    monkeypatch.setattr(stt, "_last_transcribe_rejected_low_confidence", True)
    monkeypatch.setattr(stt, "_last_transcribe_raw_text", "to leading")
    assert stt._windows_whisper_fallback_should_run(b"\x01\x00" * stt.SAMPLE_RATE) is False

    monkeypatch.setattr(stt, "_last_transcribe_raw_text", "Friday leading")
    assert stt._windows_whisper_fallback_should_run(b"\x01\x00" * stt.SAMPLE_RATE) is True


def test_windows_speech_fuzzy_repairs_seen_live_misses(monkeypatch):
    monkeypatch.setattr(stt, "config_value", lambda key, default=None: default)

    assert stt._repair_windows_transcript("Friday relating") == "Friday how are you doing"
    assert stt._repair_windows_transcript("Friday holly Gore") == "Friday how are you doing"
    assert stt._repair_windows_transcript("totally unrelated phrase") == "totally unrelated phrase"


def test_windows_command_phrases_include_named_common_commands(monkeypatch):
    def fake_config(key, default=None):
        if key == "attention_names":
            return "friday,freddie"
        if key == "stt_windows_command_phrases":
            return "how are you doing,what time is it"
        return default

    monkeypatch.setattr(stt, "config_value", fake_config)

    phrases = stt._windows_command_phrases()

    assert "friday how are you doing" in [phrase.lower() for phrase in phrases]
    assert "hey freddie what time is it" in [phrase.lower() for phrase in phrases]


def test_backend_model_prefix_can_force_faster_whisper(monkeypatch):
    fake_faster = FakeFasterWhisper()

    def fake_config(key, default=None):
        values = {
            "stt_backend": "windows-speech",
            "stt_device": "cpu",
            "stt_compute_type": "int8",
            "stt_cpu_threads": 4,
            "stt_num_workers": 1,
        }
        return values.get(key, default)

    monkeypatch.setattr(stt, "FasterWhisperModel", fake_faster)
    monkeypatch.setattr(stt, "config_value", fake_config)

    model = stt.load_model("faster-whisper:small.en")

    assert isinstance(model, FakeFasterModel)
    assert fake_faster.calls[0][0] == "small.en"


def test_backend_model_prefix_can_force_whisper_cpp(monkeypatch, tmp_path):
    cli_path = tmp_path / "whisper-cli.exe"
    model_path = tmp_path / "ggml-small.en-q5_1.bin"
    cli_path.write_text("", encoding="utf-8")
    model_path.write_text("", encoding="utf-8")

    def fake_config(key, default=None):
        values = {
            "stt_backend": "openai",
            "stt_whisper_cpp_cli_path": str(cli_path),
            "stt_whisper_cpp_model_path": str(model_path),
            "stt_whisper_cpp_threads": 4,
        }
        return values.get(key, default)

    monkeypatch.setattr(stt, "config_value", fake_config)

    model = stt.load_model("whisper-cpp:ggml-small.en-q5_1.bin")

    assert model["backend"] == "whisper-cpp"
    assert model["cli_path"] == cli_path
    assert model["model_path"] == model_path


def test_whisper_cpp_backend_transcribes_via_cli(monkeypatch, tmp_path):
    cli_path = tmp_path / "whisper-cli.exe"
    model_path = tmp_path / "ggml-small.en-q5_1.bin"
    cli_path.write_text("", encoding="utf-8")
    model_path.write_text("", encoding="utf-8")
    calls = []

    def fake_config(key, default=None):
        values = {
            "stt_language": "en",
            "stt_beam_size": 1,
            "stt_best_of": 1,
            "stt_temperature": 0.0,
            "stt_no_speech_threshold": 0.6,
            "stt_without_timestamps": True,
            "stt_whisper_cpp_no_prints": True,
            "stt_whisper_cpp_no_gpu": True,
            "stt_whisper_cpp_suppress_non_speech": True,
            "stt_whisper_cpp_timeout_seconds": 5.0,
            "stt_initial_prompt": "",
            "stt_whisper_cpp_extra_args": "",
        }
        return values.get(key, default)

    def fake_run(command, **kwargs):
        calls.append(command)
        output_base = Path(command[command.index("-of") + 1])
        output_base.with_suffix(".txt").write_text("[00:00:00.000 --> 00:00:01.000] Friday how are you doing\n", encoding="utf-8")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(stt, "config_value", fake_config)
    monkeypatch.setattr(stt.subprocess, "run", fake_run)

    model = {"backend": "whisper-cpp", "cli_path": cli_path, "model_path": model_path, "threads": 4}

    assert stt.transcribe(b"\x01\x00" * 10, model=model, strip_wake=False) == "Friday how are you doing"
    assert calls[0][0] == str(cli_path)
    assert "-otxt" in calls[0]
    assert "-nt" in calls[0]
    assert "-np" in calls[0]
    assert "-sns" in calls[0]


def test_transcribe_can_preserve_wake_phrase_for_attention(monkeypatch):
    monkeypatch.setattr(stt, "np", FakeNumpy)

    assert stt.transcribe(b"\x01\x00" * 10, model=FakeWakeNameModel()) == "how are you doing"
    assert stt.transcribe(b"\x01\x00" * 10, model=FakeWakeNameModel(), strip_wake=False) == "Friday, how are you doing"


def test_strip_wake_phrase_removes_prefix():
    assert stt.strip_wake_phrase("Hey Jarvis, open Chrome") == "open Chrome"


def test_strip_wake_phrase_removes_common_mishearing():
    assert stt.strip_wake_phrase("Hey, Jeff.") == ""
    assert stt.strip_wake_phrase("Hey Jeff, what time is it?") == "what time is it"


def test_clean_transcript_removes_configured_trailing_junk(monkeypatch):
    monkeypatch.setattr(stt, "config_value", lambda key, default=None: "city,see" if key == "stt_trailing_junk_words" else default)

    assert stt.clean_transcript("How are you doing city") == "How are you doing"
    assert stt.clean_transcript("open city") == "open city"


def test_clean_transcript_drops_ignored_filler(monkeypatch):
    def fake_config(key, default=None):
        if key == "stt_ignore_captures":
            return "ok,okay,hey,in,you"
        return default

    monkeypatch.setattr(stt, "config_value", fake_config)

    assert stt.clean_transcript("you") == ""


def test_clean_transcript_drops_prompt_hallucination(monkeypatch):
    def fake_config(key, default=None):
        if key == "stt_hallucination_phrases":
            return "this is a spoken command to jarvis,a windows personal assistant,common words include"
        return default

    monkeypatch.setattr(stt, "config_value", fake_config)

    assert stt.clean_transcript("This is a spoken command to Jarvis a Windows personal assistant") == ""


def test_clean_transcript_drops_groq_prompt_leak(monkeypatch):
    monkeypatch.setattr(stt, "config_value", lambda key, default=None: default)

    leaked = "Audio is a short command for an AI assistant named Friday, Chrome, Gmail, VS Code, camera, file"

    assert stt.clean_transcript(leaked) == ""


def test_clean_transcript_drops_common_silence_hallucinations(monkeypatch):
    monkeypatch.setattr(stt, "config_value", lambda key, default=None: default)

    assert stt.clean_transcript("Thank you for watching.") == ""
    assert stt.clean_transcript("CREDITS") == ""


def test_clean_transcript_repairs_short_command_after_wake_name(monkeypatch):
    def fake_config(key, default=None):
        values = {
            "stt_short_command_repairs": "coyote=can you code;and you could=can you code",
            "wake_word_strip_phrases": "friday,hey friday",
            "attention_names": "friday",
        }
        return values.get(key, default)

    monkeypatch.setattr(stt, "config_value", fake_config)

    assert stt.clean_transcript("Friday coyote") == "Friday can you code"
    assert stt.clean_transcript("Friday and you could") == "Friday can you code"


def test_clean_transcript_repairs_exact_short_command_only(monkeypatch):
    def fake_config(key, default=None):
        if key == "stt_short_command_repairs":
            return "coyote=can you code;and you could=can you code;what this=what time is it"
        return default

    monkeypatch.setattr(stt, "config_value", fake_config)

    assert stt.clean_transcript("and you could") == "can you code"
    assert stt.clean_transcript("what this") == "what time is it"
    assert stt.clean_transcript("what is a coyote") == "what is a coyote"


def test_clean_transcript_corrects_gmail_mishearing(monkeypatch):
    def fake_config(key, default=None):
        if key == "stt_phrase_corrections":
            return "open gym=open gmail;open g mail=open gmail"
        return default

    monkeypatch.setattr(stt, "config_value", fake_config)

    assert stt.clean_transcript("open gym") == "open gmail"


def test_clean_transcript_corrects_file_question_mishearing(monkeypatch):
    def fake_config(key, default=None):
        if key == "stt_phrase_corrections":
            return "what does the fire=what does the file"
        return default

    monkeypatch.setattr(stt, "config_value", fake_config)

    assert stt.clean_transcript("what does the fire say") == "what does the file say"


def test_prompt_hallucination_does_not_retry_fallback(monkeypatch):
    calls = []

    def fake_transcribe(audio, model=None, model_name=None, strip_wake=True):
        calls.append(model_name or "primary")
        stt._last_transcribe_was_hallucination = True
        return ""

    monkeypatch.setattr(stt, "transcribe", fake_transcribe)
    monkeypatch.setattr(stt, "config_value", lambda key, default=None: True if key == "stt_retry_on_blank" else default)

    assert stt.transcribe_best_effort(b"\x01\x00" * 10) == ""
    assert calls == ["primary"]


def test_load_model_retries_checksum_failure(monkeypatch):
    fake = FlakyWhisper()
    monkeypatch.setattr(stt, "whisper", fake)
    monkeypatch.setattr(stt, "_remove_model_cache", lambda model_name: None)
    def fake_config(key, default=None):
        if key == "stt_backend":
            return "openai"
        if key == "stt_retry_corrupt_download":
            return True
        return default

    monkeypatch.setattr(stt, "config_value", fake_config)

    assert isinstance(stt.load_model("small.en"), FakeModel)
    assert fake.calls == ["small.en", "small.en"]


def test_load_model_falls_back_after_failed_retry(monkeypatch):
    fake = FailingThenFallbackWhisper()

    def fake_config(key, default=None):
        values = {
            "stt_backend": "openai",
            "stt_model": "small.en",
            "stt_fallback_model": "base.en",
            "stt_retry_corrupt_download": True,
        }
        return values.get(key, default)

    monkeypatch.setattr(stt, "whisper", fake)
    monkeypatch.setattr(stt, "_remove_model_cache", lambda model_name: None)
    monkeypatch.setattr(stt, "config_value", fake_config)

    assert isinstance(stt.load_model(), FakeModel)
    assert fake.calls == ["small.en", "small.en", "base.en"]
