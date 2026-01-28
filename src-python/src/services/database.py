"""SQLite database service with async support."""

import logging
from pathlib import Path
from types import TracebackType

import aiosqlite

logger = logging.getLogger("ttai.database")


class DatabaseService:
    """Async SQLite database wrapper."""

    def __init__(self, db_path: Path) -> None:
        """Initialize the database service.

        Args:
            db_path: Path to the SQLite database file
        """
        self._db_path = db_path
        self._connection: aiosqlite.Connection | None = None

    @classmethod
    async def create(cls, db_path: Path) -> "DatabaseService":
        """Factory method to create and initialize a database service.

        Args:
            db_path: Path to the SQLite database file

        Returns:
            An initialized DatabaseService instance
        """
        service = cls(db_path)
        await service._connect()
        await service._initialize_schema()
        return service

    async def _connect(self) -> None:
        """Establish database connection."""
        # Ensure parent directory exists
        self._db_path.parent.mkdir(parents=True, exist_ok=True)

        self._connection = await aiosqlite.connect(self._db_path)
        self._connection.row_factory = aiosqlite.Row

        # Enable foreign keys and WAL mode for better concurrency
        await self._connection.execute("PRAGMA foreign_keys = ON")
        await self._connection.execute("PRAGMA journal_mode = WAL")

        logger.info(f"Connected to database: {self._db_path}")

    async def _initialize_schema(self) -> None:
        """Initialize database schema with migrations table."""
        if self._connection is None:
            raise RuntimeError("Database not connected")

        # Create migrations table to track schema versions
        await self._connection.execute("""
            CREATE TABLE IF NOT EXISTS _migrations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await self._connection.commit()

        logger.debug("Database schema initialized")

    async def close(self) -> None:
        """Close the database connection."""
        if self._connection is not None:
            await self._connection.close()
            self._connection = None
            logger.info("Database connection closed")

    async def __aenter__(self) -> "DatabaseService":
        """Async context manager entry."""
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Async context manager exit."""
        await self.close()

    @property
    def connection(self) -> aiosqlite.Connection:
        """Get the database connection.

        Raises:
            RuntimeError: If the database is not connected
        """
        if self._connection is None:
            raise RuntimeError("Database not connected")
        return self._connection

    async def execute(
        self, sql: str, parameters: tuple[object, ...] | None = None
    ) -> aiosqlite.Cursor:
        """Execute a SQL statement.

        Args:
            sql: SQL statement to execute
            parameters: Optional parameters for the statement

        Returns:
            The cursor from the executed statement
        """
        if parameters is None:
            return await self.connection.execute(sql)
        return await self.connection.execute(sql, parameters)

    async def executemany(
        self, sql: str, parameters: list[tuple[object, ...]]
    ) -> aiosqlite.Cursor:
        """Execute a SQL statement with multiple parameter sets.

        Args:
            sql: SQL statement to execute
            parameters: List of parameter tuples

        Returns:
            The cursor from the executed statement
        """
        return await self.connection.executemany(sql, parameters)

    async def commit(self) -> None:
        """Commit the current transaction."""
        await self.connection.commit()

    async def fetchone(
        self, sql: str, parameters: tuple[object, ...] | None = None
    ) -> aiosqlite.Row | None:
        """Execute a query and fetch one result.

        Args:
            sql: SQL query to execute
            parameters: Optional parameters for the query

        Returns:
            The first row of results, or None if no results
        """
        cursor = await self.execute(sql, parameters)
        return await cursor.fetchone()

    async def fetchall(
        self, sql: str, parameters: tuple[object, ...] | None = None
    ) -> list[aiosqlite.Row]:
        """Execute a query and fetch all results.

        Args:
            sql: SQL query to execute
            parameters: Optional parameters for the query

        Returns:
            List of all result rows
        """
        cursor = await self.execute(sql, parameters)
        return await cursor.fetchall()
