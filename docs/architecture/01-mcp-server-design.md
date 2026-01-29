# MCP Server Design

## Overview

The MCP (Model Context Protocol) server is a Python application that provides tools, resources, and prompts for AI-assisted trading analysis, handles TastyTrade authentication with locally-encrypted credentials, and orchestrates all backend functionality for the TTAI system.

The server supports two deployment modes with the same codebase:
- **Sidecar Mode**: Bundled with the Tauri desktop app, communicating via stdio
- **Headless Mode**: Run directly from source as a standalone server, communicating via HTTP/SSE

Both modes share the same configuration, support both transport protocols, and provide identical functionality.

## Architecture

### Deployment Modes

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         Python MCP Server                                    │
│                    (One Codebase, Two Deployment Modes)                      │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌────────────────────────────────┐    ┌────────────────────────────────┐   │
│  │      SIDECAR MODE              │    │      HEADLESS MODE             │   │
│  │  (Bundled with Tauri App)      │    │  (Run from Source)             │   │
│  ├────────────────────────────────┤    ├────────────────────────────────┤   │
│  │                                │    │                                │   │
│  │  ┌──────────────────────────┐  │    │  ┌──────────────────────────┐  │   │
│  │  │    Tauri Desktop App     │  │    │  │   External MCP Client    │  │   │
│  │  │  (Svelte + Rust Shell)   │  │    │  │  (Claude Desktop, etc.)  │  │   │
│  │  └───────────┬──────────────┘  │    │  └───────────┬──────────────┘  │   │
│  │              │ stdio           │    │              │ HTTP/SSE        │   │
│  │              ▼                 │    │              ▼                 │   │
│  │  ┌──────────────────────────┐  │    │  ┌──────────────────────────┐  │   │
│  │  │   Python MCP Server      │  │    │  │   Python MCP Server      │  │   │
│  │  │   (PyInstaller binary)   │  │    │  │   (python -m src.server) │  │   │
│  │  └──────────────────────────┘  │    │  └──────────────────────────┘  │   │
│  │                                │    │                                │   │
│  │  Notifications: stderr→Tauri   │    │  Notifications: Webhooks       │   │
│  └────────────────────────────────┘    └────────────────────────────────┘   │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Server Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                    Python MCP Server                                 │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ┌────────────────────────────────────────────────────────────────┐ │
│  │                     Transport Layer                             │ │
│  │  ┌──────────────────────┐    ┌──────────────────────┐          │ │
│  │  │   stdio Transport    │    │   HTTP/SSE Transport │          │ │
│  │  │  (Sidecar + CLI)     │    │  (Network Access)    │          │ │
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
│  │                       Data Layer                               │  │
│  │  ┌──────────────────┐  ┌──────────────────┐                   │  │
│  │  │  SQLite Database │  │ Encrypted Creds  │                   │  │
│  │  └──────────────────┘  └──────────────────┘                   │  │
│  └───────────────────────────────────────────────────────────────┘  │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

## Transport Layer

Both transports are first-class citizens—the server supports either based on configuration.

### stdio Transport

Used for sidecar mode (Tauri desktop app) and CLI integrations. The MCP protocol messages are exchanged via standard input/output streams.

```python
# src/server/main.py
import asyncio
from mcp.server import Server
from mcp.server.stdio import stdio_server

from .tools import register_tools
from .resources import register_resources
from .prompts import register_prompts
from ..services.database import DatabaseService
from ..services.tastytrade import TastyTradeService
from ..services.cache import CacheService

async def run_stdio():
    """Run the MCP server with stdio transport."""
    server = await create_server()

    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options()
        )
```

### HTTP/SSE Transport

Used for headless mode and network-accessible deployments. Enables external MCP clients (like Claude Desktop) to connect over HTTP.

```python
# src/server/main.py
from mcp.server.sse import SseServerTransport
from starlette.applications import Starlette
from starlette.routing import Route
import uvicorn

async def run_sse(host: str = "localhost", port: int = 5180):
    """Run the MCP server with HTTP/SSE transport."""
    server = await create_server()
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

    config = uvicorn.Config(app, host=host, port=port)
    server = uvicorn.Server(config)
    await server.serve()
```

### Transport Selection

Transport is selected via CLI arguments or environment variables:

```python
# src/server/main.py
import argparse
import os

async def main():
    """Main entry point with transport selection."""
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
    args = parser.parse_args()

    if args.transport == "stdio":
        await run_stdio()
    else:
        await run_sse(args.host, args.port)

if __name__ == "__main__":
    asyncio.run(main())
```

## Server Configuration

```python
# src/server/config.py
from dataclasses import dataclass, field
from pathlib import Path
import os

@dataclass
class ServerConfig:
    """Configuration for the MCP server."""

    # Data directory (platform-specific)
    data_dir: Path = field(default_factory=lambda: Path.home() / ".ttai")

    # Database path
    db_path: Path = None

    # Log level
    log_level: str = "INFO"

    # Transport settings
    transport: str = "stdio"  # "stdio" or "sse"
    host: str = "localhost"
    port: int = 5180

    # Cache settings
    quote_cache_ttl: int = 60  # seconds
    chain_cache_ttl: int = 300  # seconds

    # TastyTrade API
    tastytrade_api_url: str = "https://api.tastyworks.com"

    # Notification settings
    notification_backend: str = "auto"  # "auto", "tauri", "webhook"
    webhook_url: str | None = None

    def __post_init__(self):
        # Ensure data directory exists
        self.data_dir.mkdir(parents=True, exist_ok=True)

        # Set database path
        if self.db_path is None:
            self.db_path = self.data_dir / "ttai.db"

        # Create subdirectories
        (self.data_dir / "knowledge").mkdir(exist_ok=True)
        (self.data_dir / "exports").mkdir(exist_ok=True)
        (self.data_dir / "logs").mkdir(exist_ok=True)

        # Auto-detect notification backend
        if self.notification_backend == "auto":
            self.notification_backend = "tauri" if self.transport == "stdio" else "webhook"

    @classmethod
    def from_env(cls) -> "ServerConfig":
        """Create config from environment variables."""
        return cls(
            data_dir=Path(os.getenv("TTAI_DATA_DIR", str(Path.home() / ".ttai"))),
            log_level=os.getenv("TTAI_LOG_LEVEL", "INFO"),
            transport=os.getenv("TTAI_TRANSPORT", "stdio"),
            host=os.getenv("TTAI_HOST", "localhost"),
            port=int(os.getenv("TTAI_PORT", "5180")),
            tastytrade_api_url=os.getenv("TASTYTRADE_API_URL", "https://api.tastyworks.com"),
            notification_backend=os.getenv("TTAI_NOTIFICATION_BACKEND", "auto"),
            webhook_url=os.getenv("TTAI_WEBHOOK_URL"),
        )

# Global configuration instance
config = ServerConfig.from_env()
```

## TastyTrade Authentication

### Local Credential Storage

User credentials are stored locally with encryption using Fernet symmetric encryption. No cloud storage is used.

```python
# src/auth/credentials.py
from cryptography.fernet import Fernet
from pathlib import Path
import json
import os

class CredentialManager:
    """Manages encrypted credential storage."""

    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.key_file = data_dir / ".key"
        self.creds_file = data_dir / ".credentials"
        self._fernet = None

    @property
    def fernet(self) -> Fernet:
        """Get or create the Fernet instance."""
        if self._fernet is None:
            self._fernet = Fernet(self._get_or_create_key())
        return self._fernet

    def _get_or_create_key(self) -> bytes:
        """Get existing key or create a new one."""
        if self.key_file.exists():
            return self.key_file.read_bytes()

        key = Fernet.generate_key()
        self.key_file.write_bytes(key)
        # Restrict permissions (Unix only)
        if os.name != 'nt':
            os.chmod(self.key_file, 0o600)
        return key

    def store_credentials(
        self,
        username: str,
        session_token: str,
        remember_token: str | None = None
    ) -> None:
        """Store encrypted credentials."""
        data = {
            "username": username,
            "session_token": session_token,
            "remember_token": remember_token,
        }
        encrypted = self.fernet.encrypt(json.dumps(data).encode())
        self.creds_file.write_bytes(encrypted)

        if os.name != 'nt':
            os.chmod(self.creds_file, 0o600)

    def load_credentials(self) -> dict | None:
        """Load and decrypt credentials."""
        if not self.creds_file.exists():
            return None

        try:
            encrypted = self.creds_file.read_bytes()
            decrypted = self.fernet.decrypt(encrypted)
            return json.loads(decrypted.decode())
        except Exception:
            return None

    def clear_credentials(self) -> None:
        """Remove stored credentials."""
        if self.creds_file.exists():
            self.creds_file.unlink()
```

### TastyTrade Session Management

```python
# src/auth/tastytrade.py
from tastytrade import Session
from tastytrade.account import Account
from typing import Optional
import asyncio

class TastyTradeAuth:
    """Handles TastyTrade authentication."""

    def __init__(self, credential_manager: CredentialManager):
        self.creds = credential_manager
        self._session: Optional[Session] = None
        self._accounts: list[Account] = []

    @property
    def is_authenticated(self) -> bool:
        """Check if we have a valid session."""
        return self._session is not None and self._session.is_valid

    async def login(self, username: str, password: str, remember_me: bool = False) -> bool:
        """
        Authenticate with TastyTrade.

        Args:
            username: TastyTrade username or email
            password: TastyTrade password
            remember_me: Store credentials for auto-login

        Returns:
            True if authentication successful
        """
        try:
            # Create session using official tastytrade package
            self._session = Session(username, password, remember_me=remember_me)

            # Fetch accounts
            self._accounts = Account.get_accounts(self._session)

            # Store credentials if remember_me
            if remember_me:
                self.creds.store_credentials(
                    username=username,
                    session_token=self._session.session_token,
                    remember_token=self._session.remember_token
                )

            return True

        except Exception as e:
            self._session = None
            self._accounts = []
            raise AuthenticationError(f"Login failed: {e}")

    async def restore_session(self) -> bool:
        """Attempt to restore session from stored credentials."""
        creds = self.creds.load_credentials()
        if not creds:
            return False

        try:
            # Restore session using remember token
            if creds.get("remember_token"):
                self._session = Session(
                    creds["username"],
                    remember_token=creds["remember_token"]
                )
            else:
                return False

            self._accounts = Account.get_accounts(self._session)
            return True

        except Exception:
            self.creds.clear_credentials()
            return False

    async def logout(self) -> None:
        """Log out and clear stored credentials."""
        if self._session:
            try:
                self._session.destroy()
            except Exception:
                pass

        self._session = None
        self._accounts = []
        self.creds.clear_credentials()

    @property
    def session(self) -> Session:
        """Get the current session."""
        if not self._session:
            raise AuthenticationError("Not authenticated")
        return self._session

    @property
    def accounts(self) -> list[Account]:
        """Get user's accounts."""
        return self._accounts

    @property
    def primary_account(self) -> Account:
        """Get the primary (first) account."""
        if not self._accounts:
            raise AuthenticationError("No accounts available")
        return self._accounts[0]


class AuthenticationError(Exception):
    """Raised when authentication fails."""
    pass
```

## MCP Server Implementation

### Tool Registration with Decorators

```python
# src/server/tools.py
from mcp.server import Server
from mcp.types import Tool, TextContent
from pydantic import BaseModel, Field
from typing import Any

def register_tools(
    server: Server,
    db: "DatabaseService",
    tastytrade: "TastyTradeService",
    cache: "CacheService"
) -> None:
    """Register all MCP tools."""

    # Tool input schemas using Pydantic
    class GetQuoteInput(BaseModel):
        symbol: str = Field(description="Stock or ETF symbol")

    class GetOptionChainInput(BaseModel):
        symbol: str = Field(description="Underlying symbol")
        expiration: str | None = Field(
            default=None,
            description="Expiration date (YYYY-MM-DD) or None for all"
        )

    class AnalyzeChartInput(BaseModel):
        symbol: str = Field(description="Symbol to analyze")
        timeframe: str = Field(
            default="daily",
            description="Timeframe: intraday, daily, weekly"
        )

    class RunFullAnalysisInput(BaseModel):
        symbol: str = Field(description="Symbol to analyze")
        strategy: str = Field(
            default="csp",
            description="Strategy: csp, covered_call, spread"
        )

    # Register tools
    @server.tool()
    async def get_quote(symbol: str) -> list[TextContent]:
        """Get real-time quote for a symbol."""
        quote = await tastytrade.get_quote(symbol)
        return [TextContent(
            type="text",
            text=json.dumps(quote, indent=2)
        )]

    @server.tool()
    async def get_option_chain(
        symbol: str,
        expiration: str | None = None
    ) -> list[TextContent]:
        """Get option chain for a symbol."""
        chain = await tastytrade.get_option_chain(symbol, expiration)
        return [TextContent(
            type="text",
            text=json.dumps(chain, indent=2)
        )]

    @server.tool()
    async def get_positions() -> list[TextContent]:
        """Get current portfolio positions."""
        positions = await tastytrade.get_positions()
        return [TextContent(
            type="text",
            text=json.dumps(positions, indent=2)
        )]

    @server.tool()
    async def analyze_chart(
        symbol: str,
        timeframe: str = "daily"
    ) -> list[TextContent]:
        """Run AI-powered chart analysis on a symbol."""
        from ..agents.chart_analyst import ChartAnalyst

        agent = ChartAnalyst(tastytrade, cache)
        result = await agent.analyze(symbol, timeframe)

        return [TextContent(
            type="text",
            text=json.dumps(result, indent=2)
        )]

    @server.tool()
    async def analyze_options(
        symbol: str,
        strategy: str = "csp",
        chart_context: dict | None = None
    ) -> list[TextContent]:
        """Run options analysis for a symbol."""
        from ..agents.options_analyst import OptionsAnalyst

        agent = OptionsAnalyst(tastytrade, cache)
        result = await agent.analyze(symbol, strategy, chart_context)

        return [TextContent(
            type="text",
            text=json.dumps(result, indent=2)
        )]

    @server.tool()
    async def run_full_analysis(
        symbol: str,
        strategy: str = "csp"
    ) -> list[TextContent]:
        """Run comprehensive analysis including chart, options, and research."""
        from ..agents.orchestrator import AnalysisOrchestrator

        orchestrator = AnalysisOrchestrator(tastytrade, cache, db)
        result = await orchestrator.run_full_analysis(symbol, strategy)

        # Save to database
        await db.save_analysis(symbol, "full", result)

        return [TextContent(
            type="text",
            text=json.dumps(result, indent=2)
        )]

    @server.tool()
    async def search_knowledge(
        query: str,
        limit: int = 5
    ) -> list[TextContent]:
        """Search the knowledge base for relevant information."""
        from ..services.knowledge import KnowledgeService

        knowledge = KnowledgeService(db)
        results = await knowledge.search(query, limit)

        return [TextContent(
            type="text",
            text=json.dumps(results, indent=2)
        )]

    @server.tool()
    async def set_price_alert(
        symbol: str,
        condition: str,
        threshold: float
    ) -> list[TextContent]:
        """Set a price alert for a symbol."""
        alert_id = await db.create_alert(
            symbol=symbol,
            alert_type="price",
            condition=condition,  # "above" or "below"
            threshold=threshold
        )

        return [TextContent(
            type="text",
            text=f"Alert created with ID: {alert_id}"
        )]
```

### Resource Registration

```python
# src/server/resources.py
from mcp.server import Server
from mcp.types import Resource, TextResourceContents
import json

def register_resources(
    server: Server,
    db: "DatabaseService",
    tastytrade: "TastyTradeService"
) -> None:
    """Register all MCP resources."""

    @server.resource("portfolio://positions")
    async def get_positions_resource() -> str:
        """Current portfolio positions."""
        positions = await tastytrade.get_positions()
        return json.dumps(positions, indent=2)

    @server.resource("portfolio://balances")
    async def get_balances_resource() -> str:
        """Account balances and buying power."""
        balances = await tastytrade.get_balances()
        return json.dumps(balances, indent=2)

    @server.resource("history://analyses")
    async def get_analyses_resource() -> str:
        """Recent analysis results."""
        analyses = await db.get_recent_analyses(limit=20)
        return json.dumps(analyses, indent=2)

    @server.resource("history://analyses/{symbol}")
    async def get_symbol_analyses_resource(symbol: str) -> str:
        """Analysis history for a specific symbol."""
        analyses = await db.get_analyses_by_symbol(symbol)
        return json.dumps(analyses, indent=2)

    @server.resource("alerts://active")
    async def get_active_alerts_resource() -> str:
        """Active price and position alerts."""
        alerts = await db.get_active_alerts()
        return json.dumps(alerts, indent=2)

    @server.resource("knowledge://options/strategies/{strategy}")
    async def get_strategy_resource(strategy: str) -> str:
        """Options strategy documentation."""
        from ..services.knowledge import KnowledgeService

        knowledge = KnowledgeService(db)
        doc = await knowledge.get_document(f"options/strategies/{strategy}.md")
        return doc or f"Strategy not found: {strategy}"

    # List available resources
    @server.list_resources()
    async def list_resources() -> list[Resource]:
        """List all available resources."""
        return [
            Resource(
                uri="portfolio://positions",
                name="Portfolio Positions",
                description="Current open positions",
                mimeType="application/json"
            ),
            Resource(
                uri="portfolio://balances",
                name="Account Balances",
                description="Account balances and buying power",
                mimeType="application/json"
            ),
            Resource(
                uri="history://analyses",
                name="Analysis History",
                description="Recent analysis results",
                mimeType="application/json"
            ),
            Resource(
                uri="alerts://active",
                name="Active Alerts",
                description="Active price and position alerts",
                mimeType="application/json"
            ),
        ]
```

### Prompt Registration

```python
# src/server/prompts.py
from mcp.server import Server
from mcp.types import Prompt, PromptArgument, PromptMessage, TextContent

def register_prompts(server: Server) -> None:
    """Register all MCP prompts."""

    @server.prompt("analyze-for-csp")
    async def analyze_for_csp_prompt(symbol: str) -> list[PromptMessage]:
        """Prompt for analyzing a symbol for cash-secured put opportunities."""
        return [
            PromptMessage(
                role="user",
                content=TextContent(
                    type="text",
                    text=f"""Analyze {symbol} for a cash-secured put opportunity.

Please:
1. Use the analyze_chart tool to get technical analysis
2. Use the analyze_options tool with strategy="csp" to find optimal strikes
3. Check current positions with get_positions
4. Provide a recommendation with specific strike and expiration

Consider:
- Current trend and support levels
- IV rank and premium available
- Risk/reward profile
- Position sizing relative to portfolio"""
                )
            )
        ]

    @server.prompt("morning-briefing")
    async def morning_briefing_prompt() -> list[PromptMessage]:
        """Prompt for generating a morning market briefing."""
        return [
            PromptMessage(
                role="user",
                content=TextContent(
                    type="text",
                    text="""Generate a morning briefing for my portfolio.

Please:
1. Get current positions with get_positions
2. Get quotes for each position
3. Check for any positions approaching expiration (< 7 DTE)
4. Identify any positions with significant P&L changes
5. Suggest any adjustments or new opportunities

Format as a concise briefing I can review quickly."""
                )
            )
        ]

    @server.prompt("position-review")
    async def position_review_prompt(symbol: str) -> list[PromptMessage]:
        """Prompt for reviewing a specific position."""
        return [
            PromptMessage(
                role="user",
                content=TextContent(
                    type="text",
                    text=f"""Review my position in {symbol}.

Please:
1. Get current quote and position details
2. Analyze current chart setup
3. Evaluate if position should be:
   - Held to expiration
   - Rolled to new strike/expiration
   - Closed for profit/loss
4. Provide specific recommendations"""
                )
            )
        ]

    # List available prompts
    @server.list_prompts()
    async def list_prompts() -> list[Prompt]:
        """List all available prompts."""
        return [
            Prompt(
                name="analyze-for-csp",
                description="Analyze a symbol for cash-secured put opportunities",
                arguments=[
                    PromptArgument(
                        name="symbol",
                        description="Stock symbol to analyze",
                        required=True
                    )
                ]
            ),
            Prompt(
                name="morning-briefing",
                description="Generate a morning market briefing",
                arguments=[]
            ),
            Prompt(
                name="position-review",
                description="Review a specific position",
                arguments=[
                    PromptArgument(
                        name="symbol",
                        description="Symbol of position to review",
                        required=True
                    )
                ]
            ),
        ]
```

## Error Handling

### Error Types

```python
# src/server/errors.py
from enum import Enum
from typing import Any

class ErrorCode(str, Enum):
    """Standard error codes."""
    AUTHENTICATION_ERROR = "AUTHENTICATION_ERROR"
    AUTHORIZATION_ERROR = "AUTHORIZATION_ERROR"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    NOT_FOUND = "NOT_FOUND"
    RATE_LIMIT = "RATE_LIMIT"
    TASTYTRADE_ERROR = "TASTYTRADE_ERROR"
    ANALYSIS_ERROR = "ANALYSIS_ERROR"
    DATABASE_ERROR = "DATABASE_ERROR"
    INTERNAL_ERROR = "INTERNAL_ERROR"

class TTAIError(Exception):
    """Base error class for TTAI."""

    def __init__(
        self,
        message: str,
        code: ErrorCode = ErrorCode.INTERNAL_ERROR,
        retryable: bool = False,
        details: dict[str, Any] | None = None
    ):
        super().__init__(message)
        self.code = code
        self.retryable = retryable
        self.details = details or {}

    def to_dict(self) -> dict:
        return {
            "error": {
                "code": self.code.value,
                "message": str(self),
                "retryable": self.retryable,
                "details": self.details
            }
        }

class AuthenticationError(TTAIError):
    def __init__(self, message: str = "Authentication required"):
        super().__init__(message, ErrorCode.AUTHENTICATION_ERROR, False)

class ValidationError(TTAIError):
    def __init__(self, message: str, details: dict | None = None):
        super().__init__(message, ErrorCode.VALIDATION_ERROR, False, details)

class TastyTradeError(TTAIError):
    def __init__(self, message: str, retryable: bool = True):
        super().__init__(message, ErrorCode.TASTYTRADE_ERROR, retryable)

class RateLimitError(TTAIError):
    def __init__(self, retry_after: int = 60):
        super().__init__(
            f"Rate limited. Retry after {retry_after}s",
            ErrorCode.RATE_LIMIT,
            True,
            {"retry_after": retry_after}
        )
```

### Error Handling Middleware

```python
# src/server/middleware.py
import logging
import traceback
from functools import wraps
from typing import Callable, TypeVar, ParamSpec

from .errors import TTAIError, ErrorCode

logger = logging.getLogger(__name__)

P = ParamSpec('P')
T = TypeVar('T')

def handle_errors(func: Callable[P, T]) -> Callable[P, T]:
    """Decorator to handle errors in tool handlers."""
    @wraps(func)
    async def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
        try:
            return await func(*args, **kwargs)
        except TTAIError:
            # Re-raise known errors
            raise
        except Exception as e:
            # Log unexpected errors
            logger.error(f"Unexpected error in {func.__name__}: {e}")
            logger.error(traceback.format_exc())

            # Wrap in TTAIError
            raise TTAIError(
                f"Internal error: {e}",
                ErrorCode.INTERNAL_ERROR,
                retryable=True
            )

    return wrapper
```

## Notification System

See [Background Tasks](./06-background-tasks.md) for the complete notification system implementation, which supports both Tauri (stderr) and webhook notification backends.

```python
# src/server/notifications.py (summary)
from abc import ABC, abstractmethod

class NotificationBackend(ABC):
    @abstractmethod
    async def send(self, notification: Notification) -> None: ...

class TauriNotifier(NotificationBackend):
    """Emits to stderr for Tauri to capture (sidecar mode)."""
    ...

class WebhookNotifier(NotificationBackend):
    """POSTs to configured webhook URLs (headless mode)."""
    ...
```

## Cross-References

- [Workflow Orchestration](./02-workflow-orchestration.md) - Python asyncio task orchestration
- [Python Server](./03-python-server.md) - Server architecture, running modes, and project structure
- [Data Layer](./05-data-layer.md) - SQLite database and credential storage
- [Background Tasks](./06-background-tasks.md) - Notification system with Tauri and webhook backends
- [Integration Patterns](./09-integration-patterns.md) - Tauri ↔ Python and HTTP/SSE communication
- [Local Development](./10-local-development.md) - Running in sidecar and headless modes
