"""Provider-backed text-to-3D generation for studio-quality model workflows."""

from __future__ import annotations

import datetime as dt
import json
import os
import re
import shlex
import subprocess
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from core.config import DATA_DIR, ROOT_DIR, config_value

MODEL_FORMATS = {"glb", "gltf", "obj", "fbx", "stl", "usdz", "3mf"}
TEXTURE_KEYS = {"base_color", "metallic", "normal", "roughness", "emission"}


def generate(
    prompt: str,
    output_dir: str | Path,
    *,
    formats: list[str] | tuple[str, ...] | str | None = None,
    provider: str = "",
    name: str = "",
    shape: str = "",
) -> dict[str, Any]:
    clean_prompt = _clean(prompt)
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    if not bool(config_value("text_to_3d_enabled", True)):
        return _result(False, provider or "disabled", root, summary="Text-to-3D backends are disabled by text_to_3d_enabled.")
    wanted = _formats(formats)
    chain = _provider_chain(provider)
    attempts: list[dict[str, Any]] = []
    for item in chain:
        if item == "meshy":
            result = _generate_meshy(clean_prompt, root / "meshy", wanted, name=name, shape=shape)
        elif item == "tripo":
            result = _generate_tripo(clean_prompt, root / "tripo", wanted, name=name)
        elif item in {"local", "local_command"}:
            result = _generate_local_command(clean_prompt, root / "local", wanted, name=name)
        else:
            result = _result(False, item, root, summary=f"Unsupported text-to-3D provider: {item}")
        attempts.append(_attempt(result))
        if result.get("ok"):
            result["attempts"] = attempts
            return result
    summary = "No text-to-3D backend completed successfully."
    if attempts:
        summary += " " + " ".join(f"{item['provider']}: {item['summary']}" for item in attempts)
    return _result(False, provider or ">".join(chain), root, summary=summary, attempts=attempts)


def status() -> dict[str, Any]:
    providers = _provider_chain("")
    return {
        "enabled": bool(config_value("text_to_3d_enabled", True)),
        "providers": providers,
        "configured": {
            "meshy": bool(_api_key("text_to_3d_meshy_api_key_env", "MESHY_API_KEY")),
            "tripo": bool(_api_key("text_to_3d_tripo_api_key_env", "TRIPO_API_KEY")),
            "local_command": bool(str(config_value("text_to_3d_local_command", "") or "").strip()),
        },
        "summary": "Text-to-3D backend status ready.",
    }


def _generate_meshy(prompt: str, output_dir: Path, formats: set[str], *, name: str, shape: str) -> dict[str, Any]:
    api_key = _api_key("text_to_3d_meshy_api_key_env", "MESHY_API_KEY")
    if not api_key:
        return _result(False, "meshy", output_dir, summary="MESHY_API_KEY is not configured.")
    requests = _requests()
    if requests is None:
        return _result(False, "meshy", output_dir, summary="The requests package is required for Meshy text-to-3D.")
    output_dir.mkdir(parents=True, exist_ok=True)
    base_url = str(config_value("text_to_3d_meshy_base_url", "https://api.meshy.ai/openapi/v2/text-to-3d")).rstrip("/")
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    target_formats = sorted((formats & {"glb", "obj", "fbx", "stl", "usdz", "3mf"}) or {"glb"})
    preview_body: dict[str, Any] = {
        "mode": "preview",
        "prompt": prompt[:600],
        "model_type": str(config_value("text_to_3d_meshy_model_type", "standard")),
        "ai_model": str(config_value("text_to_3d_meshy_ai_model", "meshy-6")),
        "should_remesh": bool(config_value("text_to_3d_meshy_should_remesh", True)),
        "target_polycount": int(config_value("text_to_3d_meshy_target_polycount", 100000)),
        "target_formats": target_formats,
        "auto_size": bool(config_value("text_to_3d_meshy_auto_size", True)),
        "moderation": bool(config_value("text_to_3d_meshy_moderation", True)),
    }
    pose = _pose_mode(prompt, shape)
    if pose:
        preview_body["pose_mode"] = pose
    preview = _http_json(requests, "post", base_url, headers=headers, json=preview_body)
    if not preview["ok"]:
        return _result(False, "meshy", output_dir, summary=preview["summary"], raw=preview)
    preview_id = str((preview.get("json") or {}).get("result") or "")
    if not preview_id:
        return _result(False, "meshy", output_dir, summary="Meshy did not return a preview task id.", raw=preview)
    preview_task = _poll_meshy(requests, base_url, headers, preview_id)
    if not preview_task.get("ok"):
        return _result(False, "meshy", output_dir, summary=preview_task["summary"], task_ids={"preview": preview_id}, raw=preview_task)
    final_task = preview_task["task"]
    task_ids = {"preview": preview_id}
    if bool(config_value("text_to_3d_meshy_refine_enabled", True)):
        refine_body = {
            "mode": "refine",
            "preview_task_id": preview_id,
            "enable_pbr": bool(config_value("text_to_3d_meshy_enable_pbr", True)),
            "target_formats": target_formats,
            "auto_size": bool(config_value("text_to_3d_meshy_auto_size", True)),
        }
        refine = _http_json(requests, "post", base_url, headers=headers, json=refine_body)
        if refine["ok"] and (refine.get("json") or {}).get("result"):
            refine_id = str((refine.get("json") or {}).get("result"))
            task_ids["refine"] = refine_id
            refined_task = _poll_meshy(requests, base_url, headers, refine_id)
            if refined_task.get("ok"):
                final_task = refined_task["task"]
            else:
                task_ids["refine_error"] = refined_task["summary"]
    paths = _download_meshy_outputs(requests, final_task, output_dir, target_formats)
    ok = bool(paths)
    return _result(
        ok,
        "meshy",
        output_dir,
        paths=paths,
        task_ids=task_ids,
        raw={"task": final_task},
        summary=("Meshy text-to-3D model generated." if ok else "Meshy finished but no downloadable model files were found."),
    )


def _generate_tripo(prompt: str, output_dir: Path, formats: set[str], *, name: str) -> dict[str, Any]:
    api_key = _api_key("text_to_3d_tripo_api_key_env", "TRIPO_API_KEY")
    if not api_key:
        return _result(False, "tripo", output_dir, summary="TRIPO_API_KEY is not configured.")
    requests = _requests()
    if requests is None:
        return _result(False, "tripo", output_dir, summary="The requests package is required for Tripo text-to-3D.")
    output_dir.mkdir(parents=True, exist_ok=True)
    base_url = str(config_value("text_to_3d_tripo_base_url", "https://api.tripo3d.ai/v2/openapi")).rstrip("/")
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    body: dict[str, Any] = {
        "type": "text_to_model",
        "prompt": prompt[:1024],
        "model_version": str(config_value("text_to_3d_tripo_model_version", "v3.1-20260211")),
        "texture": bool(config_value("text_to_3d_tripo_texture", True)),
        "pbr": bool(config_value("text_to_3d_tripo_pbr", True)),
        "texture_quality": str(config_value("text_to_3d_tripo_texture_quality", "detailed")),
        "geometry_quality": str(config_value("text_to_3d_tripo_geometry_quality", "detailed")),
        "auto_size": bool(config_value("text_to_3d_tripo_auto_size", True)),
        "export_uv": bool(config_value("text_to_3d_tripo_export_uv", True)),
    }
    face_limit = int(config_value("text_to_3d_tripo_face_limit", 0) or 0)
    if face_limit > 0:
        body["face_limit"] = face_limit
    submit = _http_json(requests, "post", f"{base_url}/task", headers=headers, json=body)
    if not submit["ok"]:
        return _result(False, "tripo", output_dir, summary=submit["summary"], raw=submit)
    submit_json = submit.get("json") or {}
    task_id = _first_text(submit_json, "task_id") or _first_text(submit_json.get("data") or {}, "task_id")
    if not task_id:
        return _result(False, "tripo", output_dir, summary="Tripo did not return a task_id.", raw=submit)
    task = _poll_tripo(requests, base_url, headers, task_id)
    if not task.get("ok"):
        return _result(False, "tripo", output_dir, summary=task["summary"], task_ids={"task": task_id}, raw=task)
    data = task["task"]
    output = data.get("output") or (data.get("data") or {}).get("output") or {}
    paths = _download_tripo_outputs(requests, output, output_dir, formats)
    ok = bool(paths)
    return _result(
        ok,
        "tripo",
        output_dir,
        paths=paths,
        task_ids={"task": task_id},
        raw={"task": data},
        summary=("Tripo text-to-3D model generated." if ok else "Tripo finished but no downloadable model files were found."),
    )


def _generate_local_command(prompt: str, output_dir: Path, formats: set[str], *, name: str) -> dict[str, Any]:
    template = str(config_value("text_to_3d_local_command", "") or "").strip()
    if not template:
        return _result(False, "local_command", output_dir, summary="text_to_3d_local_command is not configured.")
    output_dir.mkdir(parents=True, exist_ok=True)
    replacements = {
        "{prompt}": prompt,
        "{output_dir}": str(output_dir),
        "{formats}": ",".join(sorted(formats)),
        "{name}": _safe_name(name or prompt),
    }
    command_text = template
    for key, value in replacements.items():
        command_text = command_text.replace(key, value)
    command = shlex.split(command_text, posix=False)
    if not command:
        return _result(False, "local_command", output_dir, summary="text_to_3d_local_command resolved to an empty command.")
    timeout = max(30, int(config_value("text_to_3d_timeout_seconds", 900)))
    try:
        completed = subprocess.run(command, cwd=str(output_dir), text=True, capture_output=True, shell=False, timeout=timeout)
    except FileNotFoundError:
        return _result(False, "local_command", output_dir, summary=f"Local text-to-3D command was not found: {command[0]}")
    except subprocess.TimeoutExpired as exc:
        return _result(False, "local_command", output_dir, summary=f"Local text-to-3D command timed out after {timeout} seconds: {exc}")
    paths = _collect_outputs(output_dir, formats)
    ok = completed.returncode == 0 and bool(paths)
    return _result(
        ok,
        "local_command",
        output_dir,
        paths=paths,
        raw={"command": command, "returncode": completed.returncode, "stdout": _bounded(completed.stdout), "stderr": _bounded(completed.stderr)},
        summary="Local text-to-3D command generated model files." if ok else f"Local text-to-3D command failed or produced no model files: {_bounded(completed.stderr or completed.stdout, 500)}",
    )


def _poll_meshy(requests: Any, base_url: str, headers: dict[str, str], task_id: str) -> dict[str, Any]:
    deadline = time.time() + max(30, int(config_value("text_to_3d_timeout_seconds", 900)))
    poll_seconds = max(1.0, float(config_value("text_to_3d_poll_seconds", 5.0)))
    while time.time() < deadline:
        result = _http_json(requests, "get", f"{base_url}/{task_id}", headers=headers)
        if not result["ok"]:
            return {"ok": False, "summary": result["summary"], "raw": result}
        task = result.get("json") or {}
        status = str(task.get("status") or "").upper()
        if status == "SUCCEEDED":
            return {"ok": True, "summary": "Meshy task succeeded.", "task": task}
        if status in {"FAILED", "CANCELED"}:
            error = task.get("task_error") or {}
            return {"ok": False, "summary": f"Meshy task {status.lower()}: {error.get('message') or 'no details'}", "task": task}
        time.sleep(poll_seconds)
    return {"ok": False, "summary": f"Meshy task timed out: {task_id}"}


def _poll_tripo(requests: Any, base_url: str, headers: dict[str, str], task_id: str) -> dict[str, Any]:
    deadline = time.time() + max(30, int(config_value("text_to_3d_timeout_seconds", 900)))
    poll_seconds = max(1.0, float(config_value("text_to_3d_poll_seconds", 5.0)))
    while time.time() < deadline:
        result = _http_json(requests, "get", f"{base_url}/task/{task_id}", headers=headers)
        if not result["ok"]:
            return {"ok": False, "summary": result["summary"], "raw": result}
        raw = result.get("json") or {}
        task = raw.get("data") if isinstance(raw.get("data"), dict) else raw
        status = str(task.get("status") or "").lower()
        if status == "success":
            return {"ok": True, "summary": "Tripo task succeeded.", "task": task}
        if status in {"failed", "banned", "expired", "cancelled", "unknown"}:
            return {"ok": False, "summary": f"Tripo task {status}.", "task": task}
        time.sleep(poll_seconds)
    return {"ok": False, "summary": f"Tripo task timed out: {task_id}"}


def _download_meshy_outputs(requests: Any, task: dict[str, Any], output_dir: Path, target_formats: list[str]) -> dict[str, str]:
    paths: dict[str, str] = {}
    model_urls = task.get("model_urls") if isinstance(task.get("model_urls"), dict) else {}
    for fmt in list(target_formats) + ["mtl"]:
        url = str(model_urls.get(fmt) or "")
        if url:
            downloaded = _download_url(requests, url, output_dir / f"model.{fmt}")
            if downloaded:
                paths[fmt] = str(downloaded)
    if task.get("thumbnail_url"):
        downloaded = _download_url(requests, str(task["thumbnail_url"]), output_dir / "preview.png")
        if downloaded:
            paths["preview"] = str(downloaded)
    for index, texture_set in enumerate(task.get("texture_urls") or []):
        if not isinstance(texture_set, dict):
            continue
        for key in TEXTURE_KEYS:
            url = str(texture_set.get(key) or "")
            if url:
                downloaded = _download_url(requests, url, output_dir / f"texture_{index}_{key}.png")
                if downloaded:
                    paths[f"texture_{index}_{key}"] = str(downloaded)
    return paths


def _download_tripo_outputs(requests: Any, output: dict[str, Any], output_dir: Path, formats: set[str]) -> dict[str, str]:
    paths: dict[str, str] = {}
    model_url = str(output.get("pbr_model") or output.get("model") or output.get("base_model") or "")
    if model_url:
        suffix = _suffix_from_url(model_url) or ".glb"
        key = suffix.lstrip(".").lower()
        downloaded = _download_url(requests, model_url, output_dir / f"model{suffix}")
        if downloaded:
            paths[key] = str(downloaded)
    for image_key in ("rendered_image", "generated_image"):
        url = str(output.get(image_key) or "")
        if url:
            downloaded = _download_url(requests, url, output_dir / f"{image_key}.png")
            if downloaded:
                paths["preview" if image_key == "rendered_image" else image_key] = str(downloaded)
    return paths


def _download_url(requests: Any, url: str, path: Path) -> Path | None:
    timeout = max(15, int(config_value("text_to_3d_download_timeout_seconds", 180)))
    response = requests.get(url, timeout=timeout)
    if int(getattr(response, "status_code", 0)) >= 400:
        return None
    path.parent.mkdir(parents=True, exist_ok=True)
    content = getattr(response, "content", b"")
    path.write_bytes(content)
    return path


def _http_json(requests: Any, method: str, url: str, **kwargs: Any) -> dict[str, Any]:
    timeout = max(15, int(config_value("text_to_3d_request_timeout_seconds", 60)))
    try:
        response = getattr(requests, method)(url, timeout=timeout, **kwargs)
    except Exception as exc:
        return {"ok": False, "summary": f"HTTP {method.upper()} failed: {exc}", "json": {}}
    status = int(getattr(response, "status_code", 0))
    try:
        data = response.json()
    except Exception:
        data = {}
    if status >= 400:
        detail = data.get("message") or data.get("error") or getattr(response, "text", "")
        return {"ok": False, "summary": f"HTTP {status}: {_bounded(detail, 500)}", "json": data, "status_code": status}
    return {"ok": True, "summary": "HTTP request succeeded.", "json": data, "status_code": status}


def _collect_outputs(output_dir: Path, formats: set[str]) -> dict[str, str]:
    paths: dict[str, str] = {}
    for file in output_dir.rglob("*"):
        if not file.is_file():
            continue
        suffix = file.suffix.lower().lstrip(".")
        if suffix in formats or suffix in {"mtl", "png", "jpg", "jpeg"}:
            key = suffix
            if key in {"png", "jpg", "jpeg"}:
                key = "preview"
            if key not in paths:
                paths[key] = str(file)
    return paths


def _provider_chain(provider: str) -> list[str]:
    raw = provider or str(config_value("text_to_3d_provider_chain", "meshy>tripo>local_command") or "")
    items = [item.strip().lower() for item in re.split(r"[>,]", raw) if item.strip()]
    return items or ["meshy", "tripo", "local_command"]


def _formats(formats: list[str] | tuple[str, ...] | str | None) -> set[str]:
    raw = formats if formats is not None else str(config_value("model_3d_studio_default_formats", "glb,obj,preview"))
    if isinstance(raw, str):
        items = [item.strip() for item in re.split(r"[, ]+", raw) if item.strip()]
    else:
        items = [str(item).strip() for item in raw if str(item).strip()]
    wanted = {item.lower().lstrip(".") for item in items}
    return (wanted & (MODEL_FORMATS | {"preview", "blend"})) or {"glb"}


def _api_key(config_key: str, default_env: str) -> str:
    env_name = str(config_value(config_key, default_env) or default_env).strip()
    return os.getenv(env_name, "").strip()


def _requests() -> Any:
    try:
        import requests

        return requests
    except Exception:
        return None


def _result(
    ok: bool,
    provider: str,
    output_dir: Path,
    *,
    paths: dict[str, str] | None = None,
    task_ids: dict[str, Any] | None = None,
    raw: dict[str, Any] | None = None,
    summary: str = "",
    attempts: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "ok": ok,
        "provider": provider,
        "output_dir": str(output_dir),
        "paths": paths or {},
        "task_ids": task_ids or {},
        "raw": raw or {},
        "attempts": attempts or [],
        "created_at": dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "summary": summary or ("Text-to-3D generation succeeded." if ok else "Text-to-3D generation failed."),
    }


def _attempt(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "provider": result.get("provider", "unknown"),
        "ok": bool(result.get("ok")),
        "summary": str(result.get("summary") or ""),
        "paths": result.get("paths") or {},
    }


def _pose_mode(prompt: str, shape: str) -> str:
    if re.search(r"\b(?:human|person|character|avatar|humanoid|man|woman)\b", f"{prompt} {shape}".lower()):
        return str(config_value("text_to_3d_meshy_human_pose_mode", "a-pose") or "a-pose")
    return str(config_value("text_to_3d_meshy_pose_mode", "") or "")


def _suffix_from_url(url: str) -> str:
    path = urlparse(url).path
    suffix = Path(path).suffix.lower()
    return suffix if suffix in {f".{fmt}" for fmt in MODEL_FORMATS} else ""


def _first_text(data: dict[str, Any], key: str) -> str:
    value = data.get(key) if isinstance(data, dict) else ""
    return str(value or "").strip()


def _safe_name(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "-", str(value or "").lower()).strip(".-")
    return cleaned[:48] or "text-to-3d"


def _clean(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip(" ,.!?:;")


def _bounded(text: Any, limit: int = 6000) -> str:
    value = str(text or "").strip()
    return value if len(value) <= limit else value[:limit].rstrip() + "\n... truncated ..."
