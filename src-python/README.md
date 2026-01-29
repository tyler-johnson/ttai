# TTAI

TastyTrade AI - Desktop app and MCP server for TastyTrade trading assistant.

## Installation

```bash
pip install -e ".[dev]"
```

## Usage

### GUI Mode (default)

Double-click the app or run without arguments:

```bash
ttai-server
```

### Headless MCP Server

For Claude Desktop or other MCP clients:

```bash
# HTTP mode (default transport)
ttai-server --headless --port 8080

# Stdio mode (for subprocess/sidecar integration)
ttai-server --headless --transport stdio
```

## Environment Variables

- `TTAI_TRANSPORT`: "stdio" or "http" (default: http)
- `TTAI_HOST`: Server host (default: localhost)
- `TTAI_PORT`: Server port (default: 8080)
- `TTAI_LOG_LEVEL`: Log level (default: INFO)
- `TTAI_DATA_DIR`: Data directory (default: ~/.ttai)
