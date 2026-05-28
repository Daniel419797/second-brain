"""Core API routes: auth, health, dashboard snapshot, and chat."""

from __future__ import annotations

import datetime as dt
from typing import Any

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    username: str = Field(default="friday", max_length=80)
    password: str = Field(min_length=1, max_length=500)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)


class ChatAttachmentRequest(BaseModel):
    filename: str = Field(default="attachment", max_length=300)
    content_type: str = Field(default="", max_length=160)
    data_url: str = Field(default="", max_length=30_000_000)
    base64: str = Field(default="", max_length=30_000_000)


def register_routes(app: Any, ctx: Any) -> None:
    router = APIRouter()

    @router.post("/auth/login")
    def login(request: LoginRequest, response: Response) -> dict[str, Any]:
        if not ctx.api_auth.authenticate(request.username, request.password):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API credentials.")
        access_token = ctx.api_auth.create_token(request.username, token_type="access")
        refresh_token = ctx.api_auth.create_token(
            request.username,
            token_type="refresh",
            hours=float(ctx.config_value("api_refresh_exp_hours", 24 * 7)),
        )
        response.set_cookie(
            "friday_refresh_token",
            refresh_token,
            httponly=True,
            secure=bool(ctx.config_value("api_secure_cookies", False)),
            samesite="lax",
            max_age=int(float(ctx.config_value("api_refresh_exp_hours", 24 * 7)) * 3600),
        )
        return {"access_token": access_token, "token_type": "bearer", "expires_at": ctx.api_auth.token_expiry()}

    @router.post("/auth/refresh")
    def refresh(response: Response, friday_refresh_token: str | None = Cookie(default=None)) -> dict[str, Any]:
        if not friday_refresh_token:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing refresh token.")
        payload = ctx._decode_or_401(friday_refresh_token, token_type="refresh")
        access_token = ctx.api_auth.create_token(str(payload["sub"]), token_type="access")
        return {"access_token": access_token, "token_type": "bearer", "expires_at": ctx.api_auth.token_expiry()}

    @router.get("/health")
    def health(_user: str = Depends(ctx.require_user)) -> dict[str, Any]:
        return {"ok": True, "name": "Friday", "api": "v2"}

    @router.get("/dashboard/snapshot")
    def dashboard_snapshot(_user: str = Depends(ctx.require_user)) -> dict[str, Any]:
        return ctx._dashboard_snapshot()

    @router.post("/chat")
    def chat(request: ChatRequest, _user: str = Depends(ctx.require_user)) -> dict[str, Any]:
        message = " ".join(str(request.message or "").split())
        if not message:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Message is empty.")
        reply = ctx.orchestrator.handle_command(message)
        return {
            "message": message,
            "reply": reply,
            "timestamp": dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds"),
        }

    @router.post("/voice/chat")
    def voice_chat(request: ChatRequest, _user: str = Depends(ctx.require_user)) -> dict[str, Any]:
        message = " ".join(str(request.message or "").split())
        if not message:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Message is empty.")
        with ctx.llm.voice_route():
            reply = ctx.orchestrator.handle_command(message)
        return {
            "message": message,
            "reply": reply,
            "mode": "voice-fast",
            "model": str(ctx.config_value("voice_nvidia_model", "meta/llama-3.1-8b-instruct")),
            "timestamp": dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds"),
        }

    @router.post("/chat/attachments")
    def chat_attachment(request: ChatAttachmentRequest, _user: str = Depends(ctx.require_user)) -> dict[str, Any]:
        return ctx._store_chat_attachment(request)

    app.include_router(router)
