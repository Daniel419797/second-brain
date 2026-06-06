from pathlib import Path

from core import design_pipeline, product_studio


def test_design_pipeline_dry_run_writes_full_stage_contract(monkeypatch, tmp_path):
    monkeypatch.setattr(design_pipeline.search_broker, "search", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("dry-run research should not call search")))

    result = design_pipeline.run(
        "Build a landing page for Nexus Forge, a developer-tools backend platform.",
        root=tmp_path,
        product_name="Nexus Forge",
        stack={"stack": "nextjs", "label": "Next.js web app"},
        dry_run=True,
    )

    stage_ids = [stage["id"] for stage in result["stages"]]
    assert result["status"] == "planned"
    assert stage_ids == [stage_id for stage_id, _label in design_pipeline.PIPELINE_STAGES]
    assert result["research"]["status"] == "planned"
    assert result["design_critique"]["status"] == "planned"
    assert (tmp_path / ".friday" / "design-pipeline" / "01-market-research.json").exists()
    assert (tmp_path / ".friday" / "design-pipeline" / "02-product-design-spec.json").exists()
    assert (tmp_path / ".friday" / "design-pipeline" / "04-design-tokens.css").exists()
    assert (tmp_path / ".friday" / "design-pipeline" / "11-final-design-proof.md").exists()


def test_design_pipeline_live_run_applies_selected_handoff(monkeypatch, tmp_path):
    def fake_search(query, **kwargs):
        return {
            "ok": True,
            "query": query,
            "results": [{"title": "Reference", "url": "https://example.com", "snippet": "useful design reference"}],
            "providers_succeeded": ["test"],
        }

    def fake_critique(request, **kwargs):
        return {
            "ok": True,
            "status": "selected",
            "provider": "design_critique_loop",
            "summary": "Selected strong developer-tools landing direction.",
            "frontend_handoff_allowed": True,
            "variant_count": kwargs.get("variant_count") or 3,
            "selected_variant": {"id": "terminal", "label": "Terminal proof", "score": 91, "accepted": True},
            "variants": [{"id": "terminal", "label": "Terminal proof", "score": 91, "accepted": True}],
            "rejected_variants": [],
            "artifacts": [str(tmp_path / ".friday" / "design" / "frontend-handoff.json")],
        }

    monkeypatch.setattr(design_pipeline.search_broker, "search", fake_search)
    monkeypatch.setattr(design_pipeline.design_providers, "run_design_critique_loop", fake_critique)
    monkeypatch.setattr(
        design_pipeline.design_providers,
        "apply_selected_design_to_nextjs",
        lambda *args, **kwargs: {"ok": True, "status": "applied", "summary": "Applied selected handoff.", "files": [str(tmp_path / "src" / "app" / "page.tsx")], "artifacts": []},
    )

    result = design_pipeline.run(
        "Build a landing page for Nexus Forge, a developer-tools backend platform.",
        root=tmp_path,
        product_name="Nexus Forge",
        stack={"stack": "nextjs", "label": "Next.js web app"},
        dry_run=False,
        apply_to_source=True,
        research_live=True,
        run_browser=False,
    )

    assert result["status"] == "applied"
    assert result["ok"] is True
    assert result["research"]["status"] == "completed"
    assert result["frontend_handoff_allowed"] is True
    assert result["applied_design"]["ok"] is True


def test_product_studio_design_handoff_uses_design_pipeline(monkeypatch, tmp_path):
    captured = {}

    def fake_pipeline(request, **kwargs):
        captured["request"] = request
        captured["kwargs"] = kwargs
        return {
            "ok": True,
            "status": "applied",
            "summary": "Design pipeline applied selected handoff.",
            "frontend_handoff_allowed": True,
            "design_plan": {"product_name": "Nexus Forge"},
            "design_critique": {"status": "selected", "frontend_handoff_allowed": True, "summary": "Selected."},
            "applied_design": {"ok": True, "status": "applied"},
            "design_visual_ready": True,
            "artifacts": [str(tmp_path / ".friday" / "design-pipeline" / "design-pipeline.json")],
        }

    monkeypatch.setattr(product_studio.design_pipeline, "run", fake_pipeline)

    result = product_studio.prepare_design_handoff(
        tmp_path,
        "Build a landing page for Nexus Forge.",
        product_name="Nexus Forge",
        stack={"stack": "nextjs"},
        run_live=True,
        apply_to_source=True,
    )

    assert captured["kwargs"]["dry_run"] is False
    assert captured["kwargs"]["apply_to_source"] is True
    assert captured["kwargs"]["run_browser"] is True
    assert result["ok"] is True
    assert result["status"] == "applied"
    assert result["design_pipeline"]["status"] == "applied"
