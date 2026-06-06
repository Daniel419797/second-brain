"""Screenshot-based visual critique helpers for Friday design variants."""

from __future__ import annotations

import math
import re
from io import BytesIO
from pathlib import Path
from typing import Any


def review_variant(
    *,
    html: str,
    audit: dict[str, Any],
    request: str = "",
) -> dict[str, Any]:
    """Score actual rendered screenshots plus browser layout metrics."""

    findings: list[str] = []
    dimensions: dict[str, Any] = {}
    context_scores: list[int] = []
    for item in audit.get("contexts") or []:
        if not isinstance(item, dict):
            continue
        context_scores.append(_score_context(item, findings))
    screenshot_scores = [_score_screenshot(path, findings) for path in audit.get("screenshots") or []]
    section_count = str(html or "").lower().count("<section")
    visible_words = len(re.findall(r"[A-Za-z][A-Za-z'-]{2,}", _strip_tags(html)))
    request_lower = str(request or "").lower()
    if any(term in request_lower for term in ("landing", "website", "site")):
        if section_count < 3:
            findings.append("screenshot critic: page content depth is too shallow for a credible web page")
        if visible_words < 80:
            findings.append("screenshot critic: visible copy is too thin for a complete website")
    if context_scores or screenshot_scores:
        score = round(sum([*context_scores, *screenshot_scores]) / max(1, len(context_scores) + len(screenshot_scores)))
    else:
        score = 35
        findings.append("screenshot critic: no screenshot or browser context was available")
    severe = [item for item in findings if any(term in item.lower() for term in ("blank", "empty", "overflow", "too shallow", "too thin", "uncompiled", "broken image", "low-resolution"))]
    dimensions["context_scores"] = context_scores
    dimensions["screenshot_scores"] = screenshot_scores
    return {
        "passed": score >= 72 and not severe,
        "score": max(0, min(100, int(score))),
        "findings": _dedupe(findings),
        "dimensions": dimensions,
        "method": "screenshot_pixel_and_browser_context_review",
    }


def _score_context(item: dict[str, Any], findings: list[str]) -> int:
    viewport = item.get("viewport") if isinstance(item.get("viewport"), dict) else {}
    visual = item.get("visual") if isinstance(item.get("visual"), dict) else {}
    label = str(viewport.get("label") or f"{viewport.get('width', '?')}x{viewport.get('height', '?')}")
    width = int(viewport.get("width") or (visual.get("viewport") or {}).get("width") or 0)
    height = int(viewport.get("height") or (visual.get("viewport") or {}).get("height") or 0)
    score = 100
    headings = visual.get("headings") if isinstance(visual.get("headings"), list) else []
    h1 = next((heading for heading in headings if str(heading.get("tag") or "").lower() == "h1"), {})
    h1_size = float(h1.get("fontSize") or 0)
    h1_height = float(h1.get("height") or 0)
    h1_bottom = float(h1.get("bottom") or 0)
    if width >= 900 and (h1_size > 84 or h1_height > height * 0.48):
        findings.append(f"{label}: type scale overwhelms the first viewport")
        score -= 22
    if width < 600 and h1_size > 46:
        findings.append(f"{label}: mobile headline scale is too large")
        score -= 18
    if height and h1_bottom > height * 0.98:
        findings.append(f"{label}: primary headline is clipped below the first viewport")
        score -= 18
    first_text = int(visual.get("firstViewportTextLength") or 0)
    if first_text < 35:
        findings.append(f"{label}: first viewport is too empty to judge product value")
        score -= 24
    if bool(visual.get("horizontalOverflow")):
        findings.append(f"{label}: rendered layout has horizontal overflow")
        score -= 24
    clipped = visual.get("clipped") if isinstance(visual.get("clipped"), list) else []
    if len(clipped) >= 2:
        findings.append(f"{label}: multiple visible elements are clipped or outside the viewport")
        score -= 18
    style_health = visual.get("styleHealth") if isinstance(visual.get("styleHealth"), dict) else {}
    miss_ratio = float(style_health.get("utilityMissRatio") or 0)
    if miss_ratio >= 0.45:
        findings.append(f"{label}: utility-class styling appears uncompiled")
        score -= 26
    images = visual.get("images") if isinstance(visual.get("images"), list) else []
    visible_images = [image for image in images if isinstance(image, dict) and (image.get("rect") or {}).get("visible")]
    for image in visible_images:
        rect = image.get("rect") if isinstance(image.get("rect"), dict) else {}
        natural_width = int(image.get("naturalWidth") or 0)
        natural_height = int(image.get("naturalHeight") or 0)
        displayed_width = float(rect.get("width") or 0)
        if not image.get("complete") or natural_width <= 1 or natural_height <= 1:
            findings.append(f"{label}: visible media includes a broken image")
            score -= 22
            break
        if displayed_width >= 420 and natural_width < displayed_width * 1.25:
            findings.append(f"{label}: visible media is likely too low-resolution for its rendered size")
            score -= 18
            break
    interactives = visual.get("interactives") if isinstance(visual.get("interactives"), list) else []
    if not interactives:
        findings.append(f"{label}: no clear interactive action is visible")
        score -= 10
    return max(0, min(100, score))


def _score_screenshot(path: str, findings: list[str]) -> int:
    try:
        from PIL import Image, ImageFilter, ImageStat
    except Exception:
        return 72
    try:
        image = Image.open(Path(path))
        image.load()
    except Exception:
        findings.append("screenshot critic: screenshot could not be decoded")
        return 20
    width, height = image.size
    if width < 320 or height < 240:
        findings.append("screenshot critic: screenshot dimensions are too small")
        return 30
    sample = image.convert("RGB").resize((min(320, width), max(1, int(height * min(320, width) / max(1, width)))))
    stat = ImageStat.Stat(sample)
    channel_std = sum(float(value) for value in stat.stddev) / 3.0
    colors = len(sample.convert("P", palette=Image.ADAPTIVE, colors=64).getcolors(maxcolors=100000) or [])
    edges = sample.convert("L").filter(ImageFilter.FIND_EDGES)
    edge_stat = ImageStat.Stat(edges)
    edge_mean = float(edge_stat.mean[0] or 0)
    score = 100
    if channel_std < 9 or colors <= 4:
        findings.append("screenshot critic: screenshot appears blank, washed out, or visually flat")
        score -= 36
    if edge_mean < 2.5:
        findings.append("screenshot critic: screenshot has very low detail/edge clarity")
        score -= 22
    if _mostly_one_tone(stat.mean, stat.stddev):
        findings.append("screenshot critic: first viewport lacks enough visual contrast")
        score -= 18
    return max(0, min(100, score))


def inspect_image_bytes(data: bytes) -> dict[str, Any]:
    """Validate and measure a downloaded image payload."""

    if not data:
        return {"ok": False, "reason": "empty_image"}
    try:
        from PIL import Image
        image = Image.open(BytesIO(data))
        width, height = image.size
        image.verify()
        return {"ok": True, "width": int(width), "height": int(height), "format": str(image.format or "").lower()}
    except Exception as exc:
        dimensions = _header_dimensions(data)
        if dimensions.get("ok"):
            return dimensions
        return {"ok": False, "reason": "image_decode_failed", "detail": str(exc)[:200]}


def _header_dimensions(data: bytes) -> dict[str, Any]:
    if data.startswith(b"\x89PNG\r\n\x1a\n") and len(data) >= 24:
        return {"ok": True, "width": int.from_bytes(data[16:20], "big"), "height": int.from_bytes(data[20:24], "big"), "format": "png"}
    if data[:6] in {b"GIF87a", b"GIF89a"} and len(data) >= 10:
        return {"ok": True, "width": int.from_bytes(data[6:8], "little"), "height": int.from_bytes(data[8:10], "little"), "format": "gif"}
    if data.startswith(b"\xff\xd8"):
        index = 2
        while index + 9 < len(data):
            if data[index] != 0xFF:
                index += 1
                continue
            marker = data[index + 1]
            length = int.from_bytes(data[index + 2:index + 4], "big")
            if marker in {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}:
                return {"ok": True, "width": int.from_bytes(data[index + 7:index + 9], "big"), "height": int.from_bytes(data[index + 5:index + 7], "big"), "format": "jpeg"}
            index += max(2, length + 2)
    return {"ok": False, "reason": "unsupported_image_header"}


def _mostly_one_tone(means: list[float], stddevs: list[float]) -> bool:
    if not means or not stddevs:
        return False
    spread = max(means) - min(means)
    return spread < 7 and sum(stddevs) / max(1, len(stddevs)) < 14


def _strip_tags(value: str) -> str:
    return re.sub(r"<[^>]+>", " ", str(value or ""))


def _dedupe(values: list[Any]) -> list[Any]:
    output: list[Any] = []
    seen: set[str] = set()
    for item in values:
        marker = str(item)
        if not marker or marker in seen:
            continue
        seen.add(marker)
        output.append(item)
    return output
