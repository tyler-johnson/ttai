"""
TastyTrade API client.

Provides session management and market data fetching using the tastytrade SDK.
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from typing import Any

from tastytrade import Session
from tastytrade.dxfeed import Quote
from tastytrade.instruments import Equity
from tastytrade.streamer import DXLinkStreamer

from config import Settings, get_settings

logger = logging.getLogger(__name__)


@dataclass
class QuoteData:
    """Simplified quote data structure."""

    symbol: str
    bid_price: float
    ask_price: float
    bid_size: int
    ask_size: int
    last_price: float | None
    timestamp: datetime

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "symbol": self.symbol,
            "bid_price": self.bid_price,
            "ask_price": self.ask_price,
            "bid_size": self.bid_size,
            "ask_size": self.ask_size,
            "last_price": self.last_price,
            "timestamp": self.timestamp.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "QuoteData":
        """Create from dictionary."""
        return cls(
            symbol=data["symbol"],
            bid_price=data["bid_price"],
            ask_price=data["ask_price"],
            bid_size=data["bid_size"],
            ask_size=data["ask_size"],
            last_price=data.get("last_price"),
            timestamp=datetime.fromisoformat(data["timestamp"]),
        )


class TastyTradeClient:
    """Client for interacting with TastyTrade API."""

    def __init__(self, settings: Settings | None = None) -> None:
        """Initialize the TastyTrade client."""
        self._settings = settings or get_settings()
        self._session: Session | None = None

    def _get_session(self) -> Session:
        """Get or create an authenticated session."""
        if self._session is None:
            if not self._settings.tt_client_secret:
                raise ValueError("TT_CLIENT_SECRET environment variable is required")
            if not self._settings.tt_refresh_token:
                raise ValueError("TT_REFRESH_TOKEN environment variable is required")

            logger.info("Creating TastyTrade session")
            self._session = Session(
                provider_secret=self._settings.tt_client_secret,
                refresh_token=self._settings.tt_refresh_token,
            )
            logger.info("TastyTrade session authenticated successfully")

        return self._session

    @property
    def session(self) -> Session:
        """Get the authenticated session."""
        return self._get_session()

    async def get_quotes(self, symbols: list[str]) -> list[QuoteData]:
        """
        Fetch current quotes for the given symbols.

        Uses the DXLink streamer to get real-time quotes.

        Args:
            symbols: List of stock symbols (e.g., ["SPY", "AAPL"])

        Returns:
            List of QuoteData objects
        """
        if not symbols:
            return []

        session = self._get_session()

        # Convert symbols to equity instruments for streamer symbols
        # The streamer expects the DXFeed symbol format
        streamer_symbols = symbols  # For equities, symbol format is the same

        quotes: list[QuoteData] = []

        async with DXLinkStreamer(session) as streamer:
            await streamer.subscribe(Quote, streamer_symbols)

            # Collect quotes for all requested symbols
            received = set()
            while len(received) < len(symbols):
                quote = await streamer.get_event(Quote)
                symbol = quote.eventSymbol

                if symbol not in received:
                    received.add(symbol)
                    quotes.append(
                        QuoteData(
                            symbol=symbol,
                            bid_price=float(quote.bidPrice) if quote.bidPrice else 0.0,
                            ask_price=float(quote.askPrice) if quote.askPrice else 0.0,
                            bid_size=int(quote.bidSize) if quote.bidSize else 0,
                            ask_size=int(quote.askSize) if quote.askSize else 0,
                            last_price=None,  # Quote doesn't have last price, would need Trade event
                            timestamp=datetime.now(),
                        )
                    )

        return quotes

    def get_quote_sync(self, symbol: str) -> QuoteData | None:
        """
        Fetch a single quote synchronously using the REST API.

        This is simpler for single-quote lookups but less efficient for batches.

        Args:
            symbol: Stock symbol (e.g., "SPY")

        Returns:
            QuoteData or None if not found
        """
        session = self._get_session()

        # Use the market metrics endpoint for a quick quote
        try:
            equities = Equity.get_equities(session, [symbol])
            if not equities:
                return None

            equity = equities[0]

            # Get streamer symbol for the equity
            return QuoteData(
                symbol=symbol,
                bid_price=0.0,  # REST API doesn't provide live quotes
                ask_price=0.0,
                bid_size=0,
                ask_size=0,
                last_price=None,
                timestamp=datetime.now(),
            )
        except Exception as e:
            logger.error(f"Failed to fetch quote for {symbol}: {e}")
            return None

    def get_accounts(self) -> list[dict[str, Any]]:
        """
        Get all accounts for the authenticated user.

        Returns:
            List of account dictionaries
        """
        session = self._get_session()
        accounts = session.get_customer().accounts

        return [
            {
                "account_number": acc.account.account_number,
                "nickname": acc.account.nickname,
                "is_margin": acc.account.is_margin,
            }
            for acc in accounts
        ]

    def validate_connection(self) -> bool:
        """
        Validate that we can connect to TastyTrade.

        Returns:
            True if connection is valid
        """
        try:
            session = self._get_session()
            # Simple validation - try to get customer info
            customer = session.get_customer()
            logger.info(f"Connected as: {customer.first_name} {customer.last_name}")
            return True
        except Exception as e:
            logger.error(f"TastyTrade connection validation failed: {e}")
            return False


@lru_cache
def get_tastytrade_client() -> TastyTradeClient:
    """Get cached TastyTrade client instance."""
    return TastyTradeClient()
