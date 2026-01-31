# TTAI Python (Reference Implementation)

Python implementation of the TTAI MCP server. This serves as a reference for the TastyTrade API integration - the primary implementation is the [Go version](../src-go/).

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
ttai-server --headless --port 5180

# Stdio mode (for subprocess/sidecar integration)
ttai-server --headless --transport stdio
```

## Environment Variables

- `TTAI_TRANSPORT`: "stdio" or "http" (default: http)
- `TTAI_HOST`: Server host (default: localhost)
- `TTAI_PORT`: Server port (default: 5180)
- `TTAI_LOG_LEVEL`: Log level (default: INFO)
- `TTAI_DATA_DIR`: Data directory (default: ~/.ttai)
