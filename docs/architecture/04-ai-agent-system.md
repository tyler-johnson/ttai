# AI Agent System

## Overview

The AI agent system provides specialized analysts for different aspects of trading analysis. Each agent uses LiteLLM for provider-agnostic LLM integration, allowing users to choose their preferred AI provider (Anthropic, OpenAI, etc.). Agents run locally as part of the Python MCP server and can be orchestrated for comprehensive multi-step analysis.

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                       AI Agent System                                │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ┌────────────────────────────────────────────────────────────────┐ │
│  │                    Analysis Orchestrator                       │ │
│  │        Coordinates multi-agent analysis workflows              │ │
│  └───────────────────────────┬────────────────────────────────────┘ │
│                              │                                       │
│      ┌───────────────────────┼───────────────────────┐              │
│      │                       │                       │              │
│      ▼                       ▼                       ▼              │
│  ┌─────────┐          ┌─────────┐          ┌─────────────┐          │
│  │ Chart   │          │ Options │          │  Research   │          │
│  │ Analyst │          │ Analyst │          │  Analyst    │          │
│  └────┬────┘          └────┬────┘          └──────┬──────┘          │
│       │                    │                      │                  │
│       └────────────────────┼──────────────────────┘                  │
│                            ▼                                         │
│  ┌────────────────────────────────────────────────────────────────┐ │
│  │                     Base Agent Class                           │ │
│  │    LiteLLM Integration | Tool Execution | Memory               │ │
│  └────────────────────────────────────────────────────────────────┘ │
│                            │                                         │
│  ┌────────────────────────────────────────────────────────────────┐ │
│  │                 LiteLLM (Provider Agnostic)                    │ │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐       │ │
│  │  │ Anthropic│  │  OpenAI  │  │  Google  │  │  Bedrock │       │ │
│  │  │  Claude  │  │   GPT    │  │  Gemini  │  │  Claude  │       │ │
│  │  └──────────┘  └──────────┘  └──────────┘  └──────────┘       │ │
│  └────────────────────────────────────────────────────────────────┘ │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

## LiteLLM Configuration

### Environment Variables

LiteLLM reads API keys from environment variables. Users configure these in the app settings or system environment.

```python
# src/agents/llm_config.py
import os
from dataclasses import dataclass
from typing import Optional
import litellm

@dataclass
class LLMConfig:
    """Configuration for LLM providers."""

    # Default model (can be overridden per-agent)
    default_model: str = "anthropic/claude-sonnet-4-20250514"

    # Temperature for generation
    temperature: float = 0.7

    # Max tokens for responses
    max_tokens: int = 4096

    # Timeout in seconds
    timeout: int = 120

    @classmethod
    def from_env(cls) -> "LLMConfig":
        """Create config from environment variables."""
        return cls(
            default_model=os.getenv(
                "TTAI_DEFAULT_MODEL",
                "anthropic/claude-sonnet-4-20250514"
            ),
            temperature=float(os.getenv("TTAI_LLM_TEMPERATURE", "0.7")),
            max_tokens=int(os.getenv("TTAI_LLM_MAX_TOKENS", "4096")),
            timeout=int(os.getenv("TTAI_LLM_TIMEOUT", "120")),
        )

def setup_litellm():
    """Configure LiteLLM settings."""
    # Enable verbose logging in debug mode
    litellm.set_verbose = os.getenv("TTAI_DEBUG", "false").lower() == "true"

    # Set callbacks for logging/monitoring if needed
    # litellm.success_callback = [custom_callback]

# Supported models for UI dropdown
SUPPORTED_MODELS = [
    # Anthropic
    "anthropic/claude-sonnet-4-20250514",
    "anthropic/claude-opus-4-20250514",
    "anthropic/claude-3-5-haiku-20241022",

    # OpenAI
    "openai/gpt-4o",
    "openai/gpt-4o-mini",
    "openai/o1-preview",

    # Google
    "gemini/gemini-1.5-pro",
    "gemini/gemini-1.5-flash",

    # AWS Bedrock
    "bedrock/anthropic.claude-3-sonnet-20240229-v1:0",
    "bedrock/anthropic.claude-3-haiku-20240307-v1:0",
]
```

## Base Agent Class

```python
# src/agents/base.py
import json
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional
import litellm

from .llm_config import LLMConfig

logger = logging.getLogger(__name__)

@dataclass
class Message:
    """A conversation message."""
    role: str  # "user", "assistant", "system", "tool"
    content: str
    tool_call_id: Optional[str] = None
    tool_calls: Optional[List[Dict]] = None
    name: Optional[str] = None

@dataclass
class Tool:
    """A tool available to the agent."""
    name: str
    description: str
    parameters: Dict[str, Any]
    handler: Callable[..., Any]

@dataclass
class AgentContext:
    """Context passed to agent during execution."""
    symbol: Optional[str] = None
    timeframe: Optional[str] = None
    strategy: Optional[str] = None
    chart_context: Optional[Dict[str, Any]] = None
    additional_data: Dict[str, Any] = field(default_factory=dict)

class BaseAgent(ABC):
    """
    Base class for AI agents with LiteLLM integration.

    Provides:
    - LLM completion with tool use
    - Conversation memory
    - Tool execution loop
    - Error handling
    """

    def __init__(
        self,
        name: str,
        system_prompt: str,
        config: Optional[LLMConfig] = None,
        tools: Optional[List[Tool]] = None,
    ):
        self.name = name
        self.system_prompt = system_prompt
        self.config = config or LLMConfig.from_env()
        self.tools = tools or []
        self._messages: List[Message] = []

    @property
    def messages(self) -> List[Dict[str, Any]]:
        """Get messages in LiteLLM format."""
        return [
            {"role": "system", "content": self.system_prompt}
        ] + [
            self._message_to_dict(m) for m in self._messages
        ]

    def _message_to_dict(self, msg: Message) -> Dict[str, Any]:
        """Convert Message to dict for LiteLLM."""
        d = {"role": msg.role, "content": msg.content}
        if msg.tool_call_id:
            d["tool_call_id"] = msg.tool_call_id
        if msg.tool_calls:
            d["tool_calls"] = msg.tool_calls
        if msg.name:
            d["name"] = msg.name
        return d

    def _tools_to_openai_format(self) -> List[Dict[str, Any]]:
        """Convert tools to OpenAI function calling format."""
        return [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.parameters,
                }
            }
            for tool in self.tools
        ]

    async def complete(
        self,
        user_message: str,
        max_iterations: int = 10
    ) -> str:
        """
        Run completion with tool execution loop.

        Args:
            user_message: The user's input message
            max_iterations: Maximum tool execution iterations

        Returns:
            Final assistant response text
        """
        # Add user message
        self._messages.append(Message(role="user", content=user_message))

        for iteration in range(max_iterations):
            logger.debug(f"{self.name}: Iteration {iteration + 1}/{max_iterations}")

            # Call LLM
            response = await self._call_llm()

            # Extract assistant message
            assistant_message = response.choices[0].message

            # Check for tool calls
            if assistant_message.tool_calls:
                # Add assistant message with tool calls
                self._messages.append(Message(
                    role="assistant",
                    content=assistant_message.content or "",
                    tool_calls=[
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments
                            }
                        }
                        for tc in assistant_message.tool_calls
                    ]
                ))

                # Execute each tool call
                for tool_call in assistant_message.tool_calls:
                    result = await self._execute_tool(
                        tool_call.function.name,
                        json.loads(tool_call.function.arguments)
                    )

                    # Add tool result
                    self._messages.append(Message(
                        role="tool",
                        content=json.dumps(result) if isinstance(result, dict) else str(result),
                        tool_call_id=tool_call.id,
                        name=tool_call.function.name
                    ))
            else:
                # No tool calls, we have our final response
                final_content = assistant_message.content or ""
                self._messages.append(Message(
                    role="assistant",
                    content=final_content
                ))
                return final_content

        # Max iterations reached
        logger.warning(f"{self.name}: Max iterations reached")
        return self._messages[-1].content if self._messages else "Analysis incomplete"

    async def _call_llm(self) -> Any:
        """Call the LLM via LiteLLM."""
        try:
            response = await litellm.acompletion(
                model=self.config.default_model,
                messages=self.messages,
                tools=self._tools_to_openai_format() if self.tools else None,
                temperature=self.config.temperature,
                max_tokens=self.config.max_tokens,
                timeout=self.config.timeout,
            )
            return response

        except litellm.RateLimitError as e:
            logger.error(f"Rate limit error: {e}")
            raise
        except litellm.APIError as e:
            logger.error(f"API error: {e}")
            raise
        except Exception as e:
            logger.error(f"LLM call failed: {e}")
            raise

    async def _execute_tool(
        self,
        tool_name: str,
        arguments: Dict[str, Any]
    ) -> Any:
        """Execute a tool by name."""
        logger.debug(f"{self.name}: Executing tool {tool_name}")

        tool = next((t for t in self.tools if t.name == tool_name), None)
        if not tool:
            return {"error": f"Unknown tool: {tool_name}"}

        try:
            result = await tool.handler(**arguments)
            return result
        except Exception as e:
            logger.error(f"Tool {tool_name} failed: {e}")
            return {"error": str(e)}

    def clear_memory(self) -> None:
        """Clear conversation history."""
        self._messages.clear()

    @abstractmethod
    async def analyze(self, *args, **kwargs) -> Dict[str, Any]:
        """Run the agent's analysis. Implemented by subclasses."""
        pass
```

## Chart Analyst Agent

```python
# src/agents/chart_analyst.py
import json
from typing import Any, Dict, Optional

from .base import BaseAgent, Tool, AgentContext
from ..services.tastytrade import TastyTradeService
from ..services.cache import CacheService
from ..analysis.indicators import calculate_indicators
from ..analysis.levels import detect_support_resistance

CHART_ANALYST_PROMPT = """You are a technical chart analyst specializing in options trading setups.
Your job is to analyze price charts and identify:

1. **Trend Analysis**: Current trend direction and strength
2. **Support/Resistance**: Key price levels
3. **Technical Indicators**: RSI, MACD, moving averages
4. **Chart Patterns**: Any significant patterns forming
5. **Volatility Assessment**: Current volatility state

Focus on setups suitable for selling options premium (CSPs, covered calls).
Prefer stocks that are:
- In established uptrends or bouncing off support
- Not extended too far from moving averages
- Showing signs of consolidation or pullback

Output your analysis as structured JSON with your recommendation."""

class ChartAnalyst(BaseAgent):
    """
    Technical chart analysis agent.

    Analyzes price action, indicators, and chart patterns
    to identify trading setups.
    """

    def __init__(
        self,
        tastytrade: TastyTradeService,
        cache: CacheService,
        model: Optional[str] = None
    ):
        self.tastytrade = tastytrade
        self.cache = cache

        # Define tools available to this agent
        tools = [
            Tool(
                name="get_quote",
                description="Get current quote data for a symbol",
                parameters={
                    "type": "object",
                    "properties": {
                        "symbol": {
                            "type": "string",
                            "description": "Stock symbol"
                        }
                    },
                    "required": ["symbol"]
                },
                handler=self._get_quote
            ),
            Tool(
                name="get_price_history",
                description="Get historical price data for technical analysis",
                parameters={
                    "type": "object",
                    "properties": {
                        "symbol": {
                            "type": "string",
                            "description": "Stock symbol"
                        },
                        "timeframe": {
                            "type": "string",
                            "description": "Timeframe: daily, weekly",
                            "enum": ["daily", "weekly"]
                        },
                        "periods": {
                            "type": "integer",
                            "description": "Number of periods",
                            "default": 100
                        }
                    },
                    "required": ["symbol"]
                },
                handler=self._get_price_history
            ),
            Tool(
                name="calculate_technicals",
                description="Calculate technical indicators for a symbol",
                parameters={
                    "type": "object",
                    "properties": {
                        "symbol": {
                            "type": "string",
                            "description": "Stock symbol"
                        }
                    },
                    "required": ["symbol"]
                },
                handler=self._calculate_technicals
            ),
            Tool(
                name="find_levels",
                description="Find support and resistance levels",
                parameters={
                    "type": "object",
                    "properties": {
                        "symbol": {
                            "type": "string",
                            "description": "Stock symbol"
                        }
                    },
                    "required": ["symbol"]
                },
                handler=self._find_levels
            ),
        ]

        super().__init__(
            name="ChartAnalyst",
            system_prompt=CHART_ANALYST_PROMPT,
            tools=tools
        )

        if model:
            self.config.default_model = model

    async def _get_quote(self, symbol: str) -> Dict[str, Any]:
        """Get quote data."""
        return await self.tastytrade.get_quote(symbol)

    async def _get_price_history(
        self,
        symbol: str,
        timeframe: str = "daily",
        periods: int = 100
    ) -> Dict[str, Any]:
        """Get historical price data."""
        # This would fetch from TastyTrade or another data source
        return {
            "symbol": symbol,
            "timeframe": timeframe,
            "periods": periods,
            "data": "Price history would be fetched here"
        }

    async def _calculate_technicals(self, symbol: str) -> Dict[str, Any]:
        """Calculate technical indicators."""
        quote = await self.tastytrade.get_quote(symbol)
        return calculate_indicators(symbol, quote)

    async def _find_levels(self, symbol: str) -> Dict[str, Any]:
        """Find support/resistance levels."""
        quote = await self.tastytrade.get_quote(symbol)
        return detect_support_resistance(symbol, quote["last"])

    async def analyze(
        self,
        symbol: str,
        timeframe: str = "daily"
    ) -> Dict[str, Any]:
        """
        Run chart analysis for a symbol.

        Args:
            symbol: Stock symbol to analyze
            timeframe: Analysis timeframe (daily, weekly)

        Returns:
            Analysis results with recommendation
        """
        self.clear_memory()

        prompt = f"""Analyze {symbol} on the {timeframe} timeframe.

Use the available tools to gather data, then provide your analysis.

Your response should be valid JSON with this structure:
{{
    "symbol": "{symbol}",
    "timeframe": "{timeframe}",
    "trend": "bullish" | "neutral" | "bearish",
    "trend_strength": 1-10,
    "support_levels": [price1, price2, ...],
    "resistance_levels": [price1, price2, ...],
    "indicators": {{
        "rsi": value,
        "macd_signal": "bullish" | "neutral" | "bearish",
        "above_200ma": true | false
    }},
    "patterns": ["pattern1", ...],
    "recommendation": "bullish" | "neutral" | "bearish",
    "score": 1-10,
    "reasoning": "Your analysis explanation"
}}"""

        response = await self.complete(prompt)

        # Parse JSON response
        try:
            if "```json" in response:
                json_str = response.split("```json")[1].split("```")[0]
            elif "```" in response:
                json_str = response.split("```")[1].split("```")[0]
            else:
                json_str = response

            return json.loads(json_str.strip())

        except json.JSONDecodeError:
            return {
                "symbol": symbol,
                "timeframe": timeframe,
                "recommendation": "neutral",
                "score": 5,
                "reasoning": response,
                "raw_response": True
            }
```

## Options Analyst Agent

```python
# src/agents/options_analyst.py
import json
from typing import Any, Dict, Optional

from .base import BaseAgent, Tool
from ..services.tastytrade import TastyTradeService
from ..services.cache import CacheService

OPTIONS_ANALYST_PROMPT = """You are an options analyst specializing in premium-selling strategies.
Given chart analysis context, your job is to:

1. **Evaluate Option Chain**: Find optimal strikes and expirations
2. **Assess IV Rank**: Determine if premium is attractive
3. **Calculate Risk/Reward**: Analyze potential outcomes
4. **Select Strike**: Choose appropriate strike based on probability and premium
5. **Recommend Position**: Specific option contract recommendation

For Cash-Secured Puts (CSP):
- Target 30-45 DTE
- Look for 0.20-0.30 delta puts
- Ensure strike is at or below support
- Premium should be > 1% of strike

For Covered Calls:
- Target 30-45 DTE
- Look for 0.20-0.30 delta calls
- Ensure strike is at or above resistance
- Consider assignment risk

Output structured JSON with your recommendation."""

class OptionsAnalyst(BaseAgent):
    """
    Options analysis agent.

    Analyzes option chains to find optimal premium-selling opportunities.
    """

    def __init__(
        self,
        tastytrade: TastyTradeService,
        cache: CacheService,
        model: Optional[str] = None
    ):
        self.tastytrade = tastytrade
        self.cache = cache

        tools = [
            Tool(
                name="get_option_chain",
                description="Get option chain for a symbol",
                parameters={
                    "type": "object",
                    "properties": {
                        "symbol": {
                            "type": "string",
                            "description": "Underlying symbol"
                        },
                        "expiration": {
                            "type": "string",
                            "description": "Specific expiration (YYYY-MM-DD) or null for all"
                        }
                    },
                    "required": ["symbol"]
                },
                handler=self._get_option_chain
            ),
            Tool(
                name="get_quote",
                description="Get current quote for the underlying",
                parameters={
                    "type": "object",
                    "properties": {
                        "symbol": {
                            "type": "string",
                            "description": "Stock symbol"
                        }
                    },
                    "required": ["symbol"]
                },
                handler=self._get_quote
            ),
            Tool(
                name="calculate_roi",
                description="Calculate return on investment for an option trade",
                parameters={
                    "type": "object",
                    "properties": {
                        "premium": {
                            "type": "number",
                            "description": "Option premium collected"
                        },
                        "strike": {
                            "type": "number",
                            "description": "Strike price"
                        },
                        "dte": {
                            "type": "integer",
                            "description": "Days to expiration"
                        }
                    },
                    "required": ["premium", "strike", "dte"]
                },
                handler=self._calculate_roi
            ),
        ]

        super().__init__(
            name="OptionsAnalyst",
            system_prompt=OPTIONS_ANALYST_PROMPT,
            tools=tools
        )

        if model:
            self.config.default_model = model

    async def _get_option_chain(
        self,
        symbol: str,
        expiration: Optional[str] = None
    ) -> Dict[str, Any]:
        """Get option chain."""
        return await self.tastytrade.get_option_chain(symbol, expiration)

    async def _get_quote(self, symbol: str) -> Dict[str, Any]:
        """Get quote data."""
        return await self.tastytrade.get_quote(symbol)

    async def _calculate_roi(
        self,
        premium: float,
        strike: float,
        dte: int
    ) -> Dict[str, Any]:
        """Calculate ROI metrics."""
        trade_return = premium / strike
        annual_return = trade_return * (365 / dte) if dte > 0 else 0

        return {
            "trade_return": round(trade_return * 100, 2),
            "annualized_return": round(annual_return * 100, 2),
            "breakeven": round(strike - premium, 2),
            "max_profit": round(premium * 100, 2),
            "max_loss": round((strike - premium) * 100, 2),
        }

    async def analyze(
        self,
        symbol: str,
        strategy: str = "csp",
        chart_context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Analyze options opportunities for a symbol.

        Args:
            symbol: Underlying symbol
            strategy: Strategy type (csp, covered_call, spread)
            chart_context: Chart analysis context for informed decisions

        Returns:
            Options analysis with specific recommendation
        """
        self.clear_memory()

        context_str = ""
        if chart_context:
            context_str = f"""
Chart Analysis Context:
- Trend: {chart_context.get('trend', 'unknown')}
- Support Levels: {chart_context.get('support_levels', [])}
- Resistance Levels: {chart_context.get('resistance_levels', [])}
- Recommendation: {chart_context.get('recommendation', 'neutral')}
"""

        strategy_guidance = {
            "csp": "Focus on cash-secured put opportunities. Look for puts at or below support with good premium.",
            "covered_call": "Focus on covered call opportunities. Look for calls at or above resistance.",
            "spread": "Focus on vertical spread opportunities. Consider both risk and premium."
        }

        prompt = f"""Analyze {symbol} for {strategy} opportunities.
{context_str}
{strategy_guidance.get(strategy, '')}

Use the tools to analyze the option chain, then provide your recommendation.

Your response should be valid JSON with this structure:
{{
    "symbol": "{symbol}",
    "strategy": "{strategy}",
    "recommendation": "select" | "watchlist" | "pass",
    "selected_option": {{
        "type": "put" | "call",
        "strike": strike_price,
        "expiration": "YYYY-MM-DD",
        "dte": days,
        "premium": premium_per_share,
        "delta": delta_value,
        "iv": implied_volatility
    }},
    "metrics": {{
        "trade_return": percentage,
        "annualized_return": percentage,
        "breakeven": price,
        "max_profit": dollars,
        "max_loss": dollars,
        "probability_of_profit": percentage
    }},
    "reasoning": "Your analysis explanation"
}}"""

        response = await self.complete(prompt)

        try:
            if "```json" in response:
                json_str = response.split("```json")[1].split("```")[0]
            elif "```" in response:
                json_str = response.split("```")[1].split("```")[0]
            else:
                json_str = response

            return json.loads(json_str.strip())

        except json.JSONDecodeError:
            return {
                "symbol": symbol,
                "strategy": strategy,
                "recommendation": "watchlist",
                "reasoning": response,
                "raw_response": True
            }
```

## Analysis Orchestrator

```python
# src/agents/orchestrator.py
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

from .chart_analyst import ChartAnalyst
from .options_analyst import OptionsAnalyst
from ..services.tastytrade import TastyTradeService
from ..services.cache import CacheService
from ..services.database import DatabaseService
from ..server.notifications import NotificationEmitter

logger = logging.getLogger(__name__)

@dataclass
class FullAnalysisResult:
    """Complete analysis result."""
    symbol: str
    chart_analysis: Dict[str, Any]
    options_analysis: Optional[Dict[str, Any]]
    recommendation: str
    score: float
    timestamp: datetime

class AnalysisOrchestrator:
    """
    Orchestrates multi-agent analysis workflows.

    Coordinates chart and options analysts for comprehensive analysis.
    """

    def __init__(
        self,
        tastytrade: TastyTradeService,
        cache: CacheService,
        db: DatabaseService
    ):
        self.tastytrade = tastytrade
        self.cache = cache
        self.db = db

        # Initialize agents
        self.chart_analyst = ChartAnalyst(tastytrade, cache)
        self.options_analyst = OptionsAnalyst(tastytrade, cache)

    async def run_full_analysis(
        self,
        symbol: str,
        strategy: str = "csp",
        notify: bool = True
    ) -> Dict[str, Any]:
        """
        Run comprehensive multi-agent analysis.

        Steps:
        1. Chart analysis (technical)
        2. Options analysis (if chart favorable)
        3. Synthesize final recommendation
        4. Save results
        5. Notify user (optional)
        """
        logger.info(f"Starting full analysis for {symbol}")

        # Step 1: Chart Analysis
        chart_result = await self.chart_analyst.analyze(symbol)

        # Early exit if chart analysis is bearish
        if chart_result.get("recommendation") == "bearish":
            result = {
                "symbol": symbol,
                "chart_analysis": chart_result,
                "options_analysis": None,
                "recommendation": "reject",
                "score": chart_result.get("score", 3),
                "reasoning": "Chart analysis indicates bearish conditions",
                "timestamp": datetime.now().isoformat()
            }

            await self._save_analysis(symbol, "full", result)

            if notify:
                NotificationEmitter.analysis_complete(symbol, "reject")

            return result

        # Step 2: Options Analysis
        options_result = await self.options_analyst.analyze(
            symbol,
            strategy=strategy,
            chart_context=chart_result
        )

        # Step 3: Synthesize Recommendation
        recommendation, score = self._synthesize_recommendation(
            chart_result,
            options_result
        )

        result = {
            "symbol": symbol,
            "strategy": strategy,
            "chart_analysis": chart_result,
            "options_analysis": options_result,
            "recommendation": recommendation,
            "score": score,
            "reasoning": self._generate_reasoning(chart_result, options_result),
            "timestamp": datetime.now().isoformat()
        }

        # Step 4: Save Results
        await self._save_analysis(symbol, "full", result)

        # Step 5: Notify
        if notify:
            NotificationEmitter.analysis_complete(symbol, recommendation)

        logger.info(f"Completed analysis for {symbol}: {recommendation}")
        return result

    def _synthesize_recommendation(
        self,
        chart: Dict[str, Any],
        options: Optional[Dict[str, Any]]
    ) -> tuple[str, float]:
        """Synthesize final recommendation from agent outputs."""
        score = 0.0

        chart_rec = chart.get("recommendation", "neutral")
        chart_score = chart.get("score", 5)

        if chart_rec == "bullish":
            score += min(chart_score / 2, 2.5)
        elif chart_rec == "neutral":
            score += 1.0

        if options:
            options_rec = options.get("recommendation", "pass")
            if options_rec == "select":
                score += 2.5

                metrics = options.get("metrics", {})
                if metrics.get("annualized_return", 0) > 20:
                    score += 0.5
                if metrics.get("probability_of_profit", 0) > 70:
                    score += 0.5

            elif options_rec == "watchlist":
                score += 1.0

        if score >= 4.0:
            return "strong_select", score
        elif score >= 2.5:
            return "select", score
        elif score >= 1.0:
            return "watchlist", score
        else:
            return "reject", score

    def _generate_reasoning(
        self,
        chart: Dict[str, Any],
        options: Optional[Dict[str, Any]]
    ) -> str:
        """Generate combined reasoning from analyses."""
        parts = []

        if chart.get("reasoning"):
            parts.append(f"Chart: {chart['reasoning']}")

        if options and options.get("reasoning"):
            parts.append(f"Options: {options['reasoning']}")

        return " | ".join(parts) if parts else "Analysis complete"

    async def _save_analysis(
        self,
        symbol: str,
        analysis_type: str,
        result: Dict[str, Any]
    ) -> None:
        """Save analysis to database."""
        await self.db.save_analysis(
            symbol=symbol,
            analysis_type=analysis_type,
            result=result
        )

    async def run_screener(
        self,
        symbols: List[str],
        strategy: str = "csp",
        max_concurrent: int = 3
    ) -> List[Dict[str, Any]]:
        """
        Screen multiple symbols concurrently.

        Args:
            symbols: List of symbols to screen
            strategy: Options strategy
            max_concurrent: Max concurrent analyses

        Returns:
            Ranked list of analysis results
        """
        import asyncio

        semaphore = asyncio.Semaphore(max_concurrent)

        async def analyze_with_limit(symbol: str) -> Optional[Dict[str, Any]]:
            async with semaphore:
                try:
                    return await self.run_full_analysis(
                        symbol,
                        strategy=strategy,
                        notify=False
                    )
                except Exception as e:
                    logger.warning(f"Failed to analyze {symbol}: {e}")
                    return None

        tasks = [analyze_with_limit(s) for s in symbols]
        all_results = await asyncio.gather(*tasks)

        valid_results = [r for r in all_results if r is not None]
        ranked = sorted(
            valid_results,
            key=lambda x: x.get("score", 0),
            reverse=True
        )

        return ranked[:10]
```

## Technical Indicators Utilities

```python
# src/analysis/indicators.py
from typing import Any, Dict

def calculate_indicators(symbol: str, quote: Dict[str, Any]) -> Dict[str, Any]:
    """
    Calculate technical indicators from quote data.

    In a real implementation, this would use historical data
    and proper indicator calculations (e.g., pandas-ta).
    """
    current_price = quote.get("last", 0)

    return {
        "symbol": symbol,
        "current_price": current_price,
        "indicators": {
            "rsi_14": 55.0,
            "macd": {
                "value": 0.5,
                "signal": 0.3,
                "histogram": 0.2,
                "trend": "bullish"
            },
            "moving_averages": {
                "sma_20": current_price * 0.98,
                "sma_50": current_price * 0.95,
                "sma_200": current_price * 0.90,
                "above_20": True,
                "above_50": True,
                "above_200": True
            },
            "bollinger_bands": {
                "upper": current_price * 1.05,
                "middle": current_price,
                "lower": current_price * 0.95,
                "position": "middle"
            }
        }
    }


# src/analysis/levels.py
def detect_support_resistance(symbol: str, current_price: float) -> Dict[str, Any]:
    """
    Detect support and resistance levels.

    Real implementation would analyze historical price action.
    """
    return {
        "symbol": symbol,
        "current_price": current_price,
        "support_levels": [
            round(current_price * 0.95, 2),
            round(current_price * 0.90, 2),
            round(current_price * 0.85, 2),
        ],
        "resistance_levels": [
            round(current_price * 1.05, 2),
            round(current_price * 1.10, 2),
            round(current_price * 1.15, 2),
        ],
        "key_level": round(current_price * 0.95, 2),
        "level_type": "support"
    }
```

## Cross-References

- [MCP Server Design](./01-mcp-server-design.md) - Tool registration
- [Python Server](./03-python-server.md) - Project structure
- [Workflow Orchestration](./02-workflow-orchestration.md) - Task integration
- [Knowledge Base](./07-knowledge-base.md) - RAG for research agent
