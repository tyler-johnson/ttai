# Workflow Orchestration

## Overview

The TTAI system uses Cloudflare Workflows for durable execution of long-running operations. Cloudflare Workflows provide automatic retries, state persistence, and resumability for complex multi-step processes like AI analysis pipelines, background monitoring, and scheduled tasks.

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                     Cloudflare Edge Network                          │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ┌────────────────────────────────────────────────────────────────┐ │
│  │              MCP Server (TypeScript Worker)                     │ │
│  │                   Workflow Triggers                             │ │
│  └──────────────────────────┬─────────────────────────────────────┘ │
│                             │                                        │
│                             ▼                                        │
│  ┌────────────────────────────────────────────────────────────────┐ │
│  │              Cloudflare Workflows (Durable Execution)           │ │
│  │  ┌────────────┐  ┌────────────┐  ┌────────────┐                │ │
│  │  │  Analysis  │  │  Screener  │  │   Alert    │                │ │
│  │  │  Workflow  │  │  Workflow  │  │  Workflow  │                │ │
│  │  └─────┬──────┘  └─────┬──────┘  └─────┬──────┘                │ │
│  └────────┼───────────────┼───────────────┼───────────────────────┘ │
│           │               │               │                          │
│           └───────────────┼───────────────┘                          │
│                           ▼                                          │
│  ┌────────────────────────────────────────────────────────────────┐ │
│  │                    Python Workers                               │ │
│  │  ┌────────────┐  ┌────────────┐  ┌────────────┐                │ │
│  │  │   Chart    │  │  Options   │  │  Research  │                │ │
│  │  │  Analysis  │  │  Analysis  │  │  Analysis  │                │ │
│  │  └────────────┘  └────────────┘  └────────────┘                │ │
│  └────────────────────────────────────────────────────────────────┘ │
│                                                                      │
│  ┌────────────────────────────────────────────────────────────────┐ │
│  │              Durable Objects (Stateful Background Tasks)        │ │
│  │  ┌────────────┐  ┌────────────┐  ┌────────────┐                │ │
│  │  │  Monitor   │  │   Alert    │  │  Session   │                │ │
│  │  │  (Alarms)  │  │  (Alarms)  │  │  (WS)      │                │ │
│  │  └────────────┘  └────────────┘  └────────────┘                │ │
│  └────────────────────────────────────────────────────────────────┘ │
│                                                                      │
│  ┌────────────────────────────────────────────────────────────────┐ │
│  │              Cron Triggers (Scheduled Tasks)                    │ │
│  │  ┌────────────┐  ┌────────────┐  ┌────────────┐                │ │
│  │  │  Daily     │  │  Hourly    │  │  Market    │                │ │
│  │  │  Report    │  │  Scan      │  │  Open/Close│                │ │
│  │  └────────────┘  └────────────┘  └────────────┘                │ │
│  └────────────────────────────────────────────────────────────────┘ │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

## Cloudflare Workflows

### Workflow Definition

Workflows are defined in TypeScript and execute on Cloudflare's edge network with durable state.

```typescript
// src/workflows/analysis.ts
import { WorkflowEntrypoint, WorkflowStep, WorkflowEvent } from "cloudflare:workers";

export interface AnalysisParams {
  type: "chart_analysis" | "options_analysis" | "full_analysis";
  userId: string;
  symbol: string;
  timeframe?: string;
  strategy?: string;
}

export class AnalysisWorkflow extends WorkflowEntrypoint<Env, AnalysisParams> {
  async run(event: WorkflowEvent<AnalysisParams>, step: WorkflowStep) {
    const { type, userId, symbol, timeframe, strategy } = event.payload;

    // Step 1: Fetch market data (automatically retried on failure)
    const marketData = await step.do("fetch-market-data", async () => {
      const response = await this.env.PYTHON_WORKER.fetch(
        new Request("https://internal/market-data", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "X-User-Id": userId,
          },
          body: JSON.stringify({ symbol, timeframe }),
        })
      );
      return response.json();
    });

    // Step 2: Run chart analysis
    const chartAnalysis = await step.do("chart-analysis", async () => {
      const response = await this.env.PYTHON_WORKER.fetch(
        new Request("https://internal/analyze/chart", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "X-User-Id": userId,
          },
          body: JSON.stringify({
            symbol,
            marketData,
            timeframe: timeframe || "daily",
          }),
        })
      );
      return response.json();
    });

    // Early exit if chart analysis rejects
    if (chartAnalysis.recommendation === "reject") {
      await step.do("save-result", async () => {
        await this.saveAnalysis(userId, symbol, type, {
          status: "rejected",
          reason: chartAnalysis.chartNotes,
          chartAnalysis,
        });
      });
      return { status: "rejected", chartAnalysis };
    }

    // Step 3: Run options analysis (only for full analysis)
    let optionsAnalysis = null;
    if (type === "full_analysis" || type === "options_analysis") {
      optionsAnalysis = await step.do("options-analysis", async () => {
        const response = await this.env.PYTHON_WORKER.fetch(
          new Request("https://internal/analyze/options", {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
              "X-User-Id": userId,
            },
            body: JSON.stringify({
              symbol,
              chartContext: chartAnalysis,
              strategy: strategy || "csp",
            }),
          })
        );
        return response.json();
      });
    }

    // Step 4: Run research analysis (only for full analysis)
    let researchAnalysis = null;
    if (type === "full_analysis") {
      researchAnalysis = await step.do("research-analysis", async () => {
        const response = await this.env.PYTHON_WORKER.fetch(
          new Request("https://internal/analyze/research", {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
              "X-User-Id": userId,
            },
            body: JSON.stringify({ symbol }),
          })
        );
        return response.json();
      });
    }

    // Step 5: Synthesize results
    const result = await step.do("synthesize", async () => {
      return this.synthesizeResults(chartAnalysis, optionsAnalysis, researchAnalysis);
    });

    // Step 6: Save to database
    await step.do("save-result", async () => {
      await this.saveAnalysis(userId, symbol, type, result);
    });

    // Step 7: Notify user if configured
    await step.do("notify", async () => {
      await this.notifyUser(userId, symbol, result);
    });

    return result;
  }

  private synthesizeResults(chart: any, options: any, research: any) {
    // Combine analyses into final recommendation
    let recommendation = "neutral";

    if (chart?.recommendation === "bullish") {
      if (options?.recommendation === "select") {
        recommendation = research?.sentiment === "positive" ? "strong_select" : "select";
      }
    }

    return {
      overallRecommendation: recommendation,
      chartAnalysis: chart,
      optionsAnalysis: options,
      researchAnalysis: research,
      synthesizedAt: new Date().toISOString(),
    };
  }

  private async saveAnalysis(userId: string, symbol: string, type: string, result: any) {
    await this.env.DB.prepare(
      `INSERT INTO analyses (user_id, symbol, type, result, created_at)
       VALUES (?, ?, ?, ?, ?)`
    )
      .bind(userId, symbol, type, JSON.stringify(result), Date.now())
      .run();
  }

  private async notifyUser(userId: string, symbol: string, result: any) {
    // Queue notification
    await this.env.QUEUE.send({
      type: "analysis_complete",
      userId,
      symbol,
      recommendation: result.overallRecommendation,
    });
  }
}
```

### Screener Workflow

Long-running screener that analyzes multiple symbols.

```typescript
// src/workflows/screener.ts
export interface ScreenerParams {
  userId: string;
  criteria: ScreenerCriteria;
  maxSymbols: number;
}

export class ScreenerWorkflow extends WorkflowEntrypoint<Env, ScreenerParams> {
  async run(event: WorkflowEvent<ScreenerParams>, step: WorkflowStep) {
    const { userId, criteria, maxSymbols } = event.payload;

    // Step 1: Get candidate symbols
    const candidates = await step.do("get-candidates", async () => {
      const response = await this.env.PYTHON_WORKER.fetch(
        new Request("https://internal/screener/candidates", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(criteria),
        })
      );
      return response.json<string[]>();
    });

    // Step 2: Analyze each symbol (with parallel batching)
    const batchSize = 5;
    const results: AnalysisResult[] = [];

    for (let i = 0; i < Math.min(candidates.length, maxSymbols); i += batchSize) {
      const batch = candidates.slice(i, i + batchSize);

      const batchResults = await step.do(`analyze-batch-${i}`, async () => {
        const analyses = await Promise.all(
          batch.map(async (symbol) => {
            const response = await this.env.PYTHON_WORKER.fetch(
              new Request("https://internal/analyze/quick", {
                method: "POST",
                headers: {
                  "Content-Type": "application/json",
                  "X-User-Id": userId,
                },
                body: JSON.stringify({ symbol, strategy: criteria.strategy }),
              })
            );
            return response.json();
          })
        );
        return analyses;
      });

      results.push(...batchResults);

      // Sleep between batches to avoid rate limits
      await step.sleep("batch-delay", "5 seconds");
    }

    // Step 3: Rank and filter results
    const rankedResults = await step.do("rank-results", async () => {
      return results
        .filter((r) => r.recommendation !== "reject")
        .sort((a, b) => (b.score || 0) - (a.score || 0))
        .slice(0, 10);
    });

    // Step 4: Save screener results
    await step.do("save-results", async () => {
      await this.env.DB.prepare(
        `INSERT INTO screener_results (user_id, criteria, results, created_at)
         VALUES (?, ?, ?, ?)`
      )
        .bind(userId, JSON.stringify(criteria), JSON.stringify(rankedResults), Date.now())
        .run();
    });

    return { candidates: candidates.length, analyzed: results.length, results: rankedResults };
  }
}
```

### Workflow Registration

```toml
# wrangler.toml
[[workflows]]
binding = "ANALYSIS_WORKFLOW"
name = "analysis-workflow"
class_name = "AnalysisWorkflow"

[[workflows]]
binding = "SCREENER_WORKFLOW"
name = "screener-workflow"
class_name = "ScreenerWorkflow"
```

## Durable Objects for Stateful Background Tasks

### Portfolio Monitor

Durable Object that uses alarms for continuous portfolio monitoring.

```typescript
// src/durableObjects/portfolioMonitor.ts
export class PortfolioMonitor implements DurableObject {
  private state: DurableObjectState;
  private env: Env;

  constructor(state: DurableObjectState, env: Env) {
    this.state = state;
    this.env = env;
  }

  async fetch(request: Request): Promise<Response> {
    const url = new URL(request.url);

    if (url.pathname === "/start") {
      return this.startMonitoring(request);
    }

    if (url.pathname === "/stop") {
      return this.stopMonitoring();
    }

    if (url.pathname === "/status") {
      return this.getStatus();
    }

    return new Response("Not Found", { status: 404 });
  }

  async startMonitoring(request: Request): Promise<Response> {
    const { userId, positions, alertRules } = await request.json<MonitorConfig>();

    // Store configuration
    await this.state.storage.put("config", { userId, positions, alertRules });
    await this.state.storage.put("active", true);

    // Set initial alarm
    await this.state.storage.setAlarm(Date.now() + 60000); // Check every minute

    return new Response(JSON.stringify({ status: "started" }));
  }

  async stopMonitoring(): Promise<Response> {
    await this.state.storage.put("active", false);
    await this.state.storage.deleteAlarm();

    return new Response(JSON.stringify({ status: "stopped" }));
  }

  async getStatus(): Promise<Response> {
    const active = await this.state.storage.get<boolean>("active");
    const lastCheck = await this.state.storage.get<number>("lastCheck");
    const alerts = await this.state.storage.get<Alert[]>("recentAlerts") || [];

    return new Response(
      JSON.stringify({ active, lastCheck, recentAlerts: alerts })
    );
  }

  async alarm(): Promise<void> {
    const active = await this.state.storage.get<boolean>("active");
    if (!active) return;

    const config = await this.state.storage.get<MonitorConfig>("config");
    if (!config) return;

    try {
      // Check positions
      const alerts = await this.checkPositions(config);

      // Process any triggered alerts
      for (const alert of alerts) {
        await this.processAlert(config.userId, alert);
      }

      // Store last check time
      await this.state.storage.put("lastCheck", Date.now());

      // Store recent alerts
      const recentAlerts = await this.state.storage.get<Alert[]>("recentAlerts") || [];
      await this.state.storage.put(
        "recentAlerts",
        [...alerts, ...recentAlerts].slice(0, 50)
      );
    } catch (error) {
      console.error("Monitor check failed:", error);
    }

    // Schedule next check
    await this.state.storage.setAlarm(Date.now() + 60000);
  }

  private async checkPositions(config: MonitorConfig): Promise<Alert[]> {
    const alerts: Alert[] = [];

    // Fetch current quotes for all positions
    const symbols = config.positions.map((p) => p.symbol);
    const response = await this.env.PYTHON_WORKER.fetch(
      new Request("https://internal/quotes", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-User-Id": config.userId,
        },
        body: JSON.stringify({ symbols }),
      })
    );
    const quotes = await response.json<Record<string, Quote>>();

    // Check each position against rules
    for (const position of config.positions) {
      const quote = quotes[position.symbol];
      if (!quote) continue;

      for (const rule of config.alertRules) {
        if (this.checkRule(position, quote, rule)) {
          alerts.push({
            type: rule.type,
            symbol: position.symbol,
            message: this.formatAlertMessage(rule, position, quote),
            timestamp: Date.now(),
          });
        }
      }
    }

    return alerts;
  }

  private checkRule(position: Position, quote: Quote, rule: AlertRule): boolean {
    switch (rule.type) {
      case "price_above":
        return quote.price > rule.threshold;
      case "price_below":
        return quote.price < rule.threshold;
      case "delta_breach":
        return position.delta && Math.abs(position.delta) > rule.threshold;
      case "dte_warning":
        return position.dte && position.dte <= rule.threshold;
      default:
        return false;
    }
  }

  private async processAlert(userId: string, alert: Alert): Promise<void> {
    // Send to notification queue
    await this.env.QUEUE.send({
      type: "position_alert",
      userId,
      alert,
    });
  }
}
```

### Price Alert Durable Object

```typescript
// src/durableObjects/priceAlert.ts
export class PriceAlertDO implements DurableObject {
  private state: DurableObjectState;
  private env: Env;

  constructor(state: DurableObjectState, env: Env) {
    this.state = state;
    this.env = env;
  }

  async fetch(request: Request): Promise<Response> {
    const url = new URL(request.url);

    if (url.pathname === "/set") {
      return this.setAlert(request);
    }

    if (url.pathname === "/cancel") {
      return this.cancelAlert();
    }

    return new Response("Not Found", { status: 404 });
  }

  async setAlert(request: Request): Promise<Response> {
    const { userId, symbol, condition, threshold } = await request.json<AlertConfig>();

    await this.state.storage.put("alert", { userId, symbol, condition, threshold });
    await this.state.storage.setAlarm(Date.now() + 30000); // Check every 30 seconds

    return new Response(JSON.stringify({ status: "alert_set" }));
  }

  async cancelAlert(): Promise<Response> {
    await this.state.storage.delete("alert");
    await this.state.storage.deleteAlarm();

    return new Response(JSON.stringify({ status: "cancelled" }));
  }

  async alarm(): Promise<void> {
    const alert = await this.state.storage.get<AlertConfig>("alert");
    if (!alert) return;

    // Fetch current price
    const response = await this.env.PYTHON_WORKER.fetch(
      new Request("https://internal/quotes", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ symbols: [alert.symbol] }),
      })
    );
    const quotes = await response.json<Record<string, Quote>>();
    const quote = quotes[alert.symbol];

    if (!quote) {
      await this.state.storage.setAlarm(Date.now() + 30000);
      return;
    }

    // Check condition
    const triggered =
      (alert.condition === "above" && quote.price >= alert.threshold) ||
      (alert.condition === "below" && quote.price <= alert.threshold);

    if (triggered) {
      // Send notification
      await this.env.QUEUE.send({
        type: "price_alert_triggered",
        userId: alert.userId,
        symbol: alert.symbol,
        condition: alert.condition,
        threshold: alert.threshold,
        currentPrice: quote.price,
      });

      // Clear alert (one-time trigger)
      await this.state.storage.delete("alert");
    } else {
      // Schedule next check
      await this.state.storage.setAlarm(Date.now() + 30000);
    }
  }
}
```

## Cron Triggers

### Scheduled Task Handler

```typescript
// src/index.ts
export default {
  async scheduled(event: ScheduledEvent, env: Env, ctx: ExecutionContext) {
    switch (event.cron) {
      case "0 14 * * 1-5": // 9:30 AM ET (market open) on weekdays
        await handleMarketOpen(env);
        break;

      case "0 21 * * 1-5": // 4:00 PM ET (market close) on weekdays
        await handleMarketClose(env);
        break;

      case "0 */1 14-21 * * 1-5": // Every hour during market hours
        await handleHourlyScan(env);
        break;

      case "0 22 * * 1-5": // 5:00 PM ET (after market close)
        await handleDailyReport(env);
        break;
    }
  },
};

async function handleMarketOpen(env: Env): Promise<void> {
  // Get all active users with morning alerts enabled
  const users = await env.DB.prepare(
    `SELECT user_id FROM user_preferences WHERE morning_alert = true`
  ).all();

  for (const user of users.results) {
    // Queue morning briefing generation
    await env.QUEUE.send({
      type: "morning_briefing",
      userId: user.user_id,
    });
  }
}

async function handleMarketClose(env: Env): Promise<void> {
  // Get all active users
  const users = await env.DB.prepare(
    `SELECT DISTINCT user_id FROM positions WHERE status = 'open'`
  ).all();

  for (const user of users.results) {
    // Queue end-of-day P&L summary
    await env.QUEUE.send({
      type: "eod_summary",
      userId: user.user_id,
    });
  }
}

async function handleHourlyScan(env: Env): Promise<void> {
  // Run automated screeners for all users
  const screeners = await env.DB.prepare(
    `SELECT * FROM saved_screeners WHERE auto_run = true`
  ).all();

  for (const screener of screeners.results) {
    // Start screener workflow
    await env.SCREENER_WORKFLOW.create({
      params: {
        userId: screener.user_id,
        criteria: JSON.parse(screener.criteria),
        maxSymbols: 50,
      },
    });
  }
}

async function handleDailyReport(env: Env): Promise<void> {
  // Generate daily performance reports
  const users = await env.DB.prepare(
    `SELECT DISTINCT user_id FROM positions`
  ).all();

  for (const user of users.results) {
    await env.QUEUE.send({
      type: "daily_report",
      userId: user.user_id,
    });
  }
}
```

### wrangler.toml Cron Configuration

```toml
# wrangler.toml
[triggers]
crons = [
  "0 14 * * 1-5",      # Market open (9:30 AM ET)
  "0 21 * * 1-5",      # Market close (4:00 PM ET)
  "0 */1 14-21 * * 1-5", # Hourly during market
  "0 22 * * 1-5"       # Daily report (5:00 PM ET)
]
```

## Retry and Timeout Patterns

### Workflow Step Configuration

```typescript
// Automatic retries with exponential backoff
const result = await step.do(
  "api-call",
  {
    retries: {
      limit: 3,
      delay: "1 second",
      backoff: "exponential",
    },
    timeout: "30 seconds",
  },
  async () => {
    // API call that may fail
    return fetchExternalAPI();
  }
);
```

### Manual Retry Logic

```typescript
async function withRetry<T>(
  fn: () => Promise<T>,
  maxRetries: number = 3,
  delayMs: number = 1000
): Promise<T> {
  let lastError: Error | undefined;

  for (let attempt = 0; attempt < maxRetries; attempt++) {
    try {
      return await fn();
    } catch (error) {
      lastError = error as Error;

      if (attempt < maxRetries - 1) {
        await new Promise((resolve) =>
          setTimeout(resolve, delayMs * Math.pow(2, attempt))
        );
      }
    }
  }

  throw lastError;
}
```

## Cross-References

- [MCP Server Design](./01-mcp-server-design.md) - Workflow triggering from MCP tools
- [Python Workers](./03-python-workers.md) - Analysis execution in Python
- [Background Tasks](./06-background-tasks.md) - Detailed background task patterns
- [Integration Patterns](./09-integration-patterns.md) - Worker communication
