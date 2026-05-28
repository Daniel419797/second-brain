from types import SimpleNamespace

from core import llm


class FakeMessages:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = 0

    def create(self, **kwargs):
        self.calls += 1
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class FakeClient:
    def __init__(self, outcomes):
        self.messages = FakeMessages(outcomes)


def test_ask_returns_tool_use_block(monkeypatch):
    response = SimpleNamespace(
        content=[SimpleNamespace(type="tool_use", name="pc_control", input={"action": "open_app", "target": "chrome"}, id="1")],
        usage=SimpleNamespace(input_tokens=10, output_tokens=5),
    )
    fake = FakeClient([response])
    monkeypatch.setattr(llm, "client", fake)
    monkeypatch.setattr(llm, "config_value", lambda key, default=None: "anthropic" if key == "llm_provider" else default)

    result = llm.ask([{"role": "user", "content": "open chrome"}], retries=1)

    assert result.content[0].type == "tool_use"
    assert result.content[0].name == "pc_control"
    assert fake.messages.calls == 1


def test_pc_control_tool_schema_includes_desktop_task():
    pc_tool = next(tool for tool in llm.TOOL_DEFINITIONS if tool["name"] == "pc_control")

    assert "desktop_task" in pc_tool["input_schema"]["properties"]["action"]["enum"]


def test_app_integrations_tool_schema_includes_workspace_index():
    tool = next(tool for tool in llm.TOOL_DEFINITIONS if tool["name"] == "app_integrations")

    assert "index_workspace" in tool["input_schema"]["properties"]["action"]["enum"]
    assert "create_reminder" in tool["input_schema"]["properties"]["action"]["enum"]


def test_capability_center_tool_schema_includes_security_lab():
    tool = next(tool for tool in llm.TOOL_DEFINITIONS if tool["name"] == "capability_center")

    actions = tool["input_schema"]["properties"]["action"]["enum"]
    assert "open_port_scan" in actions
    assert "hardening_plan" in actions


def test_phone_bridge_tool_schema_includes_v2_controls():
    tool = next(tool for tool in llm.TOOL_DEFINITIONS if tool["name"] == "phone_bridge")

    actions = tool["input_schema"]["properties"]["action"]["enum"]
    assert "sms_draft" in actions
    assert "import_photos" in actions


def test_power_center_tool_schema_includes_new_powers():
    tool = next(tool for tool in llm.TOOL_DEFINITIONS if tool["name"] == "power_center")

    actions = tool["input_schema"]["properties"]["action"]["enum"]
    assert "install_builtin_skills" in actions
    assert "workspace_analyze" in actions
    assert "operate_app" in actions
    assert "autonomous_coding" in actions
    assert "backup_config" in actions
    assert "guardian_scan" in actions
    assert "voice_repair" in actions
    assert "automation_from_text" in actions
    assert "git_status" in actions
    assert "git_push" in actions
    assert "github_pr_create" in actions
    assert "model3d_create" in actions


def test_self_update_tool_schema_includes_apply():
    tool = next(tool for tool in llm.TOOL_DEFINITIONS if tool["name"] == "self_update")

    actions = tool["input_schema"]["properties"]["action"]["enum"]
    assert "propose" in actions
    assert "stage_change" in actions
    assert "apply" in actions


def test_ask_retries_rate_limit_three_times(monkeypatch):
    class RateLimitError(Exception):
        pass

    fake = FakeClient([RateLimitError("slow down"), RateLimitError("slow down"), RateLimitError("slow down")])
    monkeypatch.setattr(llm, "client", fake)
    monkeypatch.setattr(llm, "anthropic", SimpleNamespace())
    monkeypatch.setattr(llm, "config_value", lambda key, default=None: "anthropic" if key == "llm_provider" else default)
    monkeypatch.setattr(llm.time, "sleep", lambda seconds: None)

    assert llm.ask([{"role": "user", "content": "hello"}], retries=3) is None
    assert fake.messages.calls == 3


def test_ask_simple_extracts_text(monkeypatch):
    response = SimpleNamespace(
        content=[SimpleNamespace(type="text", text="A list stores ordered values.")],
        usage=SimpleNamespace(input_tokens=8, output_tokens=8),
    )
    monkeypatch.setattr(llm, "client", FakeClient([response]))
    monkeypatch.setattr(llm, "config_value", lambda key, default=None: "anthropic" if key == "llm_provider" else default)

    assert llm.ask_simple("what is a list in Python", retries=1) == "A list stores ordered values."


def test_provider_chain_falls_back_in_order(monkeypatch):
    calls = []

    def fake_ask_provider(provider, messages, tools=None, retries=1):
        calls.append((provider, retries))
        if provider == "gemini":
            return None
        return SimpleNamespace(
            content=[SimpleNamespace(type="text", text=f"Hello from {provider}.")],
            usage=SimpleNamespace(input_tokens=1, output_tokens=1),
        )

    monkeypatch.setattr(llm, "_ask_provider", fake_ask_provider)

    result = llm.ask_simple_with_provider_chain("hello", "gemini>nvidia>ollama", retries=2)

    assert result == "Hello from nvidia."
    assert calls == [("gemini", 2), ("nvidia", 1)]


def test_online_provider_availability_uses_configured_api_keys(monkeypatch):
    monkeypatch.setenv("NVIDIA_API_KEY", "test-key")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    assert llm.online_provider_available("gemini>nvidia") is True
    assert llm.provider_has_credentials("nvidia") is True
    assert llm.provider_has_credentials("gemini") is False


def test_ollama_tool_call_is_wrapped(monkeypatch):
    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "message": {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "function": {
                                "name": "pc_control",
                                "arguments": {"action": "open_app", "target": "chrome"},
                            }
                        }
                    ],
                },
                "prompt_eval_count": 11,
                "eval_count": 7,
            }

    calls = []

    class FakeRequests:
        @staticmethod
        def post(url, json, timeout):
            calls.append((url, json, timeout))
            return FakeResponse()

    def fake_config(key, default=None):
        values = {
            "llm_provider": "ollama",
            "ollama_base_url": "http://localhost:11434",
            "ollama_model": "qwen3:8b",
            "ollama_timeout": 5,
            "ollama_keep_alive": "30m",
            "ollama_num_predict": 120,
            "ollama_num_ctx": 2048,
            "ollama_temperature": 0.2,
        }
        return values.get(key, default)

    monkeypatch.setattr(llm, "requests", FakeRequests)
    monkeypatch.setattr(llm, "config_value", fake_config)

    result = llm.ask([{"role": "user", "content": "open chrome"}], retries=1)

    assert result.content[0].type == "tool_use"
    assert result.content[0].name == "pc_control"
    assert result.content[0].input == {"action": "open_app", "target": "chrome"}
    assert calls[0][0] == "http://localhost:11434/api/chat"
    assert calls[0][1]["tools"][0]["type"] == "function"
    assert calls[0][1]["keep_alive"] == "30m"
    assert calls[0][1]["options"]["num_predict"] == 120


def test_ollama_text_response_is_wrapped(monkeypatch):
    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"message": {"role": "assistant", "content": "Hello from local."}}

    class FakeRequests:
        @staticmethod
        def post(url, json, timeout):
            return FakeResponse()

    def fake_config(key, default=None):
        return "ollama" if key == "llm_provider" else default

    monkeypatch.setattr(llm, "requests", FakeRequests)
    monkeypatch.setattr(llm, "config_value", fake_config)

    assert llm.ask_simple("hello", retries=1) == "Hello from local."


def test_gemini_text_response_is_wrapped(monkeypatch):
    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"candidates": [{"content": {"parts": [{"text": "Hello from Gemini."}]}}]}

    calls = []

    class FakeRequests:
        @staticmethod
        def post(url, json, timeout):
            calls.append((url, json, timeout))
            return FakeResponse()

    def fake_config(key, default=None):
        values = {
            "llm_provider": "gemini",
            "gemini_model": "gemini-free",
            "gemini_base_url": "https://generativelanguage.googleapis.com/v1beta",
            "gemini_timeout": 5,
        }
        return values.get(key, default)

    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(llm, "requests", FakeRequests)
    monkeypatch.setattr(llm, "config_value", fake_config)

    assert llm.ask_simple("hello", retries=1) == "Hello from Gemini."
    assert "models/gemini-free:generateContent" in calls[0][0]


def test_openrouter_tool_call_is_wrapped(monkeypatch):
    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "choices": [
                    {
                        "message": {
                            "tool_calls": [
                                {
                                    "id": "1",
                                    "function": {"name": "agent_team", "arguments": '{"action":"status"}'},
                                }
                            ]
                        }
                    }
                ],
                "usage": {"prompt_tokens": 3, "completion_tokens": 4},
            }

    class FakeRequests:
        @staticmethod
        def post(url, json, headers, timeout):
            return FakeResponse()

    def fake_config(key, default=None):
        values = {
            "llm_provider": "openrouter",
            "openrouter_model": "free/model",
            "openrouter_base_url": "https://openrouter.ai/api/v1",
            "openrouter_timeout": 5,
        }
        return values.get(key, default)

    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setattr(llm, "requests", FakeRequests)
    monkeypatch.setattr(llm, "config_value", fake_config)

    result = llm.ask([{"role": "user", "content": "team status"}], retries=1)

    assert result.content[0].type == "tool_use"
    assert result.content[0].name == "agent_team"
    assert result.content[0].input == {"action": "status"}


def test_nvidia_text_response_is_wrapped(monkeypatch):
    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "choices": [{"message": {"content": "Hello from NVIDIA."}}],
                "usage": {"prompt_tokens": 5, "completion_tokens": 6},
            }

    calls = []

    class FakeRequests:
        @staticmethod
        def post(url, json, headers, timeout):
            calls.append((url, json, headers, timeout))
            return FakeResponse()

    def fake_config(key, default=None):
        values = {
            "llm_provider": "nvidia",
            "nvidia_model": "meta/llama-3.3-70b-instruct",
            "nvidia_base_url": "https://integrate.api.nvidia.com/v1",
            "nvidia_timeout": 5,
            "nvidia_temperature": 0.2,
            "nvidia_max_tokens": 128,
        }
        return values.get(key, default)

    monkeypatch.setenv("NVIDIA_API_KEY", "test-key")
    monkeypatch.setattr(llm, "requests", FakeRequests)
    monkeypatch.setattr(llm, "config_value", fake_config)

    assert llm.ask_simple("hello", retries=1) == "Hello from NVIDIA."
    assert calls[0][0] == "https://integrate.api.nvidia.com/v1/chat/completions"
    assert calls[0][1]["model"] == "meta/llama-3.3-70b-instruct"
    assert calls[0][2]["Authorization"] == "Bearer test-key"


def test_nvidia_falls_back_to_ollama_when_key_missing(monkeypatch):
    calls = []

    def fake_config(key, default=None):
        values = {
            "llm_provider": "nvidia",
            "llm_fallback_provider": "ollama",
            "nvidia_api_key_env": "NVIDIA_API_KEY",
        }
        return values.get(key, default)

    monkeypatch.delenv("NVIDIA_API_KEY", raising=False)
    monkeypatch.setattr(llm, "config_value", fake_config)
    monkeypatch.setattr(llm, "_ask_ollama", lambda messages, tools=None, retries=1: calls.append((messages, tools, retries)) or SimpleNamespace(content=[SimpleNamespace(type="text", text="Local fallback.")]))

    assert llm.ask_simple("hello", retries=1) == "Local fallback."
    assert calls
