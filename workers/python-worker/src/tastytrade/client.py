"""TastyTrade HTTP client for market data."""

from typing import Any
import httpx

from .auth import get_access_token

API_URL = "https://api.tastyworks.com"
API_VERSION = "20251101"


class TastyTradeClient:
    """HTTP client for TastyTrade API."""

    def __init__(self, client_secret: str, refresh_token: str):
        """
        Initialize the client with OAuth credentials.

        Args:
            client_secret: OAuth client secret for your provider
            refresh_token: Refresh token for the user
        """
        self.client_secret = client_secret
        self.refresh_token = refresh_token
        self._access_token: str | None = None

    @classmethod
    def from_access_token(cls, access_token: str) -> "TastyTradeClient":
        """
        Create a client with a pre-fetched access token.

        This is used for per-user authentication where the MCP server
        has already obtained and refreshed the access token.

        Args:
            access_token: Valid TastyTrade access token

        Returns:
            TastyTradeClient instance with the token pre-set
        """
        # Create instance without credentials (won't be used)
        instance = cls.__new__(cls)
        instance.client_secret = None
        instance.refresh_token = None
        instance._access_token = access_token
        return instance

    async def _ensure_authenticated(self) -> str:
        """Get or refresh the access token."""
        if self._access_token is None:
            if not self.client_secret or not self.refresh_token:
                raise ValueError("No access token or credentials available")
            self._access_token = await get_access_token(
                self.client_secret, self.refresh_token
            )
        return self._access_token

    async def get_market_metrics(self, symbols: list[str]) -> dict[str, Any]:
        """
        Get market metrics for the given symbols.

        Args:
            symbols: List of stock symbols (e.g., ["AAPL", "GOOGL"])

        Returns:
            Market metrics data from TastyTrade API

        Raises:
            httpx.HTTPStatusError: If the API request fails
        """
        access_token = await self._ensure_authenticated()

        async with httpx.AsyncClient(base_url=API_URL) as client:
            response = await client.get(
                "/market-metrics",
                params={"symbols": ",".join(symbols)},
                headers={
                    "Accept": "application/json",
                    "Accept-Version": API_VERSION,
                    "Authorization": f"Bearer {access_token}",
                },
                timeout=30.0,
            )
            response.raise_for_status()
            return response.json()

    async def get_market_data(
        self,
        equities: list[str] | None = None,
        options: list[str] | None = None,
    ) -> dict[str, Any]:
        """
        Get market data (bid/ask/last) for symbols.

        Args:
            equities: List of equity symbols (e.g., ["AAPL", "SPY"])
            options: List of OCC option symbols

        Returns:
            Market data from TastyTrade API (limit 100 total symbols)
        """
        access_token = await self._ensure_authenticated()

        params = {}
        if equities:
            params["equity"] = equities
        if options:
            params["equity-option"] = options

        async with httpx.AsyncClient(base_url=API_URL) as client:
            response = await client.get(
                "/market-data/by-type",
                params=params,
                headers={
                    "Accept": "application/json",
                    "Accept-Version": API_VERSION,
                    "Authorization": f"Bearer {access_token}",
                },
                timeout=30.0,
            )
            response.raise_for_status()
            return response.json()

    async def get_quote(self, symbol: str) -> dict[str, Any]:
        """
        Get quote data for a single equity symbol.

        Args:
            symbol: Stock symbol (e.g., "AAPL")

        Returns:
            Quote data with bid/ask/last and market metrics
        """
        symbol = symbol.upper()

        # Fetch market data (bid/ask/last) and market metrics in parallel
        market_data_result = await self.get_market_data(equities=[symbol])
        metrics_result = await self.get_market_metrics([symbol])

        # Parse market data
        market_items = market_data_result.get("data", {}).get("items", [])
        market_data = market_items[0] if market_items else {}

        # Parse market metrics
        metrics_items = metrics_result.get("data", {}).get("items", [])
        metrics = metrics_items[0] if metrics_items else {}

        if not market_data and not metrics:
            return {
                "symbol": symbol,
                "error": f"No data found for symbol {symbol}",
            }

        return {
            "symbol": symbol,
            # Quote data
            "bid": market_data.get("bid"),
            "ask": market_data.get("ask"),
            "last": market_data.get("last"),
            "mid": market_data.get("mid"),
            "mark": market_data.get("mark"),
            "volume": market_data.get("volume"),
            "open": market_data.get("open"),
            "high": market_data.get("day-high-price"),
            "low": market_data.get("day-low-price"),
            "close": market_data.get("close"),
            "prev_close": market_data.get("prev-close"),
            # Market metrics
            "iv_rank": metrics.get("implied-volatility-index-rank"),
            "iv_percentile": metrics.get("implied-volatility-percentile"),
            "iv_30_day": metrics.get("implied-volatility-30-day"),
            "hv_30_day": metrics.get("historical-volatility-30-day"),
            "beta": metrics.get("beta"),
            "market_cap": metrics.get("market-cap"),
            "earnings_date": metrics.get("earnings", {}).get("expected-report-date") if metrics.get("earnings") else None,
            "updated_at": market_data.get("updated-at") or metrics.get("updated-at"),
        }
