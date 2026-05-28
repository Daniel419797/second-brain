"""Tool wrapper for Friday image generation."""

from __future__ import annotations

from typing import Any

from core import image_generation


def execute(inputs: dict[str, Any]) -> str:
    action = str(inputs.get("action") or "generate").strip().lower()
    try:
        if action == "status":
            status = image_generation.status()
            local = status.get("local_stable_diffusion") or {}
            hf = status.get("hugging_face") or {}
            pollinations = status.get("pollinations") or {}
            local_state = "reachable" if local.get("reachable") else f"not reachable ({local.get('reason') or 'not checked'})"
            hosted_state = "reachable" if pollinations.get("reachable") else f"not ready ({pollinations.get('reason') or 'not configured'})"
            if status.get("ready"):
                return (
                    "Image generation is ready. "
                    f"Local Stable Diffusion: {local_state} at {local.get('url') or 'not set'}. "
                    f"Hugging Face configured: {'yes' if hf.get('configured') else 'no'}. "
                    f"Pollinations hosted provider: {hosted_state}."
                )
            return (
                "Image generation is not ready yet. "
                f"Local Stable Diffusion: {local_state} at {local.get('url') or 'not set'}. "
                f"Hugging Face configured: {'yes' if hf.get('configured') else 'no'}. "
                f"Pollinations hosted provider: {hosted_state}. "
                f"{status.get('setup_hint')}"
            )
        if action == "list":
            items = image_generation.list_images(limit=_int(inputs.get("limit"), 8))
            if not items:
                return "No image generation requests found."
            return "\n".join(_format_item(item) for item in items[:8])
        if action == "generate":
            prompt = str(inputs.get("prompt") or inputs.get("target") or "").strip()
            if not prompt:
                return "Tell me what image to generate."
            result = image_generation.generate_image(
                prompt,
                negative_prompt=str(inputs.get("negative_prompt") or ""),
                width=_int(inputs.get("width"), 768),
                height=_int(inputs.get("height"), 768),
                steps=_int(inputs.get("steps"), 24),
                provider=str(inputs.get("provider") or "auto"),
            )
            if result.get("ok"):
                return f"Image generated: {result.get('path')}"
            return f"Image generation {result.get('status')}: {result.get('reason')}"
    except Exception as exc:
        return f"Image generation failed: {exc}"
    return "Unknown image generation action."


def _format_item(item: dict[str, Any]) -> str:
    target = item.get("path") or item.get("reason") or ""
    return f"#{item.get('id')} [{item.get('status')}] {item.get('prompt')} -> {target}"


def _int(value: Any, default: int) -> int:
    try:
        return int(value)
    except Exception:
        return default
