"""TastyTrade API service using the official SDK."""

import logging
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from tastytrade import Session
from tastytrade.instruments import InstrumentType
from tastytrade.market_data import get_market_data
from tastytrade.metrics import get_market_metrics

from src.auth.credentials import CredentialManager
from src.services.cache import CacheService

logger = logging.getLogger("ttai.tastytrade")

QUOTE_CACHE_TTL = 60.0  # seconds


def _to_float(val: Decimal | None) -> float | None:
    """Convert Decimal to float, handling None."""
    return float(val) if val is not None else None


@dataclass
class QuoteData:
    """Quote data with market data and metrics."""

    symbol: str
    # Quote data
    bid: float | None = None
    ask: float | None = None
    last: float | None = None
    mid: float | None = None
    mark: float | None = None
    volume: float | None = None
    open: float | None = None
    high: float | None = None
    low: float | None = None
    close: float | None = None
    prev_close: float | None = None
    # 52-week range
    year_high: float | None = None
    year_low: float | None = None
    # Market metrics
    iv_rank: float | None = None
    iv_percentile: float | None = None
    iv_30_day: float | None = None
    hv_30_day: float | None = None
    iv_hv_diff: float | None = None
    beta: float | None = None
    market_cap: float | None = None
    pe_ratio: float | None = None
    earnings_per_share: float | None = None
    dividend_yield: float | None = None
    liquidity_rating: int | None = None
    earnings_date: str | None = None
    updated_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {k: v for k, v in self.__dict__.items() if v is not None}


class TastyTradeService:
    """Service for interacting with TastyTrade API."""

    def __init__(
        self,
        credential_manager: CredentialManager,
        cache: CacheService,
    ) -> None:
        """Initialize the TastyTrade service.

        Args:
            credential_manager: Manager for credential storage
            cache: Cache service for quote caching
        """
        self._credential_manager = credential_manager
        self._cache = cache
        self._session: Session | None = None

    @property
    def is_authenticated(self) -> bool:
        """Check if we have an active session."""
        return self._session is not None

    async def login(
        self,
        client_secret: str,
        refresh_token: str,
        remember_me: bool = False,
    ) -> bool:
        """Authenticate with TastyTrade using OAuth.

        Args:
            client_secret: TastyTrade OAuth client secret
            refresh_token: TastyTrade OAuth refresh token
            remember_me: Whether to store credentials for session restore

        Returns:
            True if login successful, False otherwise
        """
        try:
            self._session = Session(client_secret, refresh_token)
            logger.info("Successfully authenticated with TastyTrade OAuth")

            if remember_me:
                self._credential_manager.store_credentials(
                    client_secret=client_secret,
                    refresh_token=refresh_token,
                )

            return True
        except Exception as e:
            logger.error(f"Login failed: {e}")
            self._session = None
            return False

    async def restore_session(self) -> bool:
        """Attempt to restore session from stored credentials.

        Returns:
            True if session restored successfully, False otherwise
        """
        credentials = self._credential_manager.load_credentials()
        if credentials is None:
            return False

        try:
            self._session = Session(credentials.client_secret, credentials.refresh_token)
            logger.info("Session restored using stored OAuth credentials")
            return True
        except Exception as e:
            logger.error(f"Failed to restore session: {e}")
            return False

    async def logout(self, clear_credentials: bool = True) -> None:
        """Log out and optionally clear stored credentials.

        Args:
            clear_credentials: Whether to remove stored credentials
        """
        if self._session:
            try:
                self._session.destroy()
            except Exception as e:
                logger.warning(f"Error destroying session: {e}")

        self._session = None

        if clear_credentials:
            self._credential_manager.clear_credentials()

        logger.info("Logged out successfully")

    async def get_quote(self, symbol: str) -> QuoteData | None:
        """Get quote data for a symbol.

        Fetches both market data (bid/ask/last) and market metrics (IV, beta, etc.).

        Args:
            symbol: The ticker symbol

        Returns:
            QuoteData if successful, None otherwise
        """
        if not self.is_authenticated:
            logger.error("Not authenticated")
            return None

        symbol = symbol.upper()
        cache_key = f"quote:{symbol}"

        # Check cache first
        cached = self._cache.get(cache_key)
        if cached is not None:
            logger.debug(f"Cache hit for {symbol}")
            return cached

        try:
            # Fetch market data and market metrics
            market_data = get_market_data(self._session, symbol, InstrumentType.EQUITY)
            metrics_list = get_market_metrics(self._session, [symbol])
            metrics = metrics_list[0] if metrics_list else None

            # Extract earnings date if available
            earnings_date = None
            if metrics and metrics.earnings:
                earnings_date = str(metrics.earnings.expected_report_date)

            quote_data = QuoteData(
                symbol=symbol,
                # Quote data
                bid=_to_float(market_data.bid),
                ask=_to_float(market_data.ask),
                last=_to_float(market_data.last),
                mid=_to_float(market_data.mid),
                mark=_to_float(market_data.mark),
                volume=_to_float(market_data.volume),
                open=_to_float(market_data.day_open),
                high=_to_float(market_data.day_high_price),
                low=_to_float(market_data.day_low_price),
                close=_to_float(market_data.close),
                prev_close=_to_float(market_data.prev_close),
                year_high=_to_float(market_data.year_high_price),
                year_low=_to_float(market_data.year_low_price),
                # Market metrics
                iv_rank=_to_float(metrics.tw_implied_volatility_index_rank) if metrics else None,
                iv_percentile=float(metrics.implied_volatility_percentile) if metrics and metrics.implied_volatility_percentile else None,
                iv_30_day=_to_float(metrics.implied_volatility_30_day) if metrics else None,
                hv_30_day=_to_float(metrics.historical_volatility_30_day) if metrics else None,
                iv_hv_diff=_to_float(metrics.iv_hv_30_day_difference) if metrics else None,
                beta=_to_float(metrics.beta) if metrics else None,
                market_cap=_to_float(metrics.market_cap) if metrics else None,
                pe_ratio=_to_float(metrics.price_earnings_ratio) if metrics else None,
                earnings_per_share=_to_float(metrics.earnings_per_share) if metrics else None,
                dividend_yield=_to_float(metrics.dividend_yield) if metrics else None,
                liquidity_rating=metrics.liquidity_rating if metrics else None,
                earnings_date=earnings_date,
                updated_at=market_data.updated_at.isoformat() if market_data.updated_at else None,
            )

            # Cache the result
            self._cache.set(cache_key, quote_data, ttl=QUOTE_CACHE_TTL)
            logger.debug(f"Fetched quote for {symbol}")

            return quote_data
        except Exception as e:
            logger.error(f"Failed to get quote for {symbol}: {e}")
            return None

    def get_auth_status(self) -> dict:
        """Get current authentication status.

        Returns:
            Dictionary with authentication status details
        """
        return {
            "authenticated": self.is_authenticated,
            "has_stored_credentials": self._credential_manager.has_credentials(),
        }
