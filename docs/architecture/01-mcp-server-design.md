# MCP Server Design

## Overview

The MCP (Model Context Protocol) server is the primary interface between AI clients (Claude Code, Claude Desktop, etc.) and the TastyTrade AI system. Built in TypeScript/Node.js, it exposes tools, resources, and prompts that enable AI-powered trading analysis.

## Server Architecture

```
┌────────────────────────────────────────────────────────────────────┐
│                         MCP Server (Node.js)                       │
├────────────────────────────────────────────────────────────────────┤
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐              │
│  │   Transport  │  │    Cache     │  │   Temporal   │              │
│  │   Manager    │  │   Manager    │  │    Client    │              │
│  │  (stdio/SSE) │  │   (Redis)    │  │              │              │
│  └──────────────┘  └──────────────┘  └──────────────┘              │
│           │               │               │                        │
│           └───────────────┴───────────────┘                        │
│                           │                                        │
│  ┌────────────────────────┴────────────────────────┐               │
│  │              Tool Router                        │               │
│  │  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌────────┐ │               │
│  │  │ Stock   │ │ Options │ │ Agent   │ │Screener│ │               │
│  │  │ Tools   │ │ Tools   │ │ Tools   │ │ Tools  │ │               │
│  │  └─────────┘ └─────────┘ └─────────┘ └────────┘ │               │
│  └─────────────────────────────────────────────────┘               │
│                           │                                        │
│  ┌────────────────────────┴────────────────────────┐               │
│  │              Handler Layer                      │               │
│  │  ┌─────────┐ ┌─────────┐ ┌─────────┐            │               │
│  │  │Resources│ │ Prompts │ │Sampling │            │               │
│  │  └─────────┘ └─────────┘ └─────────┘            │               │
│  └─────────────────────────────────────────────────┘               │
└────────────────────────────────────────────────────────────────────┘
```

## Project Structure

```
mcp-server/
├── src/
│   ├── index.ts              # Entry point, server initialization
│   ├── server.ts             # MCP server setup and configuration
│   ├── config.ts             # Environment configuration
│   │
│   ├── transport/
│   │   ├── index.ts          # Transport factory
│   │   ├── stdio.ts          # stdio transport for local use
│   │   └── sse.ts            # SSE transport for remote access
│   │
│   ├── tools/
│   │   ├── index.ts          # Tool registry and router
│   │   ├── stock.ts          # Stock data tools
│   │   ├── options.ts        # Options data tools
│   │   ├── financials.ts     # Financial metrics tools
│   │   ├── news.ts           # News and SEC filing tools
│   │   ├── portfolio.ts      # Portfolio management tools
│   │   ├── screener.ts       # Screener tools
│   │   └── agents.ts         # AI agent invocation tools
│   │
│   ├── resources/
│   │   ├── index.ts          # Resource registry
│   │   ├── watchlist.ts      # Watchlist resources
│   │   ├── positions.ts      # Position resources
│   │   ├── market-data.ts    # Market data resources
│   │   └── alerts.ts         # Alert resources
│   │
│   ├── prompts/
│   │   ├── index.ts          # Prompt registry
│   │   ├── csp-analysis.ts   # CSP analysis prompts
│   │   ├── strategy.ts       # Options strategy prompts
│   │   └── playbook.ts       # Playbook lookup prompts
│   │
│   ├── temporal/
│   │   ├── client.ts         # Temporal client wrapper
│   │   ├── workflows.ts      # Workflow definitions (client-side)
│   │   └── types.ts          # Shared workflow/activity types
│   │
│   ├── cache/
│   │   ├── redis.ts          # Redis client and utilities
│   │   └── tiers.ts          # Cache tier definitions
│   │
│   └── utils/
│       ├── errors.ts         # Error handling utilities
│       ├── validation.ts     # Input validation
│       └── formatting.ts     # Response formatting
│
├── package.json
├── tsconfig.json
└── Dockerfile
```

## Transport Configuration

### stdio Transport (Local)

Default transport for local Claude Code integration:

```typescript
// src/transport/stdio.ts
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";

export function createStdioTransport(): StdioServerTransport {
  return new StdioServerTransport();
}
```

Configuration in Claude Code (`~/.claude/claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "tastytrade-ai": {
      "command": "node",
      "args": ["/path/to/mcp-server/dist/index.js"],
      "env": {
        "REDIS_URL": "redis://localhost:6379",
        "TEMPORAL_ADDRESS": "localhost:7233"
      }
    }
  }
}
```

### SSE Transport (Remote)

For remote access via HTTPS (e.g., cloud deployment):

```typescript
// src/transport/sse.ts
import { SSEServerTransport } from "@modelcontextprotocol/sdk/server/sse.js";
import express from "express";

export function createSSEServer(port: number = 3000) {
  const app = express();

  app.get("/sse", async (req, res) => {
    const transport = new SSEServerTransport("/messages", res);
    await server.connect(transport);
  });

  app.post("/messages", async (req, res) => {
    // Handle incoming messages
  });

  return app.listen(port);
}
```

## Tool Specifications

### Stock Data Tools

#### `get_quote`

Get real-time quote for a single symbol.

```typescript
{
  name: "get_quote",
  description: "Get real-time stock quote including price, volume, and daily change",
  inputSchema: {
    type: "object",
    properties: {
      symbol: {
        type: "string",
        description: "Stock ticker symbol (e.g., 'AAPL')"
      }
    },
    required: ["symbol"]
  }
}
```

**Response:**

```typescript
interface QuoteResponse {
  symbol: string;
  price: number;
  bid: number;
  ask: number;
  volume: number;
  avgVolume: number;
  change: number;
  changePercent: number;
  high: number;
  low: number;
  open: number;
  previousClose: number;
  marketCap: number;
  timestamp: string;
}
```

#### `get_quotes_batch`

Get quotes for multiple symbols in one call.

```typescript
{
  name: "get_quotes_batch",
  description: "Get real-time quotes for multiple symbols",
  inputSchema: {
    type: "object",
    properties: {
      symbols: {
        type: "array",
        items: { type: "string" },
        description: "List of ticker symbols",
        maxItems: 50
      }
    },
    required: ["symbols"]
  }
}
```

#### `get_price_history`

Get historical OHLCV data for charting and analysis.

```typescript
{
  name: "get_price_history",
  description: "Get historical price data (OHLCV) for technical analysis",
  inputSchema: {
    type: "object",
    properties: {
      symbol: { type: "string" },
      interval: {
        type: "string",
        enum: ["1m", "5m", "15m", "1h", "1d", "1wk", "1mo"],
        default: "1d"
      },
      period: {
        type: "string",
        enum: ["1d", "5d", "1mo", "3mo", "6mo", "1y", "2y", "5y"],
        default: "6mo"
      }
    },
    required: ["symbol"]
  }
}
```

**Response:**

```typescript
interface PriceHistoryResponse {
  symbol: string;
  interval: string;
  bars: Array<{
    timestamp: string;
    open: number;
    high: number;
    low: number;
    close: number;
    volume: number;
  }>;
}
```

#### `get_company_info`

Get company profile and basic information.

```typescript
{
  name: "get_company_info",
  description: "Get company profile including sector, industry, and description",
  inputSchema: {
    type: "object",
    properties: {
      symbol: { type: "string" }
    },
    required: ["symbol"]
  }
}
```

### Options Data Tools

#### `get_option_chain`

Get full options chain for a symbol.

```typescript
{
  name: "get_option_chain",
  description: "Get options chain with all available expirations and strikes",
  inputSchema: {
    type: "object",
    properties: {
      symbol: { type: "string" },
      expiration: {
        type: "string",
        description: "Specific expiration date (YYYY-MM-DD) or 'all'"
      },
      strikeRange: {
        type: "object",
        properties: {
          minStrike: { type: "number" },
          maxStrike: { type: "number" }
        }
      },
      optionType: {
        type: "string",
        enum: ["call", "put", "both"],
        default: "both"
      }
    },
    required: ["symbol"]
  }
}
```

**Response:**

```typescript
interface OptionChainResponse {
  symbol: string;
  underlyingPrice: number;
  expirations: Array<{
    date: string;
    dte: number;
    strikes: Array<{
      strike: number;
      call?: OptionContract;
      put?: OptionContract;
    }>;
  }>;
}

interface OptionContract {
  symbol: string;
  bid: number;
  ask: number;
  mid: number;
  last: number;
  volume: number;
  openInterest: number;
  iv: number;
  delta: number;
  gamma: number;
  theta: number;
  vega: number;
}
```

#### `get_option_quote`

Get detailed quote for a specific option contract.

```typescript
{
  name: "get_option_quote",
  description: "Get detailed quote for a specific option contract",
  inputSchema: {
    type: "object",
    properties: {
      optionSymbol: {
        type: "string",
        description: "OCC option symbol (e.g., 'AAPL240119C00150000')"
      }
    },
    required: ["optionSymbol"]
  }
}
```

#### `get_greeks`

Get Greeks for an option or calculate theoretical Greeks.

```typescript
{
  name: "get_greeks",
  description: "Get or calculate option Greeks (delta, gamma, theta, vega, rho)",
  inputSchema: {
    type: "object",
    properties: {
      optionSymbol: { type: "string" },
      // Or calculate from parameters:
      underlyingPrice: { type: "number" },
      strike: { type: "number" },
      dte: { type: "number" },
      iv: { type: "number" },
      optionType: { type: "string", enum: ["call", "put"] },
      riskFreeRate: { type: "number", default: 0.05 }
    }
  }
}
```

#### `calculate_iv_hv`

Compare implied volatility to historical volatility.

```typescript
{
  name: "calculate_iv_hv",
  description: "Calculate IV/HV ratio and IV percentile for a symbol",
  inputSchema: {
    type: "object",
    properties: {
      symbol: { type: "string" },
      period: {
        type: "number",
        description: "Historical volatility period in days",
        default: 20
      }
    },
    required: ["symbol"]
  }
}
```

**Response:**

```typescript
interface IVHVResponse {
  symbol: string;
  iv: number; // Current ATM implied volatility
  hv: number; // Historical volatility
  ivHvRatio: number; // IV / HV
  ivPercentile: number; // IV percentile over past year
  ivRank: number; // IV rank over past year
}
```

### Financial Metrics Tools

#### `get_financials`

Get key financial metrics and ratios.

```typescript
{
  name: "get_financials",
  description: "Get financial metrics including P/E, EPS, revenue, margins",
  inputSchema: {
    type: "object",
    properties: {
      symbol: { type: "string" },
      period: {
        type: "string",
        enum: ["quarterly", "annual"],
        default: "quarterly"
      }
    },
    required: ["symbol"]
  }
}
```

#### `get_earnings`

Get earnings history and upcoming earnings dates.

```typescript
{
  name: "get_earnings",
  description: "Get earnings history, estimates, and next earnings date",
  inputSchema: {
    type: "object",
    properties: {
      symbol: { type: "string" }
    },
    required: ["symbol"]
  }
}
```

**Response:**

```typescript
interface EarningsResponse {
  symbol: string;
  nextEarningsDate: string | null;
  daysToEarnings: number | null;
  history: Array<{
    date: string;
    epsEstimate: number;
    epsActual: number;
    surprise: number;
    surprisePercent: number;
  }>;
}
```

#### `get_short_interest`

Get short interest data.

```typescript
{
  name: "get_short_interest",
  description: "Get short interest, days to cover, and short ratio",
  inputSchema: {
    type: "object",
    properties: {
      symbol: { type: "string" }
    },
    required: ["symbol"]
  }
}
```

#### `get_analyst_ratings`

Get analyst ratings and price targets.

```typescript
{
  name: "get_analyst_ratings",
  description: "Get analyst ratings, price targets, and recommendations",
  inputSchema: {
    type: "object",
    properties: {
      symbol: { type: "string" }
    },
    required: ["symbol"]
  }
}
```

### News Tools

#### `get_news`

Get recent news for a symbol.

```typescript
{
  name: "get_news",
  description: "Get recent news articles for a symbol",
  inputSchema: {
    type: "object",
    properties: {
      symbol: { type: "string" },
      limit: {
        type: "number",
        default: 10,
        maximum: 50
      }
    },
    required: ["symbol"]
  }
}
```

#### `search_news`

Search news across all symbols.

```typescript
{
  name: "search_news",
  description: "Search news articles by keyword or topic",
  inputSchema: {
    type: "object",
    properties: {
      query: { type: "string" },
      symbols: {
        type: "array",
        items: { type: "string" },
        description: "Optional: filter by symbols"
      },
      days: {
        type: "number",
        default: 7,
        description: "Number of days to search back"
      }
    },
    required: ["query"]
  }
}
```

#### `get_sec_filings`

Get SEC filings for a company.

```typescript
{
  name: "get_sec_filings",
  description: "Get recent SEC filings (10-K, 10-Q, 8-K, etc.)",
  inputSchema: {
    type: "object",
    properties: {
      symbol: { type: "string" },
      filingTypes: {
        type: "array",
        items: {
          type: "string",
          enum: ["10-K", "10-Q", "8-K", "4", "SC 13G", "DEF 14A"]
        }
      },
      limit: { type: "number", default: 10 }
    },
    required: ["symbol"]
  }
}
```

### Portfolio Tools

#### `get_positions`

Get current positions from TastyTrade account.

```typescript
{
  name: "get_positions",
  description: "Get current positions including stocks and options",
  inputSchema: {
    type: "object",
    properties: {
      accountId: {
        type: "string",
        description: "TastyTrade account ID (uses default if not specified)"
      },
      type: {
        type: "string",
        enum: ["all", "stocks", "options"],
        default: "all"
      }
    }
  }
}
```

**Response:**

```typescript
interface PositionsResponse {
  accountId: string;
  positions: Array<{
    symbol: string;
    quantity: number;
    averageCost: number;
    currentPrice: number;
    marketValue: number;
    dayPnl: number;
    totalPnl: number;
    pnlPercent: number;
    // For options:
    optionType?: "call" | "put";
    strike?: number;
    expiration?: string;
    dte?: number;
  }>;
  summary: {
    totalValue: number;
    dayPnl: number;
    totalPnl: number;
  };
}
```

#### `get_balances`

Get account balances and buying power.

```typescript
{
  name: "get_balances",
  description: "Get account balances, margin, and buying power",
  inputSchema: {
    type: "object",
    properties: {
      accountId: { type: "string" }
    }
  }
}
```

#### `get_transactions`

Get transaction history.

```typescript
{
  name: "get_transactions",
  description: "Get transaction history for the account",
  inputSchema: {
    type: "object",
    properties: {
      accountId: { type: "string" },
      startDate: { type: "string", format: "date" },
      endDate: { type: "string", format: "date" },
      type: {
        type: "string",
        enum: ["all", "trades", "transfers", "dividends"]
      }
    }
  }
}
```

#### `get_pnl`

Get P&L analysis.

```typescript
{
  name: "get_pnl",
  description: "Get profit/loss analysis for positions or time period",
  inputSchema: {
    type: "object",
    properties: {
      accountId: { type: "string" },
      period: {
        type: "string",
        enum: ["day", "week", "month", "ytd", "all"],
        default: "day"
      },
      symbol: {
        type: "string",
        description: "Optional: filter by symbol"
      }
    }
  }
}
```

### Screener Tools

#### `run_screener`

Run a stock screener with criteria.

```typescript
{
  name: "run_screener",
  description: "Screen stocks based on technical and fundamental criteria",
  inputSchema: {
    type: "object",
    properties: {
      criteria: {
        type: "object",
        properties: {
          minPrice: { type: "number" },
          maxPrice: { type: "number" },
          minVolume: { type: "number" },
          minMarketCap: { type: "number" },
          maxMarketCap: { type: "number" },
          sector: { type: "string" },
          industry: { type: "string" },
          // Technical filters
          aboveSMA20: { type: "boolean" },
          aboveSMA50: { type: "boolean" },
          aboveSMA200: { type: "boolean" },
          rsiRange: {
            type: "object",
            properties: {
              min: { type: "number" },
              max: { type: "number" }
            }
          }
        }
      },
      sortBy: {
        type: "string",
        enum: ["volume", "price", "change", "marketCap"],
        default: "volume"
      },
      limit: { type: "number", default: 50 }
    },
    required: ["criteria"]
  }
}
```

#### `run_csp_screener`

Run specialized cash-secured put screener.

```typescript
{
  name: "run_csp_screener",
  description: "Screen for optimal cash-secured put opportunities",
  inputSchema: {
    type: "object",
    properties: {
      maxPrice: {
        type: "number",
        description: "Maximum stock price (for capital efficiency)"
      },
      minRocWeekly: {
        type: "number",
        description: "Minimum weekly return on capital (%)",
        default: 0.5
      },
      maxDelta: {
        type: "number",
        description: "Maximum delta (probability of assignment)",
        default: 0.3
      },
      dteRange: {
        type: "object",
        properties: {
          min: { type: "number", default: 14 },
          max: { type: "number", default: 45 }
        }
      },
      excludeEarnings: {
        type: "boolean",
        description: "Exclude stocks with earnings within DTE",
        default: true
      },
      tiers: {
        type: "array",
        items: {
          type: "string",
          enum: ["high_risk", "medium_risk", "low_risk"]
        },
        default: ["medium_risk"]
      }
    }
  }
}
```

#### `save_screener`

Save a screener configuration for reuse.

```typescript
{
  name: "save_screener",
  description: "Save a screener configuration for later use",
  inputSchema: {
    type: "object",
    properties: {
      name: { type: "string" },
      description: { type: "string" },
      type: { type: "string", enum: ["stock", "csp"] },
      criteria: { type: "object" }
    },
    required: ["name", "type", "criteria"]
  }
}
```

#### `list_screeners`

List saved screener configurations.

```typescript
{
  name: "list_screeners",
  description: "List saved screener configurations",
  inputSchema: {
    type: "object",
    properties: {
      type: {
        type: "string",
        enum: ["all", "stock", "csp"],
        default: "all"
      }
    }
  }
}
```

### AI Agent Tools

#### `analyze_chart`

Run chart analysis agent.

```typescript
{
  name: "analyze_chart",
  description: "Run AI chart analysis to identify trends, support/resistance, and patterns",
  inputSchema: {
    type: "object",
    properties: {
      symbol: { type: "string" },
      timeframe: {
        type: "string",
        enum: ["intraday", "daily", "weekly"],
        default: "daily"
      },
      analysisDepth: {
        type: "string",
        enum: ["quick", "standard", "deep"],
        default: "standard"
      }
    },
    required: ["symbol"]
  }
}
```

**Response:**

```typescript
interface ChartAnalysisResponse {
  symbol: string;
  recommendation: "bullish" | "bearish" | "neutral" | "reject";
  trendDirection: "up" | "down" | "sideways";
  trendQuality: "strong" | "moderate" | "weak";
  supportLevels: Array<{
    price: number;
    strength: "strong" | "moderate" | "weak";
    type: string; // e.g., "fib_61.8", "prior_low", "sma_50"
  }>;
  resistanceLevels: Array<{
    price: number;
    strength: "strong" | "moderate" | "weak";
    type: string;
  }>;
  fibConfluenceZones: Array<{
    price: number;
    levels: string[]; // e.g., ["38.2%", "50%"]
  }>;
  extensionRisk: "low" | "moderate" | "high";
  chartNotes: string;
  toolCallsMade: number;
}
```

#### `analyze_options`

Run options analysis agent.

```typescript
{
  name: "analyze_options",
  description: "Run AI options analysis to find optimal strikes and expirations",
  inputSchema: {
    type: "object",
    properties: {
      symbol: { type: "string" },
      strategy: {
        type: "string",
        enum: ["csp", "covered_call", "spread", "iron_condor"],
        default: "csp"
      },
      chartContext: {
        type: "object",
        description: "Optional chart analysis context for informed strike selection"
      },
      constraints: {
        type: "object",
        properties: {
          maxDelta: { type: "number" },
          minRoc: { type: "number" },
          dteRange: {
            type: "object",
            properties: {
              min: { type: "number" },
              max: { type: "number" }
            }
          }
        }
      }
    },
    required: ["symbol"]
  }
}
```

**Response:**

```typescript
interface OptionsAnalysisResponse {
  symbol: string;
  recommendation: "select" | "reject";
  strategy: string;
  bestStrike: number;
  bestExpiration: string;
  dte: number;
  premium: number;
  weeklyRoc: number;
  annualizedRoc: number;
  delta: number;
  gamma: number;
  theta: number;
  ivHvRatio: number;
  liquidityScore: "excellent" | "good" | "fair" | "poor";
  alternativeStrikes: Array<{
    strike: number;
    expiration: string;
    roc: number;
    delta: number;
  }>;
  rationale: string;
  optionsNotes: string;
  toolCallsMade: number;
}
```

#### `analyze_research`

Run research analysis agent.

```typescript
{
  name: "analyze_research",
  description: "Run AI research analysis for fundamentals and news",
  inputSchema: {
    type: "object",
    properties: {
      symbol: { type: "string" },
      focus: {
        type: "array",
        items: {
          type: "string",
          enum: ["news", "financials", "earnings", "short_interest", "analyst_ratings"]
        },
        default: ["news", "earnings"]
      }
    },
    required: ["symbol"]
  }
}
```

#### `run_full_analysis`

Run complete multi-agent analysis pipeline.

```typescript
{
  name: "run_full_analysis",
  description: "Run complete AI analysis pipeline (chart -> options -> research)",
  inputSchema: {
    type: "object",
    properties: {
      symbol: { type: "string" },
      strategy: {
        type: "string",
        enum: ["csp", "covered_call"],
        default: "csp"
      }
    },
    required: ["symbol"]
  }
}
```

**Response:**

```typescript
interface FullAnalysisResponse {
  symbol: string;
  overallRecommendation: "strong_select" | "select" | "neutral" | "reject";
  chartAnalysis: ChartAnalysisResponse;
  optionsAnalysis: OptionsAnalysisResponse;
  researchAnalysis: ResearchAnalysisResponse;
  synthesizedRationale: string;
  riskFactors: string[];
  suggestedPosition: {
    strategy: string;
    strike: number;
    expiration: string;
    quantity: number;
    maxRisk: number;
    targetReturn: number;
  };
}
```

#### `find_csp_opportunities`

Find best CSP opportunities across the market.

```typescript
{
  name: "find_csp_opportunities",
  description: "Screen and analyze market to find top CSP opportunities",
  inputSchema: {
    type: "object",
    properties: {
      maxPrice: { type: "number", default: 100 },
      minRocWeekly: { type: "number", default: 0.5 },
      maxPicks: { type: "number", default: 5 },
      excludeEarnings: { type: "boolean", default: true },
      verbose: { type: "boolean", default: false }
    }
  }
}
```

## Resource Specifications

### Watchlist Resources

```typescript
// URI: watchlist://default
// URI: watchlist://{name}

interface WatchlistResource {
  uri: string;
  name: string;
  mimeType: "application/json";
  description: string;
}

interface WatchlistContent {
  name: string;
  symbols: string[];
  createdAt: string;
  updatedAt: string;
}
```

### Position Resources

```typescript
// URI: positions://current
// URI: positions://{accountId}

interface PositionsResource {
  uri: string;
  name: string;
  mimeType: "application/json";
  description: string;
}
```

### Market Data Resources

```typescript
// URI: market_data://quote/{symbol}
// URI: market_data://chain/{symbol}

interface MarketDataResource {
  uri: string;
  name: string;
  mimeType: "application/json";
  description: string;
}
```

### Alert Resources

```typescript
// URI: alerts://active
// URI: alerts://history

interface AlertsResource {
  uri: string;
  name: string;
  mimeType: "application/json";
  description: string;
}

interface AlertContent {
  id: string;
  type: "price" | "news" | "earnings" | "assignment_risk";
  symbol: string;
  condition: string;
  triggered: boolean;
  triggeredAt?: string;
  message?: string;
}
```

## Prompt Templates

### CSP Analysis Prompt

```typescript
{
  name: "csp_analysis",
  description: "Analyze a symbol for cash-secured put selling",
  arguments: [
    {
      name: "symbol",
      description: "Stock ticker to analyze",
      required: true
    },
    {
      name: "maxCapital",
      description: "Maximum capital to deploy",
      required: false
    }
  ]
}
```

**Template:**

```
Analyze {symbol} for cash-secured put selling opportunity.

Consider:
1. Technical setup (trend, support levels, extension risk)
2. Options metrics (IV/HV, premium, delta, liquidity)
3. Fundamental factors (earnings, news, short interest)

{#if maxCapital}
Maximum capital available: ${maxCapital}
{/if}

Provide a recommendation with specific strike and expiration if appropriate.
```

### Options Strategy Prompt

```typescript
{
  name: "options_strategy",
  description: "Get strategy recommendation for a given outlook",
  arguments: [
    {
      name: "symbol",
      description: "Stock ticker",
      required: true
    },
    {
      name: "outlook",
      description: "Market outlook (bullish, bearish, neutral, volatile)",
      required: true
    },
    {
      name: "timeHorizon",
      description: "Time horizon for the trade",
      required: false
    }
  ]
}
```

### Risk Assessment Prompt

```typescript
{
  name: "risk_assessment",
  description: "Assess risk for existing or proposed position",
  arguments: [
    {
      name: "position",
      description: "Position details (symbol, strategy, strikes, etc.)",
      required: true
    }
  ]
}
```

### Playbook Lookup Prompt

```typescript
{
  name: "playbook_lookup",
  description: "Look up strategy from options playbook",
  arguments: [
    {
      name: "scenario",
      description: "Market scenario or strategy name",
      required: true
    }
  ]
}
```

## Tool-to-Temporal Bridge Pattern

Tools that require long-running operations or Python activities are routed through Temporal:

```typescript
// src/tools/agents.ts
import { TemporalClient } from "../temporal/client";
import { AnalysisWorkflow } from "../temporal/workflows";

export async function analyzeChart(
  client: TemporalClient,
  params: { symbol: string; timeframe: string; analysisDepth: string },
): Promise<ChartAnalysisResponse> {
  // Start Temporal workflow
  const handle = await client.workflow.start(AnalysisWorkflow, {
    taskQueue: "analysis-queue",
    workflowId: `chart-analysis-${params.symbol}-${Date.now()}`,
    args: [
      {
        type: "chart",
        symbol: params.symbol,
        timeframe: params.timeframe,
        depth: params.analysisDepth,
      },
    ],
  });

  // Wait for result with timeout
  const result = await handle.result();
  return result as ChartAnalysisResponse;
}
```

## Error Handling

### Error Response Format

```typescript
interface ToolError {
  error: {
    code: string;
    message: string;
    details?: Record<string, unknown>;
  };
}

// Error codes
const ErrorCodes = {
  INVALID_SYMBOL: "INVALID_SYMBOL",
  RATE_LIMITED: "RATE_LIMITED",
  NOT_AUTHENTICATED: "NOT_AUTHENTICATED",
  MARKET_CLOSED: "MARKET_CLOSED",
  WORKFLOW_FAILED: "WORKFLOW_FAILED",
  TIMEOUT: "TIMEOUT",
  INTERNAL_ERROR: "INTERNAL_ERROR",
} as const;
```

### Error Handling Utility

```typescript
// src/utils/errors.ts
export function handleToolError(error: unknown): ToolError {
  if (error instanceof TemporalError) {
    return {
      error: {
        code: "WORKFLOW_FAILED",
        message: error.message,
        details: { workflowId: error.workflowId },
      },
    };
  }

  if (error instanceof RateLimitError) {
    return {
      error: {
        code: "RATE_LIMITED",
        message: "Rate limit exceeded, please retry later",
        details: { retryAfter: error.retryAfter },
      },
    };
  }

  // ... handle other error types

  return {
    error: {
      code: "INTERNAL_ERROR",
      message: "An unexpected error occurred",
    },
  };
}
```

## Response Formatting

### Standard Response Wrapper

```typescript
// src/utils/formatting.ts
export function formatToolResponse<T>(data: T): {
  content: Array<{ type: "text"; text: string }>;
} {
  return {
    content: [
      {
        type: "text",
        text: JSON.stringify(data, null, 2),
      },
    ],
  };
}

export function formatResourceResponse<T>(data: T): {
  contents: Array<{ uri: string; mimeType: string; text: string }>;
} {
  return {
    contents: [
      {
        uri: "...",
        mimeType: "application/json",
        text: JSON.stringify(data),
      },
    ],
  };
}
```

## Server Initialization

```typescript
// src/index.ts
import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { createStdioTransport } from "./transport/stdio";
import { registerTools } from "./tools";
import { registerResources } from "./resources";
import { registerPrompts } from "./prompts";
import { createTemporalClient } from "./temporal/client";
import { createRedisClient } from "./cache/redis";

async function main() {
  // Initialize dependencies
  const redis = await createRedisClient();
  const temporal = await createTemporalClient();

  // Create MCP server
  const server = new Server(
    {
      name: "tastytrade-ai",
      version: "1.0.0",
    },
    {
      capabilities: {
        tools: {},
        resources: {},
        prompts: {},
      },
    },
  );

  // Register handlers
  registerTools(server, { redis, temporal });
  registerResources(server, { redis });
  registerPrompts(server);

  // Connect transport
  const transport = createStdioTransport();
  await server.connect(transport);

  console.error("TastyTrade AI MCP server running on stdio");
}

main().catch(console.error);
```

## Configuration

```typescript
// src/config.ts
export interface Config {
  redis: {
    url: string;
    prefix: string;
  };
  temporal: {
    address: string;
    namespace: string;
    taskQueue: string;
  };
  tastytrade: {
    clientSecret?: string;
    refreshToken?: string;
  };
  server: {
    transport: "stdio" | "sse";
    port?: number;
  };
}

export function loadConfig(): Config {
  return {
    redis: {
      url: process.env.REDIS_URL || "redis://localhost:6379",
      prefix: process.env.REDIS_PREFIX || "ttai:",
    },
    temporal: {
      address: process.env.TEMPORAL_ADDRESS || "localhost:7233",
      namespace: process.env.TEMPORAL_NAMESPACE || "default",
      taskQueue: process.env.TEMPORAL_TASK_QUEUE || "ttai-queue",
    },
    tastytrade: {
      clientSecret: process.env.TT_CLIENT_SECRET,
      refreshToken: process.env.TT_REFRESH_TOKEN,
    },
    server: {
      transport: (process.env.MCP_TRANSPORT as "stdio" | "sse") || "stdio",
      port: process.env.MCP_PORT ? parseInt(process.env.MCP_PORT) : 3000,
    },
  };
}
```
