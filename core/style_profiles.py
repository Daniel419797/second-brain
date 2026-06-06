"""Reusable project style profiles for Friday's engineering operating system."""

from __future__ import annotations

import datetime as dt
import json
import re
import sqlite3
import threading
from pathlib import Path
from typing import Any

from core.config import DATA_DIR, ensure_runtime_dirs

DB_PATH = DATA_DIR / "style_profiles.sqlite3"
_LOCK = threading.Lock()


NEXUS_FORGE_NEXTJS = {
    "id": "nexus_forge_nextjs",
    "name": "NexusForge Next.js",
    "framework": "nextjs",
    "description": "User's preferred production Next.js shape: thin app routes, feature components, services, stores, hooks, lib, shared types, and tests.",
    "required_paths": [
        "src/app",
        "src/components",
        "src/components/ui",
        "src/components/layout",
        "src/services",
        "src/store",
        "src/hooks",
        "src/lib",
        "src/types",
        "src/test",
        "components.json",
        "vitest.config.ts",
    ],
    "forbidden_paths": [
        "src/components/WorkspaceConsole.tsx",
        "src/components/WorkItemCard.tsx",
    ],
    "rules": [
        "Use src/app only for routes, layouts, route handlers, and route-local boundaries.",
        "Put real feature UI in src/components/<FeatureName>.",
        "Put generic primitives in src/components/ui.",
        "Put navigation and shell components in src/components/layout.",
        "Put API clients and response normalization in src/services.",
        "Put shared browser state in src/store.",
        "Put reusable client workflows in src/hooks.",
        "Put domain helpers, utilities, security helpers, and product contracts in src/lib.",
        "Put shared DTOs and UI contracts in src/types.",
        "Keep tests colocated in __tests__ or shared under src/test.",
        "Do not put large feature UI, state, services, and route logic into one blob.",
    ],
    "evidence": [
        "FRONTEND_STRUCTURE.md in C:/Users/HomePC/Desktop/my_project/frontend",
        "components.json uses @/ aliases and lucide icons",
        "Route groups: (auth), (dashboard), (test), public legal routes",
    ],
}

DEFAULT_PROFILES = {NEXUS_FORGE_NEXTJS["id"]: NEXUS_FORGE_NEXTJS}


def init_db(path: Path | None = None) -> None:
    ensure_runtime_dirs()
    db_path = path or DB_PATH
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path, timeout=10) as conn:
        try:
            conn.execute("PRAGMA journal_mode=WAL")
        except sqlite3.OperationalError:
            pass
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS style_profiles (
                id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                name TEXT NOT NULL,
                framework TEXT NOT NULL,
                description TEXT NOT NULL,
                profile_json TEXT NOT NULL
            )
            """
        )


def list_profiles() -> list[dict[str, Any]]:
    init_db()
    profiles = [dict(profile) for profile in DEFAULT_PROFILES.values()]
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM style_profiles ORDER BY updated_at DESC").fetchall()
    seen = {profile["id"] for profile in profiles}
    for row in rows:
        profile = _json_loads(row["profile_json"], {})
        if isinstance(profile, dict) and profile.get("id") not in seen:
            profiles.append(profile)
            seen.add(str(profile.get("id")))
    return profiles


def get_profile(profile_id: str = "nexus_forge_nextjs") -> dict[str, Any] | None:
    clean_id = _slug(profile_id) or "nexus_forge_nextjs"
    if clean_id in DEFAULT_PROFILES:
        return dict(DEFAULT_PROFILES[clean_id])
    init_db()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT profile_json FROM style_profiles WHERE id=?", (clean_id,)).fetchone()
    if not row:
        return None
    profile = _json_loads(row["profile_json"], {})
    return profile if isinstance(profile, dict) else None


def save_profile(profile: dict[str, Any]) -> dict[str, Any]:
    init_db()
    profile_id = _slug(profile.get("id") or profile.get("name") or "custom_profile")
    payload = {
        "id": profile_id,
        "name": _clean(profile.get("name") or profile_id.replace("_", " ").title()),
        "framework": _clean(profile.get("framework") or "generic").lower(),
        "description": _clean(profile.get("description") or ""),
        "required_paths": _strings(profile.get("required_paths") or []),
        "forbidden_paths": _strings(profile.get("forbidden_paths") or []),
        "rules": _strings(profile.get("rules") or []),
        "evidence": _strings(profile.get("evidence") or []),
    }
    now = _now()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.execute(
            """
            INSERT INTO style_profiles(id, created_at, updated_at, name, framework, description, profile_json)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET updated_at=excluded.updated_at, name=excluded.name, framework=excluded.framework, description=excluded.description, profile_json=excluded.profile_json
            """,
            (payload["id"], now, now, payload["name"], payload["framework"], payload["description"], _json_dumps(payload)),
        )
    return payload


def infer_profile(root: str | Path, framework: str = "") -> dict[str, Any] | None:
    base = Path(root)
    normalized_framework = _clean(framework).lower()
    if normalized_framework == "nextjs" or (base / "next.config.mjs").exists() or (base / "next.config.js").exists():
        return get_profile("nexus_forge_nextjs")
    return None


def evaluate_project(root: str | Path, profile_id: str = "nexus_forge_nextjs") -> dict[str, Any]:
    profile = get_profile(profile_id)
    if not profile:
        return {"ok": False, "profile_id": profile_id, "summary": "Style profile not found.", "checks": [], "gaps": ["style profile not found"]}
    base = Path(root).resolve()
    single_landing = profile.get("id") == "nexus_forge_nextjs" and _is_single_landing_project(base)
    web_contract = profile.get("id") == "nexus_forge_nextjs" and _is_web_contract_project(base)
    stitch_native = profile.get("id") == "nexus_forge_nextjs" and _is_stitch_native_project(base)
    required_paths = list(profile.get("required_paths") or [])
    if single_landing or web_contract or stitch_native:
        required_paths = [
            relative
            for relative in required_paths
            if relative
            not in {
                "src/components/layout",
                *({"src/services", "src/store", "src/hooks"} if single_landing or stitch_native else set()),
            }
        ]
    if single_landing:
        landing_component_path = _single_landing_component_path(base)
        if landing_component_path and landing_component_path not in required_paths:
            required_paths.insert(2, landing_component_path)
    if web_contract and "src/components/WebContract" not in required_paths:
        required_paths.insert(2, "src/components/WebContract")
    if stitch_native and "src/components/Stitch" not in required_paths:
        required_paths.insert(2, "src/components/Stitch")
    checks: list[dict[str, Any]] = []
    gaps: list[str] = []
    for relative in required_paths:
        exists = (base / relative).exists()
        checks.append({"id": f"path:{relative}", "label": f"Required path: {relative}", "status": "passed" if exists else "failed"})
        if not exists:
            gaps.append(f"Missing required style path: {relative}")
    for relative in profile.get("forbidden_paths") or []:
        exists = (base / relative).exists()
        checks.append({"id": f"forbidden:{relative}", "label": f"Forbidden flat file: {relative}", "status": "failed" if exists else "passed"})
        if exists:
            gaps.append(f"Flat blob path is forbidden by style profile: {relative}")
    if profile.get("id") == "nexus_forge_nextjs":
        checks.extend(_nextjs_shape_checks(base, gaps, single_landing=single_landing, web_contract=web_contract, stitch_native=stitch_native))
    ok = not gaps
    return {
        "ok": ok,
        "profile": profile,
        "profile_id": profile.get("id"),
        "root": str(base),
        "checks": checks,
        "gaps": gaps,
        "summary": "Style profile satisfied." if ok else f"Style profile has {len(gaps)} gap(s).",
    }


def apply_profile(root: str | Path, profile_id: str = "nexus_forge_nextjs") -> dict[str, Any]:
    evaluation = evaluate_project(root, profile_id)
    profile = evaluation.get("profile") or {}
    root_path = Path(root).resolve()
    marker = root_path / ".friday" / "style-profile.json"
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(_json_dumps({"profile_id": profile.get("id"), "applied_at": _now(), "evaluation": evaluation}), encoding="utf-8")
    return {**evaluation, "artifact": str(marker)}


def status(root: str | Path = "") -> dict[str, Any]:
    profiles = list_profiles()
    result = {"profiles": profiles, "summary": f"{len(profiles)} style profile(s) available."}
    if root:
        profile = infer_profile(root)
        result["evaluation"] = evaluate_project(root, profile.get("id") if profile else "nexus_forge_nextjs")
    return result


def _nextjs_shape_checks(base: Path, gaps: list[str], *, single_landing: bool = False, web_contract: bool = False, stitch_native: bool = False) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    page = _read(base / "src/app/page.tsx")
    components_json = _read(base / "components.json")
    service_files = list((base / "src/services").glob("*.ts")) if (base / "src/services").exists() else []
    store_files = list((base / "src/store").glob("*.ts")) if (base / "src/store").exists() else []
    hook_files = list((base / "src/hooks").glob("*.ts")) if (base / "src/hooks").exists() else []
    route_blob = bool(page and ("useState" in page or "axios" in page or "fetch(" in page) and "components/" not in page)
    checks.append({"id": "thin_routes", "label": "Route files stay thin", "status": "failed" if route_blob else "passed"})
    if route_blob:
        gaps.append("src/app/page.tsx appears to mix route, UI state, and data access instead of composing feature components.")
    if single_landing:
        landing_component = (base / "src/components/Landing/SingleLandingPage.tsx").exists() or (base / "src/components/Stitch/StitchNativePage.tsx").exists()
        landing_content = (base / "src/lib/landingContent.ts").exists() or (base / "src/lib/stitchNativeContent.ts").exists()
        checks.append({"id": "single_landing_component", "label": "Single landing component exists", "status": "passed" if landing_component else "failed"})
        checks.append({"id": "single_landing_content", "label": "Landing content contract exists", "status": "passed" if landing_content else "failed"})
        if not landing_component:
            gaps.append("Single landing profile expects a landing component under src/components/Landing or src/components/Stitch.")
        if not landing_content:
            gaps.append("Single landing profile expects src/lib/landingContent.ts or src/lib/stitchNativeContent.ts.")
    elif stitch_native:
        native_component = (base / "src/components/Stitch/StitchNativePage.tsx").exists()
        native_content = (base / "src/lib/stitchNativeContent.ts").exists()
        checks.append({"id": "stitch_native_component", "label": "Stitch-native component exists", "status": "passed" if native_component else "failed"})
        checks.append({"id": "stitch_native_content", "label": "Stitch-native content contract exists", "status": "passed" if native_content else "failed"})
        if not native_component:
            gaps.append("Stitch-native projects need src/components/Stitch/StitchNativePage.tsx.")
        if not native_content:
            gaps.append("Stitch-native projects need src/lib/stitchNativeContent.ts.")
    elif web_contract:
        contract_files = [
            base / "src/lib/webProjectContract.ts",
            base / "src/components/WebContract/ContractShell.tsx",
            base / "src/components/WebContract/WebContractPage.tsx",
        ]
        contract_ok = all(path.exists() for path in contract_files)
        checks.append({"id": "web_contract_surface", "label": "Web project contract surface exists", "status": "passed" if contract_ok else "failed"})
        if not contract_ok:
            gaps.append("Web contract projects need src/lib/webProjectContract.ts and src/components/WebContract shell/page components.")
        for label, files in (("services", service_files), ("stores", store_files), ("hooks", hook_files)):
            passed = bool(files)
            checks.append({"id": f"has_{label}", "label": f"Has src/{label[:-1] if label.endswith('s') else label}", "status": "passed" if passed else "failed"})
            if not passed:
                gaps.append(f"NexusForge style expects src/{label} files.")
    else:
        for label, files in (("services", service_files), ("stores", store_files), ("hooks", hook_files)):
            passed = bool(files)
            checks.append({"id": f"has_{label}", "label": f"Has src/{label[:-1] if label.endswith('s') else label}", "status": "passed" if passed else "failed"})
            if not passed:
                gaps.append(f"NexusForge style expects src/{label} files.")
    aliases_ok = "@/components" in components_json and "@/lib" in components_json and "@/hooks" in components_json
    checks.append({"id": "components_aliases", "label": "components.json aliases", "status": "passed" if aliases_ok else "failed"})
    if not aliases_ok:
        gaps.append("components.json should declare @/components, @/lib, and @/hooks aliases.")
    return checks


def _is_single_landing_project(base: Path) -> bool:
    page = _read(base / "src/app/page.tsx")
    explicit_landing = bool(
        (base / "src/components/Landing/SingleLandingPage.tsx").exists()
        and (base / "src/lib/landingContent.ts").exists()
        and "SingleLandingPage" in page
    )
    native_landing = bool(
        (base / "src/lib/stitchNativeContent.ts").exists()
        and (base / "src/components/Stitch/StitchNativePage.tsx").exists()
        and ("StitchNativePage" in page or "StitchPageSurface" in page)
        and not _has_public_app_route_dirs(base)
    )
    return explicit_landing or native_landing


def _is_stitch_native_project(base: Path) -> bool:
    page = _read(base / "src/app/page.tsx")
    return bool(
        (base / "src/lib/stitchNativeContent.ts").exists()
        and (base / "src/components/Stitch/StitchNativePage.tsx").exists()
        and ("StitchNativePage" in page or "StitchPageSurface" in page or _has_public_app_route_dirs(base))
    )


def _is_web_contract_project(base: Path) -> bool:
    page = _read(base / "src/app/page.tsx")
    landing_home = _read(base / "src/components/Landing/HomePage.tsx")
    contract = _read(base / "src/lib/webProjectContract.ts")
    return bool(
        (base / "src/lib/webProjectContract.ts").exists()
        and (base / "src/components/WebContract/ContractShell.tsx").exists()
        and (base / "src/components/WebContract/WebContractPage.tsx").exists()
        and (
            "WebContractPage" in page
            or "DashboardPreviewPage" in page
            or "ContractShell" in page
            or "WebContractPage" in landing_home
            or "DashboardPreviewPage" in landing_home
            or "webProjectContract" in contract
        )
    )


def _single_landing_component_path(base: Path) -> str:
    if (base / "src/components/Stitch/StitchNativePage.tsx").exists():
        return "src/components/Stitch"
    if (base / "src/components/Landing/SingleLandingPage.tsx").exists():
        return "src/components/Landing"
    return ""


def _has_public_app_route_dirs(base: Path) -> bool:
    app_root = base / "src/app"
    if not app_root.exists():
        return False
    for child in app_root.iterdir():
        if not child.is_dir():
            continue
        name = child.name
        if name == "api" or name.startswith("(") or name.startswith("_"):
            continue
        return True
    return False


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""


def _strings(values: Any) -> list[str]:
    if isinstance(values, str):
        values = [values]
    return [_clean(value) for value in values or [] if _clean(value)]


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True, default=str) + "\n"


def _json_loads(value: str, default: Any) -> Any:
    try:
        return json.loads(value or "")
    except Exception:
        return default


def _slug(value: Any) -> str:
    return re.sub(r"[^a-z0-9_]+", "_", str(value or "").lower()).strip("_")


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").replace("\x00", " ")).strip()


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()
