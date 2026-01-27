# Document-Based Knowledge Library

## Overview

The knowledge base is a simple collection of markdown documents covering trading and investing topics. Documents are human-readable, version-controlled, and directly accessible by AI agents during analysis.

## Design Philosophy

- **Simplicity**: Plain markdown files, no database schemas or complex infrastructure
- **Human-readable**: Documents are written for both AI and human consumption
- **Version-controlled**: All knowledge tracked in git alongside code
- **Extensible**: Add new documents by creating markdown files
- **Cross-referenced**: Documents link to related topics for context

## Directory Structure

```
knowledge/
├── options/
│   ├── strategies/
│   │   ├── cash-secured-put.md
│   │   ├── covered-call.md
│   │   ├── wheel.md
│   │   ├── iron-condor.md
│   │   ├── iron-butterfly.md
│   │   ├── jade-lizard.md
│   │   ├── bull-put-spread.md
│   │   ├── bear-call-spread.md
│   │   ├── long-straddle.md
│   │   ├── long-strangle.md
│   │   ├── protective-put.md
│   │   ├── collar.md
│   │   └── calendar-spread.md
│   ├── greeks/
│   │   ├── delta.md
│   │   ├── gamma.md
│   │   ├── theta.md
│   │   ├── vega.md
│   │   └── rho.md
│   └── trade-management/
│       ├── rolling-positions.md
│       ├── adjustments.md
│       ├── exit-strategies.md
│       └── assignment-handling.md
├── fundamentals/
│   ├── financial-statements.md
│   ├── valuation-metrics.md
│   ├── earnings-analysis.md
│   ├── sector-analysis.md
│   └── dividend-analysis.md
├── technical-analysis/
│   ├── chart-patterns.md
│   ├── support-resistance.md
│   ├── trend-analysis.md
│   ├── price-action.md
│   └── indicators/
│       ├── moving-averages.md
│       ├── rsi.md
│       ├── macd.md
│       ├── bollinger-bands.md
│       └── volume-indicators.md
├── market-psychology/
│   ├── behavioral-biases.md
│   ├── sentiment-indicators.md
│   ├── trading-discipline.md
│   ├── risk-of-ruin.md
│   └── emotional-management.md
├── risk-management/
│   ├── position-sizing.md
│   ├── portfolio-allocation.md
│   ├── correlation.md
│   ├── max-drawdown.md
│   └── hedging-strategies.md
└── market-mechanics/
    ├── order-types.md
    ├── market-structure.md
    ├── options-settlement.md
    ├── margin-requirements.md
    └── tax-considerations.md
```

## Document Format

Each markdown document follows a consistent template with YAML frontmatter for metadata.

### Template Structure

```markdown
---
title: Document Title
category: options/strategies
tags: [income, bullish, neutral, premium-selling]
related:
  - covered-call.md
  - wheel.md
difficulty: intermediate
last_updated: 2024-01-15
---

# Document Title

## Overview

Brief description of the topic (2-3 sentences).

## Key Concepts

Core information organized in clear sections.

## When to Use

Situational guidance and ideal conditions.

## Examples

Practical examples with concrete numbers.

## Risks and Considerations

Important warnings and edge cases.

## Related Topics

- [Related Document 1](../path/to/doc.md)
- [Related Document 2](../path/to/doc.md)
```

### Example Document: Cash-Secured Put

```markdown
---
title: Cash-Secured Put (CSP)
category: options/strategies
tags: [income, bullish, neutral, premium-selling, beginner-friendly]
related:
  - covered-call.md
  - wheel.md
  - bull-put-spread.md
difficulty: beginner
last_updated: 2024-01-15
---

# Cash-Secured Put (CSP)

## Overview

A cash-secured put involves selling a put option while holding enough cash
to purchase the underlying stock if assigned. It generates income through
premium collection while positioning to buy stock at a discount.

## Key Concepts

### Position Structure
- Sell 1 put option
- Hold cash equal to (strike price × 100)

### Profit/Loss Profile
- **Max Profit**: Premium received
- **Max Loss**: Strike price - Premium (if stock goes to $0)
- **Breakeven**: Strike price - Premium received

### Ideal Conditions
- **Market Outlook**: Bullish to neutral
- **IV Environment**: High (better premiums)
- **Time Horizon**: 30-45 DTE optimal for theta decay
- **Account Type**: Works in cash, margin, and IRA accounts

## Strike Selection

| Delta | Risk/Reward | Probability OTM |
|-------|-------------|-----------------|
| 0.30  | Balanced    | ~70%            |
| 0.20  | Conservative| ~80%            |
| 0.40  | Aggressive  | ~60%            |

Choose strikes at prices you'd be happy owning the stock.

## Management Rules

### Profit Taking
- Close at 50% of max profit for capital efficiency
- Consider closing at 21 DTE if not at target

### Adjustment Triggers
- Delta exceeds 0.50 (position tested)
- Stock down more than 10%
- Fundamental thesis changes

### Rolling Guidelines
1. Roll for a credit only
2. Roll down and out when tested
3. Never roll into earnings

## Examples

### Example 1: Standard CSP
- Stock: AAPL trading at $175
- Sell: AAPL $170 Put, 45 DTE
- Premium: $3.50
- Cash required: $17,000
- Breakeven: $166.50
- Max profit: $350 (2.1% return)

### Outcomes:
- AAPL stays above $170: Keep $350 premium
- AAPL at $165 at expiration: Assigned at $170, cost basis $166.50
- AAPL drops to $160: Loss of $650 ($170 - $160 - $3.50) × 100

## Risks and Considerations

- **Assignment Risk**: May be assigned early, especially near ex-dividend
- **Downside Exposure**: Full downside risk below breakeven
- **Capital Intensive**: Ties up significant cash
- **Opportunity Cost**: Cash locked until expiration

## Related Topics

- [Covered Call](covered-call.md) - Pair with CSP for the wheel strategy
- [Wheel Strategy](wheel.md) - Combines CSP and covered calls
- [Bull Put Spread](bull-put-spread.md) - Defined-risk alternative
- [Rolling Positions](../trade-management/rolling-positions.md)
```

## AI Access Patterns

### Direct File Reading

AI agents read knowledge files directly during analysis workflows.

```python
# activities/knowledge.py
from pathlib import Path
from typing import Optional
import frontmatter

KNOWLEDGE_DIR = Path(__file__).parent.parent / "knowledge"

async def read_knowledge_document(path: str) -> dict:
    """Read a knowledge document and parse its frontmatter."""
    file_path = KNOWLEDGE_DIR / path

    if not file_path.exists():
        return {"error": f"Document not found: {path}"}

    post = frontmatter.load(file_path)
    return {
        "metadata": dict(post.metadata),
        "content": post.content,
    }

async def list_documents(category: Optional[str] = None) -> list[dict]:
    """List available knowledge documents."""
    documents = []

    search_path = KNOWLEDGE_DIR / category if category else KNOWLEDGE_DIR

    for md_file in search_path.rglob("*.md"):
        rel_path = md_file.relative_to(KNOWLEDGE_DIR)
        post = frontmatter.load(md_file)
        documents.append({
            "path": str(rel_path),
            "title": post.metadata.get("title", md_file.stem),
            "category": post.metadata.get("category"),
            "tags": post.metadata.get("tags", []),
        })

    return documents

async def search_by_tag(tag: str) -> list[dict]:
    """Find all documents with a specific tag."""
    documents = await list_documents()
    return [doc for doc in documents if tag in doc.get("tags", [])]
```

### MCP Resource Access

Expose knowledge base through MCP resources for browsing.

```typescript
// src/resources/knowledge.ts
import { Resource } from "@modelcontextprotocol/sdk/types.js";
import * as fs from "fs/promises";
import * as path from "path";
import matter from "gray-matter";

const KNOWLEDGE_DIR = path.join(__dirname, "../../knowledge");

export class KnowledgeResource {
  async listDocuments(category?: string): Promise<Resource[]> {
    const searchDir = category
      ? path.join(KNOWLEDGE_DIR, category)
      : KNOWLEDGE_DIR;

    const resources: Resource[] = [];
    await this.walkDir(searchDir, resources);
    return resources;
  }

  private async walkDir(dir: string, resources: Resource[]): Promise<void> {
    const entries = await fs.readdir(dir, { withFileTypes: true });

    for (const entry of entries) {
      const fullPath = path.join(dir, entry.name);

      if (entry.isDirectory()) {
        await this.walkDir(fullPath, resources);
      } else if (entry.name.endsWith(".md")) {
        const content = await fs.readFile(fullPath, "utf-8");
        const { data } = matter(content);
        const relPath = path.relative(KNOWLEDGE_DIR, fullPath);

        resources.push({
          uri: `knowledge://${relPath}`,
          name: data.title || entry.name,
          description: `${data.category} - ${(data.tags || []).join(", ")}`,
          mimeType: "text/markdown",
        });
      }
    }
  }

  async readDocument(uri: string): Promise<string> {
    const docPath = uri.replace("knowledge://", "");
    const fullPath = path.join(KNOWLEDGE_DIR, docPath);
    return fs.readFile(fullPath, "utf-8");
  }
}
```

### MCP Resource Registration

```typescript
// In MCP server setup
server.setRequestHandler(ListResourcesRequestSchema, async () => {
  const knowledge = new KnowledgeResource();
  const documents = await knowledge.listDocuments();

  return {
    resources: documents,
  };
});

server.setRequestHandler(ReadResourceRequestSchema, async (request) => {
  const { uri } = request.params;

  if (uri.startsWith("knowledge://")) {
    const knowledge = new KnowledgeResource();
    const content = await knowledge.readDocument(uri);

    return {
      contents: [{
        uri,
        mimeType: "text/markdown",
        text: content,
      }],
    };
  }

  // Handle other resource types...
});
```

## Optional: Embedding Index for Semantic Search

For semantic search capabilities, maintain a simple JSONL file with document embeddings.

### Index Structure

```jsonl
{"path": "options/strategies/cash-secured-put.md", "embedding": [0.123, -0.456, ...], "title": "Cash-Secured Put"}
{"path": "options/strategies/covered-call.md", "embedding": [0.234, -0.567, ...], "title": "Covered Call"}
```

### Index Generation

```python
# scripts/build_knowledge_index.py
import json
from pathlib import Path
import frontmatter
from sentence_transformers import SentenceTransformer

KNOWLEDGE_DIR = Path("knowledge")
INDEX_FILE = Path("knowledge/embeddings.jsonl")

def build_index():
    """Build embedding index for all knowledge documents."""
    model = SentenceTransformer("all-MiniLM-L6-v2")

    with open(INDEX_FILE, "w") as f:
        for md_file in KNOWLEDGE_DIR.rglob("*.md"):
            if md_file.name == "embeddings.jsonl":
                continue

            post = frontmatter.load(md_file)

            # Create text for embedding
            text = f"{post.metadata.get('title', '')}\n{post.content[:2000]}"
            embedding = model.encode(text).tolist()

            entry = {
                "path": str(md_file.relative_to(KNOWLEDGE_DIR)),
                "title": post.metadata.get("title", md_file.stem),
                "category": post.metadata.get("category"),
                "tags": post.metadata.get("tags", []),
                "embedding": embedding,
            }

            f.write(json.dumps(entry) + "\n")

    print(f"Built index with {sum(1 for _ in KNOWLEDGE_DIR.rglob('*.md'))} documents")

if __name__ == "__main__":
    build_index()
```

### Semantic Search

```python
# services/knowledge_search.py
import json
import numpy as np
from pathlib import Path
from sentence_transformers import SentenceTransformer

INDEX_FILE = Path("knowledge/embeddings.jsonl")

class KnowledgeSearch:
    def __init__(self):
        self.model = SentenceTransformer("all-MiniLM-L6-v2")
        self.index = self._load_index()

    def _load_index(self) -> list[dict]:
        """Load the embedding index."""
        if not INDEX_FILE.exists():
            return []

        with open(INDEX_FILE) as f:
            return [json.loads(line) for line in f]

    def search(self, query: str, limit: int = 5) -> list[dict]:
        """Search documents by semantic similarity."""
        query_embedding = self.model.encode(query)

        results = []
        for entry in self.index:
            doc_embedding = np.array(entry["embedding"])
            similarity = np.dot(query_embedding, doc_embedding) / (
                np.linalg.norm(query_embedding) * np.linalg.norm(doc_embedding)
            )
            results.append({
                "path": entry["path"],
                "title": entry["title"],
                "category": entry["category"],
                "tags": entry["tags"],
                "similarity": float(similarity),
            })

        results.sort(key=lambda x: x["similarity"], reverse=True)
        return results[:limit]
```

## Agent Integration

### Knowledge Lookup Tool

```python
# activities/agent_tools.py
from typing import Optional

async def lookup_knowledge(
    query: str,
    category: Optional[str] = None,
) -> dict:
    """
    Tool for AI agents to look up trading knowledge.

    Args:
        query: What to search for (e.g., "how to roll a put option")
        category: Optional category filter (e.g., "options/strategies")

    Returns:
        Relevant knowledge documents with content
    """
    search = KnowledgeSearch()
    results = search.search(query, limit=3)

    if category:
        results = [r for r in results if r["category"].startswith(category)]

    # Load full content for top results
    enriched = []
    for result in results[:3]:
        doc = await read_knowledge_document(result["path"])
        enriched.append({
            **result,
            "content": doc["content"][:3000],  # Limit content length
        })

    return {"documents": enriched}
```

### Usage in Analysis Workflows

```python
# Example: Options analyst uses knowledge base
async def analyze_options_position(symbol: str, position: dict) -> dict:
    """Analyze an options position using knowledge base guidance."""

    # Look up relevant strategy knowledge
    strategy_name = position.get("strategy", "cash-secured-put")
    knowledge = await lookup_knowledge(
        f"how to manage {strategy_name}",
        category="options",
    )

    # Use knowledge in analysis prompt
    prompt = f"""
    Analyze this options position:
    {json.dumps(position, indent=2)}

    Reference material on {strategy_name}:
    {knowledge['documents'][0]['content']}

    Provide management recommendations based on the guidelines above.
    """

    # Continue with AI analysis...
```

## Maintenance

### Adding New Documents

1. Create a markdown file in the appropriate directory
2. Add YAML frontmatter with required metadata
3. Follow the document template structure
4. Add cross-references to related documents
5. Run `python scripts/build_knowledge_index.py` to update embeddings

### Document Review Checklist

- [ ] Title and frontmatter complete
- [ ] Category and tags accurate
- [ ] Related documents linked
- [ ] Examples include concrete numbers
- [ ] Risks clearly documented
- [ ] Content reviewed for accuracy

### Index Maintenance

Rebuild the embedding index when documents change:

```bash
# Rebuild index after document changes
python scripts/build_knowledge_index.py

# Verify index
wc -l knowledge/embeddings.jsonl
```

## Topic Coverage

### Options (Priority)
| Document | Status | Priority |
|----------|--------|----------|
| Cash-Secured Put | TODO | High |
| Covered Call | TODO | High |
| Wheel Strategy | TODO | High |
| Iron Condor | TODO | Medium |
| Bull/Bear Spreads | TODO | Medium |
| Greeks Overview | TODO | High |
| Rolling Positions | TODO | High |

### Fundamentals
| Document | Status | Priority |
|----------|--------|----------|
| Financial Statements | TODO | Medium |
| Valuation Metrics | TODO | Medium |
| Earnings Analysis | TODO | High |

### Technical Analysis
| Document | Status | Priority |
|----------|--------|----------|
| Support/Resistance | TODO | High |
| Chart Patterns | TODO | Medium |
| Moving Averages | TODO | Medium |

### Risk Management
| Document | Status | Priority |
|----------|--------|----------|
| Position Sizing | TODO | High |
| Portfolio Allocation | TODO | Medium |
| Max Drawdown | TODO | Medium |
