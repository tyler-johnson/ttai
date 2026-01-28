# MCP Server Design

## Overview

The MCP (Model Context Protocol) server is implemented as a TypeScript Cloudflare Worker that serves as the primary API layer for the TTAI system. It handles client connections via Streamable HTTP with SSE fallback, authenticates users via TastyTrade OAuth, and orchestrates requests across the Cloudflare platform.

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                     Cloudflare Edge Network                          │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ┌────────────────────────────────────────────────────────────────┐ │
│  │              MCP Server (TypeScript Worker)                     │ │
│  │         Streamable HTTP + SSE | TastyTrade OAuth                │ │
│  └──────────────────────────┬─────────────────────────────────────┘ │
│                             │                                        │
│      ┌──────────────────────┼──────────────────────┐                │
│      ▼                      ▼                      ▼                │
│  ┌────────────┐    ┌────────────────┐    ┌────────────────┐        │
│  │  Durable   │    │   Cloudflare   │    │ Python Workers │        │
│  │  Objects   │    │   Workflows    │    │ (TastyTrade,   │        │
│  │ (Sessions, │    │   (Durable     │    │  AI Agents,    │        │
│  │  WebSocket)│    │   Execution)   │    │  Analysis)     │        │
│  └─────┬──────┘    └───────┬────────┘    └───────┬────────┘        │
│        │                   │                     │                  │
│        └───────────────────┼─────────────────────┘                  │
│                            ▼                                        │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐           │
│  │    KV    │  │    D1    │  │  Queues  │  │    R2    │           │
│  │ (Cache)  │  │ (SQLite) │  │ (Async)  │  │(Storage) │           │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘           │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
                              │
                             │
              ┌──────────────┴──────────────┐
              ▼                             ▼
       ┌───────────┐                 ┌───────────┐
       │TastyTrade │                 │ LLM APIs  │
       │   API     │                 │(via LiteLLM)│
       │  + OAuth  │                 └───────────┘
       └───────────┘
```

## Transport Layer

### Streamable HTTP (Primary)

The MCP server uses Streamable HTTP as the primary transport, which provides bidirectional communication with built-in streaming support.

```typescript
// src/index.ts
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StreamableHTTPServerTransport } from "@modelcontextprotocol/sdk/server/streamableHttp.js";
import { authenticateRequest, handleOAuthCallback } from "./auth/oauth.js";

export interface Env {
  // Cloudflare bindings
  KV: KVNamespace;
  DB: D1Database;
  SESSIONS: DurableObjectNamespace;
  WORKFLOWS: Workflow;
  PYTHON_WORKER: Fetcher;
  QUEUE: Queue;
  R2: R2Bucket;

  // Secrets
  JWT_SECRET: string;
  TASTYTRADE_CLIENT_ID: string;
  TASTYTRADE_CLIENT_SECRET: string;
}

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const url = new URL(request.url);

    // Health check endpoint
    if (url.pathname === "/health") {
      return new Response("ok", { status: 200 });
    }

    // OAuth callback endpoint
    if (url.pathname === "/oauth/callback") {
      return handleOAuthCallback(request, env);
    }

    // MCP endpoint with JWT authentication
    if (url.pathname === "/mcp") {
      return handleMcpRequest(request, env, ctx);
    }

    return new Response("Not Found", { status: 404 });
  },
};

async function handleMcpRequest(
  request: Request,
  env: Env,
  ctx: ExecutionContext
): Promise<Response> {
  // Verify session JWT (from TastyTrade OAuth flow)
  const userContext = await authenticateRequest(request, env);
  if (!userContext) {
    return new Response("Unauthorized", { status: 401 });
  }

  // Create MCP server with user context
  const server = createMcpServer(env, userContext);

  // Handle with Streamable HTTP transport
  const transport = new StreamableHTTPServerTransport({
    sessionIdGenerator: () => `${userContext.userId}-${Date.now()}`,
  });

  await server.connect(transport);
  return transport.handleRequest(request);
}
```

### SSE Fallback

For clients that don't support Streamable HTTP, the server provides an SSE endpoint.

```typescript
// src/transports/sse.ts
import { SSEServerTransport } from "@modelcontextprotocol/sdk/server/sse.js";

export async function handleSseRequest(
  request: Request,
  env: Env,
  userContext: UserContext
): Promise<Response> {
  const server = createMcpServer(env, userContext);

  const transport = new SSEServerTransport("/mcp/sse", response);
  await server.connect(transport);

  // Return SSE response
  return new Response(transport.readable, {
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache",
      "Connection": "keep-alive",
    },
  });
}
```

## TastyTrade OAuth Authentication

### Authentication Flow

Users authenticate directly via their TastyTrade account - no separate identity provider needed.

```
┌─────────────────────────────────────────────────────────────────────┐
│                    TastyTrade OAuth Flow                             │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  1. User clicks "Login with TastyTrade"                             │
│                    │                                                 │
│                    ▼                                                 │
│  2. Redirect to TastyTrade OAuth authorize endpoint                 │
│                    │                                                 │
│                    ▼                                                 │
│  3. User authenticates with TastyTrade credentials                  │
│                    │                                                 │
│                    ▼                                                 │
│  4. TastyTrade redirects back with authorization code               │
│                    │                                                 │
│                    ▼                                                 │
│  5. Exchange code for access_token + refresh_token                  │
│                    │                                                 │
│                    ▼                                                 │
│  6. Create session JWT signed with our secret                       │
│     (contains TastyTrade account ID as user identifier)             │
│                    │                                                 │
│                    ▼                                                 │
│  7. Store encrypted TT tokens in D1 keyed by TT account ID          │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

### Session JWT Structure

```typescript
interface SessionJWT {
  sub: string;           // TastyTrade account ID
  email?: string;        // From TastyTrade account
  iat: number;           // Issued at
  exp: number;           // Expires (24h)
}
```

### Auth Middleware

```typescript
// src/auth/oauth.ts
import { jwtVerify, SignJWT } from "jose";

export interface UserContext {
  userId: string;        // TastyTrade account ID
  email?: string;
}

export async function authenticateRequest(
  request: Request,
  env: Env
): Promise<UserContext | null> {
  const authHeader = request.headers.get("Authorization");
  if (!authHeader?.startsWith("Bearer ")) {
    return null;
  }

  const token = authHeader.slice(7);

  try {
    const secret = new TextEncoder().encode(env.JWT_SECRET);
    const { payload } = await jwtVerify(token, secret);

    return {
      userId: payload.sub as string,  // TastyTrade account ID
      email: payload.email as string | undefined,
    };
  } catch {
    return null;
  }
}
```

### OAuth Callback Handler

```typescript
// src/auth/oauth.ts (continued)
export async function handleOAuthCallback(
  request: Request,
  env: Env
): Promise<Response> {
  const url = new URL(request.url);
  const code = url.searchParams.get("code");

  if (!code) {
    return new Response("Missing authorization code", { status: 400 });
  }

  // Exchange code for tokens with TastyTrade
  const tokenResponse = await fetch("https://api.tastyworks.com/oauth/token", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      grant_type: "authorization_code",
      code,
      client_id: env.TASTYTRADE_CLIENT_ID,
      client_secret: env.TASTYTRADE_CLIENT_SECRET,
      redirect_uri: `${url.origin}/oauth/callback`,
    }),
  });

  if (!tokenResponse.ok) {
    return new Response("Failed to exchange code for tokens", { status: 400 });
  }

  const tokens = await tokenResponse.json<{
    access_token: string;
    refresh_token: string;
    expires_in: number;
  }>();

  // Get TastyTrade account info
  const accountResponse = await fetch("https://api.tastyworks.com/customers/me", {
    headers: { Authorization: `Bearer ${tokens.access_token}` },
  });

  const account = await accountResponse.json<{
    data: { id: string; email: string; "external-id": string };
  }>();

  const accountId = account.data["external-id"];
  const email = account.data.email;

  // Upsert user in D1
  await env.DB.prepare(
    `INSERT INTO users (id, email, created_at, updated_at)
     VALUES (?, ?, unixepoch(), unixepoch())
     ON CONFLICT(id) DO UPDATE SET
       email = excluded.email,
       updated_at = unixepoch()`
  ).bind(accountId, email).run();

  // Store encrypted TastyTrade tokens
  await env.DB.prepare(
    `INSERT OR REPLACE INTO user_oauth_tokens
     (user_id, provider, access_token, refresh_token, expires_at)
     VALUES (?, 'tastytrade', ?, ?, ?)`
  ).bind(
    accountId,
    tokens.access_token,  // Should be encrypted in production
    tokens.refresh_token,
    Date.now() + tokens.expires_in * 1000
  ).run();

  // Create session JWT
  const secret = new TextEncoder().encode(env.JWT_SECRET);
  const sessionToken = await new SignJWT({ sub: accountId, email })
    .setProtectedHeader({ alg: "HS256" })
    .setIssuedAt()
    .setExpirationTime("24h")
    .sign(secret);

  // Return token to client (frontend will store and use for subsequent requests)
  return new Response(JSON.stringify({ token: sessionToken }), {
    headers: { "Content-Type": "application/json" },
  });
}
```

### TastyTrade Token Management

```typescript
// src/auth/tastytrade.ts
export async function getTastyTradeTokens(
  env: Env,
  userId: string
): Promise<OAuthTokens | null> {
  const result = await env.DB.prepare(
    `SELECT access_token, refresh_token, expires_at
     FROM user_oauth_tokens
     WHERE user_id = ? AND provider = 'tastytrade'`
  )
    .bind(userId)
    .first<OAuthTokenRow>();

  if (!result) {
    return null;
  }

  // Check if token needs refresh
  if (Date.now() > result.expires_at) {
    return refreshTastyTradeToken(env, userId, result.refresh_token);
  }

  return {
    accessToken: result.access_token,
    refreshToken: result.refresh_token,
    expiresAt: result.expires_at,
  };
}

async function refreshTastyTradeToken(
  env: Env,
  userId: string,
  refreshToken: string
): Promise<OAuthTokens | null> {
  const response = await fetch("https://api.tastyworks.com/oauth/token", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      grant_type: "refresh_token",
      refresh_token: refreshToken,
      client_id: env.TASTYTRADE_CLIENT_ID,
      client_secret: env.TASTYTRADE_CLIENT_SECRET,
    }),
  });

  if (!response.ok) {
    return null;
  }

  const tokens = await response.json<{
    access_token: string;
    refresh_token: string;
    expires_in: number;
  }>();

  const newTokens = {
    accessToken: tokens.access_token,
    refreshToken: tokens.refresh_token,
    expiresAt: Date.now() + tokens.expires_in * 1000,
  };

  // Update stored tokens
  await env.DB.prepare(
    `UPDATE user_oauth_tokens
     SET access_token = ?, refresh_token = ?, expires_at = ?, updated_at = unixepoch()
     WHERE user_id = ? AND provider = 'tastytrade'`
  ).bind(
    newTokens.accessToken,
    newTokens.refreshToken,
    newTokens.expiresAt,
    userId
  ).run();

  return newTokens;
}
```

## MCP Server Implementation

### Server Factory

```typescript
// src/server/factory.ts
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { registerTools } from "./tools";
import { registerResources } from "./resources";
import { registerPrompts } from "./prompts";

export function createMcpServer(
  env: Env,
  userContext: UserContext
): McpServer {
  const server = new McpServer({
    name: "ttai-mcp-server",
    version: "1.0.0",
  });

  // Create service context with user-scoped bindings
  const services = {
    kv: env.KV,
    db: env.DB,
    r2: env.R2,
    queue: env.QUEUE,
    workflows: env.WORKFLOWS,
    pythonWorker: env.PYTHON_WORKER,
    userId: userContext.userId,
  };

  // Register capabilities
  registerTools(server, services);
  registerResources(server, services);
  registerPrompts(server, services);

  return server;
}
```

### Tool Registration

```typescript
// src/server/tools.ts
import { z } from "zod";

export function registerTools(server: McpServer, services: Services): void {
  // Quote lookup tool
  server.tool(
    "get_quote",
    "Get real-time quote for a symbol",
    {
      symbol: z.string().describe("Stock or ETF symbol"),
    },
    async ({ symbol }) => {
      // Check KV cache first
      const cached = await services.kv.get(`quote:${symbol}`, "json");
      if (cached) {
        return { content: [{ type: "text", text: JSON.stringify(cached) }] };
      }

      // Fetch from Python worker (which calls TastyTrade)
      const response = await services.pythonWorker.fetch(
        new Request("https://internal/quotes", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "X-User-Id": services.userId,
          },
          body: JSON.stringify({ symbols: [symbol] }),
        })
      );

      const quote = await response.json();

      // Cache with short TTL
      await services.kv.put(`quote:${symbol}`, JSON.stringify(quote), {
        expirationTtl: 60, // 1 minute
      });

      return { content: [{ type: "text", text: JSON.stringify(quote) }] };
    }
  );

  // Chart analysis tool - triggers workflow
  server.tool(
    "analyze_chart",
    "Run AI-powered chart analysis on a symbol",
    {
      symbol: z.string().describe("Stock or ETF symbol"),
      timeframe: z.enum(["intraday", "daily", "weekly"]).default("daily"),
    },
    async ({ symbol, timeframe }) => {
      // Start Cloudflare Workflow for durable execution
      const instance = await services.workflows.create({
        params: {
          type: "chart_analysis",
          userId: services.userId,
          symbol,
          timeframe,
        },
      });

      // Wait for completion (or timeout)
      const result = await instance.status();

      if (result.status === "complete") {
        return {
          content: [{ type: "text", text: JSON.stringify(result.output) }],
        };
      }

      return {
        content: [
          {
            type: "text",
            text: `Analysis started. Workflow ID: ${instance.id}`,
          },
        ],
      };
    }
  );

  // Full analysis tool
  server.tool(
    "run_full_analysis",
    "Run comprehensive analysis including chart, options, and research",
    {
      symbol: z.string().describe("Stock or ETF symbol"),
      strategy: z.enum(["csp", "covered_call", "spread"]).default("csp"),
    },
    async ({ symbol, strategy }) => {
      const instance = await services.workflows.create({
        params: {
          type: "full_analysis",
          userId: services.userId,
          symbol,
          strategy,
        },
      });

      return {
        content: [
          {
            type: "text",
            text: `Full analysis started. Workflow ID: ${instance.id}. Use get_workflow_status to check progress.`,
          },
        ],
      };
    }
  );

  // Workflow status tool
  server.tool(
    "get_workflow_status",
    "Check status of a running workflow",
    {
      workflowId: z.string().describe("Workflow instance ID"),
    },
    async ({ workflowId }) => {
      const instance = services.workflows.get(workflowId);
      const status = await instance.status();

      return {
        content: [{ type: "text", text: JSON.stringify(status) }],
      };
    }
  );
}
```

### Resource Registration

```typescript
// src/server/resources.ts
export function registerResources(server: McpServer, services: Services): void {
  // Portfolio resource
  server.resource(
    "portfolio://positions",
    "Current portfolio positions",
    async () => {
      const positions = await services.db
        .prepare(
          `SELECT * FROM positions WHERE user_id = ? AND status = 'open'`
        )
        .bind(services.userId)
        .all();

      return {
        contents: [
          {
            uri: "portfolio://positions",
            mimeType: "application/json",
            text: JSON.stringify(positions.results),
          },
        ],
      };
    }
  );

  // Knowledge base resources
  server.resource(
    "knowledge://options/strategies",
    "Options trading strategies knowledge",
    async () => {
      const doc = await services.r2.get("knowledge/options/strategies.md");
      const content = await doc?.text();

      return {
        contents: [
          {
            uri: "knowledge://options/strategies",
            mimeType: "text/markdown",
            text: content || "Not found",
          },
        ],
      };
    }
  );

  // Analysis history resource
  server.resource(
    "history://analyses",
    "Recent analysis results",
    async () => {
      const analyses = await services.db
        .prepare(
          `SELECT * FROM analyses
           WHERE user_id = ?
           ORDER BY created_at DESC
           LIMIT 20`
        )
        .bind(services.userId)
        .all();

      return {
        contents: [
          {
            uri: "history://analyses",
            mimeType: "application/json",
            text: JSON.stringify(analyses.results),
          },
        ],
      };
    }
  );
}
```

## Cloudflare Bindings

### wrangler.toml Configuration

```toml
# wrangler.toml
name = "ttai-mcp-server"
main = "src/index.ts"
compatibility_date = "2024-01-01"
compatibility_flags = ["nodejs_compat"]

# KV Namespace for caching
[[kv_namespaces]]
binding = "KV"
id = "your-kv-namespace-id"

# D1 Database
[[d1_databases]]
binding = "DB"
database_name = "ttai"
database_id = "your-d1-database-id"

# Durable Objects
[[durable_objects.bindings]]
name = "SESSIONS"
class_name = "SessionDurableObject"

# Workflows
[[workflows]]
binding = "WORKFLOWS"
name = "ttai-workflow"
class_name = "TTAIWorkflow"

# Service binding to Python Worker
[[services]]
binding = "PYTHON_WORKER"
service = "ttai-python-worker"

# Queue for async processing
[[queues.producers]]
binding = "QUEUE"
queue = "ttai-tasks"

# R2 Bucket for storage
[[r2_buckets]]
binding = "R2"
bucket_name = "ttai-storage"

# Environment variables
[vars]
ENVIRONMENT = "production"

# Secrets (set via wrangler secret)
# JWT_SECRET
# TASTYTRADE_CLIENT_ID
# TASTYTRADE_CLIENT_SECRET
```

## Session Management with Durable Objects

### Session Durable Object

```typescript
// src/durableObjects/session.ts
export class SessionDurableObject implements DurableObject {
  private state: DurableObjectState;
  private sessions: Map<string, WebSocket> = new Map();

  constructor(state: DurableObjectState, env: Env) {
    this.state = state;
  }

  async fetch(request: Request): Promise<Response> {
    const url = new URL(request.url);

    if (url.pathname === "/websocket") {
      return this.handleWebSocket(request);
    }

    if (url.pathname === "/broadcast") {
      return this.handleBroadcast(request);
    }

    return new Response("Not Found", { status: 404 });
  }

  async handleWebSocket(request: Request): Promise<Response> {
    const upgradeHeader = request.headers.get("Upgrade");
    if (upgradeHeader !== "websocket") {
      return new Response("Expected WebSocket", { status: 426 });
    }

    const [client, server] = Object.values(new WebSocketPair());

    // Use hibernation for cost efficiency
    this.state.acceptWebSocket(server);

    const sessionId = crypto.randomUUID();
    server.serializeAttachment({ sessionId });

    return new Response(null, {
      status: 101,
      webSocket: client,
    });
  }

  async webSocketMessage(ws: WebSocket, message: string | ArrayBuffer): Promise<void> {
    const data = JSON.parse(message as string);

    // Handle incoming messages
    if (data.type === "subscribe") {
      const attachment = ws.deserializeAttachment() as { sessionId: string; subscriptions?: string[] };
      attachment.subscriptions = data.channels;
      ws.serializeAttachment(attachment);
    }
  }

  async webSocketClose(ws: WebSocket): Promise<void> {
    // Cleanup handled automatically by hibernation
  }

  async handleBroadcast(request: Request): Promise<Response> {
    const { channel, message } = await request.json<{
      channel: string;
      message: unknown;
    }>();

    // Broadcast to all connected WebSockets subscribed to this channel
    for (const ws of this.state.getWebSockets()) {
      const attachment = ws.deserializeAttachment() as {
        subscriptions?: string[];
      };

      if (attachment.subscriptions?.includes(channel)) {
        ws.send(JSON.stringify({ channel, data: message }));
      }
    }

    return new Response("ok");
  }
}
```

## Multi-Tenancy Patterns

### User-Scoped Queries

All database queries include user_id for row-level isolation:

```typescript
// src/services/database.ts
export class UserScopedDB {
  constructor(
    private db: D1Database,
    private userId: string
  ) {}

  async getPositions(): Promise<Position[]> {
    const result = await this.db
      .prepare("SELECT * FROM positions WHERE user_id = ?")
      .bind(this.userId)
      .all();
    return result.results as Position[];
  }

  async getAnalyses(limit = 20): Promise<Analysis[]> {
    const result = await this.db
      .prepare(
        `SELECT * FROM analyses
         WHERE user_id = ?
         ORDER BY created_at DESC
         LIMIT ?`
      )
      .bind(this.userId, limit)
      .all();
    return result.results as Analysis[];
  }

  async saveAnalysis(analysis: Omit<Analysis, "id" | "user_id">): Promise<void> {
    await this.db
      .prepare(
        `INSERT INTO analyses (user_id, symbol, type, result, created_at)
         VALUES (?, ?, ?, ?, ?)`
      )
      .bind(
        this.userId,
        analysis.symbol,
        analysis.type,
        JSON.stringify(analysis.result),
        Date.now()
      )
      .run();
  }
}
```

### User-Scoped Cache Keys

KV cache keys are namespaced by user:

```typescript
// src/services/cache.ts
export class UserScopedCache {
  constructor(
    private kv: KVNamespace,
    private userId: string
  ) {}

  private key(base: string): string {
    return `user:${this.userId}:${base}`;
  }

  async get<T>(key: string): Promise<T | null> {
    return this.kv.get(this.key(key), "json");
  }

  async set(key: string, value: unknown, ttl?: number): Promise<void> {
    await this.kv.put(this.key(key), JSON.stringify(value), {
      expirationTtl: ttl,
    });
  }

  async delete(key: string): Promise<void> {
    await this.kv.delete(this.key(key));
  }
}
```

## Error Handling

```typescript
// src/utils/errors.ts
export class TTAIError extends Error {
  constructor(
    message: string,
    public code: string,
    public statusCode: number = 500,
    public retryable: boolean = false
  ) {
    super(message);
    this.name = "TTAIError";
  }

  toJSON() {
    return {
      error: {
        code: this.code,
        message: this.message,
        retryable: this.retryable,
      },
    };
  }
}

export class AuthenticationError extends TTAIError {
  constructor(message = "Authentication required") {
    super(message, "AUTHENTICATION_ERROR", 401, false);
  }
}

export class RateLimitError extends TTAIError {
  constructor(retryAfter: number) {
    super(`Rate limited. Retry after ${retryAfter}s`, "RATE_LIMIT", 429, true);
  }
}

export class ValidationError extends TTAIError {
  constructor(message: string) {
    super(message, "VALIDATION_ERROR", 400, false);
  }
}
```

## Cross-References

- [Workflow Orchestration](./02-workflow-orchestration.md) - Cloudflare Workflows for durable execution
- [Python Workers](./03-python-workers.md) - TastyTrade API and AI agents
- [Data Layer](./05-data-layer.md) - KV, D1, R2 storage patterns
- [Integration Patterns](./09-integration-patterns.md) - Worker-to-Worker communication
