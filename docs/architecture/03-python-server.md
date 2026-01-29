# Python Server Architecture

## Overview

The Python MCP server provides the backend for TTAI, implementing the MCP protocol for AI-assisted trading analysis, managing TastyTrade API integration, and handling all backend processing. The server supports two deployment modes with the same codebase:

- **Sidecar Mode**: Packaged as a PyInstaller binary, runs as a subprocess of the Tauri application
- **Headless Mode**: Run directly from source as a standalone server

## Running Modes

The server can run in either mode, selected via CLI arguments or environment variables.

### Quick Start

```bash
# Sidecar mode (stdio transport) - default
python -m src.server.main

# Headless mode (HTTP/SSE transport)
python -m src.server.main --transport sse --port 5180

# Or via environment variables
TTAI_TRANSPORT=sse TTAI_PORT=5180 python -m src.server.main
```

### Mode Comparison

| Feature | Sidecar Mode | Headless Mode |
|---------|--------------|---------------|
| Transport | stdio | HTTP/SSE |
| Launcher | Tauri app spawns process | User runs from terminal |
| Binary | PyInstaller executable | Python source |
| Notifications | stderr → Tauri | Webhooks |
| Use case | Desktop app users | Developers, server deployments |

### CLI Arguments

```bash
python -m src.server.main [OPTIONS]

Options:
  --transport {stdio,sse}  Transport protocol (default: stdio)
  --host HOST              Host for SSE transport (default: localhost)
  --port PORT              Port for SSE transport (default: 5180)
  --log-level LEVEL        Logging level (default: INFO)
  --data-dir PATH          Data directory (default: ~/.ttai)
```

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `TTAI_TRANSPORT` | Transport: `stdio` or `sse` | `stdio` |
| `TTAI_HOST` | SSE host | `localhost` |
| `TTAI_PORT` | SSE port | `5180` |
| `TTAI_LOG_LEVEL` | Log level | `INFO` |
| `TTAI_DATA_DIR` | Data directory | `~/.ttai` |
| `TTAI_NOTIFICATION_BACKEND` | `auto`, `tauri`, or `webhook` | `auto` |
| `TTAI_WEBHOOK_URL` | Webhook URL for notifications | None |
| `TASTYTRADE_API_URL` | TastyTrade API URL | `https://api.tastyworks.com` |

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                    Python MCP Server                                 │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ┌────────────────────────────────────────────────────────────────┐ │
│  │                        Entry Point                              │ │
│  │                    src/server/main.py                           │ │
│  │       CLI parsing | Transport selection | Graceful shutdown     │ │
│  └────────────────────────────────────────────────────────────────┘ │
│                              │                                       │
│  ┌────────────────────────────────────────────────────────────────┐ │
│  │                     Transport Layer                             │ │
│  │  ┌──────────────────────┐    ┌──────────────────────┐          │ │
│  │  │   stdio Transport    │    │   HTTP/SSE Transport │          │ │
│  │  └──────────────────────┘    └──────────────────────┘          │ │
│  └────────────────────────────────────────────────────────────────┘ │
│                              │                                       │
│  ┌───────────────────────────┴───────────────────────────────────┐  │
│  │                     MCP Protocol Layer                         │  │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐       │  │
│  │  │  Tools   │  │ Resources│  │ Prompts  │  │ Handlers │       │  │
│  │  └──────────┘  └──────────┘  └──────────┘  └──────────┘       │  │
│  └───────────────────────────────────────────────────────────────┘  │
│                              │                                       │
│  ┌───────────────────────────┴───────────────────────────────────┐  │
│  │                      Services Layer                            │  │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐       │  │
│  │  │TastyTrade│  │ Database │  │  Cache   │  │Knowledge │       │  │
│  │  └──────────┘  └──────────┘  └──────────┘  └──────────┘       │  │
│  └───────────────────────────────────────────────────────────────┘  │
│                              │                                       │
│  ┌───────────────────────────┴───────────────────────────────────┐  │
│  │                       Agents Layer                             │  │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐       │  │
│  │  │  Chart   │  │ Options  │  │ Research │  │Orchestrat│       │  │
│  │  │ Analyst  │  │ Analyst  │  │ Analyst  │  │   or     │       │  │
│  │  └──────────┘  └──────────┘  └──────────┘  └──────────┘       │  │
│  └───────────────────────────────────────────────────────────────┘  │
│                              │                                       │
│  ┌───────────────────────────┴───────────────────────────────────┐  │
│  │                    Background Tasks                            │  │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐       │  │
│  │  │ Portfolio│  │  Price   │  │ Position │  │Scheduler │       │  │
│  │  │ Monitor  │  │  Alerts  │  │   Sync   │  │          │       │  │
│  │  └──────────┘  └──────────┘  └──────────┘  └──────────┘       │  │
│  └───────────────────────────────────────────────────────────────┘  │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

## Project Structure

```
ttai/
├── src-python/                      # Python server source
│   ├── pyproject.toml               # Project configuration
│   ├── requirements.txt             # Dependencies for pip
│   ├── requirements-dev.txt         # Development dependencies
│   │
│   ├── src/
│   │   ├── __init__.py
│   │   ├── __main__.py              # Entry point for python -m
│   │   │
│   │   ├── server/                  # MCP server implementation
│   │   │   ├── __init__.py
│   │   │   ├── main.py              # Server entry point
│   │   │   ├── config.py            # Configuration
│   │   │   ├── tools.py             # MCP tool registration
│   │   │   ├── resources.py         # MCP resource registration
│   │   │   ├── prompts.py           # MCP prompt registration
│   │   │   ├── errors.py            # Error types
│   │   │   ├── notifications.py     # Notification backends
│   │   │   └── middleware.py        # Request middleware
│   │   │
│   │   ├── auth/                    # Authentication
│   │   │   ├── __init__.py
│   │   │   ├── credentials.py       # Encrypted credential storage
│   │   │   └── tastytrade.py        # TastyTrade session management
│   │   │
│   │   ├── services/                # Business logic services
│   │   │   ├── __init__.py
│   │   │   ├── tastytrade.py        # TastyTrade API wrapper
│   │   │   ├── database.py          # SQLite database service
│   │   │   ├── cache.py             # In-memory caching
│   │   │   └── knowledge.py         # Knowledge base service
│   │   │
│   │   ├── agents/                  # AI agents
│   │   │   ├── __init__.py
│   │   │   ├── base.py              # Base agent class
│   │   │   ├── chart_analyst.py     # Technical analysis agent
│   │   │   ├── options_analyst.py   # Options analysis agent
│   │   │   ├── research_analyst.py  # Fundamental research agent
│   │   │   └── orchestrator.py      # Multi-agent orchestration
│   │   │
│   │   ├── tasks/                   # Background tasks
│   │   │   ├── __init__.py
│   │   │   ├── manager.py           # Task management
│   │   │   ├── scheduler.py         # Job scheduling
│   │   │   ├── shutdown.py          # Graceful shutdown
│   │   │   ├── loops.py             # Background loop base
│   │   │   └── monitors/            # Monitor implementations
│   │   │       ├── __init__.py
│   │   │       ├── portfolio.py
│   │   │       ├── price_alerts.py
│   │   │       └── position_sync.py
│   │   │
│   │   ├── analysis/                # Analysis utilities
│   │   │   ├── __init__.py
│   │   │   ├── indicators.py        # Technical indicators
│   │   │   ├── levels.py            # Support/resistance detection
│   │   │   └── options.py           # Options calculations
│   │   │
│   │   └── utils/                   # Shared utilities
│   │       ├── __init__.py
│   │       ├── logging.py           # Logging configuration
│   │       └── serialization.py     # JSON serialization helpers
│   │
│   ├── tests/                       # Test suite
│   │   ├── conftest.py              # Pytest fixtures
│   │   ├── test_server/
│   │   ├── test_services/
│   │   ├── test_agents/
│   │   └── test_tasks/
│   │
│   └── scripts/                     # Build scripts
│       ├── build.py                 # PyInstaller build script
│       └── dev.py                   # Development server
│
├── src-tauri/                       # Tauri application
│   └── binaries/                    # PyInstaller output goes here
│       ├── ttai-server-x86_64-apple-darwin
│       ├── ttai-server-aarch64-apple-darwin
│       ├── ttai-server-x86_64-pc-windows-msvc.exe
│       └── ttai-server-x86_64-unknown-linux-gnu
│
└── src/                             # Svelte frontend
```

## pyproject.toml Configuration

```toml
# src-python/pyproject.toml
[project]
name = "ttai-server"
version = "0.1.0"
description = "TTAI MCP Server for AI-assisted trading analysis"
requires-python = ">=3.11"
license = {text = "MIT"}
authors = [
    {name = "Your Name", email = "you@example.com"}
]

dependencies = [
    # MCP SDK
    "mcp>=1.0.0",

    # HTTP server (for SSE transport)
    "starlette>=0.27.0",
    "uvicorn>=0.23.0",

    # TastyTrade API
    "tastytrade>=8.0.0",

    # LLM Integration
    "litellm>=1.0.0",

    # Database
    "aiosqlite>=0.19.0",

    # Vector search
    "sentence-transformers>=2.2.0",
    "sqlite-vec>=0.1.0",

    # Encryption
    "cryptography>=41.0.0",

    # Data processing
    "pandas>=2.0.0",
    "numpy>=1.24.0",

    # Validation
    "pydantic>=2.0.0",

    # HTTP client
    "httpx>=0.25.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=7.0.0",
    "pytest-asyncio>=0.21.0",
    "pytest-cov>=4.0.0",
    "black>=23.0.0",
    "ruff>=0.1.0",
    "mypy>=1.0.0",
    "pyinstaller>=6.0.0",
]

[project.scripts]
ttai-server = "src.server.main:run"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src"]

[tool.black]
line-length = 100
target-version = ["py311"]

[tool.ruff]
line-length = 100
select = ["E", "F", "I", "N", "W", "B", "C4", "UP"]
ignore = ["E501"]

[tool.mypy]
python_version = "3.11"
strict = true
ignore_missing_imports = true

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

## Main Entry Point

```python
# src/__main__.py
"""Entry point for python -m src"""
from src.server.main import run

if __name__ == "__main__":
    run()
```

```python
# src/server/main.py
import argparse
import asyncio
import logging
import os
import sys

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.server.sse import SseServerTransport
from starlette.applications import Starlette
from starlette.routing import Route
import uvicorn

from .config import config
from .tools import register_tools
from .resources import register_resources
from .prompts import register_prompts
from .notifications import get_notifier
from ..auth.credentials import CredentialManager
from ..auth.tastytrade import TastyTradeAuth
from ..services.database import DatabaseService
from ..services.tastytrade import TastyTradeService
from ..services.cache import CacheService
from ..tasks.manager import task_manager
from ..tasks.shutdown import shutdown_handler
from ..tasks.monitors.portfolio import PortfolioMonitor
from ..tasks.monitors.price_alerts import PriceAlertMonitor
from ..tasks.monitors.position_sync import PositionSyncMonitor
from ..tasks.scheduled_jobs import setup_scheduled_jobs
from ..utils.logging import setup_logging

logger = logging.getLogger(__name__)


async def create_server() -> tuple[Server, dict]:
    """Create and configure the MCP server with all services."""
    # Initialize services
    db = await DatabaseService.create(config.db_path)
    cache = CacheService()

    # Initialize authentication
    creds = CredentialManager(config.data_dir)
    auth = TastyTradeAuth(creds)

    # Try to restore session
    if await auth.restore_session():
        logger.info("Restored TastyTrade session")
    else:
        logger.info("No saved session, login required")

    # Initialize TastyTrade service
    tastytrade = TastyTradeService(db, cache)
    if auth.is_authenticated:
        tastytrade.set_session(auth.session)

    # Create MCP server
    server = Server("ttai-mcp-server")

    # Register MCP capabilities
    register_tools(server, db, tastytrade, cache, auth)
    register_resources(server, db, tastytrade)
    register_prompts(server)

    # Return server and services for lifecycle management
    services = {
        "db": db,
        "cache": cache,
        "auth": auth,
        "tastytrade": tastytrade,
    }

    return server, services


async def start_background_tasks(services: dict) -> list:
    """Start background monitors if authenticated."""
    tastytrade = services["tastytrade"]
    db = services["db"]
    auth = services["auth"]

    monitors = []

    if auth.is_authenticated:
        portfolio_monitor = PortfolioMonitor(tastytrade, db)
        price_alerts = PriceAlertMonitor(tastytrade, db)
        position_sync = PositionSyncMonitor(tastytrade, db)

        await portfolio_monitor.start()
        await price_alerts.start()
        await position_sync.start()

        monitors = [portfolio_monitor, price_alerts, position_sync]

        # Setup scheduled jobs
        await setup_scheduled_jobs(tastytrade, db)

    # Register cleanup callbacks
    for monitor in monitors:
        shutdown_handler.register_callback(monitor.stop)
    shutdown_handler.register_callback(db.close)

    return monitors


async def run_stdio():
    """Run with stdio transport (sidecar mode)."""
    setup_logging(config.log_level)
    logger.info("Starting TTAI MCP Server (stdio transport)")
    logger.info(f"Data directory: {config.data_dir}")

    server, services = await create_server()
    await start_background_tasks(services)

    # Setup signal handlers for graceful shutdown
    loop = asyncio.get_event_loop()
    shutdown_handler.setup_signal_handlers(loop)

    logger.info("MCP Server ready (stdio)")

    try:
        async with stdio_server() as (read_stream, write_stream):
            await server.run(
                read_stream,
                write_stream,
                server.create_initialization_options()
            )
    except Exception as e:
        logger.error(f"Server error: {e}")
        raise
    finally:
        await shutdown_handler.shutdown()
        logger.info("Server shutdown complete")


async def run_sse(host: str, port: int):
    """Run with HTTP/SSE transport (headless mode)."""
    setup_logging(config.log_level)
    logger.info(f"Starting TTAI MCP Server (SSE transport on {host}:{port})")
    logger.info(f"Data directory: {config.data_dir}")

    server, services = await create_server()
    await start_background_tasks(services)

    sse = SseServerTransport("/messages")

    async def handle_sse(request):
        async with sse.connect_sse(
            request.scope, request.receive, request._send
        ) as streams:
            await server.run(
                streams[0], streams[1],
                server.create_initialization_options()
            )

    app = Starlette(
        routes=[
            Route("/sse", endpoint=handle_sse),
            Route("/messages", endpoint=sse.handle_post_message, methods=["POST"]),
        ]
    )

    uvicorn_config = uvicorn.Config(app, host=host, port=port, log_level="info")
    uvicorn_server = uvicorn.Server(uvicorn_config)

    logger.info(f"MCP Server ready at http://{host}:{port}/sse")

    try:
        await uvicorn_server.serve()
    except Exception as e:
        logger.error(f"Server error: {e}")
        raise
    finally:
        await shutdown_handler.shutdown()
        logger.info("Server shutdown complete")


async def async_main():
    """Async main with CLI argument parsing."""
    parser = argparse.ArgumentParser(description="TTAI MCP Server")
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse"],
        default=os.getenv("TTAI_TRANSPORT", "stdio"),
        help="Transport protocol (default: stdio)"
    )
    parser.add_argument(
        "--host",
        default=os.getenv("TTAI_HOST", "localhost"),
        help="Host for SSE transport (default: localhost)"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.getenv("TTAI_PORT", "5180")),
        help="Port for SSE transport (default: 5180)"
    )
    parser.add_argument(
        "--log-level",
        default=os.getenv("TTAI_LOG_LEVEL", "INFO"),
        help="Logging level (default: INFO)"
    )
    parser.add_argument(
        "--data-dir",
        default=os.getenv("TTAI_DATA_DIR"),
        help="Data directory (default: ~/.ttai)"
    )

    args = parser.parse_args()

    # Update config from CLI args
    config.log_level = args.log_level
    config.transport = args.transport
    if args.data_dir:
        config.data_dir = Path(args.data_dir)

    if args.transport == "stdio":
        await run_stdio()
    else:
        await run_sse(args.host, args.port)


def run():
    """Synchronous entry point."""
    try:
        asyncio.run(async_main())
    except KeyboardInterrupt:
        pass
    except Exception as e:
        print(f"Fatal error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    run()
```

## TastyTrade Client Service

### Service Implementation

```python
# src/services/tastytrade.py
from tastytrade import Session
from tastytrade.account import Account
from tastytrade.instruments import Equity, Option, NestedOptionChain
from tastytrade.market_data import Quote
from typing import Optional, Dict, Any, List
import asyncio
from functools import partial

from .cache import CacheService
from .database import DatabaseService

class TastyTradeService:
    """
    Wrapper service for TastyTrade API operations.

    Provides async interface over the synchronous tastytrade package,
    with caching and error handling.
    """

    def __init__(
        self,
        db: DatabaseService,
        cache: CacheService,
        session: Optional[Session] = None
    ):
        self.db = db
        self.cache = cache
        self._session = session
        self._account: Optional[Account] = None

    @property
    def session(self) -> Session:
        """Get the current session."""
        if self._session is None:
            raise RuntimeError("Not authenticated. Call set_session first.")
        return self._session

    def set_session(self, session: Session) -> None:
        """Set the TastyTrade session."""
        self._session = session
        accounts = Account.get_accounts(session)
        self._account = accounts[0] if accounts else None

    @property
    def account(self) -> Account:
        """Get the primary account."""
        if self._account is None:
            raise RuntimeError("No account available")
        return self._account

    async def get_quote(self, symbol: str) -> Dict[str, Any]:
        """
        Get real-time quote for a symbol.

        Uses cache with 60-second TTL.
        """
        cache_key = f"quote:{symbol}"

        # Check cache first
        cached = self.cache.get(cache_key)
        if cached:
            return cached

        # Fetch from TastyTrade (run in executor to not block)
        loop = asyncio.get_event_loop()
        quote = await loop.run_in_executor(
            None,
            partial(self._fetch_quote, symbol)
        )

        # Cache the result
        self.cache.set(cache_key, quote, ttl=60)

        return quote

    def _fetch_quote(self, symbol: str) -> Dict[str, Any]:
        """Synchronous quote fetch."""
        quotes = Quote.get_quotes(self.session, [symbol])
        if not quotes:
            raise ValueError(f"No quote found for {symbol}")

        q = quotes[0]
        return {
            "symbol": symbol,
            "last": float(q.last or 0),
            "bid": float(q.bid or 0),
            "ask": float(q.ask or 0),
            "volume": int(q.volume or 0),
            "open": float(q.open or 0),
            "high": float(q.high or 0),
            "low": float(q.low or 0),
            "close": float(q.close or 0),
            "change": float(q.change or 0),
            "change_percent": float(q.change_percent or 0),
        }

    async def get_quotes(self, symbols: List[str]) -> Dict[str, Dict[str, Any]]:
        """Get quotes for multiple symbols."""
        results = {}

        # Check cache for each symbol
        uncached_symbols = []
        for symbol in symbols:
            cached = self.cache.get(f"quote:{symbol}")
            if cached:
                results[symbol] = cached
            else:
                uncached_symbols.append(symbol)

        # Batch fetch uncached symbols
        if uncached_symbols:
            loop = asyncio.get_event_loop()
            quotes = await loop.run_in_executor(
                None,
                partial(Quote.get_quotes, self.session, uncached_symbols)
            )

            for q in quotes:
                quote_data = {
                    "symbol": q.symbol,
                    "last": float(q.last or 0),
                    "bid": float(q.bid or 0),
                    "ask": float(q.ask or 0),
                    "volume": int(q.volume or 0),
                    "change": float(q.change or 0),
                    "change_percent": float(q.change_percent or 0),
                }
                results[q.symbol] = quote_data
                self.cache.set(f"quote:{q.symbol}", quote_data, ttl=60)

        return results

    async def get_option_chain(
        self,
        symbol: str,
        expiration: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get option chain for a symbol.

        Args:
            symbol: Underlying symbol
            expiration: Optional specific expiration (YYYY-MM-DD)

        Returns:
            Nested option chain data
        """
        cache_key = f"chain:{symbol}:{expiration or 'all'}"
        cached = self.cache.get(cache_key)
        if cached:
            return cached

        loop = asyncio.get_event_loop()
        chain = await loop.run_in_executor(
            None,
            partial(self._fetch_option_chain, symbol, expiration)
        )

        # Cache with longer TTL for chains (5 minutes)
        self.cache.set(cache_key, chain, ttl=300)

        return chain

    def _fetch_option_chain(
        self,
        symbol: str,
        expiration: Optional[str] = None
    ) -> Dict[str, Any]:
        """Synchronous option chain fetch."""
        chain = NestedOptionChain.get_chain(self.session, symbol)

        expirations = []
        for exp in chain.expirations:
            exp_date = exp.expiration_date.isoformat()

            # Filter by expiration if specified
            if expiration and exp_date != expiration:
                continue

            strikes = []
            for strike in exp.strikes:
                strikes.append({
                    "strike": float(strike.strike_price),
                    "call": self._format_option(strike.call) if strike.call else None,
                    "put": self._format_option(strike.put) if strike.put else None,
                })

            expirations.append({
                "expiration": exp_date,
                "dte": exp.days_to_expiration,
                "strikes": strikes,
            })

        return {
            "symbol": symbol,
            "underlying_price": float(chain.underlying_price or 0),
            "expirations": expirations,
        }

    def _format_option(self, opt) -> Dict[str, Any]:
        """Format option data."""
        return {
            "symbol": opt.symbol,
            "bid": float(opt.bid or 0),
            "ask": float(opt.ask or 0),
            "last": float(opt.last or 0),
            "volume": int(opt.volume or 0),
            "open_interest": int(opt.open_interest or 0),
            "delta": float(opt.delta or 0),
            "gamma": float(opt.gamma or 0),
            "theta": float(opt.theta or 0),
            "vega": float(opt.vega or 0),
            "iv": float(opt.implied_volatility or 0),
        }

    async def get_positions(self) -> List[Dict[str, Any]]:
        """Get current portfolio positions."""
        loop = asyncio.get_event_loop()
        positions = await loop.run_in_executor(
            None,
            partial(self.account.get_positions, self.session)
        )

        return [
            {
                "symbol": p.symbol,
                "underlying_symbol": p.underlying_symbol,
                "quantity": int(p.quantity),
                "quantity_direction": p.quantity_direction,
                "average_open_price": float(p.average_open_price or 0),
                "close_price": float(p.close_price or 0),
                "mark": float(p.mark or 0),
                "mark_price": float(p.mark_price or 0),
                "realized_day_gain": float(p.realized_day_gain or 0),
                "instrument_type": p.instrument_type,
            }
            for p in positions
        ]

    async def get_balances(self) -> Dict[str, Any]:
        """Get account balances."""
        loop = asyncio.get_event_loop()
        balances = await loop.run_in_executor(
            None,
            partial(self.account.get_balances, self.session)
        )

        return {
            "cash_balance": float(balances.cash_balance or 0),
            "net_liquidating_value": float(balances.net_liquidating_value or 0),
            "equity_buying_power": float(balances.equity_buying_power or 0),
            "derivative_buying_power": float(balances.derivative_buying_power or 0),
            "day_trading_buying_power": float(balances.day_trading_buying_power or 0),
            "maintenance_excess": float(balances.maintenance_excess or 0),
        }

    async def get_transactions(
        self,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Get account transactions."""
        loop = asyncio.get_event_loop()
        transactions = await loop.run_in_executor(
            None,
            partial(
                self.account.get_transactions,
                self.session,
                start_date=start_date,
                end_date=end_date
            )
        )

        return [
            {
                "id": t.id,
                "transaction_type": t.transaction_type,
                "transaction_sub_type": t.transaction_sub_type,
                "description": t.description,
                "executed_at": t.executed_at.isoformat() if t.executed_at else None,
                "value": float(t.value or 0),
                "net_value": float(t.net_value or 0),
            }
            for t in transactions
        ]
```

## Cache Service

```python
# src/services/cache.py
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Optional, Dict
import threading

@dataclass
class CacheEntry:
    """A cached value with expiration."""
    value: Any
    expires_at: datetime

class CacheService:
    """
    Thread-safe in-memory cache with TTL support.

    Simple LRU-style cache for quote data and API responses.
    """

    def __init__(self, max_size: int = 1000):
        self._cache: Dict[str, CacheEntry] = {}
        self._lock = threading.Lock()
        self._max_size = max_size

    def get(self, key: str) -> Optional[Any]:
        """Get a value from cache if not expired."""
        with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                return None

            if datetime.now() > entry.expires_at:
                del self._cache[key]
                return None

            return entry.value

    def set(self, key: str, value: Any, ttl: int = 60) -> None:
        """
        Set a value in cache with TTL.

        Args:
            key: Cache key
            value: Value to cache
            ttl: Time-to-live in seconds
        """
        with self._lock:
            # Evict oldest entries if at capacity
            if len(self._cache) >= self._max_size:
                self._evict_expired()
                if len(self._cache) >= self._max_size:
                    # Remove oldest entry
                    oldest_key = next(iter(self._cache))
                    del self._cache[oldest_key]

            self._cache[key] = CacheEntry(
                value=value,
                expires_at=datetime.now() + timedelta(seconds=ttl)
            )

    def delete(self, key: str) -> bool:
        """Delete a key from cache."""
        with self._lock:
            if key in self._cache:
                del self._cache[key]
                return True
            return False

    def clear(self) -> None:
        """Clear all cached values."""
        with self._lock:
            self._cache.clear()

    def _evict_expired(self) -> None:
        """Remove all expired entries."""
        now = datetime.now()
        expired_keys = [
            key for key, entry in self._cache.items()
            if now > entry.expires_at
        ]
        for key in expired_keys:
            del self._cache[key]

    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        with self._lock:
            now = datetime.now()
            valid_count = sum(
                1 for entry in self._cache.values()
                if now <= entry.expires_at
            )
            return {
                "total_entries": len(self._cache),
                "valid_entries": valid_count,
                "max_size": self._max_size,
            }
```

## Dependency Management

### requirements.txt

```
# src-python/requirements.txt
# Core MCP
mcp>=1.0.0

# HTTP server (for SSE transport)
starlette>=0.27.0
uvicorn>=0.23.0

# TastyTrade API
tastytrade>=8.0.0

# LLM Integration
litellm>=1.0.0

# Async Database
aiosqlite>=0.19.0

# Vector Search (local)
sentence-transformers>=2.2.0
sqlite-vec>=0.1.0

# Encryption
cryptography>=41.0.0

# Data Processing
pandas>=2.0.0
numpy>=1.24.0

# Validation
pydantic>=2.0.0

# HTTP Client
httpx>=0.25.0
```

### requirements-dev.txt

```
# src-python/requirements-dev.txt
-r requirements.txt

# Testing
pytest>=7.0.0
pytest-asyncio>=0.21.0
pytest-cov>=4.0.0
pytest-mock>=3.0.0

# Formatting & Linting
black>=23.0.0
ruff>=0.1.0
mypy>=1.0.0

# Build
pyinstaller>=6.0.0

# Type stubs
pandas-stubs
types-requests
```

## Logging Configuration

```python
# src/utils/logging.py
import logging
import sys
from pathlib import Path
from datetime import datetime

def setup_logging(level: str = "INFO", log_dir: Path = None) -> None:
    """
    Configure logging for the application.

    Logs to both stderr (for Tauri to capture) and file.
    """
    log_level = getattr(logging, level.upper(), logging.INFO)

    # Root logger configuration
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # Clear existing handlers
    root_logger.handlers.clear()

    # Console handler (stderr)
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setLevel(log_level)
    console_format = logging.Formatter(
        '%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        datefmt='%H:%M:%S'
    )
    console_handler.setFormatter(console_format)
    root_logger.addHandler(console_handler)

    # File handler (if log_dir specified)
    if log_dir:
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / f"ttai-{datetime.now():%Y%m%d}.log"

        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(log_level)
        file_format = logging.Formatter(
            '%(asctime)s [%(levelname)s] %(name)s (%(filename)s:%(lineno)d): %(message)s'
        )
        file_handler.setFormatter(file_format)
        root_logger.addHandler(file_handler)

    # Reduce noise from external libraries
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("tastytrade").setLevel(logging.INFO)
```

## Cross-References

- [MCP Server Design](./01-mcp-server-design.md) - MCP protocol implementation, transports
- [Workflow Orchestration](./02-workflow-orchestration.md) - Task management
- [AI Agent System](./04-ai-agent-system.md) - Agent implementations
- [Data Layer](./05-data-layer.md) - Database service details
- [Background Tasks](./06-background-tasks.md) - Background monitors and notifications
- [Build and Distribution](./08-build-distribution.md) - PyInstaller packaging, headless distribution
- [Local Development](./10-local-development.md) - Running in both modes
