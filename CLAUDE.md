# CLAUDE.md - Project Guide for Claude Code

## Project Overview

TTAI (TastyTrade AI) is an AI-assisted trading analysis system built as a Go MCP server with a system tray GUI. It provides tools for portfolio analysis, options strategies, and market research via the Model Context Protocol.

## Architecture

The system consists of:
- **Go MCP Server** (`src-go/`): Core application providing MCP tools, TastyTrade API integration, system tray GUI, and analysis capabilities
- **Cloudflare Worker** (`cert-api/`): SSL certificate distribution for HTTPS support
- **Headless Mode**: Server runs standalone for use with Claude Desktop or other MCP clients
- **GUI Mode**: System tray app with settings window (default)

## Go Development

### Building

```bash
cd src-go

# Development build (current platform)
make build

# Run in GUI mode
make run

# Run in headless mode
make run-headless

# Run in stdio mode (for MCP subprocess integration)
make run-stdio

# Run with SSL
make run-ssl
```

### Build Targets

```bash
# Build for all platforms
make build-all

# macOS builds
make build-darwin-arm64    # Apple Silicon binary
make build-darwin-amd64    # Intel Mac binary
make bundle-darwin-arm64   # Apple Silicon .app bundle
make bundle-darwin-amd64   # Intel Mac .app bundle
make zip-darwin-arm64      # Zipped .app for distribution
make zip-darwin-amd64      # Zipped .app for distribution

# Windows build
make build-windows         # Creates TTAI-windows.exe

# Linux build
make build-linux           # Creates TTAI-linux binary

# Maintenance
make clean                 # Remove build artifacts
make test                  # Run tests
make fmt                   # Format code
make lint                  # Run linters
make deps                  # Tidy and download dependencies
```

### Running the Server

```bash
cd src-go

# GUI mode (default) - launches system tray app
./ttai

# Headless HTTP mode - for Claude Desktop
./ttai --headless --port 5180

# HTTPS mode - fetches SSL cert from api.tt-ai.dev
TTAI_SSL_DOMAIN=tt-ai.dev ./ttai --headless

# Stdio mode - for subprocess/sidecar integration
./ttai --headless --transport stdio

# With debug logging
TTAI_LOG_LEVEL=DEBUG ./ttai --headless --port 5180
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
src-go/
├── main.go                  # Entry point
├── Makefile                 # Build commands
├── go.mod                   # Go module definition
├── internal/
│   ├── app/                 # Application lifecycle
│   │   └── app.go           # Main app struct, GUI/headless modes
│   ├── config/              # Configuration management
│   ├── mcp/                 # MCP server implementation
│   │   ├── server.go        # MCP protocol handling
│   │   ├── tools.go         # Tool definitions
│   │   └── rest.go          # REST API endpoints
│   ├── tastytrade/          # TastyTrade API client
│   │   ├── client.go        # API wrapper
│   │   └── types.go         # Data types
│   ├── credentials/         # Secure credential storage (keyring)
│   ├── cache/               # In-memory caching
│   ├── ssl/                 # SSL certificate management
│   └── state/               # Application state
├── ui/
│   ├── window.go            # Main settings window
│   ├── tray.go              # System tray setup
│   ├── tray_darwin.go       # macOS dock hiding (cgo)
│   ├── tray_windows.go      # Windows taskbar handling
│   ├── tray_linux.go        # Linux taskbar handling
│   ├── pages/               # UI pages (settings, about, connection)
│   └── dialogs/             # UI dialogs (login)
└── resources/
    ├── resources.go         # Embedded resources
    ├── icon.png             # App icon
    └── tray_template.png    # System tray icon

cert-api/                    # Cloudflare Worker for certificate distribution
├── src/
│   ├── index.ts             # HTTP routes + cron handler
│   ├── acme.ts              # ACME client for Let's Encrypt
│   └── dns.ts               # Cloudflare DNS API helper
└── wrangler.toml            # Cloudflare config
```

### Key Dependencies

- `fyne.io/fyne/v2` - Cross-platform GUI framework
- `fyne.io/systray` - System tray support
- `github.com/mark3labs/mcp-go` - MCP protocol SDK
- `github.com/zalando/go-keyring` - Secure credential storage

## TastyTrade API Reference

The Python implementation (`src-python/`) serves as a reference for the TastyTrade API integration. Use it to understand:

- **Authentication flow**: OAuth token exchange, session management
- **API endpoints**: Quote data, positions, option chains, order placement
- **Data structures**: How TastyTrade returns market data, account info

Key Python files for reference:
- `src-python/src/services/tastytrade.py` - TastyTrade API wrapper
- `src-python/src/auth/credentials.py` - Credential encryption patterns

The official TastyTrade Python SDK (`tastytrade>=8.0`) is also useful for understanding the API.

## Current Implementation Status

### Implemented
- MCP server with stdio/HTTP transports
- System tray GUI app (Fyne)
- Platform-specific dock/taskbar hiding (macOS, Windows, Linux)
- HTTPS support with certificate fetching from Cloudflare Worker
- Cloudflare Worker for SSL certificate distribution (cert-api/)
- Configuration management
- Credential storage via system keyring
- In-memory cache service
- TastyTrade client with session management
- MCP tools: `ping`, `login`, `logout`, `get_auth_status`, `get_quote`

### Not Yet Implemented
- Full TastyTrade API coverage (positions, chains, orders)
- AI agents (chart analyst, options analyst)
- Background tasks and monitors

## Code Style

- Go 1.21+
- Use `go fmt` for formatting
- Use `go vet` and `golangci-lint` for linting
- Follow standard Go conventions

```bash
cd src-go
make fmt    # Format code
make lint   # Run linters
make test   # Run tests
```

## Data Storage

All user data is stored locally in `~/.ttai/`:
- `logs/` - Application logs
- `ssl/` - Cached SSL certificates (when HTTPS enabled)
  - `cert.pem` - Certificate chain
  - `key.pem` - Private key
  - `meta.json` - Certificate metadata (expiry, domain)

Credentials are stored in the system keyring (macOS Keychain, Windows Credential Manager, Linux Secret Service).

## Maintaining This Document

**Keep this CLAUDE.md updated** as features are implemented:
- Update "Current Implementation Status" section
- Add new environment variables or configuration options
- Document new MCP tools and their usage
- Note any changes to project structure
