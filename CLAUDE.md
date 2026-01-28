# CLAUDE.md - Project Guide for Claude Code

## Project Overview

TTAI (TastyTrade AI) is an AI-assisted trading analysis system built as a Python MCP server. It provides tools for portfolio analysis, options strategies, and market research via the Model Context Protocol.

## Architecture

The system consists of:
- **Python MCP Server** (`src-python/`): Core backend providing MCP tools, TastyTrade API integration, and analysis capabilities
- **Tauri Desktop App** (future): Svelte frontend for settings/configuration, with Python server as sidecar
- **Headless Mode**: Python server runs standalone for use with Claude Desktop or other MCP clients

## Python Development

### Package Manager: uv

This project uses **uv** for Python dependency management. Always use uv commands:

```bash
cd src-python

# Sync dependencies (install/update all deps from pyproject.toml)
uv sync

# Run Python commands through uv
uv run python -m src.server.main --transport sse --port 8080

# Run tests
uv run pytest tests/ -v

# Run linters
uv run ruff check src/
uv run mypy src/
```

### Running the Server

```bash
cd src-python

# Headless mode (HTTP/SSE) - for development with Claude Desktop
uv run python -m src.server.main --transport sse --port 8080

# Sidecar mode (stdio) - default, for Tauri integration
uv run python -m src.server.main

# With debug logging
TTAI_LOG_LEVEL=DEBUG uv run python -m src.server.main --transport sse --port 8080
```

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `TTAI_TRANSPORT` | Transport: `stdio` or `sse` | `stdio` |
| `TTAI_HOST` | SSE host | `localhost` |
| `TTAI_PORT` | SSE port | `8080` |
| `TTAI_LOG_LEVEL` | Log level | `INFO` |
| `TTAI_DATA_DIR` | Data directory | `~/.ttai` |

### Project Structure

```
src-python/
├── pyproject.toml           # Project config and dependencies
├── src/
│   ├── server/              # MCP server implementation
│   │   ├── main.py          # Entry point
│   │   ├── config.py        # Configuration
│   │   └── tools.py         # MCP tool registration
│   ├── auth/                # Authentication
│   │   └── credentials.py   # Encrypted credential storage
│   ├── services/            # Business logic
│   │   ├── tastytrade.py    # TastyTrade API wrapper
│   │   ├── cache.py         # In-memory caching
│   │   └── database.py      # SQLite database
│   └── utils/               # Shared utilities
└── tests/                   # Test suite
```

### Key Dependencies

- `mcp>=1.0.0` - Model Context Protocol SDK
- `tastytrade>=8.0` - Official TastyTrade Python SDK
- `cryptography>=41.0.0` - Fernet encryption for credentials
- `starlette>=0.27.0` + `uvicorn>=0.23.0` - HTTP/SSE transport

## Architecture Documentation

Detailed design docs are in `docs/architecture/`:

| Document | Description |
|----------|-------------|
| [01-mcp-server-design.md](docs/architecture/01-mcp-server-design.md) | MCP protocol, transports, tool/resource registration |
| [02-workflow-orchestration.md](docs/architecture/02-workflow-orchestration.md) | Python asyncio task orchestration |
| [03-python-server.md](docs/architecture/03-python-server.md) | Server architecture, running modes, project structure |
| [04-ai-agent-system.md](docs/architecture/04-ai-agent-system.md) | AI agent implementations |
| [05-data-layer.md](docs/architecture/05-data-layer.md) | SQLite database and credential storage |
| [06-background-tasks.md](docs/architecture/06-background-tasks.md) | Background monitors and notifications |
| [07-knowledge-base.md](docs/architecture/07-knowledge-base.md) | Knowledge base and vector search |
| [08-build-distribution.md](docs/architecture/08-build-distribution.md) | PyInstaller packaging, distribution |
| [09-integration-patterns.md](docs/architecture/09-integration-patterns.md) | Tauri ↔ Python and HTTP/SSE communication |
| [10-local-development.md](docs/architecture/10-local-development.md) | Development setup and workflows |
| [11-frontend.md](docs/architecture/11-frontend.md) | Svelte/Tailwind/DaisyUI frontend |

## Current Implementation Status

### Implemented
- MCP server with stdio/SSE transports
- Configuration management
- Database and cache services
- Credential manager with Fernet encryption
- TastyTrade service with session management
- MCP tools: `ping`, `login`, `logout`, `get_auth_status`, `get_quote`

### Not Yet Implemented
- Full TastyTrade API coverage (positions, chains, orders)
- AI agents (chart analyst, options analyst)
- Background tasks and monitors
- Knowledge base
- Tauri desktop app / frontend

## Testing

```bash
cd src-python

# Run all tests
uv run pytest tests/ -v

# Run with coverage
uv run pytest tests/ -v --cov=src --cov-report=html

# Run specific test file
uv run pytest tests/test_services/test_tastytrade.py -v
```

## Code Style

- Python 3.11+
- Type hints required
- Line length: 100 characters
- Linting: ruff, mypy
- Formatting: Follows ruff defaults

```bash
cd src-python
uv run ruff check src/
uv run ruff format src/
uv run mypy src/
```

## Maintaining This Document

**Keep this CLAUDE.md updated** as more parts of the architecture are implemented. When adding new features:
- Update the "Current Implementation Status" section
- Add new environment variables or configuration options
- Document new MCP tools and their usage
- Note any changes to project structure

This ensures Claude Code has accurate context for future development sessions.

## Data Storage

All user data is stored locally in `~/.ttai/`:
- `.key` - Fernet encryption key (auto-generated)
- `.credentials` - Encrypted TastyTrade credentials
- `ttai.db` - SQLite database
- `logs/` - Application logs
