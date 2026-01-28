# TTAI Server

TastyTrade AI MCP Server - Model Context Protocol server for TastyTrade trading assistant.

## Installation

```bash
pip install -e ".[dev]"
```

## Usage

### SSE Mode (for HTTP clients)

```bash
ttai-server --transport sse --port 8080
```

### Stdio Mode (for sidecar/subprocess)

```bash
ttai-server --transport stdio
```

## Environment Variables

- `TTAI_TRANSPORT`: "stdio" or "sse" (default: stdio)
- `TTAI_HOST`: Server host (default: localhost)
- `TTAI_PORT`: Server port (default: 8080)
- `TTAI_LOG_LEVEL`: Log level (default: INFO)
- `TTAI_DATA_DIR`: Data directory (default: ~/.ttai)
