"""Central Friday run and proof-artifact routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status


def register_routes(app: Any, ctx: Any) -> None:
    router = APIRouter()

    @router.get("/friday-runs/status")
    def friday_runs_status(limit: int = 12, _user: str = Depends(ctx.require_user)) -> dict[str, Any]:
        return ctx.friday_run_engine.status(limit=limit)

    @router.get("/friday-runs/{run_id}")
    def friday_run(run_id: int, _user: str = Depends(ctx.require_user)) -> dict[str, Any]:
        run = ctx.friday_run_engine.get_run(run_id)
        if not run:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Friday run not found.")
        return run

    @router.get("/friday-runs/{run_id}/artifact")
    def friday_run_artifact(run_id: int, path: str, _user: str = Depends(ctx.require_user)) -> dict[str, Any]:
        run = ctx.friday_run_engine.get_run(run_id)
        if not run:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Friday run not found.")
        allowed = ctx.artifact_access.collect_manifest_paths(run)
        try:
            return ctx.artifact_access.read_artifact(path, allowed_paths=allowed, require_manifest_match=True)
        except FileNotFoundError:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Artifact not found.") from None
        except OverflowError:
            raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Artifact is too large for inline viewing.") from None
        except ctx.artifact_access.ArtifactAccessError as exc:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from None

    app.include_router(router)
