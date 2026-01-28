# Integration Patterns

## Overview

This document covers communication patterns between Cloudflare components: Worker-to-Worker service bindings, TypeScript to Python Worker communication, Durable Object patterns, Queue message handling, and data serialization conventions.

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                     Integration Patterns                             │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  1. Service Bindings (Synchronous)                                  │
│  ┌──────────────┐    fetch()    ┌──────────────┐                   │
│  │  TypeScript  │ ────────────→ │    Python    │                   │
│  │  MCP Server  │ ←──────────── │   Worker     │                   │
│  └──────────────┘   Response    └──────────────┘                   │
│                                                                      │
│  2. Durable Objects (Stateful)                                      │
│  ┌──────────────┐    fetch()    ┌──────────────┐                   │
│  │   Worker     │ ────────────→ │   Durable    │                   │
│  │              │ ←──────────── │    Object    │                   │
│  └──────────────┘               └──────────────┘                   │
│                                                                      │
│  3. Queues (Async)                                                  │
│  ┌──────────────┐    send()     ┌──────────────┐                   │
│  │   Producer   │ ────────────→ │    Queue     │ → Consumer        │
│  └──────────────┘               └──────────────┘                   │
│                                                                      │
│  4. KV/D1 (Shared State)                                           │
│  ┌──────────────┐               ┌──────────────┐                   │
│  │  Worker A    │ ←── KV/D1 ──→ │  Worker B    │                   │
│  └──────────────┘               └──────────────┘                   │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

## Worker-to-Worker Service Bindings

### Configuration

```toml
# wrangler.toml (MCP Server)
[[services]]
binding = "PYTHON_WORKER"
service = "ttai-python-worker"
```

### TypeScript to Python Communication

```typescript
// src/services/pythonClient.ts
export class PythonWorkerClient {
  constructor(private fetcher: Fetcher) {}

  async getQuotes(symbols: string[], userId: string): Promise<Record<string, Quote>> {
    const response = await this.fetcher.fetch(
      new Request("https://internal/quotes", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-User-Id": userId,
        },
        body: JSON.stringify({ symbols }),
      })
    );

    if (!response.ok) {
      const error = await response.json<{ error: string }>();
      throw new Error(error.error);
    }

    return response.json();
  }

  async analyzeChart(
    symbol: string,
    userId: string,
    timeframe: string = "daily"
  ): Promise<ChartAnalysis> {
    const response = await this.fetcher.fetch(
      new Request("https://internal/analyze/chart", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-User-Id": userId,
        },
        body: JSON.stringify({ symbol, timeframe }),
      })
    );

    if (!response.ok) {
      throw new Error(`Analysis failed: ${response.status}`);
    }

    return response.json();
  }

  async analyzeOptions(
    symbol: string,
    userId: string,
    chartContext: ChartAnalysis,
    strategy: string = "csp"
  ): Promise<OptionsAnalysis> {
    const response = await this.fetcher.fetch(
      new Request("https://internal/analyze/options", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-User-Id": userId,
        },
        body: JSON.stringify({
          symbol,
          chartContext,
          strategy,
        }),
      })
    );

    return response.json();
  }
}
```

### Python Request Handler

```python
# src/main.py
from js import Response, Request
import json

async def on_fetch(request, env):
    """Main entry point for Python Worker."""
    url = request.url
    path = url.split("/")[-1] if "/" in url else ""
    user_id = request.headers.get("X-User-Id")

    try:
        body = json.loads(await request.text()) if request.method == "POST" else {}

        if path == "quotes":
            return await handle_quotes(body, env, user_id)
        elif path == "chart":
            return await handle_chart_analysis(body, env, user_id)
        elif path == "options":
            return await handle_options_analysis(body, env, user_id)
        else:
            return json_response({"error": f"Unknown path: {path}"}, 404)

    except Exception as e:
        return json_response({"error": str(e)}, 500)

def json_response(data, status=200):
    return Response.new(
        json.dumps(data),
        status=status,
        headers={"Content-Type": "application/json"}
    )
```

## Durable Object Patterns

### Getting a Durable Object Instance

```typescript
// By name (deterministic ID)
const id = env.PORTFOLIO_MONITOR.idFromName(userId);
const monitor = env.PORTFOLIO_MONITOR.get(id);

// By unique ID
const id = env.SESSIONS.newUniqueId();
const session = env.SESSIONS.get(id);

// From string ID
const id = env.SESSIONS.idFromString(sessionIdString);
const session = env.SESSIONS.get(id);
```

### Making Requests to Durable Objects

```typescript
// src/services/monitorService.ts
export class MonitorService {
  constructor(private namespace: DurableObjectNamespace) {}

  async startMonitor(
    userId: string,
    positions: Position[],
    alertRules: AlertRule[]
  ): Promise<void> {
    const id = this.namespace.idFromName(userId);
    const monitor = this.namespace.get(id);

    await monitor.fetch(
      new Request("https://internal/start", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          userId,
          positions,
          alertRules,
          checkIntervalMs: 60000,
        }),
      })
    );
  }

  async stopMonitor(userId: string): Promise<void> {
    const id = this.namespace.idFromName(userId);
    const monitor = this.namespace.get(id);

    await monitor.fetch(
      new Request("https://internal/stop", { method: "POST" })
    );
  }

  async getStatus(userId: string): Promise<MonitorStatus> {
    const id = this.namespace.idFromName(userId);
    const monitor = this.namespace.get(id);

    const response = await monitor.fetch(
      new Request("https://internal/status")
    );

    return response.json();
  }
}
```

### Durable Object Response Pattern

```typescript
// src/durableObjects/base.ts
export abstract class BaseDurableObject implements DurableObject {
  constructor(
    protected state: DurableObjectState,
    protected env: Env
  ) {}

  async fetch(request: Request): Promise<Response> {
    const url = new URL(request.url);

    try {
      const handler = this.getHandler(url.pathname);
      if (!handler) {
        return this.notFound();
      }

      const result = await handler.call(this, request);
      return this.json(result);
    } catch (error) {
      return this.error(error as Error);
    }
  }

  protected abstract getHandler(path: string): ((req: Request) => Promise<any>) | null;

  protected json(data: unknown, status = 200): Response {
    return Response.json(data, { status });
  }

  protected notFound(): Response {
    return Response.json({ error: "Not Found" }, { status: 404 });
  }

  protected error(err: Error): Response {
    console.error("Durable Object error:", err);
    return Response.json(
      { error: err.message, retryable: true },
      { status: 500 }
    );
  }
}
```

## Queue Message Patterns

### Message Type Definitions

```typescript
// src/types/messages.ts
export type QueueMessage =
  | QuoteUpdateMessage
  | AnalysisRequestMessage
  | AnalysisCompleteMessage
  | AlertTriggeredMessage
  | NotificationMessage;

interface BaseMessage {
  type: string;
  timestamp: number;
  correlationId?: string;
}

export interface QuoteUpdateMessage extends BaseMessage {
  type: "quote_update";
  symbol: string;
  price: number;
  change: number;
}

export interface AnalysisRequestMessage extends BaseMessage {
  type: "analysis_request";
  userId: string;
  symbol: string;
  analysisType: "chart" | "options" | "full";
}

export interface AnalysisCompleteMessage extends BaseMessage {
  type: "analysis_complete";
  userId: string;
  symbol: string;
  workflowId: string;
  recommendation: string;
}

export interface AlertTriggeredMessage extends BaseMessage {
  type: "alert_triggered";
  userId: string;
  alertId: number;
  symbol: string;
  condition: string;
  threshold: number;
  currentValue: number;
}

export interface NotificationMessage extends BaseMessage {
  type: "notification";
  userId: string;
  channel: "discord" | "email" | "push";
  title: string;
  body: string;
  data?: Record<string, unknown>;
}
```

### Sending Messages

```typescript
// src/services/queue.ts
export class QueueService {
  constructor(private queue: Queue<QueueMessage>) {}

  async sendAnalysisRequest(
    userId: string,
    symbol: string,
    analysisType: "chart" | "options" | "full"
  ): Promise<void> {
    await this.queue.send({
      type: "analysis_request",
      timestamp: Date.now(),
      correlationId: crypto.randomUUID(),
      userId,
      symbol,
      analysisType,
    });
  }

  async sendNotification(
    userId: string,
    channel: "discord" | "email" | "push",
    title: string,
    body: string
  ): Promise<void> {
    await this.queue.send({
      type: "notification",
      timestamp: Date.now(),
      userId,
      channel,
      title,
      body,
    });
  }

  // Batch send for efficiency
  async sendBatch(messages: QueueMessage[]): Promise<void> {
    const batches = [];
    for (let i = 0; i < messages.length; i += 100) {
      batches.push(messages.slice(i, i + 100));
    }

    for (const batch of batches) {
      await this.queue.sendBatch(
        batch.map((body) => ({ body }))
      );
    }
  }
}
```

### Consuming Messages

```typescript
// src/index.ts
export default {
  async queue(
    batch: MessageBatch<QueueMessage>,
    env: Env,
    ctx: ExecutionContext
  ): Promise<void> {
    const handlers: Record<string, (msg: any, env: Env) => Promise<void>> = {
      analysis_request: handleAnalysisRequest,
      analysis_complete: handleAnalysisComplete,
      alert_triggered: handleAlertTriggered,
      notification: handleNotification,
    };

    for (const message of batch.messages) {
      const handler = handlers[message.body.type];

      if (!handler) {
        console.warn(`Unknown message type: ${message.body.type}`);
        message.ack();
        continue;
      }

      try {
        await handler(message.body, env);
        message.ack();
      } catch (error) {
        console.error(`Failed to process message:`, error);

        // Retry transient errors
        if (message.body.timestamp > Date.now() - 3600000) {
          message.retry({ delaySeconds: 30 });
        } else {
          // Too old, dead-letter
          console.error("Message expired, dropping:", message.body);
          message.ack();
        }
      }
    }
  },
};
```

## Data Serialization

### camelCase to snake_case Conversion

```typescript
// src/utils/serialization.ts
export function toSnakeCase(obj: Record<string, any>): Record<string, any> {
  const result: Record<string, any> = {};

  for (const [key, value] of Object.entries(obj)) {
    const snakeKey = key.replace(/([A-Z])/g, "_$1").toLowerCase();

    if (value && typeof value === "object" && !Array.isArray(value)) {
      result[snakeKey] = toSnakeCase(value);
    } else if (Array.isArray(value)) {
      result[snakeKey] = value.map((item) =>
        typeof item === "object" ? toSnakeCase(item) : item
      );
    } else {
      result[snakeKey] = value;
    }
  }

  return result;
}

export function toCamelCase(obj: Record<string, any>): Record<string, any> {
  const result: Record<string, any> = {};

  for (const [key, value] of Object.entries(obj)) {
    const camelKey = key.replace(/_([a-z])/g, (_, letter) => letter.toUpperCase());

    if (value && typeof value === "object" && !Array.isArray(value)) {
      result[camelKey] = toCamelCase(value);
    } else if (Array.isArray(value)) {
      result[camelKey] = value.map((item) =>
        typeof item === "object" ? toCamelCase(item) : item
      );
    } else {
      result[camelKey] = value;
    }
  }

  return result;
}
```

### Usage in Service Calls

```typescript
// TypeScript → Python (convert to snake_case)
const response = await fetcher.fetch(
  new Request("https://internal/analyze", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(toSnakeCase({
      symbol: "AAPL",
      timeframe: "daily",
      chartContext: {
        supportLevels: [150, 145],
        resistanceLevels: [160, 165],
      },
    })),
  })
);

// Python response → TypeScript (convert to camelCase)
const result = toCamelCase(await response.json());
// result.supportLevels, result.resistanceLevels
```

### Python Side

```python
# src/utils/case.py
import re

def to_snake_case(obj):
    """Convert camelCase keys to snake_case."""
    if isinstance(obj, dict):
        return {
            re.sub(r'([A-Z])', r'_\1', k).lower().lstrip('_'): to_snake_case(v)
            for k, v in obj.items()
        }
    elif isinstance(obj, list):
        return [to_snake_case(item) for item in obj]
    return obj

def to_camel_case(obj):
    """Convert snake_case keys to camelCase."""
    if isinstance(obj, dict):
        return {
            re.sub(r'_([a-z])', lambda m: m.group(1).upper(), k): to_camel_case(v)
            for k, v in obj.items()
        }
    elif isinstance(obj, list):
        return [to_camel_case(item) for item in obj]
    return obj
```

## Error Handling

### Standardized Error Response

```typescript
// src/types/errors.ts
export interface ErrorResponse {
  error: {
    code: string;
    message: string;
    retryable: boolean;
    details?: Record<string, unknown>;
  };
}

export class ServiceError extends Error {
  constructor(
    message: string,
    public code: string,
    public statusCode: number = 500,
    public retryable: boolean = false,
    public details?: Record<string, unknown>
  ) {
    super(message);
  }

  toResponse(): Response {
    return Response.json(
      {
        error: {
          code: this.code,
          message: this.message,
          retryable: this.retryable,
          details: this.details,
        },
      },
      { status: this.statusCode }
    );
  }
}

// Common error types
export class ValidationError extends ServiceError {
  constructor(message: string, details?: Record<string, unknown>) {
    super(message, "VALIDATION_ERROR", 400, false, details);
  }
}

export class AuthenticationError extends ServiceError {
  constructor(message: string = "Authentication required") {
    super(message, "AUTHENTICATION_ERROR", 401, false);
  }
}

export class NotFoundError extends ServiceError {
  constructor(resource: string) {
    super(`${resource} not found`, "NOT_FOUND", 404, false);
  }
}

export class RateLimitError extends ServiceError {
  constructor(retryAfter: number = 60) {
    super(
      `Rate limited. Retry after ${retryAfter}s`,
      "RATE_LIMIT",
      429,
      true,
      { retryAfter }
    );
  }
}
```

### Error Handling in Python

```python
# src/utils/errors.py
from js import Response
import json

class ServiceError(Exception):
    def __init__(
        self,
        message: str,
        code: str,
        status_code: int = 500,
        retryable: bool = False,
        details: dict = None,
    ):
        super().__init__(message)
        self.code = code
        self.status_code = status_code
        self.retryable = retryable
        self.details = details or {}

    def to_response(self):
        return Response.new(
            json.dumps({
                "error": {
                    "code": self.code,
                    "message": str(self),
                    "retryable": self.retryable,
                    "details": self.details,
                }
            }),
            status=self.status_code,
            headers={"Content-Type": "application/json"}
        )

class ValidationError(ServiceError):
    def __init__(self, message: str, details: dict = None):
        super().__init__(message, "VALIDATION_ERROR", 400, False, details)

class AuthenticationError(ServiceError):
    def __init__(self, message: str = "Authentication required"):
        super().__init__(message, "AUTHENTICATION_ERROR", 401, False)

class NotFoundError(ServiceError):
    def __init__(self, resource: str):
        super().__init__(f"{resource} not found", "NOT_FOUND", 404, False)
```

## Timeout and Retry Patterns

### TypeScript Fetch with Timeout

```typescript
// src/utils/fetch.ts
export async function fetchWithTimeout(
  fetcher: Fetcher,
  request: Request,
  timeoutMs: number = 30000
): Promise<Response> {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs);

  try {
    const response = await fetcher.fetch(request, {
      signal: controller.signal,
    });
    return response;
  } finally {
    clearTimeout(timeoutId);
  }
}
```

### Retry with Exponential Backoff

```typescript
// src/utils/retry.ts
export async function withRetry<T>(
  fn: () => Promise<T>,
  options: {
    maxRetries?: number;
    initialDelayMs?: number;
    maxDelayMs?: number;
    shouldRetry?: (error: Error) => boolean;
  } = {}
): Promise<T> {
  const {
    maxRetries = 3,
    initialDelayMs = 1000,
    maxDelayMs = 30000,
    shouldRetry = () => true,
  } = options;

  let lastError: Error | undefined;

  for (let attempt = 0; attempt <= maxRetries; attempt++) {
    try {
      return await fn();
    } catch (error) {
      lastError = error as Error;

      if (attempt === maxRetries || !shouldRetry(lastError)) {
        throw lastError;
      }

      const delay = Math.min(
        initialDelayMs * Math.pow(2, attempt),
        maxDelayMs
      );

      await new Promise((resolve) => setTimeout(resolve, delay));
    }
  }

  throw lastError;
}
```

## Cross-References

- [MCP Server Design](./01-mcp-server-design.md) - Service bindings
- [Python Workers](./03-python-workers.md) - Python request handling
- [Data Layer](./05-data-layer.md) - Queue patterns
- [Background Tasks](./06-background-tasks.md) - Durable Object patterns
