"""Universal external design import and Next.js implementation workflow."""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import mimetypes
import re
import shutil
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from html import escape
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

from core import design_providers, product_studio_gates
from core.config import resolve_coding_root

SUPPORTED_SOURCE_TYPES = {
    "raw_html",
    "html",
    "screenshot",
    "image",
    "figma",
    "figma_export",
    "stitch",
    "stitch_output",
    "v0",
    "v0_output",
    "uploaded_file",
    "design_brief",
    "brief",
    "existing_url",
    "url",
    "ai_design",
    "other_ai",
}

HTML_LIKE_TYPES = {"raw_html", "html", "stitch", "stitch_output", "v0", "v0_output", "ai_design", "other_ai"}
BRIEF_TYPES = {"design_brief", "brief"}
IMAGE_TYPES = {"screenshot", "image"}
FILE_TYPES = {"uploaded_file", "figma", "figma_export"}
URL_TYPES = {"existing_url", "url"}


@dataclass
class ImportedDesignPage:
    id: str
    route: str
    label: str
    source_type: str
    source_format: str
    fidelity: str
    html: str
    react_code: str
    source_artifacts: list[str]
    analysis: dict[str, Any]
    warnings: list[str]


def supported_sources() -> dict[str, Any]:
    """Return the public design import contract."""

    return {
        "source_types": sorted(SUPPORTED_SOURCE_TYPES),
        "flow": [
            "save_source_design",
            "analyze_layout_assets_routes_copy_interactions",
            "write_frontend_handoff_json",
            "create_nextjs_project",
            "implement_routes_components_assets",
            "run_optional_install_build_browser_gates",
            "write_preview_screenshots_and_proof",
        ],
        "fidelity": {
            "exact_html": "Raw HTML/Stitch/v0 HTML can be preserved as a static document route when that is safest.",
            "native_react": "Simple supported HTML can be converted into Friday's native Next.js surface.",
            "reference_reconstruction": "Images, briefs, and non-HTML exports are saved and reconstructed from available evidence; they are not treated as exact visual code.",
        },
    }


def import_and_implement(
    *,
    request: str = "",
    product_name: str = "",
    source_type: str = "raw_html",
    source: str = "",
    source_path: str = "",
    source_url: str = "",
    source_base64: str = "",
    data_url: str = "",
    root: str | Path = "",
    project_slug: str = "",
    pages: list[dict[str, Any]] | None = None,
    verify: bool = True,
    install: bool = True,
    tests: bool = True,
    audits: bool = False,
    browser: bool = True,
    preview: bool = True,
    timeout: int | None = None,
) -> dict[str, Any]:
    """Import an arbitrary design source, create a handoff, implement Next.js, and optionally verify it."""

    normalized_type = _normalize_source_type(source_type)
    project_root = _resolve_project_root(root, project_slug, product_name, request)
    import_root = project_root / ".friday" / "design-import"
    design_root = project_root / ".friday" / "design"
    import_root.mkdir(parents=True, exist_ok=True)
    design_root.mkdir(parents=True, exist_ok=True)

    page_inputs = _normalize_page_inputs(
        pages,
        source_type=normalized_type,
        source=source,
        source_path=source_path,
        source_url=source_url,
        source_base64=source_base64,
        data_url=data_url,
    )
    imported_pages = [
        _materialize_page(page, index=index, project_root=project_root, import_root=import_root, request=request, product_name=product_name)
        for index, page in enumerate(page_inputs, start=1)
    ]
    if not imported_pages:
        raise ValueError("No design source could be imported.")
    _normalize_imported_pages(imported_pages, project_root)

    handoff_artifacts = _write_handoff_artifacts(
        project_root,
        imported_pages,
        request=request,
        product_name=product_name,
        design_root=design_root,
        import_root=import_root,
    )
    applied = _apply_imported_pages(project_root, imported_pages, request=request, product_name=product_name)

    gate_results: dict[str, Any] = {}
    if verify:
        gate_results = product_studio_gates.execute_gates(
            project_root,
            stack={"stack": "nextjs", "label": "Next.js App Router"},
            install=install,
            tests=tests,
            audits=audits,
            browser=browser,
            preview=preview,
            timeout=timeout,
            request=request,
        )

    proof_path = _write_proof_report(
        project_root,
        imported_pages,
        applied=applied,
        gate_results=gate_results,
        request=request,
        product_name=product_name,
        handoff_artifacts=handoff_artifacts,
    )
    artifacts = _dedupe(
        [
            *handoff_artifacts,
            *(applied.get("artifacts") or []),
            *(gate_results.get("artifacts") or []),
            str(proof_path),
        ]
    )
    preview_url = _clean(gate_results.get("preview_url") or gate_results.get("target_url"))
    screenshots = _collect_screenshots(project_root, gate_results)
    gaps = _gaps(imported_pages, applied, gate_results, verify=verify)
    ok = bool(applied.get("ok")) and (not verify or _browser_or_build_evidence_present(gate_results, browser=browser, tests=tests, install=install))
    ok = ok and (not verify or not gaps)
    result = {
        "ok": ok,
        "status": "implemented" if ok else "implemented_with_gaps",
        "summary": _summary(imported_pages, project_root, verify=verify, ok=ok, gaps=gaps),
        "project_root": str(project_root),
        "root": str(project_root),
        "request": _clean(request),
        "product_name": _clean(product_name) or _product_name_from_request(request) or project_root.name,
        "source_types": sorted({page.source_type for page in imported_pages}),
        "page_count": len(imported_pages),
        "pages": [_page_public_payload(page) for page in imported_pages],
        "handoff": str(design_root / "frontend-handoff.json"),
        "applied_design": applied,
        "gate_results": gate_results,
        "preview_url": preview_url,
        "screenshots": screenshots,
        "artifacts": artifacts,
        "gaps": gaps,
        "proof_report": str(proof_path),
    }
    result_path = import_root / "implementation-result.json"
    result_path.write_text(_json(result), encoding="utf-8")
    result["artifacts"] = _dedupe([*result["artifacts"], str(result_path)])
    return result


def _normalize_source_type(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9_]+", "_", str(value or "raw_html").strip().lower()).strip("_")
    return normalized if normalized in SUPPORTED_SOURCE_TYPES else "uploaded_file"


def _resolve_project_root(root: str | Path, project_slug: str, product_name: str, request: str) -> Path:
    slug = _slug(project_slug or product_name or _product_name_from_request(request) or request or "friday-imported-design")
    if project_slug:
        base = resolve_coding_root(root) if _clean(root) else resolve_coding_root("")
        return base if base.name.lower() == slug.lower() else (base / slug).resolve()
    if _clean(root):
        return resolve_coding_root(root)
    return resolve_coding_root(slug)


def _normalize_page_inputs(
    pages: list[dict[str, Any]] | None,
    *,
    source_type: str,
    source: str,
    source_path: str,
    source_url: str,
    source_base64: str,
    data_url: str,
) -> list[dict[str, Any]]:
    if pages:
        normalized: list[dict[str, Any]] = []
        for index, page in enumerate(pages, start=1):
            if not isinstance(page, dict):
                continue
            item = dict(page)
            item["source_type"] = _normalize_source_type(str(item.get("source_type") or source_type))
            item["id"] = _clean_page_id(item.get("id") or item.get("label") or f"page-{index}")
            item["route"] = _route(item.get("route"), item["id"])
            item["label"] = _clean(item.get("label")) or item["id"].replace("-", " ").title()
            normalized.append(item)
        return normalized
    return [
        {
            "id": "home",
            "route": "/",
            "label": "Home",
            "source_type": source_type,
            "source": source,
            "source_path": source_path,
            "source_url": source_url,
            "source_base64": source_base64,
            "data_url": data_url,
        }
    ]


def _materialize_page(
    page: dict[str, Any],
    *,
    index: int,
    project_root: Path,
    import_root: Path,
    request: str,
    product_name: str,
) -> ImportedDesignPage:
    page_id = _clean_page_id(page.get("id") or f"page-{index}")
    route = _route(page.get("route"), page_id)
    label = _clean(page.get("label")) or page_id.replace("-", " ").title()
    source_type = _normalize_source_type(str(page.get("source_type") or "raw_html"))
    page_root = import_root / "sources" / page_id
    page_root.mkdir(parents=True, exist_ok=True)

    materialized = _source_content(page, page_root, source_type)
    html = materialized.get("html") or ""
    react_code = materialized.get("react_code") or ""
    source_format = materialized.get("source_format") or "unknown"
    source_artifacts = list(materialized.get("artifacts") or [])
    warnings = list(materialized.get("warnings") or [])
    public_asset = materialized.get("public_asset") or ""
    if html:
        copied_assets = _copy_root_relative_html_assets(html, materialized.get("origin_path") or materialized.get("source_file_path"), project_root)
        source_artifacts.extend(copied_assets.get("artifacts") or [])
        warnings.extend(copied_assets.get("warnings") or [])
    if not html and not react_code:
        html = _reference_reconstruction_html(
            request=request,
            product_name=product_name,
            label=label,
            source_text=materialized.get("text") or _clean(page.get("source")),
            source_type=source_type,
            public_asset=public_asset,
            source_artifacts=source_artifacts,
        )
        source_format = source_format if source_format != "unknown" else "reference"
        warnings.append("Source did not include executable HTML; Friday reconstructed a frontend reference from available evidence.")

    analysis = _analyze_html(html or react_code, source_type=source_type, source_format=source_format)
    analysis["source_artifacts"] = source_artifacts
    analysis["route"] = route
    analysis["label"] = label
    analysis_path = page_root / "analysis.json"
    analysis_path.write_text(_json(analysis), encoding="utf-8")
    source_artifacts.append(str(analysis_path))
    fidelity = _fidelity(source_type, source_format, warnings)
    return ImportedDesignPage(
        id=page_id,
        route=route,
        label=label,
        source_type=source_type,
        source_format=source_format,
        fidelity=fidelity,
        html=html,
        react_code=react_code,
        source_artifacts=_dedupe(source_artifacts),
        analysis=analysis,
        warnings=_dedupe(warnings),
    )


def _source_content(page: dict[str, Any], page_root: Path, source_type: str) -> dict[str, Any]:
    artifacts: list[str] = []
    warnings: list[str] = []
    raw_source = str(page.get("source") or "")
    data_url = str(page.get("data_url") or "")
    source_base64 = str(page.get("source_base64") or "")
    source_path = str(page.get("source_path") or "")
    source_url = str(page.get("source_url") or "")

    if source_type in URL_TYPES and source_url:
        fetched = _fetch_url(source_url, page_root)
        return fetched
    if source_type in URL_TYPES and _looks_like_url(raw_source):
        return _fetch_url(raw_source.strip(), page_root)

    if data_url or source_base64:
        decoded = _save_base64_source(data_url or source_base64, page_root)
        artifacts.extend(decoded.get("artifacts") or [])
        if decoded.get("html"):
            return {**decoded, "artifacts": artifacts}
        return {**decoded, "artifacts": artifacts, "warnings": decoded.get("warnings") or []}

    if source_path:
        file_result = _read_or_copy_source_file(source_path, page_root)
        if file_result.get("html") or file_result.get("text") or file_result.get("public_asset"):
            return file_result
        artifacts.extend(file_result.get("artifacts") or [])
        warnings.extend(file_result.get("warnings") or [])

    if raw_source:
        if _looks_like_react_component(raw_source):
            path = page_root / "source.tsx"
            path.write_text(raw_source, encoding="utf-8")
            return {"react_code": raw_source, "source_format": "react_tsx", "artifacts": [str(path)], "warnings": warnings}
        if _looks_like_html(raw_source):
            path = page_root / "source.html"
            path.write_text(raw_source, encoding="utf-8")
            return {"html": raw_source, "source_format": "html", "artifacts": [str(path)], "warnings": warnings}
        text_path = page_root / ("source.md" if source_type in BRIEF_TYPES else "source.txt")
        text_path.write_text(raw_source, encoding="utf-8")
        return {"text": raw_source, "source_format": "text", "artifacts": [str(text_path)], "warnings": warnings}

    return {"source_format": "empty", "artifacts": artifacts, "warnings": [*warnings, "No source content was provided."]}


def _fetch_url(source_url: str, page_root: Path) -> dict[str, Any]:
    parsed = urllib.parse.urlparse(source_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return {"source_format": "url", "artifacts": [], "warnings": ["Only http(s) design URLs can be imported."]}
    request = urllib.request.Request(source_url, headers={"User-Agent": "FridayDesignImporter/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            content_type = str(response.headers.get("content-type") or "").split(";", 1)[0].lower()
            data = response.read(4_000_000 + 1)
    except (OSError, urllib.error.URLError) as exc:
        return {"source_format": "url", "artifacts": [], "warnings": [f"Could not fetch design URL: {exc}"]}
    if len(data) > 4_000_000:
        return {"source_format": "url", "artifacts": [], "warnings": ["Fetched design URL exceeded the 4 MB import limit."]}
    suffix = mimetypes.guess_extension(content_type) or ".html"
    path = page_root / f"source-from-url{suffix}"
    path.write_bytes(data)
    if "html" in content_type or _looks_like_html(data[:8000].decode("utf-8", errors="ignore")):
        html = data.decode("utf-8", errors="replace")
        return {"html": html, "source_format": "html_url", "artifacts": [str(path)], "source_file_path": str(path), "warnings": []}
    public_asset = _copy_public_asset(path, _project_root_from_page_root(page_root))
    return {
        "source_format": content_type or "url",
        "artifacts": [str(path)],
        "public_asset": public_asset,
        "warnings": [f"Fetched URL was {content_type or 'not HTML'}; Friday will use it as a visual/reference asset."],
    }


def _save_base64_source(value: str, page_root: Path) -> dict[str, Any]:
    text = str(value or "")
    content_type = "application/octet-stream"
    payload = text
    if text.startswith("data:"):
        header, _, payload = text.partition(",")
        content_type = header[5:].split(";", 1)[0] or content_type
    try:
        raw = base64.b64decode(payload, validate=True)
    except (binascii.Error, ValueError):
        return {"source_format": "base64", "artifacts": [], "warnings": ["Base64 design source could not be decoded."]}
    suffix = mimetypes.guess_extension(content_type) or ".bin"
    path = page_root / f"source{suffix}"
    path.write_bytes(raw)
    if "html" in content_type:
        return {"html": raw.decode("utf-8", errors="replace"), "source_format": "html_base64", "artifacts": [str(path)], "source_file_path": str(path)}
    public_asset = _copy_public_asset(path, _project_root_from_page_root(page_root))
    return {"source_format": content_type, "artifacts": [str(path)], "public_asset": public_asset}


def _read_or_copy_source_file(source_path: str, page_root: Path) -> dict[str, Any]:
    path = Path(source_path).expanduser()
    if not path.exists() or not path.is_file():
        return {"source_format": "file", "artifacts": [], "warnings": [f"Source file was not found: {source_path}"]}
    dest = page_root / f"source{path.suffix or '.bin'}"
    shutil.copy2(path, dest)
    suffix = path.suffix.lower()
    if suffix in {".html", ".htm"}:
        return {"html": dest.read_text(encoding="utf-8", errors="replace"), "source_format": "html_file", "artifacts": [str(dest)], "source_file_path": str(dest), "origin_path": str(path)}
    if suffix in {".tsx", ".jsx"}:
        text = dest.read_text(encoding="utf-8", errors="replace")
        return {"react_code": text, "source_format": "react_tsx", "artifacts": [str(dest)]}
    if suffix in {".md", ".txt", ".json"}:
        text = dest.read_text(encoding="utf-8", errors="replace")
        if _looks_like_react_component(text):
            return {"react_code": text, "source_format": "react_tsx", "artifacts": [str(dest)]}
        if _looks_like_html(text):
            return {"html": text, "source_format": "html_file", "artifacts": [str(dest)], "source_file_path": str(dest), "origin_path": str(path)}
        return {"text": text, "source_format": suffix.removeprefix(".") or "text", "artifacts": [str(dest)]}
    public_asset = _copy_public_asset(dest, _project_root_from_page_root(page_root))
    return {"source_format": suffix.removeprefix(".") or "file", "artifacts": [str(dest)], "public_asset": public_asset}


def _project_root_from_page_root(page_root: Path) -> Path:
    # .friday/design-import/sources/<page-id> -> project root
    return page_root.parents[3] if len(page_root.parents) > 3 else page_root.parent


def _copy_root_relative_html_assets(html: str, source_file_path: Any, project_root: Path) -> dict[str, Any]:
    source_path = Path(str(source_file_path or "")).expanduser()
    if not source_path.exists():
        return {"artifacts": [], "warnings": []}
    public_root = _find_public_root(source_path)
    if not public_root:
        return {"artifacts": [], "warnings": []}
    references = _root_relative_asset_references(html)
    artifacts: list[str] = []
    warnings: list[str] = []
    for reference in references:
        relative = Path(*[part for part in reference.lstrip("/").split("/") if part])
        source_asset = public_root / relative
        if not source_asset.exists() or not source_asset.is_file():
            warnings.append(f"Referenced design asset was not found beside source HTML: {reference}")
            continue
        target_asset = project_root / "public" / relative
        target_asset.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_asset, target_asset)
        artifacts.append(str(target_asset))
    return {"artifacts": _dedupe(artifacts), "warnings": _dedupe(warnings)}


def _find_public_root(source_path: Path) -> Path | None:
    for ancestor in [source_path.parent, *source_path.parents]:
        if ancestor.name.lower() == "public":
            return ancestor
        candidate = ancestor / "public"
        if candidate.exists() and candidate.is_dir():
            return candidate
    return None


def _root_relative_asset_references(html: str) -> list[str]:
    text = str(html or "")
    references: list[str] = []
    for match in re.finditer(r"""(?:src|href)\s*=\s*['"](/(?:friday-assets|assets|images|img|media)/[^'"]+)['"]""", text, flags=re.IGNORECASE):
        references.append(match.group(1))
    for match in re.finditer(r"""url\(\s*['"]?(/(?:friday-assets|assets|images|img|media)/[^'")\s]+)['"]?\s*\)""", text, flags=re.IGNORECASE):
        references.append(match.group(1))
    return _dedupe(references)


def _normalize_imported_pages(pages: list[ImportedDesignPage], project_root: Path) -> None:
    available_routes = {_route(page.route, page.id) for page in pages}
    for page in pages:
        if not page.html:
            continue
        normalized = _normalize_imported_static_html(page.html, available_routes=available_routes)
        if normalized == page.html:
            continue
        page.html = normalized
        page.analysis = _analyze_html(normalized, source_type=page.source_type, source_format=page.source_format)
        page.analysis["source_artifacts"] = page.source_artifacts
        page.analysis["route"] = page.route
        page.analysis["label"] = page.label
        page_root = project_root / ".friday" / "design-import" / "sources" / page.id
        page_root.mkdir(parents=True, exist_ok=True)
        normalized_path = page_root / "normalized-source.html"
        normalized_path.write_text(normalized, encoding="utf-8")
        analysis_path = page_root / "analysis.json"
        analysis_path.write_text(_json(page.analysis), encoding="utf-8")
        page.source_artifacts = _dedupe([*page.source_artifacts, str(normalized_path), str(analysis_path)])


def _normalize_imported_static_html(html: str, *, available_routes: set[str]) -> str:
    text = str(html or "")
    text = _add_input_accessible_names(text)
    text = _add_icon_button_accessible_names(text)
    text = _repair_dead_hash_links(text)
    text = _rewrite_missing_internal_routes_to_anchors(text, available_routes=available_routes)
    text = _add_common_section_ids(text)
    return text


def _add_input_accessible_names(html: str) -> str:
    def repl(match: re.Match[str]) -> str:
        tag = match.group(0)
        if _has_any_attr(tag, ("aria-label", "aria-labelledby", "title")):
            return tag
        label = _attr(tag, "placeholder") or _attr(tag, "id") or _attr(tag, "name") or _attr(tag, "type")
        if not label:
            return tag
        label = _human_label(label)
        if _attr(tag, "type").lower() == "email" and label.lower() in {"email", "text"}:
            label = "Email address"
        return _insert_attr(tag, "aria-label", label)

    return re.sub(r"<input\b[^>]*>", repl, html, flags=re.IGNORECASE | re.DOTALL)


def _add_icon_button_accessible_names(html: str) -> str:
    def repl(match: re.Match[str]) -> str:
        open_tag, inner, close_tag = match.group(1), match.group(2), match.group(3)
        if _has_any_attr(open_tag, ("aria-label", "aria-labelledby", "title")):
            return match.group(0)
        text = _strip_tags(inner).strip()
        compact = re.sub(r"[^a-z0-9_]+", "", text.lower())
        label = {
            "menu": "Open menu",
            "shopping_bag": "Shopping bag",
            "east": "Submit email",
            "arrow_forward": "Continue",
        }.get(compact)
        if not label and text and len(text.split()) <= 4:
            label = _human_label(text)
        if not label and re.search(r"material-symbols|material-icons|icon", inner, flags=re.IGNORECASE):
            label = "Open menu"
        if not label:
            return match.group(0)
        return f"{_insert_attr(open_tag, 'aria-label', label)}{inner}{close_tag}"

    return re.sub(r"(<button\b[^>]*>)(.*?)(</button>)", repl, html, flags=re.IGNORECASE | re.DOTALL)


def _repair_dead_hash_links(html: str) -> str:
    def repl(match: re.Match[str]) -> str:
        open_tag, inner = match.group(1), match.group(2)
        label = _strip_tags(inner).lower()
        target = _target_for_link_label(label)
        return open_tag.replace('href="#"', f'href="{target}"').replace("href='#'", f"href='{target}'") + inner + "</a>"

    return re.sub(r"(<a\b[^>]*href=(?:\"#\"|'#')[^>]*>)(.*?)(</a>)", repl, html, flags=re.IGNORECASE | re.DOTALL)


def _rewrite_missing_internal_routes_to_anchors(html: str, *, available_routes: set[str]) -> str:
    anchorable = {
        "/about": "#top",
        "/conceptually-home": "/",
        "/process": "#process",
        "/services": "#process",
        "/service": "#process",
        "/inquiry": "#inquiry",
        "/contact": "#inquiry",
        "/concierge": "#inquiry",
        "/journal": "#journal",
        "/privacy": "#privacy",
        "/terms": "#terms",
    }

    def repl(match: re.Match[str]) -> str:
        quote = match.group(1)
        href = match.group(2)
        path = urllib.parse.urlparse(href).path.rstrip("/") or "/"
        if path in available_routes:
            return match.group(0)
        target = anchorable.get(path)
        if not target:
            return match.group(0)
        return f"href={quote}{target}{quote}"

    return re.sub(r"href=(['\"])(/[^'\"#?]+)(?:[?#][^'\"]*)?\1", repl, html, flags=re.IGNORECASE)


def _add_common_section_ids(html: str) -> str:
    text = html
    text = _add_id_to_first_matching_section(text, "collections", ("Curated Archives", "Collections"))
    text = _add_id_to_first_matching_section(text, "process", ("The Journey", "Process", "Art of the Impression", "Studio Process"))
    text = _add_id_to_first_matching_section(text, "inquiry", ("Secure Your Date", "Inquiry", "Begin Inquiry", "Contact"))
    text = _add_id_to_first_matching_section(text, "journal", ("Journal", "Notes", "Editorial"))
    text = _add_id_to_first_matching_section(text, "privacy", ("Privacy", "Governance"))
    text = _add_id_to_first_matching_section(text, "terms", ("Terms", "Service", "Policy"))
    return text


def _add_id_to_first_matching_section(html: str, section_id: str, terms: tuple[str, ...]) -> str:
    if re.search(rf"\bid\s*=\s*(['\"]){re.escape(section_id)}\1", html, flags=re.IGNORECASE):
        return html
    pattern = re.compile(r"<section\b([^>]*)>(.*?)</section>", flags=re.IGNORECASE | re.DOTALL)
    for match in pattern.finditer(html):
        attrs, body = match.group(1), match.group(2)
        if re.search(r"\bid\s*=", attrs, flags=re.IGNORECASE):
            continue
        body_text = _strip_tags(body).lower()
        if not any(term.lower() in body_text for term in terms):
            continue
        open_tag = f'<section id="{section_id}"{attrs}>'
        return html[: match.start()] + open_tag + body + "</section>" + html[match.end() :]
    return html


def _target_for_link_label(label: str) -> str:
    text = _clean(label).lower()
    if "location" in text or "studio" in text:
        return "#inquiry"
    if "contact" in text or "inquiry" in text:
        return "#inquiry"
    if "journal" in text:
        return "#journal"
    if "privacy" in text:
        return "#privacy"
    if "collection" in text:
        return "/collections"
    return "#top"


def _attr(tag: str, name: str) -> str:
    pattern = rf"\b{re.escape(name)}\s*=\s*(['\"])(.*?)\1"
    match = re.search(pattern, tag, flags=re.IGNORECASE | re.DOTALL)
    return _clean(match.group(2)) if match else ""


def _has_any_attr(tag: str, names: tuple[str, ...]) -> bool:
    return any(re.search(rf"\b{re.escape(name)}\s*=", tag, flags=re.IGNORECASE) for name in names)


def _insert_attr(tag: str, name: str, value: str) -> str:
    encoded = escape(_clean(value), quote=True)
    if tag.rstrip().endswith("/>"):
        return re.sub(r"\s*/>$", f' {name}="{encoded}"/>', tag)
    return re.sub(r">$", f' {name}="{encoded}">', tag)


def _human_label(value: str) -> str:
    cleaned = re.sub(r"[_-]+", " ", _clean(value))
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned[:1].upper() + cleaned[1:] if cleaned else ""


def _strip_tags(value: str) -> str:
    return re.sub(r"<[^>]+>", " ", str(value or "")).replace("\xa0", " ")


def _copy_public_asset(path: Path, project_root: Path) -> str:
    public_root = project_root / "public" / "friday-design-import"
    public_root.mkdir(parents=True, exist_ok=True)
    safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "-", path.name).strip("-") or "source-asset"
    dest = public_root / safe_name
    shutil.copy2(path, dest)
    return f"/friday-design-import/{safe_name}"


def _write_handoff_artifacts(
    project_root: Path,
    pages: list[ImportedDesignPage],
    *,
    request: str,
    product_name: str,
    design_root: Path,
    import_root: Path,
) -> list[str]:
    artifacts: list[str] = []
    aggregate = _aggregate_handoff(project_root, pages, request=request, product_name=product_name)
    for page in pages:
        page_design_root = design_root / "pages" / page.id
        report = _page_report(page, aggregate, request=request, product_name=product_name)
        artifacts.extend(design_providers._write_design_critique_artifacts(page_design_root, report))
    home = next((page for page in pages if page.route == "/"), pages[0])
    root_report = _page_report(home, aggregate, request=request, product_name=product_name)
    artifacts.extend(design_providers._write_design_critique_artifacts(design_root, root_report))

    aggregate_path = design_root / "frontend-handoff.json"
    existing: dict[str, Any] = {}
    if aggregate_path.exists():
        try:
            existing = json.loads(aggregate_path.read_text(encoding="utf-8"))
        except Exception:
            existing = {}
    aggregate_path.write_text(_json({**existing, **aggregate}), encoding="utf-8")
    aggregate_md = design_root / "frontend-handoff.md"
    aggregate_md.write_text(_handoff_markdown(aggregate), encoding="utf-8")
    source_manifest = import_root / "source-manifest.json"
    source_manifest.write_text(_json({"pages": [_page_public_payload(page) for page in pages], "artifacts": _dedupe(sum((page.source_artifacts for page in pages), []))}), encoding="utf-8")
    return _dedupe([*artifacts, str(aggregate_path), str(aggregate_md), str(source_manifest)])


def _apply_imported_pages(project_root: Path, pages: list[ImportedDesignPage], *, request: str, product_name: str) -> dict[str, Any]:
    name = _clean(product_name) or _product_name_from_request(request) or project_root.name
    html_pages = [page for page in pages if not page.react_code]
    react_pages = [page for page in pages if page.react_code]
    written: list[str] = []
    ok = True
    if html_pages:
        payloads: list[dict[str, Any]] = []
        for page in html_pages:
            handoff = {
                "selected_variant_id": f"external-{page.id}",
                "selected_variant_label": f"{page.label} external design",
                "score": 95 if page.fidelity == "exact_html" else 76,
                "design_context": {"source_type": page.source_type, "fidelity": page.fidelity, "analysis": page.analysis},
            }
            payloads.append(design_providers._selected_design_page_payload(page.id, page.route, page.label, page.html, handoff=handoff, product_name=name))
        applied_html = design_providers._apply_design_pages_to_nextjs(project_root, payloads, request=request, product_name=name)
        ok = ok and bool(applied_html.get("ok"))
        written.extend(applied_html.get("files") or [])
    if react_pages:
        written.extend(design_providers._ensure_nextjs_project_shell(project_root, name, request))
        for page in react_pages:
            component_name = f"{_pascal(page.id)}ImportedDesign"
            component_path = project_root / "src" / "components" / "ExternalDesign" / f"{component_name}.tsx"
            route_path = design_providers._next_route_path(project_root, page.route)
            component_path.parent.mkdir(parents=True, exist_ok=True)
            route_path.parent.mkdir(parents=True, exist_ok=True)
            component_path.write_text(_react_component_module(page.react_code), encoding="utf-8")
            route_path.write_text(_react_route_module(component_name), encoding="utf-8")
            written.extend([str(component_path), str(route_path)])
    manifest_path = project_root / ".friday" / "design-import" / "applied-design.json"
    manifest = {
        "ok": ok,
        "status": "applied" if ok else "failed",
        "mode": "external_design_import",
        "files": _dedupe(written),
        "pages": [{"id": page.id, "route": page.route, "fidelity": page.fidelity} for page in pages],
    }
    manifest_path.write_text(_json(manifest), encoding="utf-8")
    return {**manifest, "artifacts": [*_dedupe(written), str(manifest_path)]}


def _page_report(page: ImportedDesignPage, aggregate: dict[str, Any], *, request: str, product_name: str) -> dict[str, Any]:
    variant = {
        "id": f"external-{page.id}",
        "label": f"{page.label} external design",
        "score": 95 if page.fidelity == "exact_html" else 76,
        "html": page.html or _react_source_preview_html(page),
        "criteria": [
            {"id": "source_saved", "label": "Source design saved", "score": 20, "weight": 20},
            {"id": "handoff", "label": "Frontend handoff created", "score": 20, "weight": 20},
            {"id": "fidelity", "label": f"Fidelity: {page.fidelity}", "score": 35 if page.fidelity == "exact_html" else 20, "weight": 35},
            {"id": "implementation", "label": "Next.js route implementation source available", "score": 25, "weight": 25},
        ],
        "source_type": page.source_type,
        "source_format": page.source_format,
        "fidelity": page.fidelity,
        "warnings": page.warnings,
    }
    return {
        "status": "selected",
        "summary": f"Imported {page.label} from {page.source_type} and prepared a frontend handoff.",
        "request": _clean(request),
        "product_name": _clean(product_name),
        "score_threshold": 70,
        "frontend_handoff_allowed": True,
        "frontend_handoff_required": True,
        "selected_variant": variant,
        "variants": [variant],
        "rejected_variants": [],
        "design_context": aggregate,
        "design_strategy": {"source": "external_design_import", "fidelity": page.fidelity},
    }


def _aggregate_handoff(project_root: Path, pages: list[ImportedDesignPage], *, request: str, product_name: str) -> dict[str, Any]:
    return {
        "source": "external_design_import",
        "project_root": str(project_root),
        "request": _clean(request),
        "product_name": _clean(product_name) or _product_name_from_request(request) or project_root.name,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "supported_sources": sorted(SUPPORTED_SOURCE_TYPES),
        "pages": [_page_public_payload(page) for page in pages],
        "routes": [{"id": page.id, "route": page.route, "label": page.label} for page in pages],
        "instructions": [
            "Implement this handoff as a real Next.js App Router project.",
            "Preserve exact HTML sources as static document routes when that gives better fidelity.",
            "For image/brief-only sources, keep source artifacts attached and mark the result as reference reconstruction until visual-code verification passes.",
            "Run install/build/browser gates before claiming the imported frontend is verified.",
        ],
    }


def _reference_reconstruction_html(
    *,
    request: str,
    product_name: str,
    label: str,
    source_text: str,
    source_type: str,
    public_asset: str,
    source_artifacts: list[str],
) -> str:
    name = _clean(product_name) or _product_name_from_request(request) or "Imported Design"
    summary = _clean(source_text) or _clean(request) or f"{name} external design reference."
    bullets = _sentences(summary)[:5] or ["External design source saved", "Frontend handoff created", "Next.js implementation scaffolded"]
    asset = f"<img src=\"{escape(public_asset)}\" alt=\"Imported design reference\"/>" if public_asset else ""
    artifact_list = "".join(f"<li>{escape(Path(item).name)}</li>" for item in source_artifacts[:6])
    bullet_list = "".join(f"<li>{escape(item)}</li>" for item in bullets)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{escape(name)} - {escape(label)}</title>
  <style>
    :root {{ color-scheme: light; --ink:#161512; --muted:#5f5a52; --line:#ded8cf; --paper:#f7f4ef; --accent:#0d5f52; }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; background:var(--paper); color:var(--ink); font-family:Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }}
    main {{ min-height:100vh; display:grid; grid-template-columns:minmax(0,1fr); }}
    .hero {{ padding:72px min(7vw,96px); display:grid; grid-template-columns:minmax(0,0.9fr) minmax(280px,0.8fr); gap:56px; align-items:center; }}
    .eyebrow {{ margin:0 0 18px; text-transform:uppercase; letter-spacing:.18em; font-size:12px; color:var(--accent); font-weight:800; }}
    h1 {{ margin:0; max-width:820px; font-size:clamp(44px,7vw,104px); line-height:.94; letter-spacing:0; }}
    p {{ color:var(--muted); font-size:18px; line-height:1.7; }}
    ul {{ padding:0; margin:32px 0 0; display:grid; gap:12px; list-style:none; }}
    li {{ border-top:1px solid var(--line); padding-top:12px; font-weight:700; }}
    img {{ width:100%; min-height:420px; object-fit:cover; border:1px solid var(--line); box-shadow:0 24px 80px rgba(30,25,20,.16); }}
    .proof {{ border-top:1px solid var(--line); padding:40px min(7vw,96px); display:flex; flex-wrap:wrap; gap:18px 36px; color:var(--muted); }}
    @media (max-width: 860px) {{ .hero {{ grid-template-columns:1fr; padding:44px 24px; }} img {{ min-height:260px; }} }}
  </style>
</head>
<body>
  <main>
    <section class="hero">
      <div>
        <p class="eyebrow">{escape(source_type.replace("_", " "))} source</p>
        <h1>{escape(name)}</h1>
        <p>{escape(summary[:420])}</p>
        <ul>{bullet_list}</ul>
      </div>
      <figure>{asset or "<p>External source saved. Use the attached artifact as the visual reference for revision.</p>"}</figure>
    </section>
    <section class="proof" aria-label="Imported design artifacts">
      <strong>Source artifacts</strong>
      <ul>{artifact_list or "<li>Source manifest attached</li>"}</ul>
    </section>
  </main>
</body>
</html>"""


class _Analyzer(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title = ""
        self._in_title = False
        self._tag_stack: list[str] = []
        self.headings: list[str] = []
        self.nav: list[dict[str, str]] = []
        self.buttons: list[str] = []
        self.images: list[dict[str, str]] = []
        self.forms = 0
        self.sections = 0
        self.links: list[dict[str, str]] = []
        self._anchor_href = ""
        self._anchor_text: list[str] = []
        self._button_text: list[str] = []
        self._heading_tag = ""
        self._heading_text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_map = {key.lower(): value or "" for key, value in attrs}
        tag = tag.lower()
        self._tag_stack.append(tag)
        if tag == "title":
            self._in_title = True
        if tag in {"h1", "h2", "h3"}:
            self._heading_tag = tag
            self._heading_text = []
        if tag == "a":
            self._anchor_href = attrs_map.get("href", "")
            self._anchor_text = []
        if tag == "button":
            self._button_text = []
        if tag == "img":
            self.images.append({"src": attrs_map.get("src", ""), "alt": attrs_map.get("alt", "")})
        if tag == "form":
            self.forms += 1
        if tag == "section":
            self.sections += 1

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag == "title":
            self._in_title = False
        if tag == self._heading_tag:
            text = _clean(" ".join(self._heading_text))
            if text:
                self.headings.append(text)
            self._heading_tag = ""
            self._heading_text = []
        if tag == "a":
            text = _clean(" ".join(self._anchor_text))
            if text:
                item = {"label": text, "href": self._anchor_href}
                self.links.append(item)
                if "nav" in self._tag_stack:
                    self.nav.append(item)
            self._anchor_href = ""
            self._anchor_text = []
        if tag == "button":
            text = _clean(" ".join(self._button_text))
            if text:
                self.buttons.append(text)
            self._button_text = []
        if self._tag_stack:
            self._tag_stack.pop()

    def handle_data(self, data: str) -> None:
        text = _clean(data)
        if not text:
            return
        if self._in_title:
            self.title = _clean(f"{self.title} {text}")
        if self._heading_tag:
            self._heading_text.append(text)
        if self._anchor_href:
            self._anchor_text.append(text)
        if self._tag_stack and self._tag_stack[-1] == "button":
            self._button_text.append(text)


def _analyze_html(html: str, *, source_type: str, source_format: str) -> dict[str, Any]:
    parser = _Analyzer()
    try:
        parser.feed(html or "")
        parser.close()
    except Exception:
        pass
    return {
        "source_type": source_type,
        "source_format": source_format,
        "content_hash": hashlib.sha256(str(html or "").encode("utf-8", errors="ignore")).hexdigest(),
        "title": parser.title,
        "headings": parser.headings[:16],
        "navigation": parser.nav[:12],
        "links": parser.links[:20],
        "buttons": parser.buttons[:20],
        "images": parser.images[:20],
        "forms": parser.forms,
        "sections": parser.sections,
        "interactions": _dedupe([*(button for button in parser.buttons), *(link["label"] for link in parser.links[:8])]),
        "layout_signals": _layout_signals(html),
    }


def _layout_signals(html: str) -> list[str]:
    text = str(html or "").lower()
    signals = []
    checks = {
        "full_bleed_media": ("background-image", "object-cover", "min-height:100vh", "h-screen"),
        "split_hero": ("grid-template-columns", "grid-cols-2", "lg:grid-cols-2"),
        "cards": ("card", "border-radius", "rounded", "<article"),
        "forms": ("<form", "input", "textarea"),
        "motion": ("framer", "gsap", "animation", "transition"),
        "tailwind": ("tailwind", "bg-", "text-", "grid-cols"),
    }
    for label, terms in checks.items():
        if any(term in text for term in terms):
            signals.append(label)
    return signals


def _write_proof_report(
    project_root: Path,
    pages: list[ImportedDesignPage],
    *,
    applied: dict[str, Any],
    gate_results: dict[str, Any],
    request: str,
    product_name: str,
    handoff_artifacts: list[str],
) -> Path:
    proof_path = project_root / ".friday" / "design-import" / "final-proof-report.md"
    proof_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# External Design Import Proof",
        "",
        f"Product: {_clean(product_name) or _product_name_from_request(request) or project_root.name}",
        f"Project root: {project_root}",
        f"Request: {_clean(request) or 'not provided'}",
        "",
        "## Pages",
    ]
    for page in pages:
        warnings = "; ".join(page.warnings) or "none"
        lines.append(f"- {page.label} ({page.route}): {page.source_type}, {page.fidelity}, warnings: {warnings}")
    lines.extend(
        [
            "",
            "## Implementation",
            f"- Applied: {bool(applied.get('ok'))}",
            f"- Files written: {len(applied.get('files') or [])}",
            "",
            "## Verification",
        ]
    )
    if gate_results:
        lines.append(f"- Gate status: {gate_results.get('status') or 'recorded'}")
        lines.append(f"- Preview URL: {gate_results.get('preview_url') or gate_results.get('target_url') or 'not recorded'}")
        for gate in gate_results.get("gates") or []:
            lines.append(f"- {gate.get('id')}: {gate.get('status')} - {gate.get('summary')}")
    else:
        lines.append("- Gates were not run for this import.")
    lines.extend(["", "## Artifacts", *[f"- {item}" for item in _dedupe([*handoff_artifacts, *(applied.get("artifacts") or [])])]])
    proof_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return proof_path


def _handoff_markdown(handoff: dict[str, Any]) -> str:
    lines = [
        "# Frontend Handoff",
        "",
        f"Source: {handoff.get('source')}",
        f"Product: {handoff.get('product_name')}",
        f"Project root: {handoff.get('project_root')}",
        "",
        "## Routes",
    ]
    for page in handoff.get("pages") or []:
        lines.append(f"- {page.get('label')} ({page.get('route')}): {page.get('source_type')} / {page.get('fidelity')}")
    lines.extend(["", "## Instructions", *[f"- {item}" for item in handoff.get("instructions") or []]])
    return "\n".join(lines) + "\n"


def _page_public_payload(page: ImportedDesignPage) -> dict[str, Any]:
    return {
        "id": page.id,
        "route": page.route,
        "label": page.label,
        "source_type": page.source_type,
        "source_format": page.source_format,
        "fidelity": page.fidelity,
        "analysis": page.analysis,
        "warnings": page.warnings,
        "source_artifacts": page.source_artifacts,
    }


def _fidelity(source_type: str, source_format: str, warnings: list[str]) -> str:
    if source_format == "react_tsx":
        return "source_code_preserved"
    if source_format.startswith("html") and not warnings:
        return "exact_html"
    if source_format.startswith("html"):
        return "native_or_exact_html"
    if source_type in IMAGE_TYPES or source_type in BRIEF_TYPES or source_type in FILE_TYPES:
        return "reference_reconstruction"
    return "native_react"


def _gaps(pages: list[ImportedDesignPage], applied: dict[str, Any], gate_results: dict[str, Any], *, verify: bool) -> list[str]:
    gaps: list[str] = []
    if not applied.get("ok"):
        gaps.append("Next.js design application did not complete.")
    for page in pages:
        gaps.extend(page.warnings)
        if page.fidelity == "reference_reconstruction":
            gaps.append(f"{page.label} was reconstructed from a non-HTML source; exact visual fidelity still needs a visual-to-code pass.")
    if not verify:
        gaps.append("Install/build/browser verification was skipped.")
    elif gate_results:
        for gate in gate_results.get("gates") or []:
            if gate.get("required") and gate.get("status") not in {"passed", "skipped"}:
                gaps.append(f"{gate.get('label') or gate.get('id')} did not pass: {gate.get('summary')}")
    return _dedupe(gaps)


def _browser_or_build_evidence_present(gate_results: dict[str, Any], *, browser: bool, tests: bool, install: bool) -> bool:
    gates = gate_results.get("gates") if isinstance(gate_results.get("gates"), list) else []
    if not gates:
        return False
    status_by_id = {gate.get("id"): gate.get("status") for gate in gates if isinstance(gate, dict)}
    if install and status_by_id.get("dependencies_install") not in {"passed", "skipped"}:
        return False
    if browser and status_by_id.get("browser_check") not in {"passed", "skipped"}:
        return False
    if tests:
        test_gates = [gate for gate in gates if str(gate.get("id") or "").startswith("test_")]
        if not test_gates:
            return False
        if any(gate.get("status") not in {"passed", "skipped"} for gate in test_gates):
            return False
    return True


def _collect_screenshots(project_root: Path, gate_results: dict[str, Any]) -> list[str]:
    screenshots: list[str] = []
    for gate in gate_results.get("gates") or []:
        for item in gate.get("evidence") or []:
            if str(item).lower().endswith((".png", ".jpg", ".jpeg", ".webp")):
                screenshots.append(str(item))
    if not screenshots:
        screenshots.extend(str(path) for path in (project_root / ".friday").rglob("*.png") if path.is_file())
    return _dedupe(screenshots)


def _summary(pages: list[ImportedDesignPage], project_root: Path, *, verify: bool, ok: bool, gaps: list[str]) -> str:
    source_names = ", ".join(sorted({page.source_type for page in pages}))
    if ok:
        return f"Imported {len(pages)} external design page(s) from {source_names}, implemented a Next.js project at {project_root}, and recorded proof."
    if verify:
        return f"Imported and implemented {len(pages)} design page(s), but verification still has {len(gaps)} gap(s)."
    return f"Imported and implemented {len(pages)} design page(s) at {project_root}; verification was skipped."


def _looks_like_html(value: str) -> bool:
    text = str(value or "").strip().lower()
    return bool(re.search(r"<!doctype html|<html\b|<body\b|<main\b|<section\b|<div\b|<style\b", text))


def _looks_like_react_component(value: str) -> bool:
    text = str(value or "")
    if "export default" not in text:
        return False
    if not re.search(r"\b(function|const|class)\b", text):
        return False
    return bool(re.search(r"<[A-Z_a-z][A-Za-z0-9_:-]*(\s|>|/>)", text))


def _react_component_module(code: str) -> str:
    text = str(code or "").strip()
    if not text:
        return 'export default function ImportedDesign() { return <main />; }\n'
    if not text.startswith('"use client"') and not text.startswith("'use client'"):
        text = '"use client";\n\n' + text
    return text.rstrip() + "\n"


def _react_route_module(component_name: str) -> str:
    return f'import ImportedDesign from "@/components/ExternalDesign/{component_name}";\n\nexport default function Page() {{\n  return <ImportedDesign />;\n}}\n'


def _react_source_preview_html(page: ImportedDesignPage) -> str:
    return f"<main><section><h1>{escape(page.label)} React design source</h1><pre>{escape(page.react_code[:12000])}</pre></section></main>"


def _pascal(value: str) -> str:
    return "".join(part.capitalize() for part in re.split(r"[^A-Za-z0-9]+", str(value or "")) if part) or "Home"


def _looks_like_url(value: str) -> bool:
    try:
        parsed = urllib.parse.urlparse(str(value or "").strip())
    except Exception:
        return False
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _route(value: Any, page_id: str) -> str:
    raw = _clean(value)
    if not raw:
        return "/" if page_id == "home" else f"/{page_id}"
    if raw.startswith("http://") or raw.startswith("https://"):
        return "/" if page_id == "home" else f"/{page_id}"
    return raw if raw.startswith("/") else f"/{raw}"


def _clean_page_id(value: Any) -> str:
    raw = re.sub(r"[^a-z0-9-]+", "-", str(value or "").lower()).strip("-")
    return raw or "home"


def _slug(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(value or "").lower()).strip("-") or "friday-imported-design"


def _product_name_from_request(request: str) -> str:
    text = _clean(request)
    quoted = re.search(r"['\"]([^'\"]{3,80})['\"]", text)
    if quoted:
        return _clean(quoted.group(1))
    match = re.search(r"\b(?:for|called|named)\s+([A-Z][A-Za-z0-9& .-]{2,80})", text)
    if match:
        return _clean(match.group(1)).rstrip(".")
    words = [word for word in re.findall(r"[A-Za-z][A-Za-z0-9&-]*", text) if word.lower() not in {"build", "make", "create", "website", "landing", "page", "dashboard"}]
    return " ".join(words[:3])


def _sentences(value: str) -> list[str]:
    return [_clean(item) for item in re.split(r"(?<=[.!?])\s+|\n+", str(value or "")) if _clean(item)]


def _clean(value: Any) -> str:
    return " ".join(str(value or "").replace("\x00", " ").strip().split())


def _dedupe(values: list[Any]) -> list[Any]:
    seen: set[str] = set()
    result: list[Any] = []
    for value in values:
        key = str(value)
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(value)
    return result


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True, default=str) + "\n"
