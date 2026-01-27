# AI Agent Architecture

## Overview

The AI agent system provides intelligent analysis of trading opportunities through a hierarchy of specialized agents. The system is built on proven patterns from the `csp_screener` project, using LiteLLM for provider-agnostic LLM access. Each agent has specific expertise and tools.

## LiteLLM Integration

LiteLLM provides a unified interface for multiple LLM providers:

- **Provider agnostic**: Single interface for OpenAI, Anthropic, Google, AWS Bedrock, Azure, Cohere, etc.
- **OpenAI-compatible API**: Uses familiar message format
- **Built-in tool calling**: Works across providers that support it
- **Router/fallback support**: Can configure fallbacks between providers
- **Automatic rate limiting**: Built-in rate limit handling
- **Cost tracking**: Built-in usage tracking
- **Environment-based auth**: Reads API keys automatically from standard env vars

### Model String Format

LiteLLM uses a `provider/model` format for model strings:

```python
# Anthropic models
"anthropic/claude-sonnet-4-20250514"
"anthropic/claude-opus-4-20250514"

# OpenAI models
"openai/gpt-4o"
"openai/gpt-4-turbo"

# Google models
"gemini/gemini-1.5-pro"

# AWS Bedrock
"bedrock/anthropic.claude-3-sonnet"
```

## Agent Hierarchy

```
┌─────────────────────────────────────────────────────────────────────┐
│               Orchestrator (configurable, default: capable model)   │
│                                                                     │
│  Responsibilities:                                                  │
│  - Final recommendation decisions                                   │
│  - Synthesizing multi-agent analysis                                │
│  - Managing analysis flow based on early rejection                  │
└─────────────────────────────────────┬───────────────────────────────┘
                                      │
         ┌────────────────────────────┼────────────────────────────┐
         ▼                            ▼                            ▼
┌─────────────────┐        ┌─────────────────┐        ┌─────────────────┐
│  Chart Analyst  │        │ Options Analyst │        │Research Analyst │
│  (configurable) │        │  (configurable) │        │  (configurable) │
│                 │        │                 │        │                 │
│ - Trend analysis│        │ - Greeks eval   │        │ - News analysis │
│ - Support/Resist│        │ - Strike select │        │ - Earnings risk │
│ - Fib levels    │        │ - IV/HV analysis│        │ - Short interest│
│ - Pattern recog │        │ - Liquidity     │        │ - Red flags     │
└─────────────────┘        └─────────────────┘        └─────────────────┘
```

## Agentic Loop Implementation

The core agentic loop uses LiteLLM for provider-agnostic LLM access:

```python
# agents/agentic_loop.py
import asyncio
import json
from dataclasses import dataclass
from typing import Any, Callable, Awaitable, Optional, Union, Sequence

import litellm
from litellm import acompletion


@dataclass
class AgenticLoopResult:
    """Result from running an agentic loop."""

    final_response: str
    tool_calls_made: int
    conversation_history: list[dict]
    raw_response: Optional[dict] = None


ToolExecutor = Callable[[str, dict[str, Any]], Awaitable[dict[str, Any]]]


async def run_agentic_loop(
    model: str,
    system_prompt: str,
    tools: Sequence[dict],
    initial_message: Union[str, list[dict]],
    tool_executor: ToolExecutor,
    max_tokens: int = 4096,
    max_iterations: Optional[int] = None,
    heartbeat_fn: Optional[Callable[[], Awaitable[None]]] = None,
    verbose: bool = False,
) -> AgenticLoopResult:
    """
    Run an agentic loop where the LLM iteratively calls tools until satisfied.

    The loop continues until the LLM responds without any tool calls,
    indicating it has gathered enough information for a final response.

    Args:
        model: LiteLLM model string (e.g., "anthropic/claude-sonnet-4-20250514")
        system_prompt: System prompt guiding agent behavior
        tools: List of tool definitions (OpenAI tool format)
        initial_message: Initial user message
        tool_executor: Async function that executes tools: (name, input) -> result
        max_tokens: Maximum tokens per response
        max_iterations: Optional limit on tool-calling iterations
        heartbeat_fn: Optional async callback for activity heartbeats
        verbose: If True, print progress

    Returns:
        AgenticLoopResult with final response and conversation history
    """
    # Build initial messages
    messages: list[dict] = [
        {"role": "system", "content": system_prompt},
    ]

    if isinstance(initial_message, str):
        messages.append({"role": "user", "content": initial_message})
    else:
        messages.append({"role": "user", "content": initial_message})

    tool_calls_made = 0
    iterations = 0

    while True:
        # Check iteration limit
        if max_iterations is not None and iterations >= max_iterations:
            messages.append({
                "role": "user",
                "content": "Please provide your final analysis based on information gathered so far.",
            })

        # Heartbeat before API call
        if heartbeat_fn:
            await heartbeat_fn()

        # Make API call via LiteLLM
        # LiteLLM handles rate limiting automatically
        response = await acompletion(
            model=model,
            messages=messages,
            tools=tools if tools else None,
            max_tokens=max_tokens,
        )

        iterations += 1

        # Heartbeat after API call
        if heartbeat_fn:
            await heartbeat_fn()

        # Extract the assistant message
        assistant_message = response.choices[0].message

        # Check if the LLM is done (no tool calls)
        if not assistant_message.tool_calls:
            final_text = assistant_message.content or ""
            return AgenticLoopResult(
                final_response=final_text,
                tool_calls_made=tool_calls_made,
                conversation_history=messages,
                raw_response=response.model_dump() if hasattr(response, 'model_dump') else dict(response),
            )

        # Add assistant message to history
        messages.append({
            "role": "assistant",
            "content": assistant_message.content,
            "tool_calls": [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    }
                }
                for tc in assistant_message.tool_calls
            ],
        })

        # Execute each tool call
        for tool_call in assistant_message.tool_calls:
            tool_calls_made += 1

            tool_name = tool_call.function.name
            tool_args = json.loads(tool_call.function.arguments)

            if verbose:
                print(f"     [tool] {tool_name}(...)")

            try:
                result = await tool_executor(tool_name, tool_args)

                # Handle image results
                if isinstance(result, dict) and "image_base64" in result:
                    image_data = result.pop("image_base64")
                    # For OpenAI-compatible format with vision
                    tool_content = [
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{image_data}",
                            },
                        },
                        {
                            "type": "text",
                            "text": json.dumps(result, default=str),
                        },
                    ]
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": tool_content,
                    })
                else:
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": json.dumps(result, default=str),
                    })

            except Exception as e:
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": json.dumps({"error": str(e)}),
                })

            # Heartbeat after each tool
            if heartbeat_fn:
                await heartbeat_fn()


def build_image_message(
    text: str,
    image_base64: str,
    media_type: str = "image/png",
) -> list[dict]:
    """Build a message content list with text and an image (OpenAI format)."""
    return [
        {
            "type": "image_url",
            "image_url": {
                "url": f"data:{media_type};base64,{image_base64}",
            },
        },
        {
            "type": "text",
            "text": text,
        },
    ]
```

## Chart Analyst Agent

Specializes in technical analysis - trends, support/resistance, Fibonacci levels, and patterns.

````python
# agents/chart_analyst.py
from dataclasses import dataclass
from typing import Optional, Callable, Awaitable, Any

from .agentic_loop import run_agentic_loop, build_image_message, AgenticLoopResult
from tools.chart_tools import CHART_TOOLS, execute_chart_tool
from models.analysis import ChartAnalysisResult

CHART_ANALYST_SYSTEM_PROMPT = """You are a Chart Analyst specializing in technical analysis for options trading.

Your job is to analyze price charts to determine:
1. Trend direction and quality (strong uptrend, moderate uptrend, sideways, etc.)
2. Key support and resistance levels
3. Fibonacci retracement and extension levels
4. Whether the stock is extended from support or has room to move
5. Overall chart health for selling cash-secured puts

TOOLS AVAILABLE:
- get_price_history: Fetch OHLCV data for different timeframes
- calculate_swing_points: Identify swing highs and lows
- calculate_fib_levels: Calculate Fibonacci retracement from swing points
- find_support_resistance: Identify key support/resistance zones
- calculate_trendline: Fit trendlines to price data
- render_chart: Generate a chart image for visual analysis

ANALYSIS APPROACH:
1. Start by fetching daily price history (6 months is good)
2. Identify swing highs and lows for Fib calculations
3. Calculate Fib levels from the most significant swing
4. Find support/resistance zones
5. Render a chart to visually confirm your analysis
6. Synthesize findings into a recommendation

OUTPUT FORMAT:
Your final response MUST include a JSON block with this structure:
```json
{
  "recommendation": "bullish|bearish|neutral|reject",
  "trend_direction": "up|down|sideways",
  "trend_quality": "strong|moderate|weak",
  "support_levels": [{"price": 100.0, "strength": "strong", "type": "fib_61.8"}],
  "resistance_levels": [{"price": 110.0, "strength": "moderate", "type": "prior_high"}],
  "fib_confluence_zones": [{"price": 98.5, "levels": ["50%", "prior_low"]}],
  "extension_risk": "low|moderate|high",
  "chart_notes": "Summary of key findings"
}
````

For CSP selling, we want:

- Uptrend or strong sideways trend
- Stock NOT extended far from support
- Multiple support levels below current price
- Fib confluence zones that could provide support
  """

@dataclass
class ChartAnalyst:
    """Chart analysis agent using technical analysis tools."""

    model: str = "anthropic/claude-sonnet-4-20250514"  # LiteLLM model string
    max_iterations: int = 15
    verbose: bool = False

    async def analyze(
        self,
        symbol: str,
        timeframe: str = "daily",
        depth: str = "standard",
        heartbeat_fn: Optional[Callable[[], Awaitable[None]]] = None,
    ) -> ChartAnalysisResult:
        """
        Analyze a stock chart.

        Args:
            symbol: Stock ticker
            timeframe: "intraday", "daily", or "weekly"
            depth: "quick", "standard", or "deep"
            heartbeat_fn: Optional heartbeat callback

        Returns:
            Structured chart analysis result
        """
        # Adjust iterations based on depth
        max_iter = {
            "quick": 8,
            "standard": 12,
            "deep": 20,
        }.get(depth, 12)

        initial_message = f"""Analyze the chart for {symbol}.

Timeframe focus: {timeframe}
Analysis depth: {depth}

Please identify:

1. Current trend direction and quality
2. Key support levels (with Fibonacci and technical analysis)
3. Key resistance levels
4. Whether the stock is extended or has room to fall
5. Overall recommendation for selling cash-secured puts

Use your tools to gather data and generate a chart for visual confirmation."""

        result = await run_agentic_loop(
            model=self.model,
            system_prompt=CHART_ANALYST_SYSTEM_PROMPT,
            tools=CHART_TOOLS,
            initial_message=initial_message,
            tool_executor=execute_chart_tool,
            max_iterations=max_iter,
            heartbeat_fn=heartbeat_fn,
            verbose=self.verbose,
        )

        return self._parse_result(symbol, result)

    def _parse_result(
        self,
        symbol: str,
        result: AgenticLoopResult,
    ) -> ChartAnalysisResult:
        """Parse the agent's final response into structured result."""
        import json
        import re

        text = result.final_response

        # Try to extract JSON from response
        json_match = re.search(r"```json\s*(.*?)\s*```", text, re.DOTALL)
        if json_match:
            try:
                data = json.loads(json_match.group(1))
                return ChartAnalysisResult(
                    symbol=symbol,
                    recommendation=data.get("recommendation", "neutral"),
                    trend_direction=data.get("trend_direction", "sideways"),
                    trend_quality=data.get("trend_quality", "moderate"),
                    support_levels=data.get("support_levels", []),
                    resistance_levels=data.get("resistance_levels", []),
                    fib_confluence_zones=data.get("fib_confluence_zones", []),
                    extension_risk=data.get("extension_risk", "moderate"),
                    chart_notes=data.get("chart_notes", text),
                    tool_calls_made=result.tool_calls_made,
                )
            except json.JSONDecodeError:
                pass

        # Fallback: return with raw text as notes
        return ChartAnalysisResult(
            symbol=symbol,
            recommendation="neutral",
            trend_direction="sideways",
            trend_quality="moderate",
            support_levels=[],
            resistance_levels=[],
            fib_confluence_zones=[],
            extension_risk="moderate",
            chart_notes=text,
            tool_calls_made=result.tool_calls_made,
        )

    def result_to_context(self, result: ChartAnalysisResult) -> dict:
        """Convert chart result to context dict for passing to options analyst."""
        return {
            "trend_direction": result.trend_direction,
            "trend_quality": result.trend_quality,
            "support_levels": result.support_levels,
            "resistance_levels": result.resistance_levels,
            "fib_confluence_zones": result.fib_confluence_zones,
            "extension_risk": result.extension_risk,
            "chart_notes": result.chart_notes,
        }

````

## Options Analyst Agent

Specializes in options analysis - Greeks, strike selection, IV/HV evaluation, and premium optimization.

```python
# agents/options_analyst.py
from dataclasses import dataclass
from typing import Optional, Callable, Awaitable, Dict, Any

from .agentic_loop import run_agentic_loop, AgenticLoopResult
from tools.options_tools import OPTIONS_TOOLS, execute_options_tool
from models.analysis import OptionsAnalysisResult

OPTIONS_ANALYST_SYSTEM_PROMPT = """You are an Options Analyst specializing in strike selection and premium analysis.

Your job is to find optimal options contracts based on:
1. Greek analysis (delta, gamma, theta, vega)
2. IV/HV comparison (implied vs historical volatility)
3. Premium quality (ROC - return on capital)
4. Liquidity (bid-ask spread, volume, open interest)
5. Technical support levels from chart analysis

TOOLS AVAILABLE:
- get_option_chain: Fetch the full options chain
- get_option_greeks: Get Greeks for specific contracts
- calculate_iv_hv: Compare implied to historical volatility
- calculate_roc: Calculate return on capital for a contract
- filter_options: Filter options by criteria (delta, DTE, etc.)

ANALYSIS APPROACH:
1. Review the chart context (support levels, trend) if provided
2. Fetch the option chain for relevant expirations (14-45 DTE typically)
3. Filter for appropriate delta range (typically 0.15-0.30 for CSPs)
4. Calculate IV/HV ratio to assess premium richness
5. Evaluate specific strikes near support levels
6. Calculate ROC for best candidates
7. Check liquidity metrics

OUTPUT FORMAT:
Your final response MUST include a JSON block with this structure:
```json
{
  "recommendation": "select|reject",
  "best_strike": 95.0,
  "best_expiration": "2024-02-16",
  "dte": 21,
  "premium": 1.25,
  "weekly_roc": 0.65,
  "annualized_roc": 33.8,
  "delta": 0.22,
  "gamma": 0.015,
  "theta": 0.05,
  "iv_hv_ratio": 1.15,
  "liquidity_score": "good",
  "alternative_strikes": [
    {"strike": 92.5, "expiration": "2024-02-16", "roc": 0.55, "delta": 0.18}
  ],
  "rationale": "Strike at $95 aligns with 50% Fib support, delta 0.22 gives 78% POP...",
  "options_notes": "IV elevated at 35% vs 28% HV, good premium environment"
}
````

For CSP selling, we want:

- Delta between 0.15-0.30 (70-85% probability of profit)
- Strike at or below key support levels
- IV >= HV (rich premiums)
- Good liquidity (tight spreads, volume)
- Weekly ROC > 0.5% (target)
  """

@dataclass
class OptionsAnalyst:
    """Options analysis agent for strike selection and Greeks evaluation."""

    model: str = "anthropic/claude-sonnet-4-20250514"  # LiteLLM model string
    max_iterations: int = 12
    verbose: bool = False

    async def analyze(
        self,
        symbol: str,
        strategy: str = "csp",
        chart_context: Optional[Dict[str, Any]] = None,
        constraints: Optional[Dict[str, Any]] = None,
        heartbeat_fn: Optional[Callable[[], Awaitable[None]]] = None,
    ) -> OptionsAnalysisResult:
        """
        Analyze options for a symbol.

        Args:
            symbol: Stock ticker
            strategy: "csp", "covered_call", etc.
            chart_context: Context from chart analysis
            constraints: Optional constraints (max_delta, min_roc, etc.)
            heartbeat_fn: Optional heartbeat callback

        Returns:
            Structured options analysis result
        """
        # Build context section
        context_text = ""
        if chart_context:
            context_text = f"""

CHART CONTEXT (from Chart Analyst):

- Trend: {chart_context.get('trend_direction', 'unknown')} ({chart_context.get('trend_quality', 'unknown')})
- Support levels: {chart_context.get('support_levels', [])}
- Fib confluence zones: {chart_context.get('fib_confluence_zones', [])}
- Extension risk: {chart_context.get('extension_risk', 'unknown')}
- Notes: {chart_context.get('chart_notes', '')}
  """

        constraints_text = ""
        if constraints:
            constraints_text = f"""

  CONSTRAINTS:

- Max delta: {constraints.get('max_delta', 0.30)}
- Min weekly ROC: {constraints.get('min_roc', 0.5)}%
- DTE range: {constraints.get('dte_min', 14)}-{constraints.get('dte_max', 45)} days
  """

        initial_message = f"""Analyze options for {symbol} for {strategy.upper()} strategy.

  {context_text}
  {constraints_text}

Find the optimal strike and expiration that:

1. Aligns with support levels (if chart context provided)
2. Meets delta requirements (0.15-0.30 for CSP)
3. Has good premium (ROC)
4. Has acceptable liquidity

Use your tools to explore the options chain and find the best opportunity."""

        result = await run_agentic_loop(
            model=self.model,
            system_prompt=OPTIONS_ANALYST_SYSTEM_PROMPT,
            tools=OPTIONS_TOOLS,
            initial_message=initial_message,
            tool_executor=execute_options_tool,
            max_iterations=self.max_iterations,
            heartbeat_fn=heartbeat_fn,
            verbose=self.verbose,
        )

        return self._parse_result(symbol, result)

    def _parse_result(
        self,
        symbol: str,
        result: AgenticLoopResult,
    ) -> OptionsAnalysisResult:
        """Parse the agent's final response into structured result."""
        import json
        import re

        text = result.final_response

        json_match = re.search(r"```json\s*(.*?)\s*```", text, re.DOTALL)
        if json_match:
            try:
                data = json.loads(json_match.group(1))
                return OptionsAnalysisResult(
                    symbol=symbol,
                    recommendation=data.get("recommendation", "reject"),
                    best_strike=data.get("best_strike"),
                    best_expiration=data.get("best_expiration"),
                    dte=data.get("dte"),
                    premium=data.get("premium"),
                    weekly_roc=data.get("weekly_roc"),
                    annualized_roc=data.get("annualized_roc"),
                    delta=data.get("delta"),
                    gamma=data.get("gamma"),
                    theta=data.get("theta"),
                    iv_hv_ratio=data.get("iv_hv_ratio"),
                    liquidity_score=data.get("liquidity_score", "unknown"),
                    alternative_strikes=data.get("alternative_strikes", []),
                    rationale=data.get("rationale", ""),
                    options_notes=data.get("options_notes", text),
                    tool_calls_made=result.tool_calls_made,
                )
            except json.JSONDecodeError:
                pass

        return OptionsAnalysisResult(
            symbol=symbol,
            recommendation="reject",
            options_notes=text,
            tool_calls_made=result.tool_calls_made,
        )

````

## Research Analyst Agent

Specializes in fundamental analysis - news, earnings, short interest, and red flag detection.

```python
# agents/research_analyst.py
from dataclasses import dataclass
from typing import Optional, Callable, Awaitable, List

from .agentic_loop import run_agentic_loop, AgenticLoopResult
from tools.research_tools import RESEARCH_TOOLS, execute_research_tool
from models.analysis import ResearchAnalysisResult

RESEARCH_ANALYST_SYSTEM_PROMPT = """You are a Research Analyst specializing in fundamental analysis and risk assessment.

Your job is to identify red flags that could impact an options trade:
1. Recent significant news (earnings, lawsuits, FDA decisions, etc.)
2. Upcoming earnings within the option's DTE
3. Short interest levels
4. Analyst rating changes
5. Insider trading activity
6. SEC filings (8-K events)

TOOLS AVAILABLE:
- get_news: Get recent news articles
- get_earnings_dates: Get upcoming earnings
- get_short_interest: Get short interest data
- get_analyst_ratings: Get analyst ratings and changes
- get_sec_filings: Get recent SEC filings

RISK ASSESSMENT:
For options trades, especially CSPs, we need to be aware of:
- Earnings risk: Don't sell puts that expire after earnings unless intended
- News risk: Major negative news could cause a gap down
- Short squeeze risk: High short interest could cause volatile moves
- Regulatory risk: FDA decisions, legal outcomes, etc.

OUTPUT FORMAT:
Your final response MUST include a JSON block with this structure:
```json
{
  "recommendation": "pass|reject",
  "news_risk": "low|moderate|high",
  "earnings_risk": "low|moderate|high",
  "short_interest_risk": "low|moderate|high",
  "research_notes": "Summary of key findings and any red flags"
}
````

Be CONSERVATIVE - when in doubt, flag as risk. Better to skip a trade than take unnecessary risk.
"""

@dataclass
class ResearchAnalyst:
    """Research analysis agent for fundamentals and red flag detection."""

    model: str = "anthropic/claude-sonnet-4-20250514"  # LiteLLM model string
    max_iterations: int = 8
    verbose: bool = False

    async def analyze(
        self,
        symbol: str,
        focus: Optional[List[str]] = None,
        heartbeat_fn: Optional[Callable[[], Awaitable[None]]] = None,
    ) -> ResearchAnalysisResult:
        """
        Analyze research/fundamentals for a symbol.

        Args:
            symbol: Stock ticker
            focus: Optional list of focus areas
            heartbeat_fn: Optional heartbeat callback

        Returns:
            Structured research analysis result
        """
        focus_areas = focus or ["news", "earnings", "short_interest"]

        initial_message = f"""Research {symbol} for potential red flags.

Focus areas: {', '.join(focus_areas)}

Check for:

1. Any recent significant news that could impact the stock
2. Upcoming earnings dates
3. Short interest levels
4. Any other red flags for options trading

This is for a cash-secured put trade, so we need to know about risks of the stock moving down significantly."""

        result = await run_agentic_loop(
            model=self.model,
            system_prompt=RESEARCH_ANALYST_SYSTEM_PROMPT,
            tools=RESEARCH_TOOLS,
            initial_message=initial_message,
            tool_executor=execute_research_tool,
            max_iterations=self.max_iterations,
            heartbeat_fn=heartbeat_fn,
            verbose=self.verbose,
        )

        return self._parse_result(symbol, result)

    def _parse_result(
        self,
        symbol: str,
        result: AgenticLoopResult,
    ) -> ResearchAnalysisResult:
        """Parse the agent's final response into structured result."""
        import json
        import re

        text = result.final_response

        json_match = re.search(r"```json\s*(.*?)\s*```", text, re.DOTALL)
        if json_match:
            try:
                data = json.loads(json_match.group(1))
                return ResearchAnalysisResult(
                    symbol=symbol,
                    recommendation=data.get("recommendation", "pass"),
                    news_risk=data.get("news_risk", "low"),
                    earnings_risk=data.get("earnings_risk", "low"),
                    short_interest_risk=data.get("short_interest_risk", "low"),
                    research_notes=data.get("research_notes", text),
                )
            except json.JSONDecodeError:
                pass

        return ResearchAnalysisResult(
            symbol=symbol,
            recommendation="pass",
            news_risk="unknown",
            earnings_risk="unknown",
            short_interest_risk="unknown",
            research_notes=text,
        )

````

## Tool Definitions

### Chart Analysis Tools

Tools are defined in OpenAI-compatible format (which LiteLLM uses):

```python
# tools/chart_tools.py
from typing import Dict, Any, List

CHART_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_price_history",
            "description": "Fetch historical OHLCV data for a symbol",
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {"type": "string", "description": "Stock ticker"},
                    "period": {
                        "type": "string",
                        "enum": ["1mo", "3mo", "6mo", "1y", "2y"],
                        "description": "Time period"
                    },
                    "interval": {
                        "type": "string",
                        "enum": ["1d", "1wk"],
                        "description": "Bar interval"
                    }
                },
                "required": ["symbol"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "calculate_swing_points",
            "description": "Identify swing highs and lows in price data",
            "parameters": {
                "type": "object",
                "properties": {
                    "bars": {
                        "type": "array",
                        "description": "OHLCV bars from get_price_history"
                    },
                    "lookback": {
                        "type": "integer",
                        "description": "Bars to look back for swing detection",
                        "default": 5
                    }
                },
                "required": ["bars"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "calculate_fib_levels",
            "description": "Calculate Fibonacci retracement levels from swing points",
            "parameters": {
                "type": "object",
                "properties": {
                    "swing_high": {"type": "number", "description": "Swing high price"},
                    "swing_low": {"type": "number", "description": "Swing low price"},
                    "direction": {
                        "type": "string",
                        "enum": ["up", "down"],
                        "description": "Trend direction for retracement"
                    }
                },
                "required": ["swing_high", "swing_low", "direction"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "find_support_resistance",
            "description": "Find support and resistance zones from price history",
            "parameters": {
                "type": "object",
                "properties": {
                    "bars": {"type": "array", "description": "OHLCV bars"},
                    "num_levels": {
                        "type": "integer",
                        "description": "Number of levels to find",
                        "default": 5
                    }
                },
                "required": ["bars"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "calculate_trendline",
            "description": "Fit a trendline to price data",
            "parameters": {
                "type": "object",
                "properties": {
                    "bars": {"type": "array", "description": "OHLCV bars"},
                    "type": {
                        "type": "string",
                        "enum": ["support", "resistance"],
                        "description": "Type of trendline"
                    }
                },
                "required": ["bars", "type"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "render_chart",
            "description": "Generate a chart image with annotations",
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {"type": "string"},
                    "bars": {"type": "array", "description": "OHLCV bars"},
                    "annotations": {
                        "type": "object",
                        "properties": {
                            "support_levels": {"type": "array"},
                            "resistance_levels": {"type": "array"},
                            "fib_levels": {"type": "object"},
                            "trendlines": {"type": "array"}
                        }
                    }
                },
                "required": ["symbol", "bars"]
            }
        }
    }
]


async def execute_chart_tool(name: str, inputs: Dict[str, Any]) -> Dict[str, Any]:
    """Execute a chart analysis tool."""
    from services.yahoo import YahooFinanceClient

    if name == "get_price_history":
        client = YahooFinanceClient()
        return await client.get_price_history(
            inputs["symbol"],
            period=inputs.get("period", "6mo"),
            interval=inputs.get("interval", "1d"),
        )

    elif name == "calculate_swing_points":
        return _calculate_swing_points(
            inputs["bars"],
            lookback=inputs.get("lookback", 5),
        )

    elif name == "calculate_fib_levels":
        return _calculate_fib_levels(
            inputs["swing_high"],
            inputs["swing_low"],
            inputs["direction"],
        )

    elif name == "find_support_resistance":
        return _find_support_resistance(
            inputs["bars"],
            num_levels=inputs.get("num_levels", 5),
        )

    elif name == "calculate_trendline":
        return _calculate_trendline(
            inputs["bars"],
            inputs["type"],
        )

    elif name == "render_chart":
        return await _render_chart(
            inputs["symbol"],
            inputs["bars"],
            inputs.get("annotations", {}),
        )

    return {"error": f"Unknown tool: {name}"}


def _calculate_swing_points(bars: List[Dict], lookback: int = 5) -> Dict[str, Any]:
    """Identify swing highs and lows."""
    if len(bars) < lookback * 2 + 1:
        return {"swing_points": [], "error": "Not enough data"}

    swing_points = []
    highs = [b["high"] for b in bars]
    lows = [b["low"] for b in bars]

    for i in range(lookback, len(bars) - lookback):
        # Check for swing high
        if highs[i] == max(highs[i-lookback:i+lookback+1]):
            swing_points.append({
                "type": "high",
                "price": highs[i],
                "index": i,
                "date": bars[i]["timestamp"],
            })
        # Check for swing low
        if lows[i] == min(lows[i-lookback:i+lookback+1]):
            swing_points.append({
                "type": "low",
                "price": lows[i],
                "index": i,
                "date": bars[i]["timestamp"],
            })

    return {"swing_points": swing_points}


def _calculate_fib_levels(
    swing_high: float,
    swing_low: float,
    direction: str,
) -> Dict[str, Any]:
    """Calculate Fibonacci retracement levels."""
    diff = swing_high - swing_low

    if direction == "up":
        # Retracement from high
        levels = {
            "0%": swing_high,
            "23.6%": swing_high - diff * 0.236,
            "38.2%": swing_high - diff * 0.382,
            "50%": swing_high - diff * 0.5,
            "61.8%": swing_high - diff * 0.618,
            "78.6%": swing_high - diff * 0.786,
            "100%": swing_low,
        }
    else:
        # Retracement from low
        levels = {
            "0%": swing_low,
            "23.6%": swing_low + diff * 0.236,
            "38.2%": swing_low + diff * 0.382,
            "50%": swing_low + diff * 0.5,
            "61.8%": swing_low + diff * 0.618,
            "78.6%": swing_low + diff * 0.786,
            "100%": swing_high,
        }

    return {
        "levels": levels,
        "swing_high": swing_high,
        "swing_low": swing_low,
        "direction": direction,
    }


def _find_support_resistance(
    bars: List[Dict],
    num_levels: int = 5,
) -> Dict[str, Any]:
    """Find support and resistance zones using clustering."""
    # Get all significant prices
    prices = []
    for b in bars:
        prices.extend([b["high"], b["low"]])

    # Simple clustering: group nearby prices
    sorted_prices = sorted(set(prices))
    current_price = bars[-1]["close"]

    support = []
    resistance = []

    # Group into zones (within 1% of each other)
    zones = []
    zone_start = sorted_prices[0]
    zone_prices = [zone_start]

    for price in sorted_prices[1:]:
        if (price - zone_start) / zone_start < 0.01:
            zone_prices.append(price)
        else:
            zones.append({
                "price": sum(zone_prices) / len(zone_prices),
                "touches": len(zone_prices),
            })
            zone_start = price
            zone_prices = [price]

    zones.append({
        "price": sum(zone_prices) / len(zone_prices),
        "touches": len(zone_prices),
    })

    # Sort by touches (strength)
    zones.sort(key=lambda x: x["touches"], reverse=True)

    # Classify as support or resistance
    for zone in zones[:num_levels * 2]:
        strength = "strong" if zone["touches"] >= 4 else \
                   "moderate" if zone["touches"] >= 2 else "weak"

        level = {
            "price": round(zone["price"], 2),
            "strength": strength,
            "touches": zone["touches"],
        }

        if zone["price"] < current_price:
            support.append(level)
        else:
            resistance.append(level)

    return {
        "support": support[:num_levels],
        "resistance": resistance[:num_levels],
        "current_price": current_price,
    }
````

### Options Analysis Tools

```python
# tools/options_tools.py
from typing import Dict, Any, List, Optional

OPTIONS_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_option_chain",
            "description": "Fetch option chain for a symbol",
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {"type": "string"},
                    "dte_min": {"type": "integer", "default": 7},
                    "dte_max": {"type": "integer", "default": 60}
                },
                "required": ["symbol"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_option_greeks",
            "description": "Get Greeks for specific option contracts",
            "parameters": {
                "type": "object",
                "properties": {
                    "option_symbols": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of option symbols"
                    }
                },
                "required": ["option_symbols"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "calculate_iv_hv",
            "description": "Calculate IV/HV ratio for a symbol",
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {"type": "string"},
                    "hv_period": {"type": "integer", "default": 20}
                },
                "required": ["symbol"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "calculate_roc",
            "description": "Calculate return on capital for an option",
            "parameters": {
                "type": "object",
                "properties": {
                    "premium": {"type": "number"},
                    "strike": {"type": "number"},
                    "dte": {"type": "integer"}
                },
                "required": ["premium", "strike", "dte"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "filter_options",
            "description": "Filter options by criteria",
            "parameters": {
                "type": "object",
                "properties": {
                    "options": {"type": "array"},
                    "min_delta": {"type": "number"},
                    "max_delta": {"type": "number"},
                    "min_roc": {"type": "number"},
                    "option_type": {"type": "string", "enum": ["put", "call"]}
                },
                "required": ["options"]
            }
        }
    }
]


async def execute_options_tool(name: str, inputs: Dict[str, Any]) -> Dict[str, Any]:
    """Execute an options analysis tool."""
    from services.tastytrade import TastyTradeClient

    if name == "get_option_chain":
        client = await TastyTradeClient.get_instance()
        chain = await client.get_option_chain(inputs["symbol"])

        # Filter by DTE
        dte_min = inputs.get("dte_min", 7)
        dte_max = inputs.get("dte_max", 60)

        filtered = {
            "symbol": chain["symbol"],
            "expirations": [
                exp for exp in chain["expirations"]
                if dte_min <= exp["dte"] <= dte_max
            ]
        }

        return filtered

    elif name == "get_option_greeks":
        client = await TastyTradeClient.get_instance()
        stream_data = await client.stream_option_data(inputs["option_symbols"])

        results = []
        for sym, data in stream_data.items():
            greeks = data.get("greeks")
            quote = data.get("quote")

            if greeks:
                results.append({
                    "symbol": sym,
                    "delta": float(greeks.delta) if greeks.delta else None,
                    "gamma": float(greeks.gamma) if greeks.gamma else None,
                    "theta": float(greeks.theta) if greeks.theta else None,
                    "vega": float(greeks.vega) if greeks.vega else None,
                    "iv": float(greeks.volatility) if greeks.volatility else None,
                    "bid": float(quote.bid_price) if quote and quote.bid_price else None,
                    "ask": float(quote.ask_price) if quote and quote.ask_price else None,
                })

        return {"options": results}

    elif name == "calculate_iv_hv":
        from services.yahoo import YahooFinanceClient
        from services.tastytrade import TastyTradeClient

        # Get HV from Yahoo
        yahoo = YahooFinanceClient()
        hv = yahoo.calculate_historical_volatility(
            inputs["symbol"],
            period=inputs.get("hv_period", 20),
        )

        # Get IV from TastyTrade market metrics
        tt = await TastyTradeClient.get_instance()
        metrics = await tt.get_market_metrics([inputs["symbol"]])
        metric = metrics.get(inputs["symbol"])

        iv = float(metric.implied_volatility_index) if metric and metric.implied_volatility_index else None

        iv_hv_ratio = (iv / hv) if iv and hv else None

        return {
            "symbol": inputs["symbol"],
            "iv": round(iv * 100, 1) if iv else None,
            "hv": round(hv * 100, 1) if hv else None,
            "iv_hv_ratio": round(iv_hv_ratio, 2) if iv_hv_ratio else None,
            "iv_rank": str(metric.implied_volatility_index_rank) if metric else None,
        }

    elif name == "calculate_roc":
        premium = inputs["premium"]
        strike = inputs["strike"]
        dte = inputs["dte"]

        # Calculate ROC
        roc = (premium / strike) * 100  # As percentage
        weekly_roc = roc * (7 / dte) if dte > 0 else 0
        annualized_roc = roc * (365 / dte) if dte > 0 else 0

        return {
            "roc": round(roc, 2),
            "weekly_roc": round(weekly_roc, 2),
            "annualized_roc": round(annualized_roc, 1),
        }

    elif name == "filter_options":
        options = inputs["options"]
        filtered = []

        for opt in options:
            delta = abs(opt.get("delta", 0))

            if inputs.get("min_delta") and delta < inputs["min_delta"]:
                continue
            if inputs.get("max_delta") and delta > inputs["max_delta"]:
                continue
            if inputs.get("option_type"):
                # Would need option type in data
                pass

            filtered.append(opt)

        return {"options": filtered}

    return {"error": f"Unknown tool: {name}"}
```

## Context Passing Between Agents

The orchestrator passes context from earlier agents to later ones:

```python
# agents/orchestrator.py (context passing example)
from dataclasses import dataclass
from typing import Optional

from .chart_analyst import ChartAnalyst
from .options_analyst import OptionsAnalyst
from .research_analyst import ResearchAnalyst
from models.analysis import FullAnalysisResult


@dataclass
class Orchestrator:
    """Multi-agent orchestrator for full analysis pipeline."""

    orchestrator_model: str = "anthropic/claude-sonnet-4-20250514"  # For synthesis
    analyst_model: str = "anthropic/claude-sonnet-4-20250514"  # For sub-agents
    verbose: bool = False

    def __post_init__(self):
        self.chart_analyst = ChartAnalyst(model=self.analyst_model, verbose=self.verbose)
        self.options_analyst = OptionsAnalyst(model=self.analyst_model, verbose=self.verbose)
        self.research_analyst = ResearchAnalyst(model=self.analyst_model, verbose=self.verbose)

    async def run_full_analysis(self, symbol: str) -> FullAnalysisResult:
        # Step 1: Chart Analysis
        chart_result = await self.chart_analyst.analyze(symbol)

        if chart_result.recommendation == "reject":
            return FullAnalysisResult(
                symbol=symbol,
                overall_recommendation="reject",
                reject_reason=f"Chart: {chart_result.chart_notes}",
                chart_analysis=chart_result,
            )

        # Step 2: Options Analysis WITH chart context
        # This allows the options analyst to:
        # - Target strikes near support levels
        # - Factor in trend quality for delta selection
        # - Consider Fib confluence zones
        chart_context = self.chart_analyst.result_to_context(chart_result)

        options_result = await self.options_analyst.analyze(
            symbol,
            strategy="csp",
            chart_context=chart_context,
        )

        if options_result.recommendation == "reject":
            return FullAnalysisResult(
                symbol=symbol,
                overall_recommendation="reject",
                chart_analysis=chart_result,
                options_analysis=options_result,
                reject_reason=f"Options: {options_result.options_notes}",
            )

        # Step 3: Research Analysis
        research_result = await self.research_analyst.analyze(symbol)

        if research_result.recommendation == "reject":
            return FullAnalysisResult(
                symbol=symbol,
                overall_recommendation="reject",
                chart_analysis=chart_result,
                options_analysis=options_result,
                research_analysis=research_result,
                reject_reason=f"Research: {research_result.research_notes}",
            )

        # Step 4: Synthesize final recommendation
        synthesized = self.synthesize_recommendation(chart_result, options_result, research_result)

        return FullAnalysisResult(
            symbol=symbol,
            overall_recommendation="select",
            chart_analysis=chart_result,
            options_analysis=options_result,
            research_analysis=research_result,
            synthesized_rationale=synthesized["rationale"],
            suggested_position=synthesized["suggested_position"],
        )
```

## Result Synthesis

Combining results from all agents into a final recommendation:

```python
# agents/orchestrator.py
def synthesize_recommendation(
    self,
    chart: ChartAnalysisResult,
    options: OptionsAnalysisResult,
    research: ResearchAnalysisResult,
) -> Dict[str, Any]:
    """Synthesize findings from all agents into final recommendation."""

    # Build rationale
    rationale_parts = []

    # Chart factors
    if chart.trend_quality == "strong":
        rationale_parts.append("Strong uptrend provides momentum")
    elif chart.trend_quality == "moderate":
        rationale_parts.append("Moderate uptrend with some pullback risk")

    if chart.support_levels:
        top_support = chart.support_levels[0]
        rationale_parts.append(
            f"Key support at ${top_support['price']} ({top_support['strength']})"
        )

    if chart.fib_confluence_zones:
        zone = chart.fib_confluence_zones[0]
        rationale_parts.append(f"Fib confluence at ${zone['price']}")

    # Options factors
    if options.iv_hv_ratio:
        if options.iv_hv_ratio > 1.2:
            rationale_parts.append("IV elevated vs HV (rich premiums)")
        elif options.iv_hv_ratio >= 0.9:
            rationale_parts.append("IV/HV near fair value")

    if options.weekly_roc:
        rationale_parts.append(f"ROC: {options.weekly_roc}%/week")

    # Research factors
    if research.news_risk == "high":
        rationale_parts.append("CAUTION: elevated news risk")
    if research.earnings_risk == "high":
        rationale_parts.append("CAUTION: earnings within DTE")

    # Risk factors
    risk_factors = []
    if chart.extension_risk == "high":
        risk_factors.append("Stock extended from support")
    if research.short_interest_risk == "high":
        risk_factors.append("High short interest")

    return {
        "rationale": ". ".join(rationale_parts),
        "risk_factors": risk_factors,
        "suggested_position": {
            "strategy": "csp",
            "strike": options.best_strike,
            "expiration": options.best_expiration,
            "delta": options.delta,
            "weekly_roc": options.weekly_roc,
        },
    }
```

## Agent Activities for Temporal

Wrapping agents as Temporal activities:

```python
# activities/chart.py
from temporalio import activity
from agents.chart_analyst import ChartAnalyst
from models.analysis import ChartAnalysisParams, ChartAnalysisResult


@activity.defn
async def chart_analysis_activity(params: ChartAnalysisParams) -> ChartAnalysisResult:
    """Run chart analysis as a Temporal activity."""

    # Model is configured on the agent class
    # LiteLLM reads API keys from environment automatically
    analyst = ChartAnalyst(
        model=params.model or "anthropic/claude-sonnet-4-20250514",
        verbose=False,
    )

    async def heartbeat():
        activity.heartbeat()

    result = await analyst.analyze(
        symbol=params.symbol,
        timeframe=params.timeframe,
        depth=params.analysis_depth,
        heartbeat_fn=heartbeat,
    )

    return result
```

## Model Configuration

Models are configured directly on agent classes. LiteLLM reads API keys from standard environment variables automatically:

```python
# Example: Using different providers

# Default: Anthropic Claude
analyst = ChartAnalyst(model="anthropic/claude-sonnet-4-20250514")

# OpenAI GPT-4o
analyst = ChartAnalyst(model="openai/gpt-4o")

# Google Gemini
analyst = ChartAnalyst(model="gemini/gemini-1.5-pro")

# AWS Bedrock
analyst = ChartAnalyst(model="bedrock/anthropic.claude-3-sonnet")

# Azure OpenAI
analyst = ChartAnalyst(model="azure/gpt-4")
```

### Required Environment Variables

LiteLLM reads API keys from standard environment variables:

```bash
# Anthropic
ANTHROPIC_API_KEY=sk-ant-...

# OpenAI
OPENAI_API_KEY=sk-...

# Google
GOOGLE_API_KEY=...
# or
GEMINI_API_KEY=...

# AWS Bedrock
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
AWS_REGION_NAME=us-east-1

# Azure OpenAI
AZURE_API_KEY=...
AZURE_API_BASE=https://your-resource.openai.azure.com/
AZURE_API_VERSION=2024-02-15-preview
```

## LiteLLM Configuration (Optional)

For advanced features like fallbacks and routing:

```python
# config/litellm_config.py
import litellm

# Enable verbose logging in development
litellm.set_verbose = False  # Set to True for debugging

# Configure fallbacks (optional)
litellm.fallbacks = [
    {
        "anthropic/claude-sonnet-4-20250514": [
            "openai/gpt-4o",
            "gemini/gemini-1.5-pro"
        ]
    }
]

# Configure retries
litellm.num_retries = 3

# Configure timeout
litellm.request_timeout = 300  # 5 minutes
```

## Error Handling

LiteLLM provides unified exception handling across providers:

```python
from litellm import RateLimitError, AuthenticationError, APIConnectionError

async def safe_completion(model: str, messages: list, tools: list = None):
    """Make a completion call with error handling."""
    try:
        return await acompletion(
            model=model,
            messages=messages,
            tools=tools,
        )
    except RateLimitError as e:
        # LiteLLM handles rate limiting with automatic retries
        # This is raised after retries are exhausted
        raise RetryableError(f"Rate limited: {e}")
    except AuthenticationError as e:
        # Invalid or missing API key
        raise NonRetryableError(f"Authentication failed: {e}")
    except APIConnectionError as e:
        # Network error - may be retryable
        raise RetryableError(f"Connection error: {e}")
```
