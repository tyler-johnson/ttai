# Workflow Orchestration

## Overview

The TTAI system uses Python asyncio for orchestrating long-running operations, background monitoring, and scheduled tasks. This provides durable task execution with graceful shutdown handling, all running locally as part of the MCP server sidecar process.

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                    Python MCP Server (Sidecar)                       │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ┌────────────────────────────────────────────────────────────────┐ │
│  │              Task Manager (asyncio-based)                      │ │
│  │  ┌────────────┐  ┌────────────┐  ┌────────────┐                │ │
│  │  │  Analysis  │  │  Monitor   │  │  Scheduled │                │ │
│  │  │   Tasks    │  │   Tasks    │  │   Tasks    │                │ │
│  │  └─────┬──────┘  └─────┬──────┘  └─────┬──────┘                │ │
│  └────────┼───────────────┼───────────────┼───────────────────────┘ │
│           │               │               │                          │
│           └───────────────┼───────────────┘                          │
│                           ▼                                          │
│  ┌────────────────────────────────────────────────────────────────┐ │
│  │                   Background Task Loops                        │ │
│  │  ┌────────────┐  ┌────────────┐  ┌────────────┐                │ │
│  │  │  Portfolio │  │   Price    │  │  Position  │                │ │
│  │  │  Monitor   │  │  Alerts    │  │   Sync     │                │ │
│  │  │  (60s)     │  │  (30s)     │  │  (5min)    │                │ │
│  │  └────────────┘  └────────────┘  └────────────┘                │ │
│  └────────────────────────────────────────────────────────────────┘ │
│                                                                      │
│  ┌────────────────────────────────────────────────────────────────┐ │
│  │              Scheduler (APScheduler-style)                     │ │
│  │  ┌────────────┐  ┌────────────┐  ┌────────────┐                │ │
│  │  │  Market    │  │  Daily     │  │  Custom    │                │ │
│  │  │  Hours     │  │  Reports   │  │  Intervals │                │ │
│  │  └────────────┘  └────────────┘  └────────────┘                │ │
│  └────────────────────────────────────────────────────────────────┘ │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

## Task Manager

### Core Task Manager Implementation

```python
# src/tasks/manager.py
import asyncio
import logging
from typing import Any, Callable, Coroutine, Dict, Optional
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import traceback

logger = logging.getLogger(__name__)

class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

@dataclass
class TaskInfo:
    """Information about a managed task."""
    id: str
    name: str
    status: TaskStatus
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error: Optional[str] = None
    result: Any = None

@dataclass
class TaskManager:
    """Manages asyncio tasks with tracking and graceful shutdown."""

    _tasks: Dict[str, asyncio.Task] = field(default_factory=dict)
    _task_info: Dict[str, TaskInfo] = field(default_factory=dict)
    _shutdown_event: asyncio.Event = field(default_factory=asyncio.Event)
    _task_counter: int = 0

    async def start_task(
        self,
        coro: Coroutine,
        name: str,
        task_id: Optional[str] = None
    ) -> str:
        """
        Start a new managed task.

        Args:
            coro: The coroutine to run
            name: Human-readable task name
            task_id: Optional custom task ID

        Returns:
            The task ID
        """
        if task_id is None:
            self._task_counter += 1
            task_id = f"task-{self._task_counter}"

        # Create task info
        info = TaskInfo(
            id=task_id,
            name=name,
            status=TaskStatus.PENDING,
            created_at=datetime.now()
        )
        self._task_info[task_id] = info

        # Create and track the task
        task = asyncio.create_task(
            self._run_task(task_id, coro),
            name=name
        )
        self._tasks[task_id] = task

        logger.info(f"Started task {task_id}: {name}")
        return task_id

    async def _run_task(self, task_id: str, coro: Coroutine) -> Any:
        """Run a task with status tracking."""
        info = self._task_info[task_id]
        info.status = TaskStatus.RUNNING
        info.started_at = datetime.now()

        try:
            result = await coro
            info.status = TaskStatus.COMPLETED
            info.result = result
            return result

        except asyncio.CancelledError:
            info.status = TaskStatus.CANCELLED
            raise

        except Exception as e:
            info.status = TaskStatus.FAILED
            info.error = str(e)
            logger.error(f"Task {task_id} failed: {e}")
            logger.error(traceback.format_exc())
            raise

        finally:
            info.completed_at = datetime.now()
            # Clean up completed task
            if task_id in self._tasks:
                del self._tasks[task_id]

    async def cancel_task(self, task_id: str) -> bool:
        """Cancel a running task."""
        if task_id not in self._tasks:
            return False

        task = self._tasks[task_id]
        task.cancel()

        try:
            await task
        except asyncio.CancelledError:
            pass

        logger.info(f"Cancelled task {task_id}")
        return True

    def get_task_status(self, task_id: str) -> Optional[TaskInfo]:
        """Get the status of a task."""
        return self._task_info.get(task_id)

    def get_all_tasks(self) -> Dict[str, TaskInfo]:
        """Get all task info."""
        return self._task_info.copy()

    def get_running_tasks(self) -> Dict[str, TaskInfo]:
        """Get all currently running tasks."""
        return {
            k: v for k, v in self._task_info.items()
            if v.status == TaskStatus.RUNNING
        }

    async def wait_for_task(self, task_id: str, timeout: float = None) -> Any:
        """Wait for a task to complete."""
        if task_id not in self._tasks:
            info = self._task_info.get(task_id)
            if info and info.status == TaskStatus.COMPLETED:
                return info.result
            elif info and info.status == TaskStatus.FAILED:
                raise RuntimeError(info.error)
            return None

        task = self._tasks[task_id]
        return await asyncio.wait_for(task, timeout=timeout)

    async def shutdown(self, timeout: float = 30.0) -> None:
        """
        Gracefully shutdown all tasks.

        Args:
            timeout: Maximum time to wait for tasks to complete
        """
        self._shutdown_event.set()

        if not self._tasks:
            return

        logger.info(f"Shutting down {len(self._tasks)} tasks...")

        # Cancel all running tasks
        for task_id, task in list(self._tasks.items()):
            task.cancel()

        # Wait for all tasks to complete
        if self._tasks:
            done, pending = await asyncio.wait(
                self._tasks.values(),
                timeout=timeout,
                return_when=asyncio.ALL_COMPLETED
            )

            # Force cancel any remaining tasks
            for task in pending:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        logger.info("All tasks shutdown complete")

    @property
    def is_shutting_down(self) -> bool:
        """Check if shutdown has been initiated."""
        return self._shutdown_event.is_set()


# Global task manager instance
task_manager = TaskManager()
```

### Analysis Workflow

```python
# src/tasks/workflows.py
import asyncio
from dataclasses import dataclass
from typing import Optional, Dict, Any
from datetime import datetime

from ..agents.chart_analyst import ChartAnalyst
from ..agents.options_analyst import OptionsAnalyst
from ..agents.research_analyst import ResearchAnalyst
from ..services.database import DatabaseService
from ..services.tastytrade import TastyTradeService
from ..services.cache import CacheService
from ..server.notifications import NotificationEmitter

@dataclass
class AnalysisResult:
    """Result of a full analysis workflow."""
    symbol: str
    chart_analysis: Dict[str, Any]
    options_analysis: Optional[Dict[str, Any]]
    research_analysis: Optional[Dict[str, Any]]
    recommendation: str
    completed_at: datetime

class AnalysisWorkflow:
    """Orchestrates multi-step analysis workflows."""

    def __init__(
        self,
        tastytrade: TastyTradeService,
        cache: CacheService,
        db: DatabaseService
    ):
        self.tastytrade = tastytrade
        self.cache = cache
        self.db = db

    async def run_full_analysis(
        self,
        symbol: str,
        strategy: str = "csp",
        notify: bool = True
    ) -> AnalysisResult:
        """
        Run comprehensive analysis pipeline.

        Steps:
        1. Chart analysis (technical)
        2. Options analysis (if chart passes)
        3. Research analysis (fundamentals)
        4. Synthesize recommendation
        5. Save results
        6. Notify user
        """
        # Step 1: Chart analysis
        chart_analyst = ChartAnalyst(self.tastytrade, self.cache)
        chart_result = await chart_analyst.analyze(symbol)

        # Early exit if chart analysis rejects
        if chart_result.get("recommendation") == "reject":
            result = AnalysisResult(
                symbol=symbol,
                chart_analysis=chart_result,
                options_analysis=None,
                research_analysis=None,
                recommendation="reject",
                completed_at=datetime.now()
            )

            await self._save_result(symbol, "full", result)
            return result

        # Step 2: Options analysis
        options_analyst = OptionsAnalyst(self.tastytrade, self.cache)
        options_result = await options_analyst.analyze(
            symbol,
            strategy=strategy,
            chart_context=chart_result
        )

        # Step 3: Research analysis
        research_analyst = ResearchAnalyst(self.tastytrade, self.cache)
        research_result = await research_analyst.analyze(symbol)

        # Step 4: Synthesize recommendation
        recommendation = self._synthesize(
            chart_result,
            options_result,
            research_result
        )

        result = AnalysisResult(
            symbol=symbol,
            chart_analysis=chart_result,
            options_analysis=options_result,
            research_analysis=research_result,
            recommendation=recommendation,
            completed_at=datetime.now()
        )

        # Step 5: Save results
        await self._save_result(symbol, "full", result)

        # Step 6: Notify user
        if notify:
            NotificationEmitter.analysis_complete(symbol, recommendation)

        return result

    def _synthesize(
        self,
        chart: Dict[str, Any],
        options: Optional[Dict[str, Any]],
        research: Optional[Dict[str, Any]]
    ) -> str:
        """Synthesize results into final recommendation."""
        # Simple scoring logic
        score = 0

        # Chart score
        chart_rec = chart.get("recommendation", "neutral")
        if chart_rec == "bullish":
            score += 2
        elif chart_rec == "neutral":
            score += 1

        # Options score
        if options:
            options_rec = options.get("recommendation", "neutral")
            if options_rec == "select":
                score += 2
            elif options_rec == "watchlist":
                score += 1

        # Research score
        if research:
            sentiment = research.get("sentiment", "neutral")
            if sentiment == "positive":
                score += 1
            elif sentiment == "negative":
                score -= 1

        # Determine recommendation
        if score >= 4:
            return "strong_select"
        elif score >= 2:
            return "select"
        elif score >= 0:
            return "watchlist"
        else:
            return "reject"

    async def _save_result(
        self,
        symbol: str,
        analysis_type: str,
        result: AnalysisResult
    ) -> None:
        """Save analysis result to database."""
        await self.db.save_analysis(
            symbol=symbol,
            analysis_type=analysis_type,
            result={
                "chart_analysis": result.chart_analysis,
                "options_analysis": result.options_analysis,
                "research_analysis": result.research_analysis,
                "recommendation": result.recommendation,
                "completed_at": result.completed_at.isoformat()
            }
        )


class ScreenerWorkflow:
    """Screens multiple symbols and ranks by criteria."""

    def __init__(
        self,
        tastytrade: TastyTradeService,
        cache: CacheService,
        db: DatabaseService
    ):
        self.tastytrade = tastytrade
        self.cache = cache
        self.db = db

    async def run_screener(
        self,
        symbols: list[str],
        strategy: str = "csp",
        max_concurrent: int = 5
    ) -> list[Dict[str, Any]]:
        """
        Screen multiple symbols concurrently.

        Args:
            symbols: List of symbols to screen
            strategy: Strategy to analyze for
            max_concurrent: Maximum concurrent analyses

        Returns:
            Ranked list of results
        """
        semaphore = asyncio.Semaphore(max_concurrent)
        results = []

        async def analyze_symbol(symbol: str) -> Optional[Dict[str, Any]]:
            async with semaphore:
                try:
                    workflow = AnalysisWorkflow(
                        self.tastytrade,
                        self.cache,
                        self.db
                    )
                    result = await workflow.run_full_analysis(
                        symbol,
                        strategy=strategy,
                        notify=False  # Don't notify for screener
                    )
                    return {
                        "symbol": symbol,
                        "recommendation": result.recommendation,
                        "chart_score": result.chart_analysis.get("score", 0),
                        "options_data": result.options_analysis
                    }
                except Exception as e:
                    logger.warning(f"Failed to analyze {symbol}: {e}")
                    return None

        # Run all analyses concurrently
        tasks = [analyze_symbol(s) for s in symbols]
        all_results = await asyncio.gather(*tasks)

        # Filter and rank results
        valid_results = [r for r in all_results if r is not None]
        ranked = sorted(
            valid_results,
            key=lambda x: self._score_result(x),
            reverse=True
        )

        return ranked[:10]  # Top 10 results

    def _score_result(self, result: Dict[str, Any]) -> float:
        """Score a result for ranking."""
        score = 0.0

        rec_scores = {
            "strong_select": 4,
            "select": 3,
            "watchlist": 1,
            "reject": 0
        }
        score += rec_scores.get(result["recommendation"], 0)
        score += result.get("chart_score", 0) / 10

        return score
```

## Background Task Loops

### Monitor Loop Base Class

```python
# src/tasks/loops.py
import asyncio
import logging
from abc import ABC, abstractmethod
from typing import Any

from .manager import task_manager

logger = logging.getLogger(__name__)

class BackgroundLoop(ABC):
    """Base class for background monitoring loops."""

    def __init__(self, interval_seconds: float, name: str):
        self.interval = interval_seconds
        self.name = name
        self._running = False
        self._task_id: str | None = None

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
        return self._task_id

    async def stop(self) -> None:
        """Stop the background loop."""
        self._running = False
        if self._task_id:
            await task_manager.cancel_task(self._task_id)
            self._task_id = None

    async def _loop(self) -> None:
        """Main loop implementation."""
        logger.info(f"Starting {self.name} loop (interval: {self.interval}s)")

        while self._running and not task_manager.is_shutting_down:
            try:
                await self.execute()
            except Exception as e:
                logger.error(f"{self.name} loop error: {e}")

            # Wait for next interval or shutdown
            try:
                await asyncio.wait_for(
                    asyncio.sleep(self.interval),
                    timeout=self.interval
                )
            except asyncio.CancelledError:
                break

        logger.info(f"Stopped {self.name} loop")

    @abstractmethod
    async def execute(self) -> None:
        """Execute one iteration of the loop."""
        pass

    @property
    def is_running(self) -> bool:
        return self._running
```

### Portfolio Monitor Loop

```python
# src/tasks/monitors/portfolio.py
from ..loops import BackgroundLoop
from ...services.tastytrade import TastyTradeService
from ...services.database import DatabaseService
from ...server.notifications import NotificationEmitter
import logging

logger = logging.getLogger(__name__)

class PortfolioMonitor(BackgroundLoop):
    """Monitors portfolio positions for alerts."""

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
        """Check positions and alert rules."""
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

        # Get current quotes for all position symbols
        symbols = list(set(p["symbol"] for p in positions))
        quotes = await self.tastytrade.get_quotes(symbols)

        # Check each alert rule
        for alert in alerts:
            symbol = alert["symbol"]
            quote = quotes.get(symbol)
            if not quote:
                continue

            triggered = self._check_alert(alert, quote, positions)
            if triggered:
                await self._handle_triggered_alert(alert, quote)

    def _check_alert(
        self,
        alert: dict,
        quote: dict,
        positions: list[dict]
    ) -> bool:
        """Check if an alert condition is met."""
        current_price = quote.get("last", quote.get("mark", 0))
        alert_type = alert["alert_type"]
        condition = alert["condition"]
        threshold = alert["threshold"]

        if alert_type == "price":
            if condition == "above" and current_price >= threshold:
                return True
            if condition == "below" and current_price <= threshold:
                return True

        elif alert_type == "delta":
            # Find matching position
            for pos in positions:
                if pos["symbol"] == alert["symbol"]:
                    delta = abs(pos.get("delta", 0))
                    if delta >= threshold:
                        return True

        elif alert_type == "dte":
            # Days to expiration warning
            for pos in positions:
                if pos["symbol"] == alert["symbol"]:
                    dte = pos.get("dte", 999)
                    if dte <= threshold:
                        return True

        return False

    async def _handle_triggered_alert(
        self,
        alert: dict,
        quote: dict
    ) -> None:
        """Handle a triggered alert."""
        current_price = quote.get("last", quote.get("mark", 0))

        # Mark alert as triggered
        await self.db.trigger_alert(alert["id"])

        # Send notification
        NotificationEmitter.alert_triggered(
            symbol=alert["symbol"],
            condition=alert["condition"],
            threshold=alert["threshold"],
            current_price=current_price
        )

        logger.info(
            f"Alert triggered: {alert['symbol']} "
            f"{alert['condition']} ${alert['threshold']}"
        )
```

### Price Alert Loop

```python
# src/tasks/monitors/price_alerts.py
from ..loops import BackgroundLoop
from ...services.tastytrade import TastyTradeService
from ...services.database import DatabaseService
from ...server.notifications import NotificationEmitter
import logging

logger = logging.getLogger(__name__)

class PriceAlertMonitor(BackgroundLoop):
    """Monitors price alerts with fast polling."""

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
        alerts = await self.db.get_price_alerts()
        if not alerts:
            return

        # Group alerts by symbol for efficient quote fetching
        symbols = list(set(a["symbol"] for a in alerts))
        quotes = await self.tastytrade.get_quotes(symbols)

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
                NotificationEmitter.alert_triggered(
                    symbol=symbol,
                    condition=alert["condition"],
                    threshold=alert["threshold"],
                    current_price=current_price
                )
```

### Position Sync Loop

```python
# src/tasks/monitors/position_sync.py
from ..loops import BackgroundLoop
from ...services.tastytrade import TastyTradeService
from ...services.database import DatabaseService
import logging

logger = logging.getLogger(__name__)

class PositionSyncMonitor(BackgroundLoop):
    """Syncs positions from TastyTrade to local database."""

    def __init__(
        self,
        tastytrade: TastyTradeService,
        db: DatabaseService,
        interval_seconds: float = 300.0  # 5 minutes
    ):
        super().__init__(interval_seconds, "Position Sync")
        self.tastytrade = tastytrade
        self.db = db

    async def execute(self) -> None:
        """Sync positions from TastyTrade."""
        try:
            # Fetch positions from TastyTrade
            positions = await self.tastytrade.get_positions()

            # Sync to local database
            await self.db.sync_positions(positions)

            logger.debug(f"Synced {len(positions)} positions")

        except Exception as e:
            logger.error(f"Position sync failed: {e}")
```

## Scheduler

### APScheduler-Style Scheduling

```python
# src/tasks/scheduler.py
import asyncio
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from typing import Callable, Coroutine, Optional, List
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
    """Schedules jobs to run at specific times."""

    def __init__(self):
        self._jobs: dict[str, ScheduledJob] = {}
        self._running = False
        self._task_id: str | None = None

    def add_job(
        self,
        job_id: str,
        name: str,
        func: Callable[[], Coroutine],
        schedule_time: time,
        days: List[DayOfWeek] = None
    ) -> None:
        """
        Add a scheduled job.

        Args:
            job_id: Unique job identifier
            name: Human-readable job name
            func: Async function to execute
            schedule_time: Time of day to run (local time)
            days: Days of week to run (default: weekdays)
        """
        if days is None:
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

        logger.info(f"Scheduled job '{name}' at {schedule_time} on {[d.name for d in days]}")

    def remove_job(self, job_id: str) -> bool:
        """Remove a scheduled job."""
        if job_id in self._jobs:
            del self._jobs[job_id]
            return True
        return False

    async def start(self) -> None:
        """Start the scheduler."""
        if self._running:
            return

        self._running = True
        self._task_id = await task_manager.start_task(
            self._scheduler_loop(),
            name="Scheduler",
            task_id="scheduler"
        )

    async def stop(self) -> None:
        """Stop the scheduler."""
        self._running = False
        if self._task_id:
            await task_manager.cancel_task(self._task_id)
            self._task_id = None

    async def _scheduler_loop(self) -> None:
        """Main scheduler loop."""
        logger.info("Scheduler started")

        while self._running and not task_manager.is_shutting_down:
            now = datetime.now()

            for job in self._jobs.values():
                if not job.enabled or job.next_run is None:
                    continue

                if now >= job.next_run:
                    # Run the job
                    await self._run_job(job)

                    # Calculate next run
                    job.last_run = now
                    job.next_run = self._calculate_next_run(job)

            # Check every minute
            await asyncio.sleep(60)

        logger.info("Scheduler stopped")

    async def _run_job(self, job: ScheduledJob) -> None:
        """Execute a scheduled job."""
        logger.info(f"Running scheduled job: {job.name}")

        try:
            await job.func()
        except Exception as e:
            logger.error(f"Scheduled job '{job.name}' failed: {e}")

    def _calculate_next_run(self, job: ScheduledJob) -> Optional[datetime]:
        """Calculate the next run time for a job."""
        now = datetime.now()
        today = now.date()

        # Check if we can run today
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

    def get_jobs(self) -> List[ScheduledJob]:
        """Get all scheduled jobs."""
        return list(self._jobs.values())


# Global scheduler instance
scheduler = Scheduler()
```

### Scheduled Job Examples

```python
# src/tasks/scheduled_jobs.py
from datetime import time

from .scheduler import scheduler, DayOfWeek
from ..services.tastytrade import TastyTradeService
from ..services.database import DatabaseService
from ..server.notifications import NotificationEmitter

async def setup_scheduled_jobs(
    tastytrade: TastyTradeService,
    db: DatabaseService
) -> None:
    """Configure all scheduled jobs."""

    # Morning briefing (9:30 AM ET on weekdays)
    async def morning_briefing():
        positions = await tastytrade.get_positions()
        if positions:
            NotificationEmitter.emit(
                NotificationEmitter.NotificationType.INFO,
                "Morning Briefing",
                f"You have {len(positions)} open positions",
                {"positions": len(positions)}
            )

    scheduler.add_job(
        job_id="morning_briefing",
        name="Morning Briefing",
        func=morning_briefing,
        schedule_time=time(9, 30),  # 9:30 AM
        days=[
            DayOfWeek.MONDAY,
            DayOfWeek.TUESDAY,
            DayOfWeek.WEDNESDAY,
            DayOfWeek.THURSDAY,
            DayOfWeek.FRIDAY
        ]
    )

    # End of day summary (4:00 PM ET on weekdays)
    async def eod_summary():
        positions = await tastytrade.get_positions()
        balances = await tastytrade.get_balances()

        # Calculate daily P&L
        daily_pnl = balances.get("day_pnl", 0)

        NotificationEmitter.emit(
            NotificationEmitter.NotificationType.INFO,
            "End of Day Summary",
            f"Daily P&L: ${daily_pnl:,.2f}",
            {"daily_pnl": daily_pnl, "positions": len(positions)}
        )

    scheduler.add_job(
        job_id="eod_summary",
        name="End of Day Summary",
        func=eod_summary,
        schedule_time=time(16, 0),  # 4:00 PM
        days=[
            DayOfWeek.MONDAY,
            DayOfWeek.TUESDAY,
            DayOfWeek.WEDNESDAY,
            DayOfWeek.THURSDAY,
            DayOfWeek.FRIDAY
        ]
    )

    # Weekly review (Friday 5:00 PM)
    async def weekly_review():
        # Generate weekly performance summary
        analyses = await db.get_recent_analyses(limit=50)
        NotificationEmitter.emit(
            NotificationEmitter.NotificationType.INFO,
            "Weekly Review",
            f"Completed {len(analyses)} analyses this week",
            {"analyses_count": len(analyses)}
        )

    scheduler.add_job(
        job_id="weekly_review",
        name="Weekly Review",
        func=weekly_review,
        schedule_time=time(17, 0),  # 5:00 PM
        days=[DayOfWeek.FRIDAY]
    )

    # Start the scheduler
    await scheduler.start()
```

## Graceful Shutdown

### Shutdown Handler

```python
# src/tasks/shutdown.py
import asyncio
import signal
import logging
from typing import Callable, List

from .manager import task_manager
from .scheduler import scheduler

logger = logging.getLogger(__name__)

class ShutdownHandler:
    """Handles graceful shutdown of all background tasks."""

    def __init__(self):
        self._shutdown_callbacks: List[Callable] = []
        self._is_shutting_down = False

    def register_callback(self, callback: Callable) -> None:
        """Register a callback to run during shutdown."""
        self._shutdown_callbacks.append(callback)

    async def shutdown(self) -> None:
        """Execute graceful shutdown."""
        if self._is_shutting_down:
            return

        self._is_shutting_down = True
        logger.info("Initiating graceful shutdown...")

        # Stop scheduler first
        await scheduler.stop()

        # Run registered callbacks
        for callback in self._shutdown_callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback()
                else:
                    callback()
            except Exception as e:
                logger.error(f"Shutdown callback error: {e}")

        # Shutdown task manager (cancels all running tasks)
        await task_manager.shutdown(timeout=30.0)

        logger.info("Graceful shutdown complete")

    def setup_signal_handlers(self, loop: asyncio.AbstractEventLoop) -> None:
        """Setup OS signal handlers for graceful shutdown."""
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(
                sig,
                lambda: asyncio.create_task(self.shutdown())
            )


# Global shutdown handler
shutdown_handler = ShutdownHandler()
```

### Integration with Main Server

```python
# src/server/main.py
import asyncio
from mcp.server import Server
from mcp.server.stdio import stdio_server

from ..tasks.manager import task_manager
from ..tasks.scheduler import scheduler
from ..tasks.shutdown import shutdown_handler
from ..tasks.monitors.portfolio import PortfolioMonitor
from ..tasks.monitors.price_alerts import PriceAlertMonitor
from ..tasks.monitors.position_sync import PositionSyncMonitor
from ..tasks.scheduled_jobs import setup_scheduled_jobs

async def main():
    """Main entry point with background task management."""
    # Initialize services
    db = await DatabaseService.create()
    cache = CacheService()
    tastytrade = TastyTradeService(db, cache)

    # Create MCP server
    server = Server("ttai-mcp-server")
    register_tools(server, db, tastytrade, cache)
    register_resources(server, db, tastytrade)
    register_prompts(server)

    # Start background monitors
    portfolio_monitor = PortfolioMonitor(tastytrade, db)
    price_alerts = PriceAlertMonitor(tastytrade, db)
    position_sync = PositionSyncMonitor(tastytrade, db)

    await portfolio_monitor.start()
    await price_alerts.start()
    await position_sync.start()

    # Setup scheduled jobs
    await setup_scheduled_jobs(tastytrade, db)

    # Register cleanup callbacks
    shutdown_handler.register_callback(portfolio_monitor.stop)
    shutdown_handler.register_callback(price_alerts.stop)
    shutdown_handler.register_callback(position_sync.stop)
    shutdown_handler.register_callback(db.close)

    # Setup signal handlers
    loop = asyncio.get_event_loop()
    shutdown_handler.setup_signal_handlers(loop)

    try:
        # Run MCP server with stdio transport
        async with stdio_server() as (read_stream, write_stream):
            await server.run(
                read_stream,
                write_stream,
                server.create_initialization_options()
            )
    finally:
        # Ensure clean shutdown
        await shutdown_handler.shutdown()

if __name__ == "__main__":
    asyncio.run(main())
```

## Cross-References

- [MCP Server Design](./01-mcp-server-design.md) - Server integration
- [Python Server](./03-python-server.md) - Project structure
- [Background Tasks](./06-background-tasks.md) - Detailed monitor implementations
- [Integration Patterns](./09-integration-patterns.md) - Notification flow to Tauri
