# Temporal Workflow Architecture

## Overview

Temporal provides the durable execution layer for all long-running operations in the TastyTrade AI system. This includes AI agent analyses, background monitoring tasks, scheduled screeners, and alert processing.

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                       MCP Server (TypeScript)                       │
│                    Temporal Client (workflow starters)              │
└─────────────────────────────────┬───────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────┐
│                         Temporal Server                             │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐                  │
│  │   Frontend  │  │   History   │  │   Matching  │                  │
│  └─────────────┘  └─────────────┘  └─────────────┘                  │
│                                                                     │
│  Task Queues:                                                       │
│  ┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐        │
│  │  analysis-queue │ │background-queue │ │ streaming-queue │        │
│  └─────────────────┘ └─────────────────┘ └─────────────────┘        │
└─────────────────────────────────────────────────────────────────────┘
                                  │
            ┌─────────────────────┼─────────────────────┐
            ▼                     ▼                     ▼
┌───────────────────┐ ┌───────────────────┐ ┌───────────────────┐
│  Analysis Worker  │ │ Background Worker │ │ Streaming Worker  │
│     (Python)      │ │     (Python)      │ │     (Python)      │
│                   │ │                   │ │                   │
│ - Chart analysis  │ │ - News monitoring │ │ - DXLink stream   │
│ - Options analysis│ │ - Price alerts    │ │ - Quote updates   │
│ - Research        │ │ - Scheduled scans │ │ - Greeks stream   │
│ - Full pipeline   │ │ - Report gen      │ │                   │
└───────────────────┘ └───────────────────┘ └───────────────────┘
```

## Workflow Definitions

### Analysis Workflows

#### ChartAnalysisWorkflow

Runs chart analysis using the Chart Analyst agent.

```python
# workflows/analysis.py
from datetime import timedelta
from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from activities.chart import chart_analysis_activity

@workflow.defn
class ChartAnalysisWorkflow:
    """Workflow for running chart analysis on a single symbol."""

    @workflow.run
    async def run(self, params: ChartAnalysisParams) -> ChartAnalysisResult:
        # Run chart analysis activity with retry
        return await workflow.execute_activity(
            chart_analysis_activity,
            params,
            start_to_close_timeout=timedelta(minutes=5),
            retry_policy=RetryPolicy(
                initial_interval=timedelta(seconds=1),
                maximum_interval=timedelta(seconds=30),
                backoff_coefficient=2.0,
                maximum_attempts=3,
            ),
        )
```

**Parameters:**

```python
@dataclass
class ChartAnalysisParams:
    symbol: str
    timeframe: str = "daily"  # "intraday" | "daily" | "weekly"
    analysis_depth: str = "standard"  # "quick" | "standard" | "deep"
    include_chart_image: bool = True
```

**Result:**

```python
@dataclass
class ChartAnalysisResult:
    symbol: str
    recommendation: str  # "bullish" | "bearish" | "neutral" | "reject"
    trend_direction: str
    trend_quality: str
    support_levels: list[dict]
    resistance_levels: list[dict]
    fib_confluence_zones: list[dict]
    extension_risk: str
    chart_notes: str
    tool_calls_made: int
```

#### OptionsAnalysisWorkflow

Runs options analysis using the Options Analyst agent.

```python
@workflow.defn
class OptionsAnalysisWorkflow:
    """Workflow for running options analysis on a single symbol."""

    @workflow.run
    async def run(self, params: OptionsAnalysisParams) -> OptionsAnalysisResult:
        return await workflow.execute_activity(
            options_analysis_activity,
            params,
            start_to_close_timeout=timedelta(minutes=5),
            retry_policy=RetryPolicy(
                initial_interval=timedelta(seconds=1),
                maximum_interval=timedelta(seconds=30),
                backoff_coefficient=2.0,
                maximum_attempts=3,
            ),
        )
```

**Parameters:**

```python
@dataclass
class OptionsAnalysisParams:
    symbol: str
    strategy: str = "csp"  # "csp" | "covered_call" | "spread"
    chart_context: Optional[dict] = None  # From chart analysis
    constraints: Optional[OptionsConstraints] = None

@dataclass
class OptionsConstraints:
    max_delta: float = 0.30
    min_roc: float = 0.5
    dte_min: int = 14
    dte_max: int = 45
```

#### ResearchAnalysisWorkflow

Runs research analysis using the Research Analyst agent.

```python
@workflow.defn
class ResearchAnalysisWorkflow:
    """Workflow for running research/fundamental analysis."""

    @workflow.run
    async def run(self, params: ResearchAnalysisParams) -> ResearchAnalysisResult:
        return await workflow.execute_activity(
            research_analysis_activity,
            params,
            start_to_close_timeout=timedelta(minutes=3),
            retry_policy=RetryPolicy(
                maximum_attempts=3,
            ),
        )
```

#### FullAnalysisWorkflow

Orchestrates the complete analysis pipeline: Chart -> Options -> Research.

```python
@workflow.defn
class FullAnalysisWorkflow:
    """
    Complete analysis pipeline that coordinates all three analysts.

    Flow:
    1. Chart analysis (determines trend and support levels)
    2. If chart passes: Options analysis (with chart context)
    3. If options passes: Research analysis (red flag detection)
    4. Synthesize final recommendation
    """

    @workflow.run
    async def run(self, params: FullAnalysisParams) -> FullAnalysisResult:
        # Step 1: Chart Analysis
        chart_result = await workflow.execute_activity(
            chart_analysis_activity,
            ChartAnalysisParams(
                symbol=params.symbol,
                timeframe="daily",
                analysis_depth="standard",
            ),
            start_to_close_timeout=timedelta(minutes=5),
        )

        if chart_result.recommendation == "reject":
            return FullAnalysisResult(
                symbol=params.symbol,
                overall_recommendation="reject",
                chart_analysis=chart_result,
                reject_reason=f"Chart: {chart_result.chart_notes}",
            )

        # Step 2: Options Analysis (with chart context)
        options_result = await workflow.execute_activity(
            options_analysis_activity,
            OptionsAnalysisParams(
                symbol=params.symbol,
                strategy=params.strategy,
                chart_context={
                    "trend_direction": chart_result.trend_direction,
                    "trend_quality": chart_result.trend_quality,
                    "support_levels": chart_result.support_levels,
                    "fib_confluence_zones": chart_result.fib_confluence_zones,
                },
            ),
            start_to_close_timeout=timedelta(minutes=5),
        )

        if options_result.recommendation == "reject":
            return FullAnalysisResult(
                symbol=params.symbol,
                overall_recommendation="reject",
                chart_analysis=chart_result,
                options_analysis=options_result,
                reject_reason=f"Options: {options_result.options_notes}",
            )

        # Step 3: Research Analysis
        research_result = await workflow.execute_activity(
            research_analysis_activity,
            ResearchAnalysisParams(symbol=params.symbol),
            start_to_close_timeout=timedelta(minutes=3),
        )

        if research_result.recommendation == "reject":
            return FullAnalysisResult(
                symbol=params.symbol,
                overall_recommendation="reject",
                chart_analysis=chart_result,
                options_analysis=options_result,
                research_analysis=research_result,
                reject_reason=f"Research: {research_result.research_notes}",
            )

        # Step 4: Synthesize recommendation
        synthesized = await workflow.execute_activity(
            synthesize_recommendation_activity,
            SynthesizeParams(
                symbol=params.symbol,
                chart=chart_result,
                options=options_result,
                research=research_result,
            ),
            start_to_close_timeout=timedelta(minutes=1),
        )

        return FullAnalysisResult(
            symbol=params.symbol,
            overall_recommendation="select",
            chart_analysis=chart_result,
            options_analysis=options_result,
            research_analysis=research_result,
            synthesized_rationale=synthesized.rationale,
            suggested_position=synthesized.suggested_position,
        )
```

#### CSPScreenerWorkflow

Runs the complete CSP screening and analysis pipeline.

```python
@workflow.defn
class CSPScreenerWorkflow:
    """
    Complete CSP opportunity finder workflow.

    Flow:
    1. Run TradingView screener for candidates
    2. Fetch market metrics for all candidates
    3. Analyze top candidates through full pipeline
    4. Return ranked recommendations
    """

    @workflow.run
    async def run(self, params: CSPScreenerParams) -> CSPScreenerResult:
        # Step 1: Get candidates from screener
        candidates = await workflow.execute_activity(
            run_tradingview_screener_activity,
            ScreenerParams(
                max_price=params.max_price,
                min_volume=params.min_volume,
            ),
            start_to_close_timeout=timedelta(minutes=2),
        )

        if not candidates:
            return CSPScreenerResult(
                candidates_screened=0,
                recommendations=[],
            )

        # Step 2: Batch fetch market metrics
        metrics = await workflow.execute_activity(
            fetch_market_metrics_activity,
            [c["symbol"] for c in candidates],
            start_to_close_timeout=timedelta(minutes=2),
        )

        # Step 3: Filter by earnings and basic criteria
        filtered = self._filter_candidates(candidates, metrics, params)

        # Step 4: Analyze top candidates (with early exit)
        recommendations = []
        for candidate in filtered[:params.max_candidates_to_analyze]:
            if len(recommendations) >= params.max_picks:
                break

            result = await workflow.execute_child_workflow(
                FullAnalysisWorkflow.run,
                FullAnalysisParams(
                    symbol=candidate["symbol"],
                    strategy="csp",
                ),
                id=f"analysis-{candidate['symbol']}-{workflow.info().workflow_id}",
            )

            if result.overall_recommendation == "select":
                recommendations.append(result)

        return CSPScreenerResult(
            candidates_screened=len(candidates),
            candidates_analyzed=len(filtered[:params.max_candidates_to_analyze]),
            recommendations=recommendations,
        )

    def _filter_candidates(self, candidates, metrics, params):
        """Filter candidates based on earnings and basic criteria."""
        filtered = []
        for c in candidates:
            symbol = c["symbol"]
            metric = metrics.get(symbol, {})

            # Skip if earnings within DTE range
            if params.exclude_earnings:
                days_to_earnings = metric.get("days_to_earnings")
                if days_to_earnings and 0 < days_to_earnings < params.dte_max:
                    continue

            filtered.append(c)

        return filtered
```

### Background Workflows

#### NewsWatcherWorkflow

Continuously monitors news for watchlist symbols.

```python
@workflow.defn
class NewsWatcherWorkflow:
    """
    Long-running workflow that monitors news for watched symbols.
    Uses continue-as-new to avoid history buildup.
    """

    def __init__(self):
        self._shutdown = False
        self._watchlist: set[str] = set()

    @workflow.signal
    async def update_watchlist(self, symbols: list[str]) -> None:
        """Signal to update the monitored symbols."""
        self._watchlist = set(symbols)

    @workflow.signal
    async def shutdown(self) -> None:
        """Signal to gracefully shutdown the workflow."""
        self._shutdown = True

    @workflow.query
    def get_watchlist(self) -> list[str]:
        """Query current watchlist."""
        return list(self._watchlist)

    @workflow.run
    async def run(self, params: NewsWatcherParams) -> None:
        # Initialize watchlist
        self._watchlist = set(params.initial_symbols)
        iterations = 0

        while not self._shutdown:
            # Check news for each symbol
            if self._watchlist:
                alerts = await workflow.execute_activity(
                    check_news_activity,
                    list(self._watchlist),
                    start_to_close_timeout=timedelta(minutes=2),
                    heartbeat_timeout=timedelta(seconds=30),
                )

                # Route any alerts
                if alerts:
                    await workflow.execute_activity(
                        route_alerts_activity,
                        alerts,
                        start_to_close_timeout=timedelta(seconds=30),
                    )

            # Wait for next check interval or signal
            await workflow.wait_condition(
                lambda: self._shutdown,
                timeout=timedelta(minutes=params.check_interval_minutes),
            )

            iterations += 1

            # Continue-as-new to prevent history buildup
            if iterations >= 100:
                workflow.continue_as_new(
                    NewsWatcherParams(
                        initial_symbols=list(self._watchlist),
                        check_interval_minutes=params.check_interval_minutes,
                    )
                )
```

#### PriceAlertWorkflow

Monitors price levels and triggers alerts.

```python
@workflow.defn
class PriceAlertWorkflow:
    """
    Long-running workflow that monitors price alerts.
    Each alert is tracked until triggered or cancelled.
    """

    def __init__(self):
        self._alerts: dict[str, PriceAlert] = {}
        self._shutdown = False

    @workflow.signal
    async def add_alert(self, alert: PriceAlert) -> None:
        """Add a new price alert."""
        self._alerts[alert.id] = alert

    @workflow.signal
    async def remove_alert(self, alert_id: str) -> None:
        """Remove a price alert."""
        self._alerts.pop(alert_id, None)

    @workflow.signal
    async def shutdown(self) -> None:
        """Gracefully shutdown the workflow."""
        self._shutdown = True

    @workflow.query
    def get_alerts(self) -> list[PriceAlert]:
        """Query active alerts."""
        return list(self._alerts.values())

    @workflow.run
    async def run(self, params: PriceAlertParams) -> None:
        # Restore alerts from params
        for alert in params.initial_alerts:
            self._alerts[alert.id] = alert

        iterations = 0

        while not self._shutdown and self._alerts:
            # Get symbols to check
            symbols = list(set(a.symbol for a in self._alerts.values()))

            if symbols:
                # Fetch current prices
                prices = await workflow.execute_activity(
                    fetch_quotes_activity,
                    symbols,
                    start_to_close_timeout=timedelta(seconds=30),
                )

                # Check each alert
                triggered = []
                for alert_id, alert in list(self._alerts.items()):
                    price = prices.get(alert.symbol, {}).get("price")
                    if price and self._check_condition(alert, price):
                        triggered.append(alert)
                        del self._alerts[alert_id]

                # Route triggered alerts
                if triggered:
                    await workflow.execute_activity(
                        route_alerts_activity,
                        [self._format_alert(a) for a in triggered],
                        start_to_close_timeout=timedelta(seconds=30),
                    )

            # Wait for next check or signal
            await workflow.wait_condition(
                lambda: self._shutdown or not self._alerts,
                timeout=timedelta(seconds=params.check_interval_seconds),
            )

            iterations += 1

            # Continue-as-new periodically
            if iterations >= 1000:
                workflow.continue_as_new(
                    PriceAlertParams(
                        initial_alerts=list(self._alerts.values()),
                        check_interval_seconds=params.check_interval_seconds,
                    )
                )

    def _check_condition(self, alert: PriceAlert, price: float) -> bool:
        if alert.condition == "above":
            return price >= alert.target_price
        elif alert.condition == "below":
            return price <= alert.target_price
        return False
```

#### ScheduledScreenerWorkflow

Runs screener on a schedule (cron-like).

```python
@workflow.defn
class ScheduledScreenerWorkflow:
    """
    Workflow that runs a screener on a schedule.
    Managed via Temporal Schedules.
    """

    @workflow.run
    async def run(self, params: ScheduledScreenerParams) -> ScheduledScreenerResult:
        # Run the screener
        result = await workflow.execute_child_workflow(
            CSPScreenerWorkflow.run,
            params.screener_params,
            id=f"scheduled-screener-{workflow.info().workflow_id}",
        )

        # Store results
        await workflow.execute_activity(
            store_screener_results_activity,
            StoreResultsParams(
                screener_id=params.screener_id,
                results=result,
                run_time=workflow.now(),
            ),
            start_to_close_timeout=timedelta(seconds=30),
        )

        # Send notifications if configured
        if params.notify_channels and result.recommendations:
            await workflow.execute_activity(
                send_notifications_activity,
                NotificationParams(
                    channels=params.notify_channels,
                    message=self._format_results(result),
                ),
                start_to_close_timeout=timedelta(seconds=30),
            )

        return ScheduledScreenerResult(
            screener_id=params.screener_id,
            run_time=str(workflow.now()),
            recommendations_count=len(result.recommendations),
        )
```

#### PortfolioMonitorWorkflow

Monitors portfolio for risk conditions.

```python
@workflow.defn
class PortfolioMonitorWorkflow:
    """
    Monitors portfolio for risk conditions:
    - P&L thresholds
    - Margin utilization
    - Assignment risk (options near expiration ITM)
    - Concentration risk
    """

    def __init__(self):
        self._shutdown = False
        self._config: PortfolioMonitorConfig = None

    @workflow.signal
    async def update_config(self, config: PortfolioMonitorConfig) -> None:
        self._config = config

    @workflow.signal
    async def shutdown(self) -> None:
        self._shutdown = True

    @workflow.run
    async def run(self, params: PortfolioMonitorParams) -> None:
        self._config = params.config
        iterations = 0

        while not self._shutdown:
            # Fetch portfolio state
            portfolio = await workflow.execute_activity(
                fetch_portfolio_activity,
                params.account_id,
                start_to_close_timeout=timedelta(minutes=1),
            )

            # Check risk conditions
            alerts = []

            # P&L check
            if self._config.pnl_alert_threshold:
                if portfolio.day_pnl_percent <= -self._config.pnl_alert_threshold:
                    alerts.append({
                        "type": "pnl_warning",
                        "message": f"Daily P&L: {portfolio.day_pnl_percent:.1f}%",
                        "severity": "warning",
                    })

            # Margin check
            if self._config.margin_alert_threshold:
                if portfolio.margin_utilization >= self._config.margin_alert_threshold:
                    alerts.append({
                        "type": "margin_warning",
                        "message": f"Margin utilization: {portfolio.margin_utilization:.0f}%",
                        "severity": "warning",
                    })

            # Assignment risk check
            assignment_risks = await workflow.execute_activity(
                check_assignment_risk_activity,
                portfolio.positions,
                start_to_close_timeout=timedelta(seconds=30),
            )
            alerts.extend(assignment_risks)

            # Route alerts
            if alerts:
                await workflow.execute_activity(
                    route_alerts_activity,
                    alerts,
                    start_to_close_timeout=timedelta(seconds=30),
                )

            # Wait for next check
            await workflow.wait_condition(
                lambda: self._shutdown,
                timeout=timedelta(minutes=params.check_interval_minutes),
            )

            iterations += 1
            if iterations >= 100:
                workflow.continue_as_new(params)
```

## Activity Organization

### Activity Structure

```
workers/
├── activities/
│   ├── __init__.py
│   ├── chart.py           # Chart analysis activities
│   ├── options.py         # Options analysis activities
│   ├── research.py        # Research analysis activities
│   ├── screener.py        # Screener activities
│   ├── market_data.py     # Data fetching activities
│   ├── alerts.py          # Alert routing activities
│   ├── portfolio.py       # Portfolio activities
│   └── storage.py         # Database activities
```

### Activity Definitions

```python
# activities/chart.py
from temporalio import activity
from dataclasses import dataclass

@dataclass
class ChartAnalysisParams:
    symbol: str
    timeframe: str
    analysis_depth: str
    include_chart_image: bool = True

@activity.defn
async def chart_analysis_activity(params: ChartAnalysisParams) -> ChartAnalysisResult:
    """
    Run chart analysis using the Chart Analyst agent.

    This activity:
    1. Fetches price history
    2. Runs the agentic loop with chart analysis tools
    3. Returns structured analysis results

    LiteLLM reads API keys from environment variables automatically.
    """
    from agents.chart_analyst import ChartAnalyst

    # Model is configured on the agent class
    # LiteLLM reads API keys from standard env vars (ANTHROPIC_API_KEY, etc.)
    analyst = ChartAnalyst(
        model=params.model or "anthropic/claude-sonnet-4-20250514",
    )

    # Run analysis with heartbeat
    result = await analyst.analyze(
        params.symbol,
        heartbeat_fn=activity.heartbeat,
    )

    return result
```

```python
# activities/market_data.py
@activity.defn
async def fetch_quotes_activity(symbols: list[str]) -> dict[str, QuoteData]:
    """Fetch quotes for multiple symbols."""
    from services.tastytrade import TastyTradeClient

    client = await TastyTradeClient.get_instance()
    return await client.get_quotes(symbols)

@activity.defn
async def fetch_option_chain_activity(params: OptionChainParams) -> OptionChainData:
    """Fetch option chain for a symbol."""
    from services.tastytrade import TastyTradeClient

    client = await TastyTradeClient.get_instance()

    # Heartbeat for long operations
    activity.heartbeat()

    chain = await client.get_option_chain(
        params.symbol,
        expiration=params.expiration,
    )

    return chain

@activity.defn
async def fetch_market_metrics_activity(symbols: list[str]) -> dict[str, MarketMetrics]:
    """Batch fetch market metrics from TastyTrade."""
    from services.tastytrade import TastyTradeClient

    client = await TastyTradeClient.get_instance()
    metrics = await client.get_market_metrics(symbols)

    return {m.symbol: m for m in metrics}
```

```python
# activities/alerts.py
@activity.defn
async def route_alerts_activity(alerts: list[dict]) -> None:
    """Route alerts to configured channels."""
    from services.notifications import NotificationRouter

    router = NotificationRouter()

    for alert in alerts:
        await router.route(alert)

@activity.defn
async def check_news_activity(symbols: list[str]) -> list[dict]:
    """Check for significant news on symbols."""
    from services.news import NewsService

    news_service = NewsService()
    alerts = []

    for symbol in symbols:
        # Heartbeat periodically
        activity.heartbeat()

        news = await news_service.get_recent_news(symbol, hours=1)

        for article in news:
            if article.significance >= 0.7:  # Significant news threshold
                alerts.append({
                    "type": "news",
                    "symbol": symbol,
                    "title": article.title,
                    "url": article.url,
                    "significance": article.significance,
                })

    return alerts
```

## Python Worker Setup

### Worker Configuration

```python
# workers/worker.py
import asyncio
from temporalio.client import Client
from temporalio.worker import Worker

from activities import (
    chart_analysis_activity,
    options_analysis_activity,
    research_analysis_activity,
    fetch_quotes_activity,
    fetch_option_chain_activity,
    fetch_market_metrics_activity,
    route_alerts_activity,
    check_news_activity,
    fetch_portfolio_activity,
    store_screener_results_activity,
)
from workflows import (
    ChartAnalysisWorkflow,
    OptionsAnalysisWorkflow,
    ResearchAnalysisWorkflow,
    FullAnalysisWorkflow,
    CSPScreenerWorkflow,
    NewsWatcherWorkflow,
    PriceAlertWorkflow,
    ScheduledScreenerWorkflow,
    PortfolioMonitorWorkflow,
)

async def main():
    # Connect to Temporal
    client = await Client.connect(
        os.environ.get("TEMPORAL_ADDRESS", "localhost:7233"),
        namespace=os.environ.get("TEMPORAL_NAMESPACE", "default"),
    )

    # Create worker
    worker = Worker(
        client,
        task_queue=os.environ.get("TEMPORAL_TASK_QUEUE", "ttai-queue"),
        workflows=[
            ChartAnalysisWorkflow,
            OptionsAnalysisWorkflow,
            ResearchAnalysisWorkflow,
            FullAnalysisWorkflow,
            CSPScreenerWorkflow,
            NewsWatcherWorkflow,
            PriceAlertWorkflow,
            ScheduledScreenerWorkflow,
            PortfolioMonitorWorkflow,
        ],
        activities=[
            chart_analysis_activity,
            options_analysis_activity,
            research_analysis_activity,
            fetch_quotes_activity,
            fetch_option_chain_activity,
            fetch_market_metrics_activity,
            route_alerts_activity,
            check_news_activity,
            fetch_portfolio_activity,
            store_screener_results_activity,
        ],
    )

    print(f"Starting worker on task queue: {worker.task_queue}")
    await worker.run()

if __name__ == "__main__":
    asyncio.run(main())
```

### Worker Deployment

```yaml
# k8s/worker-deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: ttai-worker
spec:
  replicas: 2
  selector:
    matchLabels:
      app: ttai-worker
  template:
    spec:
      containers:
        - name: worker
          image: ttai-worker:latest
          env:
            - name: TEMPORAL_ADDRESS
              value: "temporal-frontend:7233"
            - name: TEMPORAL_NAMESPACE
              value: "default"
            - name: TEMPORAL_TASK_QUEUE
              value: "ttai-queue"
            - name: ANTHROPIC_API_KEY
              valueFrom:
                secretKeyRef:
                  name: ttai-secrets
                  key: anthropic-api-key
          resources:
            requests:
              memory: "512Mi"
              cpu: "250m"
            limits:
              memory: "2Gi"
              cpu: "1000m"
```

## Retry Policies

### Default Retry Policy

```python
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
```

### Activity-Specific Policies

```python
# For API calls that may rate limit
API_RETRY_POLICY = RetryPolicy(
    initial_interval=timedelta(seconds=5),
    backoff_coefficient=2.0,
    maximum_interval=timedelta(minutes=2),
    maximum_attempts=5,
)

# For AI agent activities (expensive, should not retry often)
AGENT_RETRY_POLICY = RetryPolicy(
    initial_interval=timedelta(seconds=2),
    backoff_coefficient=2.0,
    maximum_interval=timedelta(seconds=30),
    maximum_attempts=2,
)

# For notification activities (should retry more)
NOTIFICATION_RETRY_POLICY = RetryPolicy(
    initial_interval=timedelta(seconds=1),
    backoff_coefficient=1.5,
    maximum_interval=timedelta(seconds=30),
    maximum_attempts=5,
)
```

## Timeout Strategies

### Activity Timeouts

| Activity Type        | Start-to-Close | Heartbeat |
| -------------------- | -------------- | --------- |
| Chart Analysis       | 5 min          | 30 sec    |
| Options Analysis     | 5 min          | 30 sec    |
| Research Analysis    | 3 min          | 30 sec    |
| Quote Fetch          | 30 sec         | -         |
| Option Chain Fetch   | 1 min          | 15 sec    |
| Market Metrics Fetch | 2 min          | 30 sec    |
| Alert Routing        | 30 sec         | -         |
| News Check           | 2 min          | 30 sec    |

### Workflow Timeouts

```python
# For analysis workflows
ANALYSIS_WORKFLOW_TIMEOUT = timedelta(minutes=15)

# For screener workflows
SCREENER_WORKFLOW_TIMEOUT = timedelta(hours=1)

# Background workflows don't have timeouts (long-running)
```

## Continue-As-New Pattern

Long-running workflows use continue-as-new to prevent history buildup:

```python
@workflow.defn
class LongRunningWorkflow:
    MAX_ITERATIONS = 100  # Continue-as-new after this many iterations

    @workflow.run
    async def run(self, params: Params) -> None:
        iterations = 0
        state = params.initial_state

        while not self._should_stop():
            # Do work...
            await self._do_iteration()
            iterations += 1

            # Continue-as-new to reset history
            if iterations >= self.MAX_ITERATIONS:
                workflow.continue_as_new(
                    Params(initial_state=state)
                )

        # Final cleanup if stopping
        await self._cleanup()
```

## Schedule Configuration

### Cron-Based Screeners

```python
# schedule_screeners.py
from temporalio.client import Client, Schedule, ScheduleSpec, ScheduleActionStartWorkflow

async def setup_schedules(client: Client):
    # Morning CSP scan (9:35 AM ET, after market open)
    await client.create_schedule(
        "morning-csp-scan",
        Schedule(
            action=ScheduleActionStartWorkflow(
                ScheduledScreenerWorkflow.run,
                ScheduledScreenerParams(
                    screener_id="morning-csp",
                    screener_params=CSPScreenerParams(
                        max_price=100,
                        min_roc_weekly=0.5,
                    ),
                    notify_channels=["discord", "email"],
                ),
                id="morning-csp-scan",
                task_queue="ttai-queue",
            ),
            spec=ScheduleSpec(
                cron_expressions=["35 9 * * 1-5"],  # 9:35 AM, Mon-Fri
                timezone="America/New_York",
            ),
        ),
    )

    # Afternoon opportunities check (2:00 PM ET)
    await client.create_schedule(
        "afternoon-scan",
        Schedule(
            action=ScheduleActionStartWorkflow(
                ScheduledScreenerWorkflow.run,
                ScheduledScreenerParams(
                    screener_id="afternoon-opportunities",
                    screener_params=CSPScreenerParams(
                        max_price=75,
                        min_roc_weekly=0.6,
                    ),
                ),
                id="afternoon-scan",
                task_queue="ttai-queue",
            ),
            spec=ScheduleSpec(
                cron_expressions=["0 14 * * 1-5"],  # 2:00 PM, Mon-Fri
                timezone="America/New_York",
            ),
        ),
    )
```

## Signal Handling

### Workflow Signal Patterns

```python
@workflow.defn
class SignalDemoWorkflow:
    def __init__(self):
        self._pending_updates = []
        self._shutdown = False

    @workflow.signal
    async def add_item(self, item: str) -> None:
        """Signal to add an item for processing."""
        self._pending_updates.append(item)

    @workflow.signal
    async def shutdown(self) -> None:
        """Signal to initiate graceful shutdown."""
        self._shutdown = True

    @workflow.query
    def status(self) -> dict:
        """Query current workflow status."""
        return {
            "pending_items": len(self._pending_updates),
            "shutting_down": self._shutdown,
        }

    @workflow.run
    async def run(self, params: Params) -> None:
        while not self._shutdown:
            # Wait for items or shutdown
            await workflow.wait_condition(
                lambda: self._pending_updates or self._shutdown
            )

            # Process pending items
            while self._pending_updates:
                item = self._pending_updates.pop(0)
                await workflow.execute_activity(
                    process_item_activity,
                    item,
                    start_to_close_timeout=timedelta(minutes=1),
                )
```

### Sending Signals from MCP Server

```typescript
// src/temporal/client.ts
export class TemporalClient {
  async addPriceAlert(alert: PriceAlert): Promise<void> {
    const handle = this.client.workflow.getHandle("price-alerts");
    await handle.signal("add_alert", alert);
  }

  async updateWatchlist(symbols: string[]): Promise<void> {
    const handle = this.client.workflow.getHandle("news-watcher");
    await handle.signal("update_watchlist", symbols);
  }

  async getAlerts(): Promise<PriceAlert[]> {
    const handle = this.client.workflow.getHandle("price-alerts");
    return await handle.query("get_alerts");
  }
}
```

## Workflow-Activity Data Contracts

### Shared Types

```python
# shared/types.py
from dataclasses import dataclass
from typing import Optional, List
from datetime import datetime

@dataclass
class QuoteData:
    symbol: str
    price: float
    bid: float
    ask: float
    volume: int
    timestamp: datetime

@dataclass
class OptionContract:
    symbol: str
    strike: float
    expiration: str
    option_type: str  # "call" | "put"
    bid: float
    ask: float
    mid: float
    volume: int
    open_interest: int
    iv: float
    delta: float
    gamma: float
    theta: float
    vega: float

@dataclass
class ChartAnalysisResult:
    symbol: str
    recommendation: str
    trend_direction: str
    trend_quality: str
    support_levels: List[dict]
    resistance_levels: List[dict]
    fib_confluence_zones: List[dict]
    extension_risk: str
    chart_notes: str
    tool_calls_made: int

@dataclass
class OptionsAnalysisResult:
    symbol: str
    recommendation: str
    best_strike: Optional[float]
    best_expiration: Optional[str]
    dte: Optional[int]
    weekly_roc: Optional[float]
    delta: Optional[float]
    gamma: Optional[float]
    theta: Optional[float]
    iv_hv_ratio: Optional[float]
    liquidity_score: str
    alternative_strikes: List[dict]
    rationale: str
    options_notes: str
    tool_calls_made: int

@dataclass
class ResearchAnalysisResult:
    symbol: str
    recommendation: str
    news_risk: str
    short_interest_risk: str
    earnings_risk: str
    research_notes: str

@dataclass
class FullAnalysisResult:
    symbol: str
    overall_recommendation: str
    chart_analysis: Optional[ChartAnalysisResult] = None
    options_analysis: Optional[OptionsAnalysisResult] = None
    research_analysis: Optional[ResearchAnalysisResult] = None
    synthesized_rationale: Optional[str] = None
    suggested_position: Optional[dict] = None
    reject_reason: Optional[str] = None
```

### TypeScript Mirror Types

```typescript
// src/temporal/types.ts
export interface QuoteData {
  symbol: string;
  price: number;
  bid: number;
  ask: number;
  volume: number;
  timestamp: string;
}

export interface ChartAnalysisResult {
  symbol: string;
  recommendation: "bullish" | "bearish" | "neutral" | "reject";
  trendDirection: "up" | "down" | "sideways";
  trendQuality: "strong" | "moderate" | "weak";
  supportLevels: Array<{
    price: number;
    strength: string;
    type: string;
  }>;
  resistanceLevels: Array<{
    price: number;
    strength: string;
    type: string;
  }>;
  fibConfluenceZones: Array<{
    price: number;
    levels: string[];
  }>;
  extensionRisk: "low" | "moderate" | "high";
  chartNotes: string;
  toolCallsMade: number;
}

// ... other types matching Python dataclasses
```
