"""Optional LangChain adapters behind Friday's model gateway.

Friday's core model path stays in ``core.llm`` because it owns routing,
fallbacks, approval policy, logging, and local-first behavior. This module is a
thin interoperability layer for places where LangChain packages save work.
"""

from __future__ import annotations

import importlib
import importlib.util
import os
from dataclasses import dataclass
from typing import Any

from core.config import config_value


@dataclass(frozen=True)
class AdapterSpec:
    provider: str
    package: str
    class_name: str
    env_key: str
    config_model_key: str
    default_model: str
    base_url_key: str = ""
    default_base_url: str = ""


ADAPTERS = {
    "anthropic": AdapterSpec("anthropic", "langchain_anthropic", "ChatAnthropic", "ANTHROPIC_API_KEY", "anthropic_model", "claude-3-5-sonnet-20240620"),
    "gemini": AdapterSpec("gemini", "langchain_google_genai", "ChatGoogleGenerativeAI", "GEMINI_API_KEY", "gemini_model", "gemini-2.0-flash-lite"),
    "openrouter": AdapterSpec("openrouter", "langchain_openai", "ChatOpenAI", "OPENROUTER_API_KEY", "openrouter_model", "meta-llama/llama-3.2-3b-instruct:free", "openrouter_base_url", "https://openrouter.ai/api/v1"),
    "nvidia": AdapterSpec("nvidia", "langchain_openai", "ChatOpenAI", "NVIDIA_API_KEY", "nvidia_model", "meta/llama-3.3-70b-instruct", "nvidia_base_url", "https://integrate.api.nvidia.com/v1"),
    "ollama": AdapterSpec("ollama", "langchain_ollama", "ChatOllama", "", "ollama_model", "qwen3:8b", "ollama_base_url", "http://localhost:11434"),
}


def capabilities() -> dict[str, Any]:
    core_available = _module_available("langchain_core")
    adapters = {provider: adapter_status(provider) for provider in ADAPTERS}
    ready = [provider for provider, payload in adapters.items() if payload.get("ready")]
    return {
        "layer": "optional_langchain_adapter",
        "langchain_core_available": core_available,
        "ready": bool(core_available and ready),
        "ready_providers": ready,
        "adapters": adapters,
        "policy": [
            "Friday core.llm remains the model gateway.",
            "LangChain adapters are optional wrappers for interoperability.",
            "Approval, routing, tracing, and local fallback stay in Friday custom code.",
        ],
        "summary": (
            f"LangChain adapter layer can wrap {len(ready)} provider(s)."
            if core_available
            else "LangChain core is not installed; Friday will use its native model gateway only."
        ),
    }


def adapter_status(provider: str) -> dict[str, Any]:
    clean = _provider(provider)
    spec = ADAPTERS.get(clean)
    if spec is None:
        return {"provider": clean, "ready": False, "reason": "Unsupported LangChain adapter provider."}
    package_available = _module_available(spec.package)
    env_key = _env_key(spec)
    configured = True if clean == "ollama" else bool(_env_value(env_key))
    return {
        "provider": clean,
        "package": spec.package,
        "class_name": spec.class_name,
        "package_available": package_available,
        "configured": configured,
        "ready": bool(package_available and configured),
        "env_key": env_key,
        "model": str(config_value(spec.config_model_key, spec.default_model) or spec.default_model),
        "base_url": str(config_value(spec.base_url_key, spec.default_base_url) or spec.default_base_url) if spec.base_url_key else "",
        "reason": _reason(package_available, configured, spec.package, env_key),
    }


def create_chat_model(provider: str, **overrides: Any) -> Any:
    """Create a LangChain chat model for explicit interoperability paths.

    This function intentionally does not route calls. Callers should still use
    ``core.llm`` for normal Friday model selection and fallback.
    """

    clean = _provider(provider)
    spec = ADAPTERS.get(clean)
    if spec is None:
        raise ValueError(f"Unsupported LangChain adapter provider: {provider}")
    status = adapter_status(clean)
    if not status.get("ready"):
        raise RuntimeError(status.get("reason") or f"LangChain adapter for {clean} is not ready.")
    module = importlib.import_module(spec.package)
    cls = getattr(module, spec.class_name)
    model = str(overrides.pop("model", "") or status.get("model") or spec.default_model)
    temperature = float(overrides.pop("temperature", config_value(f"{clean}_temperature", 0.2) or 0.2))
    if clean == "anthropic":
        return cls(model=model, temperature=temperature, **overrides)
    if clean == "gemini":
        return cls(model=model, temperature=temperature, **overrides)
    if clean == "ollama":
        return cls(model=model, base_url=status.get("base_url") or spec.default_base_url, temperature=temperature, **overrides)
    if clean in {"openrouter", "nvidia"}:
        return cls(
            model=model,
            api_key=_env_value(status.get("env_key") or ""),
            base_url=status.get("base_url") or spec.default_base_url,
            temperature=temperature,
            **overrides,
        )
    raise ValueError(f"Unsupported LangChain adapter provider: {provider}")


def _env_key(spec: AdapterSpec) -> str:
    if spec.provider == "gemini":
        return str(config_value("gemini_api_key_env", spec.env_key) or spec.env_key)
    if spec.provider == "openrouter":
        return str(config_value("openrouter_api_key_env", spec.env_key) or spec.env_key)
    if spec.provider == "nvidia":
        return str(config_value("nvidia_api_key_env", spec.env_key) or spec.env_key)
    return spec.env_key


def _module_available(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except Exception:
        return False


def _env_value(name: str) -> str:
    value = os.getenv(str(name or ""), "")
    if _placeholder(value):
        return ""
    return value


def _placeholder(value: str) -> bool:
    text = str(value or "").strip().lower()
    return not text or text.startswith("your_") or text in {"your_key_here", "sk-ant-placeholder", "xxxx-xxxx-xxxx-xxxx"}


def _provider(provider: str) -> str:
    text = str(provider or "").strip().lower().replace("_", "-")
    aliases = {"local": "ollama", "open-router": "openrouter", "nvidia-nim": "nvidia", "nim": "nvidia"}
    return aliases.get(text, text)


def _reason(package_available: bool, configured: bool, package: str, env_key: str) -> str:
    if not package_available:
        return f"Install {package} to enable this LangChain adapter."
    if not configured:
        return f"Set {env_key} to enable this hosted adapter."
    return "Adapter ready."
