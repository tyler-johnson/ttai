"""In-memory cache service with TTL support."""

import threading
import time
from dataclasses import dataclass
from typing import Any


@dataclass
class CacheEntry:
    """A cached value with expiration time."""

    value: Any
    expires_at: float | None  # None means no expiration


class CacheService:
    """Thread-safe in-memory cache with TTL support."""

    def __init__(self) -> None:
        """Initialize the cache service."""
        self._cache: dict[str, CacheEntry] = {}
        self._lock = threading.RLock()

    def get(self, key: str) -> Any | None:
        """Get a value from the cache.

        Args:
            key: The cache key

        Returns:
            The cached value, or None if not found or expired
        """
        with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                return None

            # Check expiration
            if entry.expires_at is not None and time.time() > entry.expires_at:
                del self._cache[key]
                return None

            return entry.value

    def set(self, key: str, value: Any, ttl: float | None = None) -> None:
        """Set a value in the cache.

        Args:
            key: The cache key
            value: The value to cache
            ttl: Time-to-live in seconds (None for no expiration)
        """
        with self._lock:
            expires_at = None if ttl is None else time.time() + ttl
            self._cache[key] = CacheEntry(value=value, expires_at=expires_at)

    def delete(self, key: str) -> bool:
        """Delete a value from the cache.

        Args:
            key: The cache key

        Returns:
            True if the key was deleted, False if not found
        """
        with self._lock:
            if key in self._cache:
                del self._cache[key]
                return True
            return False

    def clear(self) -> None:
        """Clear all values from the cache."""
        with self._lock:
            self._cache.clear()

    def cleanup_expired(self) -> int:
        """Remove all expired entries from the cache.

        Returns:
            Number of entries removed
        """
        with self._lock:
            now = time.time()
            expired_keys = [
                key
                for key, entry in self._cache.items()
                if entry.expires_at is not None and now > entry.expires_at
            ]
            for key in expired_keys:
                del self._cache[key]
            return len(expired_keys)
