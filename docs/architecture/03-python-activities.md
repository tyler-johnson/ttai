# Python Activity Implementation

## Overview

Python activities are the workhorses of the TastyTrade AI system. They handle all data fetching, AI agent execution, and external service integrations. This document covers the project structure, key integrations, and implementation patterns.

## Project Structure

```
workers/
├── pyproject.toml           # Python project configuration (uv/pip)
├── Dockerfile               # Worker container image
├── worker.py                # Main worker entry point
│
├── activities/              # Temporal activities
│   ├── __init__.py
│   ├── chart.py             # Chart analysis activities
│   ├── options.py           # Options analysis activities
│   ├── research.py          # Research analysis activities
│   ├── screener.py          # Screener activities
│   ├── market_data.py       # Data fetching activities
│   ├── alerts.py            # Alert routing activities
│   ├── portfolio.py         # Portfolio activities
│   └── storage.py           # Database activities
│
├── agents/                  # AI agents
│   ├── __init__.py
│   ├── agentic_loop.py      # Shared agentic loop implementation
│   ├── chart_analyst.py     # Chart analysis agent
│   ├── options_analyst.py   # Options analysis agent
│   ├── research_analyst.py  # Research analysis agent
│   └── orchestrator.py      # Multi-agent orchestrator
│
├── tools/                   # Agent tools
│   ├── __init__.py
│   ├── chart_tools.py       # Technical analysis tools
│   ├── options_tools.py     # Options analysis tools
│   ├── research_tools.py    # Research/news tools
│   └── market_tools.py      # Market data tools
│
├── services/                # External service clients
│   ├── __init__.py
│   ├── tastytrade.py        # TastyTrade API client
│   ├── yahoo.py             # Yahoo Finance fallback
│   ├── tradingview.py       # TradingView screener
│   ├── news.py              # News aggregation
│   └── notifications.py     # Notification routing
│
├── models/                  # Data models
│   ├── __init__.py
│   ├── market.py            # Market data models
│   ├── options.py           # Options models
│   ├── analysis.py          # Analysis result models
│   └── alerts.py            # Alert models
│
├── db/                      # Database access
│   ├── __init__.py
│   ├── postgres.py          # PostgreSQL client
│   ├── redis.py             # Redis client
│   └── migrations/          # Alembic migrations
│
└── config/                  # Configuration
    ├── __init__.py
    └── settings.py          # Environment settings
```

## Dependencies

```toml
# pyproject.toml
[project]
name = "ttai-workers"
version = "0.1.0"
requires-python = ">=3.11"

dependencies = [
    # Temporal
    "temporalio>=1.7.0",

    # TastyTrade
    "tastytrade>=8.0",

    # AI (LiteLLM for provider-agnostic LLM access)
    "litellm>=1.40.0",

    # Data sources
    "yfinance>=0.2.40",
    "pandas>=2.0",
    "numpy>=1.24",

    # Database
    "asyncpg>=0.29.0",
    "redis>=5.0",
    "alembic>=1.13.0",
    "sqlalchemy>=2.0",
    "pgvector>=0.2.0",

    # HTTP
    "httpx>=0.27.0",
    "aiohttp>=3.9.0",

    # Utilities
    "pydantic>=2.0",
    "python-dotenv>=1.0.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23.0",
    "ruff>=0.5.0",
    "mypy>=1.11.0",
]
```

## TastyTrade Integration

### Session Management

Porting from `csp_tastytrade.py` - OAuth-based session management:

```python
# services/tastytrade.py
import os
from typing import Optional
from tastytrade import Session as TTSession

class TastyTradeClient:
    """Singleton TastyTrade client with session management."""

    _instance: Optional["TastyTradeClient"] = None
    _session: Optional[TTSession] = None

    @classmethod
    async def get_instance(cls) -> "TastyTradeClient":
        """Get or create the singleton instance."""
        if cls._instance is None:
            cls._instance = cls()
            await cls._instance._initialize()
        return cls._instance

    async def _initialize(self) -> None:
        """Initialize the TastyTrade session."""
        client_secret = os.environ.get("TT_CLIENT_SECRET")
        refresh_token = os.environ.get("TT_REFRESH_TOKEN")

        if not client_secret or not refresh_token:
            raise ValueError("TT_CLIENT_SECRET and TT_REFRESH_TOKEN required")

        try:
            self._session = TTSession(client_secret, refresh_token)
        except Exception as e:
            raise ConnectionError(f"Failed to create TastyTrade session: {e}")

    @property
    def session(self) -> TTSession:
        """Get the active session."""
        if self._session is None:
            raise RuntimeError("TastyTrade client not initialized")
        return self._session

    async def refresh_session(self) -> None:
        """Refresh the session if needed."""
        # TastyTrade SDK handles refresh automatically via OAuth
        # This method is here for explicit refresh if needed
        await self._initialize()
```

### Option Chain Fetching

Using `NestedOptionChain` from TastyTrade SDK:

```python
# services/tastytrade.py (continued)
from tastytrade.instruments import NestedOptionChain
from tastytrade.metrics import get_market_metrics, MarketMetricInfo
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Any

class TastyTradeClient:
    # ... (previous code)

    async def get_option_chain(
        self,
        symbol: str,
        expiration: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Fetch option chain for a symbol.

        Args:
            symbol: Stock ticker symbol
            expiration: Optional specific expiration date (YYYY-MM-DD)

        Returns:
            Nested option chain data
        """
        chains = NestedOptionChain.get(self.session, symbol)

        if not chains or not chains[0].expirations:
            return {"symbol": symbol, "expirations": []}

        chain = chains[0]
        result = {
            "symbol": symbol,
            "underlying_price": None,  # Filled by quote fetch
            "expirations": [],
        }

        for exp in chain.expirations:
            exp_date = str(exp.expiration_date)

            # Filter by expiration if specified
            if expiration and exp_date != expiration:
                continue

            exp_data = {
                "date": exp_date,
                "dte": self._calculate_dte(exp.expiration_date),
                "strikes": [],
            }

            for strike_info in exp.strikes:
                strike_data = {
                    "strike": float(strike_info.strike_price),
                    "call_symbol": strike_info.call_streamer_symbol,
                    "put_symbol": strike_info.put_streamer_symbol,
                }
                exp_data["strikes"].append(strike_data)

            result["expirations"].append(exp_data)

        return result

    async def get_option_chains_batch(
        self,
        symbols: List[str],
        max_workers: int = 10,
    ) -> Dict[str, Any]:
        """
        Fetch option chains for multiple symbols in parallel.

        Uses ThreadPoolExecutor since TastyTrade SDK is synchronous.
        """
        results = {}

        def fetch_single(symbol: str) -> tuple[str, Any]:
            try:
                chains = NestedOptionChain.get(self.session, symbol)
                if chains and chains[0].expirations:
                    return symbol, chains[0]
            except Exception:
                pass
            return symbol, None

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(fetch_single, sym): sym
                for sym in symbols
            }

            for future in as_completed(futures):
                symbol, chain = future.result()
                if chain:
                    results[symbol] = chain

        return results

    def _calculate_dte(self, exp_date) -> int:
        """Calculate days to expiration."""
        from datetime import datetime

        if isinstance(exp_date, str):
            exp_date = datetime.strptime(exp_date, "%Y-%m-%d").date()

        today = datetime.now().date()
        return (exp_date - today).days
```

### DXLink Streaming

Real-time data streaming for quotes and Greeks:

```python
# services/tastytrade.py (continued)
import asyncio
from tastytrade import DXLinkStreamer
from tastytrade.dxfeed import Quote, Greeks, Trade, Summary
from typing import Set

class TastyTradeClient:
    # ... (previous code)

    async def stream_option_data(
        self,
        option_symbols: List[str],
        timeout: float = 60.0,
        idle_timeout: float = 2.0,
    ) -> Dict[str, Dict[str, Any]]:
        """
        Stream quotes, Greeks, and summary for option symbols.

        Uses a single WebSocket connection with multiple subscriptions.
        Exits when idle_timeout passes with no new data.

        Args:
            option_symbols: List of option streamer symbols
            timeout: Maximum total timeout
            idle_timeout: Exit if no new data for this duration

        Returns:
            Dict mapping symbol to {'quote': Quote, 'greeks': Greeks, ...}
        """
        if not option_symbols:
            return {}

        results: Dict[str, Dict] = {sym: {} for sym in option_symbols}
        symbol_set = set(option_symbols)
        done_event = asyncio.Event()
        start_time = asyncio.get_event_loop().time()
        last_data_time = start_time

        def touch():
            nonlocal last_data_time
            last_data_time = asyncio.get_event_loop().time()

        async def listen_quotes(streamer: DXLinkStreamer):
            while not done_event.is_set():
                try:
                    quote = await asyncio.wait_for(
                        streamer.get_event(Quote), timeout=0.5
                    )
                    if quote.event_symbol in symbol_set:
                        results[quote.event_symbol]["quote"] = quote
                        touch()
                except asyncio.TimeoutError:
                    pass

        async def listen_greeks(streamer: DXLinkStreamer):
            while not done_event.is_set():
                try:
                    greek = await asyncio.wait_for(
                        streamer.get_event(Greeks), timeout=0.5
                    )
                    if greek.event_symbol in symbol_set:
                        results[greek.event_symbol]["greeks"] = greek
                        touch()
                except asyncio.TimeoutError:
                    pass

        async def listen_summaries(streamer: DXLinkStreamer):
            while not done_event.is_set():
                try:
                    summary = await asyncio.wait_for(
                        streamer.get_event(Summary), timeout=0.5
                    )
                    if summary.event_symbol in symbol_set:
                        results[summary.event_symbol]["summary"] = summary
                        touch()
                except asyncio.TimeoutError:
                    pass

        async def listen_trades(streamer: DXLinkStreamer):
            while not done_event.is_set():
                try:
                    trade = await asyncio.wait_for(
                        streamer.get_event(Trade), timeout=0.5
                    )
                    if trade.event_symbol in symbol_set:
                        results[trade.event_symbol]["trade"] = trade
                        touch()
                except asyncio.TimeoutError:
                    pass

        async def monitor():
            """Monitor for idle timeout."""
            while not done_event.is_set():
                await asyncio.sleep(0.25)
                now = asyncio.get_event_loop().time()

                # Check idle timeout
                if now - last_data_time >= idle_timeout:
                    done_event.set()
                    break

                # Check total timeout
                if now - start_time >= timeout:
                    done_event.set()
                    break

        try:
            async with DXLinkStreamer(self.session) as streamer:
                # Subscribe to all event types
                await streamer.subscribe(Quote, option_symbols)
                await streamer.subscribe(Greeks, option_symbols)
                await streamer.subscribe(Summary, option_symbols)
                await streamer.subscribe(Trade, option_symbols)

                # Run listeners concurrently
                tasks = [
                    asyncio.create_task(listen_quotes(streamer)),
                    asyncio.create_task(listen_greeks(streamer)),
                    asyncio.create_task(listen_summaries(streamer)),
                    asyncio.create_task(listen_trades(streamer)),
                    asyncio.create_task(monitor()),
                ]

                await done_event.wait()

                # Cancel all tasks
                for task in tasks:
                    task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)

        except Exception as e:
            print(f"Warning: Error in WebSocket streaming: {e}")

        return results
```

### Market Metrics Batch Queries

```python
# services/tastytrade.py (continued)
from tastytrade.metrics import get_market_metrics, MarketMetricInfo, EarningsReport

class TastyTradeClient:
    # ... (previous code)

    async def get_market_metrics(
        self,
        symbols: List[str],
    ) -> Dict[str, MarketMetricInfo]:
        """
        Batch fetch market metrics for symbols.

        Includes:
        - Historical volatility (HV 30-day)
        - IV index rank
        - Earnings information
        - Liquidity rating
        """
        try:
            metrics = get_market_metrics(self.session, symbols)
            return {m.symbol: m for m in metrics}
        except Exception as e:
            print(f"Warning: Failed to fetch market metrics: {e}")
            return {}

    def get_days_to_earnings(
        self,
        earnings: Optional[EarningsReport],
    ) -> Optional[int]:
        """Extract days until next earnings from EarningsReport."""
        from datetime import datetime

        if not earnings or not earnings.expected_report_date:
            return None

        today = datetime.now().date()
        return (earnings.expected_report_date - today).days

    async def get_quotes(
        self,
        symbols: List[str],
    ) -> Dict[str, Dict[str, Any]]:
        """
        Fetch current quotes for symbols.

        Uses DXLink streaming for real-time data.
        """
        results = {}

        async with DXLinkStreamer(self.session) as streamer:
            await streamer.subscribe(Quote, symbols)

            received = set()
            timeout = 5.0
            start = asyncio.get_event_loop().time()

            while len(received) < len(symbols):
                if asyncio.get_event_loop().time() - start > timeout:
                    break

                try:
                    quote = await asyncio.wait_for(
                        streamer.get_event(Quote), timeout=0.5
                    )
                    if quote.event_symbol in symbols:
                        results[quote.event_symbol] = {
                            "symbol": quote.event_symbol,
                            "price": float(quote.bid_price + quote.ask_price) / 2
                                if quote.bid_price and quote.ask_price else None,
                            "bid": float(quote.bid_price) if quote.bid_price else None,
                            "ask": float(quote.ask_price) if quote.ask_price else None,
                        }
                        received.add(quote.event_symbol)
                except asyncio.TimeoutError:
                    pass

        return results
```

## Data Source Activities

### Yahoo Finance Fallback

```python
# services/yahoo.py
import yfinance as yf
import pandas as pd
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta

class YahooFinanceClient:
    """Yahoo Finance client for fallback data."""

    async def get_price_history(
        self,
        symbol: str,
        period: str = "6mo",
        interval: str = "1d",
    ) -> Dict[str, Any]:
        """
        Fetch historical price data.

        Args:
            symbol: Stock ticker
            period: Time period (1d, 5d, 1mo, 3mo, 6mo, 1y, 2y, 5y)
            interval: Bar interval (1m, 5m, 15m, 1h, 1d, 1wk, 1mo)

        Returns:
            OHLCV data with timestamps
        """
        ticker = yf.Ticker(symbol)
        df = ticker.history(period=period, interval=interval)

        if df.empty:
            return {"symbol": symbol, "bars": []}

        bars = []
        for idx, row in df.iterrows():
            bars.append({
                "timestamp": idx.isoformat(),
                "open": float(row["Open"]),
                "high": float(row["High"]),
                "low": float(row["Low"]),
                "close": float(row["Close"]),
                "volume": int(row["Volume"]),
            })

        return {"symbol": symbol, "bars": bars}

    async def get_quote(self, symbol: str) -> Dict[str, Any]:
        """Fetch current quote."""
        ticker = yf.Ticker(symbol)
        info = ticker.info

        return {
            "symbol": symbol,
            "price": info.get("currentPrice") or info.get("regularMarketPrice"),
            "bid": info.get("bid"),
            "ask": info.get("ask"),
            "volume": info.get("volume"),
            "avg_volume": info.get("averageVolume"),
            "market_cap": info.get("marketCap"),
            "pe_ratio": info.get("trailingPE"),
            "fifty_two_week_high": info.get("fiftyTwoWeekHigh"),
            "fifty_two_week_low": info.get("fiftyTwoWeekLow"),
        }

    async def get_batch_quotes(
        self,
        symbols: List[str],
    ) -> Dict[str, Dict[str, Any]]:
        """Batch fetch current prices."""
        try:
            df = yf.download(
                symbols,
                period="1d",
                group_by="ticker",
                progress=False,
                threads=True,
            )

            results = {}
            for symbol in symbols:
                try:
                    if len(symbols) == 1:
                        price = float(df["Close"].iloc[-1])
                    else:
                        price = float(df[symbol]["Close"].iloc[-1])

                    results[symbol] = {"symbol": symbol, "price": price}
                except Exception:
                    pass

            return results

        except Exception as e:
            print(f"Warning: Batch quote fetch failed: {e}")
            return {}

    def calculate_historical_volatility(
        self,
        symbol: str,
        period: int = 20,
    ) -> Optional[float]:
        """
        Calculate historical volatility (annualized).

        Args:
            symbol: Stock ticker
            period: Number of trading days

        Returns:
            Annualized volatility as decimal (e.g., 0.35 for 35%)
        """
        import numpy as np

        ticker = yf.Ticker(symbol)
        df = ticker.history(period="3mo")

        if len(df) < period:
            return None

        # Calculate log returns
        df["log_return"] = np.log(df["Close"] / df["Close"].shift(1))

        # Calculate rolling std and annualize
        rolling_std = df["log_return"].tail(period).std()
        annualized_vol = rolling_std * np.sqrt(252)

        return float(annualized_vol)
```

### TradingView Screener Integration

```python
# services/tradingview.py
import httpx
from typing import List, Dict, Any

class TradingViewScreener:
    """TradingView screener integration."""

    BASE_URL = "https://scanner.tradingview.com/america/scan"

    def __init__(self):
        self.client = httpx.AsyncClient(timeout=30.0)

    async def run_screener(
        self,
        min_price: float = 5.0,
        max_price: float = 100.0,
        min_volume: int = 500000,
        min_market_cap: float = 1e9,
        additional_filters: List[Dict] = None,
    ) -> List[Dict[str, Any]]:
        """
        Run TradingView screener with specified criteria.

        Returns list of symbols matching criteria.
        """
        # Build filter array
        filters = [
            {"left": "close", "operation": "greater", "right": min_price},
            {"left": "close", "operation": "less", "right": max_price},
            {"left": "volume", "operation": "greater", "right": min_volume},
            {"left": "market_cap_basic", "operation": "greater", "right": min_market_cap},
            {"left": "type", "operation": "equal", "right": "stock"},
            {"left": "subtype", "operation": "equal", "right": "common"},
            {"left": "exchange", "operation": "in_range", "right": ["NYSE", "NASDAQ"]},
            # Optionable filter (has options)
            {"left": "is_primary", "operation": "equal", "right": True},
        ]

        if additional_filters:
            filters.extend(additional_filters)

        payload = {
            "filter": filters,
            "options": {"lang": "en"},
            "markets": ["america"],
            "symbols": {"query": {"types": []}, "tickers": []},
            "columns": [
                "name",
                "close",
                "volume",
                "market_cap_basic",
                "sector",
                "industry",
                "Recommend.All",
                "RSI",
                "SMA20",
                "SMA50",
                "SMA200",
            ],
            "sort": {"sortBy": "volume", "sortOrder": "desc"},
            "range": [0, 200],  # Get top 200 by volume
        }

        try:
            response = await self.client.post(self.BASE_URL, json=payload)
            response.raise_for_status()
            data = response.json()

            results = []
            for item in data.get("data", []):
                symbol = item["s"].split(":")[1]  # Remove exchange prefix
                values = item["d"]

                results.append({
                    "symbol": symbol,
                    "price": values[1],
                    "volume": values[2],
                    "market_cap": values[3],
                    "sector": values[4],
                    "industry": values[5],
                    "recommendation": values[6],  # -1 to 1 scale
                    "rsi": values[7],
                    "sma20": values[8],
                    "sma50": values[9],
                    "sma200": values[10],
                })

            return results

        except Exception as e:
            print(f"TradingView screener error: {e}")
            return []

    async def run_csp_screener(
        self,
        max_price: float = 100.0,
        min_volume: int = 1000000,
    ) -> List[Dict[str, Any]]:
        """
        Run screener optimized for CSP candidates.

        Filters for:
        - Price under max_price (capital efficiency)
        - High volume (liquidity)
        - Above SMA50 (uptrend)
        - RSI not overbought
        """
        filters = [
            # Above 50-day SMA (uptrend)
            {"left": "close", "operation": "greater", "right": "SMA50"},
            # RSI not overbought (< 70)
            {"left": "RSI", "operation": "less", "right": 70},
            # RSI not deeply oversold (> 30)
            {"left": "RSI", "operation": "greater", "right": 30},
        ]

        return await self.run_screener(
            min_price=10.0,
            max_price=max_price,
            min_volume=min_volume,
            additional_filters=filters,
        )

    async def close(self):
        """Close the HTTP client."""
        await self.client.aclose()
```

### Financial Data Fetching

```python
# services/financials.py
import yfinance as yf
from typing import Dict, Any, Optional

class FinancialsService:
    """Service for fetching financial data."""

    async def get_financials(
        self,
        symbol: str,
        period: str = "quarterly",
    ) -> Dict[str, Any]:
        """Get key financial metrics."""
        ticker = yf.Ticker(symbol)
        info = ticker.info

        return {
            "symbol": symbol,
            "pe_ratio": info.get("trailingPE"),
            "forward_pe": info.get("forwardPE"),
            "peg_ratio": info.get("pegRatio"),
            "price_to_book": info.get("priceToBook"),
            "price_to_sales": info.get("priceToSalesTrailing12Months"),
            "eps": info.get("trailingEps"),
            "forward_eps": info.get("forwardEps"),
            "revenue": info.get("totalRevenue"),
            "revenue_growth": info.get("revenueGrowth"),
            "profit_margin": info.get("profitMargins"),
            "operating_margin": info.get("operatingMargins"),
            "gross_margin": info.get("grossMargins"),
            "debt_to_equity": info.get("debtToEquity"),
            "current_ratio": info.get("currentRatio"),
            "return_on_equity": info.get("returnOnEquity"),
            "return_on_assets": info.get("returnOnAssets"),
            "free_cash_flow": info.get("freeCashflow"),
            "dividend_yield": info.get("dividendYield"),
        }

    async def get_earnings(self, symbol: str) -> Dict[str, Any]:
        """Get earnings history and upcoming dates."""
        ticker = yf.Ticker(symbol)

        # Get earnings dates
        try:
            earnings_dates = ticker.earnings_dates
            next_earnings = None
            if earnings_dates is not None and not earnings_dates.empty:
                future_dates = earnings_dates[
                    earnings_dates.index > pd.Timestamp.now()
                ]
                if not future_dates.empty:
                    next_earnings = str(future_dates.index[0].date())
        except Exception:
            next_earnings = None

        # Get earnings history
        try:
            earnings_history = ticker.earnings_history
            history = []
            if earnings_history is not None:
                for _, row in earnings_history.iterrows():
                    history.append({
                        "date": str(row.name),
                        "eps_estimate": row.get("epsEstimate"),
                        "eps_actual": row.get("epsActual"),
                        "surprise": row.get("surprise"),
                        "surprise_percent": row.get("surprisePct"),
                    })
        except Exception:
            history = []

        return {
            "symbol": symbol,
            "next_earnings_date": next_earnings,
            "history": history,
        }

    async def get_short_interest(self, symbol: str) -> Dict[str, Any]:
        """Get short interest data."""
        ticker = yf.Ticker(symbol)
        info = ticker.info

        return {
            "symbol": symbol,
            "short_ratio": info.get("shortRatio"),
            "short_percent_of_float": info.get("shortPercentOfFloat"),
            "shares_short": info.get("sharesShort"),
            "shares_short_prior_month": info.get("sharesShortPriorMonth"),
        }

    async def get_analyst_ratings(self, symbol: str) -> Dict[str, Any]:
        """Get analyst ratings and price targets."""
        ticker = yf.Ticker(symbol)
        info = ticker.info

        # Get recommendations
        try:
            recommendations = ticker.recommendations
            recent_recs = []
            if recommendations is not None and not recommendations.empty:
                for _, row in recommendations.tail(10).iterrows():
                    recent_recs.append({
                        "firm": row.get("Firm"),
                        "grade": row.get("To Grade"),
                        "action": row.get("Action"),
                    })
        except Exception:
            recent_recs = []

        return {
            "symbol": symbol,
            "target_high": info.get("targetHighPrice"),
            "target_low": info.get("targetLowPrice"),
            "target_mean": info.get("targetMeanPrice"),
            "target_median": info.get("targetMedianPrice"),
            "recommendation": info.get("recommendationKey"),
            "recommendation_mean": info.get("recommendationMean"),
            "num_analysts": info.get("numberOfAnalystOpinions"),
            "recent_recommendations": recent_recs,
        }
```

## Activity Patterns

### Heartbeat for Long Operations

```python
# activities/chart.py
from temporalio import activity
from typing import Callable, Optional

@activity.defn
async def chart_analysis_activity(
    params: ChartAnalysisParams,
) -> ChartAnalysisResult:
    """
    Run chart analysis with heartbeat support.

    Heartbeats keep the activity alive during long AI processing.
    LiteLLM reads API keys from environment variables automatically.
    """
    from agents.chart_analyst import ChartAnalyst

    # Model is configured on the agent class
    # LiteLLM reads API keys from standard env vars (ANTHROPIC_API_KEY, OPENAI_API_KEY, etc.)
    analyst = ChartAnalyst(
        model=params.model or "anthropic/claude-sonnet-4-20250514",
    )

    # Create heartbeat wrapper for the agentic loop
    async def heartbeat_callback():
        """Called periodically during analysis."""
        activity.heartbeat()

    result = await analyst.analyze(
        params.symbol,
        timeframe=params.timeframe,
        depth=params.analysis_depth,
        heartbeat_fn=heartbeat_callback,
    )

    return result
```

### Activity with Heartbeat Pattern

```python
# activities/market_data.py
@activity.defn
async def fetch_option_chain_with_greeks_activity(
    params: OptionChainParams,
) -> OptionChainWithGreeks:
    """
    Fetch option chain and stream Greeks.

    This is a longer operation that requires heartbeats.
    """
    from services.tastytrade import TastyTradeClient

    client = await TastyTradeClient.get_instance()

    # Heartbeat while fetching chain
    activity.heartbeat()
    chain = await client.get_option_chain(params.symbol)

    if not chain["expirations"]:
        return OptionChainWithGreeks(symbol=params.symbol, expirations=[])

    # Collect all option symbols for streaming
    option_symbols = []
    for exp in chain["expirations"]:
        for strike in exp["strikes"]:
            if strike.get("put_symbol"):
                option_symbols.append(strike["put_symbol"])
            if strike.get("call_symbol"):
                option_symbols.append(strike["call_symbol"])

    # Heartbeat before streaming
    activity.heartbeat()

    # Stream quotes and Greeks (with internal heartbeat)
    stream_data = await client.stream_option_data(
        option_symbols,
        timeout=60.0,
        idle_timeout=2.0,
    )

    # Heartbeat after streaming
    activity.heartbeat()

    # Merge stream data with chain
    return _merge_chain_with_stream_data(chain, stream_data)
```

### Serialization Contracts

All activity inputs and outputs use dataclasses with JSON serialization:

```python
# models/analysis.py
from dataclasses import dataclass, asdict
from typing import Optional, List, Dict, Any
import json

@dataclass
class ChartAnalysisParams:
    symbol: str
    timeframe: str = "daily"
    analysis_depth: str = "standard"
    include_chart_image: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ChartAnalysisParams":
        return cls(**data)

@dataclass
class ChartAnalysisResult:
    symbol: str
    recommendation: str
    trend_direction: str
    trend_quality: str
    support_levels: List[Dict[str, Any]]
    resistance_levels: List[Dict[str, Any]]
    fib_confluence_zones: List[Dict[str, Any]]
    extension_risk: str
    chart_notes: str
    tool_calls_made: int

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ChartAnalysisResult":
        return cls(**data)

    def to_json(self) -> str:
        return json.dumps(self.to_dict())

    @classmethod
    def from_json(cls, json_str: str) -> "ChartAnalysisResult":
        return cls.from_dict(json.loads(json_str))
```

### Error Handling and Retries

```python
# activities/base.py
from temporalio import activity
from temporalio.exceptions import ApplicationError
from functools import wraps
from typing import TypeVar, Callable, Any
import asyncio

T = TypeVar("T")

class ActivityError(ApplicationError):
    """Base class for activity errors."""
    pass

class RetryableError(ActivityError):
    """Error that should trigger a retry."""
    pass

class NonRetryableError(ActivityError):
    """Error that should not be retried."""

    def __init__(self, message: str, error_type: str = "NonRetryableError"):
        super().__init__(message, non_retryable=True, type=error_type)

class InvalidSymbolError(NonRetryableError):
    """Symbol not found or invalid."""

    def __init__(self, symbol: str):
        super().__init__(f"Invalid symbol: {symbol}", "InvalidSymbolError")

class RateLimitError(RetryableError):
    """Rate limit exceeded, should retry after delay."""

    def __init__(self, retry_after: float = 60.0):
        super().__init__(f"Rate limited, retry after {retry_after}s")
        self.retry_after = retry_after

class AuthenticationError(NonRetryableError):
    """Authentication failed."""

    def __init__(self, message: str = "Authentication failed"):
        super().__init__(message, "AuthenticationError")

def with_error_handling(func: Callable[..., T]) -> Callable[..., T]:
    """Decorator to add standard error handling to activities."""

    @wraps(func)
    async def wrapper(*args, **kwargs) -> T:
        try:
            return await func(*args, **kwargs)
        except InvalidSymbolError:
            raise  # Non-retryable
        except AuthenticationError:
            raise  # Non-retryable
        except RateLimitError:
            raise  # Retryable
        except Exception as e:
            # Wrap unknown errors as retryable
            raise RetryableError(f"Activity failed: {str(e)}")

    return wrapper
```

### Activity Registration

```python
# activities/__init__.py
from .chart import chart_analysis_activity
from .options import options_analysis_activity
from .research import research_analysis_activity
from .screener import (
    run_tradingview_screener_activity,
    filter_candidates_activity,
)
from .market_data import (
    fetch_quotes_activity,
    fetch_option_chain_activity,
    fetch_option_chain_with_greeks_activity,
    fetch_market_metrics_activity,
    fetch_price_history_activity,
)
from .alerts import (
    route_alerts_activity,
    check_news_activity,
    check_price_alerts_activity,
)
from .portfolio import (
    fetch_portfolio_activity,
    check_assignment_risk_activity,
)
from .storage import (
    store_screener_results_activity,
    store_analysis_results_activity,
    load_playbook_entry_activity,
)

__all__ = [
    # Chart
    "chart_analysis_activity",
    # Options
    "options_analysis_activity",
    # Research
    "research_analysis_activity",
    # Screener
    "run_tradingview_screener_activity",
    "filter_candidates_activity",
    # Market data
    "fetch_quotes_activity",
    "fetch_option_chain_activity",
    "fetch_option_chain_with_greeks_activity",
    "fetch_market_metrics_activity",
    "fetch_price_history_activity",
    # Alerts
    "route_alerts_activity",
    "check_news_activity",
    "check_price_alerts_activity",
    # Portfolio
    "fetch_portfolio_activity",
    "check_assignment_risk_activity",
    # Storage
    "store_screener_results_activity",
    "store_analysis_results_activity",
    "load_playbook_entry_activity",
]
```

## Worker Entry Point

```python
# worker.py
import asyncio
import os
import logging
from temporalio.client import Client
from temporalio.worker import Worker

from activities import (
    chart_analysis_activity,
    options_analysis_activity,
    research_analysis_activity,
    run_tradingview_screener_activity,
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
    FullAnalysisWorkflow,
    CSPScreenerWorkflow,
    NewsWatcherWorkflow,
    PriceAlertWorkflow,
    PortfolioMonitorWorkflow,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def main():
    """Start the Temporal worker."""
    # Connect to Temporal
    client = await Client.connect(
        os.environ.get("TEMPORAL_ADDRESS", "localhost:7233"),
        namespace=os.environ.get("TEMPORAL_NAMESPACE", "default"),
    )

    task_queue = os.environ.get("TEMPORAL_TASK_QUEUE", "ttai-queue")
    logger.info(f"Starting worker on task queue: {task_queue}")

    # Create and run worker
    worker = Worker(
        client,
        task_queue=task_queue,
        workflows=[
            ChartAnalysisWorkflow,
            OptionsAnalysisWorkflow,
            FullAnalysisWorkflow,
            CSPScreenerWorkflow,
            NewsWatcherWorkflow,
            PriceAlertWorkflow,
            PortfolioMonitorWorkflow,
        ],
        activities=[
            chart_analysis_activity,
            options_analysis_activity,
            research_analysis_activity,
            run_tradingview_screener_activity,
            fetch_quotes_activity,
            fetch_option_chain_activity,
            fetch_market_metrics_activity,
            route_alerts_activity,
            check_news_activity,
            fetch_portfolio_activity,
            store_screener_results_activity,
        ],
        # Worker options
        max_concurrent_activities=10,
        max_concurrent_workflow_tasks=5,
    )

    await worker.run()

if __name__ == "__main__":
    asyncio.run(main())
```

## Dockerfile

```dockerfile
# Dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY pyproject.toml ./
RUN pip install --no-cache-dir uv && \
    uv pip install --system -e .

# Copy application code
COPY . .

# Run worker
CMD ["python", "worker.py"]
```
