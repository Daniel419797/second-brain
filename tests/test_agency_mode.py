from types import SimpleNamespace
from pathlib import Path

from core import agency_mode
from tools import power_center


def _isolate(monkeypatch, tmp_path):
    monkeypatch.setattr(agency_mode, "DB_PATH", tmp_path / "agency_mode.sqlite3")

    def fake_config(key, default=None):
        values = {
            "agency_mode_enabled": True,
            "agency_workspace_dir": str(tmp_path / "Friday Agency"),
            "agency_default_currency": "USD",
            "agency_service_keywords": "website,automation,ai,dashboard,booking,crm",
            "agency_outreach_daily_limit": 20,
            "agency_project_run_tests": False,
            "agency_deploy_enabled": True,
            "agency_deploy_timeout_seconds": 60,
        }
        return values.get(key, default)

    monkeypatch.setattr(agency_mode, "config_value", fake_config)
    agency_mode.init_db()


def test_agency_leads_scoring_outreach_approval_and_send(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    monkeypatch.setattr(
        agency_mode.search_broker,
        "search",
        lambda query, limit=5: {
            "results": [
                {"title": "Ada Clinic needs booking automation", "url": "https://ada-clinic.test", "snippet": "Looking to build a booking dashboard.", "provider": "test", "rank": 1}
            ]
        },
    )
    monkeypatch.setattr(agency_mode, "_send_permission_blocked", lambda item: "")
    monkeypatch.setattr(agency_mode, "_send_email", lambda item: "Email sent to ada@example.test.")

    search = agency_mode.search_leads(niche="clinics", location="Lagos")
    lead = agency_mode.add_lead("Ada Clinic", email="ada@example.test", website="https://ada-clinic.test", need="Need booking automation and a dashboard.")
    scored = agency_mode.score_lead(int(lead["id"]))
    draft = agency_mode.draft_outreach(int(lead["id"]), service_offer="booking dashboard")
    skipped = agency_mode.send_outreach(int(draft["id"]))
    approved = agency_mode.approve_outreach([int(draft["id"])], note="Looks good.")
    sent = agency_mode.send_outreach([int(draft["id"])])
    contacted = agency_mode.get_lead(int(lead["id"]))

    assert search["leads"][0]["fit_score"] > 50
    assert scored["fit_score"] > 70
    assert draft["status"] == "draft"
    assert skipped["failed"][0]["reason"] == "not approved"
    assert approved["approved"] == [draft["id"]]
    assert sent["sent"][0]["id"] == draft["id"]
    assert contacted["status"] == "contacted"


def test_agency_documents_project_workflow_invoices_and_profit(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    monkeypatch.setattr(agency_mode.task_queue, "create_task", lambda *args, **kwargs: 42)
    monkeypatch.setattr(agency_mode.mission_control, "create_mission", lambda *args, **kwargs: {"id": 7, "status": "running"})
    monkeypatch.setattr(agency_mode.autonomous_qa_lab, "run_qa", lambda root, run_tests=False: {"status": "passed"})
    monkeypatch.setattr(agency_mode.autonomous_release_engine, "prepare", lambda root, run_tests=False: {"status": "ready"})
    monkeypatch.setattr(agency_mode.git_integration, "status", lambda root: {"ok": True, "summary": "Git status ready."})
    monkeypatch.setattr(agency_mode.git_integration, "add", lambda root, paths=".": {"ok": True})
    monkeypatch.setattr(agency_mode.git_integration, "commit", lambda root, message: {"ok": True, "message": message})
    monkeypatch.setattr(agency_mode.git_integration, "push", lambda root: {"ok": True})
    monkeypatch.setattr(agency_mode.command_runner, "run", lambda command, cwd=None, timeout=60: SimpleNamespace(returncode=0, stdout="deployed", stderr=""))
    monkeypatch.setattr(agency_mode.deployment_brain, "inspect", lambda target, root="", create_proof=True: {"status": "ok", "summary": "Deployment checked."})

    lead = agency_mode.add_lead("Demo Studio", email="client@example.test", need="Build an ecommerce website.")
    proposal = agency_mode.draft_proposal(int(lead["id"]), scope="Website build", price=500)
    contract = agency_mode.draft_contract(int(lead["id"]), scope="Website build", price=500)
    plan = agency_mode.draft_project_plan(int(lead["id"]), scope="Website build")
    project = agency_mode.start_client_project(int(lead["id"]), budget=500)
    workflow = agency_mode.run_project_workflow(int(project["id"]), commit=True, push=True, deploy=True, deploy_command="npm run deploy", target_url="https://example.test")
    invoice = agency_mode.create_invoice(int(project["id"]), amount=500)
    paid = agency_mode.mark_invoice_paid(int(invoice["id"]))
    expense = agency_mode.record_ledger("api_usage", 20, category="llm", description="API usage")
    profit = agency_mode.profit_summary()
    recommendation = agency_mode.recommend_payment("NVIDIA", 10, reason="API credits")
    approved = agency_mode.approve_payment(int(recommendation["id"]))
    triggered = agency_mode.trigger_approved_payment(int(recommendation["id"]))
    pipeline = agency_mode.pipeline_summary()
    budget = agency_mode.api_budget_status()
    public = agency_mode.generate_business_layer(business_name="Demo Agency", owner_email="owner@example.test")

    assert Path(proposal["path"]).exists()
    assert Path(contract["path"]).exists()
    assert Path(plan["path"]).exists()
    assert Path(project["root"]).name == "demo-studio-project"
    assert (Path(project["root"]) / "README.md").exists()
    assert workflow["qa"]["status"] == "passed"
    assert workflow["deployment"]["status"] == "deployed"
    assert workflow["deployment"]["deployment_check"]["status"] == "ok"
    assert invoice["path"].endswith(".md")
    assert paid["status"] == "paid"
    assert expense["kind"] == "api_usage"
    assert profit["revenue"] == 500
    assert profit["expenses"] == 20
    assert profit["profit"] == 480
    assert approved["kind"] == "payment_approved"
    assert triggered["ok"] is True
    assert pipeline["lead_stages"]["new"] >= 1
    assert budget["currency"] == "USD"
    assert Path(public["root"]).exists()
    assert (Path(public["root"]) / "index.html").exists()
    assert (Path(public["root"]) / "client-portal.html").exists()


def test_power_center_agency_status_action(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    monkeypatch.setattr(power_center, "_permission_reply", lambda inputs: "")

    reply = power_center.execute({"action": "agency_status"})
    pipeline = power_center.execute({"action": "agency_pipeline"})

    assert "Agency has" in reply
    assert "Pipeline" in pipeline
