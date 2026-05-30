import json

from core import codebase_standards, product_studio_gates


def test_product_studio_gates_execute_real_project_checks(tmp_path, monkeypatch):
    monkeypatch.setattr(product_studio_gates.trust_proof, "DB_PATH", tmp_path / "proof.sqlite3")
    monkeypatch.setattr(codebase_standards, "DB_PATH", tmp_path / "standards.sqlite3")
    package = {
        "name": "gate-smoke",
        "private": True,
        "version": "0.1.0",
        "scripts": {
            "test": "node -e \"console.log('test gate passed')\"",
            "build": "node -e \"console.log('build gate passed')\"",
        },
    }
    (tmp_path / "package.json").write_text(json.dumps(package), encoding="utf-8")

    result = product_studio_gates.execute_gates(
        tmp_path,
        stack={"kind": "web_app", "stack": "nextjs"},
        install=True,
        tests=True,
        audits=True,
        browser=False,
        preview=False,
        create_proof=False,
    )

    statuses = {gate["id"]: gate["status"] for gate in result["gates"]}
    assert result["attempted"] is True
    assert statuses["dependencies_install"] == "passed"
    assert statuses["dependency_audit"] == "passed"
    assert any(status == "passed" for gate_id, status in statuses.items() if gate_id.startswith("test_"))
    assert (tmp_path / ".friday" / "product-studio" / "gates" / "gate-results.json").exists()
