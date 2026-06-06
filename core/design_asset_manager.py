"""Safe remote asset fetch helpers for Friday design providers."""

from __future__ import annotations

import ipaddress
import socket
import urllib.error as urlerror
import urllib.parse as urlparse
import urllib.request as urlrequest
from pathlib import Path
from typing import Any

from core import design_vision_critic
from core.config import config_value


TEXT_MIME_PREFIXES = ("text/", "application/json", "application/xhtml", "application/xml")
IMAGE_MIME_PREFIXES = ("image/",)


def download_text(url: str, *, max_bytes: int | None = None, timeout: int | None = None) -> dict[str, Any]:
    """Download bounded text from a public https URL."""

    limit = int(max_bytes or config_value("design_remote_text_max_bytes", 2_000_000) or 2_000_000)
    return _download(url, max_bytes=limit, timeout=timeout, allowed_mime_prefixes=TEXT_MIME_PREFIXES, decode=True)


def download_binary(url: str, path: str | Path, *, max_bytes: int | None = None, timeout: int | None = None) -> dict[str, Any]:
    """Download bounded binary asset from a public https URL."""

    limit = int(max_bytes or config_value("design_remote_binary_max_bytes", 8_000_000) or 8_000_000)
    result = _download(url, max_bytes=limit, timeout=timeout, allowed_mime_prefixes=IMAGE_MIME_PREFIXES, decode=False)
    if result.get("ok"):
        image = design_vision_critic.inspect_image_bytes(result.get("content_bytes") or b"")
        if not image.get("ok"):
            return {
                **{k: v for k, v in result.items() if k != "content_bytes"},
                "ok": False,
                "reason": image.get("reason") or "image_decode_failed",
                "image_validation": image,
            }
        min_width = int(config_value("design_remote_image_min_width", 16) or 16)
        min_height = int(config_value("design_remote_image_min_height", 16) or 16)
        max_pixels = int(config_value("design_remote_image_max_pixels", 25_000_000) or 25_000_000)
        width = int(image.get("width") or 0)
        height = int(image.get("height") or 0)
        if width < min_width or height < min_height:
            return {
                **{k: v for k, v in result.items() if k != "content_bytes"},
                "ok": False,
                "reason": "image_dimensions_too_small",
                "image_validation": image,
                "min_width": min_width,
                "min_height": min_height,
            }
        if width * height > max_pixels:
            return {
                **{k: v for k, v in result.items() if k != "content_bytes"},
                "ok": False,
                "reason": "image_dimensions_exceed_limit",
                "image_validation": image,
                "max_pixels": max_pixels,
            }
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(result.get("content_bytes") or b"")
        result = {k: v for k, v in result.items() if k != "content_bytes"}
        result["image"] = image
        result["path"] = str(target)
    return result


def _download(
    url: str,
    *,
    max_bytes: int,
    timeout: int | None,
    allowed_mime_prefixes: tuple[str, ...],
    decode: bool,
) -> dict[str, Any]:
    parsed = urlparse.urlparse(str(url or "").strip())
    allowed = _url_allowed(parsed)
    if not allowed.get("ok"):
        return {"ok": False, "reason": allowed.get("reason") or "url_not_allowed", "url": _redact_url(url)}
    request_timeout = int(timeout or config_value("design_remote_fetch_timeout_seconds", 30) or 30)
    try:
        request = urlrequest.Request(
            parsed.geturl(),
            headers={
                "User-Agent": str(config_value("design_remote_fetch_user_agent", "FridayDesignBot/1.0 (+research metadata only)") or ""),
                "Accept": "text/html,application/xhtml+xml,application/json,image/*;q=0.8,*/*;q=0.5",
            },
        )
        with urlrequest.urlopen(request, timeout=request_timeout) as response:
            content_type = str(response.headers.get("Content-Type") or "").split(";")[0].strip().lower()
            content_length = response.headers.get("Content-Length")
            if content_length and int(content_length) > max_bytes:
                return {"ok": False, "reason": "content_length_exceeds_limit", "url": _redact_url(url), "content_length": int(content_length), "max_bytes": max_bytes}
            if content_type and not any(content_type.startswith(prefix) for prefix in allowed_mime_prefixes):
                return {"ok": False, "reason": "mime_type_not_allowed", "url": _redact_url(url), "content_type": content_type}
            data = _read_limited(response, max_bytes=max_bytes)
    except (OSError, ValueError, urlerror.URLError) as exc:
        return {"ok": False, "reason": "download_failed", "detail": str(exc)[:300], "url": _redact_url(url)}
    if decode:
        return {
            "ok": True,
            "url": _redact_url(url),
            "content_type": content_type,
            "bytes": len(data),
            "text": data.decode("utf-8", errors="ignore"),
        }
    return {"ok": True, "url": _redact_url(url), "content_type": content_type, "bytes": len(data), "content_bytes": data}


def _read_limited(response: Any, *, max_bytes: int) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = response.read(min(64 * 1024, max_bytes + 1 - total))
        if not chunk:
            break
        chunks.append(chunk)
        total += len(chunk)
        if total > max_bytes:
            raise ValueError(f"remote asset exceeds {max_bytes} bytes")
    return b"".join(chunks)


def _url_allowed(parsed: urlparse.ParseResult) -> dict[str, Any]:
    if parsed.scheme.lower() != "https":
        return {"ok": False, "reason": "only_https_urls_allowed"}
    host = (parsed.hostname or "").strip().lower()
    if not host:
        return {"ok": False, "reason": "missing_hostname"}
    if host in {"localhost", "127.0.0.1", "::1"} or host.endswith(".local"):
        return {"ok": False, "reason": "local_hosts_blocked"}
    try:
        ip = ipaddress.ip_address(host)
        if ip.is_private or ip.is_loopback or ip.is_link_local:
            return {"ok": False, "reason": "private_ip_blocked"}
    except ValueError:
        pass
    if bool(config_value("design_remote_resolve_hosts_for_private_ip_check", False)):
        try:
            for _, _, _, _, sockaddr in socket.getaddrinfo(host, None):
                ip = ipaddress.ip_address(sockaddr[0])
                if ip.is_private or ip.is_loopback or ip.is_link_local:
                    return {"ok": False, "reason": "resolved_private_ip_blocked"}
        except OSError:
            return {"ok": False, "reason": "hostname_resolution_failed"}
    allowlist = [str(item).strip().lower() for item in (config_value("design_remote_asset_allowed_hosts", []) or []) if str(item).strip()]
    if allowlist and not any(host == item or host.endswith(f".{item}") for item in allowlist):
        return {"ok": False, "reason": "host_not_allowlisted", "host": host}
    return {"ok": True}


def _redact_url(url: str) -> str:
    parsed = urlparse.urlparse(str(url or ""))
    return urlparse.urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", "[redacted]" if parsed.query else "", ""))
