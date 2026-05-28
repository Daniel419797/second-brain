from types import SimpleNamespace

import jarvis


def _args(**overrides):
    base = {"continuous": False, "listen_loop": False, "wake_word": False}
    base.update(overrides)
    return SimpleNamespace(**base)


def test_voice_activation_defaults_to_continuous():
    assert jarvis._voice_activation_mode(_args(), {}) == "continuous"


def test_voice_activation_can_force_wake_word():
    assert jarvis._voice_activation_mode(_args(wake_word=True), {"voice_activation_mode": "continuous"}) == "wake_word"
    assert jarvis._voice_activation_mode(_args(), {"voice_activation_mode": "wake"}) == "wake_word"


def test_voice_activation_listen_loop_forces_continuous():
    assert jarvis._voice_activation_mode(_args(listen_loop=True), {"voice_activation_mode": "wake_word"}) == "continuous"


def test_fast_voice_pauses_background_workers_by_default(monkeypatch):
    logs = []
    started = []
    monkeypatch.setattr(jarvis, "load_config", lambda: {"v2_start_background_workers_in_fast_voice": False})
    monkeypatch.setattr(jarvis.background_agents, "start_workers", lambda: started.append(True) or 1)
    monkeypatch.setattr(jarvis, "log", lambda level, message: logs.append((level, message)))

    jarvis._start_background_agents(SimpleNamespace(fast_voice=True))

    assert started == []
    assert "paused for fast voice" in logs[0][1]


def test_fast_voice_does_not_force_robotic_local_tts_by_default(monkeypatch):
    env = {}
    monkeypatch.setattr(jarvis.os, "environ", env)
    monkeypatch.setattr(jarvis, "_parse_args", lambda: SimpleNamespace(fast_voice=True, audio_devices=True, debug=False))
    monkeypatch.setattr(jarvis, "load_dotenv", lambda: None)
    monkeypatch.setattr(jarvis, "ensure_runtime_dirs", lambda: None)
    monkeypatch.setattr(jarvis, "load_config", lambda: {"fast_voice_use_local_tts": False, "log_level": "INFO"})
    monkeypatch.setattr(jarvis, "set_log_level", lambda level: None)
    monkeypatch.setattr(jarvis, "_print_audio_devices", lambda: None)

    assert jarvis.main() == 0
    assert env["JARVIS_FAST_VOICE"] == "1"
    assert "JARVIS_VOICE_BACKEND" not in env


def test_fast_voice_can_still_force_local_tts_when_configured(monkeypatch):
    env = {}
    monkeypatch.setattr(jarvis.os, "environ", env)
    monkeypatch.setattr(jarvis, "_parse_args", lambda: SimpleNamespace(fast_voice=True, audio_devices=True, debug=False))
    monkeypatch.setattr(jarvis, "load_dotenv", lambda: None)
    monkeypatch.setattr(jarvis, "ensure_runtime_dirs", lambda: None)
    monkeypatch.setattr(jarvis, "load_config", lambda: {"fast_voice_use_local_tts": True, "log_level": "INFO"})
    monkeypatch.setattr(jarvis, "set_log_level", lambda level: None)
    monkeypatch.setattr(jarvis, "_print_audio_devices", lambda: None)

    assert jarvis.main() == 0
    assert env["JARVIS_FAST_VOICE"] == "1"
    assert env["JARVIS_VOICE_BACKEND"] == "pyttsx3"


def test_voice_preview_exits_before_env_validation(monkeypatch):
    calls = []
    monkeypatch.setattr(jarvis, "_parse_args", lambda: SimpleNamespace(
        fast_voice=False,
        audio_devices=False,
        mic_test=False,
        voice_preview=True,
        voice_preview_text="Hi Friday.",
        debug=False,
    ))
    monkeypatch.setattr(jarvis, "load_dotenv", lambda: None)
    monkeypatch.setattr(jarvis, "ensure_runtime_dirs", lambda: None)
    monkeypatch.setattr(jarvis, "load_config", lambda: {"log_level": "INFO"})
    monkeypatch.setattr(jarvis, "set_log_level", lambda level: None)
    monkeypatch.setattr(jarvis, "_voice_preview", lambda text: calls.append(text) or 0)
    monkeypatch.setattr(jarvis, "_validate_env", lambda args: (_ for _ in ()).throw(AssertionError("should not validate")))

    assert jarvis.main() == 0
    assert calls == ["Hi Friday."]


def test_local_voices_exits_before_env_validation(monkeypatch):
    calls = []
    monkeypatch.setattr(jarvis, "_parse_args", lambda: SimpleNamespace(
        fast_voice=False,
        audio_devices=False,
        mic_test=False,
        local_voices=True,
        debug=False,
    ))
    monkeypatch.setattr(jarvis, "load_dotenv", lambda: None)
    monkeypatch.setattr(jarvis, "ensure_runtime_dirs", lambda: None)
    monkeypatch.setattr(jarvis, "load_config", lambda: {"log_level": "INFO"})
    monkeypatch.setattr(jarvis, "set_log_level", lambda level: None)
    monkeypatch.setattr(jarvis, "_print_local_voices", lambda: calls.append(True) or 0)
    monkeypatch.setattr(jarvis, "_validate_env", lambda args: (_ for _ in ()).throw(AssertionError("should not validate")))

    assert jarvis.main() == 0
    assert calls == [True]


def test_voice_warmup_exits_before_env_validation(monkeypatch):
    env = {}
    calls = []
    monkeypatch.setattr(jarvis.os, "environ", env)
    monkeypatch.setattr(jarvis, "_parse_args", lambda: SimpleNamespace(
        fast_voice=True,
        audio_devices=False,
        mic_test=False,
        voice_preview=False,
        voice_warmup=True,
        debug=False,
    ))
    monkeypatch.setattr(jarvis, "load_dotenv", lambda: None)
    monkeypatch.setattr(jarvis, "ensure_runtime_dirs", lambda: None)
    monkeypatch.setattr(jarvis, "load_config", lambda: {"fast_voice_use_local_tts": False, "log_level": "INFO"})
    monkeypatch.setattr(jarvis, "set_log_level", lambda level: None)
    monkeypatch.setattr(jarvis, "_voice_warmup", lambda: calls.append(True) or 0)
    monkeypatch.setattr(jarvis, "_validate_env", lambda args: (_ for _ in ()).throw(AssertionError("should not validate")))

    assert jarvis.main() == 0
    assert calls == [True]
    assert env["JARVIS_FAST_VOICE"] == "1"


def test_stt_benchmark_models_defaults_to_current_first():
    models = jarvis._stt_benchmark_models(
        None,
        {
            "stt_model": "large-v3-turbo",
            "stt_benchmark_models": "medium.en,large-v3-turbo,distil-medium.en",
        },
    )

    assert models == ["large-v3-turbo", "medium.en", "distil-medium.en"]


def test_stt_benchmark_models_respects_custom_order():
    models = jarvis._stt_benchmark_models("distil-medium.en, small.en, distil-medium.en", {"stt_model": "medium.en"})

    assert models == ["distil-medium.en", "small.en"]


def test_word_error_rate_scores_transcript_against_expected():
    assert jarvis._word_error_rate("Friday open Chrome", "Friday open Chrome") == 0
    assert jarvis._word_error_rate("Friday open", "Friday open Chrome") == 1 / 3
    assert jarvis._word_error_rate("Friday what is the time?", "Friday what time is it") == 0
    assert jarvis._word_error_rate("anything", "") is None


def test_attention_accepts_named_assistant(monkeypatch):
    monkeypatch.setattr(
        jarvis,
        "load_config",
        lambda: {
            "attention_gate_enabled": True,
            "attention_mode": "smart",
            "attention_names": "jarvis,jervis",
        },
    )

    accepted, cleaned, reason = jarvis._attention_decision("Jarvis, what is your name?")

    assert accepted is True
    assert cleaned == "what is your name"
    assert reason == "name"


def test_attention_ignores_side_conversation(monkeypatch):
    monkeypatch.setattr(
        jarvis,
        "load_config",
        lambda: {
            "attention_gate_enabled": True,
            "attention_mode": "smart",
            "attention_names": "jarvis",
            "attention_side_conversation_phrases": "i said,he said",
        },
    )

    accepted, _cleaned, reason = jarvis._attention_decision("I said can you build software")

    assert accepted is False
    assert reason == "side_cue"


def test_attention_followup_accepts_without_name(monkeypatch):
    monkeypatch.setattr(jarvis, "load_config", lambda: {"attention_gate_enabled": True})

    accepted, cleaned, reason = jarvis._attention_decision("My name is Daniel", expect_reply=True)

    assert accepted is True
    assert cleaned == "My name is Daniel"
    assert reason == "followup"


def test_attention_strict_can_recover_low_risk_action(monkeypatch):
    monkeypatch.setattr(
        jarvis,
        "load_config",
        lambda: {
            "attention_gate_enabled": True,
            "attention_mode": "name",
            "attention_names": "friday",
            "attention_action_recovery_enabled": True,
        },
    )

    accepted, cleaned, reason = jarvis._attention_decision("open Gmail")

    assert accepted is True
    assert cleaned == "open Gmail"
    assert reason == "action_recovery"


def test_attention_strict_can_recover_open_camera(monkeypatch):
    monkeypatch.setattr(
        jarvis,
        "load_config",
        lambda: {
            "attention_gate_enabled": True,
            "attention_mode": "name",
            "attention_names": "friday",
            "attention_action_recovery_enabled": True,
        },
    )

    accepted, cleaned, reason = jarvis._attention_decision("open camera")

    assert accepted is True
    assert cleaned == "open camera"
    assert reason == "action_recovery"


def test_attention_strict_still_rejects_general_question_without_name(monkeypatch):
    monkeypatch.setattr(
        jarvis,
        "load_config",
        lambda: {
            "attention_gate_enabled": True,
            "attention_mode": "name",
            "attention_names": "friday",
            "attention_action_recovery_enabled": True,
        },
    )

    accepted, _cleaned, reason = jarvis._attention_decision("how are you doing")

    assert accepted is False
    assert reason == "name_required"


def test_attention_strict_can_recover_safe_request_when_enabled(monkeypatch):
    monkeypatch.setattr(
        jarvis,
        "load_config",
        lambda: {
            "attention_gate_enabled": True,
            "attention_mode": "name",
            "attention_names": "friday",
            "attention_action_recovery_enabled": True,
            "attention_safe_request_recovery_enabled": True,
        },
    )

    accepted, cleaned, reason = jarvis._attention_decision("can you code")

    assert accepted is True
    assert cleaned == "can you code"
    assert reason == "safe_request_recovery"


def test_capture_attended_text_keeps_name_until_attention_gate(monkeypatch):
    calls = []

    def fake_record(*, strip_wake=True):
        calls.append(strip_wake)
        return "Friday, how are you doing", b"audio"

    monkeypatch.setattr(
        jarvis,
        "load_config",
        lambda: {
            "attention_gate_enabled": True,
            "attention_mode": "name",
            "attention_names": "friday",
        },
    )
    monkeypatch.setattr(jarvis, "record_and_transcribe_with_audio", fake_record)
    monkeypatch.setattr(jarvis, "_speaker_allowed", lambda audio: True)

    text, reason = jarvis._capture_attended_text()

    assert calls == [False]
    assert text == "how are you doing"
    assert reason == "accepted"


def test_capture_attended_text_fast_path_accepts_safe_intent(monkeypatch):
    calls = []

    def fake_transcribe(audio, model_name=None, strip_wake=True):
        calls.append(model_name)
        return "Friday, what time is it"

    monkeypatch.setattr(
        jarvis,
        "load_config",
        lambda: {
            "attention_gate_enabled": True,
            "attention_mode": "name",
            "attention_names": "friday",
            "stt_fast_path_enabled": True,
            "stt_fast_path_model": "small.en",
            "stt_model": "medium.en",
        },
    )
    monkeypatch.setattr(jarvis.stt, "record_audio", lambda: b"\x01\x00" * jarvis.stt.SAMPLE_RATE)
    monkeypatch.setattr(jarvis.stt, "transcribe", fake_transcribe)
    monkeypatch.setattr(jarvis.stt, "load_model", lambda name=None: object())
    monkeypatch.setattr(jarvis, "_speaker_allowed", lambda audio: True)

    text, reason = jarvis._capture_attended_text()

    assert calls == ["small.en"]
    assert text == "what time is it"
    assert reason == "accepted"


def test_capture_attended_text_fast_path_defers_actions_to_primary(monkeypatch):
    calls = []

    def fake_transcribe(audio, model_name=None, strip_wake=True):
        calls.append(model_name)
        return "Friday, open Chrome"

    monkeypatch.setattr(
        jarvis,
        "load_config",
        lambda: {
            "attention_gate_enabled": True,
            "attention_mode": "name",
            "attention_names": "friday",
            "stt_fast_path_enabled": True,
            "stt_fast_path_model": "small.en",
            "stt_model": "medium.en",
        },
    )
    monkeypatch.setattr(jarvis.stt, "record_audio", lambda: b"\x01\x00" * jarvis.stt.SAMPLE_RATE)
    monkeypatch.setattr(jarvis.stt, "transcribe", fake_transcribe)
    monkeypatch.setattr(jarvis, "_speaker_allowed", lambda audio: True)

    text, reason = jarvis._capture_attended_text()

    assert calls == ["small.en", "medium.en"]
    assert text == "open Chrome"
    assert reason == "accepted"


def test_capture_attended_text_fast_path_rejects_obvious_side_speech(monkeypatch):
    calls = []

    def fake_transcribe(audio, model_name=None, strip_wake=True):
        calls.append(model_name)
        return "You"

    monkeypatch.setattr(
        jarvis,
        "load_config",
        lambda: {
            "attention_gate_enabled": True,
            "attention_mode": "name",
            "attention_names": "friday",
            "stt_fast_path_enabled": True,
            "stt_fast_path_model": "small.en",
            "stt_model": "medium.en",
        },
    )
    monkeypatch.setattr(jarvis.stt, "record_audio", lambda: b"\x01\x00" * jarvis.stt.SAMPLE_RATE)
    monkeypatch.setattr(jarvis.stt, "transcribe", fake_transcribe)
    monkeypatch.setattr(jarvis.stt, "load_model", lambda name=None: object())
    monkeypatch.setattr(jarvis, "_speaker_allowed", lambda audio: True)

    text, reason = jarvis._capture_attended_text()

    assert calls == ["small.en"]
    assert text == ""
    assert reason == "attention"


def test_attention_accepts_common_friday_mishearing(monkeypatch):
    monkeypatch.setattr(
        jarvis,
        "load_config",
        lambda: {
            "attention_gate_enabled": True,
            "attention_mode": "name",
            "attention_names": "friday,friiday,freddie,freddy",
        },
    )

    accepted, cleaned, reason = jarvis._attention_decision("Hey Freddie, how are you doing?")

    assert accepted is True
    assert cleaned == "how are you doing"
    assert reason == "name"

    accepted, cleaned, reason = jarvis._attention_decision("Friiday Shutdown")

    assert accepted is True
    assert cleaned == "Shutdown"
    assert reason == "name"


def test_attention_accepts_live_friday_mishearings(monkeypatch):
    monkeypatch.setattr(
        jarvis,
        "load_config",
        lambda: {
            "attention_gate_enabled": True,
            "attention_mode": "name",
            "attention_names": "friday,friady,friyday",
        },
    )

    accepted, cleaned, reason = jarvis._attention_decision("Friady, how are you doing?")

    assert accepted is True
    assert cleaned == "how are you doing"
    assert reason == "name"

    accepted, cleaned, reason = jarvis._attention_decision("Friyday, what time is it?")

    assert accepted is True
    assert cleaned == "what time is it"
    assert reason == "name"


def test_attention_rejects_stt_prompt_leak_even_if_name_present(monkeypatch):
    monkeypatch.setattr(
        jarvis,
        "load_config",
        lambda: {
            "attention_gate_enabled": True,
            "attention_mode": "name",
            "attention_names": "friday",
        },
    )

    accepted, _cleaned, reason = jarvis._attention_decision(
        "Audio is a short command for an AI assistant named Friday, Chrome, Gmail, VS Code, camera, file"
    )

    assert accepted is False
    assert reason == "stt_prompt"


def test_attention_accepts_shut_down_phrase_without_name(monkeypatch):
    monkeypatch.setattr(jarvis, "load_config", lambda: {"attention_gate_enabled": True, "attention_mode": "name"})

    accepted, cleaned, reason = jarvis._attention_decision("Shut down.")

    assert accepted is True
    assert cleaned == "Shut down"
    assert reason == "shutdown"


def test_voice_challenge_only_protects_sensitive_commands(monkeypatch):
    monkeypatch.setattr(
        jarvis,
        "load_config",
        lambda: {
            "voice_challenge_enabled": True,
            "voice_challenge_mode": "protected",
            "voice_challenge_protected_keywords": "send email,open,delete",
        },
    )

    assert jarvis._requires_voice_challenge("what does POS mean") is False
    assert jarvis._requires_voice_challenge("open Chrome") is True
    assert jarvis._requires_voice_challenge("send email to Sam") is True


def test_challenge_phrase_matches_words_in_order():
    assert jarvis._challenge_matches("please say blue river paper", "blue river paper") is True
    assert jarvis._challenge_matches("blue paper river", "blue river paper") is False


def test_secure_voice_blocks_when_liveness_fails(monkeypatch):
    calls = []
    monkeypatch.setattr(jarvis, "_requires_voice_challenge", lambda text: True)
    monkeypatch.setattr(jarvis, "_voice_liveness_challenge", lambda: False)
    monkeypatch.setattr(jarvis, "speak", lambda text: None)
    monkeypatch.setattr(jarvis.orchestrator, "handle_command", lambda text: calls.append(text) or "Should not run")

    assert jarvis._handle_text("open Chrome", 0, speak_reply=False, secure_voice=True) == "I could not verify you. Action cancelled."
    assert calls == []


def test_liveness_challenge_stops_when_speaker_profile_missing(monkeypatch):
    spoken = []
    monkeypatch.setattr(
        jarvis,
        "load_config",
        lambda: {
            "speaker_verification_enabled": True,
            "voice_challenge_cache_seconds": 0,
        },
    )
    monkeypatch.setattr(jarvis.SpeakerVerifier, "available", classmethod(lambda cls: False))
    monkeypatch.setattr(jarvis, "speak", lambda text: spoken.append(text))
    monkeypatch.setattr(jarvis, "record_and_transcribe_with_audio", lambda: (_ for _ in ()).throw(AssertionError("should not record challenge")))

    assert jarvis._voice_liveness_challenge() is False
    assert "speaker profile" in spoken[0].lower()
