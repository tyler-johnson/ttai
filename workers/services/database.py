"""
PostgreSQL async database client.

Provides connection pooling and basic query execution using asyncpg.
"""

import logging
from typing import Any
from urllib.parse import urlparse

import asyncpg
from asyncpg import Connection, Pool

from config import Settings, get_settings

logger = logging.getLogger(__name__)


class DatabaseClient:
    """Async PostgreSQL client with connection pooling."""

    def __init__(self, settings: Settings | None = None) -> None:
        """Initialize the database client."""
        self._settings = settings or get_settings()
        self._pool: Pool | None = None

    def _parse_dsn(self) -> dict[str, Any]:
        """Parse DATABASE_URL into connection parameters."""
        url = urlparse(self._settings.database_url)
        return {
            "user": url.username,
            "password": url.password,
            "host": url.hostname,
            "port": url.port or 5432,
            "database": url.path.lstrip("/"),
        }

    async def _get_pool(self) -> Pool:
        """Get or create the connection pool."""
        if self._pool is None:
            conn_params = self._parse_dsn()
            logger.info(
                f"Creating PostgreSQL pool: {conn_params['host']}:{conn_params['port']}"
                f"/{conn_params['database']}"
            )

            self._pool = await asyncpg.create_pool(
                **conn_params,
                min_size=self._settings.db_pool_min_size,
                max_size=self._settings.db_pool_max_size,
            )
            logger.info("PostgreSQL connection pool created")

        return self._pool

    async def close(self) -> None:
        """Close the connection pool."""
        if self._pool is not None:
            await self._pool.close()
            self._pool = None
            logger.info("PostgreSQL connection pool closed")

    async def execute(
        self,
        query: str,
        *args: Any,
    ) -> str:
        """
        Execute a query that doesn't return rows.

        Args:
            query: SQL query string
            args: Query parameters

        Returns:
            Status string (e.g., "INSERT 0 1")
        """
        pool = await self._get_pool()
        return await pool.execute(query, *args)

    async def fetch(
        self,
        query: str,
        *args: Any,
    ) -> list[asyncpg.Record]:
        """
        Execute a query and return all rows.

        Args:
            query: SQL query string
            args: Query parameters

        Returns:
            List of Record objects
        """
        pool = await self._get_pool()
        return await pool.fetch(query, *args)

    async def fetchrow(
        self,
        query: str,
        *args: Any,
    ) -> asyncpg.Record | None:
        """
        Execute a query and return the first row.

        Args:
            query: SQL query string
            args: Query parameters

        Returns:
            Record object or None if no rows
        """
        pool = await self._get_pool()
        return await pool.fetchrow(query, *args)

    async def fetchval(
        self,
        query: str,
        *args: Any,
        column: int = 0,
    ) -> Any:
        """
        Execute a query and return a single value.

        Args:
            query: SQL query string
            args: Query parameters
            column: Column index to return (default 0)

        Returns:
            Single value from the specified column
        """
        pool = await self._get_pool()
        return await pool.fetchval(query, *args, column=column)

    async def acquire(self) -> Connection:
        """
        Acquire a connection from the pool.

        Use as an async context manager:
            async with db.acquire() as conn:
                await conn.execute(...)

        Returns:
            Connection object
        """
        pool = await self._get_pool()
        return pool.acquire()

    async def health_check(self) -> bool:
        """
        Check if the database is reachable and responding.

        Returns:
            True if healthy
        """
        try:
            result = await self.fetchval("SELECT 1")
            return result == 1
        except Exception as e:
            logger.error(f"Database health check failed: {e}")
            return False

    async def get_version(self) -> str | None:
        """
        Get the PostgreSQL version.

        Returns:
            Version string or None on error
        """
        try:
            return await self.fetchval("SELECT version()")
        except Exception as e:
            logger.error(f"Failed to get database version: {e}")
            return None


# Global client instance
_database_client: DatabaseClient | None = None


async def get_database_client() -> DatabaseClient:
    """Get or create the global database client."""
    global _database_client
    if _database_client is None:
        _database_client = DatabaseClient()
    return _database_client
