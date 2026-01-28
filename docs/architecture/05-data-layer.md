# Data Layer

## Overview

The TTAI data layer uses Cloudflare's native storage services: KV for caching, D1 for SQLite-based persistence, R2 for object storage, and Queues for async messaging. All data is multi-tenant with `user_id` isolation.

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                     Cloudflare Edge Network                          │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ┌────────────────────────────────────────────────────────────────┐ │
│  │              MCP Server / Python Workers                        │ │
│  └──────────────────────────┬─────────────────────────────────────┘ │
│                             │                                        │
│      ┌──────────────────────┼──────────────────────────┐            │
│      ▼                      ▼                          ▼            │
│  ┌────────────┐    ┌────────────────┐    ┌────────────────┐        │
│  │ Cloudflare │    │  Cloudflare    │    │  Cloudflare    │        │
│  │     KV     │    │      D1        │    │      R2        │        │
│  │  (Cache)   │    │   (SQLite)     │    │  (Storage)     │        │
│  │            │    │                │    │                │        │
│  │ - Quotes   │    │ - Users        │    │ - Documents    │        │
│  │ - Chains   │    │ - Positions    │    │ - Embeddings   │        │
│  │ - Analysis │    │ - Analyses     │    │ - Exports      │        │
│  │ - Sessions │    │ - OAuth tokens │    │ - Backups      │        │
│  └────────────┘    └────────────────┘    └────────────────┘        │
│                                                                      │
│  ┌────────────────────────────────────────────────────────────────┐ │
│  │                    Cloudflare Queues                            │ │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐            │ │
│  │  │ Async Tasks │  │Notifications│  │  Analysis   │            │ │
│  │  │   Queue     │  │   Queue     │  │   Queue     │            │ │
│  │  └─────────────┘  └─────────────┘  └─────────────┘            │ │
│  └────────────────────────────────────────────────────────────────┘ │
│                                                                      │
│  ┌────────────────────────────────────────────────────────────────┐ │
│  │                  Cloudflare Vectorize                           │ │
│  │              (Semantic Search / Embeddings)                     │ │
│  └────────────────────────────────────────────────────────────────┘ │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

## Cloudflare KV (Caching)

### Cache Tiers

| Tier     | TTL            | Use Case               | Examples                 |
| -------- | -------------- | ---------------------- | ------------------------ |
| Hot      | 30-60 seconds  | Real-time data         | Quotes, last price       |
| Warm     | 5-15 minutes   | Frequently accessed    | Option chains, Greeks    |
| Cold     | 1 hour - 1 day | Slow-changing data     | Financials, company info |
| Session  | 24 hours       | User sessions          | Auth state               |
| Analysis | 15-30 minutes  | Expensive computations | Agent results            |

### Key Naming Convention

```typescript
// Format: {category}:{user_id?}:{identifier}

// Global keys (shared across users)
quote:{symbol}                     // AAPL quote
chain:{symbol}:{expiration}        // Option chain
company:{symbol}                   // Company info

// User-scoped keys
user:{user_id}:watchlist:{name}    // User watchlist
user:{user_id}:analysis:{symbol}   // User's analysis cache
user:{user_id}:session             // User session data
user:{user_id}:positions           // Cached positions
```

### KV Operations

```typescript
// src/services/kv.ts
export class CacheService {
  constructor(private kv: KVNamespace) {}

  // Quotes (hot tier - 60s TTL)
  async getQuote(symbol: string): Promise<Quote | null> {
    return this.kv.get(`quote:${symbol}`, "json");
  }

  async setQuote(symbol: string, quote: Quote): Promise<void> {
    await this.kv.put(`quote:${symbol}`, JSON.stringify(quote), {
      expirationTtl: 60,
    });
  }

  // Option chains (warm tier - 5m TTL)
  async getOptionChain(symbol: string, expiration?: string): Promise<OptionChain | null> {
    const key = expiration
      ? `chain:${symbol}:${expiration}`
      : `chain:${symbol}:all`;
    return this.kv.get(key, "json");
  }

  async setOptionChain(
    symbol: string,
    chain: OptionChain,
    expiration?: string
  ): Promise<void> {
    const key = expiration
      ? `chain:${symbol}:${expiration}`
      : `chain:${symbol}:all`;
    await this.kv.put(key, JSON.stringify(chain), {
      expirationTtl: 300, // 5 minutes
    });
  }

  // Analysis results (15m TTL)
  async getAnalysis(userId: string, symbol: string): Promise<Analysis | null> {
    return this.kv.get(`user:${userId}:analysis:${symbol}`, "json");
  }

  async setAnalysis(userId: string, symbol: string, analysis: Analysis): Promise<void> {
    await this.kv.put(
      `user:${userId}:analysis:${symbol}`,
      JSON.stringify(analysis),
      { expirationTtl: 900 } // 15 minutes
    );
  }

  // Company info (cold tier - 1 day TTL)
  async getCompanyInfo(symbol: string): Promise<CompanyInfo | null> {
    return this.kv.get(`company:${symbol}`, "json");
  }

  async setCompanyInfo(symbol: string, info: CompanyInfo): Promise<void> {
    await this.kv.put(`company:${symbol}`, JSON.stringify(info), {
      expirationTtl: 86400, // 24 hours
    });
  }

  // Batch operations
  async getQuotes(symbols: string[]): Promise<Map<string, Quote>> {
    const results = new Map<string, Quote>();

    // KV doesn't support batch get, so we parallelize
    await Promise.all(
      symbols.map(async (symbol) => {
        const quote = await this.getQuote(symbol);
        if (quote) results.set(symbol, quote);
      })
    );

    return results;
  }
}
```

## Cloudflare D1 (SQLite Database)

### Multi-Tenant Schema

All tables include `user_id` for row-level isolation:

```sql
-- schema.sql

-- Users (from TastyTrade OAuth)
CREATE TABLE users (
    id TEXT PRIMARY KEY,                 -- TastyTrade account ID (external-id)
    email TEXT,
    name TEXT,
    created_at INTEGER DEFAULT (unixepoch()),
    updated_at INTEGER DEFAULT (unixepoch())
);

-- Sessions (JWT session tracking)
CREATE TABLE sessions (
    id TEXT PRIMARY KEY,                 -- JWT ID (jti claim)
    user_id TEXT NOT NULL,               -- TastyTrade account ID
    created_at INTEGER DEFAULT (unixepoch()),
    expires_at INTEGER NOT NULL,
    revoked_at INTEGER,                  -- NULL if active, timestamp if revoked
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE INDEX idx_sessions_user ON sessions(user_id);
CREATE INDEX idx_sessions_expires ON sessions(expires_at);

-- User OAuth tokens (encrypted)
CREATE TABLE user_oauth_tokens (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,               -- TastyTrade account ID
    provider TEXT NOT NULL,              -- 'tastytrade'
    access_token TEXT NOT NULL,          -- Encrypted
    refresh_token TEXT NOT NULL,         -- Encrypted
    expires_at INTEGER NOT NULL,         -- Unix timestamp
    created_at INTEGER DEFAULT (unixepoch()),
    updated_at INTEGER DEFAULT (unixepoch()),
    UNIQUE(user_id, provider),
    FOREIGN KEY (user_id) REFERENCES users(id)
);

-- User preferences
CREATE TABLE user_preferences (
    user_id TEXT PRIMARY KEY,
    default_strategy TEXT DEFAULT 'csp',
    morning_alert INTEGER DEFAULT 0,
    eod_summary INTEGER DEFAULT 0,
    notification_channels TEXT DEFAULT '[]', -- JSON array
    created_at INTEGER DEFAULT (unixepoch()),
    updated_at INTEGER DEFAULT (unixepoch())
);

-- Positions (synced from TastyTrade)
CREATE TABLE positions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    quantity INTEGER NOT NULL,
    average_cost REAL NOT NULL,
    position_type TEXT NOT NULL,          -- 'stock', 'option'
    option_type TEXT,                     -- 'call', 'put'
    strike REAL,
    expiration TEXT,
    status TEXT DEFAULT 'open',           -- 'open', 'closed'
    opened_at INTEGER,
    closed_at INTEGER,
    created_at INTEGER DEFAULT (unixepoch()),
    updated_at INTEGER DEFAULT (unixepoch())
);

CREATE INDEX idx_positions_user ON positions(user_id);
CREATE INDEX idx_positions_user_status ON positions(user_id, status);

-- Analysis history
CREATE TABLE analyses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    type TEXT NOT NULL,                   -- 'chart', 'options', 'full'
    result TEXT NOT NULL,                 -- JSON
    recommendation TEXT,                  -- 'select', 'reject', 'neutral'
    workflow_id TEXT,
    created_at INTEGER DEFAULT (unixepoch())
);

CREATE INDEX idx_analyses_user ON analyses(user_id);
CREATE INDEX idx_analyses_user_symbol ON analyses(user_id, symbol);

-- Screener configurations
CREATE TABLE screeners (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    name TEXT NOT NULL,
    description TEXT,
    type TEXT NOT NULL,                   -- 'stock', 'csp'
    criteria TEXT NOT NULL,               -- JSON
    auto_run INTEGER DEFAULT 0,
    created_at INTEGER DEFAULT (unixepoch()),
    updated_at INTEGER DEFAULT (unixepoch()),
    UNIQUE(user_id, name)
);

CREATE INDEX idx_screeners_user ON screeners(user_id);

-- Screener results
CREATE TABLE screener_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    screener_id INTEGER,
    criteria TEXT NOT NULL,               -- JSON (snapshot)
    results TEXT NOT NULL,                -- JSON
    created_at INTEGER DEFAULT (unixepoch()),
    FOREIGN KEY (screener_id) REFERENCES screeners(id)
);

CREATE INDEX idx_screener_results_user ON screener_results(user_id);

-- Alerts
CREATE TABLE alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    alert_type TEXT NOT NULL,             -- 'price', 'delta', 'dte', 'news'
    condition TEXT NOT NULL,              -- 'above', 'below', etc.
    threshold REAL,
    message_template TEXT,
    status TEXT DEFAULT 'active',         -- 'active', 'triggered', 'cancelled'
    triggered_at INTEGER,
    created_at INTEGER DEFAULT (unixepoch())
);

CREATE INDEX idx_alerts_user ON alerts(user_id);
CREATE INDEX idx_alerts_active ON alerts(user_id, status) WHERE status = 'active';

-- Watchlists
CREATE TABLE watchlists (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    name TEXT NOT NULL,
    symbols TEXT NOT NULL,                -- JSON array
    created_at INTEGER DEFAULT (unixepoch()),
    updated_at INTEGER DEFAULT (unixepoch()),
    UNIQUE(user_id, name)
);

CREATE INDEX idx_watchlists_user ON watchlists(user_id);
```

### D1 Operations

```typescript
// src/services/database.ts
export class DatabaseService {
  constructor(
    private db: D1Database,
    private userId: string
  ) {}

  // Positions
  async getPositions(status: "open" | "closed" | "all" = "open"): Promise<Position[]> {
    let query = "SELECT * FROM positions WHERE user_id = ?";
    const params: any[] = [this.userId];

    if (status !== "all") {
      query += " AND status = ?";
      params.push(status);
    }

    const result = await this.db.prepare(query).bind(...params).all();
    return result.results as Position[];
  }

  async upsertPosition(position: Omit<Position, "id">): Promise<void> {
    await this.db.prepare(`
      INSERT INTO positions (user_id, symbol, quantity, average_cost, position_type,
                            option_type, strike, expiration, status, opened_at)
      VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
      ON CONFLICT(user_id, symbol, option_type, strike, expiration)
      DO UPDATE SET quantity = excluded.quantity,
                    average_cost = excluded.average_cost,
                    status = excluded.status,
                    updated_at = unixepoch()
    `).bind(
      this.userId,
      position.symbol,
      position.quantity,
      position.averageCost,
      position.positionType,
      position.optionType,
      position.strike,
      position.expiration,
      position.status,
      position.openedAt
    ).run();
  }

  // Analyses
  async saveAnalysis(analysis: Omit<Analysis, "id" | "userId">): Promise<number> {
    const result = await this.db.prepare(`
      INSERT INTO analyses (user_id, symbol, type, result, recommendation, workflow_id)
      VALUES (?, ?, ?, ?, ?, ?)
    `).bind(
      this.userId,
      analysis.symbol,
      analysis.type,
      JSON.stringify(analysis.result),
      analysis.recommendation,
      analysis.workflowId
    ).run();

    return result.meta.last_row_id;
  }

  async getAnalyses(limit = 20, symbol?: string): Promise<Analysis[]> {
    let query = "SELECT * FROM analyses WHERE user_id = ?";
    const params: any[] = [this.userId];

    if (symbol) {
      query += " AND symbol = ?";
      params.push(symbol);
    }

    query += " ORDER BY created_at DESC LIMIT ?";
    params.push(limit);

    const result = await this.db.prepare(query).bind(...params).all();
    return result.results.map((row: any) => ({
      ...row,
      result: JSON.parse(row.result),
    })) as Analysis[];
  }

  // Screeners
  async getScreeners(): Promise<Screener[]> {
    const result = await this.db.prepare(
      "SELECT * FROM screeners WHERE user_id = ? ORDER BY name"
    ).bind(this.userId).all();

    return result.results.map((row: any) => ({
      ...row,
      criteria: JSON.parse(row.criteria),
    })) as Screener[];
  }

  async saveScreener(screener: Omit<Screener, "id">): Promise<number> {
    const result = await this.db.prepare(`
      INSERT INTO screeners (user_id, name, description, type, criteria, auto_run)
      VALUES (?, ?, ?, ?, ?, ?)
      ON CONFLICT(user_id, name) DO UPDATE SET
        description = excluded.description,
        type = excluded.type,
        criteria = excluded.criteria,
        auto_run = excluded.auto_run,
        updated_at = unixepoch()
    `).bind(
      this.userId,
      screener.name,
      screener.description,
      screener.type,
      JSON.stringify(screener.criteria),
      screener.autoRun ? 1 : 0
    ).run();

    return result.meta.last_row_id;
  }

  // Alerts
  async getActiveAlerts(): Promise<Alert[]> {
    const result = await this.db.prepare(
      "SELECT * FROM alerts WHERE user_id = ? AND status = 'active'"
    ).bind(this.userId).all();

    return result.results as Alert[];
  }

  async createAlert(alert: Omit<Alert, "id" | "status" | "triggeredAt">): Promise<number> {
    const result = await this.db.prepare(`
      INSERT INTO alerts (user_id, symbol, alert_type, condition, threshold, message_template)
      VALUES (?, ?, ?, ?, ?, ?)
    `).bind(
      this.userId,
      alert.symbol,
      alert.alertType,
      alert.condition,
      alert.threshold,
      alert.messageTemplate
    ).run();

    return result.meta.last_row_id;
  }

  async triggerAlert(alertId: number): Promise<void> {
    await this.db.prepare(`
      UPDATE alerts
      SET status = 'triggered', triggered_at = unixepoch()
      WHERE id = ? AND user_id = ?
    `).bind(alertId, this.userId).run();
  }
}
```

## Cloudflare R2 (Object Storage)

### Storage Structure

```
ttai-storage/
├── knowledge/                  # Knowledge base documents
│   ├── options/
│   │   ├── strategies.md
│   │   └── greeks.md
│   └── trading/
│       └── risk-management.md
│
├── users/{user_id}/           # User-specific storage
│   ├── exports/               # Exported reports
│   │   └── analysis-2024-01-15.pdf
│   └── uploads/               # User uploads
│
├── embeddings/                # Vector embedding data
│   └── knowledge/
│       └── chunks.json
│
└── backups/                   # D1 backups
    └── d1-backup-2024-01-15.sql
```

### R2 Operations

```typescript
// src/services/storage.ts
export class StorageService {
  constructor(
    private r2: R2Bucket,
    private userId?: string
  ) {}

  // Knowledge base
  async getKnowledgeDoc(path: string): Promise<string | null> {
    const object = await this.r2.get(`knowledge/${path}`);
    if (!object) return null;
    return object.text();
  }

  async listKnowledgeDocs(prefix?: string): Promise<string[]> {
    const listed = await this.r2.list({
      prefix: prefix ? `knowledge/${prefix}` : "knowledge/",
    });
    return listed.objects.map((obj) => obj.key);
  }

  // User exports
  async saveExport(filename: string, content: ArrayBuffer): Promise<string> {
    if (!this.userId) throw new Error("User ID required for exports");

    const key = `users/${this.userId}/exports/${filename}`;
    await this.r2.put(key, content, {
      httpMetadata: {
        contentType: this.getContentType(filename),
      },
    });

    return key;
  }

  async getExport(filename: string): Promise<ArrayBuffer | null> {
    if (!this.userId) throw new Error("User ID required for exports");

    const object = await this.r2.get(`users/${this.userId}/exports/${filename}`);
    if (!object) return null;
    return object.arrayBuffer();
  }

  async listExports(): Promise<ExportFile[]> {
    if (!this.userId) throw new Error("User ID required");

    const listed = await this.r2.list({
      prefix: `users/${this.userId}/exports/`,
    });

    return listed.objects.map((obj) => ({
      name: obj.key.split("/").pop() || "",
      size: obj.size,
      uploaded: obj.uploaded,
    }));
  }

  private getContentType(filename: string): string {
    const ext = filename.split(".").pop()?.toLowerCase();
    const types: Record<string, string> = {
      pdf: "application/pdf",
      csv: "text/csv",
      json: "application/json",
      md: "text/markdown",
    };
    return types[ext || ""] || "application/octet-stream";
  }
}
```

## Cloudflare Queues (Async Processing)

### Queue Definitions

```toml
# wrangler.toml

# Task queue (producer)
[[queues.producers]]
binding = "TASK_QUEUE"
queue = "ttai-tasks"

# Task queue (consumer)
[[queues.consumers]]
queue = "ttai-tasks"
max_batch_size = 10
max_batch_timeout = 30

# Notification queue
[[queues.producers]]
binding = "NOTIFICATION_QUEUE"
queue = "ttai-notifications"

[[queues.consumers]]
queue = "ttai-notifications"
max_batch_size = 20
max_batch_timeout = 5
```

### Queue Message Types

```typescript
// src/types/queue.ts
export type QueueMessage =
  | AnalysisCompleteMessage
  | AlertTriggeredMessage
  | ScreenerCompleteMessage
  | NotificationMessage;

export interface AnalysisCompleteMessage {
  type: "analysis_complete";
  userId: string;
  symbol: string;
  recommendation: string;
  workflowId: string;
}

export interface AlertTriggeredMessage {
  type: "alert_triggered";
  userId: string;
  alertId: number;
  symbol: string;
  condition: string;
  currentValue: number;
}

export interface ScreenerCompleteMessage {
  type: "screener_complete";
  userId: string;
  screenerId: number;
  resultCount: number;
}

export interface NotificationMessage {
  type: "notification";
  userId: string;
  channel: "discord" | "email" | "push";
  title: string;
  body: string;
  data?: Record<string, unknown>;
}
```

### Queue Consumer

```typescript
// src/index.ts
export default {
  // ... fetch handler

  async queue(batch: MessageBatch<QueueMessage>, env: Env): Promise<void> {
    for (const message of batch.messages) {
      try {
        await processMessage(message.body, env);
        message.ack();
      } catch (error) {
        console.error("Queue message failed:", error);
        message.retry();
      }
    }
  },
};

async function processMessage(msg: QueueMessage, env: Env): Promise<void> {
  switch (msg.type) {
    case "analysis_complete":
      await handleAnalysisComplete(msg, env);
      break;
    case "alert_triggered":
      await handleAlertTriggered(msg, env);
      break;
    case "notification":
      await sendNotification(msg, env);
      break;
  }
}

async function handleAnalysisComplete(
  msg: AnalysisCompleteMessage,
  env: Env
): Promise<void> {
  // Get user preferences
  const prefs = await env.DB.prepare(
    "SELECT notification_channels FROM user_preferences WHERE user_id = ?"
  ).bind(msg.userId).first();

  if (!prefs) return;

  const channels = JSON.parse(prefs.notification_channels || "[]");

  // Queue notification for each channel
  for (const channel of channels) {
    await env.NOTIFICATION_QUEUE.send({
      type: "notification",
      userId: msg.userId,
      channel,
      title: `Analysis Complete: ${msg.symbol}`,
      body: `Recommendation: ${msg.recommendation}`,
      data: { symbol: msg.symbol, workflowId: msg.workflowId },
    });
  }
}
```

## Pub/Sub with Durable Objects

For real-time updates, Durable Objects + WebSocket hibernation provides a pub/sub pattern:

```typescript
// src/durableObjects/pubsub.ts
export class PubSubDO implements DurableObject {
  private state: DurableObjectState;
  private channels: Map<string, Set<WebSocket>> = new Map();

  constructor(state: DurableObjectState, env: Env) {
    this.state = state;
  }

  async fetch(request: Request): Promise<Response> {
    const url = new URL(request.url);

    if (url.pathname === "/subscribe") {
      return this.handleSubscribe(request);
    }

    if (url.pathname === "/publish") {
      return this.handlePublish(request);
    }

    return new Response("Not Found", { status: 404 });
  }

  async handleSubscribe(request: Request): Promise<Response> {
    const upgradeHeader = request.headers.get("Upgrade");
    if (upgradeHeader !== "websocket") {
      return new Response("Expected WebSocket", { status: 426 });
    }

    const url = new URL(request.url);
    const channels = url.searchParams.get("channels")?.split(",") || [];

    const [client, server] = Object.values(new WebSocketPair());

    // Use hibernation
    this.state.acceptWebSocket(server);
    server.serializeAttachment({ channels });

    return new Response(null, { status: 101, webSocket: client });
  }

  async handlePublish(request: Request): Promise<Response> {
    const { channel, data } = await request.json<{
      channel: string;
      data: unknown;
    }>();

    const message = JSON.stringify({ channel, data, timestamp: Date.now() });

    // Send to all WebSockets subscribed to this channel
    for (const ws of this.state.getWebSockets()) {
      const attachment = ws.deserializeAttachment() as { channels: string[] };
      if (attachment.channels.includes(channel)) {
        ws.send(message);
      }
    }

    return new Response("ok");
  }

  async webSocketClose(ws: WebSocket): Promise<void> {
    // Automatic cleanup via hibernation
  }
}
```

## Cross-References

- [MCP Server Design](./01-mcp-server-design.md) - KV/D1 access patterns
- [Background Tasks](./06-background-tasks.md) - Queue processing
- [Knowledge Base](./07-knowledge-base.md) - R2 document storage
- [Infrastructure](./08-infrastructure.md) - Binding configuration
