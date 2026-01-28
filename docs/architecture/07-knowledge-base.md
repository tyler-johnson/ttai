# Knowledge Base

## Overview

The TTAI knowledge base provides trading and options education content accessible to AI agents during analysis. Documents are stored in Cloudflare R2, with semantic search powered by Cloudflare Vectorize. The system supports both direct document access via MCP resources and similarity search for context retrieval.

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                     Cloudflare Edge Network                          │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ┌────────────────────────────────────────────────────────────────┐ │
│  │              MCP Server (Resource Access)                       │ │
│  │         knowledge://options/strategies                          │ │
│  │         knowledge://trading/risk-management                     │ │
│  └──────────────────────────┬─────────────────────────────────────┘ │
│                             │                                        │
│      ┌──────────────────────┼──────────────────────┐                │
│      ▼                      ▼                      ▼                │
│  ┌────────────┐    ┌────────────────┐    ┌────────────────┐        │
│  │Cloudflare  │    │  Cloudflare    │    │  Workers AI    │        │
│  │    R2      │    │   Vectorize    │    │  (Embeddings)  │        │
│  │ (Storage)  │    │   (Search)     │    │                │        │
│  │            │    │                │    │                │        │
│  │ - Markdown │    │ - Chunk index  │    │ - bge-base-en  │        │
│  │ - PDFs     │    │ - Similarity   │    │ - text-embed-  │        │
│  │ - Images   │    │   search       │    │   ada-002      │        │
│  └────────────┘    └────────────────┘    └────────────────┘        │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

## Document Storage (R2)

### Directory Structure

```
ttai-storage/
├── knowledge/
│   ├── options/
│   │   ├── strategies/
│   │   │   ├── cash-secured-put.md
│   │   │   ├── covered-call.md
│   │   │   ├── wheel.md
│   │   │   ├── iron-condor.md
│   │   │   ├── bull-put-spread.md
│   │   │   └── bear-call-spread.md
│   │   ├── greeks/
│   │   │   ├── delta.md
│   │   │   ├── gamma.md
│   │   │   ├── theta.md
│   │   │   ├── vega.md
│   │   │   └── rho.md
│   │   └── concepts/
│   │       ├── implied-volatility.md
│   │       ├── iv-rank.md
│   │       ├── iv-percentile.md
│   │       └── option-pricing.md
│   ├── trading/
│   │   ├── risk-management.md
│   │   ├── position-sizing.md
│   │   ├── portfolio-management.md
│   │   └── trade-psychology.md
│   ├── technical/
│   │   ├── support-resistance.md
│   │   ├── trend-analysis.md
│   │   ├── fibonacci.md
│   │   └── indicators.md
│   └── tastytrade/
│       ├── api-reference.md
│       ├── order-types.md
│       └── account-types.md
│
└── embeddings/
    └── chunks/
        ├── index.json          # Chunk metadata
        └── vectors.bin         # Pre-computed vectors (backup)
```

### Document Format

Documents use frontmatter for metadata:

```markdown
---
title: Cash-Secured Put Strategy
category: options/strategies
tags: [premium-selling, bullish, neutral]
difficulty: beginner
related:
  - covered-call
  - wheel
  - bull-put-spread
updated: 2024-01-15
---

# Cash-Secured Put (CSP)

## Overview

A cash-secured put is an options strategy where you sell a put option
while holding enough cash to purchase the underlying stock if assigned.

## When to Use

- **Bullish to neutral** outlook on the underlying
- Want to potentially acquire shares at a discount
- Comfortable owning the stock at the strike price
- Elevated implied volatility (better premiums)

## Risk/Reward Profile

| Metric          | Value                              |
| --------------- | ---------------------------------- |
| Max Profit      | Premium received                   |
| Max Loss        | Strike price - premium (if → $0)   |
| Breakeven       | Strike price - premium             |
| Capital Req.    | Strike × 100 (per contract)        |

## Example

...
```

### R2 Document Service

```typescript
// src/services/knowledge.ts
export class KnowledgeService {
  constructor(
    private r2: R2Bucket,
    private vectorize: VectorizeIndex
  ) {}

  async getDocument(path: string): Promise<KnowledgeDocument | null> {
    const object = await this.r2.get(`knowledge/${path}`);
    if (!object) return null;

    const content = await object.text();
    const { frontmatter, body } = this.parseFrontmatter(content);

    return {
      path,
      title: frontmatter.title,
      category: frontmatter.category,
      tags: frontmatter.tags || [],
      content: body,
      metadata: frontmatter,
    };
  }

  async listDocuments(prefix?: string): Promise<DocumentInfo[]> {
    const path = prefix ? `knowledge/${prefix}` : "knowledge/";
    const listed = await this.r2.list({ prefix: path });

    return listed.objects
      .filter((obj) => obj.key.endsWith(".md"))
      .map((obj) => ({
        path: obj.key.replace("knowledge/", ""),
        size: obj.size,
        updated: obj.uploaded,
      }));
  }

  async searchDocuments(query: string, limit = 5): Promise<SearchResult[]> {
    // Generate embedding for query
    const embedding = await this.generateEmbedding(query);

    // Search Vectorize
    const results = await this.vectorize.query(embedding, {
      topK: limit,
      returnMetadata: true,
    });

    // Fetch full documents for top results
    const documents = await Promise.all(
      results.matches.map(async (match) => {
        const doc = await this.getDocument(match.metadata?.path as string);
        return {
          document: doc,
          score: match.score,
          chunk: match.metadata?.chunk as string,
        };
      })
    );

    return documents.filter((d) => d.document !== null) as SearchResult[];
  }

  private parseFrontmatter(content: string): {
    frontmatter: Record<string, any>;
    body: string;
  } {
    const match = content.match(/^---\n([\s\S]*?)\n---\n([\s\S]*)$/);
    if (!match) {
      return { frontmatter: {}, body: content };
    }

    // Simple YAML parsing (use js-yaml in production)
    const frontmatter: Record<string, any> = {};
    match[1].split("\n").forEach((line) => {
      const [key, ...valueParts] = line.split(":");
      if (key && valueParts.length) {
        const value = valueParts.join(":").trim();
        frontmatter[key.trim()] = value.startsWith("[")
          ? JSON.parse(value.replace(/'/g, '"'))
          : value;
      }
    });

    return { frontmatter, body: match[2] };
  }

  private async generateEmbedding(text: string): Promise<number[]> {
    // Use Workers AI for embeddings
    const response = await fetch(
      "https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run/@cf/baai/bge-base-en-v1.5",
      {
        method: "POST",
        headers: {
          Authorization: `Bearer ${this.apiToken}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ text: [text] }),
      }
    );

    const result = await response.json();
    return result.result.data[0];
  }
}
```

## Cloudflare Vectorize

### Index Configuration

```typescript
// scripts/setup-vectorize.ts
import { Vectorize } from "@cloudflare/workers-types";

// Create index via wrangler CLI:
// wrangler vectorize create ttai-knowledge --dimensions 768 --metric cosine

interface ChunkMetadata {
  path: string;
  title: string;
  category: string;
  chunk: string;
  chunkIndex: number;
  totalChunks: number;
}
```

### Document Indexing

```typescript
// src/services/indexer.ts
export class DocumentIndexer {
  constructor(
    private r2: R2Bucket,
    private vectorize: VectorizeIndex,
    private ai: Ai
  ) {}

  async indexAllDocuments(): Promise<IndexResult> {
    const documents = await this.listAllDocuments();
    let indexed = 0;
    let chunks = 0;

    for (const docPath of documents) {
      const result = await this.indexDocument(docPath);
      indexed++;
      chunks += result.chunkCount;
    }

    return { documentsIndexed: indexed, chunksCreated: chunks };
  }

  async indexDocument(path: string): Promise<{ chunkCount: number }> {
    // Fetch document
    const object = await this.r2.get(`knowledge/${path}`);
    if (!object) throw new Error(`Document not found: ${path}`);

    const content = await object.text();
    const { frontmatter, body } = this.parseFrontmatter(content);

    // Split into chunks (roughly 500 tokens each)
    const chunks = this.splitIntoChunks(body, 500);

    // Generate embeddings for all chunks
    const embeddings = await this.generateEmbeddings(chunks);

    // Upsert to Vectorize
    const vectors = chunks.map((chunk, i) => ({
      id: `${path}#${i}`,
      values: embeddings[i],
      metadata: {
        path,
        title: frontmatter.title || path,
        category: frontmatter.category || "uncategorized",
        chunk,
        chunkIndex: i,
        totalChunks: chunks.length,
      },
    }));

    await this.vectorize.upsert(vectors);

    return { chunkCount: chunks.length };
  }

  private splitIntoChunks(text: string, targetTokens: number): string[] {
    const chunks: string[] = [];
    const paragraphs = text.split(/\n\n+/);

    let currentChunk = "";
    let currentTokens = 0;

    for (const paragraph of paragraphs) {
      const paragraphTokens = this.estimateTokens(paragraph);

      if (currentTokens + paragraphTokens > targetTokens && currentChunk) {
        chunks.push(currentChunk.trim());
        currentChunk = "";
        currentTokens = 0;
      }

      currentChunk += paragraph + "\n\n";
      currentTokens += paragraphTokens;
    }

    if (currentChunk.trim()) {
      chunks.push(currentChunk.trim());
    }

    return chunks;
  }

  private estimateTokens(text: string): number {
    // Rough estimate: ~4 characters per token
    return Math.ceil(text.length / 4);
  }

  private async generateEmbeddings(texts: string[]): Promise<number[][]> {
    // Batch embedding generation with Workers AI
    const response = await this.ai.run("@cf/baai/bge-base-en-v1.5", {
      text: texts,
    });

    return response.data;
  }

  private async listAllDocuments(): Promise<string[]> {
    const listed = await this.r2.list({ prefix: "knowledge/" });
    return listed.objects
      .filter((obj) => obj.key.endsWith(".md"))
      .map((obj) => obj.key.replace("knowledge/", ""));
  }

  private parseFrontmatter(content: string): {
    frontmatter: Record<string, any>;
    body: string;
  } {
    const match = content.match(/^---\n([\s\S]*?)\n---\n([\s\S]*)$/);
    if (!match) return { frontmatter: {}, body: content };

    const frontmatter: Record<string, any> = {};
    match[1].split("\n").forEach((line) => {
      const colonIndex = line.indexOf(":");
      if (colonIndex > 0) {
        const key = line.substring(0, colonIndex).trim();
        const value = line.substring(colonIndex + 1).trim();
        frontmatter[key] = value;
      }
    });

    return { frontmatter, body: match[2] };
  }
}
```

## MCP Resource Access

### Knowledge Resources

```typescript
// src/server/resources.ts
export function registerKnowledgeResources(
  server: McpServer,
  services: Services
): void {
  const knowledge = new KnowledgeService(services.r2, services.vectorize);

  // Static document access
  server.resource(
    "knowledge://options/strategies/{strategy}",
    "Options strategy documentation",
    async (uri) => {
      const strategy = uri.pathname.split("/").pop();
      const doc = await knowledge.getDocument(`options/strategies/${strategy}.md`);

      if (!doc) {
        return {
          contents: [
            {
              uri: uri.href,
              mimeType: "text/plain",
              text: `Strategy not found: ${strategy}`,
            },
          ],
        };
      }

      return {
        contents: [
          {
            uri: uri.href,
            mimeType: "text/markdown",
            text: doc.content,
          },
        ],
      };
    }
  );

  // Document listing
  server.resource(
    "knowledge://list/{category}",
    "List documents in a category",
    async (uri) => {
      const category = uri.pathname.replace("/list/", "");
      const documents = await knowledge.listDocuments(category);

      return {
        contents: [
          {
            uri: uri.href,
            mimeType: "application/json",
            text: JSON.stringify(documents, null, 2),
          },
        ],
      };
    }
  );

  // Semantic search tool
  server.tool(
    "search_knowledge",
    "Search the knowledge base for relevant information",
    {
      query: z.string().describe("Search query"),
      limit: z.number().optional().default(5).describe("Max results"),
    },
    async ({ query, limit }) => {
      const results = await knowledge.searchDocuments(query, limit);

      const formatted = results.map((r) => ({
        title: r.document?.title,
        path: r.document?.path,
        score: r.score,
        excerpt: r.chunk.substring(0, 200) + "...",
      }));

      return {
        content: [
          {
            type: "text",
            text: JSON.stringify(formatted, null, 2),
          },
        ],
      };
    }
  );
}
```

### Resource Templates

```typescript
// src/server/resourceTemplates.ts
export function registerResourceTemplates(server: McpServer): void {
  // Options strategies
  server.resourceTemplate(
    "knowledge://options/strategies/{strategy}",
    "Options strategy documentation",
    {
      strategy: {
        type: "string",
        description: "Strategy name (e.g., cash-secured-put, covered-call)",
      },
    }
  );

  // Greeks
  server.resourceTemplate(
    "knowledge://options/greeks/{greek}",
    "Option greek documentation",
    {
      greek: {
        type: "string",
        description: "Greek name (delta, gamma, theta, vega, rho)",
      },
    }
  );

  // Trading concepts
  server.resourceTemplate(
    "knowledge://trading/{topic}",
    "Trading concept documentation",
    {
      topic: {
        type: "string",
        description: "Topic (risk-management, position-sizing, etc.)",
      },
    }
  );
}
```

## Embedding Generation

### Workers AI Integration

```typescript
// src/services/embeddings.ts
export class EmbeddingService {
  constructor(private ai: Ai) {}

  async generateEmbedding(text: string): Promise<number[]> {
    const response = await this.ai.run("@cf/baai/bge-base-en-v1.5", {
      text: [text],
    });

    return response.data[0];
  }

  async generateEmbeddings(texts: string[]): Promise<number[][]> {
    // Batch up to 100 texts at a time
    const batchSize = 100;
    const embeddings: number[][] = [];

    for (let i = 0; i < texts.length; i += batchSize) {
      const batch = texts.slice(i, i + batchSize);
      const response = await this.ai.run("@cf/baai/bge-base-en-v1.5", {
        text: batch,
      });
      embeddings.push(...response.data);
    }

    return embeddings;
  }
}
```

### External Embedding Provider (Optional)

```typescript
// src/services/externalEmbeddings.ts
import { OpenAI } from "openai";

export class OpenAIEmbeddingService {
  private client: OpenAI;

  constructor(apiKey: string) {
    this.client = new OpenAI({ apiKey });
  }

  async generateEmbedding(text: string): Promise<number[]> {
    const response = await this.client.embeddings.create({
      model: "text-embedding-ada-002",
      input: text,
    });

    return response.data[0].embedding;
  }

  async generateEmbeddings(texts: string[]): Promise<number[][]> {
    const response = await this.client.embeddings.create({
      model: "text-embedding-ada-002",
      input: texts,
    });

    return response.data.map((d) => d.embedding);
  }
}
```

## wrangler.toml Configuration

```toml
# wrangler.toml

# R2 bucket for document storage
[[r2_buckets]]
binding = "R2"
bucket_name = "ttai-storage"

# Vectorize index for semantic search
[[vectorize]]
binding = "VECTORIZE"
index_name = "ttai-knowledge"

# Workers AI for embeddings
[ai]
binding = "AI"
```

## Document Management CLI

```typescript
// scripts/manage-knowledge.ts
import { program } from "commander";

program
  .command("upload <path>")
  .description("Upload a document to the knowledge base")
  .action(async (path) => {
    // Upload to R2 and index
  });

program
  .command("reindex")
  .description("Reindex all documents")
  .action(async () => {
    const indexer = new DocumentIndexer(r2, vectorize, ai);
    const result = await indexer.indexAllDocuments();
    console.log(`Indexed ${result.documentsIndexed} documents, ${result.chunksCreated} chunks`);
  });

program
  .command("search <query>")
  .description("Search the knowledge base")
  .option("-l, --limit <number>", "Max results", "5")
  .action(async (query, options) => {
    const knowledge = new KnowledgeService(r2, vectorize);
    const results = await knowledge.searchDocuments(query, parseInt(options.limit));
    console.log(JSON.stringify(results, null, 2));
  });

program.parse();
```

## Cross-References

- [MCP Server Design](./01-mcp-server-design.md) - Resource registration
- [Data Layer](./05-data-layer.md) - R2 storage patterns
- [AI Agent System](./04-ai-agent-system.md) - Agent knowledge access
- [Infrastructure](./08-infrastructure.md) - Vectorize configuration
