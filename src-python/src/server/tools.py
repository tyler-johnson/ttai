"""MCP tool registration for TTAI server."""

import logging

from mcp.server import Server
from mcp.types import TextContent, Tool

logger = logging.getLogger("ttai.tools")


def register_tools(server: Server) -> None:
    """Register all MCP tools with the server.

    Args:
        server: The MCP server instance to register tools with
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

        raise ValueError(f"Unknown tool: {name}")
