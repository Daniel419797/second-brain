"""Taste and quality checks for Friday-generated product surfaces."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from core import web_project_contract
from core.config import config_value, resolve_coding_root

FRIDAY_DIR = ".friday"
STUDIO_DIR = "product-studio"
QUALITY_DIR = "quality"

VISIBLE_SURFACE_CANDIDATES = (
    "src/lib/siteContent.ts",
    "src/lib/webProjectContract.ts",
    "src/lib/productPlan.ts",
    "src/lib/stitchNativeContent.ts",
    "src/components/Landing/HomePage.tsx",
    "src/components/Marketing/AboutPage.tsx",
    "src/components/Marketing/ServicesPage.tsx",
    "src/components/Marketing/ContactPage.tsx",
    "src/components/Marketing/SiteHeader.tsx",
    "src/components/Marketing/SiteFooter.tsx",
    "src/components/WebContract/WebContractPage.tsx",
    "src/components/WebContract/DashboardPreviewPage.tsx",
    "src/components/Workspace/WorkspaceConsole.tsx",
    "src/components/Stitch/StitchNativePage.tsx",
    "src/components/Stitch/StitchNativePage.module.css",
    "src/app/page.tsx",
    "src/app/about/page.tsx",
    "src/app/services/page.tsx",
    "src/app/contact/page.tsx",
    "src/app/globals.css",
)

GENERIC_COPY = (
    "AI-assisted everyday workflow tool",
    "Generate a brief to see the AI workflow",
    "Customer asked for status",
    "designer is blocked",
    "service businesses",
    "SMB operators",
    "Open workspace",
    "Launch signal",
    "Normal Real Workspace",
    "Independent service studio",
    "A clear four-page website",
    "Built for clients who need clarity",
    "Discovery and planning",
    "Execution support",
    "Launch readiness",
)

BAD_LINK_PATTERNS = (
    'href="#"',
    "href='#'",
    'href="javascript:',
    "href='javascript:",
)


def review_project(
    root: str | Path,
    request: str,
    *,
    stack: dict[str, Any] | None = None,
    gate_results: dict[str, Any] | None = None,
    design_handoff: dict[str, Any] | None = None,
    create_files: bool = True,
) -> dict[str, Any]:
    """Review whether generated output feels like a real product, not a scaffold."""

    project_root = resolve_coding_root(root)
    stack = stack or {}
    request_text = _clean(request)
    surface_files = _surface_files(project_root)
    surface_text = "\n".join(path.read_text(encoding="utf-8", errors="ignore")[:150000] for path in surface_files)
    issues: list[dict[str, Any]] = []

    issues.extend(_website_shape_issues(project_root, request_text, stack))
    issues.extend(_scaffold_copy_issues(surface_text, surface_files, request_text))
    issues.extend(_interaction_static_issues(surface_text, surface_files, request_text))
    issues.extend(_experience_mode_static_issues(project_root, surface_text, surface_files, request_text))
    issues.extend(_design_handoff_issues(design_handoff or {}))
    issues.extend(_visual_gate_issues(gate_results or {}))

    score = _score(issues)
    threshold = int(config_value("quality_taste_min_score", 82) or 82)
    blocking = [item for item in issues if int(item.get("severity") or 0) >= 4]
    passed = score >= threshold and not blocking
    report = {
        "ok": passed,
        "status": "passed" if passed else "needs_revision",
        "score": score,
        "threshold": threshold,
        "root": str(project_root),
        "request": request_text,
        "stack": stack,
        "issues": issues,
        "summary": _summary(score, threshold, issues),
        "files_checked": [_relative(path, project_root) for path in surface_files],
        "safe_fix_available": _safe_fix_available(issues, project_root),
    }
    artifacts = _write_report(project_root, report) if create_files else []
    return {**report, "artifacts": artifacts}


def apply_safe_fixes(root: str | Path, review: dict[str, Any]) -> dict[str, Any]:
    """Apply deterministic low-risk UI fixes for layout safety only."""

    project_root = resolve_coding_root(root)
    issues = review.get("issues") if isinstance(review.get("issues"), list) else []
    issue_ids = {str(item.get("id") or "") for item in issues if isinstance(item, dict)}
    changed: list[str] = []
    fixes: list[str] = []

    needs_layout_guard = bool(
        issue_ids
        & {
            "visual_h1_too_large",
            "visual_horizontal_overflow",
            "visual_clipped_elements",
            "css_missing_overflow_guard",
            "visual_hero_extends",
            "missing_reduced_motion_fallback",
            "visual_missing_reduced_motion",
        }
    )
    if needs_layout_guard:
        globals_css = project_root / "src" / "app" / "globals.css"
        if _append_once(
            globals_css,
            "/* Friday quality guard: generated UI must not break viewport layout. */",
            """

/* Friday quality guard: generated UI must not break viewport layout. */
h1, h2, h3, p, a, button {
  overflow-wrap: anywhere;
}

img, video, canvas, svg {
  max-width: 100%;
  height: auto;
}

body {
  overflow-x: hidden;
}

.single-copy h1,
.single-hero h1,
.landing-hero h1,
.hero h1 {
  font-size: clamp(2.25rem, 5vw, 4.75rem) !important;
  line-height: 1.03 !important;
  overflow-wrap: anywhere;
}

@media (max-width: 700px) {
  .single-copy h1,
  .single-hero h1,
  .landing-hero h1,
  .hero h1 {
    font-size: clamp(2rem, 12vw, 3rem) !important;
  }
}

@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: 0.001ms !important;
    animation-iteration-count: 1 !important;
    scroll-behavior: auto !important;
    transition-duration: 0.001ms !important;
  }
}
""",
        ):
            changed.append(str(globals_css))
            fixes.append("Added global overflow/image layout and reduced-motion guard.")

        stitch_css = project_root / "src" / "components" / "Stitch" / "StitchNativePage.module.css"
        if _append_once(
            stitch_css,
            "/* Friday quality guard: normalize exaggerated Stitch hero scale. */",
            """

/* Friday quality guard: normalize exaggerated Stitch hero scale. */
.hero h1 {
  font-size: clamp(2.25rem, 5vw, 4.75rem) !important;
  line-height: 1.02 !important;
  overflow-wrap: anywhere;
}

@media (max-width: 700px) {
  .hero h1 {
    font-size: clamp(2rem, 12vw, 3rem) !important;
  }
}
""",
        ):
            changed.append(str(stitch_css))
            fixes.append("Added Stitch hero scale guard.")

    return {
        "ok": bool(changed),
        "status": "fixed" if changed else "no_safe_fix",
        "changed": changed,
        "fixes": fixes,
        "summary": f"Applied {len(fixes)} safe quality fix(es)." if fixes else "No deterministic safe quality fix was available.",
    }


def _website_shape_issues(project_root: Path, request: str, stack: dict[str, Any]) -> list[dict[str, Any]]:
    text = request.lower()
    stack_id = str((stack or {}).get("stack") or "").lower()
    contract_routes = web_project_contract.expected_route_paths(project_root, request, stack=stack)
    if stack_id != "nextjs":
        return []
    if not contract_routes and not any(term in text for term in ("website", "site", "4 pages", "four pages")):
        return []
    if not contract_routes and _single_page_website_request(text):
        return []
    issues: list[dict[str, Any]] = []
    routes = contract_routes or _expected_website_routes(project_root, request)
    missing = [name for name, path in routes.items() if not path.exists()]
    if missing:
        issues.append(_issue("missing_website_routes", 5, f"Website is missing route(s): {', '.join(missing)}.", [str(routes[name]) for name in missing]))
    for name, path in routes.items():
        if not path.exists():
            continue
        body = path.read_text(encoding="utf-8", errors="ignore")
        if len([line for line in body.splitlines() if line.strip()]) > 28:
            issues.append(_issue("fat_route_file", 4, f"{name} route is too large; route files should compose page components.", [str(path)]))
    return issues


def _single_page_website_request(text: str) -> bool:
    single_page = any(term in text for term in ("landing page", "single-page", "single page", "one-page", "one page"))
    if not single_page:
        return False
    if re.search(r"\bpages\s+(?:must|should|include|including)\b", text):
        return False
    affirmative_multi_page = re.search(r"\b(?:four|4|multi|multiple)[-\s]?pages?\b", text)
    negated_multi_page = re.search(
        r"\b(?:not|no|never|don't|do not|isn't|is not)\s+(?:a\s+)?(?:four|4|multi|multiple)[-\s]?pages?\b",
        text,
    )
    return not affirmative_multi_page or bool(negated_multi_page)


def _scaffold_copy_issues(surface_text: str, files: list[Path], request: str) -> list[dict[str, Any]]:
    text = surface_text.lower()
    request_lower = request.lower()
    issues: list[dict[str, Any]] = []
    stale = [phrase for phrase in GENERIC_COPY if phrase.lower() in text and phrase.lower() not in request_lower]
    if stale:
        issues.append(_issue("generic_scaffold_copy", 5, f"Visible surfaces contain scaffold/generic copy: {', '.join(stale[:5])}.", [str(path) for path in files[:8]]))
    rendered_files = [path for path in files if _is_rendered_surface_file(path)]
    rendered_text = "\n".join(path.read_text(encoding="utf-8", errors="ignore")[:120000] for path in rendered_files).lower()
    if request and request[:180].lower() in rendered_text:
        issues.append(_issue("raw_request_visible", 5, "Visible UI appears to render the raw user request.", [str(path) for path in rendered_files[:8]]))
    if _affirmative_industry_mention(request_lower, "construction"):
        needed = ("construction", "builder", "project", "safety", "services")
        missing = [term for term in needed if term not in text]
        if missing:
            issues.append(_issue("missing_domain_copy", 4, f"Construction-company copy is missing core terms: {', '.join(missing)}.", [str(path) for path in files[:8]]))
    if _energy_climate_request(request_lower):
        required = [term for term in ("energy", "microgrid", "solar", "battery", "grid", "demand", "outage", "building", "load", "resilience") if term in request_lower]
        missing = [term for term in (required[:6] or ["energy", "grid", "building"]) if term not in text]
        if missing:
            issues.append(_issue("missing_domain_copy", 4, f"Climate/energy copy is missing core terms: {', '.join(missing)}.", [str(path) for path in files[:8]]))
        wrong_domain = [term for term in _energy_wrong_domain_terms() if term not in request_lower and term in text]
        if wrong_domain:
            issues.append(_issue("wrong_domain_copy", 5, f"Climate/energy request drifted into wrong-domain copy: {', '.join(wrong_domain[:5])}.", [str(path) for path in files[:8]]))
    repeated_page_labels = re.findall(r"\b(?:home|about|service|services|contact)\s+[0-9]\b", text, flags=re.IGNORECASE)
    if repeated_page_labels:
        issues.append(_issue("stitch_page_label_artifacts", 5, "Visible UI contains page-label artifacts like Home 1 or Service 2 from design generation.", [str(path) for path in files[:8]]))
    return issues


def _energy_climate_request(request_lower: str) -> bool:
    return any(
        term in request_lower
        for term in (
            "climate-tech",
            "climatetech",
            "climate-risk",
            "climate risk",
            "property risk",
            "portfolio risk",
            "wildfire",
            "flood",
            "heat risk",
            "insurance risk",
            "tenant-impact",
            "tenant impact",
            "clean energy",
            "energy management",
            "energy grid",
            "microgrid",
            "microgrids",
            "solar",
            "battery",
            "batteries",
            "demand spike",
            "demand spikes",
            "outage risk",
            "building energy",
            "commercial building",
            "commercial buildings",
            "grid monitoring",
            "renewable",
            "decarbonization",
        )
    )


def _energy_wrong_domain_terms() -> tuple[str, ...]:
    return (
        "construction services",
        "contractor",
        "jobsite",
        "handover",
        "crane",
        "concrete",
        "bid package",
        "atelier",
        "collections",
        "private inquiry",
        "private clients",
        "private client",
        "private appointment",
        "high-intent clients",
        "concierge",
        "concierge access",
        "permanent legacy",
        "craftsmanship",
        "provenance",
        "notice the difference",
        "crafted for private",
        "quiet confidence",
        "every detail",
        "material integrity",
        "intelligence collection",
        "appointment",
        "self-hosted backend",
        "web3 modules",
        "web3 module",
        "cli install",
        "api routes",
        "schema builder",
    )


def _interaction_static_issues(surface_text: str, files: list[Path], request: str) -> list[dict[str, Any]]:
    text = surface_text.lower()
    issues: list[dict[str, Any]] = []
    bad_links = [pattern for pattern in BAD_LINK_PATTERNS if pattern in text]
    if bad_links:
        issues.append(_issue("dead_static_links", 4, "Static UI contains dead #/javascript links.", [str(path) for path in files[:8]]))
    if ("no login" in request.lower() or "not a login" in request.lower()) and "sign in" in text:
        issues.append(_issue("forbidden_login_copy", 4, "Request said not to build a login portal, but visible copy includes Sign in.", [str(path) for path in files[:8]]))
    for path in files:
        if path.name == "globals.css" and "overflow-wrap" not in path.read_text(encoding="utf-8", errors="ignore"):
            issues.append(_issue("css_missing_overflow_guard", 3, "Global CSS does not protect long headings from clipping.", [str(path)]))
            break
    return issues


def _experience_mode_static_issues(project_root: Path, surface_text: str, files: list[Path], request: str) -> list[dict[str, Any]]:
    text = request.lower()
    code = surface_text.lower() + "\n" + _package_text(project_root).lower()
    issues: list[dict[str, Any]] = []
    wants_3d = any(term in text for term in ("3d", "three.js", "webgl", "react-three", "react three", "interactive scene", "immersive scene"))
    wants_parallax = any(term in text for term in ("parallax", "scroll animation", "scroll-driven", "scroll driven", "pinned scroll", "cinematic scroll"))
    wants_motion = wants_3d or wants_parallax or any(term in text for term in ("animation", "animated", "motion", "microinteraction", "micro-interaction"))
    if wants_3d:
        has_3d_code = any(term in code for term in ("three", "@react-three/fiber", "@react-three/drei", "<canvas", "webgl", "canvas"))
        if not has_3d_code:
            issues.append(_issue("missing_immersive_3d_implementation", 5, "Request asks for a 3D/immersive experience, but visible code/dependencies show no canvas, WebGL, Three.js, or scene implementation.", [str(path) for path in files[:8]]))
    if wants_parallax:
        has_parallax = any(term in code for term in ("parallax", "scroll-timeline", "animation-timeline", "gsap", "framer-motion", "motion/react", "position: sticky", "translate3d", "will-change: transform"))
        if not has_parallax:
            issues.append(_issue("missing_parallax_scroll_implementation", 5, "Request asks for parallax/cinematic scroll, but visible code shows no scroll-motion implementation.", [str(path) for path in files[:8]]))
    if wants_motion:
        has_reduced_motion = "prefers-reduced-motion" in code or "useReducedMotion" in surface_text or "use-reduced-motion" in code
        if not has_reduced_motion:
            issues.append(_issue("missing_reduced_motion_fallback", 4, "Motion/3D/parallax work needs a prefers-reduced-motion or equivalent fallback.", [str(path) for path in files[:8]]))
    return issues


def _package_text(project_root: Path) -> str:
    package_path = project_root / "package.json"
    if not package_path.exists():
        return ""
    return package_path.read_text(encoding="utf-8", errors="ignore")[:120000]


def _design_handoff_issues(design_handoff: dict[str, Any]) -> list[dict[str, Any]]:
    if not design_handoff:
        return []
    if design_handoff.get("ok") or design_handoff.get("frontend_handoff_allowed"):
        return []
    summary = _clean(design_handoff.get("summary") or "Design handoff is not accepted.")
    return [_issue("design_handoff_blocked", 5, summary, [str(item) for item in (design_handoff.get("artifacts") or [])[:8]])]


def _visual_gate_issues(gate_results: dict[str, Any]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    for gate in gate_results.get("gates") or []:
        if not isinstance(gate, dict) or gate.get("id") != "browser_visual_review":
            continue
        metadata = gate.get("metadata") if isinstance(gate.get("metadata"), dict) else {}
        findings = [str(item) for item in (metadata.get("findings") or []) if _clean(item)]
        for finding in findings:
            lowered = finding.lower()
            issue_id = "visual_quality"
            if "h1" in lowered and "large" in lowered:
                issue_id = "visual_h1_too_large"
            elif "horizontal overflow" in lowered:
                issue_id = "visual_horizontal_overflow"
            elif "overflow the viewport" in lowered:
                issue_id = "visual_clipped_elements"
            elif "extends beyond" in lowered:
                issue_id = "visual_hero_extends"
            elif "dead link" in lowered:
                issue_id = "visual_dead_link"
            elif "incoherent visible headline" in lowered or "incoherent visible copy" in lowered:
                issue_id = "visual_incoherent_copy"
            elif "stock/person portrait" in lowered or "portrait imagery" in lowered:
                issue_id = "visual_wrong_hero_imagery"
            elif "insufficient landing-page depth" in lowered or "insufficient landing page depth" in lowered:
                issue_id = "visual_shallow_landing_page"
            elif "requested 3d/immersive" in lowered:
                issue_id = "visual_missing_immersive_scene"
            elif "requested parallax/cinematic" in lowered:
                issue_id = "visual_missing_parallax_motion"
            elif "prefers-reduced-motion" in lowered:
                issue_id = "visual_missing_reduced_motion"
            issues.append(_issue(issue_id, 5, finding, [str(item) for item in gate.get("evidence") or []]))
    return issues


def _surface_files(project_root: Path) -> list[Path]:
    applied = _applied_design_files(project_root)
    if applied:
        return applied
    candidates = [project_root / item for item in VISIBLE_SURFACE_CANDIDATES if (project_root / item).exists()]
    app_root = project_root / "src" / "app"
    if app_root.exists():
        for path in sorted(app_root.glob("*/page.tsx")):
            if path not in candidates:
                candidates.append(path)
    return candidates


def _applied_design_files(project_root: Path) -> list[Path]:
    manifest = project_root / FRIDAY_DIR / "design" / "applied-design.json"
    if not manifest.exists():
        return []
    try:
        payload = json.loads(manifest.read_text(encoding="utf-8"))
    except Exception:
        return []
    files: list[Path] = []
    for raw in payload.get("files") or []:
        path = Path(str(raw))
        if not path.is_absolute():
            path = project_root / path
        try:
            path.resolve().relative_to(project_root.resolve())
        except Exception:
            continue
        if path.exists() and path.suffix.lower() in {".ts", ".tsx", ".css"}:
            files.append(path)
    return files


def _is_rendered_surface_file(path: Path) -> bool:
    normalized = path.as_posix().lower()
    return "/src/app/" in normalized or "/src/components/" in normalized or "\\src\\app\\" in str(path).lower() or "\\src\\components\\" in str(path).lower()


def _expected_website_routes(project_root: Path, request: str) -> dict[str, Path]:
    labels = _explicit_page_labels(request)
    if not labels:
        labels = ["Home", "About", "Services", "Contact"]
    routes: dict[str, Path] = {}
    for label in labels:
        route_id = _route_id(label)
        if route_id == "home":
            routes["home"] = project_root / "src" / "app" / "page.tsx"
        else:
            routes[route_id] = project_root / "src" / "app" / route_id / "page.tsx"
    return routes


def _explicit_page_labels(request: str) -> list[str]:
    text = _clean(request)
    patterns = [
        r"\bpages?\s+must\s+be\s+([^.\n]+)",
        r"\bpages?\s+should\s+be\s+([^.\n]+)",
        r"\bpages?\s+(?:include|including)\s+([^.\n]+)",
        r"\bwith\s+(?:the\s+)?(?:following\s+)?(?:four|4)[-\s ]?pages?\s*:?\s+([^.\n]+)",
        r"\b(?:four|4)[-\s ]?pages?\s*:?\s+([^.\n]+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if not match:
            continue
        labels = _split_labels(match.group(1))
        if len(labels) >= 2:
            return labels[:6]
    return []


def _split_labels(raw: str) -> list[str]:
    text = re.sub(r"\([^)]*\)", " ", str(raw or ""))
    parts = re.split(r",|/|\s+\band\b\s+", text)
    labels: list[str] = []
    for part in parts:
        label = _clean(part).strip(" .:;-\"'")
        label = re.sub(r"^(?:and|plus|including)\s+", "", label, flags=re.IGNORECASE).strip()
        if label and len(label) <= 40:
            labels.append(label.title() if label.islower() else label)
    return _dedupe(labels)


def _route_id(label: str) -> str:
    lowered = _clean(label).lower()
    if lowered == "home":
        return "home"
    if "contact" in lowered:
        return "contact"
    return re.sub(r"[^a-z0-9]+", "-", lowered).strip("-") or "page"


def _affirmative_industry_mention(request_lower: str, term: str) -> bool:
    if term not in request_lower:
        return False
    negated_patterns = [
        rf"\bdo\s+not\s+(?:make\s+it\s+)?(?:look\s+like\s+)?[^.]*\b{re.escape(term)}\b",
        rf"\bdon't\s+(?:make\s+it\s+)?(?:look\s+like\s+)?[^.]*\b{re.escape(term)}\b",
        rf"\bnot\s+(?:a\s+|an\s+)?[^.]*\b{re.escape(term)}\b",
        rf"\bavoid\s+[^.]*\b{re.escape(term)}\b",
    ]
    return not any(re.search(pattern, request_lower) for pattern in negated_patterns)


def _safe_fix_available(issues: list[dict[str, Any]], project_root: Path) -> bool:
    ids = {str(item.get("id") or "") for item in issues}
    return bool(ids & {"visual_h1_too_large", "visual_horizontal_overflow", "visual_clipped_elements", "css_missing_overflow_guard", "visual_hero_extends"}) and (
        (project_root / "src" / "app" / "globals.css").exists() or (project_root / "src" / "components" / "Stitch" / "StitchNativePage.module.css").exists()
    )


def _score(issues: list[dict[str, Any]]) -> int:
    penalty = sum(max(1, int(item.get("severity") or 1)) * 7 for item in issues)
    return max(0, min(100, 100 - penalty))


def _summary(score: int, threshold: int, issues: list[dict[str, Any]]) -> str:
    if score >= threshold and not [item for item in issues if int(item.get("severity") or 0) >= 4]:
        return f"Quality taste review passed with score {score}/100."
    return f"Quality taste review found {len(issues)} issue(s), score {score}/100; threshold is {threshold}/100."


def _write_report(project_root: Path, report: dict[str, Any]) -> list[str]:
    root = project_root / FRIDAY_DIR / STUDIO_DIR / QUALITY_DIR
    root.mkdir(parents=True, exist_ok=True)
    json_path = root / "taste-review.json"
    md_path = root / "taste-review.md"
    json_path.write_text(json.dumps(report, ensure_ascii=True, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    md_path.write_text(_markdown(report), encoding="utf-8")
    return [str(json_path), str(md_path)]


def _markdown(report: dict[str, Any]) -> str:
    issues = report.get("issues") if isinstance(report.get("issues"), list) else []
    lines = [
        "# Friday Quality Taste Review",
        "",
        f"Status: {report.get('status')}",
        f"Score: {report.get('score')}/{report.get('threshold')}",
        "",
        "## Summary",
        str(report.get("summary") or ""),
        "",
        "## Issues",
    ]
    if issues:
        lines.extend(f"- severity {item.get('severity')}: {item.get('summary')}" for item in issues if isinstance(item, dict))
    else:
        lines.append("- No taste or visual blocking issues detected.")
    return "\n".join(lines) + "\n"


def _append_once(path: Path, marker: str, content: str) -> bool:
    if not path.exists():
        return False
    body = path.read_text(encoding="utf-8", errors="ignore")
    if marker in body:
        return False
    path.write_text(body.rstrip() + content + "\n", encoding="utf-8")
    return True


def _issue(issue_id: str, severity: int, summary: str, evidence: list[str] | None = None) -> dict[str, Any]:
    return {"id": issue_id, "severity": severity, "summary": _clean(summary), "evidence": [item for item in (evidence or []) if _clean(item)]}


def _relative(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except Exception:
        return str(path)


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").replace("\x00", " ")).strip()


def _dedupe(items: list[str]) -> list[str]:
    result: list[str] = []
    for item in items:
        text = _clean(item)
        if text and text not in result:
            result.append(text)
    return result
