#!/usr/bin/env python3
"""
Test script to verify the data layer infrastructure.

This script validates that all components of the data layer are working:
- TastyTrade authentication and quote fetching
- Redis caching
- PostgreSQL connectivity

Run from the workers directory:
    python scripts/test_data_layer.py
"""

import asyncio
import logging
import sys
from pathlib import Path

# Add the workers directory to the path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import get_settings
from services.cache import CacheClient
from services.database import DatabaseClient
from services.tastytrade import TastyTradeClient

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def print_status(success: bool, message: str) -> None:
    """Print a status message with checkmark or X."""
    symbol = "\u2713" if success else "\u2717"
    print(f"{symbol} {message}")


async def test_tastytrade() -> bool:
    """Test TastyTrade authentication and quote fetching."""
    print("\n--- Testing TastyTrade ---")

    settings = get_settings()
    if not settings.tt_client_secret or not settings.tt_refresh_token:
        print_status(False, "TT_CLIENT_SECRET and/or TT_REFRESH_TOKEN not set, skipping")
        return False

    try:
        client = TastyTradeClient(settings)

        # Test authentication
        if client.validate_connection():
            print_status(True, "TastyTrade session authenticated")
        else:
            print_status(False, "TastyTrade authentication failed")
            return False

        # Test fetching quotes
        symbols = ["SPY", "AAPL"]
        print(f"Fetching quotes for: {symbols}")

        quotes = await client.get_quotes(symbols)

        if quotes:
            print_status(True, f"Fetched quotes for {[q.symbol for q in quotes]}")
            for quote in quotes:
                print(f"    {quote.symbol}: bid=${quote.bid_price:.2f}, ask=${quote.ask_price:.2f}")
            return True
        else:
            print_status(False, "No quotes returned")
            return False

    except Exception as e:
        print_status(False, f"TastyTrade error: {e}")
        logger.exception("TastyTrade test failed")
        return False


async def test_redis() -> bool:
    """Test Redis caching."""
    print("\n--- Testing Redis ---")

    try:
        client = CacheClient()

        # Test ping
        if await client.ping():
            print_status(True, "Redis connection healthy")
        else:
            print_status(False, "Redis ping failed")
            return False

        # Test basic get/set
        test_key = "test:data_layer"
        test_value = {"message": "hello from test"}

        await client.set_json(test_key, test_value, ttl=60)
        print_status(True, "Stored test data in Redis")

        retrieved = await client.get_json(test_key)
        if retrieved == test_value:
            print_status(True, "Retrieved test data from Redis (cache hit)")
        else:
            print_status(False, f"Cache mismatch: expected {test_value}, got {retrieved}")
            return False

        # Test quote caching
        test_quote = {
            "symbol": "TEST",
            "bid_price": 100.0,
            "ask_price": 100.05,
            "timestamp": "2024-01-01T12:00:00",
        }
        await client.set_quote("TEST", test_quote)
        cached_quote = await client.get_quote("TEST")

        if cached_quote == test_quote:
            print_status(True, "Quote caching works correctly")
        else:
            print_status(False, "Quote cache mismatch")
            return False

        # Cleanup
        await client.delete(test_key, "quote:TEST")
        await client.close()

        return True

    except Exception as e:
        print_status(False, f"Redis error: {e}")
        logger.exception("Redis test failed")
        return False


async def test_postgresql() -> bool:
    """Test PostgreSQL connectivity."""
    print("\n--- Testing PostgreSQL ---")

    try:
        client = DatabaseClient()

        # Test health check
        if await client.health_check():
            print_status(True, "PostgreSQL connection healthy")
        else:
            print_status(False, "PostgreSQL health check failed")
            return False

        # Get version
        version = await client.get_version()
        if version:
            # Truncate version for display
            version_short = version.split(",")[0] if "," in version else version[:50]
            print_status(True, f"PostgreSQL version: {version_short}")
        else:
            print_status(False, "Could not get PostgreSQL version")

        # Test simple query
        result = await client.fetchval("SELECT 1 + 1")
        if result == 2:
            print_status(True, "Query execution works")
        else:
            print_status(False, f"Query returned unexpected result: {result}")
            return False

        await client.close()
        return True

    except Exception as e:
        print_status(False, f"PostgreSQL error: {e}")
        logger.exception("PostgreSQL test failed")
        return False


async def test_integration() -> bool:
    """Test integration between TastyTrade and Redis cache."""
    print("\n--- Testing Integration (TastyTrade + Cache) ---")

    settings = get_settings()
    if not settings.tt_client_secret or not settings.tt_refresh_token:
        print_status(False, "TastyTrade credentials not set, skipping integration test")
        return False

    try:
        tt_client = TastyTradeClient(settings)
        cache_client = CacheClient()

        symbols = ["SPY"]

        # Check cache first
        cached, missed = await cache_client.get_quotes_cached(symbols)
        if cached:
            print_status(True, f"Found cached quotes: {list(cached.keys())}")
        else:
            print(f"    No cached quotes for {symbols}")

        # Fetch from API for missed symbols
        if missed:
            quotes = await tt_client.get_quotes(missed)
            quote_dicts = {q.symbol: q.to_dict() for q in quotes}

            # Cache the quotes
            await cache_client.set_quotes(quote_dicts)
            print_status(True, f"Fetched and cached quotes: {list(quote_dicts.keys())}")

        # Verify cache hit
        cached2, missed2 = await cache_client.get_quotes_cached(symbols)
        if cached2 and not missed2:
            print_status(True, "Verified cache hit after storing")
        else:
            print_status(False, "Cache miss after storing")
            return False

        await cache_client.close()
        return True

    except Exception as e:
        print_status(False, f"Integration error: {e}")
        logger.exception("Integration test failed")
        return False


async def main() -> int:
    """Run all tests and report results."""
    print("=" * 50)
    print("TTAI Data Layer Test Suite")
    print("=" * 50)

    settings = get_settings()
    tt_configured = settings.tt_client_secret and settings.tt_refresh_token
    print(f"\nConfiguration:")
    print(f"  Redis URL: {settings.redis_url}")
    print(f"  Database URL: {settings.database_url.split('@')[1] if '@' in settings.database_url else settings.database_url}")
    print(f"  TastyTrade: {'Configured' if tt_configured else 'Not configured'}")

    results = {
        "TastyTrade": False,
        "Redis": False,
        "PostgreSQL": False,
        "Integration": False,
    }

    # Run tests - Redis and PostgreSQL can run without TastyTrade
    results["Redis"] = await test_redis()
    results["PostgreSQL"] = await test_postgresql()

    # TastyTrade tests require credentials
    if tt_configured:
        results["TastyTrade"] = await test_tastytrade()
        if results["TastyTrade"] and results["Redis"]:
            results["Integration"] = await test_integration()
    else:
        print("\n--- Skipping TastyTrade tests (no credentials) ---")

    # Summary
    print("\n" + "=" * 50)
    print("Test Summary")
    print("=" * 50)

    all_passed = True
    for test_name, passed in results.items():
        if tt_configured or test_name not in ["TastyTrade", "Integration"]:
            print_status(passed, test_name)
            if not passed:
                all_passed = False
        else:
            print(f"- {test_name}: Skipped (no credentials)")

    print()

    if all_passed:
        print("All tests passed!")
        return 0
    else:
        print("Some tests failed. Check the output above.")
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
