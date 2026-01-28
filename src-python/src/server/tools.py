"""MCP tool registration for TTAI server."""

import json
import logging

from mcp.server import Server
from mcp.types import TextContent, Tool

from src.services.tastytrade import TastyTradeService

logger = logging.getLogger("ttai.tools")


def register_tools(server: Server, tastytrade_service: TastyTradeService) -> None:
    """Register all MCP tools with the server.

    Args:
        server: The MCP server instance to register tools with
        tastytrade_service: TastyTrade service for API operations
    """

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        """List all available tools."""
        return [
            Tool(
                name="ping",
                description="Simple ping tool to verify server connectivity",
                inputSchema={
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
            ),
            Tool(
                name="login",
                description="Authenticate with TastyTrade",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "username": {
                            "type": "string",
                            "description": "TastyTrade username",
                        },
                        "password": {
                            "type": "string",
                            "description": "TastyTrade password",
                        },
                        "remember_me": {
                            "type": "boolean",
                            "description": "Store credentials for automatic session restore",
                            "default": False,
                        },
                    },
                    "required": ["username", "password"],
                },
            ),
            Tool(
                name="logout",
                description="Log out from TastyTrade and clear stored credentials",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "clear_credentials": {
                            "type": "boolean",
                            "description": "Whether to remove stored credentials",
                            "default": True,
                        },
                    },
                    "required": [],
                },
            ),
            Tool(
                name="get_auth_status",
                description="Check current TastyTrade authentication status",
                inputSchema={
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
            ),
            Tool(
                name="get_quote",
                description="Get current quote (bid/ask/last) for a symbol",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "symbol": {
                            "type": "string",
                            "description": "Ticker symbol (e.g., AAPL, SPY)",
                        },
                    },
                    "required": ["symbol"],
                },
            ),
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict) -> list[TextContent]:
        """Handle tool calls.

        Args:
            name: Name of the tool to call
            arguments: Arguments passed to the tool

        Returns:
            List of content items with the tool result
        """
        logger.debug(f"Tool call: {name} with arguments: {arguments}")

        if name == "ping":
            return [TextContent(type="text", text="pong")]

        if name == "login":
            username = arguments["username"]
            password = arguments["password"]
            remember_me = arguments.get("remember_me", False)

            success = await tastytrade_service.login(username, password, remember_me)

            if success:
                result = {"success": True, "message": f"Logged in as {username}"}
            else:
                result = {"success": False, "message": "Login failed. Check credentials."}

            return [TextContent(type="text", text=json.dumps(result))]

        if name == "logout":
            clear_credentials = arguments.get("clear_credentials", True)
            await tastytrade_service.logout(clear_credentials)
            result = {"success": True, "message": "Logged out successfully"}
            return [TextContent(type="text", text=json.dumps(result))]

        if name == "get_auth_status":
            status = tastytrade_service.get_auth_status()
            return [TextContent(type="text", text=json.dumps(status))]

        if name == "get_quote":
            symbol = arguments["symbol"]

            if not tastytrade_service.is_authenticated:
                result = {"error": "Not authenticated. Please login first."}
                return [TextContent(type="text", text=json.dumps(result))]

            quote = await tastytrade_service.get_quote(symbol)

            if quote is None:
                result = {"error": f"Failed to get quote for {symbol}"}
            else:
                result = {
                    "symbol": quote.symbol,
                    "bid": quote.bid,
                    "ask": quote.ask,
                    "last": quote.last,
                }

            return [TextContent(type="text", text=json.dumps(result))]

        raise ValueError(f"Unknown tool: {name}")
