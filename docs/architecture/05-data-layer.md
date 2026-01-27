# Data Layer Design

## Overview

The data layer provides caching, persistence, and real-time data distribution for the TastyTrade AI system. It consists of Redis for caching and real-time data, and PostgreSQL for persistent storage.

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                           MCP Server                                │
│                    (TypeScript - Cache Reads)                       │
└─────────────────────────────────┬───────────────────────────────────┘
                                  │
            ┌─────────────────────┼─────────────────────┐
            ▼                     │                     ▼
┌───────────────────┐             │         ┌───────────────────┐
│   Redis Cache     │             │         │   PostgreSQL      │
│                   │             │         │                   │
│ - Hot: 5s TTL     │             │         │ - Analysis history│
│ - Warm: 1-5m TTL  │             │         │ - Screener results│
│ - Cold: 1h-1d TTL │             │         │ - Alert configs   │
│ - Sessions: 24h   │             │         │ - Watchlists      │
│ - Pub/Sub         │             │         │ - Trade journal   │
└───────────────────┘             │         └───────────────────┘
            ▲                     │                     ▲
            │                     │                     │
            └─────────────────────┼─────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────┐
│                        Python Workers                               │
│              (Cache Writes, DB Writes, Streaming)                   │
└─────────────────────────────────────────────────────────────────────┘
```

## Redis Caching Strategy

### Cache Tiers

| Tier     | TTL            | Use Case               | Examples                 |
| -------- | -------------- | ---------------------- | ------------------------ |
| Hot      | 5 seconds      | Real-time data         | Quotes, last price       |
| Warm     | 1-5 minutes    | Frequently accessed    | Option chains, Greeks    |
| Cold     | 1 hour - 1 day | Slow-changing data     | Financials, company info |
| Session  | 24 hours       | Auth tokens            | TastyTrade sessions      |
| Analysis | 15-30 minutes  | Expensive computations | Agent results            |

### Key Naming Convention

```
ttai:{tier}:{type}:{identifier}

Examples:
ttai:hot:quote:AAPL
ttai:warm:chain:AAPL
ttai:warm:greeks:AAPL240119P00145000
ttai:cold:financials:AAPL
ttai:cold:company:AAPL
ttai:session:tastytrade:user123
ttai:analysis:chart:AAPL:daily:standard
ttai:analysis:full:AAPL
```

### Redis Client Configuration

```typescript
// src/cache/redis.ts
import { createClient, RedisClientType } from "redis";

export interface CacheConfig {
  url: string;
  prefix: string;
}

export class RedisCache {
  private client: RedisClientType;
  private prefix: string;

  constructor(config: CacheConfig) {
    this.prefix = config.prefix;
    this.client = createClient({
      url: config.url,
      socket: {
        reconnectStrategy: (retries) => Math.min(retries * 100, 5000),
      },
    });

    this.client.on("error", (err) => console.error("Redis error:", err));
  }

  async connect(): Promise<void> {
    await this.client.connect();
  }

  async disconnect(): Promise<void> {
    await this.client.quit();
  }

  // Key helpers
  private key(parts: string[]): string {
    return `${this.prefix}${parts.join(":")}`;
  }

  // Hot tier (5s TTL)
  async setHot<T>(type: string, id: string, data: T): Promise<void> {
    const key = this.key(["hot", type, id]);
    await this.client.setEx(key, 5, JSON.stringify(data));
  }

  async getHot<T>(type: string, id: string): Promise<T | null> {
    const key = this.key(["hot", type, id]);
    const data = await this.client.get(key);
    return data ? JSON.parse(data) : null;
  }

  // Warm tier (configurable TTL, default 60s)
  async setWarm<T>(
    type: string,
    id: string,
    data: T,
    ttl: number = 60,
  ): Promise<void> {
    const key = this.key(["warm", type, id]);
    await this.client.setEx(key, ttl, JSON.stringify(data));
  }

  async getWarm<T>(type: string, id: string): Promise<T | null> {
    const key = this.key(["warm", type, id]);
    const data = await this.client.get(key);
    return data ? JSON.parse(data) : null;
  }

  // Cold tier (configurable TTL, default 1 hour)
  async setCold<T>(
    type: string,
    id: string,
    data: T,
    ttl: number = 3600,
  ): Promise<void> {
    const key = this.key(["cold", type, id]);
    await this.client.setEx(key, ttl, JSON.stringify(data));
  }

  async getCold<T>(type: string, id: string): Promise<T | null> {
    const key = this.key(["cold", type, id]);
    const data = await this.client.get(key);
    return data ? JSON.parse(data) : null;
  }

  // Analysis cache (15-30 min TTL)
  async setAnalysis<T>(
    analysisType: string,
    symbol: string,
    params: string,
    data: T,
    ttl: number = 900,
  ): Promise<void> {
    const key = this.key(["analysis", analysisType, symbol, params]);
    await this.client.setEx(key, ttl, JSON.stringify(data));
  }

  async getAnalysis<T>(
    analysisType: string,
    symbol: string,
    params: string,
  ): Promise<T | null> {
    const key = this.key(["analysis", analysisType, symbol, params]);
    const data = await this.client.get(key);
    return data ? JSON.parse(data) : null;
  }

  // Session cache (24h TTL)
  async setSession<T>(type: string, id: string, data: T): Promise<void> {
    const key = this.key(["session", type, id]);
    await this.client.setEx(key, 86400, JSON.stringify(data));
  }

  async getSession<T>(type: string, id: string): Promise<T | null> {
    const key = this.key(["session", type, id]);
    const data = await this.client.get(key);
    return data ? JSON.parse(data) : null;
  }

  // Generic get with fallback
  async getOrSet<T>(
    tier: "hot" | "warm" | "cold",
    type: string,
    id: string,
    fetcher: () => Promise<T>,
    ttl?: number,
  ): Promise<T> {
    const getter =
      tier === "hot"
        ? this.getHot
        : tier === "warm"
          ? this.getWarm
          : this.getCold;
    const setter =
      tier === "hot"
        ? this.setHot
        : tier === "warm"
          ? this.setWarm
          : this.setCold;

    const cached = await getter.call(this, type, id);
    if (cached) return cached as T;

    const data = await fetcher();
    await setter.call(this, type, id, data, ttl);
    return data;
  }

  // Invalidation
  async invalidate(pattern: string): Promise<void> {
    const fullPattern = this.key([pattern]);
    const keys = await this.client.keys(fullPattern);
    if (keys.length > 0) {
      await this.client.del(keys);
    }
  }

  // Pub/Sub
  async publish(channel: string, message: unknown): Promise<void> {
    await this.client.publish(
      `${this.prefix}${channel}`,
      JSON.stringify(message),
    );
  }

  async subscribe(
    channel: string,
    callback: (message: unknown) => void,
  ): Promise<void> {
    const subscriber = this.client.duplicate();
    await subscriber.connect();

    await subscriber.subscribe(`${this.prefix}${channel}`, (message) => {
      callback(JSON.parse(message));
    });
  }
}

export async function createRedisClient(
  config?: Partial<CacheConfig>,
): Promise<RedisCache> {
  const cache = new RedisCache({
    url: config?.url || process.env.REDIS_URL || "redis://localhost:6379",
    prefix: config?.prefix || "ttai:",
  });
  await cache.connect();
  return cache;
}
```

### Python Redis Client

```python
# db/redis.py
import json
import os
from typing import TypeVar, Optional, Callable, Awaitable, Any
import redis.asyncio as redis

T = TypeVar("T")

class RedisCache:
    """Async Redis cache client for Python workers."""

    def __init__(self, url: Optional[str] = None, prefix: str = "ttai:"):
        self.url = url or os.environ.get("REDIS_URL", "redis://localhost:6379")
        self.prefix = prefix
        self._client: Optional[redis.Redis] = None

    async def connect(self) -> None:
        self._client = await redis.from_url(self.url)

    async def disconnect(self) -> None:
        if self._client:
            await self._client.close()

    @property
    def client(self) -> redis.Redis:
        if self._client is None:
            raise RuntimeError("Redis client not connected")
        return self._client

    def _key(self, *parts: str) -> str:
        return f"{self.prefix}{':'.join(parts)}"

    # Hot tier
    async def set_hot(self, type_: str, id_: str, data: Any) -> None:
        key = self._key("hot", type_, id_)
        await self.client.setex(key, 5, json.dumps(data, default=str))

    async def get_hot(self, type_: str, id_: str) -> Optional[Any]:
        key = self._key("hot", type_, id_)
        data = await self.client.get(key)
        return json.loads(data) if data else None

    # Warm tier
    async def set_warm(
        self, type_: str, id_: str, data: Any, ttl: int = 60
    ) -> None:
        key = self._key("warm", type_, id_)
        await self.client.setex(key, ttl, json.dumps(data, default=str))

    async def get_warm(self, type_: str, id_: str) -> Optional[Any]:
        key = self._key("warm", type_, id_)
        data = await self.client.get(key)
        return json.loads(data) if data else None

    # Cold tier
    async def set_cold(
        self, type_: str, id_: str, data: Any, ttl: int = 3600
    ) -> None:
        key = self._key("cold", type_, id_)
        await self.client.setex(key, ttl, json.dumps(data, default=str))

    async def get_cold(self, type_: str, id_: str) -> Optional[Any]:
        key = self._key("cold", type_, id_)
        data = await self.client.get(key)
        return json.loads(data) if data else None

    # Analysis cache
    async def set_analysis(
        self,
        analysis_type: str,
        symbol: str,
        params: str,
        data: Any,
        ttl: int = 900,
    ) -> None:
        key = self._key("analysis", analysis_type, symbol, params)
        await self.client.setex(key, ttl, json.dumps(data, default=str))

    async def get_analysis(
        self, analysis_type: str, symbol: str, params: str
    ) -> Optional[Any]:
        key = self._key("analysis", analysis_type, symbol, params)
        data = await self.client.get(key)
        return json.loads(data) if data else None

    # Generic get-or-set
    async def get_or_set(
        self,
        tier: str,
        type_: str,
        id_: str,
        fetcher: Callable[[], Awaitable[T]],
        ttl: Optional[int] = None,
    ) -> T:
        if tier == "hot":
            cached = await self.get_hot(type_, id_)
        elif tier == "warm":
            cached = await self.get_warm(type_, id_)
        else:
            cached = await self.get_cold(type_, id_)

        if cached is not None:
            return cached

        data = await fetcher()

        if tier == "hot":
            await self.set_hot(type_, id_, data)
        elif tier == "warm":
            await self.set_warm(type_, id_, data, ttl or 60)
        else:
            await self.set_cold(type_, id_, data, ttl or 3600)

        return data

    # Pub/Sub
    async def publish(self, channel: str, message: Any) -> None:
        await self.client.publish(
            f"{self.prefix}{channel}",
            json.dumps(message, default=str),
        )

    async def subscribe(
        self,
        channel: str,
        callback: Callable[[Any], Awaitable[None]],
    ) -> None:
        pubsub = self.client.pubsub()
        await pubsub.subscribe(f"{self.prefix}{channel}")

        async for message in pubsub.listen():
            if message["type"] == "message":
                data = json.loads(message["data"])
                await callback(data)
```

## Real-Time Data Flow via Redis Pub/Sub

### Streaming Worker

```python
# workers/streaming_worker.py
import asyncio
from db.redis import RedisCache
from services.tastytrade import TastyTradeClient

class StreamingWorker:
    """Worker that streams real-time data and publishes to Redis."""

    def __init__(self, redis: RedisCache, tt_client: TastyTradeClient):
        self.redis = redis
        self.tt_client = tt_client
        self._symbols: set[str] = set()
        self._shutdown = False

    async def add_symbols(self, symbols: list[str]) -> None:
        """Add symbols to the streaming set."""
        self._symbols.update(symbols)

    async def remove_symbols(self, symbols: list[str]) -> None:
        """Remove symbols from the streaming set."""
        self._symbols -= set(symbols)

    async def run(self) -> None:
        """Main streaming loop."""
        while not self._shutdown:
            if not self._symbols:
                await asyncio.sleep(1)
                continue

            try:
                # Stream quotes for all symbols
                async for quote in self.tt_client.stream_quotes(list(self._symbols)):
                    # Update hot cache
                    await self.redis.set_hot("quote", quote.symbol, {
                        "symbol": quote.symbol,
                        "price": quote.price,
                        "bid": quote.bid,
                        "ask": quote.ask,
                        "timestamp": quote.timestamp,
                    })

                    # Publish to channel
                    await self.redis.publish(f"quotes:{quote.symbol}", {
                        "symbol": quote.symbol,
                        "price": quote.price,
                    })

            except Exception as e:
                print(f"Streaming error: {e}")
                await asyncio.sleep(5)  # Reconnect delay

    async def shutdown(self) -> None:
        self._shutdown = True
```

### MCP Server Subscription

```typescript
// src/resources/market-data.ts
import { RedisCache } from "../cache/redis";

export class MarketDataResource {
  constructor(private cache: RedisCache) {}

  async subscribeToQuotes(
    symbols: string[],
    callback: (quote: QuoteData) => void,
  ): Promise<void> {
    for (const symbol of symbols) {
      await this.cache.subscribe(`quotes:${symbol}`, (data) => {
        callback(data as QuoteData);
      });
    }
  }

  async getLatestQuote(symbol: string): Promise<QuoteData | null> {
    return this.cache.getHot<QuoteData>("quote", symbol);
  }
}
```

## PostgreSQL Schema

### Database Structure

```sql
-- migrations/20240115_000001_initial_schema.sql

-- Analysis history
CREATE TABLE analysis_history (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    symbol VARCHAR(10) NOT NULL,
    analysis_type VARCHAR(50) NOT NULL,  -- 'chart', 'options', 'research', 'full'
    params JSONB,
    result JSONB NOT NULL,
    recommendation VARCHAR(20),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_analysis_symbol ON analysis_history(symbol);
CREATE INDEX idx_analysis_type ON analysis_history(analysis_type);
CREATE INDEX idx_analysis_created ON analysis_history(created_at);

-- Screener results
CREATE TABLE screener_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    screener_id VARCHAR(100),
    screener_type VARCHAR(50) NOT NULL,  -- 'stock', 'csp'
    params JSONB NOT NULL,
    candidates_found INTEGER NOT NULL,
    results JSONB NOT NULL,
    run_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_screener_id ON screener_runs(screener_id);
CREATE INDEX idx_screener_run_at ON screener_runs(run_at);

-- Alert configurations
CREATE TABLE alert_configs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(100) NOT NULL,
    alert_type VARCHAR(50) NOT NULL,  -- 'price', 'news', 'earnings', 'assignment_risk'
    symbol VARCHAR(10),
    conditions JSONB NOT NULL,
    channels JSONB NOT NULL,  -- ['discord', 'email', 'slack']
    enabled BOOLEAN DEFAULT true,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_alert_symbol ON alert_configs(symbol);
CREATE INDEX idx_alert_type ON alert_configs(alert_type);
CREATE INDEX idx_alert_enabled ON alert_configs(enabled);

-- Alert history (triggered alerts)
CREATE TABLE alert_history (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    config_id UUID REFERENCES alert_configs(id),
    symbol VARCHAR(10),
    alert_type VARCHAR(50) NOT NULL,
    message TEXT NOT NULL,
    details JSONB,
    channels_notified JSONB,
    triggered_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_alert_history_config ON alert_history(config_id);
CREATE INDEX idx_alert_history_triggered ON alert_history(triggered_at);

-- Watchlists
CREATE TABLE watchlists (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(100) NOT NULL UNIQUE,
    description TEXT,
    symbols JSONB NOT NULL DEFAULT '[]',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Saved screeners
CREATE TABLE saved_screeners (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(100) NOT NULL UNIQUE,
    description TEXT,
    screener_type VARCHAR(50) NOT NULL,
    criteria JSONB NOT NULL,
    schedule VARCHAR(100),  -- cron expression if scheduled
    notify_channels JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Trade journal (for tracking actual trades)
CREATE TABLE trade_journal (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    symbol VARCHAR(10) NOT NULL,
    strategy VARCHAR(100) NOT NULL,
    legs JSONB NOT NULL,
    entry_date DATE NOT NULL,
    entry_price DECIMAL(10, 2) NOT NULL,
    exit_date DATE,
    exit_price DECIMAL(10, 2),
    pnl DECIMAL(10, 2),
    pnl_percent DECIMAL(6, 2),
    notes TEXT,
    analysis_id UUID REFERENCES analysis_history(id),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_trade_symbol ON trade_journal(symbol);
CREATE INDEX idx_trade_entry ON trade_journal(entry_date);
```

### Migration Strategy

Using Alembic (Python) since Python activities are the primary data producers.

#### Alembic Configuration

```python
# db/migrations/env.py
import asyncio
from logging.config import fileConfig
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config
from alembic import context

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = None  # Use raw SQL migrations

def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()

def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()

async def run_async_migrations() -> None:
    """Run migrations in 'online' mode."""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()

def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

#### Migration Naming Convention

```
YYYYMMDD_HHMMSS_description.py

Examples:
20240115_000001_initial_schema.py
20240115_120000_add_screener_tables.py
20240116_090000_add_trade_journal.py
```

#### Running Migrations

```bash
# Create a new migration
alembic revision -m "add_new_table"

# Run migrations
alembic upgrade head

# Rollback
alembic downgrade -1
```

### Python Database Client

```python
# db/postgres.py
import os
from typing import Optional, List, Dict, Any
from contextlib import asynccontextmanager
import asyncpg

class PostgresClient:
    """Async PostgreSQL client for Python workers."""

    def __init__(self, dsn: Optional[str] = None):
        self.dsn = dsn or os.environ.get(
            "DATABASE_URL",
            "postgresql://ttai:ttai@localhost:5432/ttai"
        )
        self._pool: Optional[asyncpg.Pool] = None

    async def connect(self) -> None:
        self._pool = await asyncpg.create_pool(
            self.dsn,
            min_size=2,
            max_size=10,
        )

    async def disconnect(self) -> None:
        if self._pool:
            await self._pool.close()

    @property
    def pool(self) -> asyncpg.Pool:
        if self._pool is None:
            raise RuntimeError("Database not connected")
        return self._pool

    @asynccontextmanager
    async def connection(self):
        async with self.pool.acquire() as conn:
            yield conn

    # Analysis history
    async def save_analysis(
        self,
        symbol: str,
        analysis_type: str,
        params: Dict[str, Any],
        result: Dict[str, Any],
        recommendation: Optional[str] = None,
    ) -> str:
        async with self.connection() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO analysis_history (symbol, analysis_type, params, result, recommendation)
                VALUES ($1, $2, $3, $4, $5)
                RETURNING id
                """,
                symbol,
                analysis_type,
                params,
                result,
                recommendation,
            )
            return str(row["id"])

    async def get_analysis_history(
        self,
        symbol: str,
        analysis_type: Optional[str] = None,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        async with self.connection() as conn:
            if analysis_type:
                rows = await conn.fetch(
                    """
                    SELECT * FROM analysis_history
                    WHERE symbol = $1 AND analysis_type = $2
                    ORDER BY created_at DESC
                    LIMIT $3
                    """,
                    symbol,
                    analysis_type,
                    limit,
                )
            else:
                rows = await conn.fetch(
                    """
                    SELECT * FROM analysis_history
                    WHERE symbol = $1
                    ORDER BY created_at DESC
                    LIMIT $2
                    """,
                    symbol,
                    limit,
                )
            return [dict(row) for row in rows]

    # Screener results
    async def save_screener_run(
        self,
        screener_id: Optional[str],
        screener_type: str,
        params: Dict[str, Any],
        results: List[Dict[str, Any]],
    ) -> str:
        async with self.connection() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO screener_runs (screener_id, screener_type, params, candidates_found, results)
                VALUES ($1, $2, $3, $4, $5)
                RETURNING id
                """,
                screener_id,
                screener_type,
                params,
                len(results),
                results,
            )
            return str(row["id"])

    # Watchlists
    async def get_watchlist(self, name: str) -> Optional[Dict[str, Any]]:
        async with self.connection() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM watchlists WHERE name = $1",
                name,
            )
            return dict(row) if row else None

    async def update_watchlist(
        self,
        name: str,
        symbols: List[str],
    ) -> None:
        async with self.connection() as conn:
            await conn.execute(
                """
                INSERT INTO watchlists (name, symbols)
                VALUES ($1, $2)
                ON CONFLICT (name) DO UPDATE
                SET symbols = $2, updated_at = NOW()
                """,
                name,
                symbols,
            )

    # Alert configs
    async def get_enabled_alerts(
        self,
        alert_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        async with self.connection() as conn:
            if alert_type:
                rows = await conn.fetch(
                    """
                    SELECT * FROM alert_configs
                    WHERE enabled = true AND alert_type = $1
                    """,
                    alert_type,
                )
            else:
                rows = await conn.fetch(
                    "SELECT * FROM alert_configs WHERE enabled = true"
                )
            return [dict(row) for row in rows]

    async def save_alert_history(
        self,
        config_id: Optional[str],
        symbol: Optional[str],
        alert_type: str,
        message: str,
        details: Dict[str, Any],
        channels_notified: List[str],
    ) -> str:
        async with self.connection() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO alert_history (config_id, symbol, alert_type, message, details, channels_notified)
                VALUES ($1, $2, $3, $4, $5, $6)
                RETURNING id
                """,
                config_id,
                symbol,
                alert_type,
                message,
                details,
                channels_notified,
            )
            return str(row["id"])
```

### TypeScript Database Access

For reads and alert/watchlist writes from the MCP server:

```typescript
// src/db/postgres.ts
import { Pool, PoolClient } from "pg";

export class PostgresClient {
  private pool: Pool;

  constructor(connectionString?: string) {
    this.pool = new Pool({
      connectionString:
        connectionString ||
        process.env.DATABASE_URL ||
        "postgresql://ttai:ttai@localhost:5432/ttai",
      max: 10,
      idleTimeoutMillis: 30000,
    });
  }

  async query<T>(text: string, params?: unknown[]): Promise<T[]> {
    const result = await this.pool.query(text, params);
    return result.rows;
  }

  async queryOne<T>(text: string, params?: unknown[]): Promise<T | null> {
    const result = await this.pool.query(text, params);
    return result.rows[0] || null;
  }

  // Watchlists
  async getWatchlist(name: string): Promise<Watchlist | null> {
    return this.queryOne<Watchlist>(
      "SELECT * FROM watchlists WHERE name = $1",
      [name],
    );
  }

  async listWatchlists(): Promise<Watchlist[]> {
    return this.query<Watchlist>("SELECT * FROM watchlists ORDER BY name");
  }

  async updateWatchlist(name: string, symbols: string[]): Promise<void> {
    await this.query(
      `INSERT INTO watchlists (name, symbols)
       VALUES ($1, $2)
       ON CONFLICT (name) DO UPDATE
       SET symbols = $2, updated_at = NOW()`,
      [name, JSON.stringify(symbols)],
    );
  }

  // Alert configs
  async getAlertConfigs(enabled?: boolean): Promise<AlertConfig[]> {
    if (enabled !== undefined) {
      return this.query<AlertConfig>(
        "SELECT * FROM alert_configs WHERE enabled = $1",
        [enabled],
      );
    }
    return this.query<AlertConfig>("SELECT * FROM alert_configs");
  }

  async createAlertConfig(config: Partial<AlertConfig>): Promise<string> {
    const result = await this.queryOne<{ id: string }>(
      `INSERT INTO alert_configs (name, alert_type, symbol, conditions, channels)
       VALUES ($1, $2, $3, $4, $5)
       RETURNING id`,
      [
        config.name,
        config.alertType,
        config.symbol,
        JSON.stringify(config.conditions),
        JSON.stringify(config.channels),
      ],
    );
    return result!.id;
  }

  // Analysis history (read-only from TypeScript)
  async getAnalysisHistory(
    symbol: string,
    limit: number = 10,
  ): Promise<AnalysisRecord[]> {
    return this.query<AnalysisRecord>(
      `SELECT * FROM analysis_history
       WHERE symbol = $1
       ORDER BY created_at DESC
       LIMIT $2`,
      [symbol, limit],
    );
  }

  // Screener results (read-only from TypeScript)
  async getScreenerRuns(
    screenerId?: string,
    limit: number = 10,
  ): Promise<ScreenerRun[]> {
    if (screenerId) {
      return this.query<ScreenerRun>(
        `SELECT * FROM screener_runs
         WHERE screener_id = $1
         ORDER BY run_at DESC
         LIMIT $2`,
        [screenerId, limit],
      );
    }
    return this.query<ScreenerRun>(
      `SELECT * FROM screener_runs
       ORDER BY run_at DESC
       LIMIT $1`,
      [limit],
    );
  }

  async close(): Promise<void> {
    await this.pool.end();
  }
}

// Types
interface Watchlist {
  id: string;
  name: string;
  description?: string;
  symbols: string[];
  createdAt: Date;
  updatedAt: Date;
}

interface AlertConfig {
  id: string;
  name: string;
  alertType: string;
  symbol?: string;
  conditions: Record<string, unknown>;
  channels: string[];
  enabled: boolean;
  createdAt: Date;
  updatedAt: Date;
}

interface AnalysisRecord {
  id: string;
  symbol: string;
  analysisType: string;
  params: Record<string, unknown>;
  result: Record<string, unknown>;
  recommendation?: string;
  createdAt: Date;
}

interface ScreenerRun {
  id: string;
  screenerId?: string;
  screenerType: string;
  params: Record<string, unknown>;
  candidatesFound: number;
  results: Record<string, unknown>[];
  runAt: Date;
}
```

## Data Access Patterns

### Read Path (MCP Server)

```typescript
// Example: Get quote with cache fallback
async function getQuote(symbol: string): Promise<QuoteData> {
  // 1. Try hot cache first
  const cached = await redis.getHot<QuoteData>("quote", symbol);
  if (cached) return cached;

  // 2. Start a Temporal workflow to fetch fresh data
  const handle = await temporal.workflow.start(FetchQuoteWorkflow, {
    taskQueue: "ttai-queue",
    workflowId: `fetch-quote-${symbol}`,
    args: [symbol],
  });

  return await handle.result();
}
```

### Write Path (Python Workers)

```python
# Example: Save analysis result
async def save_analysis_result(
    symbol: str,
    analysis_type: str,
    result: dict,
) -> None:
    # 1. Save to PostgreSQL for persistence
    await db.save_analysis(
        symbol=symbol,
        analysis_type=analysis_type,
        params={},
        result=result,
        recommendation=result.get("recommendation"),
    )

    # 2. Cache in Redis for fast access
    cache_key = f"{analysis_type}:{symbol}"
    await redis.set_analysis(analysis_type, symbol, "latest", result)

    # 3. Publish update notification
    await redis.publish(f"analysis:{symbol}", {
        "type": analysis_type,
        "recommendation": result.get("recommendation"),
    })
```

### Cache Invalidation

```python
# Invalidate on significant events
async def on_earnings_released(symbol: str) -> None:
    # Invalidate all warm/cold cache for the symbol
    await redis.invalidate(f"warm:*:{symbol}")
    await redis.invalidate(f"cold:*:{symbol}")
    await redis.invalidate(f"analysis:*:{symbol}:*")
```
