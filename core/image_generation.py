"""Free-first image generation boundary for Friday.

Providers are deliberately explicit. Friday may create images only when a
local Stable Diffusion/AUTOMATIC1111 server or an optional Hugging Face image
endpoint is configured. Otherwise it records the request and reports the setup
gap instead of pretending that an image was generated.
"""

from __future__ import annotations

import base64
import datetime as dt
import json
import os
import re
import sqlite3
import threading
from pathlib import Path
from typing import Any
from urllib.parse import quote

try:
    import requests
except Exception:  # pragma: no cover - dependency may be absent in scaffold tests
    requests = None

from core.config import DATA_DIR, config_value, ensure_runtime_dirs

DB_PATH = DATA_DIR / "image_generation.sqlite3"
OUTPUT_DIR = DATA_DIR / "generated_images"
_LOCK = threading.Lock()

DEFAULT_HF_MODEL = "stabilityai/stable-diffusion-xl-base-1.0"
DEFAULT_POLLINATIONS_MODEL = "flux"
DEFAULT_POLLINATIONS_BASE_URL = "https://image.pollinations.ai/prompt"
BLOCKED_PATTERNS = (
    r"\b(?:minor|child|children|kid|kids|underage)\b.*\b(?:nude|sexual|explicit|erotic|porn)\b",
    r"\b(?:nude|sexual|explicit|erotic|porn)\b.*\b(?:minor|child|children|kid|kids|underage)\b",
)


def init_db(path: Path | None = None) -> None:
    ensure_runtime_dirs()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    db_path = path or DB_PATH
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path, timeout=10) as conn:
        try:
            conn.execute("PRAGMA journal_mode=WAL")
        except sqlite3.OperationalError:
            pass
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS image_generation_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                prompt TEXT NOT NULL,
                negative_prompt TEXT NOT NULL,
                provider TEXT NOT NULL,
                status TEXT NOT NULL,
                filename TEXT NOT NULL,
                path TEXT NOT NULL,
                width INTEGER NOT NULL,
                height INTEGER NOT NULL,
                steps INTEGER NOT NULL,
                reason TEXT NOT NULL,
                metadata_json TEXT NOT NULL
            )
            """
        )


def status() -> dict[str, Any]:
    """Return provider readiness without claiming any provider is working."""

    local_url = _stable_diffusion_url()
    local_probe = _stable_diffusion_probe(local_url)
    hf_token = _hf_token()
    pollinations = _pollinations_status()
    provider = _provider_setting()
    ready = bool(local_probe.get("reachable") or hf_token or pollinations.get("reachable"))
    return {
        "enabled": True,
        "provider": provider,
        "ready": ready,
        "local_stable_diffusion": {
            "configured": bool(local_url),
            "reachable": bool(local_probe.get("reachable")),
            "url": local_url,
            "kind": "AUTOMATIC1111 /sdapi/v1/txt2img",
            "reason": str(local_probe.get("reason") or ""),
        },
        "hugging_face": {
            "configured": bool(hf_token),
            "model": _hf_model(),
        },
        "pollinations": pollinations,
        "setup_hint": setup_hint(),
    }


def setup_hint() -> str:
    return (
        "To generate images, run a local Stable Diffusion/AUTOMATIC1111 server at "
        "STABLE_DIFFUSION_URL, set HF_TOKEN/HUGGINGFACE_API_TOKEN and HF_IMAGE_MODEL, "
        "or set IMAGE_GENERATION_PROVIDER=pollinations for the hosted no-key provider."
    )


def generate_image(
    prompt: str,
    *,
    negative_prompt: str = "",
    width: int = 768,
    height: int = 768,
    steps: int = 24,
    provider: str = "auto",
) -> dict[str, Any]:
    init_db()
    cleaned_prompt = _clean_prompt(prompt)
    if not cleaned_prompt:
        return _record(
            prompt="",
            negative_prompt=negative_prompt,
            provider="none",
            status="failed",
            width=width,
            height=height,
            steps=steps,
            reason="Prompt is empty.",
        )
    blocked = _blocked_reason(cleaned_prompt)
    if blocked:
        return _record(
            prompt=cleaned_prompt,
            negative_prompt=negative_prompt,
            provider="safety",
            status="blocked",
            width=width,
            height=height,
            steps=steps,
            reason=blocked,
        )

    width = _clamp_dimension(width)
    height = _clamp_dimension(height)
    steps = max(1, min(80, int(steps or 24)))
    chosen_provider = _canonical_provider(provider or _provider_setting())
    chain = _provider_chain(chosen_provider)
    failures: list[str] = []
    for item in chain:
        try:
            if item == "stable_diffusion":
                result = _generate_stable_diffusion(cleaned_prompt, negative_prompt, width, height, steps)
            elif item == "hugging_face":
                result = _generate_hugging_face(cleaned_prompt, negative_prompt, width, height, steps)
            elif item == "pollinations":
                result = _generate_pollinations(cleaned_prompt, negative_prompt, width, height, steps)
            else:
                result = {"ok": False, "reason": f"Unknown image provider: {item}"}
        except Exception as exc:
            result = {"ok": False, "reason": str(exc)}
        if result.get("ok"):
            return _record(
                prompt=cleaned_prompt,
                negative_prompt=negative_prompt,
                provider=item,
                status="generated",
                width=width,
                height=height,
                steps=steps,
                filename=str(result["filename"]),
                path=str(result["path"]),
                reason="Image generated.",
                metadata={"providers_tried": chain},
            )
        failures.append(f"{item}: {result.get('reason') or 'unavailable'}")

    reason = "; ".join(failures) if failures else "No image provider is configured."
    return _record(
        prompt=cleaned_prompt,
        negative_prompt=negative_prompt,
        provider=chosen_provider,
        status="unavailable",
        width=width,
        height=height,
        steps=steps,
        reason=f"{reason} {setup_hint()}",
        metadata={"providers_tried": chain},
    )


def list_images(limit: int = 30) -> list[dict[str, Any]]:
    init_db()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM image_generation_requests ORDER BY id DESC LIMIT ?",
            (max(1, min(100, int(limit))),),
        ).fetchall()
    return [_row_to_item(row) for row in rows]


def image_path(filename: str) -> Path:
    safe = Path(str(filename or "")).name
    path = (OUTPUT_DIR / safe).resolve()
    root = OUTPUT_DIR.resolve()
    if not str(path).lower().startswith(str(root).lower()) or path.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp"}:
        raise ValueError("Invalid generated image filename.")
    return path


def _generate_stable_diffusion(prompt: str, negative_prompt: str, width: int, height: int, steps: int) -> dict[str, Any]:
    if requests is None:
        return {"ok": False, "reason": "requests is not installed."}
    base_url = _stable_diffusion_url()
    if not base_url:
        return {"ok": False, "reason": "STABLE_DIFFUSION_URL is not configured."}
    payload = {
        "prompt": prompt,
        "negative_prompt": negative_prompt,
        "width": width,
        "height": height,
        "steps": steps,
        "cfg_scale": float(config_value("image_generation_cfg_scale", 7.0)),
        "sampler_name": str(config_value("image_generation_sampler", "Euler a")),
    }
    timeout = float(config_value("image_generation_timeout_seconds", 90))
    response = requests.post(f"{base_url.rstrip('/')}/sdapi/v1/txt2img", json=payload, timeout=timeout)
    if response.status_code >= 400:
        return {"ok": False, "reason": f"Stable Diffusion HTTP {response.status_code}: {response.text[:240]}"}
    data = response.json()
    images = data.get("images") or []
    if not images:
        return {"ok": False, "reason": "Stable Diffusion returned no images."}
    raw = str(images[0]).split(",", 1)[-1]
    return _save_image_bytes(base64.b64decode(raw), prompt, ".png")


def _generate_hugging_face(prompt: str, negative_prompt: str, width: int, height: int, steps: int) -> dict[str, Any]:
    if requests is None:
        return {"ok": False, "reason": "requests is not installed."}
    token = _hf_token()
    if not token:
        return {"ok": False, "reason": "HF_TOKEN or HUGGINGFACE_API_TOKEN is not configured."}
    model = _hf_model()
    payload = {
        "inputs": prompt,
        "parameters": {
            "negative_prompt": negative_prompt,
            "width": width,
            "height": height,
            "num_inference_steps": steps,
        },
    }
    timeout = float(config_value("image_generation_timeout_seconds", 90))
    response = requests.post(
        f"https://api-inference.huggingface.co/models/{model}",
        headers={"Authorization": f"Bearer {token}"},
        json=payload,
        timeout=timeout,
    )
    content_type = response.headers.get("content-type", "")
    if response.status_code >= 400:
        return {"ok": False, "reason": f"Hugging Face HTTP {response.status_code}: {response.text[:240]}"}
    if "image/" in content_type:
        suffix = ".png" if "png" in content_type else ".jpg"
        return _save_image_bytes(response.content, prompt, suffix)
    try:
        body = response.json()
    except Exception:
        body = {"message": response.text[:240]}
    return {"ok": False, "reason": f"Hugging Face did not return image bytes: {body}"}


def _generate_pollinations(prompt: str, negative_prompt: str, width: int, height: int, steps: int) -> dict[str, Any]:
    if requests is None:
        return {"ok": False, "reason": "requests is not installed."}
    if not _pollinations_enabled():
        return {"ok": False, "reason": "Pollinations provider is not configured."}
    base_url = _pollinations_base_url()
    generation_prompt = prompt
    if negative_prompt:
        generation_prompt = f"{prompt}. Avoid: {negative_prompt}"
    params = {
        "width": int(width),
        "height": int(height),
        "model": _pollinations_model(),
        "nologo": "true",
        "safe": "true",
    }
    seed = str(os.getenv("POLLINATIONS_SEED") or config_value("pollinations_seed", "") or "").strip()
    if seed:
        params["seed"] = seed
    timeout = float(config_value("image_generation_timeout_seconds", 90))
    response = requests.get(f"{base_url.rstrip('/')}/{quote(generation_prompt)}", params=params, timeout=timeout)
    content_type = response.headers.get("content-type", "")
    if response.status_code >= 400:
        return {"ok": False, "reason": f"Pollinations HTTP {response.status_code}: {response.text[:240]}"}
    if "image/" not in content_type:
        return {"ok": False, "reason": f"Pollinations did not return image bytes: {response.text[:240]}"}
    suffix = ".png" if "png" in content_type else ".jpg"
    return _save_image_bytes(response.content, prompt, suffix)


def _save_image_bytes(content: bytes, prompt: str, suffix: str) -> dict[str, Any]:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    slug = re.sub(r"[^a-z0-9]+", "_", prompt.lower()).strip("_")[:48] or "image"
    filename = f"{stamp}_{slug}{suffix}"
    path = image_path(filename)
    path.write_bytes(content)
    return {"ok": True, "filename": filename, "path": str(path)}


def _record(
    *,
    prompt: str,
    negative_prompt: str,
    provider: str,
    status: str,
    width: int,
    height: int,
    steps: int,
    reason: str,
    filename: str = "",
    path: str = "",
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    init_db()
    timestamp = dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds")
    metadata = metadata or {}
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        cursor = conn.execute(
            """
            INSERT INTO image_generation_requests (
                timestamp, prompt, negative_prompt, provider, status, filename, path,
                width, height, steps, reason, metadata_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                timestamp,
                prompt,
                str(negative_prompt or ""),
                provider,
                status,
                filename,
                path,
                int(width or 0),
                int(height or 0),
                int(steps or 0),
                reason,
                json.dumps(metadata, ensure_ascii=True, sort_keys=True),
            ),
        )
        item_id = int(cursor.lastrowid)
    item = {
        "id": item_id,
        "timestamp": timestamp,
        "prompt": prompt,
        "negative_prompt": str(negative_prompt or ""),
        "provider": provider,
        "status": status,
        "ok": status == "generated",
        "filename": filename,
        "path": path,
        "url": f"/images/{filename}" if filename else "",
        "width": int(width or 0),
        "height": int(height or 0),
        "steps": int(steps or 0),
        "reason": reason,
        "metadata": metadata,
    }
    return item


def _row_to_item(row: sqlite3.Row) -> dict[str, Any]:
    metadata = _json_loads(row["metadata_json"], {})
    return {
        "id": int(row["id"]),
        "timestamp": str(row["timestamp"]),
        "prompt": str(row["prompt"]),
        "negative_prompt": str(row["negative_prompt"]),
        "provider": str(row["provider"]),
        "status": str(row["status"]),
        "ok": str(row["status"]) == "generated",
        "filename": str(row["filename"]),
        "path": str(row["path"]),
        "url": f"/images/{row['filename']}" if row["filename"] else "",
        "width": int(row["width"] or 0),
        "height": int(row["height"] or 0),
        "steps": int(row["steps"] or 0),
        "reason": str(row["reason"]),
        "metadata": metadata,
    }


def _provider_chain(provider: str) -> list[str]:
    if provider in {"auto", ""}:
        chain = ["stable_diffusion"]
        if _hf_token():
            chain.append("hugging_face")
        if _pollinations_enabled():
            chain.append("pollinations")
        return chain
    return [provider]


def _canonical_provider(value: str) -> str:
    provider = str(value or "auto").strip().lower().replace("-", "_")
    aliases = {
        "local": "stable_diffusion",
        "a1111": "stable_diffusion",
        "automatic1111": "stable_diffusion",
        "stable_diffusion_webui": "stable_diffusion",
        "hf": "hugging_face",
        "huggingface": "hugging_face",
        "pollinations_ai": "pollinations",
        "pollination": "pollinations",
    }
    return aliases.get(provider, provider)


def _provider_setting() -> str:
    return _canonical_provider(os.getenv("IMAGE_GENERATION_PROVIDER") or str(config_value("image_generation_provider", "auto")))


def _stable_diffusion_url() -> str:
    return str(os.getenv("STABLE_DIFFUSION_URL") or config_value("stable_diffusion_url", "http://127.0.0.1:7860") or "").strip().rstrip("/")


def _stable_diffusion_probe(base_url: str) -> dict[str, Any]:
    if not base_url:
        return {"reachable": False, "reason": "STABLE_DIFFUSION_URL is not configured."}
    if requests is None:
        return {"reachable": False, "reason": "requests is not installed."}
    timeout = float(config_value("image_generation_status_timeout_seconds", 2.0))
    try:
        response = requests.get(f"{base_url.rstrip('/')}/sdapi/v1/sd-models", timeout=timeout)
    except Exception as exc:
        return {"reachable": False, "reason": _connection_reason(exc)}
    if response.status_code >= 400:
        return {"reachable": False, "reason": f"HTTP {response.status_code}: {response.text[:160]}"}
    return {"reachable": True, "reason": "reachable"}


def _connection_reason(exc: Exception) -> str:
    message = str(exc).lower()
    if "timed out" in message or "timeout" in message:
        return "connection timed out"
    if "connection refused" in message or "actively refused" in message:
        return "connection refused"
    if "max retries exceeded" in message or "failed to establish" in message:
        return "connection failed"
    cleaned = " ".join(str(exc).split())
    return cleaned[:180] or exc.__class__.__name__


def _hf_token() -> str:
    return str(os.getenv("HF_TOKEN") or os.getenv("HUGGINGFACE_API_TOKEN") or config_value("hf_token", "") or "").strip()


def _hf_model() -> str:
    return str(os.getenv("HF_IMAGE_MODEL") or config_value("hf_image_model", DEFAULT_HF_MODEL) or DEFAULT_HF_MODEL).strip()


def _pollinations_enabled() -> bool:
    provider = _provider_setting()
    raw = str(os.getenv("POLLINATIONS_ENABLED") or config_value("pollinations_enabled", "") or "").strip().lower()
    return provider == "pollinations" or raw in {"1", "true", "yes", "on"}


def _pollinations_status() -> dict[str, Any]:
    configured = _pollinations_enabled()
    probe = _pollinations_probe() if configured else {"reachable": False, "reason": "not configured"}
    return {
        "configured": configured,
        "reachable": bool(probe.get("reachable")),
        "url": _pollinations_base_url(),
        "model": _pollinations_model(),
        "reason": str(probe.get("reason") or ""),
        "kind": "Pollinations hosted image endpoint",
    }


def _pollinations_probe() -> dict[str, Any]:
    if requests is None:
        return {"reachable": False, "reason": "requests is not installed."}
    timeout = float(config_value("image_generation_status_timeout_seconds", 2.0))
    try:
        response = requests.head(_pollinations_base_url().removesuffix("/prompt"), timeout=timeout, allow_redirects=True)
    except Exception as exc:
        return {"reachable": False, "reason": _connection_reason(exc)}
    if response.status_code >= 400:
        return {"reachable": False, "reason": f"HTTP {response.status_code}"}
    return {"reachable": True, "reason": "reachable"}


def _pollinations_base_url() -> str:
    return str(os.getenv("POLLINATIONS_IMAGE_BASE_URL") or config_value("pollinations_image_base_url", DEFAULT_POLLINATIONS_BASE_URL) or DEFAULT_POLLINATIONS_BASE_URL).strip().rstrip("/")


def _pollinations_model() -> str:
    return str(os.getenv("POLLINATIONS_IMAGE_MODEL") or config_value("pollinations_image_model", DEFAULT_POLLINATIONS_MODEL) or DEFAULT_POLLINATIONS_MODEL).strip()


def _clean_prompt(prompt: str) -> str:
    return " ".join(str(prompt or "").strip().split())[:2000]


def _blocked_reason(prompt: str) -> str:
    lowered = prompt.lower()
    for pattern in BLOCKED_PATTERNS:
        if re.search(pattern, lowered):
            return "I cannot generate sexual or explicit content involving minors."
    return ""


def _clamp_dimension(value: int) -> int:
    try:
        number = int(value)
    except Exception:
        number = 768
    number = max(256, min(1536, number))
    return int(round(number / 8) * 8)


def _json_loads(value: str, default: Any) -> Any:
    try:
        return json.loads(value or "")
    except Exception:
        return default
