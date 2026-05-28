"""Repository hygiene checks for CI and pre-commit."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SKIP_DIRS = {".git", ".venv", "venv", "node_modules", "__pycache__", ".pytest_cache", ".next", "dist", "win-unpacked", "data"}
TEMPLATE_REQUIRED_KEYS = {
    "ANTHROPIC_API_KEY",
    "ELEVENLABS_API_KEY",
    "ELEVENLABS_VOICE_ID",
    "ALPHA_VANTAGE_KEY",
    "GMAIL_ADDRESS",
    "GMAIL_APP_PASSWORD",
    "GROQ_API_KEY",
    "DEEPGRAM_API_KEY",
    "GEMINI_API_KEY",
    "OPENROUTER_API_KEY",
    "NVIDIA_API_KEY",
    "MESHY_API_KEY",
    "TRIPO_API_KEY",
    "BRAVE_SEARCH_API_KEY",
    "GOOGLE_SEARCH_API_KEY",
    "GOOGLE_SEARCH_CX",
    "TAVILY_API_KEY",
    "SERPAPI_API_KEY",
    "GOOGLE_CLIENT_ID",
    "GOOGLE_CLIENT_SECRET",
    "PHONE_NTFY_TOPIC",
    "JARVIS_API_USERNAME",
    "JARVIS_API_PASSWORD",
    "JARVIS_API_SECRET",
    "FRIDAY_PRODUCTION_URL",
    "DATABASE_URL",
}
SECRET_PATTERNS = [
    re.compile(r"\bsk-ant-[A-Za-z0-9_-]{16,}"),
    re.compile(r"\bsk-or-v1-[A-Za-z0-9_-]{16,}"),
    re.compile(r"\bnvapi-[A-Za-z0-9_-]{16,}"),
    re.compile(r"\bAIza[A-Za-z0-9_-]{20,}"),
    re.compile(r"\bgsk_[A-Za-z0-9_-]{20,}"),
    re.compile(r"\b[A-Fa-f0-9]{32,}\b"),
]


def main() -> int:
    failures: list[str] = []
    failures.extend(check_env_template())
    failures.extend(check_config())
    failures.extend(scan_secret_like_values())
    if failures:
        print("Repository validation failed:")
        for failure in failures:
            print(f"- {failure}")
        return 1
    print("Repository validation passed.")
    return 0


def check_env_template() -> list[str]:
    path = ROOT / ".env.example"
    if not path.exists():
        return [".env.example is missing"]
    text = path.read_text(encoding="utf-8", errors="ignore")
    failures = [f".env.example missing {key}" for key in sorted(TEMPLATE_REQUIRED_KEYS) if f"{key}=" not in text]
    for line in text.splitlines():
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key.endswith(("PASSWORD", "SECRET", "TOKEN", "KEY")) and _looks_real_secret(value):
            failures.append(f".env.example has a real-looking secret for {key}")
    return failures


def check_config() -> list[str]:
    config_path = ROOT / "config.json"
    if not config_path.exists():
        return ["config.json is missing"]
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return [f"config.json is not valid JSON: {exc}"]
    required = {
        "safe_command_allowlist",
        "performance_budget_api_import_seconds",
        "performance_budget_orchestrator_import_seconds",
        "search_broker_provider_chain",
        "text_to_3d_provider_chain",
        "model_3d_blender_enabled",
    }
    return [f"config.json missing {key}" for key in sorted(required) if key not in config]


def scan_secret_like_values() -> list[str]:
    failures: list[str] = []
    for path in ROOT.rglob("*"):
        if not path.is_file() or _skip(path):
            continue
        if path.name == ".env":
            continue
        if path.suffix.lower() not in {".py", ".js", ".jsx", ".ts", ".tsx", ".json", ".md", ".yml", ".yaml", ".toml", ".ini", ".example"} and path.name not in {".env.example", ".gitignore", ".dockerignore"}:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        for pattern in SECRET_PATTERNS:
            if pattern.search(text):
                failures.append(f"secret-like value in {path.relative_to(ROOT)}")
                break
    return failures[:20]


def _skip(path: Path) -> bool:
    return any(part in SKIP_DIRS for part in path.relative_to(ROOT).parts)


def _looks_real_secret(value: str) -> bool:
    text = value.strip()
    lowered = text.lower()
    if not text or any(marker in lowered for marker in ("your_", "example", "placeholder", "xxxx", "user:password")):
        return False
    return len(text) >= 12 or any(pattern.search(text) for pattern in SECRET_PATTERNS)


if __name__ == "__main__":
    raise SystemExit(main())
