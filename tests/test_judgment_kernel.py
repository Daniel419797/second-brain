from pathlib import Path

from core import (
    debugging_judgment,
    failure_autopsy,
    friday_memory,
    intent_judgment,
    judgment_kernel,
    personal_taste_engine,
    readiness_claim_guard,
    shallow_output_detector,
    style_profiles,
)


def _isolate(monkeypatch, tmp_path):
    monkeypatch.setattr(friday_memory, "DB_PATH", tmp_path / "friday_memory.sqlite3")
    monkeypatch.setattr(personal_taste_engine, "DB_PATH", tmp_path / "taste.sqlite3")
    monkeypatch.setattr(failure_autopsy, "DB_PATH", tmp_path / "failure_autopsy.sqlite3")
    monkeypatch.setattr(style_profiles, "DB_PATH", tmp_path / "style_profiles.sqlite3")
    monkeypatch.setattr(failure_autopsy.skill_improvement, "record_failure", lambda *args, **kwargs: None)


def test_testing_friday_intent_does_not_bypass_agent(tmp_path):
    result = intent_judgment.judge("I am testing Friday. Do not build the app yourself.", root=tmp_path)

    assert result["user_intent"] == "test_friday_do_not_bypass"
    assert result["do_not_bypass_friday"] is True
    assert result["recommended_action"] == "route_through_friday_and_review_agent_output"
    assert any("Do not complete" in action for action in result["blocked_actions"])


def test_shallow_scaffold_output_is_rejected(tmp_path):
    output = {
        "summary": "Created a runnable Next.js app. Install dependencies and run the README command.",
        "project_root": str(tmp_path / "missing"),
    }

    result = shallow_output_detector.detect(output)

    assert result["shallow"] is True
    assert any("Project root does not exist" in reason for reason in result["reasons"])
    assert any("final proof" in reason.lower() for reason in result["reasons"])


def test_flat_nextjs_blob_fails_nexus_forge_style(tmp_path):
    root = tmp_path / "web"
    (root / "src/app").mkdir(parents=True)
    (root / "src/components").mkdir(parents=True)
    (root / "next.config.mjs").write_text("export default {};\n", encoding="utf-8")
    (root / "src/app/page.tsx").write_text("'use client';\nimport { useState } from 'react';\nexport default function Page(){ const [x]=useState(1); return <div>{x}</div>; }\n", encoding="utf-8")
    (root / "src/components/WorkspaceConsole.tsx").write_text("export function WorkspaceConsole(){ return null; }\n", encoding="utf-8")

    result = style_profiles.evaluate_project(root, "nexus_forge_nextjs")

    assert result["ok"] is False
    assert any("Flat blob" in gap or "forbidden" in gap.lower() for gap in result["gaps"])


def test_claims_are_blocked_without_evidence():
    tested = readiness_claim_guard.guard_claims(["tested"], {"tested": False})
    market = readiness_claim_guard.guard_claims(
        ["market-ready"],
        {
            "market_ready": True,
            "approvals": {"deploy_preview": {"approved": True}},
        },
    )

    assert tested["ok"] is False
    assert any("tested requires" in item for item in tested["blocked"])
    assert market["ok"] is False
    assert any("requires approvals" in item for item in market["blocked"])


def test_debugging_judgment_generates_hypotheses(tmp_path):
    result = debugging_judgment.judge_failure("npm build failed: Module not found: Can't resolve '@/components/Widget'", root=tmp_path)

    assert "missing dependency" in result["likely_causes"]
    assert result["next_probe"] == "run typecheck"
    assert result["fix_scope"]


def test_judgment_kernel_blocks_shallow_done_claim(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    result = judgment_kernel.review(
        text="Done, tested, and verified.",
        result={"summary": "Done, tested, and verified.", "project_root": str(tmp_path / "missing")},
        root=tmp_path / "missing",
        claims=["done", "tested", "verified"],
        remember=True,
    )

    assert result["ok"] is False
    assert result["gaps"]
    assert friday_memory.status()["counts"].get("judgment_gap", 0) >= 1


def test_failure_autopsy_writes_memory(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)

    result = judgment_kernel.debug_failure("tsc failed with Type error in src/components/App.tsx", root=tmp_path, remember=True)

    assert result["hypothesis"]["likely_causes"]
    assert result["memory"]["memory_type"] == "failure_pattern"
    assert friday_memory.status()["counts"]["failure_pattern"] == 1


def test_friday_studio_judgment_buttons_call_real_endpoints():
    source = Path("apps/web/src/components/views/FridayStudioView.jsx").read_text(encoding="utf-8")

    for endpoint in ["/judgment/review", "/judgment/claims", "/judgment/self-review", "/judgment/debug", "/judgment/taste"]:
        assert endpoint in source
