"""MCP Server entry point for TTAI."""

import argparse
import asyncio
import contextlib
import logging

import uvicorn
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route

from src.auth.credentials import CredentialManager
from src.server.config import ServerConfig
from src.server.tools import register_tools
from src.services.cache import CacheService
from src.services.tastytrade import TastyTradeService
from src.utils.logging import setup_logging

# Global reference to TastyTrade service for REST API
_tastytrade_service: TastyTradeService | None = None

logger = logging.getLogger("ttai.server")


def create_server(cfg: ServerConfig) -> Server:
    """Create and configure the MCP server.

    Args:
        cfg: Server configuration

    Returns:
        Configured MCP Server instance with tools registered
    """
    global _tastytrade_service

    server = Server("ttai-server")

    # Initialize services
    credential_manager = CredentialManager(cfg.data_dir)
    cache_service = CacheService()
    tastytrade_service = TastyTradeService(credential_manager, cache_service)

    # Store global reference for REST API
    _tastytrade_service = tastytrade_service

    # Register tools with services
    register_tools(server, tastytrade_service)

    return server


# REST API handlers for Tauri frontend
async def handle_health(request: Request) -> JSONResponse:
    """Health check endpoint."""
    return JSONResponse({"status": "ok"})


async def handle_auth_status(request: Request) -> JSONResponse:
    """Get authentication status."""
    if _tastytrade_service is None:
        return JSONResponse({"error": "Service not initialized"}, status_code=500)

    return JSONResponse(_tastytrade_service.get_auth_status())


async def handle_login(request: Request) -> JSONResponse:
    """Login to TastyTrade."""
    if _tastytrade_service is None:
        return JSONResponse({"error": "Service not initialized"}, status_code=500)

    try:
        body = await request.json()
        client_secret = body.get("client_secret")
        refresh_token = body.get("refresh_token")
        remember_me = body.get("remember_me", True)

        if not client_secret or not refresh_token:
            return JSONResponse({
                "success": False,
                "error": "client_secret and refresh_token are required"
            }, status_code=400)

        success = await _tastytrade_service.login(client_secret, refresh_token, remember_me)
        if success:
            return JSONResponse({"success": True})
        else:
            return JSONResponse({"success": False, "error": "Login failed"})
    except Exception as e:
        logger.exception("Login failed")
        return JSONResponse({"success": False, "error": str(e)})


async def handle_logout(request: Request) -> JSONResponse:
    """Logout from TastyTrade."""
    if _tastytrade_service is None:
        return JSONResponse({"error": "Service not initialized"}, status_code=500)

    try:
        body = await request.json()
        clear_credentials = body.get("clear_credentials", False)

        await _tastytrade_service.logout(clear_credentials)
        return JSONResponse({"success": True})
    except Exception as e:
        logger.exception("Logout failed")
        return JSONResponse({"success": False, "error": str(e)})


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
    session_manager = StreamableHTTPSessionManager(app=server)

    @contextlib.asynccontextmanager
    async def lifespan(app: Starlette):
        async with session_manager.run():
            yield

    # Create an ASGI app wrapper for the MCP endpoint
    async def mcp_asgi_app(scope, receive, send):
        await session_manager.handle_request(scope, receive, send)

    app = Starlette(
        lifespan=lifespan,
        routes=[
            # MCP streamable HTTP transport at /mcp
            Mount("/mcp", app=mcp_asgi_app),
            # REST API for Tauri frontend
            Route("/api/health", endpoint=handle_health),
            Route("/api/auth-status", endpoint=handle_auth_status),
            Route("/api/login", endpoint=handle_login, methods=["POST"]),
            Route("/api/logout", endpoint=handle_logout, methods=["POST"]),
        ],
    )

    logger.info(f"Starting MCP server in HTTP mode at http://{host}:{port}/mcp")

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
