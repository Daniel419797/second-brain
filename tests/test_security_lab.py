from core import autonomy_control, permissions, security_lab


def isolate_security_lab(monkeypatch, tmp_path):
    monkeypatch.setattr(security_lab, "DB_PATH", tmp_path / "security_lab.sqlite3")
    monkeypatch.setattr(security_lab, "ARTIFACT_ROOT", tmp_path / "security_lab_artifacts")
    monkeypatch.setattr(permissions, "DB_PATH", tmp_path / "permissions.sqlite3")
    monkeypatch.setattr(autonomy_control, "DB_PATH", tmp_path / "autonomy_control.sqlite3")
    monkeypatch.delenv("FRIDAY_AUTHORITY_MODE", raising=False)
    monkeypatch.delenv("FRIDAY_AUTONOMY_MODE", raising=False)
    permissions.init_db()

    def fake_config(key, default=None):
        values = {
            "autonomy_control_enabled": True,
            "autonomy_mode": "supervised",
            "autonomy_trusted_roots": str(tmp_path),
            "autonomy_hard_stop_keys": "power_center.security_lab",
        }
        return values.get(key, default)

    monkeypatch.setattr(autonomy_control, "config_value", fake_config)


def test_security_lab_status_lists_tools(monkeypatch, tmp_path):
    isolate_security_lab(monkeypatch, tmp_path)

    status = security_lab.status()

    assert status["tool_count"] >= 10
    assert any(tool["id"] == "nmap_discovery" for tool in status["tools"])
    assert any(profile["id"] == "web_owasp" for profile in status["profiles"])


def test_security_lab_code_scan_writes_report_in_full_access(monkeypatch, tmp_path):
    isolate_security_lab(monkeypatch, tmp_path)
    project = tmp_path / "app"
    project.mkdir()
    (project / "app.py").write_text("API_KEY='abc123'\n", encoding="utf-8")
    autonomy_control.set_authority_mode("full_access", actor="test")

    run = security_lab.run_scan(root=project, tools=["secret_scan", "threat_model"], profile="code_audit")

    assert run["status"] == "done"
    assert run["result_count"] == 2
    assert run["report_path"]
    assert "Security Lab completed" in run["summary"]


def test_security_lab_auth_review_and_remediation(monkeypatch, tmp_path):
    isolate_security_lab(monkeypatch, tmp_path)
    project = tmp_path / "web"
    project.mkdir()
    (project / "auth.ts").write_text("export function login(){ return session.cookie }\n", encoding="utf-8")
    autonomy_control.set_authority_mode("full_access", actor="test")

    run = security_lab.run_scan(root=project, tools=["auth_session_review"])
    remediation = security_lab.remediate(run_id=run["id"])

    assert run["status"] == "done"
    assert remediation["status"] == "done"
    assert remediation["path"].endswith("security-remediation-plan.md")


def test_security_lab_blocks_public_target_without_verified_scope(monkeypatch, tmp_path):
    isolate_security_lab(monkeypatch, tmp_path)
    autonomy_control.set_authority_mode("full_access", actor="test")

    result = security_lab.run_scan(root=tmp_path, target="example.com", tools=["nmap_discovery"])

    assert result["status"] == "blocked_for_scope"
    assert "nmap_discovery" in result["blocked_tools"]


def test_security_lab_sandbox_mode_blocks_when_backend_unconfigured(monkeypatch, tmp_path):
    isolate_security_lab(monkeypatch, tmp_path)
    autonomy_control.set_authority_mode("full_access", actor="test")

    result = security_lab.run_scan(root=tmp_path, tools=["secret_scan"], execution_mode="sandbox")

    assert result["status"] == "blocked_sandbox_unavailable"


def test_security_lab_approval_gated_mode_creates_approval(monkeypatch, tmp_path):
    isolate_security_lab(monkeypatch, tmp_path)

    result = security_lab.run_scan(root=tmp_path, tools=["secret_scan"])

    assert result["status"] == "blocked_for_approval"
    assert result["approval"]["kind"] == "security_lab"
