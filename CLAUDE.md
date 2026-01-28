# TTAI - TastyTrade AI Assistant

MCP (Model Context Protocol) server for TastyTrade API integration, running on Cloudflare Workers.

## Architecture Overview

```
Client (Claude) → MCP Server (TypeScript) → Python Worker → TastyTrade API
```

- **MCP Server** (`workers/mcp-server/`): TypeScript Cloudflare Worker handling MCP protocol
- **Python Worker** (`workers/python-worker/`): Python Cloudflare Worker calling TastyTrade REST API
- **Service Binding**: Workers communicate via Cloudflare service bindings (no HTTP overhead in production)

## Quick Start

```bash
# 1. Configure credentials
cp .dev.vars.example .dev.vars
# Edit .dev.vars with your TastyTrade OAuth credentials

# 2. Start local development
tilt up

# 3. Open Tilt UI
# http://localhost:10350

# 4. Test MCP endpoint
curl http://localhost:8787/health

# 5. Test with MCP Inspector
# http://localhost:6274
```

## Project Structure

```
ttai/
├── workers/
│   ├── mcp-server/           # TypeScript MCP server
│   │   ├── src/index.ts      # Entry point, MCP tool registration
│   │   └── wrangler.toml     # Cloudflare Worker config
│   │
│   └── python-worker/        # Python worker for TastyTrade API
│       ├── src/
│       │   ├── main.py       # Entry point with routing
│       │   └── tastytrade/
│       │       ├── auth.py   # OAuth token refresh
│       │       └── client.py # TastyTrade HTTP client
│       ├── cf-requirements.txt
│       └── wrangler.toml
│
├── docs/architecture/        # Detailed architecture documentation
├── Tiltfile                  # Local development orchestration
├── .dev.vars                 # Local secrets (gitignored)
└── .dev.vars.example         # Example secrets template
```

## MCP Tools

### get_quote

Get stock quote with bid/ask/last prices and market metrics (IV rank, beta, etc.).

```json
{
  "name": "get_quote",
  "arguments": { "symbol": "AAPL" }
}
```

**Response fields:**
- `bid`, `ask`, `last`, `mid`, `mark` - Price data
- `volume`, `open`, `high`, `low`, `close`, `prev_close` - Trading data
- `iv_rank`, `iv_percentile`, `iv_30_day`, `hv_30_day` - Volatility metrics
- `beta`, `market_cap`, `earnings_date` - Market metrics

## Local Development

### Using Tilt (Recommended)

Tilt runs both workers together with service bindings working natively:

```bash
tilt up
```

Resources:
- **workers**: MCP server + Python worker at http://localhost:8787
- **mcp-inspector**: Testing UI at http://localhost:6274

### Manual Wrangler

Run workers together with multi-config mode:

```bash
npx wrangler dev -c workers/mcp-server/wrangler.toml -c workers/python-worker/wrangler.toml --port 8787
```

### Credentials

Create `.dev.vars` in project root:

```bash
TT_CLIENT_SECRET=your-client-secret
TT_REFRESH_TOKEN=your-refresh-token
```

Symlinks in each worker directory point to the root `.dev.vars`.

## TastyTrade API

### Authentication

Uses OAuth with client_secret + refresh_token:
- **Endpoint**: `POST https://api.tastyworks.com/oauth/token`
- **Grant type**: `refresh_token`
- **Access tokens**: Expire in 900 seconds (15 minutes)

### Endpoints Used

- `/oauth/token` - Token refresh
- `/market-data/by-type` - Bid/ask/last prices
- `/market-metrics` - IV rank, beta, earnings dates

### Pyodide Limitations

The `tastytrade` Python package uses WebSocket streaming which isn't supported in Cloudflare Python Workers. Instead, we use raw `httpx` calls to REST endpoints.

## Endpoints

| Path | Method | Description |
|------|--------|-------------|
| `/` | POST | MCP protocol (tools/call, etc.) |
| `/health` | GET | Health check |
| `/debug/python-worker` | GET | Test Python worker connection |
| HEAD | HEAD | Returns MCP-Protocol-Version header |

## Architecture Documentation

Detailed architecture docs are in `docs/architecture/`:

| Doc | Description |
|-----|-------------|
| **01-mcp-server-design.md** | MCP server implementation, Streamable HTTP transport, TastyTrade OAuth flow, tool/resource/prompt registration |
| **02-workflow-orchestration.md** | Cloudflare Workflows for durable execution |
| **03-python-workers.md** | Python Workers with Pyodide, TastyTrade HTTP client, pandas/numpy analysis |
| **04-ai-agent-system.md** | AI agent architecture and LLM integration |
| **05-data-layer.md** | KV caching, D1 database, R2 storage patterns |
| **06-background-tasks.md** | Queues and async task processing |
| **07-knowledge-base.md** | Knowledge storage and retrieval |
| **08-infrastructure.md** | Production deployment and configuration |
| **09-integration-patterns.md** | Worker-to-worker communication, service bindings |
| **10-local-development.md** | Wrangler dev setup, Miniflare, D1/KV/R2 local simulation |

## Testing

### MCP Inspector

Start via Tilt or manually:

```bash
npx @modelcontextprotocol/inspector --transport http --server-url http://localhost:8787/
```

### curl

```bash
# Health check
curl http://localhost:8787/health

# Call get_quote tool
curl -X POST http://localhost:8787/ \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "tools/call",
    "params": {
      "name": "get_quote",
      "arguments": { "symbol": "AAPL" }
    }
  }'
```

## Claude Integration

### Claude.ai (Web)

Settings → Integrations → Add URL:
```
https://your-deployed-url.workers.dev/
```

### Claude Desktop

Requires `mcp-remote` for HTTP MCP servers:

```json
{
  "mcpServers": {
    "ttai": {
      "command": "npx",
      "args": ["mcp-remote", "http://localhost:8787/"]
    }
  }
}
```

## Common Issues

### "Credentials not configured"

Check that `.dev.vars` exists and has valid `TT_CLIENT_SECRET` and `TT_REFRESH_TOKEN`.

### Service binding errors

Use Tilt or multi-config wrangler mode to run workers together.

### Python import errors

Use `from workers import Response` (not `from js import Response`) in Python workers.
