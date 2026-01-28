# Background Tasks

## Overview

The TTAI background task system uses Cloudflare primitives for continuous monitoring, scheduled operations, and alert delivery. Durable Object alarms handle stateful monitoring tasks, Cron Triggers run scheduled operations, and Cloudflare Queues process async work.

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                     Cloudflare Edge Network                          │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ┌────────────────────────────────────────────────────────────────┐ │
│  │              Durable Object Alarms (Continuous)                 │ │
│  │  ┌────────────┐  ┌────────────┐  ┌────────────┐                │ │
│  │  │  Portfolio │  │   Price    │  │    News    │                │ │
│  │  │  Monitor   │  │  Alerts    │  │  Watcher   │                │ │
│  │  │ (60s loop) │  │ (30s loop) │  │(300s loop) │                │ │
│  │  └────────────┘  └────────────┘  └────────────┘                │ │
│  └────────────────────────────────────────────────────────────────┘ │
│                                                                      │
│  ┌────────────────────────────────────────────────────────────────┐ │
│  │              Cron Triggers (Scheduled)                          │ │
│  │  ┌────────────┐  ┌────────────┐  ┌────────────┐                │ │
│  │  │  Market    │  │   Hourly   │  │   Daily    │                │ │
│  │  │Open/Close  │  │   Scan     │  │  Reports   │                │ │
│  │  │ 9:30/4:00  │  │   :00      │  │  5:00 PM   │                │ │
│  │  └────────────┘  └────────────┘  └────────────┘                │ │
│  └────────────────────────────────────────────────────────────────┘ │
│                                                                      │
│  ┌────────────────────────────────────────────────────────────────┐ │
│  │              Cloudflare Queues (Async Processing)               │ │
│  │  ┌────────────┐  ┌────────────┐  ┌────────────┐                │ │
│  │  │ Analysis   │  │ Notifica-  │  │  Screener  │                │ │
│  │  │  Results   │  │   tions    │  │  Results   │                │ │
│  │  └────────────┘  └────────────┘  └────────────┘                │ │
│  └────────────────────────────────────────────────────────────────┘ │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

## Durable Object Alarms

### Portfolio Monitor

Continuously monitors user positions for alerts.

```typescript
// src/durableObjects/portfolioMonitor.ts
interface MonitorConfig {
  userId: string;
  positions: Position[];
  alertRules: AlertRule[];
  checkIntervalMs: number;
}

interface AlertRule {
  type: "price_above" | "price_below" | "delta_breach" | "dte_warning";
  threshold: number;
  symbol?: string; // Optional - if not set, applies to all
}

export class PortfolioMonitor implements DurableObject {
  private state: DurableObjectState;
  private env: Env;

  constructor(state: DurableObjectState, env: Env) {
    this.state = state;
    this.env = env;
  }

  async fetch(request: Request): Promise<Response> {
    const url = new URL(request.url);

    switch (url.pathname) {
      case "/start":
        return this.start(request);
      case "/stop":
        return this.stop();
      case "/status":
        return this.getStatus();
      case "/update-rules":
        return this.updateRules(request);
      default:
        return new Response("Not Found", { status: 404 });
    }
  }

  async start(request: Request): Promise<Response> {
    const config = await request.json<MonitorConfig>();

    await this.state.storage.put("config", config);
    await this.state.storage.put("active", true);
    await this.state.storage.put("stats", {
      checksPerformed: 0,
      alertsTriggered: 0,
      lastCheck: null,
    });

    // Start the alarm loop
    await this.state.storage.setAlarm(Date.now() + config.checkIntervalMs);

    return Response.json({ status: "started", nextCheck: Date.now() + config.checkIntervalMs });
  }

  async stop(): Promise<Response> {
    await this.state.storage.put("active", false);
    await this.state.storage.deleteAlarm();

    return Response.json({ status: "stopped" });
  }

  async getStatus(): Promise<Response> {
    const active = await this.state.storage.get<boolean>("active");
    const stats = await this.state.storage.get("stats");
    const config = await this.state.storage.get<MonitorConfig>("config");
    const alarm = await this.state.storage.getAlarm();

    return Response.json({
      active,
      stats,
      positionCount: config?.positions.length || 0,
      ruleCount: config?.alertRules.length || 0,
      nextCheckAt: alarm,
    });
  }

  async updateRules(request: Request): Promise<Response> {
    const { alertRules } = await request.json<{ alertRules: AlertRule[] }>();
    const config = await this.state.storage.get<MonitorConfig>("config");

    if (config) {
      config.alertRules = alertRules;
      await this.state.storage.put("config", config);
    }

    return Response.json({ status: "updated", ruleCount: alertRules.length });
  }

  async alarm(): Promise<void> {
    const active = await this.state.storage.get<boolean>("active");
    if (!active) return;

    const config = await this.state.storage.get<MonitorConfig>("config");
    if (!config) return;

    try {
      await this.performCheck(config);
    } catch (error) {
      console.error("Portfolio monitor check failed:", error);
    }

    // Schedule next check
    await this.state.storage.setAlarm(Date.now() + config.checkIntervalMs);
  }

  private async performCheck(config: MonitorConfig): Promise<void> {
    const { userId, positions, alertRules } = config;

    // Fetch current quotes
    const symbols = [...new Set(positions.map((p) => p.symbol))];
    const response = await this.env.PYTHON_WORKER.fetch(
      new Request("https://internal/quotes", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-User-Id": userId,
        },
        body: JSON.stringify({ symbols }),
      })
    );
    const quotes = await response.json<Record<string, Quote>>();

    // Check each position against rules
    const triggeredAlerts: TriggeredAlert[] = [];

    for (const position of positions) {
      const quote = quotes[position.symbol];
      if (!quote) continue;

      for (const rule of alertRules) {
        // Skip if rule is symbol-specific and doesn't match
        if (rule.symbol && rule.symbol !== position.symbol) continue;

        if (this.checkRule(position, quote, rule)) {
          triggeredAlerts.push({
            ruleType: rule.type,
            symbol: position.symbol,
            threshold: rule.threshold,
            currentValue: this.getCurrentValue(position, quote, rule.type),
            timestamp: Date.now(),
          });
        }
      }
    }

    // Update stats
    const stats = await this.state.storage.get("stats") as any;
    stats.checksPerformed++;
    stats.lastCheck = Date.now();
    stats.alertsTriggered += triggeredAlerts.length;
    await this.state.storage.put("stats", stats);

    // Queue notifications for triggered alerts
    for (const alert of triggeredAlerts) {
      await this.env.QUEUE.send({
        type: "position_alert",
        userId,
        alert,
      });
    }
  }

  private checkRule(position: Position, quote: Quote, rule: AlertRule): boolean {
    switch (rule.type) {
      case "price_above":
        return quote.price > rule.threshold;
      case "price_below":
        return quote.price < rule.threshold;
      case "delta_breach":
        return position.delta != null && Math.abs(position.delta) > rule.threshold;
      case "dte_warning":
        return position.dte != null && position.dte <= rule.threshold;
      default:
        return false;
    }
  }

  private getCurrentValue(position: Position, quote: Quote, ruleType: string): number {
    switch (ruleType) {
      case "price_above":
      case "price_below":
        return quote.price;
      case "delta_breach":
        return position.delta || 0;
      case "dte_warning":
        return position.dte || 0;
      default:
        return 0;
    }
  }
}
```

### Price Alert Durable Object

One-time or recurring price alerts.

```typescript
// src/durableObjects/priceAlert.ts
interface PriceAlertConfig {
  userId: string;
  symbol: string;
  condition: "above" | "below";
  threshold: number;
  recurring: boolean;
  checkIntervalMs: number;
}

export class PriceAlertDO implements DurableObject {
  private state: DurableObjectState;
  private env: Env;

  constructor(state: DurableObjectState, env: Env) {
    this.state = state;
    this.env = env;
  }

  async fetch(request: Request): Promise<Response> {
    const url = new URL(request.url);

    switch (url.pathname) {
      case "/set":
        return this.setAlert(request);
      case "/cancel":
        return this.cancelAlert();
      case "/status":
        return this.getStatus();
      default:
        return new Response("Not Found", { status: 404 });
    }
  }

  async setAlert(request: Request): Promise<Response> {
    const config = await request.json<PriceAlertConfig>();

    await this.state.storage.put("config", config);
    await this.state.storage.put("triggered", false);
    await this.state.storage.setAlarm(Date.now() + config.checkIntervalMs);

    return Response.json({ status: "alert_set", config });
  }

  async cancelAlert(): Promise<Response> {
    await this.state.storage.deleteAll();
    await this.state.storage.deleteAlarm();

    return Response.json({ status: "cancelled" });
  }

  async getStatus(): Promise<Response> {
    const config = await this.state.storage.get<PriceAlertConfig>("config");
    const triggered = await this.state.storage.get<boolean>("triggered");
    const alarm = await this.state.storage.getAlarm();

    return Response.json({
      config,
      triggered,
      nextCheckAt: alarm,
    });
  }

  async alarm(): Promise<void> {
    const config = await this.state.storage.get<PriceAlertConfig>("config");
    if (!config) return;

    // Fetch current price
    const response = await this.env.PYTHON_WORKER.fetch(
      new Request("https://internal/quotes", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ symbols: [config.symbol] }),
      })
    );
    const quotes = await response.json<Record<string, Quote>>();
    const quote = quotes[config.symbol];

    if (!quote) {
      // Reschedule if quote unavailable
      await this.state.storage.setAlarm(Date.now() + config.checkIntervalMs);
      return;
    }

    // Check condition
    const triggered =
      (config.condition === "above" && quote.price >= config.threshold) ||
      (config.condition === "below" && quote.price <= config.threshold);

    if (triggered) {
      // Send notification
      await this.env.QUEUE.send({
        type: "price_alert_triggered",
        userId: config.userId,
        symbol: config.symbol,
        condition: config.condition,
        threshold: config.threshold,
        currentPrice: quote.price,
      });

      if (config.recurring) {
        // Reset for next trigger (swap condition)
        await this.state.storage.put("triggered", true);
        await this.state.storage.setAlarm(Date.now() + config.checkIntervalMs);
      } else {
        // One-time alert - cleanup
        await this.state.storage.deleteAll();
      }
    } else {
      // Not triggered - schedule next check
      await this.state.storage.setAlarm(Date.now() + config.checkIntervalMs);
    }
  }
}
```

### News Watcher

Monitors news for specified symbols.

```typescript
// src/durableObjects/newsWatcher.ts
interface NewsWatcherConfig {
  userId: string;
  symbols: string[];
  keywords: string[];
  checkIntervalMs: number;
}

export class NewsWatcher implements DurableObject {
  private state: DurableObjectState;
  private env: Env;

  constructor(state: DurableObjectState, env: Env) {
    this.state = state;
    this.env = env;
  }

  async fetch(request: Request): Promise<Response> {
    const url = new URL(request.url);

    switch (url.pathname) {
      case "/start":
        return this.start(request);
      case "/stop":
        return this.stop();
      case "/add-symbol":
        return this.addSymbol(request);
      case "/remove-symbol":
        return this.removeSymbol(request);
      default:
        return new Response("Not Found", { status: 404 });
    }
  }

  async start(request: Request): Promise<Response> {
    const config = await request.json<NewsWatcherConfig>();

    await this.state.storage.put("config", config);
    await this.state.storage.put("active", true);
    await this.state.storage.put("seenArticles", new Set<string>());
    await this.state.storage.setAlarm(Date.now() + config.checkIntervalMs);

    return Response.json({ status: "started" });
  }

  async stop(): Promise<Response> {
    await this.state.storage.put("active", false);
    await this.state.storage.deleteAlarm();

    return Response.json({ status: "stopped" });
  }

  async addSymbol(request: Request): Promise<Response> {
    const { symbol } = await request.json<{ symbol: string }>();
    const config = await this.state.storage.get<NewsWatcherConfig>("config");

    if (config && !config.symbols.includes(symbol)) {
      config.symbols.push(symbol);
      await this.state.storage.put("config", config);
    }

    return Response.json({ status: "added", symbols: config?.symbols });
  }

  async removeSymbol(request: Request): Promise<Response> {
    const { symbol } = await request.json<{ symbol: string }>();
    const config = await this.state.storage.get<NewsWatcherConfig>("config");

    if (config) {
      config.symbols = config.symbols.filter((s) => s !== symbol);
      await this.state.storage.put("config", config);
    }

    return Response.json({ status: "removed", symbols: config?.symbols });
  }

  async alarm(): Promise<void> {
    const active = await this.state.storage.get<boolean>("active");
    if (!active) return;

    const config = await this.state.storage.get<NewsWatcherConfig>("config");
    if (!config) return;

    try {
      await this.checkNews(config);
    } catch (error) {
      console.error("News check failed:", error);
    }

    await this.state.storage.setAlarm(Date.now() + config.checkIntervalMs);
  }

  private async checkNews(config: NewsWatcherConfig): Promise<void> {
    // Fetch news from Python worker
    const response = await this.env.PYTHON_WORKER.fetch(
      new Request("https://internal/news", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ symbols: config.symbols }),
      })
    );
    const articles = await response.json<NewsArticle[]>();

    // Filter for new articles matching keywords
    const seenArticles = (await this.state.storage.get<Set<string>>("seenArticles")) || new Set();
    const newArticles = articles.filter((article) => {
      if (seenArticles.has(article.id)) return false;

      // Check for keyword matches
      const text = `${article.title} ${article.summary}`.toLowerCase();
      return config.keywords.some((kw) => text.includes(kw.toLowerCase()));
    });

    // Queue notifications for new articles
    for (const article of newArticles) {
      await this.env.QUEUE.send({
        type: "news_alert",
        userId: config.userId,
        article,
      });
      seenArticles.add(article.id);
    }

    // Prune old seen articles (keep last 1000)
    if (seenArticles.size > 1000) {
      const arr = Array.from(seenArticles);
      await this.state.storage.put("seenArticles", new Set(arr.slice(-1000)));
    } else {
      await this.state.storage.put("seenArticles", seenArticles);
    }
  }
}
```

## Cron Triggers

### Scheduled Task Configuration

```toml
# wrangler.toml
[triggers]
crons = [
  "30 14 * * 1-5",     # 9:30 AM ET - Market open
  "0 21 * * 1-5",      # 4:00 PM ET - Market close
  "0 14-21 * * 1-5",   # Hourly during market hours
  "0 22 * * 1-5",      # 5:00 PM ET - Daily reports
  "0 22 * * 5"         # 5:00 PM ET Friday - Weekly summary
]
```

### Cron Handler

```typescript
// src/index.ts
export default {
  async scheduled(event: ScheduledEvent, env: Env, ctx: ExecutionContext) {
    const hour = new Date(event.scheduledTime).getUTCHours();
    const dayOfWeek = new Date(event.scheduledTime).getUTCDay();

    // Market open (9:30 AM ET = 14:30 UTC)
    if (event.cron === "30 14 * * 1-5") {
      await handleMarketOpen(env);
      return;
    }

    // Market close (4:00 PM ET = 21:00 UTC)
    if (event.cron === "0 21 * * 1-5") {
      await handleMarketClose(env);
      return;
    }

    // Hourly during market
    if (event.cron === "0 14-21 * * 1-5") {
      await handleHourlyScan(env);
      return;
    }

    // Daily report (5:00 PM ET = 22:00 UTC)
    if (event.cron === "0 22 * * 1-5" && dayOfWeek !== 5) {
      await handleDailyReport(env);
      return;
    }

    // Weekly summary (Friday 5:00 PM ET)
    if (event.cron === "0 22 * * 5") {
      await handleWeeklySummary(env);
      return;
    }
  },
};
```

### Market Open Handler

```typescript
async function handleMarketOpen(env: Env): Promise<void> {
  // Get users with morning alerts enabled
  const users = await env.DB.prepare(
    "SELECT user_id FROM user_preferences WHERE morning_alert = 1"
  ).all();

  for (const user of users.results) {
    const userId = user.user_id as string;

    // Queue morning briefing
    await env.QUEUE.send({
      type: "morning_briefing",
      userId,
    });

    // Activate portfolio monitors
    const monitorId = env.PORTFOLIO_MONITOR.idFromName(userId);
    const monitor = env.PORTFOLIO_MONITOR.get(monitorId);

    // Fetch user positions
    const positions = await env.DB.prepare(
      "SELECT * FROM positions WHERE user_id = ? AND status = 'open'"
    ).bind(userId).all();

    if (positions.results.length > 0) {
      const alerts = await env.DB.prepare(
        "SELECT * FROM alerts WHERE user_id = ? AND status = 'active'"
      ).bind(userId).all();

      await monitor.fetch(
        new Request("https://internal/start", {
          method: "POST",
          body: JSON.stringify({
            userId,
            positions: positions.results,
            alertRules: alerts.results.map((a: any) => ({
              type: a.alert_type,
              threshold: a.threshold,
              symbol: a.symbol,
            })),
            checkIntervalMs: 60000, // 1 minute
          }),
        })
      );
    }
  }
}
```

### Market Close Handler

```typescript
async function handleMarketClose(env: Env): Promise<void> {
  // Stop all portfolio monitors
  const users = await env.DB.prepare(
    "SELECT DISTINCT user_id FROM positions WHERE status = 'open'"
  ).all();

  for (const user of users.results) {
    const userId = user.user_id as string;

    // Stop monitor
    const monitorId = env.PORTFOLIO_MONITOR.idFromName(userId);
    const monitor = env.PORTFOLIO_MONITOR.get(monitorId);
    await monitor.fetch(new Request("https://internal/stop", { method: "POST" }));

    // Queue EOD summary
    await env.QUEUE.send({
      type: "eod_summary",
      userId,
    });
  }
}
```

### Hourly Scan Handler

```typescript
async function handleHourlyScan(env: Env): Promise<void> {
  // Run auto-run screeners
  const screeners = await env.DB.prepare(
    "SELECT * FROM screeners WHERE auto_run = 1"
  ).all();

  for (const screener of screeners.results) {
    await env.SCREENER_WORKFLOW.create({
      params: {
        userId: screener.user_id,
        screenerId: screener.id,
        criteria: JSON.parse(screener.criteria as string),
        maxSymbols: 50,
      },
    });
  }
}
```

### Daily Report Handler

```typescript
async function handleDailyReport(env: Env): Promise<void> {
  // Get users with positions
  const users = await env.DB.prepare(
    "SELECT DISTINCT user_id FROM positions"
  ).all();

  for (const user of users.results) {
    const userId = user.user_id as string;

    // Generate daily P&L report
    await env.QUEUE.send({
      type: "daily_report",
      userId,
    });
  }
}

async function handleWeeklySummary(env: Env): Promise<void> {
  // Similar to daily but with weekly aggregation
  const users = await env.DB.prepare(
    "SELECT DISTINCT user_id FROM positions"
  ).all();

  for (const user of users.results) {
    await env.QUEUE.send({
      type: "weekly_summary",
      userId: user.user_id as string,
    });
  }
}
```

## Notification Routing

### Queue Consumer

```typescript
// src/notifications/handler.ts
export async function handleNotification(
  message: NotificationMessage,
  env: Env
): Promise<void> {
  // Get user notification preferences
  const prefs = await env.DB.prepare(
    "SELECT notification_channels FROM user_preferences WHERE user_id = ?"
  ).bind(message.userId).first();

  if (!prefs) return;

  const channels = JSON.parse(prefs.notification_channels as string || "[]");

  for (const channel of channels) {
    switch (channel) {
      case "discord":
        await sendDiscordNotification(message, env);
        break;
      case "email":
        await sendEmailNotification(message, env);
        break;
      case "push":
        await sendPushNotification(message, env);
        break;
    }
  }
}

async function sendDiscordNotification(
  message: NotificationMessage,
  env: Env
): Promise<void> {
  // Get user's Discord webhook
  const webhook = await env.DB.prepare(
    "SELECT discord_webhook FROM user_preferences WHERE user_id = ?"
  ).bind(message.userId).first();

  if (!webhook?.discord_webhook) return;

  await fetch(webhook.discord_webhook as string, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      content: `**${message.title}**\n${message.body}`,
    }),
  });
}

async function sendEmailNotification(
  message: NotificationMessage,
  env: Env
): Promise<void> {
  // Use Cloudflare Email Workers or external service
  // Implementation depends on email provider
}

async function sendPushNotification(
  message: NotificationMessage,
  env: Env
): Promise<void> {
  // Use web push or mobile push service
  // Implementation depends on push provider
}
```

## Cross-References

- [Workflow Orchestration](./02-workflow-orchestration.md) - Cloudflare Workflows
- [Data Layer](./05-data-layer.md) - Queue processing
- [Infrastructure](./08-infrastructure.md) - Cron configuration
