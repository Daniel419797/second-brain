"""Cross-page visual continuity review for Friday website design handoffs."""

from __future__ import annotations

import html
import json
import re
from pathlib import Path
from typing import Any

from core import browser_playwright


def review_multipage_site(
    *,
    request: str,
    product_name: str,
    pages: list[dict[str, Any]],
    site_brief: dict[str, Any],
    design_root: str | Path,
) -> dict[str, Any]:
    root = Path(design_root) / "site-continuity"
    root.mkdir(parents=True, exist_ok=True)
    findings: list[str] = []
    artifacts: list[str] = []
    selected = [page for page in pages if page.get("frontend_handoff_allowed")]
    expected_nav = [str(item.get("label") or "") for item in _website_page_specs(request)]
    brand = _clean(product_name) or _clean(site_brief.get("product_name") or "")
    if len(selected) != len(pages):
        findings.append("not every requested page has an accepted handoff")
    providers = {_clean(page.get("source_provider") or "").lower() for page in selected if _clean(page.get("source_provider"))}
    if providers and any("stitch" not in provider for provider in providers):
        findings.append("multi-page website mixes non-Stitch design sources")
    signatures: list[dict[str, Any]] = []
    page_docs: list[str] = []
    for page in selected:
        variant = page.get("selected_variant") if isinstance(page.get("selected_variant"), dict) else {}
        html_text = _variant_html(variant)
        visible = _visible_text(html_text)
        label = str(page.get("label") or page.get("id") or "page")
        if brand and not re.search(re.escape(brand), visible, flags=re.IGNORECASE):
            findings.append(f"{label} page does not visibly carry the site brand")
        missing_nav = [item for item in expected_nav if item and not re.search(rf"\b{re.escape(item)}\b", visible, flags=re.IGNORECASE)]
        if len(missing_nav) >= max(2, len(expected_nav) - 1):
            findings.append(f"{label} page is missing most shared navigation labels")
        browser_review = variant.get("browser_visual_review") if isinstance(variant.get("browser_visual_review"), dict) else {}
        if browser_review and not browser_review.get("passed"):
            findings.append(f"{label} page failed browser variant review")
        signature = _page_signature(html_text)
        signatures.append({"page": label, **signature})
        page_docs.append(_page_panel(label, html_text))
    findings.extend(_signature_findings(signatures))
    site = ((site_brief.get("design_context") or {}).get("site_continuity") or {}).get("site_design_system") if isinstance(site_brief.get("design_context"), dict) else {}
    if not site:
        findings.append("shared site design system was not generated")
    combined_path = root / "site-continuity.html"
    combined_path.write_text(_combined_document(page_docs), encoding="utf-8")
    artifacts.append(str(combined_path))
    visual_artifacts: list[str] = []
    if browser_playwright.available().get("available"):
        screenshot_dir = root / "screenshots"
        audit = browser_playwright.visual_audit(
            combined_path.resolve().as_uri(),
            screenshot_dir=screenshot_dir,
            viewports=[{"label": "desktop", "width": 1440, "height": 1200}],
        )
        visual_artifacts.extend(str(item) for item in (audit.get("screenshots") or []))
        if not audit.get("ok"):
            findings.extend(str(item) for item in (audit.get("findings") or []))
    report = {
        "ok": not findings,
        "status": "passed" if not findings else "failed",
        "findings": _dedupe(findings),
        "expected_navigation": expected_nav,
        "page_count": len(pages),
        "selected_page_count": len(selected),
        "signatures": signatures,
        "method": "cross_page_html_and_browser_continuity_review",
        "artifacts": _dedupe([*artifacts, *visual_artifacts]),
    }
    report_path = root / "site-continuity-review.json"
    report_path.write_text(json.dumps(report, ensure_ascii=True, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    report["artifacts"] = _dedupe([*report["artifacts"], str(report_path)])
    return report


def _variant_html(variant: dict[str, Any]) -> str:
    if _clean(variant.get("html") or variant.get("htmlContent")):
        return str(variant.get("html") or variant.get("htmlContent"))
    path = Path(str(variant.get("html_path") or ""))
    if path.exists() and path.is_file():
        return path.read_text(encoding="utf-8", errors="ignore")
    return ""


def _page_signature(html_text: str) -> dict[str, Any]:
    lower = html_text.lower()
    h1_size = _first_font_size(lower, "h1")
    body_font = _first_font_family(lower)
    section_count = lower.count("<section")
    nav_count = lower.count("<nav")
    cards = lower.count("card") + lower.count("<article")
    return {"h1_size": h1_size, "body_font": body_font, "sections": section_count, "navs": nav_count, "cards": cards}


def _signature_findings(signatures: list[dict[str, Any]]) -> list[str]:
    findings: list[str] = []
    if len(signatures) < 2:
        return findings
    h1_values = [int(item.get("h1_size") or 0) for item in signatures if int(item.get("h1_size") or 0) > 0]
    if len(h1_values) >= 2 and max(h1_values) - min(h1_values) > 34:
        findings.append("pages have inconsistent headline scale")
    fonts = {_clean(item.get("body_font")).lower() for item in signatures if _clean(item.get("body_font"))}
    if len(fonts) > 2:
        findings.append("pages have inconsistent typography families")
    if any(int(item.get("navs") or 0) == 0 for item in signatures):
        findings.append("one or more pages are missing a shared navigation structure")
    return findings


def _first_font_size(lower_html: str, tag: str) -> int:
    pattern = rf"{tag}[^>]*style=['\"][^'\"]*font-size:\s*(\d+)px"
    match = re.search(pattern, lower_html)
    return int(match.group(1)) if match else 0


def _first_font_family(lower_html: str) -> str:
    match = re.search(r"font-family:\s*([^;'\"]+)", lower_html)
    return _clean(match.group(1)) if match else ""


def _page_panel(label: str, html_text: str) -> str:
    return f"<section class='continuity-page'><h2>{html.escape(label)}</h2><div class='continuity-frame'>{html_text}</div></section>"


def _combined_document(page_docs: list[str]) -> str:
    return (
        "<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
        "<style>body{margin:0;font-family:Inter,Arial,sans-serif;background:#111;color:#f8f8f8}.continuity-page{padding:32px;border-bottom:1px solid #333}.continuity-frame{background:#fff;color:#111;overflow:hidden}</style>"
        "</head><body>"
        + "\n".join(page_docs)
        + "</body></html>"
    )


def _website_page_specs(request: str) -> list[dict[str, str]]:
    lower = str(request or "").lower()
    labels = ["Home", "About", "Services", "Contact"]
    if "pricing" in lower:
        labels = ["Home", "Product", "Pricing", "Contact"]
    return [{"id": label.lower().replace(" ", "-"), "label": label} for label in labels]


def _visible_text(html_text: str) -> str:
    text = re.sub(r"<(script|style)\b[^>]*>.*?</\1>", " ", html_text or "", flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<[^>]+>", " ", text)
    return _clean(text)


def _clean(value: Any) -> str:
    return " ".join(str(value or "").replace("\r", " ").split())


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
