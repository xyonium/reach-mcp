"""Assemble the app: reach_* MCP tools + /health on one server."""
from __future__ import annotations

import logging

from reach_mcp.config import Settings
from reach_mcp.tools import build_mcp

log = logging.getLogger(__name__)


def build_app(settings: Settings):
    mcp = build_mcp(settings)

    @mcp.custom_route("/health", methods=["GET"])
    async def _health(request):
        from starlette.responses import JSONResponse
        return JSONResponse({"status": "ok"})

    app = mcp.streamable_http_app()
    app.state.settings = settings
    app.state.mcp = mcp
    return app
