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
uv run python -m src.server.main --headless --port 5180

# Run tests
uv run pytest tests/ -v

# Run linters
uv run ruff check src/
uv run mypy src/
```

### Running the Server

```bash
cd src-python

# GUI mode (default) - launches desktop app
uv run python -m src.server.main

# Headless HTTP mode - for Claude Desktop
uv run python -m src.server.main --headless --port 5180

# HTTPS mode - fetches SSL cert from api.tt-ai.dev, runs on local.tt-ai.dev:5181
TTAI_SSL_DOMAIN=tt-ai.dev uv run python -m src.server.main --headless

# Stdio mode - for subprocess/sidecar integration
uv run python -m src.server.main --headless --transport stdio

# With debug logging
TTAI_LOG_LEVEL=DEBUG uv run python -m src.server.main --headless --port 5180
```

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `TTAI_TRANSPORT` | Transport: `stdio` or `http` | `http` |
| `TTAI_HOST` | HTTP host | `localhost` |
| `TTAI_PORT` | HTTP port | `5180` |
| `TTAI_LOG_LEVEL` | Log level | `INFO` |
| `TTAI_DATA_DIR` | Data directory | `~/.ttai` |
| `TTAI_SSL_DOMAIN` | Base domain for SSL | `tt-ai.dev` |
| `TTAI_SSL_PORT` | HTTPS port | `5181` |

When `TTAI_SSL_DOMAIN` is set:
- Cert API URL: `https://api.{TTAI_SSL_DOMAIN}/cert`
- HTTPS server: `https://local.{TTAI_SSL_DOMAIN}:{TTAI_SSL_PORT}`
- Falls back to HTTP if cert fetch fails

### Project Structure

```
src-python/
├── pyproject.toml           # Project config and dependencies
├── src/
│   ├── server/              # MCP server implementation
│   │   ├── main.py          # Entry point
│   │   ├── config.py        # Configuration
│   │   ├── ssl.py           # SSL certificate management
│   │   └── tools.py         # MCP tool registration
│   ├── auth/                # Authentication
│   │   └── credentials.py   # Encrypted credential storage
│   ├── services/            # Business logic
│   │   ├── tastytrade.py    # TastyTrade API wrapper
│   │   ├── cache.py         # In-memory caching
│   │   └── database.py      # SQLite database
│   └── utils/               # Shared utilities
└── tests/                   # Test suite

cert-api/                    # Cloudflare Worker for certificate distribution
├── src/
│   ├── index.ts             # HTTP routes + cron handler
│   ├── acme.ts              # ACME client for Let's Encrypt
│   └── dns.ts               # Cloudflare DNS API helper
└── wrangler.toml            # Cloudflare config
```

### Key Dependencies

- `mcp>=1.0.0` - Model Context Protocol SDK
- `tastytrade>=8.0` - Official TastyTrade Python SDK
- `cryptography>=41.0.0` - Fernet encryption for credentials
- `starlette>=0.27.0` + `uvicorn>=0.23.0` - HTTP transport
- `httpx>=0.25.0` - Async HTTP client for certificate fetching

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
- MCP server with stdio/HTTP transports
- Desktop GUI app (PySide6)
- HTTPS support with certificate fetching from Cloudflare Worker
- Cloudflare Worker for SSL certificate distribution (cert-api/)
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
- `ssl/` - Cached SSL certificates (when HTTPS enabled)
  - `cert.pem` - Certificate chain
  - `key.pem` - Private key
  - `meta.json` - Certificate metadata (expiry, domain)
