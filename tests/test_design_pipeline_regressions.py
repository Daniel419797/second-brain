import json

from core import design_asset_manager, design_pipeline, design_providers, design_visual_reviewer, dribbble_scraper


def test_browser_variant_review_rejects_hero_only_low_resolution_media(monkeypatch, tmp_path):
    monkeypatch.setattr(design_visual_reviewer.browser_playwright, "available", lambda: {"available": True, "mode": "test"})

    def fake_audit(*args, **kwargs):
        return {
            "ok": True,
            "screenshots": [str(tmp_path / "shot.png")],
            "findings": [],
            "contexts": [
                {
                    "viewport": {"label": "desktop", "width": 1440, "height": 900},
                    "visual": {
                        "images": [
                            {"naturalWidth": 320, "rect": {"visible": True, "width": 900}},
                        ]
                    },
                }
            ],
        }

    monkeypatch.setattr(design_visual_reviewer.browser_playwright, "visual_audit", fake_audit)

    result = design_visual_reviewer.review_variants(
        [
            {
                "id": "hero-only",
                "html": "<main><section><h1>Pretty hero</h1><p>Thin copy.</p><img src='hero.png' /></section><footer>Done</footer></main>",
            }
        ],
        design_root=tmp_path / ".friday" / "design",
        request="Build a landing page for a premium product.",
        required=True,
    )

    review = result["variants"][0]["browser_visual_review"]
    assert review["passed"] is False
    assert any("too shallow" in item for item in review["findings"])
    assert any("low-resolution" in item for item in review["findings"])


def test_visual_review_failure_blocks_provider_handoff(monkeypatch, tmp_path):
    def fake_review(variants, **kwargs):
        return {
            "ok": False,
            "status": "failed",
            "variants": [
                {
                    **variants[0],
                    "browser_visual_review": {
                        "passed": False,
                        "findings": ["desktop: first viewport appears visually empty or uninformative."],
                    },
                }
            ],
            "artifacts": [str(tmp_path / "visual-variant-review.json")],
        }

    monkeypatch.setattr(design_providers.design_visual_reviewer, "review_variants", fake_review)
    report = design_providers.critique_design_variants(
        [
            {
                "id": "empty",
                "html": "<main><header><nav>Home Pricing</nav></header><section><h1>Product</h1><p>Specific useful product copy with an action.</p><a href='/start'>Start</a></section><section><h2>Proof</h2><figure>Proof object</figure></section><section><h2>Pricing</h2><p>Clear pricing.</p></section></main>",
            }
        ],
        {"request": "Build a landing page for Product.", "product_name": "Product", "root": str(tmp_path), "design_root": str(tmp_path / ".friday" / "design")},
        visual_review=True,
    )

    assert report["frontend_handoff_allowed"] is False
    assert "Browser screenshot review failed" in " ".join(report["variants"][0]["rejection_reasons"])
    assert report["browser_variant_review"]["status"] == "failed"
    assert str(tmp_path / "visual-variant-review.json") in report["artifacts"]


def test_partial_stitch_variant_set_cannot_be_handed_off(tmp_path):
    html = """
    <main><header><nav>Home Product Pricing Contact</nav></header>
    <section><h1>PulseGrid gives clinics real-time capacity control.</h1><p>Track staffing, lab queues, patient waits, escalation risk, and action ownership from one operating room.</p><a href='/demo'>Book demo</a></section>
    <section><h2>Capacity proof</h2><p>Provider utilization, urgent messages, room availability, and diversion risk are visible before the morning huddle.</p></section>
    <section><h2>Pricing</h2><p>Simple per-location plans with onboarding, audit logs, and support.</p></section></main>
    """
    report = design_providers.critique_design_variants(
        [{"id": "base", "label": "Base", "html": html}],
        {
            "request": "Build a healthcare dashboard landing page for PulseGrid.",
            "product_name": "PulseGrid",
            "root": str(tmp_path),
            "design_root": str(tmp_path / ".friday" / "design"),
            "provider_generation_status": "partial_provider_result",
            "expected_variant_count": 3,
            "single_variant_allowed": False,
        },
    )

    assert report["frontend_handoff_allowed"] is False
    assert "1/3 requested variant" in report["summary"]
    assert any("partial provider output" in reason for reason in report["variants"][0]["rejection_reasons"])


def test_design_pipeline_research_uses_director_classification(tmp_path):
    result = design_pipeline.run(
        "Build a landing page for a luxury watch concierge.",
        root=tmp_path,
        product_name="CrownVault",
        stack={"stack": "nextjs"},
        dry_run=True,
    )

    assert result["research"]["category"]["industry"] == "luxury"
    assert result["research"]["category"]["surface"] == "marketing_website"


def test_browser_verification_disabled_is_not_visual_ready(tmp_path):
    result = design_pipeline._browser_verification(
        tmp_path,
        request="Build a landing page.",
        stack={"stack": "nextjs"},
        generation={},
        enabled=False,
    )

    assert result["design_visual_status"] == "not_applicable"
    assert result["design_visual_ready"] is False
    assert result["browser_gate_ready"] is False
    assert result["technical_ready"] is False


def test_stitch_timeout_with_base_checkpoint_is_partial_not_handoff_ready(monkeypatch, tmp_path):
    monkeypatch.setattr(design_providers, "ROOT_DIR", tmp_path)
    monkeypatch.setattr(design_providers, "config_value", lambda key, default=None: {"design_stitch_timeout_seconds": 1}.get(key, default))
    killed = {}
    payload = {
        "ok": True,
        "status": "base_generated",
        "provider": "stitch",
        "projectId": "project-1",
        "screenId": "screen-1",
        "variants": [{"id": "screen-1", "htmlUrl": "https://example.com/screen.html"}],
    }

    class Process:
        returncode = None
        args = ["node"]
        pid = 789

        def communicate(self, timeout=None):
            if timeout is not None:
                raise design_providers.subprocess.TimeoutExpired(self.args, timeout)
            return (json.dumps(payload) + "\n", "")

    monkeypatch.setattr(design_providers.subprocess, "Popen", lambda *args, **kwargs: Process())
    monkeypatch.setattr(design_providers.command_runner, "terminate_process_tree", lambda pid: killed.setdefault("pid", pid))

    result = design_providers._run_stitch_sdk({"root": str(tmp_path), "stitch_prompt": "Design", "product_name": "Demo"}, variant_count=3)

    assert killed["pid"] == 789
    assert result["ok"] is False
    assert result["status"] == "partial_provider_result"
    assert "partial evidence" in result["summary"]


def test_remote_asset_manager_blocks_non_https_and_private_hosts(tmp_path):
    http_result = design_asset_manager.download_text("http://example.com/file.html")
    local_result = design_asset_manager.download_binary("https://localhost/image.png", tmp_path / "image.png")

    assert http_result["ok"] is False
    assert http_result["reason"] == "only_https_urls_allowed"
    assert local_result["ok"] is False
    assert local_result["reason"] == "local_hosts_blocked"


def test_remote_asset_manager_rejects_undecodable_image(monkeypatch, tmp_path):
    monkeypatch.setattr(
        design_asset_manager,
        "_download",
        lambda *args, **kwargs: {
            "ok": True,
            "url": "https://cdn.example/bad.png",
            "content_type": "image/png",
            "bytes": 12,
            "content_bytes": b"not an image",
        },
    )

    result = design_asset_manager.download_binary("https://cdn.example/bad.png", tmp_path / "bad.png")

    assert result["ok"] is False
    assert result["reason"] == "image_decode_failed"
    assert not (tmp_path / "bad.png").exists()


def test_dribbble_reference_collector_writes_manifest(monkeypatch, tmp_path):
    monkeypatch.setattr(
        dribbble_scraper.search_broker,
        "search",
        lambda *args, **kwargs: {
            "ok": True,
            "results": [{"title": "Luxury audio landing page", "url": "https://dribbble.com/shots/123-demo", "snippet": "Dark editorial product UI"}],
        },
    )
    monkeypatch.setattr(
        dribbble_scraper.design_asset_manager,
        "download_text",
        lambda *args, **kwargs: {
            "ok": True,
            "text": "<html><head><meta property='og:title' content='Nocturne Audio'><meta property='og:description' content='Cinematic product-led dark editorial UI'><meta property='og:image' content='https://cdn.example/image.png'></head></html>",
        },
    )

    result = dribbble_scraper.collect("luxury audio landing page", root=tmp_path, limit=2)

    assert result["ok"] is True
    assert result["references"][0]["title"] == "Nocturne Audio"
    assert (tmp_path / ".friday" / "design" / "research" / "dribbble-references.json").exists()
