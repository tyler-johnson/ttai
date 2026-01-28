"""MCP Server entry point for TTAI."""

import argparse
import asyncio
import logging
from typing import Literal

from mcp.server import Server
from mcp.server.sse import SseServerTransport
from mcp.server.stdio import stdio_server
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Route
import uvicorn

from src.auth.credentials import CredentialManager
from src.server.config import ServerConfig, config
from src.server.tools import register_tools
from src.services.cache import CacheService
from src.services.tastytrade import TastyTradeService
from src.utils.logging import setup_logging

logger = logging.getLogger("ttai.server")


def create_server(cfg: ServerConfig) -> Server:
    """Create and configure the MCP server.

    Args:
        cfg: Server configuration

    Returns:
        Configured MCP Server instance with tools registered
    """
    server = Server("ttai-server")

    # Initialize services
    credential_manager = CredentialManager(cfg.data_dir)
    cache_service = CacheService()
    tastytrade_service = TastyTradeService(credential_manager, cache_service)

    # Register tools with services
    register_tools(server, tastytrade_service)

    return server


async def run_stdio(server: Server) -> None:
    """Run the server in stdio mode.

    Args:
        server: The MCP server instance
    """
    logger.info("Starting MCP server in stdio mode")

    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


async def run_sse(server: Server, host: str, port: int) -> None:
    """Run the server in SSE mode with HTTP transport.

    Args:
        server: The MCP server instance
        host: Host to bind to
        port: Port to bind to
    """
    sse_transport = SseServerTransport("/messages/")

    async def handle_sse(request: Request) -> Response:
        """Handle SSE connection requests."""
        async with sse_transport.connect_sse(
            request.scope, request.receive, request._send
        ) as streams:
            await server.run(
                streams[0],
                streams[1],
                server.create_initialization_options(),
            )
        return Response()

    async def handle_messages(request: Request) -> Response:
        """Handle incoming messages."""
        return await sse_transport.handle_post_message(
            request.scope, request.receive, request._send
        )

    app = Starlette(
        routes=[
            Route("/sse", endpoint=handle_sse),
            Route("/messages/", endpoint=handle_messages, methods=["POST"]),
        ],
    )

    logger.info(f"Starting MCP server in SSE mode at http://{host}:{port}/sse")

    uvicorn_config = uvicorn.Config(
        app,
        host=host,
        port=port,
        log_level="warning",
    )
    uvicorn_server = uvicorn.Server(uvicorn_config)
    await uvicorn_server.serve()


def parse_args() -> argparse.Namespace:
    """Parse command line arguments.

    Returns:
        Parsed arguments namespace
    """
    parser = argparse.ArgumentParser(
        description="TTAI MCP Server - TastyTrade AI Assistant"
    )
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse"],
        default=None,
        help="Transport mode (default: from TTAI_TRANSPORT env or 'stdio')",
    )
    parser.add_argument(
        "--host",
        default=None,
        help="Host to bind to for SSE mode (default: from TTAI_HOST env or 'localhost')",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help="Port to bind to for SSE mode (default: from TTAI_PORT env or 8080)",
    )
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        default=None,
        help="Log level (default: from TTAI_LOG_LEVEL env or 'INFO')",
    )
    parser.add_argument(
        "--data-dir",
        default=None,
        help="Data directory (default: from TTAI_DATA_DIR env or '~/.ttai')",
    )
    return parser.parse_args()


def build_config(args: argparse.Namespace) -> ServerConfig:
    """Build server configuration from args and environment.

    CLI arguments take precedence over environment variables.

    Args:
        args: Parsed command line arguments

    Returns:
        Final server configuration
    """
    # Start with environment-based config
    cfg = ServerConfig.from_env()

    # Override with CLI arguments if provided
    if args.transport is not None:
        cfg.transport = args.transport
    if args.host is not None:
        cfg.host = args.host
    if args.port is not None:
        cfg.port = args.port
    if args.log_level is not None:
        cfg.log_level = args.log_level
    if args.data_dir is not None:
        cfg.data_dir = args.data_dir

    return cfg


def run() -> None:
    """Main entry point for the TTAI MCP server."""
    args = parse_args()
    cfg = build_config(args)

    # Setup logging
    setup_logging(cfg.log_level, cfg.log_dir)

    logger.info(f"TTAI Server starting with config: {cfg}")

    # Create server with config
    server = create_server(cfg)

    # Run in appropriate mode
    if cfg.transport == "sse":
        asyncio.run(run_sse(server, cfg.host, cfg.port))
    else:
        asyncio.run(run_stdio(server))


if __name__ == "__main__":
    run()
