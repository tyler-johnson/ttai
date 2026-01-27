"""
Data fetching activities for Temporal workflows.

Activities are the building blocks that perform actual work (API calls, caching, etc.).
"""

import logging
from dataclasses import dataclass
from typing import Any

from temporalio import activity
from temporalio.exceptions import ApplicationError

from services.cache import CacheClient
from services.tastytrade import TastyTradeClient

logger = logging.getLogger(__name__)


@dataclass
class FetchQuoteInput:
    """Input parameters for fetch_quote activity."""

    symbol: str


@dataclass
class FetchQuoteOutput:
    """Output from fetch_quote activity."""

    symbol: str
    bid_price: float
    ask_price: float
    bid_size: int
    ask_size: int
    last_price: float | None
    timestamp: str
    cached: bool

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "symbol": self.symbol,
            "bid_price": self.bid_price,
            "ask_price": self.ask_price,
            "bid_size": self.bid_size,
            "ask_size": self.ask_size,
            "last_price": self.last_price,
            "timestamp": self.timestamp,
            "cached": self.cached,
        }


@activity.defn
async def fetch_quote(input: FetchQuoteInput) -> FetchQuoteOutput:
    """
    Fetch a quote for a single symbol.

    This activity:
    1. Checks Redis cache first
    2. If cache miss, fetches from TastyTrade API
    3. Caches the result with 5s TTL
    4. Returns the quote data

    Args:
        input: FetchQuoteInput with the symbol to fetch

    Returns:
        FetchQuoteOutput with quote data and cache status
    """
    symbol = input.symbol.upper()
    logger.info(f"Fetching quote for {symbol}")

    cache = CacheClient()
    tastytrade = TastyTradeClient()

    try:
        # Check cache first
        cached_quote = await cache.get_quote(symbol)
        if cached_quote is not None:
            logger.info(f"Cache hit for {symbol}")
            return FetchQuoteOutput(
                symbol=cached_quote["symbol"],
                bid_price=cached_quote["bid_price"],
                ask_price=cached_quote["ask_price"],
                bid_size=cached_quote["bid_size"],
                ask_size=cached_quote["ask_size"],
                last_price=cached_quote.get("last_price"),
                timestamp=cached_quote["timestamp"],
                cached=True,
            )

        # Cache miss - fetch from TastyTrade
        logger.info(f"Cache miss for {symbol}, fetching from TastyTrade")
        quotes = await tastytrade.get_quotes([symbol])

        if not quotes:
            raise ApplicationError(
                f"No quote data returned for {symbol}",
                type="QuoteNotFound",
                non_retryable=True,
            )

        quote = quotes[0]

        # Cache the result
        await cache.set_quote(symbol, quote.to_dict())
        logger.info(f"Cached quote for {symbol}")

        return FetchQuoteOutput(
            symbol=quote.symbol,
            bid_price=quote.bid_price,
            ask_price=quote.ask_price,
            bid_size=quote.bid_size,
            ask_size=quote.ask_size,
            last_price=quote.last_price,
            timestamp=quote.timestamp.isoformat(),
            cached=False,
        )

    except ApplicationError:
        # Re-raise application errors without wrapping
        raise
    except Exception as e:
        logger.error(f"Error fetching quote for {symbol}: {e}")
        raise ApplicationError(
            f"Failed to fetch quote for {symbol}: {e}",
            type="QuoteFetchError",
            non_retryable=False,
        ) from e
    finally:
        await cache.close()
