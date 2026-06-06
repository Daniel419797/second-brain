"""Domain router registration for the Friday API."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI

from api.routers import core, friday_runs, media, ops, realtime


def register_domain_routers(app: FastAPI, ctx: Any) -> None:
    """Register extracted domain routers.

    The server module is passed as ``ctx`` so route modules can be split out
    gradually without circular imports or a giant dependency container.
    """

    core.register_routes(app, ctx)
    friday_runs.register_routes(app, ctx)
    media.register_routes(app, ctx)
    ops.register_routes(app, ctx)
    realtime.register_routes(app, ctx)
