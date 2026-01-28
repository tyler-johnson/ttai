# Infrastructure

## Overview

TTAI runs entirely on Cloudflare's edge network. This document covers the Cloudflare Workers project structure, wrangler.toml configuration, bindings setup, secrets management, and GitHub Actions deployment.

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                     Cloudflare Edge Network                          │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  Workers                                                             │
│  ┌────────────────────────────────────────────────────────────────┐ │
│  │ ttai-mcp-server     │ ttai-python-worker                       │ │
│  │ (TypeScript)        │ (Python/Pyodide)                         │ │
│  └────────────────────────────────────────────────────────────────┘ │
│                                                                      │
│  Storage                                                             │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐           │
│  │    KV    │  │    D1    │  │    R2    │  │ Vectorize│           │
│  │  Cache   │  │  SQLite  │  │  Storage │  │  Search  │           │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘           │
│                                                                      │
│  Compute                                                             │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐           │
│  │ Durable  │  │Workflows │  │  Queues  │  │   Cron   │           │
│  │ Objects  │  │          │  │          │  │ Triggers │           │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘           │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

## Project Structure

```
ttai/
├── workers/
│   ├── mcp-server/              # TypeScript MCP server
│   │   ├── src/
│   │   │   ├── index.ts         # Worker entry point
│   │   │   ├── server/          # MCP server implementation
│   │   │   │   ├── factory.ts
│   │   │   │   ├── tools.ts
│   │   │   │   └── resources.ts
│   │   │   ├── auth/            # TastyTrade OAuth authentication
│   │   │   │   ├── oauth.ts     # JWT verification, OAuth callback
│   │   │   │   └── tastytrade.ts # TT token management
│   │   │   ├── durableObjects/  # Durable Object classes
│   │   │   │   ├── session.ts
│   │   │   │   ├── portfolioMonitor.ts
│   │   │   │   └── priceAlert.ts
│   │   │   ├── workflows/       # Cloudflare Workflows
│   │   │   │   ├── analysis.ts
│   │   │   │   └── screener.ts
│   │   │   ├── services/        # Service layer
│   │   │   │   ├── cache.ts
│   │   │   │   ├── database.ts
│   │   │   │   └── storage.ts
│   │   │   └── types/           # TypeScript types
│   │   │       └── index.ts
│   │   ├── wrangler.toml
│   │   ├── package.json
│   │   └── tsconfig.json
│   │
│   └── python-worker/           # Python worker
│       ├── src/
│       │   ├── main.py          # Worker entry point
│       │   ├── handlers/        # Request handlers
│       │   │   ├── quotes.py
│       │   │   ├── options.py
│       │   │   └── analysis.py
│       │   ├── agents/          # AI agents
│       │   │   ├── base.py
│       │   │   ├── chart.py
│       │   │   └── options.py
│       │   ├── tastytrade/      # TastyTrade client
│       │   │   ├── client.py
│       │   │   └── oauth.py
│       │   └── analysis/        # Analysis utilities
│       │       ├── indicators.py
│       │       └── levels.py
│       ├── wrangler.toml
│       └── requirements.txt
│
├── migrations/                   # D1 migrations
│   ├── 0001_initial.sql
│   └── 0002_add_alerts.sql
│
├── scripts/                      # Management scripts
│   ├── setup.sh
│   ├── deploy.sh
│   └── manage-knowledge.ts
│
├── .github/
│   └── workflows/
│       ├── deploy.yml
│       └── test.yml
│
└── docs/
    └── architecture/
```

## wrangler.toml Configuration

### MCP Server (TypeScript)

```toml
# workers/mcp-server/wrangler.toml
name = "ttai-mcp-server"
main = "src/index.ts"
compatibility_date = "2024-01-01"
compatibility_flags = ["nodejs_compat"]

# Account ID (optional - can use CLOUDFLARE_ACCOUNT_ID env var)
# account_id = "your-account-id"

# Build configuration
[build]
command = "npm run build"

# Node.js compatibility
node_compat = true

# ===== KV Namespaces =====
[[kv_namespaces]]
binding = "KV"
id = "abc123def456"
preview_id = "preview123"

# ===== D1 Databases =====
[[d1_databases]]
binding = "DB"
database_name = "ttai"
database_id = "your-d1-database-id"

# ===== R2 Buckets =====
[[r2_buckets]]
binding = "R2"
bucket_name = "ttai-storage"
preview_bucket_name = "ttai-storage-preview"

# ===== Durable Objects =====
[[durable_objects.bindings]]
name = "SESSIONS"
class_name = "SessionDurableObject"

[[durable_objects.bindings]]
name = "PORTFOLIO_MONITOR"
class_name = "PortfolioMonitor"

[[durable_objects.bindings]]
name = "PRICE_ALERT"
class_name = "PriceAlertDO"

[[durable_objects.bindings]]
name = "NEWS_WATCHER"
class_name = "NewsWatcher"

# Durable Object migrations
[[migrations]]
tag = "v1"
new_classes = ["SessionDurableObject", "PortfolioMonitor", "PriceAlertDO", "NewsWatcher"]

# ===== Workflows =====
[[workflows]]
binding = "ANALYSIS_WORKFLOW"
name = "analysis-workflow"
class_name = "AnalysisWorkflow"

[[workflows]]
binding = "SCREENER_WORKFLOW"
name = "screener-workflow"
class_name = "ScreenerWorkflow"

# ===== Service Bindings =====
[[services]]
binding = "PYTHON_WORKER"
service = "ttai-python-worker"

# ===== Queues =====
[[queues.producers]]
binding = "QUEUE"
queue = "ttai-tasks"

[[queues.producers]]
binding = "NOTIFICATION_QUEUE"
queue = "ttai-notifications"

[[queues.consumers]]
queue = "ttai-tasks"
max_batch_size = 10
max_batch_timeout = 30

[[queues.consumers]]
queue = "ttai-notifications"
max_batch_size = 20
max_batch_timeout = 5

# ===== Vectorize =====
[[vectorize]]
binding = "VECTORIZE"
index_name = "ttai-knowledge"

# ===== Workers AI =====
[ai]
binding = "AI"

# ===== Cron Triggers =====
[triggers]
crons = [
  "30 14 * * 1-5",     # Market open
  "0 21 * * 1-5",      # Market close
  "0 14-21 * * 1-5",   # Hourly during market
  "0 22 * * 1-5",      # Daily reports
  "0 22 * * 5"         # Weekly summary
]

# ===== Environment Variables =====
[vars]
ENVIRONMENT = "production"
LOG_LEVEL = "info"

# ===== Environments =====
[env.staging]
name = "ttai-mcp-server-staging"
vars = { ENVIRONMENT = "staging", LOG_LEVEL = "debug" }

[[env.staging.kv_namespaces]]
binding = "KV"
id = "staging-kv-id"

[env.production]
name = "ttai-mcp-server"
vars = { ENVIRONMENT = "production", LOG_LEVEL = "warn" }
```

### Python Worker

```toml
# workers/python-worker/wrangler.toml
name = "ttai-python-worker"
main = "src/main.py"
compatibility_date = "2024-01-01"

# Python worker config
[build]
command = "pip install -r requirements.txt -t ./packages"

# KV for caching
[[kv_namespaces]]
binding = "KV"
id = "abc123def456"

# D1 for database
[[d1_databases]]
binding = "DB"
database_name = "ttai"
database_id = "your-d1-database-id"

# Environment variables
[vars]
ENVIRONMENT = "production"
DEFAULT_LLM_MODEL = "anthropic/claude-sonnet-4-20250514"
```

## Secrets Management

### Setting Secrets

```bash
# JWT signing key (generate with: openssl rand -hex 32)
wrangler secret put JWT_SECRET

# TastyTrade OAuth (app credentials)
wrangler secret put TASTYTRADE_CLIENT_ID
wrangler secret put TASTYTRADE_CLIENT_SECRET

# LLM API keys (for Python worker)
wrangler secret put ANTHROPIC_API_KEY
wrangler secret put OPENAI_API_KEY

# Encryption key for tokens (generate with: openssl rand -hex 32)
wrangler secret put TOKEN_ENCRYPTION_KEY
```

### Accessing Secrets

```typescript
// Secrets are available in env
export interface Env {
  // Bindings
  KV: KVNamespace;
  DB: D1Database;
  // ...

  // Secrets
  JWT_SECRET: string;
  TASTYTRADE_CLIENT_ID: string;
  TASTYTRADE_CLIENT_SECRET: string;
  ANTHROPIC_API_KEY: string;
  TOKEN_ENCRYPTION_KEY: string;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    // Use env.JWT_SECRET for session verification
  },
};
```

## D1 Database Migrations

### Creating Migrations

```bash
# Create a new migration
wrangler d1 migrations create ttai add_alerts_table
```

### Migration Files

```sql
-- migrations/0001_initial.sql
CREATE TABLE user_oauth_tokens (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    provider TEXT NOT NULL,
    access_token TEXT NOT NULL,
    refresh_token TEXT NOT NULL,
    expires_at INTEGER NOT NULL,
    created_at INTEGER DEFAULT (unixepoch()),
    updated_at INTEGER DEFAULT (unixepoch()),
    UNIQUE(user_id, provider)
);

CREATE TABLE positions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    quantity INTEGER NOT NULL,
    average_cost REAL NOT NULL,
    position_type TEXT NOT NULL,
    option_type TEXT,
    strike REAL,
    expiration TEXT,
    status TEXT DEFAULT 'open',
    opened_at INTEGER,
    closed_at INTEGER,
    created_at INTEGER DEFAULT (unixepoch()),
    updated_at INTEGER DEFAULT (unixepoch())
);

CREATE INDEX idx_positions_user ON positions(user_id);
CREATE INDEX idx_positions_user_status ON positions(user_id, status);

-- Additional tables...
```

### Applying Migrations

```bash
# Apply migrations (local)
wrangler d1 migrations apply ttai --local

# Apply migrations (remote)
wrangler d1 migrations apply ttai --remote

# Apply to production
wrangler d1 migrations apply ttai --remote --env production
```

## GitHub Actions Deployment

### Deploy Workflow

```yaml
# .github/workflows/deploy.yml
name: Deploy to Cloudflare

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

env:
  CLOUDFLARE_API_TOKEN: ${{ secrets.CLOUDFLARE_API_TOKEN }}
  CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CLOUDFLARE_ACCOUNT_ID }}

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Setup Node.js
        uses: actions/setup-node@v4
        with:
          node-version: "20"
          cache: "npm"
          cache-dependency-path: workers/mcp-server/package-lock.json

      - name: Install dependencies
        run: npm ci
        working-directory: workers/mcp-server

      - name: Type check
        run: npm run typecheck
        working-directory: workers/mcp-server

      - name: Run tests
        run: npm test
        working-directory: workers/mcp-server

  deploy-staging:
    needs: test
    if: github.event_name == 'pull_request'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Setup Node.js
        uses: actions/setup-node@v4
        with:
          node-version: "20"

      - name: Install dependencies
        run: npm ci
        working-directory: workers/mcp-server

      - name: Deploy MCP Server to staging
        run: npx wrangler deploy --env staging
        working-directory: workers/mcp-server

      - name: Deploy Python Worker to staging
        run: npx wrangler deploy --env staging
        working-directory: workers/python-worker

  deploy-production:
    needs: test
    if: github.ref == 'refs/heads/main' && github.event_name == 'push'
    runs-on: ubuntu-latest
    environment: production
    steps:
      - uses: actions/checkout@v4

      - name: Setup Node.js
        uses: actions/setup-node@v4
        with:
          node-version: "20"

      - name: Install dependencies
        run: npm ci
        working-directory: workers/mcp-server

      - name: Run D1 migrations
        run: npx wrangler d1 migrations apply ttai --remote
        working-directory: workers/mcp-server

      - name: Deploy MCP Server
        run: npx wrangler deploy
        working-directory: workers/mcp-server

      - name: Deploy Python Worker
        run: npx wrangler deploy
        working-directory: workers/python-worker
```

### Secret Setup in GitHub

Required secrets in GitHub repository settings:

| Secret                   | Description                    |
| ------------------------ | ------------------------------ |
| `CLOUDFLARE_API_TOKEN`   | Cloudflare API token           |
| `CLOUDFLARE_ACCOUNT_ID`  | Cloudflare account ID          |

## Cost Estimates

### Cloudflare Workers

| Service      | Free Tier       | Paid Plan                 |
| ------------ | --------------- | ------------------------- |
| Workers      | 100K req/day    | $5/mo + $0.50/million req |
| KV           | 100K reads/day  | $0.50/million reads       |
| D1           | 5M rows read    | $0.001/million rows       |
| R2           | 10GB storage    | $0.015/GB/mo              |
| Queues       | 1M messages/mo  | $0.40/million messages    |
| Vectorize    | 30M queries/mo  | $0.01/1K queries          |
| Durable Obj. | 400K GB-s/mo    | $12.50/million GB-s       |

### Estimated Monthly Cost

For a typical usage pattern (1000 active users):

| Component              | Estimated Cost |
| ---------------------- | -------------- |
| Workers (requests)     | ~$10           |
| KV (reads/writes)      | ~$5            |
| D1 (database)          | ~$5            |
| R2 (storage)           | ~$2            |
| Queues                 | ~$2            |
| Durable Objects        | ~$10           |
| Workers AI (optional)  | ~$5            |
| **Total**              | **~$40/month** |

## Resource Creation Commands

```bash
# Create KV namespace
wrangler kv:namespace create "CACHE"
wrangler kv:namespace create "CACHE" --preview

# Create D1 database
wrangler d1 create ttai

# Create R2 bucket
wrangler r2 bucket create ttai-storage

# Create Vectorize index
wrangler vectorize create ttai-knowledge --dimensions 768 --metric cosine

# Create Queues
wrangler queues create ttai-tasks
wrangler queues create ttai-notifications
```

## Cross-References

- [MCP Server Design](./01-mcp-server-design.md) - Worker implementation
- [Data Layer](./05-data-layer.md) - Storage bindings
- [Local Development](./10-local-development.md) - Development setup
