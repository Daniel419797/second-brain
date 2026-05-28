"""Media, search, and generated asset routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field


class WebSearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=1000)
    limit: int = Field(default=5, ge=1, le=20)
    providers: str = Field(default="", max_length=200)
    use_cache: bool = True
    mode: str = Field(default="", max_length=40)


class ImageGenerateRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=2000)
    negative_prompt: str = Field(default="", max_length=1000)
    provider: str = Field(default="auto", max_length=80)
    width: int = Field(default=768, ge=128, le=2048)
    height: int = Field(default=768, ge=128, le=2048)
    steps: int = Field(default=24, ge=1, le=100)


class Model3DRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=4000)
    name: str = Field(default="", max_length=200)
    shape: str = Field(default="", max_length=80)
    formats: list[str] | str | None = None
    quality: str = Field(default="", max_length=80)
    backend: str = Field(default="", max_length=80)


class TextTo3DRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=4000)
    name: str = Field(default="", max_length=200)
    shape: str = Field(default="", max_length=80)
    formats: list[str] | str | None = None
    provider: str = Field(default="", max_length=80)


def register_routes(app: Any, ctx: Any) -> None:
    router = APIRouter()

    @router.get("/search/status")
    def web_search_status(_user: str = Depends(ctx.require_user)) -> dict[str, Any]:
        return ctx.search_broker.status()

    @router.post("/search/query")
    def web_search_query(request: WebSearchRequest, _user: str = Depends(ctx.require_user)) -> dict[str, Any]:
        return ctx.search_broker.search(
            request.query,
            limit=request.limit,
            providers=request.providers or None,
            use_cache=request.use_cache,
            mode=request.mode or None,
        )

    @router.get("/images/status")
    def images_status(_user: str = Depends(ctx.require_user)) -> dict[str, Any]:
        return ctx.image_generation.status()

    @router.get("/images")
    def images_list(limit: int = 20, _user: str = Depends(ctx.require_user)) -> list[dict[str, Any]]:
        return ctx.image_generation.list_images(limit=max(1, min(int(limit), 100)))

    @router.post("/images/generate")
    def images_generate(request: ImageGenerateRequest, _user: str = Depends(ctx.require_user)) -> dict[str, Any]:
        return ctx.image_generation.generate_image(
            request.prompt,
            negative_prompt=request.negative_prompt,
            provider=request.provider,
            width=request.width,
            height=request.height,
            steps=request.steps,
        )

    @router.get("/images/{filename}")
    def generated_image(
        filename: str,
        token: str = "",
        authorization: str = Header(default=""),
    ) -> FileResponse:
        ctx._require_user_from_header_or_token(authorization, token)
        try:
            path = ctx.image_generation.image_path(filename)
        except ValueError:
            raise HTTPException(status_code=404, detail="Generated image not found.")
        if not path.exists() or not path.is_file():
            raise HTTPException(status_code=404, detail="Generated image not found.")
        return FileResponse(str(path))

    @router.get("/models/3d/status")
    def model_3d_status(_user: str = Depends(ctx.require_user)) -> dict[str, Any]:
        from core import provider_readiness

        readiness = provider_readiness.status(probe=False)
        return readiness["providers"]["text_to_3d"] | {
            "model_3d": readiness["providers"]["model_3d"],
            "summary": "3D model provider status ready.",
        }

    @router.post("/models/3d/generate")
    def model_3d_generate(request: Model3DRequest, _user: str = Depends(ctx.require_user)) -> dict[str, Any]:
        return ctx.model_3d.create_model(
            request.prompt,
            shape=request.shape,
            formats=request.formats,
            name=request.name,
            quality=request.quality,
            backend=request.backend,
        )

    @router.get("/text-to-3d/status")
    def text_to_3d_status(_user: str = Depends(ctx.require_user)) -> dict[str, Any]:
        return ctx.text_to_3d.status()

    @router.post("/text-to-3d/generate")
    def text_to_3d_generate(request: TextTo3DRequest, _user: str = Depends(ctx.require_user)) -> dict[str, Any]:
        output_dir = ctx.DATA_DIR / "3d_models" / "text_to_3d_api"
        return ctx.text_to_3d.generate(
            request.prompt,
            output_dir,
            formats=request.formats,
            provider=request.provider,
            name=request.name,
            shape=request.shape,
        )

    app.include_router(router)
