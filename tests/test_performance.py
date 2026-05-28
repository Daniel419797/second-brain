from core import performance


def test_api_core_benchmark_reports_fast_checks(monkeypatch):
    monkeypatch.setattr(performance.background_agents, "worker_status", lambda: {"running": False})
    monkeypatch.setattr(performance.task_queue, "list_tasks", lambda limit=20: [])
    monkeypatch.setattr(performance.task_queue, "counts", lambda: {"total": 0})
    monkeypatch.setattr(performance, "config_value", lambda key, default=None: 500 if key == "api_response_target_ms" else default)

    result = performance.benchmark_api_core()

    assert result["ok"] is True
    assert {check["name"] for check in result["checks"]} == {"worker_status", "task_list", "task_counts"}
