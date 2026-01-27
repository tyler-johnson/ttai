# TypeScript-Python Integration Patterns

## Overview

The TastyTrade AI system uses TypeScript for the MCP server and Python for workers and activities. This document covers the communication patterns, data serialization, error handling, and timeout coordination between these components.

## Communication Patterns

```
┌─────────────────────────────────────────────────────────────────────┐
│                    Communication Patterns                            │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  1. Temporal Workflow/Activity Bridge (Primary)                      │
│  ┌──────────────┐    Temporal    ┌──────────────┐                   │
│  │  TypeScript  │ ─────────────→ │    Python    │                   │
│  │  MCP Server  │    Protocol    │   Workers    │                   │
│  │   (Client)   │ ←───────────── │ (Activities) │                   │
│  └──────────────┘                └──────────────┘                   │
│                                                                      │
│  2. Redis Pub/Sub (Real-time Data)                                  │
│  ┌──────────────┐     Redis      ┌──────────────┐                   │
│  │  TypeScript  │ ←───────────── │    Python    │                   │
│  │   (Sub)      │    Pub/Sub     │   (Pub)      │                   │
│  └──────────────┘                └──────────────┘                   │
│                                                                      │
│  3. Redis Cache (Shared State)                                       │
│  ┌──────────────┐                ┌──────────────┐                   │
│  │  TypeScript  │ ←─── Redis ──→ │    Python    │                   │
│  │   (Read)     │     Cache      │   (Write)    │                   │
│  └──────────────┘                └──────────────┘                   │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

## Temporal Workflow/Activity Bridge

### TypeScript Client

```typescript
// src/temporal/client.ts
import { Client, Connection, WorkflowClient } from "@temporalio/client";

export class TemporalClient {
  private client: Client;
  private workflowClient: WorkflowClient;

  async connect(address: string = "localhost:7233"): Promise<void> {
    const connection = await Connection.connect({
      address,
    });

    this.client = new Client({
      connection,
      namespace: process.env.TEMPORAL_NAMESPACE || "default",
    });

    this.workflowClient = this.client.workflow;
  }

  // Start a workflow and wait for result
  async executeWorkflow<TResult, TArgs extends unknown[]>(
    workflowName: string,
    args: TArgs,
    options?: {
      workflowId?: string;
      taskQueue?: string;
      timeout?: number;
    }
  ): Promise<TResult> {
    const handle = await this.workflowClient.start(workflowName, {
      taskQueue: options?.taskQueue || "ttai-queue",
      workflowId: options?.workflowId || `${workflowName}-${Date.now()}`,
      args,
    });

    // Wait for result with optional timeout
    if (options?.timeout) {
      const timeoutPromise = new Promise<never>((_, reject) =>
        setTimeout(
          () => reject(new Error("Workflow timeout")),
          options.timeout
        )
      );
      return Promise.race([handle.result(), timeoutPromise]);
    }

    return handle.result();
  }

  // Start workflow without waiting (fire-and-forget)
  async startWorkflow<TArgs extends unknown[]>(
    workflowName: string,
    args: TArgs,
    options?: {
      workflowId?: string;
      taskQueue?: string;
    }
  ): Promise<string> {
    const handle = await this.workflowClient.start(workflowName, {
      taskQueue: options?.taskQueue || "ttai-queue",
      workflowId: options?.workflowId || `${workflowName}-${Date.now()}`,
      args,
    });

    return handle.workflowId;
  }

  // Get workflow handle for signals/queries
  getWorkflowHandle(workflowId: string) {
    return this.workflowClient.getHandle(workflowId);
  }

  // Send signal to workflow
  async signalWorkflow<T>(
    workflowId: string,
    signalName: string,
    args: T
  ): Promise<void> {
    const handle = this.workflowClient.getHandle(workflowId);
    await handle.signal(signalName, args);
  }

  // Query workflow state
  async queryWorkflow<TResult>(
    workflowId: string,
    queryName: string
  ): Promise<TResult> {
    const handle = this.workflowClient.getHandle(workflowId);
    return handle.query(queryName);
  }
}
```

### Tool Implementation Pattern

```typescript
// src/tools/agents.ts
import { TemporalClient } from "../temporal/client";
import {
  ChartAnalysisParams,
  ChartAnalysisResult,
  FullAnalysisParams,
  FullAnalysisResult,
} from "../temporal/types";

export class AgentTools {
  constructor(private temporal: TemporalClient) {}

  async analyzeChart(params: ChartAnalysisParams): Promise<ChartAnalysisResult> {
    return this.temporal.executeWorkflow<ChartAnalysisResult, [ChartAnalysisParams]>(
      "ChartAnalysisWorkflow",
      [params],
      {
        workflowId: `chart-${params.symbol}-${Date.now()}`,
        timeout: 300000, // 5 minutes
      }
    );
  }

  async runFullAnalysis(params: FullAnalysisParams): Promise<FullAnalysisResult> {
    return this.temporal.executeWorkflow<FullAnalysisResult, [FullAnalysisParams]>(
      "FullAnalysisWorkflow",
      [params],
      {
        workflowId: `full-${params.symbol}-${Date.now()}`,
        timeout: 900000, // 15 minutes
      }
    );
  }

  async findCSPOpportunities(params: CSPScreenerParams): Promise<CSPScreenerResult> {
    // Start workflow without waiting (may take a long time)
    const workflowId = await this.temporal.startWorkflow(
      "CSPScreenerWorkflow",
      [params],
      {
        workflowId: `csp-screener-${Date.now()}`,
      }
    );

    // Return workflow ID so caller can check status later
    return { workflowId, status: "started" };
  }
}
```

## Data Serialization Contracts

### Shared Type Definitions

Both TypeScript and Python need to agree on data structures:

```typescript
// src/temporal/types.ts

// ==================== Input Types ====================

export interface ChartAnalysisParams {
  symbol: string;
  timeframe: "intraday" | "daily" | "weekly";
  analysisDepth: "quick" | "standard" | "deep";
  includeChartImage?: boolean;
}

export interface OptionsAnalysisParams {
  symbol: string;
  strategy: "csp" | "covered_call" | "spread";
  chartContext?: ChartContext;
  constraints?: OptionsConstraints;
}

export interface ChartContext {
  trendDirection: string;
  trendQuality: string;
  supportLevels: SupportLevel[];
  fibConfluenceZones: FibZone[];
}

export interface OptionsConstraints {
  maxDelta?: number;
  minRoc?: number;
  dteMin?: number;
  dteMax?: number;
}

// ==================== Output Types ====================

export interface ChartAnalysisResult {
  symbol: string;
  recommendation: "bullish" | "bearish" | "neutral" | "reject";
  trendDirection: "up" | "down" | "sideways";
  trendQuality: "strong" | "moderate" | "weak";
  supportLevels: SupportLevel[];
  resistanceLevels: ResistanceLevel[];
  fibConfluenceZones: FibZone[];
  extensionRisk: "low" | "moderate" | "high";
  chartNotes: string;
  toolCallsMade: number;
}

export interface SupportLevel {
  price: number;
  strength: "strong" | "moderate" | "weak";
  type: string;
}

export interface ResistanceLevel {
  price: number;
  strength: "strong" | "moderate" | "weak";
  type: string;
}

export interface FibZone {
  price: number;
  levels: string[];
}

export interface OptionsAnalysisResult {
  symbol: string;
  recommendation: "select" | "reject";
  bestStrike: number | null;
  bestExpiration: string | null;
  dte: number | null;
  premium: number | null;
  weeklyRoc: number | null;
  annualizedRoc: number | null;
  delta: number | null;
  gamma: number | null;
  theta: number | null;
  ivHvRatio: number | null;
  liquidityScore: "excellent" | "good" | "fair" | "poor";
  alternativeStrikes: AlternativeStrike[];
  rationale: string;
  optionsNotes: string;
  toolCallsMade: number;
}

export interface AlternativeStrike {
  strike: number;
  expiration: string;
  roc: number;
  delta: number;
}

export interface FullAnalysisResult {
  symbol: string;
  overallRecommendation: "strong_select" | "select" | "neutral" | "reject";
  chartAnalysis: ChartAnalysisResult | null;
  optionsAnalysis: OptionsAnalysisResult | null;
  researchAnalysis: ResearchAnalysisResult | null;
  synthesizedRationale: string | null;
  suggestedPosition: SuggestedPosition | null;
  rejectReason: string | null;
}
```

```python
# shared/types.py
from dataclasses import dataclass, asdict, field
from typing import Optional, List, Literal
from datetime import datetime
import json

# ==================== Input Types ====================

@dataclass
class ChartAnalysisParams:
    symbol: str
    timeframe: Literal["intraday", "daily", "weekly"] = "daily"
    analysis_depth: Literal["quick", "standard", "deep"] = "standard"
    include_chart_image: bool = True

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "ChartAnalysisParams":
        # Handle camelCase from TypeScript
        return cls(
            symbol=data["symbol"],
            timeframe=data.get("timeframe", "daily"),
            analysis_depth=data.get("analysisDepth", data.get("analysis_depth", "standard")),
            include_chart_image=data.get("includeChartImage", data.get("include_chart_image", True)),
        )

@dataclass
class OptionsConstraints:
    max_delta: float = 0.30
    min_roc: float = 0.5
    dte_min: int = 14
    dte_max: int = 45

    @classmethod
    def from_dict(cls, data: dict) -> "OptionsConstraints":
        return cls(
            max_delta=data.get("maxDelta", data.get("max_delta", 0.30)),
            min_roc=data.get("minRoc", data.get("min_roc", 0.5)),
            dte_min=data.get("dteMin", data.get("dte_min", 14)),
            dte_max=data.get("dteMax", data.get("dte_max", 45)),
        )

# ==================== Output Types ====================

@dataclass
class SupportLevel:
    price: float
    strength: Literal["strong", "moderate", "weak"]
    type: str

    def to_dict(self) -> dict:
        return asdict(self)

@dataclass
class ChartAnalysisResult:
    symbol: str
    recommendation: Literal["bullish", "bearish", "neutral", "reject"]
    trend_direction: Literal["up", "down", "sideways"]
    trend_quality: Literal["strong", "moderate", "weak"]
    support_levels: List[dict] = field(default_factory=list)
    resistance_levels: List[dict] = field(default_factory=list)
    fib_confluence_zones: List[dict] = field(default_factory=list)
    extension_risk: Literal["low", "moderate", "high"] = "moderate"
    chart_notes: str = ""
    tool_calls_made: int = 0

    def to_dict(self) -> dict:
        """Convert to dict with camelCase keys for TypeScript."""
        return {
            "symbol": self.symbol,
            "recommendation": self.recommendation,
            "trendDirection": self.trend_direction,
            "trendQuality": self.trend_quality,
            "supportLevels": self.support_levels,
            "resistanceLevels": self.resistance_levels,
            "fibConfluenceZones": self.fib_confluence_zones,
            "extensionRisk": self.extension_risk,
            "chartNotes": self.chart_notes,
            "toolCallsMade": self.tool_calls_made,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict())

@dataclass
class OptionsAnalysisResult:
    symbol: str
    recommendation: Literal["select", "reject"]
    best_strike: Optional[float] = None
    best_expiration: Optional[str] = None
    dte: Optional[int] = None
    premium: Optional[float] = None
    weekly_roc: Optional[float] = None
    annualized_roc: Optional[float] = None
    delta: Optional[float] = None
    gamma: Optional[float] = None
    theta: Optional[float] = None
    iv_hv_ratio: Optional[float] = None
    liquidity_score: str = "unknown"
    alternative_strikes: List[dict] = field(default_factory=list)
    rationale: str = ""
    options_notes: str = ""
    tool_calls_made: int = 0

    def to_dict(self) -> dict:
        """Convert to dict with camelCase keys for TypeScript."""
        return {
            "symbol": self.symbol,
            "recommendation": self.recommendation,
            "bestStrike": self.best_strike,
            "bestExpiration": self.best_expiration,
            "dte": self.dte,
            "premium": self.premium,
            "weeklyRoc": self.weekly_roc,
            "annualizedRoc": self.annualized_roc,
            "delta": self.delta,
            "gamma": self.gamma,
            "theta": self.theta,
            "ivHvRatio": self.iv_hv_ratio,
            "liquidityScore": self.liquidity_score,
            "alternativeStrikes": self.alternative_strikes,
            "rationale": self.rationale,
            "optionsNotes": self.options_notes,
            "toolCallsMade": self.tool_calls_made,
        }
```

### Serialization Utilities

```python
# shared/serialization.py
import json
from datetime import datetime, date
from decimal import Decimal
from dataclasses import asdict, is_dataclass
from typing import Any

def serialize_for_temporal(obj: Any) -> Any:
    """
    Serialize Python objects for Temporal workflow/activity communication.

    Handles:
    - Dataclasses
    - Datetime objects
    - Decimal
    - Lists and dicts (recursively)
    """
    if is_dataclass(obj) and not isinstance(obj, type):
        # Use to_dict if available (for camelCase conversion)
        if hasattr(obj, "to_dict"):
            return obj.to_dict()
        return {k: serialize_for_temporal(v) for k, v in asdict(obj).items()}

    if isinstance(obj, datetime):
        return obj.isoformat()

    if isinstance(obj, date):
        return obj.isoformat()

    if isinstance(obj, Decimal):
        return float(obj)

    if isinstance(obj, dict):
        return {k: serialize_for_temporal(v) for k, v in obj.items()}

    if isinstance(obj, (list, tuple)):
        return [serialize_for_temporal(item) for item in obj]

    return obj


def deserialize_from_temporal(data: dict, cls: type) -> Any:
    """
    Deserialize data from Temporal into a dataclass.

    Handles camelCase to snake_case conversion.
    """
    if hasattr(cls, "from_dict"):
        return cls.from_dict(data)

    # Auto-convert camelCase to snake_case
    converted = {}
    for key, value in data.items():
        snake_key = camel_to_snake(key)
        converted[snake_key] = value

    return cls(**converted)


def camel_to_snake(name: str) -> str:
    """Convert camelCase to snake_case."""
    import re
    s1 = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', name)
    return re.sub('([a-z0-9])([A-Z])', r'\1_\2', s1).lower()


def snake_to_camel(name: str) -> str:
    """Convert snake_case to camelCase."""
    components = name.split('_')
    return components[0] + ''.join(x.title() for x in components[1:])
```

## Error Handling Across Language Boundaries

### Error Types

```python
# shared/errors.py
from temporalio.exceptions import ApplicationError

class TTAIError(ApplicationError):
    """Base error class for TTAI system."""

    def __init__(self, message: str, error_type: str, details: dict = None):
        super().__init__(
            message,
            type=error_type,
            non_retryable=False,
            details=details or {},
        )

class NonRetryableError(TTAIError):
    """Error that should not be retried."""

    def __init__(self, message: str, error_type: str, details: dict = None):
        super().__init__(message, error_type, details)
        self._non_retryable = True

class InvalidSymbolError(NonRetryableError):
    """Invalid or unknown symbol."""

    def __init__(self, symbol: str):
        super().__init__(
            f"Invalid symbol: {symbol}",
            "InvalidSymbolError",
            {"symbol": symbol},
        )

class AuthenticationError(NonRetryableError):
    """Authentication failure."""

    def __init__(self, service: str, message: str = "Authentication failed"):
        super().__init__(
            f"{service}: {message}",
            "AuthenticationError",
            {"service": service},
        )

class RateLimitError(TTAIError):
    """Rate limit exceeded (retryable)."""

    def __init__(self, service: str, retry_after: float = 60.0):
        super().__init__(
            f"{service} rate limit exceeded",
            "RateLimitError",
            {"service": service, "retry_after": retry_after},
        )

class DataNotAvailableError(TTAIError):
    """Requested data not available."""

    def __init__(self, data_type: str, identifier: str):
        super().__init__(
            f"{data_type} not available for {identifier}",
            "DataNotAvailableError",
            {"data_type": data_type, "identifier": identifier},
        )
```

### TypeScript Error Handling

```typescript
// src/utils/errors.ts
export interface TemporalError {
  type: string;
  message: string;
  details?: Record<string, unknown>;
  retryable: boolean;
}

export class TTAIError extends Error {
  constructor(
    message: string,
    public readonly code: string,
    public readonly details?: Record<string, unknown>,
    public readonly retryable: boolean = true
  ) {
    super(message);
    this.name = "TTAIError";
  }

  static fromTemporalError(error: unknown): TTAIError {
    // Extract error info from Temporal ApplicationError
    if (error instanceof Error) {
      const temporalError = error as {
        type?: string;
        details?: Record<string, unknown>;
        nonRetryable?: boolean;
      };

      return new TTAIError(
        error.message,
        temporalError.type || "UnknownError",
        temporalError.details,
        !temporalError.nonRetryable
      );
    }

    return new TTAIError(String(error), "UnknownError");
  }

  toJSON() {
    return {
      error: {
        code: this.code,
        message: this.message,
        details: this.details,
        retryable: this.retryable,
      },
    };
  }
}

// Error handler for tool responses
export function handleToolError(error: unknown): { error: object } {
  const ttaiError = TTAIError.fromTemporalError(error);

  // Log error
  console.error(`Tool error: ${ttaiError.code} - ${ttaiError.message}`, ttaiError.details);

  return ttaiError.toJSON();
}
```

### Activity Error Wrapper

```python
# activities/base.py
from functools import wraps
from typing import TypeVar, Callable, Any
from temporalio import activity
from shared.errors import TTAIError, NonRetryableError, RateLimitError

T = TypeVar("T")

def with_error_handling(func: Callable[..., T]) -> Callable[..., T]:
    """Decorator to standardize error handling in activities."""

    @wraps(func)
    async def wrapper(*args, **kwargs) -> T:
        try:
            return await func(*args, **kwargs)

        except NonRetryableError:
            # Re-raise non-retryable errors as-is
            raise

        except RateLimitError:
            # Re-raise rate limit errors (Temporal will retry with backoff)
            raise

        except TTAIError:
            # Re-raise our custom errors
            raise

        except Exception as e:
            # Wrap unexpected errors
            activity.logger.error(f"Unexpected error in {func.__name__}: {e}")
            raise TTAIError(
                f"Activity failed: {str(e)}",
                "UnexpectedError",
                {"activity": func.__name__, "original_error": str(e)},
            )

    return wrapper


# Usage example
@activity.defn
@with_error_handling
async def fetch_quotes_activity(symbols: list[str]) -> dict:
    from services.tastytrade import TastyTradeClient

    client = await TastyTradeClient.get_instance()
    return await client.get_quotes(symbols)
```

## Timeout and Retry Coordination

### Timeout Configuration

```python
# config/timeouts.py
from datetime import timedelta
from dataclasses import dataclass

@dataclass
class ActivityTimeouts:
    """Timeout configuration for different activity types."""

    # Quick operations (API calls, cache reads)
    quick = {
        "start_to_close": timedelta(seconds=30),
        "heartbeat": None,
    }

    # Standard operations (data fetching)
    standard = {
        "start_to_close": timedelta(minutes=2),
        "heartbeat": timedelta(seconds=30),
    }

    # Long operations (AI agents, streaming)
    long = {
        "start_to_close": timedelta(minutes=5),
        "heartbeat": timedelta(seconds=30),
    }

    # Very long operations (full analysis pipeline)
    very_long = {
        "start_to_close": timedelta(minutes=15),
        "heartbeat": timedelta(minutes=1),
    }

# Usage in workflows
from config.timeouts import ActivityTimeouts

await workflow.execute_activity(
    fetch_quotes_activity,
    symbols,
    **ActivityTimeouts.quick,
)

await workflow.execute_activity(
    chart_analysis_activity,
    params,
    **ActivityTimeouts.long,
    retry_policy=AGENT_RETRY_POLICY,
)
```

### Retry Policy Configuration

```python
# config/retry.py
from datetime import timedelta
from temporalio.common import RetryPolicy

# Default retry policy
DEFAULT_RETRY_POLICY = RetryPolicy(
    initial_interval=timedelta(seconds=1),
    backoff_coefficient=2.0,
    maximum_interval=timedelta(seconds=60),
    maximum_attempts=3,
    non_retryable_error_types=[
        "InvalidSymbolError",
        "AuthenticationError",
        "ValidationError",
    ],
)

# For external API calls (may rate limit)
API_RETRY_POLICY = RetryPolicy(
    initial_interval=timedelta(seconds=5),
    backoff_coefficient=2.0,
    maximum_interval=timedelta(minutes=2),
    maximum_attempts=5,
    non_retryable_error_types=[
        "InvalidSymbolError",
        "AuthenticationError",
    ],
)

# For AI agent activities (expensive, limit retries)
AGENT_RETRY_POLICY = RetryPolicy(
    initial_interval=timedelta(seconds=2),
    backoff_coefficient=2.0,
    maximum_interval=timedelta(seconds=30),
    maximum_attempts=2,
    non_retryable_error_types=[
        "InvalidSymbolError",
        "AuthenticationError",
    ],
)

# For notification activities (should retry more)
NOTIFICATION_RETRY_POLICY = RetryPolicy(
    initial_interval=timedelta(seconds=1),
    backoff_coefficient=1.5,
    maximum_interval=timedelta(seconds=30),
    maximum_attempts=5,
)
```

### TypeScript Timeout Handling

```typescript
// src/temporal/timeouts.ts
export const WORKFLOW_TIMEOUTS = {
  // Quick workflows
  quick: 60000, // 1 minute

  // Standard analysis
  standard: 300000, // 5 minutes

  // Full analysis pipeline
  full: 900000, // 15 minutes

  // Screener workflows
  screener: 3600000, // 1 hour
};

// Helper for workflow execution with timeout
export async function executeWithTimeout<T>(
  promise: Promise<T>,
  timeout: number,
  workflowId: string
): Promise<T> {
  const timeoutPromise = new Promise<never>((_, reject) => {
    setTimeout(() => {
      reject(new TTAIError(
        `Workflow ${workflowId} timed out after ${timeout}ms`,
        "WorkflowTimeout",
        { workflowId, timeout },
        true // Retryable
      ));
    }, timeout);
  });

  return Promise.race([promise, timeoutPromise]);
}
```

## Redis Pub/Sub Integration

### Publisher (Python)

```python
# services/publisher.py
from db.redis import RedisCache
from typing import Any

class EventPublisher:
    """Publish events to Redis for real-time updates."""

    def __init__(self, redis: RedisCache):
        self.redis = redis

    async def publish_quote_update(self, symbol: str, quote: dict) -> None:
        """Publish quote update."""
        await self.redis.publish(f"quotes:{symbol}", {
            "type": "quote",
            "symbol": symbol,
            "data": quote,
        })

    async def publish_analysis_complete(
        self,
        symbol: str,
        analysis_type: str,
        result: dict,
    ) -> None:
        """Publish analysis completion event."""
        await self.redis.publish(f"analysis:{symbol}", {
            "type": "analysis_complete",
            "symbol": symbol,
            "analysisType": analysis_type,
            "recommendation": result.get("recommendation"),
        })

    async def publish_alert(self, alert: dict) -> None:
        """Publish alert for real-time notification."""
        await self.redis.publish("alerts", {
            "type": "alert",
            **alert,
        })
```

### Subscriber (TypeScript)

```typescript
// src/realtime/subscriber.ts
import { RedisCache } from "../cache/redis";

export type EventHandler = (event: unknown) => void;

export class EventSubscriber {
  private subscriptions: Map<string, EventHandler[]> = new Map();

  constructor(private redis: RedisCache) {}

  async subscribeToQuotes(
    symbols: string[],
    handler: EventHandler
  ): Promise<void> {
    for (const symbol of symbols) {
      const channel = `quotes:${symbol}`;
      await this.redis.subscribe(channel, handler);
      this.addHandler(channel, handler);
    }
  }

  async subscribeToAnalysis(
    symbol: string,
    handler: EventHandler
  ): Promise<void> {
    const channel = `analysis:${symbol}`;
    await this.redis.subscribe(channel, handler);
    this.addHandler(channel, handler);
  }

  async subscribeToAlerts(handler: EventHandler): Promise<void> {
    await this.redis.subscribe("alerts", handler);
    this.addHandler("alerts", handler);
  }

  private addHandler(channel: string, handler: EventHandler): void {
    const handlers = this.subscriptions.get(channel) || [];
    handlers.push(handler);
    this.subscriptions.set(channel, handlers);
  }
}
```

## Best Practices Summary

1. **Type Safety**: Use shared type definitions with explicit serialization
2. **Error Handling**: Classify errors as retryable vs non-retryable
3. **Timeouts**: Configure appropriate timeouts at activity and workflow levels
4. **Retries**: Use different retry policies based on operation type
5. **Serialization**: Handle camelCase/snake_case conversion explicitly
6. **Real-time Updates**: Use Redis Pub/Sub for immediate notifications
7. **Heartbeats**: Use heartbeats for long-running activities to prevent timeouts
