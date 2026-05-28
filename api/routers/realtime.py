"""Realtime WebSocket routes."""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect


def register_routes(app: Any, ctx: Any) -> None:
    router = APIRouter()

    @router.websocket("/ws/tasks")
    async def task_stream(websocket: WebSocket, token: str = "") -> None:
        try:
            ctx.api_auth.decode_token(token, token_type="access")
        except ctx.api_auth.AuthError:
            await websocket.close(code=1008)
            return
        await websocket.accept()
        last_payload = ""
        try:
            while True:
                payload = await asyncio.to_thread(ctx._task_stream_payload)
                text = ctx._stream_payload_signature(payload)
                if text != last_payload:
                    last_payload = text
                    await websocket.send_json(payload)
                await asyncio.sleep(1.0)
        except WebSocketDisconnect:
            return

    app.include_router(router)
