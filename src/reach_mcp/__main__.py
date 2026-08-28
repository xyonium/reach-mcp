"""CLI entrypoint: dispatch http (uvicorn) or stdio (mcp.run)."""

from __future__ import annotations

import argparse
import logging

import uvicorn

from reach_mcp.config import get_settings
from reach_mcp.server import build_app


def main() -> None:
    parser = argparse.ArgumentParser(prog="reach-mcp")
    parser.add_argument(
        "--transport",
        choices=["http", "stdio"],
        default=None,
        help="http (streamable-HTTP, default) or stdio",
    )
    parser.add_argument("--host", default=None)
    parser.add_argument("--port", type=int, default=None)
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    settings = get_settings()
    transport = args.transport or settings.transport
    host = args.host or settings.host
    port = args.port or settings.port

    if transport == "stdio":
        app = build_app(settings)
        app.state.mcp.run(transport="stdio")
        return

    app = build_app(settings)
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
