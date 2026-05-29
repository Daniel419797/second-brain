from core import dynamic_interface


def sample_payload():
    return {
        "timestamp": "2026-05-29T06:30:00+01:00",
        "status": {"running": True, "workers": 4, "mode": "agent mode"},
        "tasks": [
            {"id": 1, "title": "Wire the frontend", "status": "active"},
            {"id": 2, "title": "Clean copy", "status": "pending"},
        ],
        "missions": [{"id": 7, "goal": "Build the hackathon product", "status": "active"}],
        "approvalSummary": {"count": 2, "items": []},
        "pcAwareness": {"active_window": "second-brain - Visual Studio Code", "stats": {"running_apps": 8}},
        "notifications": {"unread_count": 1, "items": [{"title": "Build", "message": "Build finished"}]},
        "gateway": {"enabled_count": 5, "pending_high_risk": 1},
        "projectMemory": {
            "projects": [
                {
                    "name": "second-brain",
                    "architecture": {"summary": "Local AI command center."},
                    "common_bugs": ["Fix memory leak in websocket connections"],
                    "past_fixes": ["Websocket retry loop tuned"],
                    "commands": ["npm run build", "pytest"],
                    "env_names": ["NEXT_PUBLIC_API_URL"],
                    "metadata": {"has_package_json": True},
                }
            ]
        },
        "contextFusion": {"observations": [{"summary": "The operator screen is open and ready."}]},
    }


def test_snapshot_includes_dynamic_view_contracts():
    payload = dynamic_interface.snapshot(sample_payload())

    assert payload["brand"]["name"] == "Friday"
    assert payload["chrome"]["title"] != "Friday Command Center"
    assert payload["facts"]["approval_count"] == 2
    assert "dashboard" in payload["views"]
    assert "operators" in payload["views"]
    assert payload["views"]["dashboard"]["primaryAction"]["href"] == "/approvals"


def test_operator_copy_targets_active_app_and_ui_endpoints():
    copy = dynamic_interface.view_copy("operators", sample_payload())

    assert "Vscode" in copy["title"] or "Visual" in copy["subtitle"]
    assert any(action.get("endpoint") == "/ui-control/context" for action in copy["actions"])
    assert copy["empty"]["sessions"]


def test_unknown_view_uses_dashboard_contract_without_generic_execute_copy():
    copy = dynamic_interface.view_copy("some-new-surface", sample_payload())

    assert copy["view"] == "dashboard"
    assert copy["labels"]["execute"] != "Execute"
    assert "Friday" in copy["title"] or "decision" in copy["title"].lower()


def test_project_insight_is_backend_authored_not_frontend_template():
    copy = dynamic_interface.view_copy("projects", sample_payload())

    assert copy["insight"]["title"] == "Friday's Project Read"
    assert "Fix memory leak in websocket connections" in copy["insight"]["summary"]
    assert "appears connected to" not in copy["insight"]["summary"]
    assert copy["actions"][1]["id"] == "review-project-insight"
