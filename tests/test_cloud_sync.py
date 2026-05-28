from core import audit_log, cloud_sync, task_queue


def test_cloud_sync_disabled_without_database_url(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)

    result = cloud_sync.sync_once()

    assert result["enabled"] is False


def test_cloud_sync_reads_local_rows_when_placeholder_url(monkeypatch, tmp_path):
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:password@host:5432/friday")
    monkeypatch.setattr(task_queue, "DB_PATH", tmp_path / "tasks.sqlite3")
    monkeypatch.setattr(audit_log, "DB_PATH", tmp_path / "audit.sqlite3")
    task_queue.create_task("Sync me")
    audit_log.record(category="pc_control", action="open_app", target="chrome")

    result = cloud_sync.sync_once()

    assert result["enabled"] is False
