"""Operational, readiness, backup, and cloud routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends
from pydantic import BaseModel, Field


class BackupFileRequest(BaseModel):
    path: str = Field(default="", max_length=1000)
    label: str = Field(default="", max_length=200)


class RestoreBackupRequest(BaseModel):
    confirm: bool = False


class CloudWorkerSubmitRequest(BaseModel):
    job_type: str = Field(default="research", max_length=80)
    title: str = Field(min_length=1, max_length=300)
    payload: dict[str, Any] = Field(default_factory=dict)
    prefer_cloud: bool = True


def register_routes(app: Any, ctx: Any) -> None:
    router = APIRouter()

    @router.get("/providers/readiness")
    def providers_readiness(probe: bool = False, _user: str = Depends(ctx.require_user)) -> dict[str, Any]:
        from core import provider_readiness

        return provider_readiness.status(probe=probe)

    @router.get("/production/readiness")
    def production_readiness(_user: str = Depends(ctx.require_user)) -> dict[str, Any]:
        from core import provider_readiness

        return provider_readiness.production_readiness()

    @router.get("/github/status")
    def github_status(root: str = "", _user: str = Depends(ctx.require_user)) -> dict[str, Any]:
        from core import provider_readiness

        return provider_readiness.github_status(root=root)

    @router.post("/backup/config")
    def backup_config(request: BackupFileRequest | None = Body(default=None), _user: str = Depends(ctx.require_user)) -> dict[str, Any]:
        return ctx.backup_recovery.snapshot_config(label=(request.label if request else "config snapshot"))

    @router.post("/backup/file")
    def backup_file(request: BackupFileRequest, _user: str = Depends(ctx.require_user)) -> dict[str, Any]:
        return ctx.backup_recovery.backup_file(request.path, label=request.label)

    @router.get("/backup/list")
    def backup_list(limit: int = 50, _user: str = Depends(ctx.require_user)) -> list[dict[str, Any]]:
        return ctx.backup_recovery.list_backups(limit=limit)

    @router.post("/backup/{backup_id}/restore")
    def backup_restore(backup_id: int, request: RestoreBackupRequest, _user: str = Depends(ctx.require_user)) -> dict[str, Any]:
        return ctx.backup_recovery.restore_backup(backup_id, confirm=request.confirm)

    @router.post("/backup/delete-guard")
    def backup_delete_guard(request: BackupFileRequest, _user: str = Depends(ctx.require_user)) -> dict[str, Any]:
        return ctx.backup_recovery.risky_delete_guard(request.path)

    @router.get("/cloud-worker/status")
    def cloud_worker_status(_user: str = Depends(ctx.require_user)) -> dict[str, Any]:
        return ctx.cloud_worker_mode.status()

    @router.get("/cloud-worker/jobs")
    def cloud_worker_jobs(limit: int = 20, status: str = "", _user: str = Depends(ctx.require_user)) -> list[dict[str, Any]]:
        return ctx.cloud_worker_mode.list_jobs(limit=limit, status=status)

    @router.post("/cloud-worker/submit")
    def cloud_worker_submit(request: CloudWorkerSubmitRequest, _user: str = Depends(ctx.require_user)) -> dict[str, Any]:
        return ctx.cloud_worker_mode.submit(request.job_type, request.title, request.payload, prefer_cloud=request.prefer_cloud)

    @router.get("/metrics/api-benchmark")
    def api_benchmark(_user: str = Depends(ctx.require_user)) -> dict[str, Any]:
        return ctx.performance.benchmark_api_core()

    @router.post("/sync/run")
    def run_sync(_user: str = Depends(ctx.require_user)) -> dict[str, Any]:
        return ctx.cloud_sync.sync_once()

    app.include_router(router)
