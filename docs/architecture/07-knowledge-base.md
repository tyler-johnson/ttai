# Knowledge Base

## Overview

The TTAI knowledge base provides trading and options education content accessible to AI agents during analysis. Documents are stored locally in `~/.ttai/knowledge/`, with semantic search powered by sentence-transformers for local embeddings and sqlite-vec for vector storage. The system supports both direct document access via MCP resources and similarity search for context retrieval (RAG).

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                    Python MCP Server (Sidecar)                       │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ┌────────────────────────────────────────────────────────────────┐ │
│  │              Knowledge Service (MCP Resources)                  │ │
│  │         knowledge://options/strategies/csp                      │ │
│  │         knowledge://trading/risk-management                     │ │
│  └──────────────────────────┬─────────────────────────────────────┘ │
│                             │                                        │
│      ┌──────────────────────┼──────────────────────┐                │
│      ▼                      ▼                      ▼                │
│  ┌────────────┐    ┌────────────────┐    ┌────────────────┐        │
│  │   File     │    │    SQLite      │    │  sentence-     │        │
│  │  System    │    │  (sqlite-vec)  │    │  transformers  │        │
│  │            │    │                │    │                │        │
│  │ - Markdown │    │ - Chunk store  │    │ - all-MiniLM-  │        │
│  │ - PDFs     │    │ - Embeddings   │    │   L6-v2        │        │
│  │ - Text     │    │ - Metadata     │    │ - Local model  │        │
│  └────────────┘    └────────────────┘    └────────────────┘        │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

## Document Storage

### Directory Structure

```
~/.ttai/knowledge/
├── options/
│   └── strategies/
│       ├── csp.md                    # Cash-Secured Puts
│       ├── covered_call.md           # Covered Calls
│       ├── spreads.md                # Vertical Spreads
│       ├── iron_condor.md            # Iron Condors
│       └── wheel.md                  # The Wheel Strategy
├── trading/
│   ├── risk-management.md            # Position Sizing, Risk Rules
│   ├── technical-analysis.md         # Chart Patterns, Indicators
│   └── psychology.md                 # Trading Psychology
├── research/
│   ├── earnings-analysis.md          # How to Analyze Earnings
│   └── sector-overview.md            # Sector Analysis Framework
└── custom/
    └── my-notes.md                   # User's custom notes
```

### Document Format

Documents should be markdown with YAML frontmatter for metadata:

```markdown
---
title: Cash-Secured Put Strategy
category: options/strategies
tags: [csp, put-selling, income]
difficulty: beginner
last_updated: 2024-01-15
---

# Cash-Secured Put (CSP) Strategy

## Overview

A cash-secured put is an options strategy where you sell a put option
while holding enough cash to buy the underlying stock if assigned.

## When to Use

- Bullish or neutral outlook on the underlying
- Willing to own the stock at the strike price
- Want to generate income while waiting to buy

...
```

## Embedding Pipeline

### Sentence Transformers Setup

```python
# src/services/embeddings.py
import logging
from typing import List, Optional
import numpy as np

logger = logging.getLogger(__name__)

# Lazy load the model to reduce startup time
_model = None

def get_embedding_model():
    """Get or initialize the embedding model."""
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        logger.info("Loading embedding model...")
        _model = SentenceTransformer('all-MiniLM-L6-v2')
        logger.info("Embedding model loaded")
    return _model

def generate_embedding(text: str) -> List[float]:
    """
    Generate embedding for a text string.

    Uses all-MiniLM-L6-v2 which produces 384-dimensional embeddings.
    This model is small (~80MB), fast, and works well for semantic search.
    """
    model = get_embedding_model()
    embedding = model.encode(text, normalize_embeddings=True)
    return embedding.tolist()

def generate_embeddings_batch(texts: List[str]) -> List[List[float]]:
    """Generate embeddings for multiple texts efficiently."""
    model = get_embedding_model()
    embeddings = model.encode(texts, normalize_embeddings=True)
    return [e.tolist() for e in embeddings]

def cosine_similarity(a: List[float], b: List[float]) -> float:
    """Calculate cosine similarity between two embeddings."""
    a_arr = np.array(a)
    b_arr = np.array(b)
    return float(np.dot(a_arr, b_arr) / (np.linalg.norm(a_arr) * np.linalg.norm(b_arr)))
```

### Document Chunking

```python
# src/services/chunker.py
from dataclasses import dataclass
from typing import List, Dict, Any, Optional
import re

@dataclass
class DocumentChunk:
    """A chunk of a document with metadata."""
    document_path: str
    chunk_index: int
    content: str
    metadata: Dict[str, Any]

class DocumentChunker:
    """
    Splits documents into chunks for embedding.

    Uses semantic chunking based on markdown headers
    with a fallback to fixed-size chunks.
    """

    def __init__(
        self,
        chunk_size: int = 1000,
        chunk_overlap: int = 200
    ):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def chunk_document(
        self,
        content: str,
        document_path: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> List[DocumentChunk]:
        """
        Split a document into chunks.

        Strategy:
        1. Try to split on markdown headers (semantic boundaries)
        2. If chunks are too large, split on paragraphs
        3. If still too large, use fixed-size splitting
        """
        metadata = metadata or {}
        chunks = []

        # Try semantic chunking first (by headers)
        sections = self._split_by_headers(content)

        chunk_index = 0
        for section in sections:
            if len(section) <= self.chunk_size:
                chunks.append(DocumentChunk(
                    document_path=document_path,
                    chunk_index=chunk_index,
                    content=section.strip(),
                    metadata=metadata
                ))
                chunk_index += 1
            else:
                # Section too large, split by paragraphs
                paragraphs = section.split('\n\n')
                current_chunk = ""

                for para in paragraphs:
                    if len(current_chunk) + len(para) <= self.chunk_size:
                        current_chunk += para + "\n\n"
                    else:
                        if current_chunk:
                            chunks.append(DocumentChunk(
                                document_path=document_path,
                                chunk_index=chunk_index,
                                content=current_chunk.strip(),
                                metadata=metadata
                            ))
                            chunk_index += 1
                        current_chunk = para + "\n\n"

                if current_chunk.strip():
                    chunks.append(DocumentChunk(
                        document_path=document_path,
                        chunk_index=chunk_index,
                        content=current_chunk.strip(),
                        metadata=metadata
                    ))
                    chunk_index += 1

        return chunks

    def _split_by_headers(self, content: str) -> List[str]:
        """Split content by markdown headers."""
        # Match ## and ### headers
        pattern = r'\n(?=#{2,3}\s)'
        sections = re.split(pattern, content)
        return [s for s in sections if s.strip()]
```

## Knowledge Service

### Core Implementation

```python
# src/services/knowledge.py
import logging
import yaml
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime

from .embeddings import generate_embedding, generate_embeddings_batch
from .chunker import DocumentChunker, DocumentChunk
from .database import DatabaseService

logger = logging.getLogger(__name__)

class KnowledgeService:
    """
    Manages the local knowledge base.

    Provides:
    - Document ingestion with chunking and embedding
    - Semantic search across documents
    - Direct document access for MCP resources
    """

    def __init__(self, db: DatabaseService, knowledge_dir: Path):
        self.db = db
        self.knowledge_dir = knowledge_dir
        self.chunker = DocumentChunker()

    async def get_document(self, path: str) -> Optional[str]:
        """
        Get a document by path.

        Args:
            path: Relative path within knowledge directory (e.g., "options/strategies/csp.md")

        Returns:
            Document content or None if not found
        """
        full_path = self.knowledge_dir / path
        if not full_path.exists():
            return None

        return full_path.read_text()

    async def search(
        self,
        query: str,
        limit: int = 5,
        category: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Search knowledge base using semantic similarity.

        Args:
            query: Search query
            limit: Maximum results to return
            category: Optional category filter (e.g., "options/strategies")

        Returns:
            List of matching chunks with similarity scores
        """
        # Generate query embedding
        query_embedding = generate_embedding(query)

        # Search using sqlite-vec
        results = await self._vector_search(
            query_embedding,
            limit=limit,
            category=category
        )

        return results

    async def _vector_search(
        self,
        query_embedding: List[float],
        limit: int = 5,
        category: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Perform vector similarity search."""
        # Convert embedding to bytes for sqlite-vec
        import struct
        embedding_bytes = struct.pack(f'{len(query_embedding)}f', *query_embedding)

        # Build query
        sql = """
            SELECT
                c.id,
                c.document_path,
                c.chunk_index,
                c.content,
                c.metadata,
                vec_distance_cosine(e.embedding, ?) as distance
            FROM knowledge_chunks c
            JOIN knowledge_embeddings e ON e.chunk_id = c.id
        """
        params = [embedding_bytes]

        if category:
            sql += " WHERE c.document_path LIKE ?"
            params.append(f"{category}%")

        sql += " ORDER BY distance ASC LIMIT ?"
        params.append(limit)

        cursor = await self.db._connection.execute(sql, params)
        rows = await cursor.fetchall()

        results = []
        for row in rows:
            results.append({
                "chunk_id": row["id"],
                "document_path": row["document_path"],
                "chunk_index": row["chunk_index"],
                "content": row["content"],
                "metadata": yaml.safe_load(row["metadata"]) if row["metadata"] else {},
                "similarity": 1 - row["distance"],  # Convert distance to similarity
            })

        return results

    async def index_document(self, path: str) -> int:
        """
        Index a document into the knowledge base.

        Args:
            path: Relative path to document

        Returns:
            Number of chunks indexed
        """
        full_path = self.knowledge_dir / path

        if not full_path.exists():
            raise FileNotFoundError(f"Document not found: {path}")

        content = full_path.read_text()

        # Parse frontmatter if present
        metadata = {}
        if content.startswith('---'):
            parts = content.split('---', 2)
            if len(parts) >= 3:
                metadata = yaml.safe_load(parts[1])
                content = parts[2]

        metadata['indexed_at'] = datetime.now().isoformat()
        metadata['source_path'] = path

        # Chunk the document
        chunks = self.chunker.chunk_document(content, path, metadata)

        # Generate embeddings for all chunks
        chunk_texts = [c.content for c in chunks]
        embeddings = generate_embeddings_batch(chunk_texts)

        # Store chunks and embeddings
        for chunk, embedding in zip(chunks, embeddings):
            await self._store_chunk(chunk, embedding)

        logger.info(f"Indexed {len(chunks)} chunks from {path}")
        return len(chunks)

    async def _store_chunk(
        self,
        chunk: DocumentChunk,
        embedding: List[float]
    ) -> int:
        """Store a chunk and its embedding."""
        import struct
        import json

        # Insert chunk
        cursor = await self.db._connection.execute("""
            INSERT INTO knowledge_chunks (document_path, chunk_index, content, metadata)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(document_path, chunk_index) DO UPDATE SET
                content = excluded.content,
                metadata = excluded.metadata
        """, (
            chunk.document_path,
            chunk.chunk_index,
            chunk.content,
            json.dumps(chunk.metadata)
        ))

        chunk_id = cursor.lastrowid

        # Insert embedding
        embedding_bytes = struct.pack(f'{len(embedding)}f', *embedding)

        await self.db._connection.execute("""
            INSERT INTO knowledge_embeddings (chunk_id, embedding)
            VALUES (?, ?)
            ON CONFLICT(chunk_id) DO UPDATE SET
                embedding = excluded.embedding
        """, (chunk_id, embedding_bytes))

        await self.db._connection.commit()
        return chunk_id

    async def index_all(self) -> Dict[str, int]:
        """Index all documents in the knowledge directory."""
        results = {}

        for md_file in self.knowledge_dir.rglob("*.md"):
            relative_path = str(md_file.relative_to(self.knowledge_dir))
            try:
                count = await self.index_document(relative_path)
                results[relative_path] = count
            except Exception as e:
                logger.error(f"Failed to index {relative_path}: {e}")
                results[relative_path] = 0

        return results

    async def delete_document(self, path: str) -> bool:
        """Remove a document and its chunks from the index."""
        # Delete embeddings first (foreign key)
        await self.db._connection.execute("""
            DELETE FROM knowledge_embeddings
            WHERE chunk_id IN (
                SELECT id FROM knowledge_chunks WHERE document_path = ?
            )
        """, (path,))

        # Delete chunks
        cursor = await self.db._connection.execute(
            "DELETE FROM knowledge_chunks WHERE document_path = ?",
            (path,)
        )
        await self.db._connection.commit()

        return cursor.rowcount > 0
```

## MCP Resource Integration

### Knowledge Resources

```python
# src/server/resources.py (knowledge section)
from mcp.server import Server
from mcp.types import Resource

def register_knowledge_resources(
    server: Server,
    knowledge: "KnowledgeService"
) -> None:
    """Register knowledge base resources."""

    @server.resource("knowledge://options/strategies/{strategy}")
    async def get_strategy_doc(strategy: str) -> str:
        """Get options strategy documentation."""
        path = f"options/strategies/{strategy}.md"
        doc = await knowledge.get_document(path)
        return doc or f"Strategy not found: {strategy}"

    @server.resource("knowledge://trading/{topic}")
    async def get_trading_doc(topic: str) -> str:
        """Get trading topic documentation."""
        path = f"trading/{topic}.md"
        doc = await knowledge.get_document(path)
        return doc or f"Topic not found: {topic}"

    @server.resource("knowledge://search")
    async def search_knowledge(query: str) -> str:
        """Search the knowledge base."""
        import json
        results = await knowledge.search(query, limit=5)
        return json.dumps(results, indent=2)

    @server.list_resources()
    async def list_knowledge_resources() -> list[Resource]:
        """List available knowledge resources."""
        return [
            Resource(
                uri="knowledge://options/strategies/csp",
                name="Cash-Secured Put Strategy",
                description="Guide to selling cash-secured puts",
                mimeType="text/markdown"
            ),
            Resource(
                uri="knowledge://options/strategies/covered_call",
                name="Covered Call Strategy",
                description="Guide to selling covered calls",
                mimeType="text/markdown"
            ),
            Resource(
                uri="knowledge://trading/risk-management",
                name="Risk Management",
                description="Position sizing and risk rules",
                mimeType="text/markdown"
            ),
        ]
```

## Search Tool

```python
# src/server/tools.py (search_knowledge tool)

@server.tool()
async def search_knowledge(
    query: str,
    limit: int = 5,
    category: str | None = None
) -> list[TextContent]:
    """
    Search the knowledge base for relevant information.

    Args:
        query: Natural language search query
        limit: Maximum number of results (default 5)
        category: Optional category filter (e.g., "options/strategies")

    Returns:
        Relevant knowledge chunks with similarity scores
    """
    results = await knowledge.search(query, limit=limit, category=category)

    # Format results
    formatted = []
    for r in results:
        formatted.append({
            "path": r["document_path"],
            "content": r["content"][:500] + "..." if len(r["content"]) > 500 else r["content"],
            "similarity": round(r["similarity"], 3),
        })

    return [TextContent(
        type="text",
        text=json.dumps(formatted, indent=2)
    )]
```

## Sample Documents

### Cash-Secured Put Guide

```markdown
---
title: Cash-Secured Put Strategy
category: options/strategies
tags: [csp, put-selling, income, premium]
difficulty: beginner
---

# Cash-Secured Put (CSP) Strategy

## What is a Cash-Secured Put?

A cash-secured put is an options strategy where you:
1. Sell a put option on a stock you want to own
2. Hold enough cash to buy 100 shares if assigned
3. Collect premium regardless of outcome

## Entry Criteria

- **Stock Selection**: Quality stocks you want to own long-term
- **Strike Selection**: At or below support levels (20-30 delta)
- **Expiration**: 30-45 DTE for optimal theta decay
- **Premium Target**: >1% of strike price per month

## Example Trade

Stock: AAPL trading at $180
- Sell 1 AAPL $170 Put @ $3.00 (45 DTE)
- Cash Required: $17,000 ($170 x 100)
- Premium Collected: $300
- Return if expires worthless: 1.76% in 45 days (14.3% annualized)
- Break-even: $167

## Risk Management

- Only sell puts on stocks you want to own
- Keep position size to 2-5% of portfolio per underlying
- Have a plan if stock drops significantly

## When to Roll

- Stock approaching strike with >7 DTE remaining
- Roll down and out for credit if possible
- Take assignment if stock is oversold at good value
```

## Cross-References

- [AI Agent System](./04-ai-agent-system.md) - Agents use knowledge for research
- [Data Layer](./05-data-layer.md) - Chunk and embedding storage
- [MCP Server Design](./01-mcp-server-design.md) - Resource registration
