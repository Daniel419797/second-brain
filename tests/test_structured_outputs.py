from core import structured_outputs


def test_agent_result_contract_accepts_evidence_and_gaps():
    result = structured_outputs.validate(
        "agent_result",
        {
            "summary": "Built and verified the project.",
            "next_step": "Review preview.",
            "risks": ["Preview deploy is not production."],
            "evidence": [{"kind": "log", "path": "build.log", "summary": "Build passed."}],
            "gaps": [],
            "confidence": 0.8,
            "status": "done",
        },
    )

    assert result["ok"] is True
    assert result["output"]["status"] == "done"


def test_agent_result_contract_rejects_empty_summary():
    result = structured_outputs.validate("agent_result", {"summary": "", "status": "done"})

    assert result["ok"] is False
    assert result["errors"]


def test_coerce_agent_result_adds_artifact_evidence():
    result = structured_outputs.coerce_agent_result(
        {"summary": "Scaffolded.", "artifacts": ["proof.md"], "failed_required": ["No build log"], "status": "blocked"}
    )

    assert result["status"] == "blocked"
    assert result["evidence"][0]["path"] == "proof.md"
    assert result["gaps"] == ["No build log"]
