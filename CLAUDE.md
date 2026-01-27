# CLAUDE.md

This file provides context for Claude Code when working with the TTAI (TastyTrade AI) codebase.

## Project Overview

TTAI is an AI-powered trading analysis system that integrates with TastyTrade for market data and trading operations. The system uses the Model Context Protocol (MCP) to expose tools to AI clients like Claude.

## Architecture

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  AI Clients     │────▶│   MCP Server    │────▶│    Temporal     │
│ (Claude, etc.)  │     │  (TypeScript)   │     │   (Workflows)   │
└─────────────────┘     └─────────────────┘     └─────────────────┘
                                                        │
                        ┌───────────────────────────────┘
                        ▼
                ┌─────────────────┐     ┌─────────────────┐
                │  Python Worker  │────▶│   TastyTrade    │
                │  (Activities)   │     │      API        │
                └─────────────────┘     └─────────────────┘
                        │
        ┌───────────────┼───────────────┐
        ▼               ▼               ▼
   PostgreSQL        Redis        Streaming Worker
```

## Directory Structure

- `mcp-server/` - TypeScript MCP server (AI client interface)
- `workers/` - Python workers (Temporal activities, data fetching)
- `k8s/dev/` - Kubernetes manifests for local development
- `helm/` - Helm values for dependencies (PostgreSQL, Redis, Temporal)
- `docs/architecture/` - Design documents

## Local Development

### Prerequisites
- Minikube
- Tilt
- uv (Python package manager)

### Start Development Environment
```bash
minikube start
tilt up
```

### Port Forwards (automatic via Tilt)
- PostgreSQL: `localhost:5432`
- Redis: `localhost:6379`
- Temporal Web UI: `localhost:8080`
- Temporal Frontend: `localhost:7233`
- MCP Server: `localhost:3000`

### Environment Variables
Copy `.env.local.example` to `.env.local` and fill in:
- `TT_CLIENT_SECRET` - TastyTrade OAuth client secret
- `TT_REFRESH_TOKEN` - TastyTrade refresh token
- `ANTHROPIC_API_KEY` - For LiteLLM

## Workers (Python)

### Package Management
Always use `uv` for Python dependencies:
```bash
cd workers
uv sync              # Install dependencies
uv add <package>     # Add a dependency
uv run python ...    # Run Python with venv
uv run pytest        # Run tests
```

### Key Services
- `services/tastytrade.py` - TastyTrade API client
- `services/cache.py` - Redis cache client
- `services/database.py` - PostgreSQL async client
- `config.py` - Configuration via pydantic-settings

### Test Data Layer
```bash
cd workers
uv run python scripts/test_data_layer.py
```

## Conventions

### Python
- Python 3.11+
- Async/await for I/O operations
- Pydantic for data validation
- Type hints required

### Code Style
- Ruff for linting/formatting
- Line length: 100 characters
- Strict mypy type checking

## Infrastructure Defaults (Local Dev)

```
REDIS_URL=redis://:devpassword@localhost:6379
DATABASE_URL=postgresql://ttai:devpassword@localhost:5432/ttai
TEMPORAL_ADDRESS=localhost:7233
```
