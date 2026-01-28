# TTAI - TastyTrade AI Assistant

MCP (Model Context Protocol) server for TastyTrade API integration, running on Cloudflare Workers.

## Architecture Overview

```
Client (Claude) → MCP Server (TypeScript) → Python Worker → TastyTrade API
```

- **MCP Server** (`workers/mcp-server/`): TypeScript Cloudflare Worker handling MCP protocol
- **Python Worker** (`workers/python-worker/`): Python Cloudflare Worker calling TastyTrade REST API
- **Service Binding**: Workers communicate via Cloudflare service bindings (no HTTP overhead in production)
- **Shared Storage**: Both workers access the same D1 database, KV namespace, and R2 bucket

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
│   │   ├── src/
│   │   │   ├── index.ts      # Entry point, MCP tool registration
│   │   │   └── auth/         # Authentication module
│   │   │       ├── oauth.ts      # OAuth handlers
│   │   │       ├── jwt.ts        # JWT utilities
│   │   │       ├── encryption.ts # Token encryption
│   │   │       └── middleware.ts # Auth middleware
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
├── migrations/               # D1 database migrations (shared)
│   └── 0001_initial_schema.sql
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

## Authentication

### Per-User OAuth (Recommended)

Users authenticate with their own TastyTrade credentials via browser-based OAuth:

```
User → /oauth/authorize → TastyTrade Login → /oauth/callback → JWT Session
```

**Flow:**
1. Client visits `/.well-known/oauth-authorization-server` for discovery
2. Client redirects to `/oauth/authorize?redirect_uri=...`
3. User logs in at TastyTrade
4. TastyTrade redirects to `/oauth/callback` with auth code
5. Server exchanges code for tokens, stores encrypted in D1
6. Server returns JWT session token to client

**Required secrets for per-user auth:**
```bash
TT_CLIENT_ID=your-tastytrade-app-client-id
TT_CLIENT_SECRET=your-tastytrade-app-client-secret
JWT_SECRET=your-jwt-signing-secret-32-chars-min
TOKEN_ENCRYPTION_KEY=base64-encoded-32-byte-key
```

### Legacy Authentication

For backward compatibility, shared credentials can still be used:

```bash
TT_CLIENT_SECRET=your-client-secret
TT_REFRESH_TOKEN=your-refresh-token
```

### Database Setup

Create D1 database:

```bash
# Create database (production)
wrangler d1 create ttai

# Update BOTH wrangler.toml files with database_id:
# - workers/mcp-server/wrangler.toml
# - workers/python-worker/wrangler.toml

# Run migrations (local) - done automatically by Tilt
wrangler d1 migrations apply ttai --local -c workers/mcp-server/wrangler.toml

# Run migrations (production)
wrangler d1 migrations apply ttai -c workers/mcp-server/wrangler.toml
```

### Creating New Migrations

```bash
# Create a new migration file
wrangler d1 migrations create ttai add_new_feature -c workers/mcp-server/wrangler.toml

# Edit the generated file in migrations/

# Apply locally
wrangler d1 migrations apply ttai --local -c workers/mcp-server/wrangler.toml
```

## Storage

Both workers share access to the same storage resources:

| Binding | Service | Purpose |
|---------|---------|---------|
| `DB` | D1 (SQLite) | Users, tokens, positions, analysis history, alerts |
| `KV` | KV Namespace | Quote cache (30-60s), chain cache (5-15m), session cache |
| `R2` | R2 Bucket | Knowledge base docs, user exports |

### KV Key Patterns

- Global: `quote:{symbol}`, `chain:{symbol}:{expiration}`
- User-scoped: `user:{user_id}:analysis:{symbol}`, `user:{user_id}:session`

### R2 Path Patterns

- Shared: `knowledge/options/strategies.md`, `knowledge/trading/risk.md`
- User-isolated: `users/{user_id}/exports/report.pdf`

## TastyTrade API

### Endpoints Used

- `/oauth/authorize` - Start OAuth flow
- `/oauth/token` - Token exchange and refresh
- `/customers/me` - Get user info
- `/market-data/by-type` - Bid/ask/last prices
- `/market-metrics` - IV rank, beta, earnings dates

### Pyodide Limitations

The `tastytrade` Python package uses WebSocket streaming which isn't supported in Cloudflare Python Workers. Instead, we use raw `httpx` calls to REST endpoints.

## Endpoints

| Path | Method | Description |
|------|--------|-------------|
| `/` | POST | MCP protocol (tools/call, etc.) - requires auth |
| `/health` | GET | Health check |
| `/debug/python-worker` | GET | Test Python worker connection |
| `/.well-known/oauth-authorization-server` | GET | OAuth discovery metadata (RFC 8414) |
| `/oauth/authorize` | GET | Start OAuth flow |
| `/oauth/callback` | GET | OAuth callback from TastyTrade |
| `/oauth/token` | POST | Token endpoint |
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

### "Authentication required"

Per-user auth is enabled. Either:
1. Complete OAuth flow via `/oauth/authorize`
2. Or for development, remove `JWT_SECRET` from `.dev.vars` to use legacy auth

### "Credentials not configured"

Check that `.dev.vars` exists and has valid credentials:
- For per-user auth: `TT_CLIENT_ID`, `TT_CLIENT_SECRET`, `JWT_SECRET`, `TOKEN_ENCRYPTION_KEY`
- For legacy auth: `TT_CLIENT_SECRET`, `TT_REFRESH_TOKEN`

### Service binding errors

Use Tilt or multi-config wrangler mode to run workers together.

### Python import errors

Use `from workers import Response` (not `from js import Response`) in Python workers.
