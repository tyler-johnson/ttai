"""
Quote fetching workflow.

This is the foundational workflow that fetches market quotes with caching.
"""

from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from activities.data_fetching import FetchQuoteInput, fetch_quote


@dataclass
class GetQuoteInput:
    """Input for GetQuoteWorkflow."""

    symbol: str


@dataclass
class GetQuoteResult:
    """Result from GetQuoteWorkflow."""

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


@workflow.defn
class GetQuoteWorkflow:
    """
    Workflow to fetch a quote for a single symbol.

    This workflow:
    1. Executes the fetch_quote activity
    2. Returns the quote data

    The activity handles caching internally, so this workflow
    simply orchestrates the fetch with proper retry policies.
    """

    @workflow.run
    async def run(self, input: GetQuoteInput) -> GetQuoteResult:
        """
        Execute the quote fetching workflow.

        Args:
            input: GetQuoteInput with the symbol to fetch

        Returns:
            GetQuoteResult with quote data
        """
        workflow.logger.info(f"Starting GetQuoteWorkflow for {input.symbol}")

        # Define retry policy for transient failures
        retry_policy = RetryPolicy(
            initial_interval=timedelta(seconds=1),
            backoff_coefficient=2.0,
            maximum_interval=timedelta(seconds=30),
            maximum_attempts=3,
        )

        # Execute the fetch_quote activity
        result = await workflow.execute_activity(
            fetch_quote,
            FetchQuoteInput(symbol=input.symbol),
            start_to_close_timeout=timedelta(seconds=30),
            retry_policy=retry_policy,
        )

        workflow.logger.info(
            f"GetQuoteWorkflow completed for {input.symbol} "
            f"(cached={result.cached}, bid={result.bid_price}, ask={result.ask_price})"
        )

        return GetQuoteResult(
            symbol=result.symbol,
            bid_price=result.bid_price,
            ask_price=result.ask_price,
            bid_size=result.bid_size,
            ask_size=result.ask_size,
            last_price=result.last_price,
            timestamp=result.timestamp,
            cached=result.cached,
        )
