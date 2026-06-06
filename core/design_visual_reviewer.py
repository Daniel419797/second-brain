"""Browser-based visual review for provider design variants."""

from __future__ import annotations

import html
import json
import re
from pathlib import Path
from typing import Any

from core import browser_playwright, design_vision_critic
from core.config import config_value


def review_variants(
    variants: list[dict[str, Any]],
    *,
    design_root: str | Path,
    request: str = "",
    required: bool = True,
) -> dict[str, Any]:
    """Render each variant in a browser and attach screenshot-based findings."""

    root = Path(design_root)
    out_dir = root / "visual-variant-review"
    out_dir.mkdir(parents=True, exist_ok=True)
    reviewed: list[dict[str, Any]] = []
    artifacts: list[str] = []
    available = browser_playwright.available()
    if required and not available.get("available"):
        payload = {
            "ok": False,
            "status": "blocked",
            "summary": available.get("install_hint") or available.get("reason") or "Playwright is not available for visual variant review.",
            "provider": available,
            "variants": [{**variant, "browser_visual_review": {"passed": False, "findings": ["Playwright is unavailable."]}} for variant in variants],
            "artifacts": [],
        }
        return _write_report(out_dir, payload)
    if not available.get("available"):
        payload = {
            "ok": True,
            "status": "skipped",
            "summary": "Visual variant review skipped because Playwright is unavailable and review is not required.",
            "provider": available,
            "variants": variants,
            "artifacts": [],
        }
        return _write_report(out_dir, payload)
    for index, variant in enumerate(variants, start=1):
        variant_id = _safe_id(str(variant.get("id") or variant.get("screenId") or f"variant-{index}"))
        html_text = _variant_html(variant)
        html_path = out_dir / f"{index:02d}-{variant_id}.html"
        html_path.write_text(_document(html_text, title=str(variant.get("label") or variant_id)), encoding="utf-8")
        screenshot_dir = out_dir / f"{index:02d}-{variant_id}-screenshots"
        result = browser_playwright.visual_audit(
            html_path.resolve().as_uri(),
            screenshot_dir=screenshot_dir,
            viewports=[
                {"label": "desktop", "width": 1440, "height": 900},
                {"label": "mobile", "width": 390, "height": 844},
            ],
        )
        vision = design_vision_critic.review_variant(html=html_text, audit=result, request=request)
        findings = _dedupe(
            [
                *(str(item) for item in (result.get("findings") or [])),
                *_content_findings(html_text, result, request),
                *(str(item) for item in (vision.get("findings") or [])),
            ]
        )
        content_penalty = min(28, len(_content_findings(html_text, result, request)) * 10)
        score = max(0, min(100, int(vision.get("score") or 0) - content_penalty))
        passed = (
            bool(result.get("ok"))
            and bool(vision.get("passed"))
            and not findings
            and score >= int(config_value("design_variant_visual_min_score", 72) or 72)
        )
        review = {
            "passed": passed,
            "status": "passed" if passed else "failed",
            "score": score,
            "findings": findings,
            "screenshots": result.get("screenshots") or [],
            "contexts": result.get("contexts") or [],
            "html_path": str(html_path),
            "vision_review": vision,
        }
        artifacts.extend([str(html_path), *(str(item) for item in (result.get("screenshots") or []))])
        reviewed.append({**variant, "browser_visual_review": review})
    payload = {
        "ok": all((variant.get("browser_visual_review") or {}).get("passed") for variant in reviewed) if reviewed else False,
        "status": "passed" if reviewed and all((variant.get("browser_visual_review") or {}).get("passed") for variant in reviewed) else "failed",
        "summary": _summary(reviewed),
        "variants": reviewed,
        "artifacts": artifacts,
    }
    return _write_report(out_dir, payload)


def _content_findings(html_text: str, audit: dict[str, Any], request: str) -> list[str]:
    lower_html = str(html_text or "").lower()
    visible_words = len(re.findall(r"[A-Za-z][A-Za-z'-]{2,}", _strip_tags(html_text)))
    findings: list[str] = []
    section_count = lower_html.count("<section")
    request_lower = str(request or "").lower()
    if any(term in request_lower for term in ("landing page", "website", "product page")) and section_count < 3:
        findings.append("variant is too shallow; expected hero plus at least two supporting content sections")
    if "<footer" in lower_html and section_count <= 1:
        findings.append("footer appears before enough page content")
    if visible_words < 55 and any(term in request_lower for term in ("landing", "website", "site")):
        findings.append("visible copy is too thin for a credible website")
    for item in audit.get("contexts") or []:
        visual = item.get("visual") if isinstance(item, dict) and isinstance(item.get("visual"), dict) else {}
        viewport = item.get("viewport") if isinstance(item, dict) and isinstance(item.get("viewport"), dict) else {}
        label = str(viewport.get("label") or "viewport")
        for image in visual.get("images") or []:
            rect = image.get("rect") if isinstance(image.get("rect"), dict) else {}
            if not rect.get("visible"):
                continue
            displayed_width = float(rect.get("width") or 0)
            natural_width = int(image.get("naturalWidth") or 0)
            if displayed_width >= 320 and natural_width and natural_width < displayed_width * 1.15:
                findings.append(f"{label}: visible hero/media image is likely too low-resolution for its rendered size")
                break
    return findings


def _variant_html(variant: dict[str, Any]) -> str:
    if variant.get("html"):
        return str(variant.get("html") or "")
    html_path = variant.get("html_path")
    if html_path and Path(str(html_path)).exists():
        return Path(str(html_path)).read_text(encoding="utf-8", errors="ignore")
    image_path = variant.get("image_path")
    if image_path and Path(str(image_path)).exists():
        return f"<main><section><img src='{html.escape(Path(str(image_path)).resolve().as_uri())}' alt='Generated design variant' /></section></main>"
    return "<main><section><p>No HTML handoff was available for this variant.</p></section></main>"


def _document(body: str, *, title: str) -> str:
    text = str(body or "")
    if re.search(r"<html\b", text, flags=re.IGNORECASE):
        return text
    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width, initial-scale=1'>"
        f"<title>{html.escape(title)}</title>"
        "<style>body{margin:0;font-family:Inter,Arial,sans-serif}img,svg,video,canvas{max-width:100%;height:auto}</style>"
        "</head><body>"
        f"{text}"
        "</body></html>"
    )


def _write_report(out_dir: Path, payload: dict[str, Any]) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    report_path = out_dir / "visual-variant-review.json"
    report_path.write_text(json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    return {**payload, "artifacts": _dedupe([*(payload.get("artifacts") or []), str(report_path)])}


def _summary(variants: list[dict[str, Any]]) -> str:
    failed = [variant for variant in variants if not (variant.get("browser_visual_review") or {}).get("passed")]
    if not variants:
        return "No variants were available for browser visual review."
    if failed:
        first = (failed[0].get("browser_visual_review") or {}).get("findings") or ["visual review failed"]
        return f"Browser visual review rejected {len(failed)}/{len(variants)} variant(s): {first[0]}"
    return f"Browser visual review passed for {len(variants)} variant(s)."


def _strip_tags(value: str) -> str:
    return re.sub(r"<[^>]+>", " ", str(value or ""))


def _safe_id(value: str) -> str:
    return re.sub(r"[^a-z0-9_-]+", "-", str(value or "variant").lower()).strip("-") or "variant"


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
