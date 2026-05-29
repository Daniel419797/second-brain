from core import audit_log, competitive_benchmark, trust_proof


def test_competitive_benchmark_records_metrics_and_proof(monkeypatch, tmp_path):
    monkeypatch.setattr(competitive_benchmark, "DB_PATH", tmp_path / "benchmark.sqlite3")
    monkeypatch.setattr(trust_proof, "DB_PATH", tmp_path / "proof.sqlite3")
    monkeypatch.setattr(audit_log, "DB_PATH", tmp_path / "audit.sqlite3")
    monkeypatch.setattr(
        competitive_benchmark,
        "_readiness",
        lambda: {
            "connector_runtime": True,
            "approval": True,
            "gateway": True,
            "signature": True,
            "approval_inbox": True,
            "audit": True,
            "desktop_sandbox": True,
            "ci": True,
            "proof": True,
            "company_runtime": True,
            "state_machine": True,
            "memory_governance": True,
            "control_room": True,
            "agency_mode": True,
            "playwright": True,
            "operator_skills": True,
            "skill_library": True,
            "model_router": True,
            "cloud_worker": True,
            "android_companion": True,
            "phone_mesh": True,
            "agency_business_layer": True,
            "evidence_required": True,
        },
    )

    result = competitive_benchmark.run_suite()

    assert result["metrics"]["completion_rate"] == 1.0
    assert result["metrics"]["false_success_claims"] == 0
    assert result["proof_id"] > 0
    assert competitive_benchmark.status()["latest"]["id"] == result["id"]
