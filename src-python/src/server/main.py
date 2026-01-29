"""MCP Server entry point for TTAI."""

import argparse
import asyncio
import contextlib
import logging
import sys
from pathlib import Path

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
from src.server.ssl import CertificateFetchError, CertificateManager
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
    logger.debug(f"TastyTrade service created and stored: {_tastytrade_service}")

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


async def run_http(
    server: Server,
    host: str,
    port: int,
    ssl_certfile: Path | None = None,
    ssl_keyfile: Path | None = None,
) -> None:
    """Run the server in HTTP/HTTPS mode with streamable HTTP transport.

    Args:
        server: The MCP server instance
        host: Host to bind to
        port: Port to bind to
        ssl_certfile: Path to SSL certificate file (for HTTPS)
        ssl_keyfile: Path to SSL private key file (for HTTPS)
    """
    session_manager = StreamableHTTPSessionManager(app=server)

    @contextlib.asynccontextmanager
    async def lifespan(app: Starlette):
        async with session_manager.run():
            yield

    # Create an ASGI app wrapper for the MCP endpoint
    async def mcp_asgi_app(scope, receive, send):
        await session_manager.handle_request(scope, receive, send)

    starlette_app = Starlette(
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

    # Middleware to normalize /mcp to /mcp/ (avoid 307 redirect)
    async def app(scope, receive, send):
        if scope["type"] == "http" and scope["path"] == "/mcp":
            scope = dict(scope)
            scope["path"] = "/mcp/"
        await starlette_app(scope, receive, send)

    # Configure SSL if certificates provided
    ssl_enabled = ssl_certfile is not None and ssl_keyfile is not None
    protocol = "https" if ssl_enabled else "http"
    logger.info(f"Starting MCP server in {protocol.upper()} mode at {protocol}://{host}:{port}/mcp")

    uvicorn_config = uvicorn.Config(
        app,
        host=host,
        port=port,
        log_level="warning",
        ssl_certfile=str(ssl_certfile) if ssl_certfile else None,
        ssl_keyfile=str(ssl_keyfile) if ssl_keyfile else None,
    )
    uvicorn_server = uvicorn.Server(uvicorn_config)
    await uvicorn_server.serve()


def parse_args() -> argparse.Namespace:
    """Parse command line arguments.

    Returns:
        Parsed arguments namespace
    """
    parser = argparse.ArgumentParser(
        description="TTAI - TastyTrade AI Assistant"
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run as headless MCP server (no GUI). Default is to launch GUI.",
    )
    parser.add_argument(
        "--transport",
        choices=["stdio", "http"],
        default=None,
        help="Transport mode (default: from TTAI_TRANSPORT env or 'http')",
    )
    parser.add_argument(
        "--host",
        default=None,
        help="Host to bind to for HTTP mode (default: from TTAI_HOST env or 'localhost')",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help="Port to bind to for HTTP mode (default: from TTAI_PORT env or 8080)",
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
    parser.add_argument(
        "--ssl-domain",
        default=None,
        help="Base domain for SSL (e.g., 'tt-ai.dev'). Enables HTTPS mode.",
    )
    parser.add_argument(
        "--ssl-port",
        type=int,
        default=None,
        help="Port for HTTPS mode (default: from TTAI_SSL_PORT env or 8443)",
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
        cfg.data_dir = Path(args.data_dir)
    if args.ssl_domain is not None:
        cfg.ssl_domain = args.ssl_domain
    if args.ssl_port is not None:
        cfg.ssl_port = args.ssl_port

    return cfg


async def _run_http_with_ssl(server: Server, cfg: ServerConfig) -> None:
    """Run HTTP server with optional SSL support.

    Attempts HTTPS if ssl_domain is configured, falls back to HTTP on failure.

    Args:
        server: The MCP server instance
        cfg: Server configuration
    """
    # Auto-restore TastyTrade session if credentials exist
    if _tastytrade_service is not None:
        try:
            if await _tastytrade_service.restore_session():
                logger.info("TastyTrade session restored from stored credentials")
            else:
                logger.warning("No stored credentials to restore TastyTrade session")
        except Exception as e:
            logger.warning(f"Failed to restore TastyTrade session: {e}")

    ssl_certfile: Path | None = None
    ssl_keyfile: Path | None = None
    host = cfg.host
    port = cfg.port

    if cfg.ssl_enabled:
        logger.info(f"SSL enabled for domain: {cfg.ssl_local_domain}")
        cert_manager = CertificateManager(cfg.ssl_cert_dir, cfg.ssl_cert_api)

        try:
            ssl_certfile, ssl_keyfile = await cert_manager.ensure_certificate()
            # Bind to 127.0.0.1 (the domain resolves here via DNS)
            host = "127.0.0.1"
            port = cfg.ssl_port
            logger.info(f"Certificate ready, starting HTTPS on {cfg.ssl_local_domain}:{port}")
        except CertificateFetchError as e:
            logger.warning(f"Failed to obtain SSL certificate: {e}")
            logger.warning(f"Falling back to HTTP on {cfg.host}:{cfg.port}")
            ssl_certfile = None
            ssl_keyfile = None

    await run_http(server, host, port, ssl_certfile, ssl_keyfile)


def run() -> None:
    """Main entry point for TTAI.

    Default behavior is to launch the GUI. Use --headless for MCP server mode.
    """
    args = parse_args()
    cfg = build_config(args)

    # Setup logging
    setup_logging(cfg.log_level, cfg.log_dir)

    if not args.headless:
        # GUI mode (default)
        from src.gui.app import run_gui

        # If transport is also specified via env, run both GUI and server
        mcp_server = None
        tastytrade_svc = None
        if cfg.transport == "http":
            logger.info("TTAI starting in GUI mode with MCP server")
            mcp_server = create_server(cfg)
            tastytrade_svc = _tastytrade_service
        else:
            logger.info("TTAI starting in GUI mode")

        sys.exit(run_gui(cfg, mcp_server, tastytrade_svc))

    # Headless MCP server mode
    logger.info(f"TTAI Server starting in headless mode with config: {cfg}")

    # Create server with config
    server = create_server(cfg)

    # Run in appropriate mode
    try:
        if cfg.transport == "http":
            asyncio.run(_run_http_with_ssl(server, cfg))
        else:
            asyncio.run(run_stdio(server))
    except KeyboardInterrupt:
        logger.info("Server stopped")


if __name__ == "__main__":
    run()
