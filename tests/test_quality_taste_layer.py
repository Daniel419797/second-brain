from pathlib import Path
import json

from core import quality_taste_layer


def test_quality_taste_review_rejects_generic_scaffold_copy(tmp_path):
    (tmp_path / "src/lib").mkdir(parents=True)
    (tmp_path / "src/app").mkdir(parents=True)
    (tmp_path / "src/lib/siteContent.ts").write_text(
        "export const siteContent = { brand: 'Normal Real Workspace', hero: 'AI-assisted everyday workflow tool' };\n",
        encoding="utf-8",
    )
    (tmp_path / "src/app/globals.css").write_text("body { margin: 0; }\n", encoding="utf-8")

    review = quality_taste_layer.review_project(
        tmp_path,
        "Build a normal website for a real construction company: Turner Construction Company",
        stack={"stack": "nextjs"},
    )

    assert review["ok"] is False
    assert any(issue["id"] == "generic_scaffold_copy" for issue in review["issues"])
    assert any(issue["id"] == "missing_domain_copy" for issue in review["issues"])
    assert (tmp_path / ".friday" / "product-studio" / "quality" / "taste-review.json").exists()


def test_quality_taste_rejects_energy_project_that_drifted_to_construction_or_developer_copy(tmp_path):
    (tmp_path / "src/lib").mkdir(parents=True)
    (tmp_path / "src/app").mkdir(parents=True)
    (tmp_path / "src/lib/stitchNativeContent.ts").write_text(
        """
export const stitchNativeContent = {
  meta: { productName: 'KineticGrid Energy' },
  pages: {
    home: {
      title: 'KineticGrid Energy builds dependable spaces from plan to handover.',
      summary: 'Construction services for contractors, jobsite safety, concrete, CLI install, and Web3 modules.'
    }
  }
} as const;
""",
        encoding="utf-8",
    )
    (tmp_path / "src/app/page.tsx").write_text("export default function Page(){ return <main>KineticGrid Energy</main>; }\n", encoding="utf-8")
    (tmp_path / "src/app/globals.css").write_text("body { margin: 0; overflow-wrap: anywhere; }\n", encoding="utf-8")

    review = quality_taste_layer.review_project(
        tmp_path,
        "Build a climate-tech website for KineticGrid Energy with microgrid, solar, battery, demand, outage, and commercial building telemetry.",
        stack={"stack": "nextjs"},
    )
    issue_ids = {issue["id"] for issue in review["issues"]}

    assert review["ok"] is False
    assert "wrong_domain_copy" in issue_ids
    assert "missing_domain_copy" in issue_ids


def test_quality_taste_safe_fix_adds_layout_guards(tmp_path):
    globals_css = tmp_path / "src/app/globals.css"
    stitch_css = tmp_path / "src/components/Stitch/StitchNativePage.module.css"
    globals_css.parent.mkdir(parents=True)
    stitch_css.parent.mkdir(parents=True)
    globals_css.write_text("body { margin: 0; }\n", encoding="utf-8")
    stitch_css.write_text(".hero h1 { font-size: 9rem; }\n", encoding="utf-8")
    review = {
        "issues": [
            {"id": "visual_h1_too_large", "severity": 5, "summary": "desktop: H1 font is too large."},
        ]
    }

    result = quality_taste_layer.apply_safe_fixes(tmp_path, review)

    assert result["ok"] is True
    assert str(globals_css) in result["changed"]
    assert str(stitch_css) in result["changed"]
    assert "overflow-wrap" in globals_css.read_text(encoding="utf-8")
    assert ".single-copy h1" in globals_css.read_text(encoding="utf-8")
    assert "normalize exaggerated Stitch hero scale" in stitch_css.read_text(encoding="utf-8")
    assert "prefers-reduced-motion" in globals_css.read_text(encoding="utf-8")


def test_quality_taste_honors_custom_website_routes_and_applied_design_scope(tmp_path):
    app = tmp_path / "src" / "app"
    for route in ("atelier", "collections", "contact"):
        (app / route).mkdir(parents=True)
        (app / route / "page.tsx").write_text("export default function Page(){ return null; }\n", encoding="utf-8")
    app.mkdir(parents=True, exist_ok=True)
    (app / "page.tsx").write_text("export default function Page(){ return null; }\n", encoding="utf-8")
    stitch = tmp_path / "src" / "components" / "Stitch" / "StitchNativePage.tsx"
    stitch.parent.mkdir(parents=True)
    stitch.write_text("export function StitchNativePage(){ return <main>Maison Noire Atelier</main>; }\n", encoding="utf-8")
    legacy = tmp_path / "src" / "components" / "Landing" / "HomePage.tsx"
    legacy.parent.mkdir(parents=True)
    legacy.write_text("<a>Open workspace</a>\n", encoding="utf-8")
    manifest = tmp_path / ".friday" / "design" / "applied-design.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(json.dumps({"files": [str(stitch), str(app / "page.tsx"), str(app / "atelier" / "page.tsx"), str(app / "collections" / "page.tsx"), str(app / "contact" / "page.tsx")]}), encoding="utf-8")

    review = quality_taste_layer.review_project(
        tmp_path,
        "Build a polished four-page Next.js website for Maison Noire Atelier, a fictional luxury watch and jewelry atelier. Pages must be Home, Atelier, Collections, and Concierge Contact. Do not make it look like SaaS, construction, or a generic service studio.",
        stack={"stack": "nextjs"},
    )

    issue_ids = {issue["id"] for issue in review["issues"]}
    assert "missing_website_routes" not in issue_ids
    assert "generic_scaffold_copy" not in issue_ids
    assert "missing_domain_copy" not in issue_ids


def test_quality_taste_does_not_require_extra_routes_for_single_page_landing_site(tmp_path):
    app = tmp_path / "src" / "app"
    app.mkdir(parents=True)
    (app / "page.tsx").write_text("export default function Page(){ return <main>Nexus Forge backend-as-a-service</main>; }\n", encoding="utf-8")
    (app / "globals.css").write_text("body { margin: 0; overflow-wrap: anywhere; }\n", encoding="utf-8")

    review = quality_taste_layer.review_project(
        tmp_path,
        "Build a polished production-quality single-page landing page website for Nexus Forge. The page should sell the product clearly. This is a landing page, not a four-page website.",
        stack={"stack": "nextjs"},
    )

    assert not any(issue["id"] == "missing_website_routes" for issue in review["issues"])


def test_quality_taste_requires_web_app_requested_routes(tmp_path):
    app = tmp_path / "src" / "app"
    app.mkdir(parents=True)
    (app / "page.tsx").write_text("export default function Page(){ return <main>CivicPermit Studio permit intake</main>; }\n", encoding="utf-8")
    (app / "globals.css").write_text("body { margin: 0; overflow-wrap: anywhere; }\n", encoding="utf-8")

    review = quality_taste_layer.review_project(
        tmp_path,
        """
        web-app: Build CivicPermit Studio.
        Required screens/routes:
        - Home landing page
        - Product page
        - Pricing page
        - Contact/demo page
        - Dashboard preview route
        """,
        stack={"stack": "nextjs"},
    )

    missing = [issue for issue in review["issues"] if issue["id"] == "missing_website_routes"]
    assert missing
    assert "product" in missing[0]["summary"].lower()
    assert "dashboard-preview" in missing[0]["summary"].lower()


def test_quality_taste_does_not_treat_negated_industry_as_domain(tmp_path):
    (tmp_path / "src/app").mkdir(parents=True)
    (tmp_path / "src/app/page.tsx").write_text("export default function Page(){ return <main>Maison Noire Atelier luxury watches</main>; }\n", encoding="utf-8")
    (tmp_path / "src/app/globals.css").write_text("body { margin: 0; overflow-wrap: anywhere; }\n", encoding="utf-8")

    review = quality_taste_layer.review_project(
        tmp_path,
        "Build a luxury website for Maison Noire Atelier. Do not make it look like construction.",
        stack={"stack": "nextjs"},
    )

    assert not any(issue["id"] == "missing_domain_copy" for issue in review["issues"])


def test_quality_taste_maps_visual_copy_and_wrong_hero_to_design_revision_issues(tmp_path):
    review = quality_taste_layer.review_project(
        tmp_path,
        "Build a landing page for Nexus Forge, an open-source backend-as-a-service developer tool.",
        stack={"stack": "nextjs"},
        gate_results={
            "gates": [
                {
                    "id": "browser_visual_review",
                    "status": "failed",
                    "evidence": [str(tmp_path / "desktop.png")],
                    "metadata": {
                        "findings": [
                            "desktop: incoherent visible headline copy found: The backend for the of indie hackers.",
                            "desktop: developer-tools hero uses stock/person portrait imagery instead of product, code, docs, or architecture proof.",
                            "desktop: insufficient landing-page depth for the requested proof, capabilities, how-it-works, security, marketplace, and CTA sections.",
                        ]
                    },
                }
            ]
        },
    )
    issue_ids = {issue["id"] for issue in review["issues"]}

    assert "visual_incoherent_copy" in issue_ids
    assert "visual_wrong_hero_imagery" in issue_ids
    assert "visual_shallow_landing_page" in issue_ids


def test_quality_taste_rejects_missing_3d_parallax_and_motion_fallback(tmp_path):
    (tmp_path / "src/app").mkdir(parents=True)
    (tmp_path / "src/app/page.tsx").write_text(
        "export default function Page(){ return <main><h1>OrbitForge</h1><p>Static page only.</p></main>; }\n",
        encoding="utf-8",
    )
    (tmp_path / "src/app/globals.css").write_text("body { margin: 0; overflow-wrap: anywhere; }\n", encoding="utf-8")

    review = quality_taste_layer.review_project(
        tmp_path,
        "Build a 3D interactive WebGL landing page with parallax scroll animation for OrbitForge.",
        stack={"stack": "nextjs"},
    )
    issue_ids = {issue["id"] for issue in review["issues"]}

    assert "missing_immersive_3d_implementation" in issue_ids
    assert "missing_parallax_scroll_implementation" in issue_ids
    assert "missing_reduced_motion_fallback" in issue_ids


def test_quality_taste_accepts_3d_signals_and_reduced_motion_fallback(tmp_path):
    (tmp_path / "src/app").mkdir(parents=True)
    (tmp_path / "src/app/page.tsx").write_text(
        """
        import { Canvas } from '@react-three/fiber';
        export default function Page(){ return <main><Canvas aria-label="OrbitForge 3D scene" /><section className="parallax">Scene</section></main>; }
        """,
        encoding="utf-8",
    )
    (tmp_path / "src/app/globals.css").write_text(
        """
        .parallax { transform: translate3d(0, 0, 0); will-change: transform; }
        @media (prefers-reduced-motion: reduce) { .parallax { transform: none; } }
        """,
        encoding="utf-8",
    )
    (tmp_path / "package.json").write_text(
        json.dumps({"dependencies": {"three": "latest", "@react-three/fiber": "latest"}}),
        encoding="utf-8",
    )

    review = quality_taste_layer.review_project(
        tmp_path,
        "Build a 3D interactive WebGL landing page with parallax scroll animation for OrbitForge.",
        stack={"stack": "nextjs"},
    )
    issue_ids = {issue["id"] for issue in review["issues"]}

    assert "missing_immersive_3d_implementation" not in issue_ids
    assert "missing_parallax_scroll_implementation" not in issue_ids
    assert "missing_reduced_motion_fallback" not in issue_ids
