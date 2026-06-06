from pathlib import Path

from core import product_build_loop, product_studio


def _write_minimal_next_project(root: Path) -> None:
    files = {
        "src/app/page.tsx": "import { HomePage } from '@/components/Landing/HomePage';\nexport default function Page() { return <HomePage />; }\n",
        "src/app/about/page.tsx": "import { AboutPage } from '@/components/Marketing/AboutPage';\nexport default function Page() { return <AboutPage />; }\n",
        "src/app/services/page.tsx": "import { ServicesPage } from '@/components/Marketing/ServicesPage';\nexport default function Page() { return <ServicesPage />; }\n",
        "src/app/contact/page.tsx": "import { ContactPage } from '@/components/Marketing/ContactPage';\nexport default function Page() { return <ContactPage />; }\n",
        "src/app/globals.css": "body { margin: 0; }\n",
        "src/lib/siteContent.ts": "export const siteContent = { brand: 'Turner Construction Company', hero: 'construction builder project safety services' };\n",
    }
    for relative, content in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


def test_product_build_loop_blocks_before_gates_when_design_handoff_fails(monkeypatch, tmp_path):
    _write_minimal_next_project(tmp_path)
    monkeypatch.setattr(
        product_studio,
        "prepare_design_handoff",
        lambda *args, **kwargs: {
            "ok": False,
            "status": "partial",
            "summary": "Prepared 4 website page design run(s); 0/4 selected handoff(s).",
            "frontend_handoff_allowed": False,
            "design_critique": {"pages": [{"label": "Home", "status": "failed", "frontend_handoff_allowed": False, "summary": "Stitch SDK failed: fetch failed"}]},
            "artifacts": [str(tmp_path / ".friday/design/pages/home/stitch-run.log")],
        },
    )

    def fail_if_called(*args, **kwargs):
        raise AssertionError("gate runner should not run")

    result = product_build_loop.run_after_scaffold(
        tmp_path,
        "Build a normal website for a real construction company: Turner Construction Company",
        product_name="Turner Construction Company",
        stack={"stack": "nextjs", "kind": "web_app"},
        run_live_design=True,
        gate_runner=fail_if_called,
    )

    assert result["status"] == "blocked"
    assert result["workflow_phases"] == ["inspect", "plan", "design_handoff", "taste_preflight", "verify_fix_retry", "prove"]
    assert result["gate_results"]["gates"][0]["id"] == "design_provider_handoff"
    assert (tmp_path / ".friday" / "product-studio" / "implementation-loop" / "implementation-loop.json").exists()


def test_prepare_design_handoff_blocks_when_pipeline_disabled(monkeypatch, tmp_path):
    monkeypatch.setattr(product_studio, "config_value", lambda key, default=None: False if key == "design_pipeline_enabled" else default)

    result = product_studio.prepare_design_handoff(
        tmp_path,
        "Build a landing page for Nexus Forge as a developer-tools web app.",
        product_name="Nexus Forge",
        stack={"stack": "nextjs", "kind": "web_app"},
        run_live=True,
        apply_to_source=True,
    )

    assert result["ok"] is False
    assert result["status"] == "disabled"
    assert result["frontend_handoff_allowed"] is False
    assert "legacy design fallback is not used" in result["summary"]


def test_product_build_loop_applies_visual_fix_and_reruns_gates(monkeypatch, tmp_path):
    _write_minimal_next_project(tmp_path)
    (tmp_path / "src/app/globals.css").write_text("body { margin: 0; }\nh1 { overflow-wrap: anywhere; }\n", encoding="utf-8")
    calls = []
    monkeypatch.setattr(product_build_loop, "config_value", lambda key, default=None: 2 if key == "friday_product_loop_max_attempts" else default)
    monkeypatch.setattr(
        product_studio,
        "prepare_design_handoff",
        lambda *args, **kwargs: {"ok": True, "status": "selected", "frontend_handoff_allowed": True, "summary": "Design selected.", "artifacts": []},
    )

    def gate_runner(project_root, *, stack, install, request):
        calls.append(1)
        visual_gate = {
            "id": "browser_visual_review",
            "label": "Rendered UI visual review",
            "status": "failed" if len(calls) == 1 else "passed",
            "required": True,
            "summary": "H1 too large" if len(calls) == 1 else "Visual review passed.",
            "evidence": [],
            "metadata": {"findings": ["desktop: H1 font is too large (120px)."] if len(calls) == 1 else []},
        }
        return {
            "status": "attention" if len(calls) == 1 else "passed",
            "technical_ready": len(calls) > 1,
            "failed_required": ["Rendered UI visual review: failed - H1 too large"] if len(calls) == 1 else [],
            "gates": [visual_gate],
            "artifacts": [],
            "summary": "fake gates",
        }

    result = product_build_loop.run_after_scaffold(
        tmp_path,
        "Build a normal website for a real construction company: Turner Construction Company",
        product_name="Turner Construction Company",
        stack={"stack": "nextjs", "kind": "web_app"},
        run_live_design=True,
        gate_runner=gate_runner,
    )

    assert len(calls) == 2
    assert result["gate_results"]["technical_ready"] is True
    assert result["workflow_backend"] in {"langgraph", "native"}
    assert result["fix_attempts"]
    assert "Friday quality guard" in (tmp_path / "src/app/globals.css").read_text(encoding="utf-8")


def test_product_build_loop_reruns_design_for_non_css_taste_failures(monkeypatch, tmp_path):
    _write_minimal_next_project(tmp_path)
    design_calls = []
    review_calls = []
    gate_calls = []

    def fake_design(root, request, **kwargs):
        design_calls.append(request)
        return {
            "ok": True,
            "status": "applied",
            "summary": "Design handoff applied.",
            "frontend_handoff_allowed": True,
            "applied_design": {"ok": True, "files": [str(tmp_path / "src/components/Stitch/StitchNativePage.tsx")]},
            "artifacts": [str(tmp_path / ".friday/design/frontend-handoff.json")],
        }

    def fake_review(root, request, **kwargs):
        review_calls.append(1)
        if len(review_calls) == 1:
            return {"ok": True, "status": "passed", "summary": "preflight ok", "issues": [], "artifacts": []}
        if len(review_calls) == 2:
            return {
                "ok": False,
                "status": "needs_revision",
                "summary": "visual copy failed",
                "issues": [
                    {"id": "visual_incoherent_copy", "severity": 5, "summary": "desktop: incoherent visible headline copy found."},
                    {"id": "visual_wrong_hero_imagery", "severity": 5, "summary": "desktop: developer-tools hero uses stock/person portrait imagery."},
                ],
                "artifacts": [],
            }
        return {"ok": True, "status": "passed", "summary": "revised ok", "issues": [], "artifacts": []}

    def fake_gates(project_root, *, stack, install, request):
        gate_calls.append(1)
        ready = len(gate_calls) > 1
        return {
            "status": "passed" if ready else "attention",
            "technical_ready": ready,
            "failed_required": [] if ready else ["Rendered UI visual review: failed - incoherent visible headline copy found."],
            "gates": [
                {
                    "id": "browser_visual_review",
                    "label": "Rendered UI visual review",
                    "status": "passed" if ready else "failed",
                    "required": True,
                    "summary": "ok" if ready else "incoherent visible headline copy found.",
                    "evidence": [],
                    "metadata": {"findings": [] if ready else ["desktop: incoherent visible headline copy found."]},
                }
            ],
            "artifacts": [],
            "summary": "fake gates",
        }

    monkeypatch.setattr(product_studio, "prepare_design_handoff", fake_design)
    monkeypatch.setattr(product_build_loop.quality_taste_layer, "review_project", fake_review)
    monkeypatch.setattr(product_build_loop.quality_taste_layer, "apply_safe_fixes", lambda *args, **kwargs: {"ok": False, "status": "no_safe_fix", "summary": "No CSS fix."})
    monkeypatch.setattr(product_build_loop, "config_value", lambda key, default=None: 2 if key == "friday_product_loop_max_attempts" else default)

    result = product_build_loop.run_after_scaffold(
        tmp_path,
        "Build a landing page for Nexus Forge, an open-source backend-as-a-service developer tool.",
        product_name="Nexus Forge",
        stack={"stack": "nextjs", "kind": "web_app"},
        run_live_design=True,
        gate_runner=fake_gates,
    )

    assert result["status"] == "passed"
    assert len(gate_calls) == 2
    assert len(design_calls) == 2
    assert "Design revision required by Friday visual/taste review" in design_calls[-1]
    assert any(item.get("status") == "design_revision_applied" for item in result["fix_attempts"])
