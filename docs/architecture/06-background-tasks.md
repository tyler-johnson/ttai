# Background Tasks

## Overview

The TTAI background task system uses Python asyncio for continuous monitoring, scheduled operations, and alert delivery. Background loops run as part of the MCP server process, with different intervals for portfolio monitoring (60s), price alerts (30s), and position sync (5min). Notifications are dispatched through a pluggable backend system that supports both Tauri (sidecar mode) and webhooks (headless mode).

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                    Python MCP Server                                 │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ┌────────────────────────────────────────────────────────────────┐ │
│  │                   Background Monitor Loops                      │ │
│  │  ┌────────────┐  ┌────────────┐  ┌────────────┐                │ │
│  │  │  Portfolio │  │   Price    │  │  Position  │                │ │
│  │  │  Monitor   │  │  Alerts    │  │   Sync     │                │ │
│  │  │   (60s)    │  │   (30s)    │  │  (5min)    │                │ │
│  │  └────────────┘  └────────────┘  └────────────┘                │ │
│  └────────────────────────────────────────────────────────────────┘ │
│                                                                      │
│  ┌────────────────────────────────────────────────────────────────┐ │
│  │                   Scheduled Jobs (Time-based)                   │ │
│  │  ┌────────────┐  ┌────────────┐  ┌────────────┐                │ │
│  │  │  Morning   │  │    EOD     │  │   Weekly   │                │ │
│  │  │ Briefing   │  │  Summary   │  │  Review    │                │ │
│  │  │  9:30 AM   │  │  4:00 PM   │  │  Fri 5 PM  │                │ │
│  │  └────────────┘  └────────────┘  └────────────┘                │ │
│  └────────────────────────────────────────────────────────────────┘ │
│                                                                      │
│  ┌────────────────────────────────────────────────────────────────┐ │
│  │               Notification System (Pluggable Backend)           │ │
│  │  ┌─────────────────────────────────────────────────────────┐   │ │
│  │  │               NotificationBackend (Abstract)             │   │ │
│  │  └──────────────────────┬──────────────────────────────────┘   │ │
│  │                         │                                       │ │
│  │         ┌───────────────┴───────────────┐                      │ │
│  │         ▼                               ▼                      │ │
│  │  ┌─────────────────┐          ┌─────────────────┐              │ │
│  │  │  TauriNotifier  │          │ WebhookNotifier │              │ │
│  │  │  (stderr→Tauri) │          │  (HTTP POST)    │              │ │
│  │  │  Sidecar Mode   │          │  Headless Mode  │              │ │
│  │  └─────────────────┘          └─────────────────┘              │ │
│  └────────────────────────────────────────────────────────────────┘ │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

### Notification Flow

```
┌─────────────────────────────────────────────────────────────────────┐
│                    Notification Flow                                 │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  SIDECAR MODE                        HEADLESS MODE                  │
│  ┌─────────────┐                     ┌─────────────┐                │
│  │  Monitor    │                     │  Monitor    │                │
│  │  triggers   │                     │  triggers   │                │
│  └──────┬──────┘                     └──────┬──────┘                │
│         │                                   │                        │
│         ▼                                   ▼                        │
│  ┌─────────────┐                     ┌─────────────┐                │
│  │   Notifier  │                     │   Notifier  │                │
│  │   .send()   │                     │   .send()   │                │
│  └──────┬──────┘                     └──────┬──────┘                │
│         │                                   │                        │
│         ▼                                   ▼                        │
│  ┌─────────────┐                     ┌─────────────┐                │
│  │TauriNotifier│                     │  Webhook    │                │
│  │ write JSON  │                     │ HTTP POST   │                │
│  │ to stderr   │                     │ to URL      │                │
│  └──────┬──────┘                     └──────┬──────┘                │
│         │                                   │                        │
│         ▼                                   ▼                        │
│  ┌─────────────┐                     ┌─────────────┐                │
│  │ Tauri reads │                     │  Webhook    │                │
│  │ stderr,     │                     │  Receiver   │                │
│  │ shows OS    │                     │  (Slack,    │                │
│  │ notification│                     │  Discord,   │                │
│  └─────────────┘                     │  custom)    │                │
│                                      └─────────────┘                │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

## Notification System

### Abstract Backend Interface

```python
# src/services/notifications.py
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional
import json
import sys
import httpx
import logging

logger = logging.getLogger(__name__)

class NotificationType(str, Enum):
    """Types of notifications."""
    ALERT_TRIGGERED = "alert_triggered"
    ANALYSIS_COMPLETE = "analysis_complete"
    POSITION_UPDATE = "position_update"
    ERROR = "error"
    INFO = "info"
    WARNING = "warning"

@dataclass
class Notification:
    """A notification to be sent."""
    notification_type: NotificationType
    title: str
    body: str
    data: Dict[str, Any] = None
    timestamp: datetime = None

    def __post_init__(self):
        if self.data is None:
            self.data = {}
        if self.timestamp is None:
            self.timestamp = datetime.now()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": "notification",
            "notification_type": self.notification_type.value,
            "title": self.title,
            "body": self.body,
            "data": self.data,
            "timestamp": self.timestamp.isoformat(),
        }


class NotificationBackend(ABC):
    """Abstract base class for notification backends."""

    @abstractmethod
    async def send(self, notification: Notification) -> None:
        """Send a notification through this backend."""
        pass


class TauriNotifier(NotificationBackend):
    """
    Notification backend for Tauri sidecar mode.

    Emits JSON to stderr, which Tauri's sidecar handler reads
    and converts to OS-level notifications.
    """

    async def send(self, notification: Notification) -> None:
        """Write notification JSON to stderr for Tauri to capture."""
        print(json.dumps(notification.to_dict()), file=sys.stderr, flush=True)


class WebhookNotifier(NotificationBackend):
    """
    Notification backend for headless mode.

    POSTs notifications to configured webhook URLs.
    Compatible with Slack, Discord, and custom webhook receivers.
    """

    def __init__(self, webhook_url: str, timeout: float = 10.0):
        self.webhook_url = webhook_url
        self.timeout = timeout

    async def send(self, notification: Notification) -> None:
        """POST notification to webhook URL."""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self.webhook_url,
                    json=notification.to_dict(),
                    timeout=self.timeout
                )
                response.raise_for_status()
                logger.debug(f"Webhook notification sent: {notification.title}")
        except httpx.HTTPError as e:
            logger.error(f"Failed to send webhook notification: {e}")
        except Exception as e:
            logger.error(f"Unexpected error sending webhook: {e}")


class CompositeNotifier(NotificationBackend):
    """
    Notification backend that sends to multiple backends.

    Useful for sending to both local and remote destinations.
    """

    def __init__(self, backends: list[NotificationBackend]):
        self.backends = backends

    async def send(self, notification: Notification) -> None:
        """Send to all configured backends."""
        for backend in self.backends:
            try:
                await backend.send(notification)
            except Exception as e:
                logger.error(f"Backend {backend.__class__.__name__} failed: {e}")


class NullNotifier(NotificationBackend):
    """No-op notification backend for testing or when notifications are disabled."""

    async def send(self, notification: Notification) -> None:
        """Do nothing."""
        logger.debug(f"Notification suppressed: {notification.title}")


# Global notifier instance
_notifier: NotificationBackend = None


def configure_notifier(
    backend: str = "auto",
    webhook_url: Optional[str] = None,
    transport: str = "stdio"
) -> NotificationBackend:
    """
    Configure the notification backend.

    Args:
        backend: "auto", "tauri", "webhook", or "none"
        webhook_url: URL for webhook backend
        transport: Current transport mode ("stdio" or "sse")

    Returns:
        Configured NotificationBackend
    """
    global _notifier

    if backend == "none":
        _notifier = NullNotifier()
    elif backend == "webhook":
        if not webhook_url:
            raise ValueError("webhook_url required for webhook backend")
        _notifier = WebhookNotifier(webhook_url)
    elif backend == "tauri":
        _notifier = TauriNotifier()
    elif backend == "auto":
        # Auto-detect based on transport
        if transport == "stdio":
            _notifier = TauriNotifier()
        elif webhook_url:
            _notifier = WebhookNotifier(webhook_url)
        else:
            # No webhook configured in headless mode, log only
            _notifier = NullNotifier()
            logger.warning("No webhook URL configured, notifications disabled")
    else:
        raise ValueError(f"Unknown notification backend: {backend}")

    logger.info(f"Notification backend configured: {_notifier.__class__.__name__}")
    return _notifier


def get_notifier() -> NotificationBackend:
    """Get the configured notifier, creating a default if needed."""
    global _notifier
    if _notifier is None:
        _notifier = TauriNotifier()  # Default to Tauri for backwards compatibility
    return _notifier
```

### Notification Emitter (High-Level API)

```python
# src/server/notifications.py
from ..services.notifications import (
    Notification, NotificationType, get_notifier
)

class NotificationEmitter:
    """
    High-level notification API used by monitors and services.

    Wraps the notification backend with convenient helper methods.
    """

    @staticmethod
    async def emit(
        notification_type: NotificationType,
        title: str,
        body: str,
        data: dict | None = None
    ) -> None:
        """Emit a notification through the configured backend."""
        notification = Notification(
            notification_type=notification_type,
            title=title,
            body=body,
            data=data or {}
        )
        await get_notifier().send(notification)

    @staticmethod
    async def alert_triggered(
        symbol: str,
        condition: str,
        threshold: float,
        current_price: float
    ) -> None:
        """Emit a price alert notification."""
        await NotificationEmitter.emit(
            NotificationType.ALERT_TRIGGERED,
            f"Price Alert: {symbol}",
            f"{symbol} is now ${current_price:.2f} ({condition} ${threshold:.2f})",
            {
                "symbol": symbol,
                "condition": condition,
                "threshold": threshold,
                "current_price": current_price
            }
        )

    @staticmethod
    async def analysis_complete(symbol: str, recommendation: str) -> None:
        """Emit an analysis complete notification."""
        rec_text = {
            "strong_select": "Strong Select",
            "select": "Select",
            "watchlist": "Watchlist",
            "reject": "Reject"
        }.get(recommendation, recommendation)

        await NotificationEmitter.emit(
            NotificationType.ANALYSIS_COMPLETE,
            f"Analysis Complete: {symbol}",
            f"Recommendation: {rec_text}",
            {"symbol": symbol, "recommendation": recommendation}
        )

    @staticmethod
    async def position_opened(symbol: str, quantity: int, price: float) -> None:
        """Emit position opened notification."""
        await NotificationEmitter.emit(
            NotificationType.POSITION_UPDATE,
            "Position Opened",
            f"Opened {quantity} {symbol} @ ${price:.2f}",
            {"symbol": symbol, "quantity": quantity, "price": price}
        )

    @staticmethod
    async def position_closed(
        symbol: str,
        pnl: float,
        pnl_percent: float
    ) -> None:
        """Emit position closed notification."""
        pnl_str = f"+${pnl:.2f}" if pnl >= 0 else f"-${abs(pnl):.2f}"
        pct_str = f"+{pnl_percent:.1f}%" if pnl >= 0 else f"{pnl_percent:.1f}%"

        await NotificationEmitter.emit(
            NotificationType.POSITION_UPDATE,
            "Position Closed",
            f"{symbol}: {pnl_str} ({pct_str})",
            {"symbol": symbol, "pnl": pnl, "pnl_percent": pnl_percent}
        )

    @staticmethod
    async def info(title: str, body: str, data: dict | None = None) -> None:
        """Emit an info notification."""
        await NotificationEmitter.emit(NotificationType.INFO, title, body, data)

    @staticmethod
    async def warning(title: str, body: str, data: dict | None = None) -> None:
        """Emit a warning notification."""
        await NotificationEmitter.emit(NotificationType.WARNING, title, body, data)

    @staticmethod
    async def error(title: str, body: str, data: dict | None = None) -> None:
        """Emit an error notification."""
        await NotificationEmitter.emit(NotificationType.ERROR, title, body, data)
```

## Background Monitor Implementation

### Base Loop Class

```python
# src/tasks/loops.py
import asyncio
import logging
from abc import ABC, abstractmethod
from typing import Optional

from .manager import task_manager

logger = logging.getLogger(__name__)

class BackgroundLoop(ABC):
    """
    Base class for background monitoring loops.

    Provides:
    - Automatic restart on failure
    - Graceful shutdown handling
    - Status tracking
    """

    def __init__(self, interval_seconds: float, name: str):
        self.interval = interval_seconds
        self.name = name
        self._running = False
        self._task_id: Optional[str] = None
        self._iteration_count = 0
        self._last_error: Optional[str] = None

    async def start(self) -> str:
        """Start the background loop."""
        if self._running:
            return self._task_id

        self._running = True
        self._task_id = await task_manager.start_task(
            self._loop(),
            name=f"{self.name} Loop",
            task_id=f"loop-{self.name.lower().replace(' ', '-')}"
        )

        logger.info(f"Started {self.name} loop (interval: {self.interval}s)")
        return self._task_id

    async def stop(self) -> None:
        """Stop the background loop."""
        self._running = False
        if self._task_id:
            await task_manager.cancel_task(self._task_id)
            self._task_id = None
            logger.info(f"Stopped {self.name} loop")

    async def _loop(self) -> None:
        """Main loop implementation with error handling."""
        while self._running and not task_manager.is_shutting_down:
            try:
                await self.execute()
                self._iteration_count += 1
                self._last_error = None
            except Exception as e:
                self._last_error = str(e)
                logger.error(f"{self.name} loop error: {e}")

            # Wait for next interval, but check for shutdown
            try:
                await asyncio.sleep(self.interval)
            except asyncio.CancelledError:
                break

    @abstractmethod
    async def execute(self) -> None:
        """Execute one iteration of the loop. Implemented by subclasses."""
        pass

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def stats(self) -> dict:
        return {
            "name": self.name,
            "running": self._running,
            "interval": self.interval,
            "iterations": self._iteration_count,
            "last_error": self._last_error,
        }
```

### Portfolio Monitor (60s)

```python
# src/tasks/monitors/portfolio.py
import logging
from datetime import datetime
from typing import Dict, List, Any

from ..loops import BackgroundLoop
from ...services.tastytrade import TastyTradeService
from ...services.database import DatabaseService
from ...server.notifications import NotificationEmitter

logger = logging.getLogger(__name__)

class PortfolioMonitor(BackgroundLoop):
    """
    Monitors portfolio positions for various alert conditions.

    Checks:
    - Price alerts (above/below thresholds)
    - Delta alerts (for options positions)
    - DTE alerts (days to expiration warnings)
    - P&L alerts (profit/loss thresholds)
    """

    def __init__(
        self,
        tastytrade: TastyTradeService,
        db: DatabaseService,
        interval_seconds: float = 60.0
    ):
        super().__init__(interval_seconds, "Portfolio Monitor")
        self.tastytrade = tastytrade
        self.db = db

    async def execute(self) -> None:
        """Check all portfolio alert conditions."""
        # Get current positions
        try:
            positions = await self.tastytrade.get_positions()
        except Exception as e:
            logger.warning(f"Failed to fetch positions: {e}")
            return

        if not positions:
            return

        # Get active alerts
        alerts = await self.db.get_active_alerts()
        if not alerts:
            return

        # Get quotes for all position symbols
        symbols = list(set(p["underlying_symbol"] or p["symbol"] for p in positions))
        quotes = await self.tastytrade.get_quotes(symbols)

        # Check each alert
        for alert in alerts:
            await self._check_alert(alert, quotes, positions)

    async def _check_alert(
        self,
        alert: Dict[str, Any],
        quotes: Dict[str, Dict],
        positions: List[Dict]
    ) -> None:
        """Check if an alert condition is met."""
        symbol = alert["symbol"]
        quote = quotes.get(symbol)

        if not quote:
            return

        current_price = quote.get("last", quote.get("mark", 0))
        triggered = False

        alert_type = alert["alert_type"]
        condition = alert["condition"]
        threshold = alert["threshold"]

        # Price alerts
        if alert_type == "price":
            if condition == "above" and current_price >= threshold:
                triggered = True
            elif condition == "below" and current_price <= threshold:
                triggered = True

        # Delta alerts (for options)
        elif alert_type == "delta":
            for pos in positions:
                if pos["underlying_symbol"] == symbol:
                    delta = abs(pos.get("delta", 0))
                    if delta >= threshold:
                        triggered = True
                        break

        # DTE alerts
        elif alert_type == "dte":
            for pos in positions:
                if pos["underlying_symbol"] == symbol and pos.get("expiration_date"):
                    exp_date = datetime.fromisoformat(pos["expiration_date"])
                    dte = (exp_date - datetime.now()).days
                    if dte <= threshold:
                        triggered = True
                        break

        # P&L alerts
        elif alert_type == "pnl":
            for pos in positions:
                if pos["symbol"] == symbol or pos["underlying_symbol"] == symbol:
                    pnl_percent = self._calculate_pnl_percent(pos)
                    if condition == "profit" and pnl_percent >= threshold:
                        triggered = True
                    elif condition == "loss" and pnl_percent <= -threshold:
                        triggered = True

        if triggered:
            await self._trigger_alert(alert, current_price)

    def _calculate_pnl_percent(self, position: Dict) -> float:
        """Calculate P&L percentage for a position."""
        avg_price = position.get("average_open_price", 0)
        mark = position.get("mark", 0)

        if avg_price == 0:
            return 0

        return ((mark - avg_price) / avg_price) * 100

    async def _trigger_alert(
        self,
        alert: Dict[str, Any],
        current_price: float
    ) -> None:
        """Handle a triggered alert."""
        # Mark alert as triggered
        await self.db.trigger_alert(alert["id"])

        # Send notification (works in both sidecar and headless modes)
        await NotificationEmitter.alert_triggered(
            symbol=alert["symbol"],
            condition=alert["condition"],
            threshold=alert["threshold"],
            current_price=current_price
        )

        logger.info(
            f"Alert triggered: {alert['symbol']} "
            f"{alert['alert_type']} {alert['condition']} {alert['threshold']}"
        )
```

### Price Alert Monitor (30s)

```python
# src/tasks/monitors/price_alerts.py
import logging
from typing import Dict, Any

from ..loops import BackgroundLoop
from ...services.tastytrade import TastyTradeService
from ...services.database import DatabaseService
from ...server.notifications import NotificationEmitter

logger = logging.getLogger(__name__)

class PriceAlertMonitor(BackgroundLoop):
    """
    Fast-polling monitor for price alerts.

    Runs more frequently than portfolio monitor to catch
    rapid price movements.
    """

    def __init__(
        self,
        tastytrade: TastyTradeService,
        db: DatabaseService,
        interval_seconds: float = 30.0
    ):
        super().__init__(interval_seconds, "Price Alerts")
        self.tastytrade = tastytrade
        self.db = db

    async def execute(self) -> None:
        """Check all active price alerts."""
        # Get active price alerts only
        alerts = await self.db.get_price_alerts()
        if not alerts:
            return

        # Batch fetch quotes for all alert symbols
        symbols = list(set(a["symbol"] for a in alerts))
        quotes = await self.tastytrade.get_quotes(symbols)

        # Check each alert
        for alert in alerts:
            symbol = alert["symbol"]
            quote = quotes.get(symbol)

            if not quote:
                continue

            current_price = quote.get("last", quote.get("mark", 0))
            triggered = False

            if alert["condition"] == "above" and current_price >= alert["threshold"]:
                triggered = True
            elif alert["condition"] == "below" and current_price <= alert["threshold"]:
                triggered = True

            if triggered:
                await self.db.trigger_alert(alert["id"])

                await NotificationEmitter.alert_triggered(
                    symbol=symbol,
                    condition=alert["condition"],
                    threshold=alert["threshold"],
                    current_price=current_price
                )

                logger.info(
                    f"Price alert: {symbol} at ${current_price:.2f} "
                    f"({alert['condition']} ${alert['threshold']:.2f})"
                )
```

### Position Sync Monitor (5min)

```python
# src/tasks/monitors/position_sync.py
import logging
from typing import List, Dict, Any

from ..loops import BackgroundLoop
from ...services.tastytrade import TastyTradeService
from ...services.database import DatabaseService

logger = logging.getLogger(__name__)

class PositionSyncMonitor(BackgroundLoop):
    """
    Syncs positions from TastyTrade to local database.

    Runs less frequently as positions don't change rapidly.
    Also syncs account balances and transaction history.
    """

    def __init__(
        self,
        tastytrade: TastyTradeService,
        db: DatabaseService,
        interval_seconds: float = 300.0  # 5 minutes
    ):
        super().__init__(interval_seconds, "Position Sync")
        self.tastytrade = tastytrade
        self.db = db
        self._last_positions: List[Dict] = []

    async def execute(self) -> None:
        """Sync positions from TastyTrade."""
        try:
            # Fetch current positions
            positions = await self.tastytrade.get_positions()

            # Sync to local database
            await self.db.sync_positions(positions)

            # Check for position changes
            changes = self._detect_changes(positions)
            if changes:
                logger.info(f"Position changes detected: {changes}")

            self._last_positions = positions
            logger.debug(f"Synced {len(positions)} positions")

        except Exception as e:
            logger.error(f"Position sync failed: {e}")

    def _detect_changes(self, new_positions: List[Dict]) -> Dict[str, Any]:
        """Detect changes between old and new positions."""
        old_symbols = {p["symbol"] for p in self._last_positions}
        new_symbols = {p["symbol"] for p in new_positions}

        return {
            "opened": list(new_symbols - old_symbols),
            "closed": list(old_symbols - new_symbols),
        }
```

## Scheduled Jobs

### Scheduler Implementation

```python
# src/tasks/scheduler.py
import asyncio
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from typing import Callable, Coroutine, List, Optional
from enum import Enum
import logging

from .manager import task_manager

logger = logging.getLogger(__name__)

class DayOfWeek(Enum):
    MONDAY = 0
    TUESDAY = 1
    WEDNESDAY = 2
    THURSDAY = 3
    FRIDAY = 4
    SATURDAY = 5
    SUNDAY = 6

# Market hours (Eastern Time)
MARKET_OPEN = time(9, 30)
MARKET_CLOSE = time(16, 0)

@dataclass
class ScheduledJob:
    """A scheduled job definition."""
    id: str
    name: str
    func: Callable[[], Coroutine]
    schedule_time: time
    days: List[DayOfWeek]
    enabled: bool = True
    last_run: Optional[datetime] = None
    next_run: Optional[datetime] = None

class Scheduler:
    """
    Time-based job scheduler.

    Runs jobs at specific times on specific days.
    """

    def __init__(self):
        self._jobs: dict[str, ScheduledJob] = {}
        self._running = False
        self._task_id: Optional[str] = None

    def add_job(
        self,
        job_id: str,
        name: str,
        func: Callable[[], Coroutine],
        schedule_time: time,
        days: Optional[List[DayOfWeek]] = None
    ) -> None:
        """Add a scheduled job."""
        if days is None:
            # Default to weekdays
            days = [
                DayOfWeek.MONDAY,
                DayOfWeek.TUESDAY,
                DayOfWeek.WEDNESDAY,
                DayOfWeek.THURSDAY,
                DayOfWeek.FRIDAY
            ]

        job = ScheduledJob(
            id=job_id,
            name=name,
            func=func,
            schedule_time=schedule_time,
            days=days
        )
        job.next_run = self._calculate_next_run(job)
        self._jobs[job_id] = job

        logger.info(
            f"Scheduled '{name}' at {schedule_time} "
            f"on {[d.name for d in days]}"
        )

    async def start(self) -> None:
        """Start the scheduler."""
        if self._running:
            return

        self._running = True
        self._task_id = await task_manager.start_task(
            self._scheduler_loop(),
            name="Job Scheduler",
            task_id="scheduler"
        )

    async def stop(self) -> None:
        """Stop the scheduler."""
        self._running = False
        if self._task_id:
            await task_manager.cancel_task(self._task_id)

    async def _scheduler_loop(self) -> None:
        """Main scheduler loop."""
        while self._running and not task_manager.is_shutting_down:
            now = datetime.now()

            for job in self._jobs.values():
                if not job.enabled or job.next_run is None:
                    continue

                if now >= job.next_run:
                    await self._run_job(job)
                    job.last_run = now
                    job.next_run = self._calculate_next_run(job)

            # Check every minute
            await asyncio.sleep(60)

    async def _run_job(self, job: ScheduledJob) -> None:
        """Execute a scheduled job."""
        logger.info(f"Running scheduled job: {job.name}")
        try:
            await job.func()
        except Exception as e:
            logger.error(f"Job '{job.name}' failed: {e}")

    def _calculate_next_run(self, job: ScheduledJob) -> Optional[datetime]:
        """Calculate next run time for a job."""
        now = datetime.now()
        today = now.date()

        # Check if can run today
        today_weekday = DayOfWeek(today.weekday())
        today_run_time = datetime.combine(today, job.schedule_time)

        if today_weekday in job.days and now < today_run_time:
            return today_run_time

        # Find next valid day
        for days_ahead in range(1, 8):
            next_date = today + timedelta(days=days_ahead)
            next_weekday = DayOfWeek(next_date.weekday())

            if next_weekday in job.days:
                return datetime.combine(next_date, job.schedule_time)

        return None
```

### Job Definitions

```python
# src/tasks/scheduled_jobs.py
from datetime import time
import logging

from .scheduler import scheduler, DayOfWeek
from ..services.tastytrade import TastyTradeService
from ..services.database import DatabaseService
from ..server.notifications import NotificationEmitter

logger = logging.getLogger(__name__)

async def setup_scheduled_jobs(
    tastytrade: TastyTradeService,
    db: DatabaseService
) -> None:
    """Configure all scheduled jobs."""

    # Morning Briefing - 9:30 AM ET on weekdays
    async def morning_briefing():
        """Generate morning portfolio briefing."""
        positions = await tastytrade.get_positions()
        balances = await tastytrade.get_balances()

        if positions:
            # Find positions expiring this week
            expiring_soon = [
                p for p in positions
                if p.get("instrument_type") == "Option"
                and p.get("dte", 999) <= 7
            ]

            body = f"You have {len(positions)} open positions"
            if expiring_soon:
                body += f", {len(expiring_soon)} expiring this week"

            await NotificationEmitter.info(
                "Good Morning!",
                body,
                {
                    "positions": len(positions),
                    "expiring_soon": len(expiring_soon),
                    "buying_power": balances.get("equity_buying_power", 0)
                }
            )

    scheduler.add_job(
        job_id="morning_briefing",
        name="Morning Briefing",
        func=morning_briefing,
        schedule_time=time(9, 30)
    )

    # End of Day Summary - 4:00 PM ET on weekdays
    async def eod_summary():
        """Generate end-of-day summary."""
        positions = await tastytrade.get_positions()
        balances = await tastytrade.get_balances()

        # Calculate day's P&L
        day_pnl = sum(
            p.get("realized_day_gain", 0) or 0
            for p in positions
        )

        pnl_str = f"+${day_pnl:,.2f}" if day_pnl >= 0 else f"-${abs(day_pnl):,.2f}"

        await NotificationEmitter.info(
            "Market Closed",
            f"Today's P&L: {pnl_str}",
            {
                "day_pnl": day_pnl,
                "nlv": balances.get("net_liquidating_value", 0)
            }
        )

    scheduler.add_job(
        job_id="eod_summary",
        name="End of Day Summary",
        func=eod_summary,
        schedule_time=time(16, 0)
    )

    # Weekly Review - Friday 5:00 PM
    async def weekly_review():
        """Generate weekly performance review."""
        analyses = await db.get_recent_analyses(limit=50)

        # Count recommendations
        recommendations = {}
        for a in analyses:
            rec = a.get("recommendation", "unknown")
            recommendations[rec] = recommendations.get(rec, 0) + 1

        await NotificationEmitter.info(
            "Weekly Review",
            f"Completed {len(analyses)} analyses this week",
            {"analyses": len(analyses), "recommendations": recommendations}
        )

    scheduler.add_job(
        job_id="weekly_review",
        name="Weekly Review",
        func=weekly_review,
        schedule_time=time(17, 0),
        days=[DayOfWeek.FRIDAY]
    )

    # Start the scheduler
    await scheduler.start()
```

## Configuration

### Environment Variables for Notifications

| Variable | Description | Default |
|----------|-------------|---------|
| `TTAI_NOTIFICATION_BACKEND` | Backend: `auto`, `tauri`, `webhook`, `none` | `auto` |
| `TTAI_WEBHOOK_URL` | Webhook endpoint URL | None |
| `TTAI_TRANSPORT` | Current transport (used by `auto`) | `stdio` |

### Webhook Payload Format

When using the webhook backend, notifications are POSTed as JSON:

```json
{
  "type": "notification",
  "notification_type": "alert_triggered",
  "title": "Price Alert: AAPL",
  "body": "AAPL is now $185.50 (above $185.00)",
  "data": {
    "symbol": "AAPL",
    "condition": "above",
    "threshold": 185.0,
    "current_price": 185.5
  },
  "timestamp": "2024-01-15T14:30:00.000000"
}
```

Compatible with:
- Custom webhook receivers
- Slack incoming webhooks (with adapter)
- Discord webhooks (with adapter)
- Zapier/IFTTT/n8n

## Task Manager Integration

```python
# src/tasks/manager.py (integration with server startup)
from .monitors.portfolio import PortfolioMonitor
from .monitors.price_alerts import PriceAlertMonitor
from .monitors.position_sync import PositionSyncMonitor
from .scheduled_jobs import setup_scheduled_jobs
from .shutdown import shutdown_handler
from ..services.notifications import configure_notifier

async def start_background_tasks(
    tastytrade: TastyTradeService,
    db: DatabaseService,
    transport: str = "stdio",
    webhook_url: str | None = None
) -> list:
    """Start all background monitoring tasks."""

    # Configure notification backend based on mode
    configure_notifier(
        backend="auto",
        webhook_url=webhook_url,
        transport=transport
    )

    monitors = []

    # Portfolio monitor (60s)
    portfolio = PortfolioMonitor(tastytrade, db)
    await portfolio.start()
    monitors.append(portfolio)

    # Price alerts (30s)
    price_alerts = PriceAlertMonitor(tastytrade, db)
    await price_alerts.start()
    monitors.append(price_alerts)

    # Position sync (5min)
    position_sync = PositionSyncMonitor(tastytrade, db)
    await position_sync.start()
    monitors.append(position_sync)

    # Setup scheduled jobs
    await setup_scheduled_jobs(tastytrade, db)

    # Register cleanup on shutdown
    for monitor in monitors:
        shutdown_handler.register_callback(monitor.stop)

    return monitors
```

## Cross-References

- [MCP Server Design](./01-mcp-server-design.md) - Deployment modes and notification overview
- [Workflow Orchestration](./02-workflow-orchestration.md) - Task management architecture
- [Python Server](./03-python-server.md) - Entry point and configuration
- [Integration Patterns](./09-integration-patterns.md) - Tauri notification handling
- [Data Layer](./05-data-layer.md) - Alert storage
- [Local Development](./10-local-development.md) - Testing with both backends
