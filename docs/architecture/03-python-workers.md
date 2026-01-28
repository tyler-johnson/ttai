# Python Workers

## Overview

TTAI uses Cloudflare Python Workers (powered by Pyodide) to run Python code at the edge. Python Workers handle TastyTrade API integration, AI agent execution, data analysis, and market data fetching. The Pyodide runtime provides a WebAssembly-based Python environment with access to many popular packages.

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                     Cloudflare Edge Network                          │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ┌────────────────────────────────────────────────────────────────┐ │
│  │              TypeScript MCP Server                              │ │
│  │                 (Service Binding)                               │ │
│  └──────────────────────────┬─────────────────────────────────────┘ │
│                             │                                        │
│                             ▼                                        │
│  ┌────────────────────────────────────────────────────────────────┐ │
│  │              Python Workers (Pyodide Runtime)                   │ │
│  │                                                                  │ │
│  │  ┌────────────┐  ┌────────────┐  ┌────────────┐                │ │
│  │  │ TastyTrade │  │     AI     │  │  Analysis  │                │ │
│  │  │    API     │  │   Agents   │  │  Workers   │                │ │
│  │  └────────────┘  └────────────┘  └────────────┘                │ │
│  │                                                                  │ │
│  │  Available Packages:                                            │ │
│  │  - httpx (HTTP client)                                          │ │
│  │  - pandas (data analysis)                                       │ │
│  │  - numpy (numerical computing)                                  │ │
│  │  - litellm (LLM abstraction)                                    │ │
│  │  - pydantic (data validation)                                   │ │
│  │                                                                  │ │
│  └────────────────────────────────────────────────────────────────┘ │
│                             │                                        │
│              ┌──────────────┼──────────────┐                        │
│              ▼              ▼              ▼                        │
│        ┌──────────┐  ┌──────────┐  ┌──────────┐                    │
│        │    KV    │  │    D1    │  │ External │                    │
│        │  Cache   │  │ Database │  │   APIs   │                    │
│        └──────────┘  └──────────┘  └──────────┘                    │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

## Python Worker Setup

### Worker Entry Point

```python
# src/main.py
from js import Response, Request, JSON
import json

async def on_fetch(request, env):
    """Main entry point for Python Worker."""
    url = request.url
    path = url.split("/")[-1] if "/" in url else ""

    # Get user ID from headers
    user_id = request.headers.get("X-User-Id")

    try:
        if path == "quotes":
            return await handle_quotes(request, env, user_id)
        elif path == "option-chain":
            return await handle_option_chain(request, env, user_id)
        elif path == "market-data":
            return await handle_market_data(request, env, user_id)
        elif path.startswith("analyze/"):
            analysis_type = path.split("/")[1]
            return await handle_analysis(request, env, user_id, analysis_type)
        elif path == "screener/candidates":
            return await handle_screener(request, env)
        else:
            return Response.new(
                json.dumps({"error": "Not found"}),
                status=404,
                headers={"Content-Type": "application/json"}
            )
    except Exception as e:
        return Response.new(
            json.dumps({"error": str(e)}),
            status=500,
            headers={"Content-Type": "application/json"}
        )
```

### wrangler.toml for Python Worker

```toml
# wrangler.toml
name = "ttai-python-worker"
main = "src/main.py"
compatibility_date = "2024-01-01"

[build]
command = "pip install -r requirements.txt -t ./packages"

# KV Namespace for caching
[[kv_namespaces]]
binding = "KV"
id = "your-kv-namespace-id"

# D1 Database
[[d1_databases]]
binding = "DB"
database_name = "ttai"
database_id = "your-d1-database-id"

# Environment variables
[vars]
ENVIRONMENT = "production"

# Secrets (set via wrangler secret)
# ANTHROPIC_API_KEY (or other LLM provider)
```

### requirements.txt

```text
httpx>=0.25.0
pydantic>=2.0.0
pandas>=2.0.0
numpy>=1.24.0
litellm>=1.0.0
```

## TastyTrade API Integration

### TastyTrade Client

```python
# src/tastytrade/client.py
import httpx
from dataclasses import dataclass
from typing import Optional, List, Dict, Any
import json

@dataclass
class TastyTradeTokens:
    access_token: str
    refresh_token: str
    expires_at: int

class TastyTradeClient:
    """HTTP-based TastyTrade API client for Cloudflare Workers."""

    BASE_URL = "https://api.tastyworks.com"

    def __init__(self, tokens: TastyTradeTokens):
        self.tokens = tokens
        self._client = httpx.AsyncClient(
            base_url=self.BASE_URL,
            headers={
                "Authorization": f"Bearer {tokens.access_token}",
                "Content-Type": "application/json",
            },
            timeout=30.0,
        )

    @classmethod
    async def from_user_id(cls, env, user_id: str) -> Optional["TastyTradeClient"]:
        """Create client from user's stored OAuth tokens."""
        result = await env.DB.prepare(
            """SELECT access_token, refresh_token, expires_at
               FROM user_oauth_tokens
               WHERE user_id = ? AND provider = 'tastytrade'"""
        ).bind(user_id).first()

        if not result:
            return None

        tokens = TastyTradeTokens(
            access_token=result["access_token"],
            refresh_token=result["refresh_token"],
            expires_at=result["expires_at"],
        )

        return cls(tokens)

    async def get_quotes(self, symbols: List[str]) -> Dict[str, Any]:
        """Fetch quotes for multiple symbols."""
        response = await self._client.get(
            "/market-data/quotes",
            params={"symbols": ",".join(symbols)},
        )
        response.raise_for_status()
        return response.json()

    async def get_option_chain(
        self,
        symbol: str,
        expiration: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Fetch option chain for a symbol."""
        params = {"symbol": symbol}
        if expiration:
            params["expiration"] = expiration

        response = await self._client.get(
            "/option-chains",
            params=params,
        )
        response.raise_for_status()
        return response.json()

    async def get_positions(self, account_id: str) -> List[Dict[str, Any]]:
        """Fetch positions for an account."""
        response = await self._client.get(
            f"/accounts/{account_id}/positions",
        )
        response.raise_for_status()
        return response.json()["data"]["items"]

    async def get_accounts(self) -> List[Dict[str, Any]]:
        """Fetch user's accounts."""
        response = await self._client.get("/customers/me/accounts")
        response.raise_for_status()
        return response.json()["data"]["items"]
```

### Per-User OAuth Token Handling

```python
# src/tastytrade/oauth.py
import httpx
import time
from typing import Optional

async def refresh_tokens(env, user_id: str, refresh_token: str) -> Optional[dict]:
    """Refresh TastyTrade OAuth tokens."""
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://api.tastyworks.com/sessions/refresh",
            json={"refresh_token": refresh_token},
        )

        if response.status_code != 200:
            return None

        data = response.json()
        new_tokens = {
            "access_token": data["access_token"],
            "refresh_token": data["refresh_token"],
            "expires_at": int(time.time()) + data["expires_in"],
        }

        # Store updated tokens
        await env.DB.prepare(
            """UPDATE user_oauth_tokens
               SET access_token = ?, refresh_token = ?, expires_at = ?
               WHERE user_id = ? AND provider = 'tastytrade'"""
        ).bind(
            new_tokens["access_token"],
            new_tokens["refresh_token"],
            new_tokens["expires_at"],
            user_id,
        ).run()

        return new_tokens

async def get_valid_tokens(env, user_id: str) -> Optional[dict]:
    """Get valid tokens, refreshing if necessary."""
    result = await env.DB.prepare(
        """SELECT access_token, refresh_token, expires_at
           FROM user_oauth_tokens
           WHERE user_id = ? AND provider = 'tastytrade'"""
    ).bind(user_id).first()

    if not result:
        return None

    # Check if token is expired (with 5 minute buffer)
    if int(time.time()) + 300 > result["expires_at"]:
        return await refresh_tokens(env, user_id, result["refresh_token"])

    return {
        "access_token": result["access_token"],
        "refresh_token": result["refresh_token"],
        "expires_at": result["expires_at"],
    }
```

## Request Handlers

### Quotes Handler

```python
# src/handlers/quotes.py
from js import Response
import json

async def handle_quotes(request, env, user_id: str):
    """Handle quote requests."""
    from tastytrade.client import TastyTradeClient

    body = json.loads(await request.text())
    symbols = body.get("symbols", [])

    if not symbols:
        return Response.new(
            json.dumps({"error": "No symbols provided"}),
            status=400,
            headers={"Content-Type": "application/json"}
        )

    # Check cache first
    cache_key = f"quotes:{','.join(sorted(symbols))}"
    cached = await env.KV.get(cache_key)
    if cached:
        return Response.new(
            cached,
            headers={"Content-Type": "application/json"}
        )

    # Fetch from TastyTrade
    client = await TastyTradeClient.from_user_id(env, user_id)
    if not client:
        return Response.new(
            json.dumps({"error": "TastyTrade not connected"}),
            status=401,
            headers={"Content-Type": "application/json"}
        )

    quotes = await client.get_quotes(symbols)

    # Cache for 30 seconds
    result = json.dumps(quotes)
    await env.KV.put(cache_key, result, expirationTtl=30)

    return Response.new(
        result,
        headers={"Content-Type": "application/json"}
    )
```

### Option Chain Handler

```python
# src/handlers/options.py
from js import Response
import json

async def handle_option_chain(request, env, user_id: str):
    """Handle option chain requests."""
    from tastytrade.client import TastyTradeClient

    body = json.loads(await request.text())
    symbol = body.get("symbol")
    expiration = body.get("expiration")

    if not symbol:
        return Response.new(
            json.dumps({"error": "No symbol provided"}),
            status=400,
            headers={"Content-Type": "application/json"}
        )

    # Check cache
    cache_key = f"chain:{symbol}:{expiration or 'all'}"
    cached = await env.KV.get(cache_key)
    if cached:
        return Response.new(
            cached,
            headers={"Content-Type": "application/json"}
        )

    # Fetch from TastyTrade
    client = await TastyTradeClient.from_user_id(env, user_id)
    if not client:
        return Response.new(
            json.dumps({"error": "TastyTrade not connected"}),
            status=401,
            headers={"Content-Type": "application/json"}
        )

    chain = await client.get_option_chain(symbol, expiration)

    # Cache for 1 minute
    result = json.dumps(chain)
    await env.KV.put(cache_key, result, expirationTtl=60)

    return Response.new(
        result,
        headers={"Content-Type": "application/json"}
    )
```

### Market Data Handler (Yahoo Finance)

```python
# src/handlers/market_data.py
from js import Response
import httpx
import json
import pandas as pd
from io import StringIO

async def handle_market_data(request, env, user_id: str):
    """Fetch historical market data from Yahoo Finance."""
    body = json.loads(await request.text())
    symbol = body.get("symbol")
    timeframe = body.get("timeframe", "daily")
    period = body.get("period", "6mo")

    # Check cache
    cache_key = f"history:{symbol}:{timeframe}:{period}"
    cached = await env.KV.get(cache_key)
    if cached:
        return Response.new(
            cached,
            headers={"Content-Type": "application/json"}
        )

    # Map timeframe to Yahoo interval
    interval_map = {
        "intraday": "5m",
        "daily": "1d",
        "weekly": "1wk",
    }
    interval = interval_map.get(timeframe, "1d")

    # Fetch from Yahoo Finance
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}",
            params={
                "interval": interval,
                "range": period,
            },
            headers={"User-Agent": "TTAI/1.0"},
        )

        if response.status_code != 200:
            return Response.new(
                json.dumps({"error": "Failed to fetch data"}),
                status=502,
                headers={"Content-Type": "application/json"}
            )

        data = response.json()

    # Parse response into OHLCV format
    result = data.get("chart", {}).get("result", [{}])[0]
    timestamps = result.get("timestamp", [])
    quote = result.get("indicators", {}).get("quote", [{}])[0]

    bars = []
    for i, ts in enumerate(timestamps):
        bars.append({
            "timestamp": ts,
            "open": quote.get("open", [])[i],
            "high": quote.get("high", [])[i],
            "low": quote.get("low", [])[i],
            "close": quote.get("close", [])[i],
            "volume": quote.get("volume", [])[i],
        })

    result = json.dumps({
        "symbol": symbol,
        "interval": interval,
        "bars": bars,
    })

    # Cache based on timeframe
    ttl = 60 if timeframe == "intraday" else 3600  # 1 min or 1 hour
    await env.KV.put(cache_key, result, expirationTtl=ttl)

    return Response.new(
        result,
        headers={"Content-Type": "application/json"}
    )
```

## Analysis with Pandas/NumPy

### Technical Indicators

```python
# src/analysis/indicators.py
import pandas as pd
import numpy as np

def calculate_sma(prices: list, period: int) -> list:
    """Calculate Simple Moving Average."""
    series = pd.Series(prices)
    return series.rolling(window=period).mean().tolist()

def calculate_ema(prices: list, period: int) -> list:
    """Calculate Exponential Moving Average."""
    series = pd.Series(prices)
    return series.ewm(span=period, adjust=False).mean().tolist()

def calculate_rsi(prices: list, period: int = 14) -> list:
    """Calculate Relative Strength Index."""
    series = pd.Series(prices)
    delta = series.diff()

    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()

    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))

    return rsi.tolist()

def calculate_bollinger_bands(prices: list, period: int = 20, std_dev: float = 2.0) -> dict:
    """Calculate Bollinger Bands."""
    series = pd.Series(prices)
    sma = series.rolling(window=period).mean()
    std = series.rolling(window=period).std()

    return {
        "upper": (sma + std_dev * std).tolist(),
        "middle": sma.tolist(),
        "lower": (sma - std_dev * std).tolist(),
    }

def calculate_fibonacci_levels(high: float, low: float) -> dict:
    """Calculate Fibonacci retracement levels."""
    diff = high - low

    return {
        "0.0": high,
        "0.236": high - 0.236 * diff,
        "0.382": high - 0.382 * diff,
        "0.5": high - 0.5 * diff,
        "0.618": high - 0.618 * diff,
        "0.786": high - 0.786 * diff,
        "1.0": low,
    }

def calculate_historical_volatility(prices: list, period: int = 20) -> float:
    """Calculate historical volatility (annualized)."""
    series = pd.Series(prices)
    returns = series.pct_change().dropna()

    # Annualize (assuming 252 trading days)
    return returns.std() * np.sqrt(252)
```

### Support/Resistance Detection

```python
# src/analysis/levels.py
import pandas as pd
import numpy as np
from typing import List, Dict

def find_support_resistance(
    prices: List[float],
    window: int = 5,
    threshold: float = 0.02,
) -> Dict[str, List[Dict]]:
    """Find support and resistance levels."""
    series = pd.Series(prices)

    # Find local minima (support) and maxima (resistance)
    support_levels = []
    resistance_levels = []

    for i in range(window, len(series) - window):
        # Local minimum (support)
        if series[i] == series[i - window:i + window + 1].min():
            support_levels.append({
                "price": series[i],
                "index": i,
                "strength": "moderate",
            })

        # Local maximum (resistance)
        if series[i] == series[i - window:i + window + 1].max():
            resistance_levels.append({
                "price": series[i],
                "index": i,
                "strength": "moderate",
            })

    # Cluster nearby levels
    support_levels = cluster_levels(support_levels, threshold)
    resistance_levels = cluster_levels(resistance_levels, threshold)

    return {
        "support": support_levels,
        "resistance": resistance_levels,
    }

def cluster_levels(levels: List[Dict], threshold: float) -> List[Dict]:
    """Cluster nearby price levels."""
    if not levels:
        return []

    # Sort by price
    levels = sorted(levels, key=lambda x: x["price"])

    clustered = []
    current_cluster = [levels[0]]

    for level in levels[1:]:
        if abs(level["price"] - current_cluster[-1]["price"]) / current_cluster[-1]["price"] < threshold:
            current_cluster.append(level)
        else:
            # Average the cluster
            avg_price = sum(l["price"] for l in current_cluster) / len(current_cluster)
            strength = "strong" if len(current_cluster) >= 3 else "moderate"
            clustered.append({
                "price": avg_price,
                "strength": strength,
                "touches": len(current_cluster),
            })
            current_cluster = [level]

    # Don't forget the last cluster
    if current_cluster:
        avg_price = sum(l["price"] for l in current_cluster) / len(current_cluster)
        strength = "strong" if len(current_cluster) >= 3 else "moderate"
        clustered.append({
            "price": avg_price,
            "strength": strength,
            "touches": len(current_cluster),
        })

    return clustered
```

## Package Compatibility Notes

### Supported Packages

Cloudflare Python Workers use Pyodide, which supports many but not all Python packages:

**Fully Supported:**
- `httpx` - HTTP client
- `pandas` - Data analysis
- `numpy` - Numerical computing
- `pydantic` - Data validation
- `json`, `datetime`, `re` - Standard library

**Partially Supported:**
- `litellm` - Works for HTTP-based providers (Anthropic, OpenAI)
- `asyncio` - Basic async support

**Not Supported:**
- Packages requiring native extensions not compiled for WebAssembly
- `websocket` libraries (use Durable Objects for WebSocket)
- Heavy ML libraries (PyTorch, TensorFlow)

### Workarounds

```python
# For unsupported packages, use HTTP APIs instead

# Instead of a TastyTrade SDK, use raw HTTP:
async def fetch_quotes(symbols: list[str], access_token: str) -> dict:
    async with httpx.AsyncClient() as client:
        response = await client.get(
            "https://api.tastyworks.com/market-data/quotes",
            params={"symbols": ",".join(symbols)},
            headers={"Authorization": f"Bearer {access_token}"},
        )
        return response.json()

# Instead of streaming WebSocket, use polling or Durable Objects:
# The Python Worker polls; real-time updates go through Durable Objects
```

## Error Handling

```python
# src/utils/errors.py
from js import Response
import json
from typing import Optional

class TTAIError(Exception):
    """Base error class."""

    def __init__(
        self,
        message: str,
        code: str,
        status_code: int = 500,
        retryable: bool = False,
    ):
        super().__init__(message)
        self.code = code
        self.status_code = status_code
        self.retryable = retryable

    def to_response(self) -> Response:
        return Response.new(
            json.dumps({
                "error": {
                    "code": self.code,
                    "message": str(self),
                    "retryable": self.retryable,
                }
            }),
            status=self.status_code,
            headers={"Content-Type": "application/json"}
        )

class AuthenticationError(TTAIError):
    def __init__(self, message: str = "Authentication required"):
        super().__init__(message, "AUTH_ERROR", 401, False)

class RateLimitError(TTAIError):
    def __init__(self, retry_after: int = 60):
        super().__init__(
            f"Rate limited. Retry after {retry_after}s",
            "RATE_LIMIT",
            429,
            True,
        )
        self.retry_after = retry_after

class ValidationError(TTAIError):
    def __init__(self, message: str):
        super().__init__(message, "VALIDATION_ERROR", 400, False)

def handle_error(error: Exception) -> Response:
    """Convert exception to Response."""
    if isinstance(error, TTAIError):
        return error.to_response()

    # Log unexpected errors
    print(f"Unexpected error: {error}")

    return Response.new(
        json.dumps({
            "error": {
                "code": "INTERNAL_ERROR",
                "message": "An unexpected error occurred",
                "retryable": True,
            }
        }),
        status=500,
        headers={"Content-Type": "application/json"}
    )
```

## Cross-References

- [MCP Server Design](./01-mcp-server-design.md) - Service binding to Python Worker
- [AI Agent System](./04-ai-agent-system.md) - AI agents in Python Workers
- [Integration Patterns](./09-integration-patterns.md) - TypeScript to Python communication
- [Data Layer](./05-data-layer.md) - KV caching and D1 database access
