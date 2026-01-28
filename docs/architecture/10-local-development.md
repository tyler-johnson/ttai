# Local Development

## Overview

Local development uses `wrangler dev` to run Cloudflare Workers locally with full access to simulated KV, D1, R2, and Durable Objects. This provides a production-like development experience with hot-reload and integrated debugging.

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                    Local Development Environment                     │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │                      wrangler dev                             │   │
│  │  http://localhost:8787 (MCP Server)                           │   │
│  │  http://localhost:8788 (Python Worker)                        │   │
│  │  - Hot reload on file changes                                 │   │
│  │  - Local bindings simulation                                  │   │
│  │  - DevTools debugging                                         │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                              │                                       │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │                       Miniflare                               │   │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐        │   │
│  │  │   Local KV   │  │   Local D1   │  │  Local R2    │        │   │
│  │  │  (in-memory) │  │   (SQLite)   │  │ (filesystem) │        │   │
│  │  └──────────────┘  └──────────────┘  └──────────────┘        │   │
│  │                                                               │   │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐        │   │
│  │  │   Durable    │  │    Queues    │  │  Vectorize   │        │   │
│  │  │   Objects    │  │   (local)    │  │   (mock)     │        │   │
│  │  └──────────────┘  └──────────────┘  └──────────────┘        │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                                                                      │
│  External Services (dev mode):                                       │
│  - TastyTrade: Sandbox environment (OAuth + API)                    │
│  - LLM APIs: Real API keys                                          │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

## Prerequisites

### Install Required Tools

```bash
# Node.js (20+)
brew install node

# Wrangler (Cloudflare CLI)
npm install -g wrangler

# Python (3.12+ for Python Workers)
brew install python@3.12

# Optional: jq for JSON processing
brew install jq
```

### Authenticate with Cloudflare

```bash
# Login to Cloudflare (opens browser)
wrangler login

# Verify authentication
wrangler whoami
```

## Project Structure

```
ttai/
├── workers/
│   ├── mcp-server/              # TypeScript MCP server
│   │   ├── src/
│   │   │   ├── index.ts         # Worker entry point
│   │   │   ├── server/          # MCP implementation
│   │   │   ├── durableObjects/  # Durable Objects
│   │   │   └── workflows/       # Cloudflare Workflows
│   │   ├── wrangler.toml        # Worker configuration
│   │   ├── package.json
│   │   └── tsconfig.json
│   │
│   └── python-worker/           # Python worker
│       ├── src/
│       │   ├── main.py          # Worker entry point
│       │   ├── handlers/        # Request handlers
│       │   ├── agents/          # AI agents
│       │   └── tastytrade/      # TastyTrade client
│       ├── wrangler.toml        # Worker configuration
│       └── requirements.txt
│
├── migrations/                   # D1 migrations
│   └── *.sql
│
├── .dev.vars                     # Local secrets (gitignored)
├── .dev.vars.example             # Example secrets file
│
└── scripts/
    ├── dev.sh                    # Start development
    └── seed.sh                   # Seed local data
```

## Environment Setup

### Create Local Secrets File

```bash
# Copy example and fill in values
cp .dev.vars.example .dev.vars
```

```bash
# .dev.vars (gitignored)

# JWT signing key (generate with: openssl rand -hex 32)
JWT_SECRET=your-256-bit-hex-key

# TastyTrade OAuth (sandbox credentials)
TASTYTRADE_CLIENT_ID=your-sandbox-client-id
TASTYTRADE_CLIENT_SECRET=your-sandbox-secret

# LLM Provider API Keys (LiteLLM reads these automatically)
# Set the key(s) for the provider(s) you want to use:

# Anthropic (for anthropic/claude-* models)
ANTHROPIC_API_KEY=sk-ant-...

# OpenAI (for openai/gpt-* models)
# OPENAI_API_KEY=sk-...

# Google (for gemini/* models)
# GOOGLE_API_KEY=...

# AWS Bedrock (for bedrock/* models)
# AWS_ACCESS_KEY_ID=...
# AWS_SECRET_ACCESS_KEY=...
# AWS_REGION_NAME=us-east-1

# Encryption key for TastyTrade tokens (generate with: openssl rand -hex 32)
TOKEN_ENCRYPTION_KEY=your-256-bit-hex-key
```

### Create Local D1 Database

```bash
cd workers/mcp-server

# Create local D1 database
wrangler d1 create ttai-local --local

# Apply migrations locally
wrangler d1 migrations apply ttai --local
```

### Create Local KV Namespace

```bash
# KV is automatically created locally when you run wrangler dev
# No explicit creation needed for local development
```

## Running Locally

### Start MCP Server (TypeScript)

```bash
cd workers/mcp-server

# Start with hot reload
wrangler dev

# Output:
# ⎔ Starting local server...
# Ready on http://localhost:8787
```

### Start Python Worker

```bash
cd workers/python-worker

# Start Python worker
wrangler dev --port 8788

# Output:
# ⎔ Starting Python worker...
# Ready on http://localhost:8788
```

### Run Both Workers Concurrently

```bash
# scripts/dev.sh
#!/bin/bash

# Start both workers in parallel
(cd workers/mcp-server && wrangler dev) &
(cd workers/python-worker && wrangler dev --port 8788) &

# Wait for both
wait
```

```bash
# Make executable and run
chmod +x scripts/dev.sh
./scripts/dev.sh
```

## wrangler.toml for Development

### MCP Server Configuration

```toml
# workers/mcp-server/wrangler.toml
name = "ttai-mcp-server"
main = "src/index.ts"
compatibility_date = "2024-01-01"
compatibility_flags = ["nodejs_compat"]

# Local development settings
[dev]
port = 8787
local_protocol = "http"

# KV Namespaces
[[kv_namespaces]]
binding = "KV"
id = "abc123"  # Production ID
preview_id = "preview123"  # Preview/local ID

# D1 Database
[[d1_databases]]
binding = "DB"
database_name = "ttai"
database_id = "your-d1-id"

# For local development, wrangler creates a local SQLite file:
# .wrangler/state/v3/d1/ttai/db.sqlite

# R2 Bucket
[[r2_buckets]]
binding = "R2"
bucket_name = "ttai-storage"
preview_bucket_name = "ttai-storage-preview"

# Durable Objects
[[durable_objects.bindings]]
name = "SESSIONS"
class_name = "SessionDurableObject"

[[durable_objects.bindings]]
name = "PORTFOLIO_MONITOR"
class_name = "PortfolioMonitor"

[[migrations]]
tag = "v1"
new_classes = ["SessionDurableObject", "PortfolioMonitor"]

# Service Binding to Python Worker
[[services]]
binding = "PYTHON_WORKER"
service = "ttai-python-worker"

# Local development: service binding points to localhost
[env.dev.services]
binding = "PYTHON_WORKER"
service = "ttai-python-worker"
environment = "dev"

# Environment variables
[vars]
ENVIRONMENT = "development"
LOG_LEVEL = "debug"
```

### Python Worker Configuration

```toml
# workers/python-worker/wrangler.toml
name = "ttai-python-worker"
main = "src/main.py"
compatibility_date = "2024-01-01"

[dev]
port = 8788
local_protocol = "http"

# KV for caching
[[kv_namespaces]]
binding = "KV"
id = "abc123"

# D1 for database
[[d1_databases]]
binding = "DB"
database_name = "ttai"
database_id = "your-d1-id"

[vars]
ENVIRONMENT = "development"
DEFAULT_LLM_MODEL = "anthropic/claude-sonnet-4-20250514"
```

## Local D1 Database

### Viewing Local Data

```bash
cd workers/mcp-server

# Open SQLite shell
wrangler d1 execute ttai --local --command "SELECT * FROM users LIMIT 10;"

# Export to JSON
wrangler d1 execute ttai --local --command "SELECT * FROM positions;" --json

# Interactive SQL
sqlite3 .wrangler/state/v3/d1/ttai/db.sqlite
```

### Running Migrations

```bash
# Apply all pending migrations
wrangler d1 migrations apply ttai --local

# Create a new migration
wrangler d1 migrations create ttai add_new_table

# List migrations
wrangler d1 migrations list ttai --local
```

### Seeding Data

```bash
# scripts/seed.sh
#!/bin/bash

cd workers/mcp-server

# Seed test user (TastyTrade account ID as primary key)
wrangler d1 execute ttai --local --command "
INSERT INTO users (id, email, created_at, updated_at)
VALUES ('tt-account-123', 'test@example.com', unixepoch(), unixepoch());
"

# Seed test OAuth token (encrypted)
wrangler d1 execute ttai --local --command "
INSERT INTO user_oauth_tokens (user_id, provider, access_token, refresh_token, expires_at)
VALUES ('tt-account-123', 'tastytrade', 'encrypted_access', 'encrypted_refresh', unixepoch() + 3600);
"
```

## Local KV Cache

### Inspecting KV Data

```bash
# List keys (local)
wrangler kv:key list --binding KV --local

# Get a value
wrangler kv:key get --binding KV --local "quote:AAPL"

# Put a value
wrangler kv:key put --binding KV --local "test:key" "test value"

# Delete a key
wrangler kv:key delete --binding KV --local "test:key"
```

### KV Persistence Location

```
.wrangler/state/v3/kv/
└── KV/
    └── *.sqlite  # KV data stored in SQLite
```

## Local R2 Storage

### R2 File Location

```
.wrangler/state/v3/r2/
└── ttai-storage/
    └── ...  # Files stored on filesystem
```

### Testing R2 Operations

```bash
# Upload a test file
wrangler r2 object put ttai-storage/test/file.txt --file ./test.txt --local

# Download a file
wrangler r2 object get ttai-storage/test/file.txt --local

# List objects
wrangler r2 object list ttai-storage --local
```

## Local Durable Objects

### Durable Object State Location

```
.wrangler/state/v3/do/
└── SessionDurableObject/
    └── *.sqlite  # Each DO instance has its own SQLite file
```

### Debugging Durable Objects

```typescript
// Add debug endpoints in development
if (env.ENVIRONMENT === 'development') {
  // Debug endpoint to inspect DO state
  app.get('/debug/do/:name/:id', async (c) => {
    const id = c.env.SESSIONS.idFromName(c.req.param('id'));
    const stub = c.env.SESSIONS.get(id);
    const response = await stub.fetch(new Request('http://internal/debug'));
    return response;
  });
}
```

## Local Queues

### Queue Simulation

Queues in local development are simulated by Miniflare:

```typescript
// Queue messages are processed immediately in local dev
// To test queue behavior, add delay:
export default {
  async queue(batch: MessageBatch<unknown>, env: Env): Promise<void> {
    for (const message of batch.messages) {
      console.log('Processing message:', message.body);
      // Process message
      message.ack();
    }
  },
};
```

## Testing

### Unit Tests with Vitest

```typescript
// workers/mcp-server/src/__tests__/tools.test.ts
import { describe, it, expect, beforeAll } from 'vitest';
import { unstable_dev } from 'wrangler';
import type { UnstableDevWorker } from 'wrangler';

describe('MCP Tools', () => {
  let worker: UnstableDevWorker;

  beforeAll(async () => {
    worker = await unstable_dev('src/index.ts', {
      experimental: { disableExperimentalWarning: true },
    });
  });

  afterAll(async () => {
    await worker.stop();
  });

  it('should return health check', async () => {
    const response = await worker.fetch('/health');
    expect(response.status).toBe(200);

    const data = await response.json();
    expect(data.status).toBe('healthy');
  });

  it('should require authentication', async () => {
    const response = await worker.fetch('/mcp');
    expect(response.status).toBe(401);
  });
});
```

### Integration Tests with Miniflare

```typescript
// workers/mcp-server/src/__tests__/integration.test.ts
import { Miniflare } from 'miniflare';
import { describe, it, expect, beforeAll, afterAll } from 'vitest';

describe('Integration Tests', () => {
  let mf: Miniflare;

  beforeAll(async () => {
    mf = new Miniflare({
      modules: true,
      scriptPath: 'dist/index.js',
      kvNamespaces: ['KV'],
      d1Databases: ['DB'],
      durableObjects: {
        SESSIONS: 'SessionDurableObject',
      },
    });
  });

  afterAll(async () => {
    await mf.dispose();
  });

  it('should cache quote in KV', async () => {
    const kv = await mf.getKVNamespace('KV');

    // Simulate caching a quote
    await kv.put('quote:AAPL', JSON.stringify({
      symbol: 'AAPL',
      price: 150.00,
      timestamp: Date.now(),
    }), { expirationTtl: 5 });

    const cached = await kv.get('quote:AAPL', 'json');
    expect(cached.symbol).toBe('AAPL');
  });

  it('should store user in D1', async () => {
    const db = await mf.getD1Database('DB');

    await db.exec(`
      INSERT INTO users (id, email)
      VALUES ('tt-account-123', 'test@test.com')
    `);

    const result = await db.prepare(
      'SELECT * FROM users WHERE id = ?'
    ).bind('tt-account-123').first();

    expect(result.email).toBe('test@test.com');
  });
});
```

### Running Tests

```bash
cd workers/mcp-server

# Run all tests
npm test

# Run with coverage
npm test -- --coverage

# Run specific test file
npm test -- src/__tests__/tools.test.ts

# Watch mode
npm test -- --watch
```

### Python Worker Tests

```python
# workers/python-worker/tests/test_handlers.py
import pytest
from unittest.mock import MagicMock, AsyncMock

from src.handlers.quotes import handle_quote_request
from src.tastytrade.client import TastyTradeClient


@pytest.fixture
def mock_env():
    """Create mock Cloudflare environment."""
    env = MagicMock()
    env.KV = AsyncMock()
    env.DB = AsyncMock()
    return env


@pytest.mark.asyncio
async def test_quote_handler(mock_env):
    """Test quote handler returns formatted data."""
    # Mock KV cache miss
    mock_env.KV.get = AsyncMock(return_value=None)

    # Mock TastyTrade response
    mock_client = AsyncMock(spec=TastyTradeClient)
    mock_client.get_quote = AsyncMock(return_value={
        'symbol': 'AAPL',
        'last': 150.00,
        'bid': 149.95,
        'ask': 150.05,
    })

    result = await handle_quote_request(
        symbol='AAPL',
        env=mock_env,
        client=mock_client,
    )

    assert result['symbol'] == 'AAPL'
    assert result['price'] == 150.00
```

```bash
cd workers/python-worker

# Run Python tests
pytest

# With coverage
pytest --cov=src

# Verbose output
pytest -v
```

## Debugging

### Enable Debug Logging

```bash
# Set log level in .dev.vars
LOG_LEVEL=debug

# Or via command line
LOG_LEVEL=debug wrangler dev
```

### Chrome DevTools

```bash
# Start with inspector
wrangler dev --inspector-port 9229

# Open Chrome and navigate to:
# chrome://inspect
# Click "inspect" under Remote Target
```

### VS Code Debugging

```json
// .vscode/launch.json
{
  "version": "0.2.0",
  "configurations": [
    {
      "name": "Debug Worker",
      "type": "node",
      "request": "attach",
      "port": 9229,
      "cwd": "${workspaceFolder}/workers/mcp-server",
      "resolveSourceMapLocations": [
        "${workspaceFolder}/**",
        "!**/node_modules/**"
      ],
      "skipFiles": ["<node_internals>/**"]
    }
  ]
}
```

### Request Logging

```typescript
// Add request logging middleware
app.use('*', async (c, next) => {
  const start = Date.now();
  console.log(`→ ${c.req.method} ${c.req.url}`);

  await next();

  const duration = Date.now() - start;
  console.log(`← ${c.res.status} ${duration}ms`);
});
```

## Service-to-Service Communication

### Local Service Bindings

When both workers run locally, service bindings need manual configuration:

```typescript
// workers/mcp-server/src/services/python.ts
export async function callPythonWorker(
  env: Env,
  endpoint: string,
  body: unknown,
): Promise<Response> {
  // In development, use localhost
  if (env.ENVIRONMENT === 'development') {
    return fetch(`http://localhost:8788${endpoint}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
  }

  // In production, use service binding
  return env.PYTHON_WORKER.fetch(
    new Request(`https://internal${endpoint}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
  );
}
```

## Testing MCP Connection

### Test with curl

```bash
# Health check
curl http://localhost:8787/health

# MCP endpoint (requires session token from OAuth flow)
curl -X POST http://localhost:8787/mcp \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <session-token>" \
  -d '{"jsonrpc": "2.0", "method": "tools/list", "id": 1}'

# For local testing, generate a test JWT:
# node -e "const jose = require('jose'); (async () => { const secret = new TextEncoder().encode('your-jwt-secret'); const jwt = await new jose.SignJWT({ sub: 'tt-account-123', email: 'test@example.com' }).setProtectedHeader({ alg: 'HS256' }).setIssuedAt().setExpirationTime('24h').sign(secret); console.log(jwt); })()"
```

### Test with Claude Desktop

```json
// ~/.claude/claude_desktop_config.json
{
  "mcpServers": {
    "ttai-dev": {
      "command": "npx",
      "args": [
        "mcp-remote-client",
        "http://localhost:8787/mcp"
      ],
      "env": {
        "SESSION_TOKEN": "your-session-jwt-token"
      }
    }
  }
}
```

## Hot Reload Behavior

### TypeScript Worker

- File changes trigger automatic rebuild
- Worker restarts with new code
- Durable Object state persists across restarts
- KV/D1 data persists in `.wrangler/state/`

### Python Worker

- Python file changes trigger restart
- No build step required
- Dependencies require manual reinstall

```bash
# After updating requirements.txt
pip install -r requirements.txt
# Then restart wrangler dev
```

## Troubleshooting

### Common Issues

#### Port Already in Use

```bash
# Find process using port
lsof -i :8787

# Kill the process
kill -9 <PID>

# Or use a different port
wrangler dev --port 8790
```

#### D1 Migration Errors

```bash
# Reset local D1 database
rm -rf .wrangler/state/v3/d1/

# Recreate and apply migrations
wrangler d1 migrations apply ttai --local
```

#### Stale Durable Object State

```bash
# Clear DO state
rm -rf .wrangler/state/v3/do/

# Restart wrangler dev
```

#### Service Binding Connection Refused

```bash
# Ensure both workers are running
# Check ports match configuration
# Verify ENVIRONMENT=development is set
```

### Reset Local State

```bash
# Nuclear option: clear all local state
rm -rf .wrangler/

# Recreate databases
wrangler d1 migrations apply ttai --local

# Restart
wrangler dev
```

### Check Wrangler Version

```bash
# Update wrangler if issues persist
npm install -g wrangler@latest

# Verify version
wrangler --version
```

## Performance Tips

### Local Development Speed

1. **Use `--local` flag**: Keeps all data local, no network calls
2. **Disable remote bindings**: Comment out production IDs during development
3. **Minimize D1 queries**: Use KV caching even in development
4. **Run workers separately**: Start only the worker you're actively developing

### Recommended Workflow

```bash
# Terminal 1: MCP Server (primary development)
cd workers/mcp-server && wrangler dev

# Terminal 2: Python Worker (as needed)
cd workers/python-worker && wrangler dev --port 8788

# Terminal 3: Run tests
cd workers/mcp-server && npm test -- --watch
```

## Cross-References

- [MCP Server Design](./01-mcp-server-design.md) - Server implementation
- [Infrastructure](./08-infrastructure.md) - Production deployment
- [Integration Patterns](./09-integration-patterns.md) - Service communication
