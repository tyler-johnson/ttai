# AI Agent System

## Overview

The AI agent system provides intelligent analysis of trading opportunities through a hierarchy of specialized agents running in Cloudflare Python Workers. Using LiteLLM for provider-agnostic LLM access (Anthropic, OpenAI, Google, Bedrock, Azure, etc.), agents analyze charts, options, and research data to generate trading recommendations.

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                     Cloudflare Python Workers                        │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ┌────────────────────────────────────────────────────────────────┐ │
│  │                  Orchestrator Agent                             │ │
│  │              (Synthesis & Final Recommendation)                 │ │
│  └──────────────────────────┬─────────────────────────────────────┘ │
│                             │                                        │
│         ┌───────────────────┼───────────────────┐                   │
│         ▼                   ▼                   ▼                   │
│  ┌────────────┐     ┌────────────┐     ┌────────────┐              │
│  │   Chart    │     │  Options   │     │  Research  │              │
│  │  Analyst   │     │  Analyst   │     │  Analyst   │              │
│  └─────┬──────┘     └─────┬──────┘     └─────┬──────┘              │
│        │                  │                  │                      │
│        └──────────────────┼──────────────────┘                      │
│                           ▼                                         │
│  ┌────────────────────────────────────────────────────────────────┐ │
│  │                       Tool Executor                             │ │
│  │  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐              │ │
│  │  │ Quotes  │ │ Options │ │  News   │ │Technical│              │ │
│  │  │  Tool   │ │  Chain  │ │  Tool   │ │ Analysis│              │ │
│  │  └─────────┘ └─────────┘ └─────────┘ └─────────┘              │ │
│  └────────────────────────────────────────────────────────────────┘ │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
                    ┌─────────────────┐
                    │    LiteLLM      │
                    │  (LLM Router)   │
                    └────────┬────────┘
                             │
         ┌───────────────────┼───────────────────┐
         ▼                   ▼                   ▼
   ┌───────────┐      ┌───────────┐      ┌───────────┐
   │ Anthropic │      │  OpenAI   │      │  Google   │
   │  Claude   │      │  GPT-4o   │      │  Gemini   │
   └───────────┘      └───────────┘      └───────────┘
```

## LiteLLM Integration

### Provider-Agnostic LLM Access

LiteLLM provides a unified interface for multiple LLM providers:

```python
# src/agents/llm.py
import litellm
from typing import List, Dict, Any, Optional

# Default model - can be overridden via environment
DEFAULT_MODEL = "anthropic/claude-sonnet-4-20250514"

async def completion(
    messages: List[Dict[str, str]],
    model: Optional[str] = None,
    tools: Optional[List[Dict]] = None,
    temperature: float = 0.7,
    max_tokens: int = 4096,
) -> Dict[str, Any]:
    """
    Make an LLM completion request via LiteLLM.

    Args:
        messages: Chat messages in OpenAI format
        model: Model string (e.g., "anthropic/claude-sonnet-4-20250514")
        tools: Tool definitions for function calling
        temperature: Sampling temperature
        max_tokens: Maximum tokens to generate

    Returns:
        LLM response with choices and usage
    """
    response = await litellm.acompletion(
        model=model or DEFAULT_MODEL,
        messages=messages,
        tools=tools,
        temperature=temperature,
        max_tokens=max_tokens,
    )

    return response
```

### Model String Format

LiteLLM uses a `provider/model` format:

```python
# Anthropic models
"anthropic/claude-sonnet-4-20250514"
"anthropic/claude-opus-4-20250514"

# OpenAI models
"openai/gpt-4o"
"openai/gpt-4-turbo"

# Google models
"gemini/gemini-1.5-pro"
"gemini/gemini-2.0-flash"

# AWS Bedrock
"bedrock/anthropic.claude-3-sonnet"

# Azure OpenAI
"azure/gpt-4o"
```

### Environment Configuration

LiteLLM reads API keys from standard environment variables:

```bash
# Anthropic
ANTHROPIC_API_KEY=sk-ant-...

# OpenAI
OPENAI_API_KEY=sk-...

# Google
GOOGLE_API_KEY=...

# AWS Bedrock
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
AWS_REGION_NAME=us-east-1

# Azure OpenAI
AZURE_API_KEY=...
AZURE_API_BASE=https://your-resource.openai.azure.com/
AZURE_API_VERSION=2024-02-15-preview
```

## Agent Implementation

### Base Agent Class

```python
# src/agents/base.py
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from abc import ABC, abstractmethod
import json

@dataclass
class AgentConfig:
    model: str = "anthropic/claude-sonnet-4-20250514"
    temperature: float = 0.7
    max_tokens: int = 4096
    max_tool_calls: int = 10

class BaseAgent(ABC):
    """Base class for all AI agents."""

    def __init__(self, env, config: Optional[AgentConfig] = None):
        self.env = env
        self.config = config or AgentConfig()
        self.tool_calls_made = 0

    @property
    @abstractmethod
    def system_prompt(self) -> str:
        """Agent's system prompt."""
        pass

    @property
    @abstractmethod
    def tools(self) -> List[Dict]:
        """Available tools for this agent."""
        pass

    async def run(self, user_message: str, context: Dict = None) -> Dict[str, Any]:
        """Execute the agent's analysis loop."""
        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": self._format_message(user_message, context)},
        ]

        while self.tool_calls_made < self.config.max_tool_calls:
            response = await completion(
                messages=messages,
                model=self.config.model,
                tools=self.tools,
                temperature=self.config.temperature,
                max_tokens=self.config.max_tokens,
            )

            assistant_message = response.choices[0].message

            # Check if agent wants to call tools
            if assistant_message.tool_calls:
                messages.append(assistant_message.model_dump())

                # Execute each tool call
                for tool_call in assistant_message.tool_calls:
                    result = await self._execute_tool(
                        tool_call.function.name,
                        json.loads(tool_call.function.arguments),
                    )

                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": json.dumps(result),
                    })

                    self.tool_calls_made += 1
            else:
                # Agent finished - parse final response
                return self._parse_response(assistant_message.content)

        return {"error": "Max tool calls exceeded", "tool_calls_made": self.tool_calls_made}

    async def _execute_tool(self, name: str, arguments: Dict) -> Any:
        """Execute a tool and return the result."""
        tool_fn = self._get_tool_function(name)
        if tool_fn:
            return await tool_fn(**arguments)
        return {"error": f"Unknown tool: {name}"}

    @abstractmethod
    def _get_tool_function(self, name: str):
        """Get the function for a tool by name."""
        pass

    def _format_message(self, message: str, context: Dict = None) -> str:
        """Format user message with optional context."""
        if context:
            context_str = json.dumps(context, indent=2)
            return f"{message}\n\nContext:\n{context_str}"
        return message

    @abstractmethod
    def _parse_response(self, content: str) -> Dict[str, Any]:
        """Parse agent's final response into structured output."""
        pass
```

### Chart Analyst Agent

```python
# src/agents/chart_analyst.py
from agents.base import BaseAgent, AgentConfig
from typing import List, Dict, Any
import json

CHART_ANALYST_PROMPT = """You are an expert technical analyst specializing in identifying
optimal entry points for options trades. Your analysis focuses on:

1. TREND ANALYSIS
   - Identify primary trend direction and quality
   - Look for higher highs/higher lows (uptrend) or lower highs/lower lows (downtrend)
   - Assess trend strength and momentum

2. SUPPORT/RESISTANCE
   - Find key support levels for potential put strike placement
   - Identify resistance levels that may cap upside
   - Note confluence zones where multiple levels align

3. FIBONACCI ANALYSIS
   - Apply Fibonacci retracements from significant swings
   - Identify retracement levels (38.2%, 50%, 61.8%)
   - Look for Fibonacci confluence with other support

4. EXTENSION RISK
   - Assess if price is extended from moving averages
   - Check RSI for overbought/oversold conditions
   - Evaluate risk of mean reversion

Your output should be a JSON object with your analysis.
"""

class ChartAnalyst(BaseAgent):
    """Agent specialized in technical chart analysis."""

    @property
    def system_prompt(self) -> str:
        return CHART_ANALYST_PROMPT

    @property
    def tools(self) -> List[Dict]:
        return [
            {
                "type": "function",
                "function": {
                    "name": "get_price_history",
                    "description": "Get historical OHLCV price data for a symbol",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "symbol": {"type": "string", "description": "Stock ticker symbol"},
                            "interval": {
                                "type": "string",
                                "enum": ["5m", "15m", "1h", "1d", "1wk"],
                                "description": "Time interval for bars"
                            },
                            "period": {
                                "type": "string",
                                "enum": ["1d", "5d", "1mo", "3mo", "6mo", "1y"],
                                "description": "Historical period"
                            },
                        },
                        "required": ["symbol"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "calculate_indicators",
                    "description": "Calculate technical indicators (SMA, EMA, RSI, Bollinger Bands)",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "symbol": {"type": "string"},
                            "indicators": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "List of indicators: sma_20, sma_50, sma_200, ema_9, rsi_14, bollinger"
                            },
                        },
                        "required": ["symbol", "indicators"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "find_support_resistance",
                    "description": "Find support and resistance levels",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "symbol": {"type": "string"},
                            "lookback_days": {"type": "integer", "default": 60},
                        },
                        "required": ["symbol"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "calculate_fibonacci",
                    "description": "Calculate Fibonacci retracement levels from a price swing",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "symbol": {"type": "string"},
                            "swing_type": {
                                "type": "string",
                                "enum": ["recent", "major"],
                                "description": "Type of swing to analyze"
                            },
                        },
                        "required": ["symbol"],
                    },
                },
            },
        ]

    def _get_tool_function(self, name: str):
        tool_map = {
            "get_price_history": self._get_price_history,
            "calculate_indicators": self._calculate_indicators,
            "find_support_resistance": self._find_support_resistance,
            "calculate_fibonacci": self._calculate_fibonacci,
        }
        return tool_map.get(name)

    async def _get_price_history(self, symbol: str, interval: str = "1d", period: str = "6mo"):
        """Fetch price history from market data service."""
        from handlers.market_data import fetch_market_data
        return await fetch_market_data(self.env, symbol, interval, period)

    async def _calculate_indicators(self, symbol: str, indicators: List[str]):
        """Calculate technical indicators."""
        from analysis.indicators import calculate_sma, calculate_ema, calculate_rsi, calculate_bollinger_bands

        # Get price data
        data = await self._get_price_history(symbol)
        closes = [bar["close"] for bar in data["bars"]]

        results = {}
        for ind in indicators:
            if ind.startswith("sma_"):
                period = int(ind.split("_")[1])
                results[ind] = calculate_sma(closes, period)[-1]
            elif ind.startswith("ema_"):
                period = int(ind.split("_")[1])
                results[ind] = calculate_ema(closes, period)[-1]
            elif ind.startswith("rsi_"):
                period = int(ind.split("_")[1])
                results[ind] = calculate_rsi(closes, period)[-1]
            elif ind == "bollinger":
                results[ind] = calculate_bollinger_bands(closes)

        return results

    async def _find_support_resistance(self, symbol: str, lookback_days: int = 60):
        """Find support and resistance levels."""
        from analysis.levels import find_support_resistance

        data = await self._get_price_history(symbol, period=f"{lookback_days}d")
        closes = [bar["close"] for bar in data["bars"]]

        return find_support_resistance(closes)

    async def _calculate_fibonacci(self, symbol: str, swing_type: str = "recent"):
        """Calculate Fibonacci levels."""
        from analysis.indicators import calculate_fibonacci_levels

        data = await self._get_price_history(symbol, period="3mo")
        highs = [bar["high"] for bar in data["bars"]]
        lows = [bar["low"] for bar in data["bars"]]

        if swing_type == "recent":
            # Use recent 20-day swing
            recent_high = max(highs[-20:])
            recent_low = min(lows[-20:])
        else:
            # Use full period swing
            recent_high = max(highs)
            recent_low = min(lows)

        return calculate_fibonacci_levels(recent_high, recent_low)

    def _parse_response(self, content: str) -> Dict[str, Any]:
        """Parse chart analyst's response."""
        try:
            # Try to extract JSON from response
            if "```json" in content:
                json_str = content.split("```json")[1].split("```")[0]
                return json.loads(json_str)
            elif "{" in content:
                start = content.index("{")
                end = content.rindex("}") + 1
                return json.loads(content[start:end])
        except (json.JSONDecodeError, ValueError):
            pass

        # Fallback: return raw content
        return {
            "recommendation": "neutral",
            "chartNotes": content,
            "tool_calls_made": self.tool_calls_made,
        }
```

### Options Analyst Agent

```python
# src/agents/options_analyst.py
from agents.base import BaseAgent, AgentConfig
from typing import List, Dict, Any
import json

OPTIONS_ANALYST_PROMPT = """You are an expert options analyst specializing in premium selling
strategies, particularly cash-secured puts. Your analysis focuses on:

1. STRIKE SELECTION
   - Choose strikes below key support levels
   - Balance premium income vs. assignment risk
   - Consider delta (typically 0.20-0.30 for CSPs)

2. EXPIRATION SELECTION
   - Target 30-45 DTE for optimal theta decay
   - Avoid earnings dates
   - Consider weekly vs monthly expirations

3. PREMIUM ANALYSIS
   - Calculate return on capital (ROC)
   - Compare to typical benchmarks (0.5%+ weekly)
   - Factor in commission costs

4. RISK ASSESSMENT
   - IV/HV ratio (prefer elevated IV)
   - Liquidity (bid-ask spread, open interest)
   - Greeks analysis (delta, gamma exposure)

Use the chart context provided to inform strike selection relative to support levels.
"""

class OptionsAnalyst(BaseAgent):
    """Agent specialized in options analysis."""

    @property
    def system_prompt(self) -> str:
        return OPTIONS_ANALYST_PROMPT

    @property
    def tools(self) -> List[Dict]:
        return [
            {
                "type": "function",
                "function": {
                    "name": "get_option_chain",
                    "description": "Get options chain for a symbol",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "symbol": {"type": "string"},
                            "expiration": {"type": "string", "description": "YYYY-MM-DD or 'all'"},
                        },
                        "required": ["symbol"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_quote",
                    "description": "Get current quote for underlying",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "symbol": {"type": "string"},
                        },
                        "required": ["symbol"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "calculate_iv_hv",
                    "description": "Compare implied volatility to historical volatility",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "symbol": {"type": "string"},
                        },
                        "required": ["symbol"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "calculate_roc",
                    "description": "Calculate return on capital for a put option",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "strike": {"type": "number"},
                            "premium": {"type": "number"},
                            "dte": {"type": "integer"},
                        },
                        "required": ["strike", "premium", "dte"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_earnings_date",
                    "description": "Get next earnings date for a symbol",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "symbol": {"type": "string"},
                        },
                        "required": ["symbol"],
                    },
                },
            },
        ]

    def _get_tool_function(self, name: str):
        tool_map = {
            "get_option_chain": self._get_option_chain,
            "get_quote": self._get_quote,
            "calculate_iv_hv": self._calculate_iv_hv,
            "calculate_roc": self._calculate_roc,
            "get_earnings_date": self._get_earnings_date,
        }
        return tool_map.get(name)

    async def _get_option_chain(self, symbol: str, expiration: str = None):
        """Fetch option chain."""
        from tastytrade.client import TastyTradeClient

        client = await TastyTradeClient.from_user_id(self.env, self.user_id)
        return await client.get_option_chain(symbol, expiration)

    async def _get_quote(self, symbol: str):
        """Fetch current quote."""
        from tastytrade.client import TastyTradeClient

        client = await TastyTradeClient.from_user_id(self.env, self.user_id)
        quotes = await client.get_quotes([symbol])
        return quotes.get(symbol)

    async def _calculate_iv_hv(self, symbol: str):
        """Calculate IV/HV ratio."""
        from analysis.indicators import calculate_historical_volatility

        # Get HV from price history
        data = await self._get_price_history(symbol)
        closes = [bar["close"] for bar in data["bars"]]
        hv = calculate_historical_volatility(closes)

        # Get IV from options chain (ATM option)
        chain = await self._get_option_chain(symbol)
        iv = chain.get("atm_iv", 0.30)  # Default if not available

        return {
            "iv": iv,
            "hv": hv,
            "iv_hv_ratio": iv / hv if hv > 0 else 0,
        }

    async def _calculate_roc(self, strike: float, premium: float, dte: int):
        """Calculate return on capital."""
        capital_required = strike * 100
        total_return = premium * 100

        roc_total = total_return / capital_required * 100
        roc_weekly = roc_total / (dte / 7)
        roc_annualized = roc_weekly * 52

        return {
            "roc_total": round(roc_total, 2),
            "roc_weekly": round(roc_weekly, 2),
            "roc_annualized": round(roc_annualized, 2),
        }

    async def _get_earnings_date(self, symbol: str):
        """Get next earnings date."""
        # Query earnings calendar
        # This would typically call an external API
        return {"next_earnings": None, "days_to_earnings": None}

    def _parse_response(self, content: str) -> Dict[str, Any]:
        """Parse options analyst's response."""
        try:
            if "```json" in content:
                json_str = content.split("```json")[1].split("```")[0]
                return json.loads(json_str)
            elif "{" in content:
                start = content.index("{")
                end = content.rindex("}") + 1
                return json.loads(content[start:end])
        except (json.JSONDecodeError, ValueError):
            pass

        return {
            "recommendation": "reject",
            "optionsNotes": content,
            "tool_calls_made": self.tool_calls_made,
        }
```

## Tool Executor

### Tool Definitions

```python
# src/agents/tools.py
from typing import Dict, Any, Callable, List
from dataclasses import dataclass

@dataclass
class ToolDefinition:
    name: str
    description: str
    parameters: Dict[str, Any]
    function: Callable

class ToolExecutor:
    """Central registry and executor for agent tools."""

    def __init__(self, env, user_id: str):
        self.env = env
        self.user_id = user_id
        self._tools: Dict[str, ToolDefinition] = {}
        self._register_default_tools()

    def _register_default_tools(self):
        """Register default tools available to all agents."""

        # Quote tools
        self.register(
            "get_quote",
            "Get real-time quote for a symbol",
            {"symbol": {"type": "string"}},
            self._get_quote,
        )

        self.register(
            "get_quotes_batch",
            "Get quotes for multiple symbols",
            {"symbols": {"type": "array", "items": {"type": "string"}}},
            self._get_quotes_batch,
        )

        # Options tools
        self.register(
            "get_option_chain",
            "Get options chain for a symbol",
            {
                "symbol": {"type": "string"},
                "expiration": {"type": "string", "optional": True},
            },
            self._get_option_chain,
        )

    def register(
        self,
        name: str,
        description: str,
        parameters: Dict[str, Any],
        function: Callable,
    ):
        """Register a new tool."""
        self._tools[name] = ToolDefinition(
            name=name,
            description=description,
            parameters=parameters,
            function=function,
        )

    async def execute(self, name: str, arguments: Dict[str, Any]) -> Any:
        """Execute a tool by name."""
        if name not in self._tools:
            return {"error": f"Unknown tool: {name}"}

        tool = self._tools[name]
        return await tool.function(**arguments)

    def get_tool_schemas(self, tool_names: List[str] = None) -> List[Dict]:
        """Get OpenAI-format tool schemas."""
        tools = tool_names or list(self._tools.keys())

        return [
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description,
                    "parameters": {
                        "type": "object",
                        "properties": t.parameters,
                        "required": [k for k, v in t.parameters.items() if not v.get("optional")],
                    },
                },
            }
            for t in self._tools.values()
            if t.name in tools
        ]

    # Tool implementations
    async def _get_quote(self, symbol: str) -> Dict:
        from tastytrade.client import TastyTradeClient

        client = await TastyTradeClient.from_user_id(self.env, self.user_id)
        if not client:
            return {"error": "TastyTrade not connected"}

        quotes = await client.get_quotes([symbol])
        return quotes.get(symbol, {"error": "Quote not found"})

    async def _get_quotes_batch(self, symbols: List[str]) -> Dict:
        from tastytrade.client import TastyTradeClient

        client = await TastyTradeClient.from_user_id(self.env, self.user_id)
        if not client:
            return {"error": "TastyTrade not connected"}

        return await client.get_quotes(symbols)

    async def _get_option_chain(self, symbol: str, expiration: str = None) -> Dict:
        from tastytrade.client import TastyTradeClient

        client = await TastyTradeClient.from_user_id(self.env, self.user_id)
        if not client:
            return {"error": "TastyTrade not connected"}

        return await client.get_option_chain(symbol, expiration)
```

## Worker-to-Worker Communication

### Analysis Request Handler

```python
# src/handlers/analysis.py
from js import Response
import json

async def handle_analysis(request, env, user_id: str, analysis_type: str):
    """Handle analysis requests from TypeScript worker."""
    body = json.loads(await request.text())
    symbol = body.get("symbol")

    if not symbol:
        return Response.new(
            json.dumps({"error": "No symbol provided"}),
            status=400,
            headers={"Content-Type": "application/json"}
        )

    # Run appropriate agent
    if analysis_type == "chart":
        from agents.chart_analyst import ChartAnalyst

        agent = ChartAnalyst(env)
        agent.user_id = user_id
        result = await agent.run(f"Analyze the chart for {symbol}", body)

    elif analysis_type == "options":
        from agents.options_analyst import OptionsAnalyst

        agent = OptionsAnalyst(env)
        agent.user_id = user_id
        context = body.get("chartContext", {})
        strategy = body.get("strategy", "csp")
        result = await agent.run(
            f"Analyze options for {symbol} using {strategy} strategy",
            {"chartContext": context, "strategy": strategy},
        )

    elif analysis_type == "research":
        from agents.research_analyst import ResearchAnalyst

        agent = ResearchAnalyst(env)
        agent.user_id = user_id
        result = await agent.run(f"Research {symbol}", body)

    else:
        return Response.new(
            json.dumps({"error": f"Unknown analysis type: {analysis_type}"}),
            status=400,
            headers={"Content-Type": "application/json"}
        )

    return Response.new(
        json.dumps(result),
        headers={"Content-Type": "application/json"}
    )
```

## Cross-References

- [MCP Server Design](./01-mcp-server-design.md) - Tool registration
- [Python Workers](./03-python-workers.md) - Python runtime environment
- [Workflow Orchestration](./02-workflow-orchestration.md) - Analysis pipelines
- [Integration Patterns](./09-integration-patterns.md) - Worker communication
