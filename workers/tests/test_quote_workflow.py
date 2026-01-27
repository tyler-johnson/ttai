"""
Tests for the quote fetching workflow.

Uses Temporal's testing framework to test workflows in isolation.
"""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from temporalio import activity
from temporalio.exceptions import ApplicationError
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from activities.data_fetching import FetchQuoteInput, FetchQuoteOutput, fetch_quote
from workflows.quote import GetQuoteInput, GetQuoteWorkflow


@pytest.fixture
def mock_quote_output() -> FetchQuoteOutput:
    """Create a mock quote output for testing."""
    return FetchQuoteOutput(
        symbol="SPY",
        bid_price=450.50,
        ask_price=450.55,
        bid_size=100,
        ask_size=150,
        last_price=450.52,
        timestamp="2024-01-15T10:30:00",
        cached=False,
    )


class TestGetQuoteWorkflow:
    """Tests for GetQuoteWorkflow."""

    @pytest.mark.asyncio
    async def test_workflow_executes_activity(self, mock_quote_output: FetchQuoteOutput) -> None:
        """Test that workflow correctly executes the fetch_quote activity."""
        async with await WorkflowEnvironment.start_time_skipping() as env:
            # Create a mock activity decorated properly
            @activity.defn(name="fetch_quote")
            async def mock_fetch_quote(input: FetchQuoteInput) -> FetchQuoteOutput:
                assert input.symbol == "SPY"
                return mock_quote_output

            async with Worker(
                env.client,
                task_queue="test-queue",
                workflows=[GetQuoteWorkflow],
                activities=[mock_fetch_quote],
            ):
                result = await env.client.execute_workflow(
                    GetQuoteWorkflow.run,
                    GetQuoteInput(symbol="SPY"),
                    id="test-workflow-id",
                    task_queue="test-queue",
                )

                assert result.symbol == "SPY"
                assert result.bid_price == 450.50
                assert result.ask_price == 450.55
                assert result.cached is False

    @pytest.mark.asyncio
    async def test_workflow_returns_cached_result(self) -> None:
        """Test that workflow correctly returns cached results."""
        cached_output = FetchQuoteOutput(
            symbol="AAPL",
            bid_price=175.00,
            ask_price=175.05,
            bid_size=200,
            ask_size=250,
            last_price=175.02,
            timestamp="2024-01-15T10:30:00",
            cached=True,
        )

        async with await WorkflowEnvironment.start_time_skipping() as env:
            @activity.defn(name="fetch_quote")
            async def mock_fetch_quote(input: FetchQuoteInput) -> FetchQuoteOutput:
                return cached_output

            async with Worker(
                env.client,
                task_queue="test-queue",
                workflows=[GetQuoteWorkflow],
                activities=[mock_fetch_quote],
            ):
                result = await env.client.execute_workflow(
                    GetQuoteWorkflow.run,
                    GetQuoteInput(symbol="AAPL"),
                    id="test-workflow-cached",
                    task_queue="test-queue",
                )

                assert result.symbol == "AAPL"
                assert result.cached is True

    @pytest.mark.asyncio
    async def test_workflow_passes_symbol_to_activity(self) -> None:
        """Test that workflow correctly passes symbol to activity."""
        async with await WorkflowEnvironment.start_time_skipping() as env:
            received_symbols: list[str] = []

            @activity.defn(name="fetch_quote")
            async def mock_fetch_quote(input: FetchQuoteInput) -> FetchQuoteOutput:
                received_symbols.append(input.symbol)
                return FetchQuoteOutput(
                    symbol=input.symbol.upper(),
                    bid_price=100.0,
                    ask_price=100.05,
                    bid_size=100,
                    ask_size=100,
                    last_price=None,
                    timestamp="2024-01-15T10:30:00",
                    cached=False,
                )

            async with Worker(
                env.client,
                task_queue="test-queue",
                workflows=[GetQuoteWorkflow],
                activities=[mock_fetch_quote],
            ):
                await env.client.execute_workflow(
                    GetQuoteWorkflow.run,
                    GetQuoteInput(symbol="spy"),
                    id="test-workflow-lowercase",
                    task_queue="test-queue",
                )

                # Activity should receive the symbol as passed from workflow
                assert len(received_symbols) == 1
                assert received_symbols[0] == "spy"


class TestFetchQuoteActivity:
    """Tests for fetch_quote activity."""

    @pytest.mark.asyncio
    async def test_fetch_quote_cache_hit(self) -> None:
        """Test that activity returns cached data when available."""
        cached_data = {
            "symbol": "SPY",
            "bid_price": 450.50,
            "ask_price": 450.55,
            "bid_size": 100,
            "ask_size": 150,
            "last_price": 450.52,
            "timestamp": "2024-01-15T10:30:00",
        }

        with patch("activities.data_fetching.CacheClient") as mock_cache_client:
            mock_cache = AsyncMock()
            mock_cache.get_quote = AsyncMock(return_value=cached_data)
            mock_cache.close = AsyncMock()
            mock_cache_client.return_value = mock_cache

            result = await fetch_quote(FetchQuoteInput(symbol="SPY"))

            assert result.symbol == "SPY"
            assert result.bid_price == 450.50
            assert result.cached is True
            mock_cache.get_quote.assert_called_once_with("SPY")

    @pytest.mark.asyncio
    async def test_fetch_quote_cache_miss(self) -> None:
        """Test that activity fetches from TastyTrade on cache miss."""
        from services.tastytrade import QuoteData

        mock_quote = QuoteData(
            symbol="AAPL",
            bid_price=175.00,
            ask_price=175.05,
            bid_size=200,
            ask_size=250,
            last_price=175.02,
            timestamp=datetime(2024, 1, 15, 10, 30, 0),
        )

        with (
            patch("activities.data_fetching.CacheClient") as mock_cache_client,
            patch("activities.data_fetching.TastyTradeClient") as mock_tt_client,
        ):
            mock_cache = AsyncMock()
            mock_cache.get_quote = AsyncMock(return_value=None)
            mock_cache.set_quote = AsyncMock(return_value=True)
            mock_cache.close = AsyncMock()
            mock_cache_client.return_value = mock_cache

            mock_tt = MagicMock()
            mock_tt.get_quotes = AsyncMock(return_value=[mock_quote])
            mock_tt_client.return_value = mock_tt

            result = await fetch_quote(FetchQuoteInput(symbol="AAPL"))

            assert result.symbol == "AAPL"
            assert result.bid_price == 175.00
            assert result.cached is False
            mock_cache.set_quote.assert_called_once()

    @pytest.mark.asyncio
    async def test_fetch_quote_not_found(self) -> None:
        """Test that activity raises error when quote not found."""
        with (
            patch("activities.data_fetching.CacheClient") as mock_cache_client,
            patch("activities.data_fetching.TastyTradeClient") as mock_tt_client,
        ):
            mock_cache = AsyncMock()
            mock_cache.get_quote = AsyncMock(return_value=None)
            mock_cache.close = AsyncMock()
            mock_cache_client.return_value = mock_cache

            mock_tt = MagicMock()
            mock_tt.get_quotes = AsyncMock(return_value=[])
            mock_tt_client.return_value = mock_tt

            with pytest.raises(ApplicationError) as exc_info:
                await fetch_quote(FetchQuoteInput(symbol="INVALID"))

            assert "No quote data returned" in str(exc_info.value)
