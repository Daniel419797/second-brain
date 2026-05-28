"""Readiness checks for external providers and production deployment."""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any

from core.config import config_value, default_coding_root

PLACEHOLDERS = {
    "",
    "password",
    "changeme",
    "change_me",
    "placeholder",
    "your_api_key_here",
    "your_api_password_here",
    "your_api_secret_here",
    "your_meshy_key_here",
    "your_tripo_key_here",
    "your_brave_key_here",
    "your_google_search_key_here",
    "your_google_cse_id_here",
    "your_tavily_key_here",
    "your_serpapi_key_here",
}


def status(*, probe: bool = False, root: str | Path = "") -> dict[str, Any]:
    """Return safe provider readiness without exposing secret values."""

    providers = {
        "search": _search_status(),
        "image_generation": _image_status(probe=probe),
        "text_to_3d": _text_to_3d_status(),
        "model_3d": _model_3d_status(),
    }
    missing = _missing_provider_steps(providers)
    return {
        "ok": not missing,
        "probe": probe,
        "providers": providers,
        "github": github_status(root=root),
        "production": production_readiness(),
        "missing": missing,
        "summary": "Provider readiness is complete." if not missing else "Some provider backends still need setup.",
    }


def production_readiness() -> dict[str, Any]:
    """Check deployment-critical configuration locally."""

    db_env = str(config_value("cloud_sync_database_url_env", "DATABASE_URL"))
    password_env = str(config_value("api_password_env", "JARVIS_API_PASSWORD"))
    secret_env = str(config_value("api_jwt_secret_env", "JARVIS_API_SECRET"))
    checks = [
        _check("https", _configured("FRIDAY_PRODUCTION_URL") and str(os.getenv("FRIDAY_PRODUCTION_URL", "")).startswith("https://"), "Set FRIDAY_PRODUCTION_URL to the deployed HTTPS API URL."),
        _check("database_url", _configured(db_env), f"Set {db_env} to a real PostgreSQL database URL."),
        _check("api_password", _configured(password_env), f"Set {password_env} to a strong non-placeholder password."),
        _check("api_jwt_secret", _configured(secret_env), f"Set {secret_env} to a strong non-placeholder JWT secret."),
        _check("secure_cookies", bool(config_value("api_secure_cookies", False)), "Enable api_secure_cookies for HTTPS production."),
        _check("cloud_sync_enabled", bool(config_value("cloud_sync_enabled", False)), "Enable cloud_sync_enabled after the real PostgreSQL database is verified."),
        _check("backup_policy", not bool(config_value("backup_allow_env_snapshot", False)), "Keep backup_allow_env_snapshot disabled unless a reviewed secrets backup policy exists."),
    ]
    ok = all(item["ok"] for item in checks)
    return {
        "ok": ok,
        "checks": checks,
        "summary": "Production prerequisites are configured." if ok else "Production still needs deployment configuration.",
    }


def github_status(root: str | Path = "") -> dict[str, Any]:
    """Return local Git/GitHub status without requiring authenticated pushes."""

    from core import git_integration

    repo_root = Path(root).expanduser() if str(root or "").strip() else Path.cwd()
    if not (repo_root / ".git").exists():
        repo_root = default_coding_root()
    git = git_integration.status(repo_root)
    gh = git_integration.github_status(repo_root)
    gh_output = "\n".join(part for part in [gh.get("stdout", ""), gh.get("stderr", "")] if part).strip()
    authenticated = bool(gh.get("ok"))
    return {
        "git_repo": bool(git.get("ok")),
        "root": str(repo_root),
        "github_cli_installed": "not installed" not in str(gh.get("summary", "")).lower(),
        "github_authenticated": authenticated,
        "remote_configured": _has_remote(repo_root),
        "gh_summary": _short(gh_output or gh.get("summary", ""), 500),
        "next_step": "" if authenticated else "Run gh auth login, then add a GitHub remote and push the branch.",
    }


def _search_status() -> dict[str, Any]:
    from core import search_broker

    payload = search_broker.status()
    return {
        "ready": bool(payload.get("configured")),
        "provider_chain": payload.get("provider_chain", []),
        "configured": payload.get("configured", []),
        "providers": payload.get("providers", {}),
        "setup_hint": "Set at least one dedicated search key: Brave, Google CSE, Tavily, or SerpAPI.",
    }


def _image_status(*, probe: bool) -> dict[str, Any]:
    if probe:
        from core import image_generation

        payload = image_generation.status()
        return {
            "ready": bool(payload.get("ready")),
            "provider": payload.get("provider", "auto"),
            "local_stable_diffusion": payload.get("local_stable_diffusion", {}),
            "hugging_face": payload.get("hugging_face", {}),
            "pollinations": payload.get("pollinations", {}),
            "setup_hint": payload.get("setup_hint", ""),
        }
    provider = str(os.getenv("IMAGE_GENERATION_PROVIDER") or config_value("image_generation_provider", "auto"))
    pollinations_enabled = provider.lower() == "pollinations" or _truthy(os.getenv("POLLINATIONS_ENABLED") or config_value("pollinations_enabled", ""))
    stable_url = _configured("STABLE_DIFFUSION_URL") or _configured_config("stable_diffusion_url")
    hf_ready = _configured("HF_TOKEN") or _configured("HUGGINGFACE_API_TOKEN")
    return {
        "ready": bool(stable_url or hf_ready or pollinations_enabled),
        "provider": provider,
        "local_stable_diffusion": {"configured": bool(stable_url)},
        "hugging_face": {"configured": bool(hf_ready), "model": str(os.getenv("HF_IMAGE_MODEL") or config_value("hf_image_model", ""))},
        "pollinations": {"configured": bool(pollinations_enabled), "reachable": None},
        "setup_hint": "Set STABLE_DIFFUSION_URL, HF_TOKEN/HUGGINGFACE_API_TOKEN, or IMAGE_GENERATION_PROVIDER=pollinations.",
    }


def _text_to_3d_status() -> dict[str, Any]:
    from core import text_to_3d

    payload = text_to_3d.status()
    configured = payload.get("configured", {})
    ready = any(bool(value) for value in configured.values())
    return payload | {
        "ready": ready,
        "setup_hint": "Set MESHY_API_KEY, TRIPO_API_KEY, or configure text_to_3d_local_command.",
    }


def _model_3d_status() -> dict[str, Any]:
    blender_path = str(config_value("model_3d_blender_path", "blender") or "blender").strip()
    blender_enabled = bool(config_value("model_3d_blender_enabled", True))
    blender_resolved = shutil.which(blender_path) if blender_path else None
    return {
        "procedural_ready": True,
        "studio_enabled": blender_enabled,
        "blender_configured": bool(blender_path),
        "blender_available": bool(blender_enabled and blender_resolved),
        "blender_path": blender_path,
        "output_dir": str(config_value("model_3d_output_dir", "data/3d_models")),
        "setup_hint": "Install Blender and set model_3d_blender_path for Blender/ZBrush-style cleanup and exports.",
    }


def _missing_provider_steps(providers: dict[str, Any]) -> list[str]:
    missing: list[str] = []
    if not providers["search"].get("ready"):
        missing.append("Configure at least one dedicated search API key.")
    if not providers["image_generation"].get("ready"):
        missing.append("Configure an image backend: Stable Diffusion, Hugging Face, or Pollinations.")
    if not providers["text_to_3d"].get("ready"):
        missing.append("Configure Meshy, Tripo, or a local text-to-3D command.")
    if not providers["model_3d"].get("blender_available"):
        missing.append("Install/configure Blender for studio-grade 3D exports.")
    return missing


def _check(name: str, ok: bool, action: str) -> dict[str, Any]:
    return {"name": name, "ok": bool(ok), "action": "" if ok else action}


def _configured(env_key: str) -> bool:
    value = os.getenv(str(env_key or ""), "")
    return bool(value and value.strip().lower() not in PLACEHOLDERS and not value.strip().lower().startswith("your_"))


def _configured_config(key: str) -> bool:
    value = str(config_value(key, "") or "")
    return bool(value and value.strip().lower() not in PLACEHOLDERS)


def _truthy(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _has_remote(root: Path) -> bool:
    if not (root / ".git").exists():
        return False
    from core import git_integration

    result = git_integration._run(["git", "remote"], cwd=root, success="Git remotes ready.")
    return bool(result.get("ok") and str(result.get("stdout", "")).strip())


def _short(value: Any, limit: int) -> str:
    text = str(value or "").strip()
    return text if len(text) <= limit else text[:limit].rstrip() + "..."
