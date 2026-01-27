"""
Redis cache client.

Provides async caching with TTL support for market data.
"""

import json
import logging
from typing import Any

import redis.asyncio as redis
from redis.asyncio.connection import ConnectionPool

from config import Settings, get_settings

logger = logging.getLogger(__name__)


class CacheClient:
    """Async Redis cache client."""

    def __init__(self, settings: Settings | None = None) -> None:
        """Initialize the cache client."""
        self._settings = settings or get_settings()
        self._pool: ConnectionPool | None = None
        self._client: redis.Redis | None = None

    async def _get_client(self) -> redis.Redis:
        """Get or create a Redis client."""
        if self._client is None:
            logger.info(f"Connecting to Redis at {self._settings.redis_url}")
            self._client = redis.from_url(
                self._settings.redis_url,
                encoding="utf-8",
                decode_responses=True,
            )
        return self._client

    async def close(self) -> None:
        """Close the Redis connection."""
        if self._client is not None:
            await self._client.close()
            self._client = None
            logger.info("Redis connection closed")

    async def get(self, key: str) -> str | None:
        """
        Get a value from cache.

        Args:
            key: Cache key

        Returns:
            Cached value or None if not found
        """
        client = await self._get_client()
        return await client.get(key)

    async def set(
        self,
        key: str,
        value: str,
        ttl: int | None = None,
    ) -> bool:
        """
        Set a value in cache.

        Args:
            key: Cache key
            value: Value to cache
            ttl: Time-to-live in seconds (optional)

        Returns:
            True if successful
        """
        client = await self._get_client()
        if ttl is not None:
            await client.setex(key, ttl, value)
        else:
            await client.set(key, value)
        return True

    async def get_json(self, key: str) -> Any | None:
        """
        Get a JSON value from cache.

        Args:
            key: Cache key

        Returns:
            Deserialized JSON value or None if not found
        """
        value = await self.get(key)
        if value is not None:
            return json.loads(value)
        return None

    async def set_json(
        self,
        key: str,
        value: Any,
        ttl: int | None = None,
    ) -> bool:
        """
        Set a JSON value in cache.

        Args:
            key: Cache key
            value: Value to cache (will be JSON serialized)
            ttl: Time-to-live in seconds (optional)

        Returns:
            True if successful
        """
        return await self.set(key, json.dumps(value), ttl)

    async def mget(self, keys: list[str]) -> list[str | None]:
        """
        Get multiple values from cache.

        Args:
            keys: List of cache keys

        Returns:
            List of values (None for missing keys)
        """
        if not keys:
            return []
        client = await self._get_client()
        return await client.mget(keys)

    async def mset(
        self,
        mapping: dict[str, str],
        ttl: int | None = None,
    ) -> bool:
        """
        Set multiple values in cache.

        Args:
            mapping: Dictionary of key-value pairs
            ttl: Time-to-live in seconds (applied to all keys)

        Returns:
            True if successful
        """
        if not mapping:
            return True

        client = await self._get_client()

        if ttl is not None:
            # Use pipeline for atomic operation with TTL
            pipe = client.pipeline()
            for key, value in mapping.items():
                pipe.setex(key, ttl, value)
            await pipe.execute()
        else:
            await client.mset(mapping)

        return True

    async def delete(self, *keys: str) -> int:
        """
        Delete keys from cache.

        Args:
            keys: Keys to delete

        Returns:
            Number of keys deleted
        """
        if not keys:
            return 0
        client = await self._get_client()
        return await client.delete(*keys)

    async def exists(self, key: str) -> bool:
        """
        Check if a key exists in cache.

        Args:
            key: Cache key

        Returns:
            True if key exists
        """
        client = await self._get_client()
        return bool(await client.exists(key))

    async def ping(self) -> bool:
        """
        Check if Redis is reachable.

        Returns:
            True if Redis responds to ping
        """
        try:
            client = await self._get_client()
            await client.ping()
            return True
        except Exception as e:
            logger.error(f"Redis ping failed: {e}")
            return False

    # Quote-specific helpers

    def _quote_key(self, symbol: str) -> str:
        """Generate cache key for a quote."""
        return f"quote:{symbol.upper()}"

    async def get_quote(self, symbol: str) -> dict[str, Any] | None:
        """
        Get a cached quote.

        Args:
            symbol: Stock symbol

        Returns:
            Quote data dict or None if not cached
        """
        return await self.get_json(self._quote_key(symbol))

    async def set_quote(self, symbol: str, quote_data: dict[str, Any]) -> bool:
        """
        Cache a quote.

        Args:
            symbol: Stock symbol
            quote_data: Quote data dictionary

        Returns:
            True if successful
        """
        return await self.set_json(
            self._quote_key(symbol),
            quote_data,
            ttl=self._settings.quote_cache_ttl,
        )

    async def get_quotes_cached(
        self,
        symbols: list[str],
    ) -> tuple[dict[str, dict[str, Any]], list[str]]:
        """
        Get cached quotes, returning hits and misses.

        Args:
            symbols: List of stock symbols

        Returns:
            Tuple of (cached_quotes dict, missed_symbols list)
        """
        if not symbols:
            return {}, []

        keys = [self._quote_key(s) for s in symbols]
        values = await self.mget(keys)

        cached: dict[str, dict[str, Any]] = {}
        missed: list[str] = []

        for symbol, value in zip(symbols, values):
            if value is not None:
                cached[symbol] = json.loads(value)
            else:
                missed.append(symbol)

        return cached, missed

    async def set_quotes(self, quotes: dict[str, dict[str, Any]]) -> bool:
        """
        Cache multiple quotes.

        Args:
            quotes: Dictionary mapping symbol to quote data

        Returns:
            True if successful
        """
        if not quotes:
            return True

        mapping = {self._quote_key(symbol): json.dumps(data) for symbol, data in quotes.items()}

        return await self.mset(mapping, ttl=self._settings.quote_cache_ttl)


# Global client instance
_cache_client: CacheClient | None = None


async def get_cache_client() -> CacheClient:
    """Get or create the global cache client."""
    global _cache_client
    if _cache_client is None:
        _cache_client = CacheClient()
    return _cache_client
