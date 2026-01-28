# Data Layer

## Overview

The TTAI data layer uses local SQLite for all persistent storage, with aiosqlite for async database operations. Credentials are encrypted using Fernet symmetric encryption, quotes are cached in memory with TTL, and all data is stored in the user's data directory (`~/.ttai/`).

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                    Python MCP Server (Sidecar)                       │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ┌────────────────────────────────────────────────────────────────┐ │
│  │                    Database Service                             │ │
│  │                   (aiosqlite wrapper)                           │ │
│  └──────────────────────────┬─────────────────────────────────────┘ │
│                             │                                        │
│      ┌──────────────────────┼──────────────────────────┐            │
│      ▼                      ▼                          ▼            │
│  ┌────────────┐    ┌────────────────┐    ┌────────────────┐        │
│  │ In-Memory  │    │    SQLite      │    │  File System   │        │
│  │   Cache    │    │   Database     │    │    Storage     │        │
│  │            │    │                │    │                │        │
│  │ - Quotes   │    │ - Positions    │    │ - Documents    │        │
│  │ - Chains   │    │ - Analyses     │    │ - Credentials  │        │
│  │ - Sessions │    │ - Alerts       │    │ - Exports      │        │
│  │            │    │ - Knowledge    │    │ - Logs         │        │
│  └────────────┘    └────────────────┘    └────────────────┘        │
│                                                                      │
│  ┌────────────────────────────────────────────────────────────────┐ │
│  │                 Local Data Directory (~/.ttai/)                 │ │
│  │  ┌───────────────┐  ┌───────────────┐  ┌───────────────┐       │ │
│  │  │  ttai.db      │  │  knowledge/   │  │  exports/     │       │ │
│  │  │  (SQLite)     │  │  (Documents)  │  │  (Reports)    │       │ │
│  │  └───────────────┘  └───────────────┘  └───────────────┘       │ │
│  │  ┌───────────────┐  ┌───────────────┐  ┌───────────────┐       │ │
│  │  │  .key         │  │  .credentials │  │  logs/        │       │ │
│  │  │  (Encryption) │  │  (Encrypted)  │  │  (App logs)   │       │ │
│  │  └───────────────┘  └───────────────┘  └───────────────┘       │ │
│  └────────────────────────────────────────────────────────────────┘ │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

## Database Schema

### Schema Definition

```sql
-- migrations/001_initial.sql
-- TTAI Database Schema

-- Positions table (synced from TastyTrade)
CREATE TABLE IF NOT EXISTS positions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    underlying_symbol TEXT,
    quantity INTEGER NOT NULL,
    quantity_direction TEXT,  -- 'Long' or 'Short'
    average_open_price REAL,
    close_price REAL,
    mark REAL,
    instrument_type TEXT,     -- 'Equity', 'Option', etc.
    expiration_date TEXT,     -- ISO date for options
    strike_price REAL,        -- For options
    option_type TEXT,         -- 'Call' or 'Put'
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now')),
    UNIQUE(symbol)
);

-- Analysis results table
CREATE TABLE IF NOT EXISTS analyses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    analysis_type TEXT NOT NULL,  -- 'chart', 'options', 'full'
    result TEXT NOT NULL,          -- JSON blob
    recommendation TEXT,           -- 'strong_select', 'select', etc.
    score REAL,
    created_at TEXT DEFAULT (datetime('now')),
    expires_at TEXT                -- Optional expiration
);

CREATE INDEX idx_analyses_symbol ON analyses(symbol);
CREATE INDEX idx_analyses_created ON analyses(created_at);

-- Price alerts table
CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    alert_type TEXT NOT NULL,      -- 'price', 'delta', 'dte', etc.
    condition TEXT NOT NULL,       -- 'above', 'below', etc.
    threshold REAL NOT NULL,
    is_active INTEGER DEFAULT 1,
    triggered_at TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX idx_alerts_symbol ON alerts(symbol);
CREATE INDEX idx_alerts_active ON alerts(is_active);

-- Knowledge base chunks table
CREATE TABLE IF NOT EXISTS knowledge_chunks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_path TEXT NOT NULL,
    chunk_index INTEGER NOT NULL,
    content TEXT NOT NULL,
    metadata TEXT,                 -- JSON blob
    created_at TEXT DEFAULT (datetime('now')),
    UNIQUE(document_path, chunk_index)
);

-- Knowledge embeddings table (for sqlite-vec)
CREATE TABLE IF NOT EXISTS knowledge_embeddings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chunk_id INTEGER NOT NULL REFERENCES knowledge_chunks(id),
    embedding BLOB NOT NULL,       -- Vector stored as blob
    UNIQUE(chunk_id)
);

-- App settings table
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT DEFAULT (datetime('now'))
);

-- Migrations tracking
CREATE TABLE IF NOT EXISTS migrations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    applied_at TEXT DEFAULT (datetime('now'))
);
```

## Database Service

### Core Implementation

```python
# src/services/database.py
import aiosqlite
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

class DatabaseService:
    """
    Async SQLite database service.

    Provides all database operations for the TTAI application.
    """

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._connection: Optional[aiosqlite.Connection] = None

    @classmethod
    async def create(cls, db_path: Path) -> "DatabaseService":
        """Create and initialize the database service."""
        service = cls(db_path)
        await service._initialize()
        return service

    async def _initialize(self) -> None:
        """Initialize database connection and run migrations."""
        # Ensure parent directory exists
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        # Connect to database
        self._connection = await aiosqlite.connect(self.db_path)
        self._connection.row_factory = aiosqlite.Row

        # Enable foreign keys
        await self._connection.execute("PRAGMA foreign_keys = ON")

        # Run migrations
        await self._run_migrations()

        logger.info(f"Database initialized at {self.db_path}")

    async def _run_migrations(self) -> None:
        """Run pending database migrations."""
        migrations_dir = Path(__file__).parent.parent / "migrations"

        if not migrations_dir.exists():
            # Create initial schema inline if no migrations dir
            await self._create_initial_schema()
            return

        # Get applied migrations
        await self._connection.execute("""
            CREATE TABLE IF NOT EXISTS migrations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                applied_at TEXT DEFAULT (datetime('now'))
            )
        """)

        cursor = await self._connection.execute(
            "SELECT name FROM migrations ORDER BY name"
        )
        applied = {row["name"] for row in await cursor.fetchall()}

        # Apply new migrations
        for migration_file in sorted(migrations_dir.glob("*.sql")):
            name = migration_file.stem
            if name not in applied:
                logger.info(f"Applying migration: {name}")
                sql = migration_file.read_text()
                await self._connection.executescript(sql)
                await self._connection.execute(
                    "INSERT INTO migrations (name) VALUES (?)",
                    (name,)
                )
                await self._connection.commit()

    async def _create_initial_schema(self) -> None:
        """Create initial database schema."""
        await self._connection.executescript("""
            CREATE TABLE IF NOT EXISTS positions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL UNIQUE,
                underlying_symbol TEXT,
                quantity INTEGER NOT NULL,
                quantity_direction TEXT,
                average_open_price REAL,
                close_price REAL,
                mark REAL,
                instrument_type TEXT,
                expiration_date TEXT,
                strike_price REAL,
                option_type TEXT,
                created_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS analyses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                analysis_type TEXT NOT NULL,
                result TEXT NOT NULL,
                recommendation TEXT,
                score REAL,
                created_at TEXT DEFAULT (datetime('now')),
                expires_at TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_analyses_symbol ON analyses(symbol);
            CREATE INDEX IF NOT EXISTS idx_analyses_created ON analyses(created_at);

            CREATE TABLE IF NOT EXISTS alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                alert_type TEXT NOT NULL,
                condition TEXT NOT NULL,
                threshold REAL NOT NULL,
                is_active INTEGER DEFAULT 1,
                triggered_at TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            );
            CREATE INDEX IF NOT EXISTS idx_alerts_symbol ON alerts(symbol);
            CREATE INDEX IF NOT EXISTS idx_alerts_active ON alerts(is_active);

            CREATE TABLE IF NOT EXISTS knowledge_chunks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                document_path TEXT NOT NULL,
                chunk_index INTEGER NOT NULL,
                content TEXT NOT NULL,
                metadata TEXT,
                created_at TEXT DEFAULT (datetime('now')),
                UNIQUE(document_path, chunk_index)
            );

            CREATE TABLE IF NOT EXISTS knowledge_embeddings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chunk_id INTEGER NOT NULL REFERENCES knowledge_chunks(id),
                embedding BLOB NOT NULL,
                UNIQUE(chunk_id)
            );

            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TEXT DEFAULT (datetime('now'))
            );
        """)
        await self._connection.commit()

    async def close(self) -> None:
        """Close the database connection."""
        if self._connection:
            await self._connection.close()
            self._connection = None

    # Position operations

    async def sync_positions(self, positions: List[Dict[str, Any]]) -> None:
        """Sync positions from TastyTrade."""
        # Clear existing positions and insert new ones
        await self._connection.execute("DELETE FROM positions")

        for pos in positions:
            await self._connection.execute("""
                INSERT INTO positions (
                    symbol, underlying_symbol, quantity, quantity_direction,
                    average_open_price, close_price, mark, instrument_type,
                    expiration_date, strike_price, option_type
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                pos.get("symbol"),
                pos.get("underlying_symbol"),
                pos.get("quantity"),
                pos.get("quantity_direction"),
                pos.get("average_open_price"),
                pos.get("close_price"),
                pos.get("mark"),
                pos.get("instrument_type"),
                pos.get("expiration_date"),
                pos.get("strike_price"),
                pos.get("option_type"),
            ))

        await self._connection.commit()

    async def get_positions(self) -> List[Dict[str, Any]]:
        """Get all cached positions."""
        cursor = await self._connection.execute(
            "SELECT * FROM positions ORDER BY underlying_symbol, symbol"
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    # Analysis operations

    async def save_analysis(
        self,
        symbol: str,
        analysis_type: str,
        result: Dict[str, Any]
    ) -> int:
        """Save an analysis result."""
        cursor = await self._connection.execute("""
            INSERT INTO analyses (symbol, analysis_type, result, recommendation, score)
            VALUES (?, ?, ?, ?, ?)
        """, (
            symbol,
            analysis_type,
            json.dumps(result),
            result.get("recommendation"),
            result.get("score"),
        ))
        await self._connection.commit()
        return cursor.lastrowid

    async def get_recent_analyses(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Get recent analyses."""
        cursor = await self._connection.execute("""
            SELECT id, symbol, analysis_type, recommendation, score, created_at
            FROM analyses
            ORDER BY created_at DESC
            LIMIT ?
        """, (limit,))
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def get_analyses_by_symbol(self, symbol: str) -> List[Dict[str, Any]]:
        """Get analyses for a specific symbol."""
        cursor = await self._connection.execute("""
            SELECT * FROM analyses
            WHERE symbol = ?
            ORDER BY created_at DESC
            LIMIT 10
        """, (symbol,))
        rows = await cursor.fetchall()
        return [
            {**dict(row), "result": json.loads(row["result"])}
            for row in rows
        ]

    async def get_analysis(self, analysis_id: int) -> Optional[Dict[str, Any]]:
        """Get a specific analysis by ID."""
        cursor = await self._connection.execute(
            "SELECT * FROM analyses WHERE id = ?",
            (analysis_id,)
        )
        row = await cursor.fetchone()
        if row:
            return {**dict(row), "result": json.loads(row["result"])}
        return None

    # Alert operations

    async def create_alert(
        self,
        symbol: str,
        alert_type: str,
        condition: str,
        threshold: float
    ) -> int:
        """Create a new alert."""
        cursor = await self._connection.execute("""
            INSERT INTO alerts (symbol, alert_type, condition, threshold)
            VALUES (?, ?, ?, ?)
        """, (symbol, alert_type, condition, threshold))
        await self._connection.commit()
        return cursor.lastrowid

    async def get_active_alerts(self) -> List[Dict[str, Any]]:
        """Get all active alerts."""
        cursor = await self._connection.execute("""
            SELECT * FROM alerts
            WHERE is_active = 1
            ORDER BY created_at DESC
        """)
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def get_price_alerts(self) -> List[Dict[str, Any]]:
        """Get active price alerts."""
        cursor = await self._connection.execute("""
            SELECT * FROM alerts
            WHERE is_active = 1 AND alert_type = 'price'
            ORDER BY symbol
        """)
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def trigger_alert(self, alert_id: int) -> None:
        """Mark an alert as triggered."""
        await self._connection.execute("""
            UPDATE alerts
            SET is_active = 0, triggered_at = datetime('now')
            WHERE id = ?
        """, (alert_id,))
        await self._connection.commit()

    async def delete_alert(self, alert_id: int) -> bool:
        """Delete an alert."""
        cursor = await self._connection.execute(
            "DELETE FROM alerts WHERE id = ?",
            (alert_id,)
        )
        await self._connection.commit()
        return cursor.rowcount > 0

    # Settings operations

    async def get_setting(self, key: str, default: Any = None) -> Any:
        """Get a setting value."""
        cursor = await self._connection.execute(
            "SELECT value FROM settings WHERE key = ?",
            (key,)
        )
        row = await cursor.fetchone()
        if row:
            return json.loads(row["value"])
        return default

    async def set_setting(self, key: str, value: Any) -> None:
        """Set a setting value."""
        await self._connection.execute("""
            INSERT INTO settings (key, value, updated_at)
            VALUES (?, ?, datetime('now'))
            ON CONFLICT(key) DO UPDATE SET
                value = excluded.value,
                updated_at = excluded.updated_at
        """, (key, json.dumps(value)))
        await self._connection.commit()
```

## Encrypted Credential Storage

### Credential Manager

```python
# src/auth/credentials.py
from cryptography.fernet import Fernet
from pathlib import Path
import json
import os

class CredentialManager:
    """
    Manages encrypted credential storage.

    Uses Fernet symmetric encryption for storing sensitive data.
    Credentials file is protected with restrictive permissions on Unix.
    """

    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.key_file = data_dir / ".key"
        self.creds_file = data_dir / ".credentials"
        self._fernet: Optional[Fernet] = None

    @property
    def fernet(self) -> Fernet:
        """Get or create the Fernet instance."""
        if self._fernet is None:
            self._fernet = Fernet(self._get_or_create_key())
        return self._fernet

    def _get_or_create_key(self) -> bytes:
        """Get existing encryption key or create a new one."""
        if self.key_file.exists():
            return self.key_file.read_bytes()

        # Generate new key
        key = Fernet.generate_key()
        self.key_file.write_bytes(key)

        # Set restrictive permissions on Unix
        if os.name != 'nt':
            os.chmod(self.key_file, 0o600)

        return key

    def store_credentials(
        self,
        username: str,
        session_token: str,
        remember_token: Optional[str] = None,
        account_id: Optional[str] = None
    ) -> None:
        """
        Store encrypted credentials.

        Args:
            username: TastyTrade username
            session_token: Current session token
            remember_token: Optional remember-me token for auto-login
            account_id: Optional default account ID
        """
        data = {
            "username": username,
            "session_token": session_token,
            "remember_token": remember_token,
            "account_id": account_id,
            "stored_at": datetime.now().isoformat(),
        }

        encrypted = self.fernet.encrypt(json.dumps(data).encode())
        self.creds_file.write_bytes(encrypted)

        # Set restrictive permissions on Unix
        if os.name != 'nt':
            os.chmod(self.creds_file, 0o600)

    def load_credentials(self) -> Optional[Dict[str, str]]:
        """
        Load and decrypt stored credentials.

        Returns:
            Credentials dict or None if not found/invalid
        """
        if not self.creds_file.exists():
            return None

        try:
            encrypted = self.creds_file.read_bytes()
            decrypted = self.fernet.decrypt(encrypted)
            return json.loads(decrypted.decode())
        except Exception as e:
            # Invalid credentials, clear them
            logger.warning(f"Failed to load credentials: {e}")
            self.clear_credentials()
            return None

    def clear_credentials(self) -> None:
        """Remove stored credentials."""
        if self.creds_file.exists():
            self.creds_file.unlink()

    def has_credentials(self) -> bool:
        """Check if credentials are stored."""
        return self.creds_file.exists()
```

## Quote Cache with TTL

### In-Memory Cache Service

```python
# src/services/cache.py
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Optional, Dict
import threading

@dataclass
class CacheEntry:
    """A cached value with expiration."""
    value: Any
    expires_at: datetime

class CacheService:
    """
    Thread-safe in-memory cache with TTL support.

    Provides tiered caching for different data types:
    - Quotes: 60 second TTL
    - Option chains: 5 minute TTL
    - Analysis results: 15 minute TTL
    """

    # Default TTLs by data type
    TTL_QUOTES = 60           # 1 minute
    TTL_CHAINS = 300          # 5 minutes
    TTL_ANALYSIS = 900        # 15 minutes
    TTL_POSITIONS = 120       # 2 minutes

    def __init__(self, max_size: int = 1000):
        self._cache: Dict[str, CacheEntry] = {}
        self._lock = threading.Lock()
        self._max_size = max_size

    def get(self, key: str) -> Optional[Any]:
        """Get a value from cache if not expired."""
        with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                return None

            if datetime.now() > entry.expires_at:
                del self._cache[key]
                return None

            return entry.value

    def set(self, key: str, value: Any, ttl: int = 60) -> None:
        """Set a value with TTL in seconds."""
        with self._lock:
            # Evict if at capacity
            if len(self._cache) >= self._max_size:
                self._evict_expired()
                if len(self._cache) >= self._max_size:
                    oldest_key = next(iter(self._cache))
                    del self._cache[oldest_key]

            self._cache[key] = CacheEntry(
                value=value,
                expires_at=datetime.now() + timedelta(seconds=ttl)
            )

    def delete(self, key: str) -> bool:
        """Delete a key from cache."""
        with self._lock:
            if key in self._cache:
                del self._cache[key]
                return True
            return False

    def clear(self) -> None:
        """Clear all cached values."""
        with self._lock:
            self._cache.clear()

    def _evict_expired(self) -> None:
        """Remove all expired entries."""
        now = datetime.now()
        expired_keys = [
            key for key, entry in self._cache.items()
            if now > entry.expires_at
        ]
        for key in expired_keys:
            del self._cache[key]

    # Convenience methods for typed access

    def get_quote(self, symbol: str) -> Optional[Dict]:
        """Get cached quote."""
        return self.get(f"quote:{symbol}")

    def set_quote(self, symbol: str, quote: Dict) -> None:
        """Cache a quote."""
        self.set(f"quote:{symbol}", quote, self.TTL_QUOTES)

    def get_chain(self, symbol: str, expiration: str = None) -> Optional[Dict]:
        """Get cached option chain."""
        key = f"chain:{symbol}:{expiration or 'all'}"
        return self.get(key)

    def set_chain(self, symbol: str, chain: Dict, expiration: str = None) -> None:
        """Cache an option chain."""
        key = f"chain:{symbol}:{expiration or 'all'}"
        self.set(key, chain, self.TTL_CHAINS)

    def get_analysis(self, symbol: str, analysis_type: str) -> Optional[Dict]:
        """Get cached analysis."""
        return self.get(f"analysis:{symbol}:{analysis_type}")

    def set_analysis(
        self,
        symbol: str,
        analysis_type: str,
        result: Dict
    ) -> None:
        """Cache an analysis result."""
        self.set(f"analysis:{symbol}:{analysis_type}", result, self.TTL_ANALYSIS)

    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        with self._lock:
            now = datetime.now()
            valid_count = sum(
                1 for entry in self._cache.values()
                if now <= entry.expires_at
            )
            return {
                "total_entries": len(self._cache),
                "valid_entries": valid_count,
                "max_size": self._max_size,
            }
```

## Data Directory Structure

```
~/.ttai/
├── ttai.db              # Main SQLite database
├── .key                 # Fernet encryption key (600 permissions)
├── .credentials         # Encrypted TastyTrade credentials (600 permissions)
├── knowledge/           # Knowledge base documents
│   ├── options/
│   │   └── strategies/
│   │       ├── csp.md
│   │       ├── covered_call.md
│   │       └── spreads.md
│   └── research/
│       └── ...
├── exports/             # Exported reports and data
│   └── analysis_2024-01-15.json
└── logs/                # Application logs
    ├── ttai-20240115.log
    └── ttai-20240114.log
```

## Migration System

```python
# src/services/migrations.py
from pathlib import Path
import aiosqlite
import logging

logger = logging.getLogger(__name__)

MIGRATIONS = [
    # Migration 001: Initial schema
    """
    -- Initial tables created inline in DatabaseService._create_initial_schema
    """,

    # Migration 002: Add watchlists
    """
    CREATE TABLE IF NOT EXISTS watchlists (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE,
        symbols TEXT NOT NULL,  -- JSON array
        created_at TEXT DEFAULT (datetime('now')),
        updated_at TEXT DEFAULT (datetime('now'))
    );
    """,

    # Migration 003: Add transaction history
    """
    CREATE TABLE IF NOT EXISTS transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        transaction_id TEXT NOT NULL UNIQUE,
        symbol TEXT NOT NULL,
        transaction_type TEXT NOT NULL,
        transaction_sub_type TEXT,
        description TEXT,
        executed_at TEXT,
        value REAL,
        net_value REAL,
        created_at TEXT DEFAULT (datetime('now'))
    );
    CREATE INDEX IF NOT EXISTS idx_transactions_symbol ON transactions(symbol);
    CREATE INDEX IF NOT EXISTS idx_transactions_date ON transactions(executed_at);
    """,
]

async def run_migrations(db: aiosqlite.Connection) -> None:
    """Run all pending migrations."""
    # Ensure migrations table exists
    await db.execute("""
        CREATE TABLE IF NOT EXISTS schema_version (
            version INTEGER PRIMARY KEY,
            applied_at TEXT DEFAULT (datetime('now'))
        )
    """)

    # Get current version
    cursor = await db.execute(
        "SELECT MAX(version) as version FROM schema_version"
    )
    row = await cursor.fetchone()
    current_version = row[0] if row[0] else 0

    # Apply pending migrations
    for i, migration in enumerate(MIGRATIONS, start=1):
        if i > current_version:
            logger.info(f"Applying migration {i}")
            await db.executescript(migration)
            await db.execute(
                "INSERT INTO schema_version (version) VALUES (?)",
                (i,)
            )
            await db.commit()

    logger.info(f"Database at version {len(MIGRATIONS)}")
```

## Cross-References

- [MCP Server Design](./01-mcp-server-design.md) - Database integration
- [Python Server](./03-python-server.md) - Service architecture
- [Knowledge Base](./07-knowledge-base.md) - Document and embedding storage
- [Background Tasks](./06-background-tasks.md) - Position sync
