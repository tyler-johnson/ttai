"""Tests for service modules."""

import asyncio
import tempfile
from pathlib import Path

import pytest

from src.services.cache import CacheService
from src.services.database import DatabaseService


class TestCacheService:
    """Tests for CacheService."""

    def test_set_and_get(self) -> None:
        cache = CacheService()
        cache.set("key", "value")
        assert cache.get("key") == "value"

    def test_get_missing_key(self) -> None:
        cache = CacheService()
        assert cache.get("missing") is None

    def test_delete(self) -> None:
        cache = CacheService()
        cache.set("key", "value")
        assert cache.delete("key") is True
        assert cache.get("key") is None
        assert cache.delete("key") is False

    def test_clear(self) -> None:
        cache = CacheService()
        cache.set("key1", "value1")
        cache.set("key2", "value2")
        cache.clear()
        assert cache.get("key1") is None
        assert cache.get("key2") is None

    def test_ttl_expiration(self) -> None:
        import time

        cache = CacheService()
        cache.set("key", "value", ttl=0.1)
        assert cache.get("key") == "value"
        time.sleep(0.15)
        assert cache.get("key") is None


class TestDatabaseService:
    """Tests for DatabaseService."""

    @pytest.mark.asyncio
    async def test_create_and_close(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = await DatabaseService.create(db_path)
            assert db_path.exists()
            await db.close()

    @pytest.mark.asyncio
    async def test_context_manager(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            async with await DatabaseService.create(db_path) as db:
                assert db.connection is not None
            # Connection should be closed after context exit

    @pytest.mark.asyncio
    async def test_execute_and_fetch(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            async with await DatabaseService.create(db_path) as db:
                await db.execute("CREATE TABLE test (id INTEGER, name TEXT)")
                await db.execute("INSERT INTO test VALUES (?, ?)", (1, "alice"))
                await db.commit()

                row = await db.fetchone("SELECT * FROM test WHERE id = ?", (1,))
                assert row is not None
                assert row["name"] == "alice"

                rows = await db.fetchall("SELECT * FROM test")
                assert len(rows) == 1
