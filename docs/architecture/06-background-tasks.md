# Background Task System

## Overview

The background task system handles continuous monitoring, scheduled operations, and alert delivery. All background tasks run as Temporal workflows for durability and observability.

## Task Types

```
┌─────────────────────────────────────────────────────────────────────┐
│                      Background Task System                         │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  Continuous Workflows              Scheduled Workflows              │
│  ┌─────────────────────┐          ┌─────────────────────┐           │
│  │ News Watcher        │          │ Morning CSP Scan    │           │
│  │ (every 5 min)       │          │ (9:35 AM ET)        │           │
│  └─────────────────────┘          └─────────────────────┘           │
│  ┌─────────────────────┐          ┌─────────────────────┐           │
│  │ Price Alerts        │          │ Afternoon Scan      │           │
│  │ (every 10 sec)      │          │ (2:00 PM ET)        │           │
│  └─────────────────────┘          └─────────────────────┘           │
│  ┌─────────────────────┐          ┌─────────────────────┐           │
│  │ Portfolio Monitor   │          │ Daily Report        │           │
│  │ (every 1 min)       │          │ (4:30 PM ET)        │           │
│  └─────────────────────┘          └─────────────────────┘           │
│                                   ┌─────────────────────┐           │
│                                   │ Weekly Summary      │           │
│                                   │ (Friday 5:00 PM ET) │           │
│                                   └─────────────────────┘           │
│                                                                     │
│  ┌──────────────────────────────────────────────────────┐           │
│  │              Notification Router                     │           │
│  │  Discord | Slack | Email | MCP Resources             │           │
│  └──────────────────────────────────────────────────────┘           │
└─────────────────────────────────────────────────────────────────────┘
```

## Continuous Workflows

### News Monitoring

```python
# workflows/background/news_watcher.py
from datetime import timedelta
from temporalio import workflow
from dataclasses import dataclass, field
from typing import Set, List

with workflow.unsafe.imports_passed_through():
    from activities.alerts import check_news_activity, route_alerts_activity

@dataclass
class NewsWatcherParams:
    initial_symbols: List[str] = field(default_factory=list)
    check_interval_minutes: int = 5
    significance_threshold: float = 0.7

@workflow.defn
class NewsWatcherWorkflow:
    """
    Continuous workflow that monitors news for watched symbols.

    Features:
    - Dynamic symbol list via signals
    - Configurable check interval
    - Significance-based filtering
    - Deduplication of already-seen articles
    - Continue-as-new for history management
    """

    def __init__(self):
        self._shutdown = False
        self._symbols: Set[str] = set()
        self._seen_articles: Set[str] = set()

    @workflow.signal
    async def update_symbols(self, symbols: List[str]) -> None:
        """Update the list of symbols to monitor."""
        self._symbols = set(symbols)
        workflow.logger.info(f"Updated watchlist to {len(self._symbols)} symbols")

    @workflow.signal
    async def add_symbols(self, symbols: List[str]) -> None:
        """Add symbols to the monitoring list."""
        self._symbols.update(symbols)

    @workflow.signal
    async def remove_symbols(self, symbols: List[str]) -> None:
        """Remove symbols from the monitoring list."""
        self._symbols -= set(symbols)

    @workflow.signal
    async def shutdown(self) -> None:
        """Gracefully shutdown the workflow."""
        self._shutdown = True

    @workflow.query
    def get_status(self) -> dict:
        """Query current monitoring status."""
        return {
            "symbols": list(self._symbols),
            "seen_articles": len(self._seen_articles),
            "shutting_down": self._shutdown,
        }

    @workflow.run
    async def run(self, params: NewsWatcherParams) -> None:
        # Initialize state
        self._symbols = set(params.initial_symbols)
        iterations = 0

        workflow.logger.info(
            f"Starting news watcher for {len(self._symbols)} symbols"
        )

        while not self._shutdown:
            if self._symbols:
                try:
                    # Check news for all monitored symbols
                    news_alerts = await workflow.execute_activity(
                        check_news_activity,
                        {
                            "symbols": list(self._symbols),
                            "significance_threshold": params.significance_threshold,
                            "exclude_ids": list(self._seen_articles),
                        },
                        start_to_close_timeout=timedelta(minutes=2),
                        heartbeat_timeout=timedelta(seconds=30),
                    )

                    # Filter out already-seen articles
                    new_alerts = []
                    for alert in news_alerts:
                        article_id = alert.get("article_id")
                        if article_id and article_id not in self._seen_articles:
                            self._seen_articles.add(article_id)
                            new_alerts.append(alert)

                    # Route any new alerts
                    if new_alerts:
                        await workflow.execute_activity(
                            route_alerts_activity,
                            {
                                "alerts": new_alerts,
                                "alert_type": "news",
                            },
                            start_to_close_timeout=timedelta(seconds=30),
                        )

                except Exception as e:
                    workflow.logger.error(f"Error checking news: {e}")

            # Wait for next check interval or signal
            await workflow.wait_condition(
                lambda: self._shutdown,
                timeout=timedelta(minutes=params.check_interval_minutes),
            )

            iterations += 1

            # Continue-as-new to prevent history buildup
            # Also trim seen_articles to last 1000 to prevent memory growth
            if iterations >= 100 or len(self._seen_articles) > 1000:
                trimmed_seen = set(list(self._seen_articles)[-500:])
                workflow.continue_as_new(
                    NewsWatcherParams(
                        initial_symbols=list(self._symbols),
                        check_interval_minutes=params.check_interval_minutes,
                        significance_threshold=params.significance_threshold,
                    )
                )
```

### Price Alerts

```python
# workflows/background/price_alerts.py
from datetime import timedelta
from temporalio import workflow
from dataclasses import dataclass, field
from typing import Dict, List, Optional

with workflow.unsafe.imports_passed_through():
    from activities.market_data import fetch_quotes_activity
    from activities.alerts import route_alerts_activity

@dataclass
class PriceAlert:
    id: str
    symbol: str
    condition: str  # "above" | "below" | "crosses"
    target_price: float
    channels: List[str] = field(default_factory=lambda: ["discord"])
    message_template: Optional[str] = None
    one_time: bool = True  # Delete after triggering

@dataclass
class PriceAlertParams:
    initial_alerts: List[PriceAlert] = field(default_factory=list)
    check_interval_seconds: int = 10

@workflow.defn
class PriceAlertWorkflow:
    """
    Continuous workflow that monitors price levels and triggers alerts.

    Supports:
    - Above/below threshold alerts
    - Cross alerts (bidirectional)
    - One-time and recurring alerts
    - Dynamic alert management via signals
    """

    def __init__(self):
        self._alerts: Dict[str, PriceAlert] = {}
        self._last_prices: Dict[str, float] = {}
        self._shutdown = False

    @workflow.signal
    async def add_alert(self, alert: dict) -> None:
        """Add a new price alert."""
        parsed = PriceAlert(**alert)
        self._alerts[parsed.id] = parsed
        workflow.logger.info(f"Added alert {parsed.id} for {parsed.symbol}")

    @workflow.signal
    async def remove_alert(self, alert_id: str) -> None:
        """Remove a price alert."""
        if alert_id in self._alerts:
            del self._alerts[alert_id]
            workflow.logger.info(f"Removed alert {alert_id}")

    @workflow.signal
    async def shutdown(self) -> None:
        """Gracefully shutdown the workflow."""
        self._shutdown = True

    @workflow.query
    def get_alerts(self) -> List[dict]:
        """Query active alerts."""
        return [
            {
                "id": a.id,
                "symbol": a.symbol,
                "condition": a.condition,
                "target_price": a.target_price,
                "channels": a.channels,
            }
            for a in self._alerts.values()
        ]

    @workflow.run
    async def run(self, params: PriceAlertParams) -> None:
        # Initialize alerts
        for alert_data in params.initial_alerts:
            if isinstance(alert_data, dict):
                alert = PriceAlert(**alert_data)
            else:
                alert = alert_data
            self._alerts[alert.id] = alert

        iterations = 0

        while not self._shutdown:
            if self._alerts:
                # Get unique symbols to check
                symbols = list(set(a.symbol for a in self._alerts.values()))

                try:
                    # Fetch current prices
                    prices = await workflow.execute_activity(
                        fetch_quotes_activity,
                        symbols,
                        start_to_close_timeout=timedelta(seconds=30),
                    )

                    # Check each alert
                    triggered = []
                    to_remove = []

                    for alert_id, alert in list(self._alerts.items()):
                        quote = prices.get(alert.symbol, {})
                        price = quote.get("price")

                        if price is None:
                            continue

                        last_price = self._last_prices.get(alert.symbol)
                        is_triggered = self._check_condition(
                            alert, price, last_price
                        )

                        if is_triggered:
                            triggered.append(self._format_alert(alert, price))
                            if alert.one_time:
                                to_remove.append(alert_id)

                    # Update last prices
                    for symbol, quote in prices.items():
                        if quote.get("price"):
                            self._last_prices[symbol] = quote["price"]

                    # Route triggered alerts
                    if triggered:
                        await workflow.execute_activity(
                            route_alerts_activity,
                            {
                                "alerts": triggered,
                                "alert_type": "price",
                            },
                            start_to_close_timeout=timedelta(seconds=30),
                        )

                    # Remove one-time alerts that triggered
                    for alert_id in to_remove:
                        del self._alerts[alert_id]

                except Exception as e:
                    workflow.logger.error(f"Error checking prices: {e}")

            # Wait for next check or signal
            await workflow.wait_condition(
                lambda: self._shutdown,
                timeout=timedelta(seconds=params.check_interval_seconds),
            )

            iterations += 1

            # Continue-as-new periodically
            if iterations >= 1000:
                workflow.continue_as_new(
                    PriceAlertParams(
                        initial_alerts=[
                            {
                                "id": a.id,
                                "symbol": a.symbol,
                                "condition": a.condition,
                                "target_price": a.target_price,
                                "channels": a.channels,
                                "message_template": a.message_template,
                                "one_time": a.one_time,
                            }
                            for a in self._alerts.values()
                        ],
                        check_interval_seconds=params.check_interval_seconds,
                    )
                )

    def _check_condition(
        self,
        alert: PriceAlert,
        current_price: float,
        last_price: Optional[float],
    ) -> bool:
        """Check if alert condition is met."""
        if alert.condition == "above":
            return current_price >= alert.target_price
        elif alert.condition == "below":
            return current_price <= alert.target_price
        elif alert.condition == "crosses":
            if last_price is None:
                return False
            # Check if price crossed the target in either direction
            crossed_up = last_price < alert.target_price <= current_price
            crossed_down = last_price > alert.target_price >= current_price
            return crossed_up or crossed_down
        return False

    def _format_alert(self, alert: PriceAlert, price: float) -> dict:
        """Format alert for notification."""
        if alert.message_template:
            message = alert.message_template.format(
                symbol=alert.symbol,
                price=price,
                target=alert.target_price,
                condition=alert.condition,
            )
        else:
            message = (
                f"{alert.symbol} {alert.condition} ${alert.target_price:.2f} "
                f"(current: ${price:.2f})"
            )

        return {
            "alert_id": alert.id,
            "symbol": alert.symbol,
            "type": "price",
            "condition": alert.condition,
            "target_price": alert.target_price,
            "current_price": price,
            "message": message,
            "channels": alert.channels,
        }
```

### Portfolio Monitor

```python
# workflows/background/portfolio_monitor.py
from datetime import timedelta
from temporalio import workflow
from dataclasses import dataclass, field
from typing import List, Optional

with workflow.unsafe.imports_passed_through():
    from activities.portfolio import (
        fetch_portfolio_activity,
        check_assignment_risk_activity,
    )
    from activities.alerts import route_alerts_activity

@dataclass
class PortfolioMonitorConfig:
    # P&L thresholds (as percentage)
    daily_loss_warning: float = 2.0  # Warn at 2% daily loss
    daily_loss_critical: float = 5.0  # Critical at 5% daily loss

    # Margin thresholds (as percentage)
    margin_warning: float = 70.0  # Warn at 70% margin utilization
    margin_critical: float = 85.0  # Critical at 85%

    # Assignment risk
    check_assignment_risk: bool = True
    assignment_risk_dte: int = 3  # Check options within 3 DTE

    # Concentration risk
    max_position_percent: float = 20.0  # Max 20% in single position

@dataclass
class PortfolioMonitorParams:
    account_id: str
    config: PortfolioMonitorConfig = field(default_factory=PortfolioMonitorConfig)
    check_interval_minutes: int = 1
    notify_channels: List[str] = field(default_factory=lambda: ["discord"])

@workflow.defn
class PortfolioMonitorWorkflow:
    """
    Monitors portfolio for risk conditions.

    Checks:
    - Daily P&L thresholds
    - Margin utilization
    - Assignment risk (ITM options near expiration)
    - Position concentration
    """

    def __init__(self):
        self._shutdown = False
        self._config: Optional[PortfolioMonitorConfig] = None
        self._last_alert_times: dict = {}  # Prevent alert spam

    @workflow.signal
    async def update_config(self, config: dict) -> None:
        """Update monitoring configuration."""
        self._config = PortfolioMonitorConfig(**config)

    @workflow.signal
    async def shutdown(self) -> None:
        """Gracefully shutdown the workflow."""
        self._shutdown = True

    @workflow.query
    def get_status(self) -> dict:
        """Query current monitoring status."""
        return {
            "config": self._config.__dict__ if self._config else None,
            "shutting_down": self._shutdown,
        }

    @workflow.run
    async def run(self, params: PortfolioMonitorParams) -> None:
        self._config = params.config
        iterations = 0

        while not self._shutdown:
            try:
                # Fetch current portfolio state
                portfolio = await workflow.execute_activity(
                    fetch_portfolio_activity,
                    params.account_id,
                    start_to_close_timeout=timedelta(minutes=1),
                )

                alerts = []

                # Check P&L thresholds
                if portfolio.get("day_pnl_percent") is not None:
                    pnl_pct = portfolio["day_pnl_percent"]

                    if pnl_pct <= -self._config.daily_loss_critical:
                        alerts.append({
                            "type": "pnl_critical",
                            "severity": "critical",
                            "message": f"CRITICAL: Daily P&L at {pnl_pct:.1f}%",
                            "details": {"pnl_percent": pnl_pct},
                        })
                    elif pnl_pct <= -self._config.daily_loss_warning:
                        alerts.append({
                            "type": "pnl_warning",
                            "severity": "warning",
                            "message": f"Warning: Daily P&L at {pnl_pct:.1f}%",
                            "details": {"pnl_percent": pnl_pct},
                        })

                # Check margin utilization
                if portfolio.get("margin_utilization") is not None:
                    margin_pct = portfolio["margin_utilization"]

                    if margin_pct >= self._config.margin_critical:
                        alerts.append({
                            "type": "margin_critical",
                            "severity": "critical",
                            "message": f"CRITICAL: Margin utilization at {margin_pct:.0f}%",
                            "details": {"margin_utilization": margin_pct},
                        })
                    elif margin_pct >= self._config.margin_warning:
                        alerts.append({
                            "type": "margin_warning",
                            "severity": "warning",
                            "message": f"Warning: Margin utilization at {margin_pct:.0f}%",
                            "details": {"margin_utilization": margin_pct},
                        })

                # Check assignment risk
                if self._config.check_assignment_risk:
                    positions = portfolio.get("positions", [])
                    option_positions = [
                        p for p in positions
                        if p.get("option_type") is not None
                    ]

                    if option_positions:
                        assignment_risks = await workflow.execute_activity(
                            check_assignment_risk_activity,
                            {
                                "positions": option_positions,
                                "dte_threshold": self._config.assignment_risk_dte,
                            },
                            start_to_close_timeout=timedelta(seconds=30),
                        )
                        alerts.extend(assignment_risks)

                # Check concentration risk
                total_value = portfolio.get("total_value", 0)
                if total_value > 0:
                    for position in portfolio.get("positions", []):
                        position_pct = (
                            position.get("market_value", 0) / total_value * 100
                        )
                        if position_pct > self._config.max_position_percent:
                            alerts.append({
                                "type": "concentration_warning",
                                "severity": "warning",
                                "symbol": position.get("symbol"),
                                "message": (
                                    f"Concentration warning: {position.get('symbol')} "
                                    f"is {position_pct:.1f}% of portfolio"
                                ),
                                "details": {"position_percent": position_pct},
                            })

                # Filter out duplicate alerts (throttle)
                alerts = self._throttle_alerts(alerts)

                # Route alerts
                if alerts:
                    for alert in alerts:
                        alert["channels"] = params.notify_channels

                    await workflow.execute_activity(
                        route_alerts_activity,
                        {
                            "alerts": alerts,
                            "alert_type": "portfolio",
                        },
                        start_to_close_timeout=timedelta(seconds=30),
                    )

            except Exception as e:
                workflow.logger.error(f"Error monitoring portfolio: {e}")

            # Wait for next check
            await workflow.wait_condition(
                lambda: self._shutdown,
                timeout=timedelta(minutes=params.check_interval_minutes),
            )

            iterations += 1
            if iterations >= 100:
                workflow.continue_as_new(params)

    def _throttle_alerts(self, alerts: list) -> list:
        """Throttle alerts to prevent spam (one per type per 5 minutes)."""
        now = workflow.now()
        throttle_duration = timedelta(minutes=5)
        filtered = []

        for alert in alerts:
            alert_key = f"{alert['type']}:{alert.get('symbol', 'all')}"
            last_time = self._last_alert_times.get(alert_key)

            if last_time is None or (now - last_time) > throttle_duration:
                filtered.append(alert)
                self._last_alert_times[alert_key] = now

        return filtered
```

## Scheduled Workflows

### Scheduled Screener

```python
# workflows/background/scheduled_screener.py
from datetime import timedelta
from temporalio import workflow
from dataclasses import dataclass, field
from typing import List, Optional

with workflow.unsafe.imports_passed_through():
    from activities.screener import run_csp_screener_activity
    from activities.storage import store_screener_results_activity
    from activities.alerts import send_notifications_activity

@dataclass
class ScheduledScreenerParams:
    screener_id: str
    screener_params: dict
    notify_channels: List[str] = field(default_factory=list)

@workflow.defn
class ScheduledScreenerWorkflow:
    """
    Workflow that runs a screener on a schedule.
    Managed via Temporal Schedules for cron-like execution.
    """

    @workflow.run
    async def run(self, params: ScheduledScreenerParams) -> dict:
        workflow.logger.info(f"Running scheduled screener: {params.screener_id}")

        # Run the screener
        result = await workflow.execute_activity(
            run_csp_screener_activity,
            params.screener_params,
            start_to_close_timeout=timedelta(minutes=30),
            heartbeat_timeout=timedelta(minutes=2),
        )

        # Store results
        await workflow.execute_activity(
            store_screener_results_activity,
            {
                "screener_id": params.screener_id,
                "results": result,
                "run_time": str(workflow.now()),
            },
            start_to_close_timeout=timedelta(seconds=30),
        )

        # Send notifications if there are results
        if params.notify_channels and result.get("recommendations"):
            message = self._format_results_message(result)

            await workflow.execute_activity(
                send_notifications_activity,
                {
                    "channels": params.notify_channels,
                    "title": f"CSP Screener Results: {params.screener_id}",
                    "message": message,
                    "data": result,
                },
                start_to_close_timeout=timedelta(seconds=30),
            )

        return {
            "screener_id": params.screener_id,
            "run_time": str(workflow.now()),
            "candidates_screened": result.get("candidates_screened", 0),
            "recommendations_count": len(result.get("recommendations", [])),
        }

    def _format_results_message(self, result: dict) -> str:
        """Format screener results for notification."""
        recs = result.get("recommendations", [])
        if not recs:
            return "No opportunities found meeting criteria."

        lines = [f"Found {len(recs)} opportunities:"]
        for rec in recs[:5]:  # Top 5
            symbol = rec.get("symbol", "?")
            strike = rec.get("best_strike", "?")
            exp = rec.get("best_expiration", "?")
            roc = rec.get("weekly_roc", 0)
            lines.append(f"  - {symbol}: ${strike} put, exp {exp}, {roc:.2f}%/wk")

        if len(recs) > 5:
            lines.append(f"  ... and {len(recs) - 5} more")

        return "\n".join(lines)
```

### Daily/Weekly Reports

```python
# workflows/background/reports.py
from datetime import timedelta, date
from temporalio import workflow
from dataclasses import dataclass, field
from typing import List

with workflow.unsafe.imports_passed_through():
    from activities.portfolio import fetch_portfolio_summary_activity
    from activities.storage import fetch_analysis_history_activity
    from activities.alerts import send_notifications_activity

@dataclass
class DailyReportParams:
    account_id: str
    notify_channels: List[str] = field(default_factory=lambda: ["email"])

@workflow.defn
class DailyReportWorkflow:
    """Generate and send daily portfolio report."""

    @workflow.run
    async def run(self, params: DailyReportParams) -> dict:
        # Fetch portfolio summary
        portfolio = await workflow.execute_activity(
            fetch_portfolio_summary_activity,
            params.account_id,
            start_to_close_timeout=timedelta(minutes=1),
        )

        # Fetch today's analysis history
        analyses = await workflow.execute_activity(
            fetch_analysis_history_activity,
            {"date": str(date.today())},
            start_to_close_timeout=timedelta(seconds=30),
        )

        # Generate report
        report = self._generate_daily_report(portfolio, analyses)

        # Send notifications
        await workflow.execute_activity(
            send_notifications_activity,
            {
                "channels": params.notify_channels,
                "title": f"Daily Report - {date.today()}",
                "message": report,
                "format": "markdown",
            },
            start_to_close_timeout=timedelta(seconds=30),
        )

        return {"report_date": str(date.today()), "sent": True}

    def _generate_daily_report(self, portfolio: dict, analyses: list) -> str:
        """Generate daily report in markdown format."""
        lines = [
            f"# Daily Portfolio Report - {date.today()}",
            "",
            "## Portfolio Summary",
            f"- **Total Value:** ${portfolio.get('total_value', 0):,.2f}",
            f"- **Day P&L:** ${portfolio.get('day_pnl', 0):,.2f} ({portfolio.get('day_pnl_percent', 0):.2f}%)",
            f"- **Open Positions:** {portfolio.get('position_count', 0)}",
            f"- **Buying Power:** ${portfolio.get('buying_power', 0):,.2f}",
            "",
            "## Today's Activity",
        ]

        if analyses:
            lines.append(f"- Analyzed {len(analyses)} symbols")
            recommendations = [a for a in analyses if a.get('recommendation') == 'select']
            if recommendations:
                lines.append(f"- {len(recommendations)} opportunities identified")
        else:
            lines.append("- No analyses run today")

        lines.extend([
            "",
            "## Positions Requiring Attention",
        ])

        # Add positions with high risk
        risky_positions = [
            p for p in portfolio.get("positions", [])
            if p.get("dte", 999) <= 7 or p.get("pnl_percent", 0) <= -20
        ]

        if risky_positions:
            for pos in risky_positions:
                lines.append(f"- **{pos.get('symbol')}**: {pos.get('notes', 'Review needed')}")
        else:
            lines.append("- None")

        return "\n".join(lines)


@dataclass
class WeeklyReportParams:
    account_id: str
    notify_channels: List[str] = field(default_factory=lambda: ["email"])

@workflow.defn
class WeeklyReportWorkflow:
    """Generate and send weekly portfolio report."""

    @workflow.run
    async def run(self, params: WeeklyReportParams) -> dict:
        # Similar to daily but with weekly aggregations
        # ... implementation
        pass
```

## Alert Routing and Deduplication

### Notification Router

```python
# services/notifications.py
import asyncio
import hashlib
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
import httpx

@dataclass
class NotificationChannel:
    type: str  # "discord", "slack", "email", "mcp"
    config: Dict[str, Any]

class NotificationRouter:
    """Routes alerts to configured notification channels."""

    def __init__(self):
        self._channels: Dict[str, NotificationChannel] = {}
        self._sent_hashes: Dict[str, datetime] = {}
        self._dedup_window = timedelta(minutes=5)

    def register_channel(self, name: str, channel: NotificationChannel) -> None:
        """Register a notification channel."""
        self._channels[name] = channel

    async def route(self, alert: Dict[str, Any]) -> List[str]:
        """
        Route an alert to appropriate channels.

        Returns list of channels that were notified.
        """
        # Check for duplicates
        alert_hash = self._hash_alert(alert)
        if self._is_duplicate(alert_hash):
            return []

        # Mark as sent
        self._sent_hashes[alert_hash] = datetime.now()

        # Get target channels
        target_channels = alert.get("channels", ["discord"])
        notified = []

        for channel_name in target_channels:
            channel = self._channels.get(channel_name)
            if channel is None:
                continue

            try:
                if channel.type == "discord":
                    await self._send_discord(channel.config, alert)
                elif channel.type == "slack":
                    await self._send_slack(channel.config, alert)
                elif channel.type == "email":
                    await self._send_email(channel.config, alert)
                elif channel.type == "mcp":
                    await self._publish_mcp(channel.config, alert)

                notified.append(channel_name)

            except Exception as e:
                print(f"Failed to send to {channel_name}: {e}")

        return notified

    def _hash_alert(self, alert: Dict[str, Any]) -> str:
        """Generate hash for deduplication."""
        key_parts = [
            alert.get("type", ""),
            alert.get("symbol", ""),
            alert.get("message", ""),
        ]
        return hashlib.md5("|".join(key_parts).encode()).hexdigest()

    def _is_duplicate(self, alert_hash: str) -> bool:
        """Check if alert was recently sent."""
        last_sent = self._sent_hashes.get(alert_hash)
        if last_sent is None:
            return False
        return datetime.now() - last_sent < self._dedup_window

    async def _send_discord(
        self, config: Dict[str, Any], alert: Dict[str, Any]
    ) -> None:
        """Send alert to Discord webhook."""
        webhook_url = config["webhook_url"]

        # Format for Discord
        embed = self._format_discord_embed(alert)

        async with httpx.AsyncClient() as client:
            await client.post(
                webhook_url,
                json={"embeds": [embed]},
                timeout=10.0,
            )

    def _format_discord_embed(self, alert: Dict[str, Any]) -> Dict[str, Any]:
        """Format alert as Discord embed."""
        severity = alert.get("severity", "info")
        color_map = {
            "critical": 0xFF0000,  # Red
            "warning": 0xFFA500,   # Orange
            "info": 0x00FF00,      # Green
        }

        return {
            "title": f"{alert.get('type', 'Alert').replace('_', ' ').title()}",
            "description": alert.get("message", ""),
            "color": color_map.get(severity, 0x808080),
            "fields": [
                {"name": "Symbol", "value": alert.get("symbol", "N/A"), "inline": True},
                {"name": "Severity", "value": severity.title(), "inline": True},
            ],
            "timestamp": datetime.now().isoformat(),
        }

    async def _send_slack(
        self, config: Dict[str, Any], alert: Dict[str, Any]
    ) -> None:
        """Send alert to Slack webhook."""
        webhook_url = config["webhook_url"]

        # Format for Slack
        blocks = self._format_slack_blocks(alert)

        async with httpx.AsyncClient() as client:
            await client.post(
                webhook_url,
                json={"blocks": blocks},
                timeout=10.0,
            )

    def _format_slack_blocks(self, alert: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Format alert as Slack blocks."""
        severity = alert.get("severity", "info")
        emoji_map = {
            "critical": ":rotating_light:",
            "warning": ":warning:",
            "info": ":information_source:",
        }

        return [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"{emoji_map.get(severity, '')} {alert.get('type', 'Alert')}",
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": alert.get("message", ""),
                }
            },
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": f"*Symbol:* {alert.get('symbol', 'N/A')} | *Severity:* {severity}",
                    }
                ]
            },
        ]

    async def _send_email(
        self, config: Dict[str, Any], alert: Dict[str, Any]
    ) -> None:
        """Send alert via email (SMTP)."""
        import smtplib
        from email.mime.text import MIMEText
        from email.mime.multipart import MIMEMultipart

        smtp_host = config["smtp_host"]
        smtp_port = config.get("smtp_port", 587)
        smtp_user = config["smtp_user"]
        smtp_pass = config["smtp_pass"]
        from_addr = config["from_address"]
        to_addrs = config["to_addresses"]

        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"[{alert.get('severity', 'INFO').upper()}] {alert.get('type', 'Alert')}"
        msg["From"] = from_addr
        msg["To"] = ", ".join(to_addrs)

        # Plain text
        text = f"{alert.get('message', '')}\n\nSymbol: {alert.get('symbol', 'N/A')}"
        msg.attach(MIMEText(text, "plain"))

        # HTML
        html = f"""
        <html>
        <body>
            <h2>{alert.get('type', 'Alert')}</h2>
            <p>{alert.get('message', '')}</p>
            <p><strong>Symbol:</strong> {alert.get('symbol', 'N/A')}</p>
        </body>
        </html>
        """
        msg.attach(MIMEText(html, "html"))

        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.starttls()
            server.login(smtp_user, smtp_pass)
            server.sendmail(from_addr, to_addrs, msg.as_string())

    async def _publish_mcp(
        self, config: Dict[str, Any], alert: Dict[str, Any]
    ) -> None:
        """Publish alert to MCP resource (via Redis pub/sub)."""
        from db.redis import RedisCache

        redis = RedisCache()
        await redis.connect()

        try:
            await redis.publish("alerts", alert)
        finally:
            await redis.disconnect()
```

## Rate Limiting and Prioritization

### Alert Rate Limiter

```python
# services/rate_limiter.py
from datetime import datetime, timedelta
from typing import Dict, Optional
from dataclasses import dataclass, field
from collections import defaultdict

@dataclass
class RateLimitConfig:
    # Per-type limits
    type_limits: Dict[str, int] = field(default_factory=lambda: {
        "price": 10,      # 10 price alerts per window
        "news": 20,       # 20 news alerts per window
        "portfolio": 5,   # 5 portfolio alerts per window
    })
    window_minutes: int = 60
    global_limit: int = 50  # Total alerts per window

class AlertRateLimiter:
    """Rate limiter for alert delivery."""

    def __init__(self, config: Optional[RateLimitConfig] = None):
        self.config = config or RateLimitConfig()
        self._counts: Dict[str, list] = defaultdict(list)
        self._global_count: list = []

    def should_allow(self, alert_type: str) -> bool:
        """Check if an alert should be allowed through."""
        now = datetime.now()
        window_start = now - timedelta(minutes=self.config.window_minutes)

        # Clean old entries
        self._clean_old_entries(window_start)

        # Check global limit
        if len(self._global_count) >= self.config.global_limit:
            return False

        # Check type-specific limit
        type_limit = self.config.type_limits.get(alert_type, 10)
        if len(self._counts[alert_type]) >= type_limit:
            return False

        return True

    def record(self, alert_type: str) -> None:
        """Record an alert being sent."""
        now = datetime.now()
        self._counts[alert_type].append(now)
        self._global_count.append(now)

    def _clean_old_entries(self, cutoff: datetime) -> None:
        """Remove entries older than cutoff."""
        self._global_count = [t for t in self._global_count if t > cutoff]
        for alert_type in self._counts:
            self._counts[alert_type] = [
                t for t in self._counts[alert_type] if t > cutoff
            ]


@dataclass
class PriorityConfig:
    # Priority levels (higher = more important)
    levels: Dict[str, int] = field(default_factory=lambda: {
        "critical": 100,
        "warning": 50,
        "info": 10,
    })

class AlertPrioritizer:
    """Prioritize alerts for delivery order."""

    def __init__(self, config: Optional[PriorityConfig] = None):
        self.config = config or PriorityConfig()

    def sort_by_priority(self, alerts: list) -> list:
        """Sort alerts by priority (highest first)."""
        return sorted(
            alerts,
            key=lambda a: self.config.levels.get(a.get("severity", "info"), 0),
            reverse=True,
        )

    def filter_by_priority(
        self, alerts: list, min_priority: str = "info"
    ) -> list:
        """Filter alerts to only include those at or above min priority."""
        min_level = self.config.levels.get(min_priority, 0)
        return [
            a for a in alerts
            if self.config.levels.get(a.get("severity", "info"), 0) >= min_level
        ]
```

## Schedule Setup

### Creating Temporal Schedules

```python
# scripts/setup_schedules.py
import asyncio
from temporalio.client import Client, Schedule, ScheduleSpec, ScheduleActionStartWorkflow

async def setup_schedules():
    """Set up all scheduled workflows."""
    client = await Client.connect("localhost:7233")

    # Morning CSP Scan (9:35 AM ET, Mon-Fri)
    await client.create_schedule(
        "morning-csp-scan",
        Schedule(
            action=ScheduleActionStartWorkflow(
                "ScheduledScreenerWorkflow",
                args=[{
                    "screener_id": "morning-csp",
                    "screener_params": {
                        "max_price": 100,
                        "min_roc_weekly": 0.5,
                        "max_picks": 10,
                    },
                    "notify_channels": ["discord"],
                }],
                id="morning-csp-scan",
                task_queue="ttai-queue",
            ),
            spec=ScheduleSpec(
                cron_expressions=["35 9 * * 1-5"],
                timezone="America/New_York",
            ),
        ),
    )
    print("Created: morning-csp-scan")

    # Afternoon Scan (2:00 PM ET, Mon-Fri)
    await client.create_schedule(
        "afternoon-scan",
        Schedule(
            action=ScheduleActionStartWorkflow(
                "ScheduledScreenerWorkflow",
                args=[{
                    "screener_id": "afternoon-opportunities",
                    "screener_params": {
                        "max_price": 75,
                        "min_roc_weekly": 0.6,
                        "max_picks": 5,
                    },
                    "notify_channels": ["discord"],
                }],
                id="afternoon-scan",
                task_queue="ttai-queue",
            ),
            spec=ScheduleSpec(
                cron_expressions=["0 14 * * 1-5"],
                timezone="America/New_York",
            ),
        ),
    )
    print("Created: afternoon-scan")

    # Daily Report (4:30 PM ET, Mon-Fri)
    await client.create_schedule(
        "daily-report",
        Schedule(
            action=ScheduleActionStartWorkflow(
                "DailyReportWorkflow",
                args=[{
                    "account_id": "default",
                    "notify_channels": ["email", "discord"],
                }],
                id="daily-report",
                task_queue="ttai-queue",
            ),
            spec=ScheduleSpec(
                cron_expressions=["30 16 * * 1-5"],
                timezone="America/New_York",
            ),
        ),
    )
    print("Created: daily-report")

    # Weekly Summary (Friday 5:00 PM ET)
    await client.create_schedule(
        "weekly-summary",
        Schedule(
            action=ScheduleActionStartWorkflow(
                "WeeklyReportWorkflow",
                args=[{
                    "account_id": "default",
                    "notify_channels": ["email"],
                }],
                id="weekly-summary",
                task_queue="ttai-queue",
            ),
            spec=ScheduleSpec(
                cron_expressions=["0 17 * * 5"],
                timezone="America/New_York",
            ),
        ),
    )
    print("Created: weekly-summary")

    print("\nAll schedules created successfully!")

if __name__ == "__main__":
    asyncio.run(setup_schedules())
```

### Starting Background Workflows

```python
# scripts/start_background_workflows.py
import asyncio
from temporalio.client import Client

async def start_background_workflows():
    """Start long-running background workflows."""
    client = await Client.connect("localhost:7233")

    # Start News Watcher
    await client.start_workflow(
        "NewsWatcherWorkflow",
        args=[{
            "initial_symbols": [],  # Will be updated via signal
            "check_interval_minutes": 5,
        }],
        id="news-watcher",
        task_queue="ttai-queue",
    )
    print("Started: news-watcher")

    # Start Price Alert Monitor
    await client.start_workflow(
        "PriceAlertWorkflow",
        args=[{
            "initial_alerts": [],  # Will be updated via signal
            "check_interval_seconds": 10,
        }],
        id="price-alerts",
        task_queue="ttai-queue",
    )
    print("Started: price-alerts")

    # Start Portfolio Monitor
    await client.start_workflow(
        "PortfolioMonitorWorkflow",
        args=[{
            "account_id": "default",
            "config": {},  # Uses defaults
            "check_interval_minutes": 1,
            "notify_channels": ["discord"],
        }],
        id="portfolio-monitor",
        task_queue="ttai-queue",
    )
    print("Started: portfolio-monitor")

    print("\nAll background workflows started!")

if __name__ == "__main__":
    asyncio.run(start_background_workflows())
```
