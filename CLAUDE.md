# CLAUDE.md - Project Guide for Claude Code

## Project Overview

TTAI (TastyTrade AI) is an AI-assisted trading analysis system built as a Go MCP server with a system tray GUI. It provides tools for portfolio analysis, options strategies, and market research via the Model Context Protocol.

## Repository Structure

```
ttai/
├── src-go/          # Primary Go MCP server (production)
├── src-web/         # SvelteKit web UI (embedded in Go binary)
├── src-python/      # Python MCP server (reference implementation)
├── cert-api/        # Cloudflare Worker for SSL certificates
├── docs/            # Architecture documentation
├── .github/         # CI/CD workflows
└── CLAUDE.md        # This file
```

## Architecture

```
┌─────────────────────────────────────────────────────┐
│  Claude Desktop / MCP Client                        │
└───────────────┬─────────────────────────────────────┘
                │
        ┌───────┴─────────────────┐
        │                         │
    ┌───▼────────┐          ┌────▼──────────┐
    │ Stdio Mode │          │ HTTP/HTTPS    │
    │ (Subprocess)│         │ Mode          │
    └───┬────────┘          └────┬──────────┘
        │                        │
    ┌───▼────────────────────────▼───────────┐
    │  Go MCP Server (src-go)                │
    │  - MCP Protocol Handler                │
    │  - System Tray GUI (Fyne)              │
    │  - Embedded Web UI (SvelteKit)         │
    │  - TastyTrade API Client               │
    └────┬───────────────┬───────────────────┘
         │               │
    ┌────▼────┐    ┌────▼──────────┐
    │TastyTrade│   │ cert-api      │
    │ API      │   │ (Cloudflare)  │
    └──────────┘   └───────────────┘
```

## Go Server (src-go/)

### Building

```bash
cd src-go

# Development build (includes web UI build)
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
make sign-darwin-arm64     # Code sign (requires CODESIGN_IDENTITY)
make zip-darwin-arm64      # Zipped .app for distribution

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
make web                   # Build web UI only
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

### CLI Arguments

| Argument | Description |
|----------|-------------|
| `--headless` | Run without GUI |
| `--transport` | Transport mode: `stdio` or `http` |
| `--host` | HTTP server host |
| `--port` | HTTP server port |
| `--log-level` | Logging level |
| `--data-dir` | Data directory |
| `--ssl-domain` | SSL domain for HTTPS |
| `--ssl-port` | HTTPS port |

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
| `TTAI_SSL_CERT_API` | Override cert API URL | (computed) |

When `TTAI_SSL_DOMAIN` is set:
- Cert API URL: `https://api.{TTAI_SSL_DOMAIN}/cert`
- HTTPS server: `https://local.{TTAI_SSL_DOMAIN}:{TTAI_SSL_PORT}`
- Falls back to HTTP if cert fetch fails

### Project Structure

```
src-go/
├── main.go                  # Entry point with CLI parsing
├── Makefile                 # Build commands
├── go.mod                   # Go module (github.com/tyler-johnson/ttai)
├── internal/
│   ├── app/
│   │   └── app.go           # Application lifecycle, GUI/headless modes
│   ├── config/
│   │   └── config.go        # Configuration from env/CLI
│   ├── mcp/
│   │   ├── server.go        # MCP JSON-RPC protocol handling
│   │   ├── tools.go         # Tool definitions and handlers
│   │   └── rest.go          # REST API endpoints (/api/*)
│   ├── tastytrade/
│   │   ├── client.go        # TastyTrade API wrapper
│   │   └── types.go         # Data types with JSON marshaling
│   ├── credentials/
│   │   └── keyring.go       # System keyring storage
│   ├── cache/
│   │   └── cache.go         # TTL-based in-memory cache
│   ├── ssl/
│   │   └── certs.go         # SSL certificate management
│   ├── state/
│   │   ├── state.go         # Application state
│   │   ├── preferences.go   # Launch at startup (cross-platform)
│   │   ├── loginitem_darwin.go  # macOS SMAppService (CGO)
│   │   └── loginitem_other.go   # Stub for non-Darwin
│   └── webui/
│       ├── webui.go         # Embedded web UI handler
│       ├── preferences.go   # User preferences (JSON file)
│       └── dist/            # Embedded SvelteKit build
├── ui/
│   ├── tray.go              # System tray manager (Fyne)
│   ├── systray_darwin.go    # macOS dock hiding (CGO)
│   └── systray_other.go     # Cross-platform stubs
├── resources/
│   ├── resources.go         # Embedded resources loader
│   ├── icon.png             # App icon
│   ├── icon.icns            # macOS app icon (ICNS format)
│   ├── pulse.svg            # Tray icon (macOS/Linux)
│   ├── tray_template.png    # Tray icon (Windows)
│   └── entitlements.plist   # macOS code signing entitlements
└── dist/                    # Build output
    └── TTAI.app/            # macOS app bundle
```

### MCP Tools

| Tool | Description | Parameters |
|------|-------------|------------|
| `ping` | Connectivity test | None |
| `login` | TastyTrade OAuth authentication | `client_secret`, `refresh_token`, `remember_me` |
| `logout` | Clear session and credentials | `clear_credentials` |
| `get_auth_status` | Check authentication state | None |
| `get_quote` | Fetch market quote data | `symbol` |

### REST API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/server-info` | GET | Server metadata (version, URLs, SSL) |
| `/api/settings` | GET | User preferences |
| `/api/settings` | PATCH | Update preferences |
| `/api/tastytrade` | GET | TastyTrade auth status |
| `/api/tastytrade` | POST | Login with OAuth |
| `/api/tastytrade` | DELETE | Logout |

### Key Dependencies

- `fyne.io/fyne/v2` - Cross-platform GUI framework
- `fyne.io/systray` - System tray support
- `github.com/mark3labs/mcp-go` - MCP protocol SDK
- `github.com/zalando/go-keyring` - Secure credential storage

## Web UI (src-web/)

SvelteKit-based settings interface embedded in the Go binary.

### Tech Stack

- SvelteKit 2 with Svelte 5 (runes)
- Tailwind CSS 4 with DaisyUI 5
- TypeScript 5.7
- Vite 6

### Structure

```
src-web/
├── package.json
├── svelte.config.js
├── vite.config.ts
├── tailwind.config.ts
└── src/
    ├── app.css              # Tailwind imports
    ├── app.html             # HTML template
    ├── lib/
    │   └── api.ts           # TypeScript API client
    └── routes/
        ├── +layout.svelte   # Root layout
        └── +page.svelte     # Main dashboard/settings
```

### Development

```bash
cd src-web
npm install
npm run dev      # Development server on :5173
npm run build    # Build for embedding
```

The build output goes to `src-web/build/` and is copied to `src-go/internal/webui/dist/` during `make build`.

## Certificate API (cert-api/)

Cloudflare Worker providing SSL certificates for local HTTPS.

### How It Works

1. Worker runs at `https://api.tt-ai.dev`
2. Uses ACME (ZeroSSL) with DNS-01 challenge for `*.tt-ai.dev`
3. Stores certificates in Cloudflare KV
4. Auto-renews via daily cron (3:00 AM UTC)
5. TTAI server fetches cert on startup when SSL enabled

### DNS Setup

- `api.tt-ai.dev` → Cloudflare Worker
- `local.tt-ai.dev` → `127.0.0.1` (points to local server)

### Structure

```
cert-api/
├── wrangler.toml            # Worker configuration
├── package.json
└── src/
    ├── index.ts             # HTTP routes + cron handler
    ├── acme.ts              # ACME client (RFC 8555)
    └── dns.ts               # Cloudflare DNS API helper
```

### Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/cert` | GET | Returns certificate bundle |
| `/health` | GET | Health check |
| `/renew` | POST | Manual certificate renewal |

### Deployment

```bash
cd cert-api
npm install
npx wrangler deploy
```

Requires Cloudflare secrets: `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ZONE_ID`

## Python Server (src-python/)

Reference implementation for TastyTrade API patterns. The Go server is the primary implementation.

### Structure

```
src-python/
├── pyproject.toml           # Python 3.11+, dependencies
└── src/
    ├── __main__.py          # Entry point
    ├── auth/
    │   └── credentials.py   # OAuth encryption patterns
    ├── server/
    │   ├── main.py          # MCP server init
    │   ├── config.py        # Configuration
    │   ├── tools.py         # MCP tools
    │   └── ssl.py           # SSL cert fetching
    ├── gui/
    │   ├── app.py           # Qt application
    │   ├── main_window.py   # Settings window
    │   └── system_tray.py   # System tray
    └── services/
        ├── tastytrade.py    # TastyTrade API (reference)
        ├── database.py      # Data persistence
        └── cache.py         # Caching
```

### Key Dependencies

- `mcp>=1.0.0` - MCP protocol
- `tastytrade>=8.0` - TastyTrade Python SDK
- `PySide6` - Qt GUI framework
- `starlette`, `uvicorn` - HTTP server

## CI/CD (.github/workflows/)

### build.yml

Triggers:
- Release creation
- Push to main (src-go changes)
- Manual dispatch

Jobs:
1. **macOS**: Builds arm64 + amd64, creates .app bundles
2. **Code signing**: Signs and notarizes macOS releases
3. **Windows**: Builds exe
4. **Linux**: Builds binary

### Required Secrets

| Secret | Description |
|--------|-------------|
| `APPLE_CERTIFICATE_BASE64` | Developer ID cert (base64) |
| `APPLE_CERTIFICATE_PASSWORD` | Cert password |
| `APPLE_API_KEY_BASE64` | Notarization API key |
| `APPLE_API_KEY_ID` | API key identifier |
| `APPLE_API_ISSUER_ID` | App Store Connect issuer |
| `APPLE_TEAM_NAME` | Team identifier |

See `docs/CODE_SIGNING_SETUP.md` for setup instructions.

## Documentation (docs/)

- `CODE_SIGNING_SETUP.md` - Apple code signing guide
- `architecture/` - Design documents:
  - `01-mcp-server-design.md` - MCP protocol
  - `02-workflow-orchestration.md` - Task patterns
  - `03-python-server.md` - Python implementation
  - `04-ai-agent-system.md` - AI agent frameworks
  - `05-data-layer.md` - Data persistence
  - `06-background-tasks.md` - Background jobs
  - `07-knowledge-base.md` - Knowledge management
  - `08-build-distribution.md` - Build/release
  - `09-integration-patterns.md` - Claude Desktop integration
  - `10-local-development.md` - Dev environment
  - `11-frontend.md` - Web UI architecture

## Data Storage

All user data stored in `~/.ttai/`:
- `logs/ttai.log` - Application logs
- `preferences.json` - User settings (ShowWindowOnLaunch, IsFirstRun)
- `ssl/` - Cached SSL certificates
  - `cert.pem` - Certificate chain
  - `key.pem` - Private key
  - `meta.json` - Certificate metadata

Credentials stored in system keyring:
- macOS: Keychain
- Windows: Credential Manager
- Linux: Secret Service (D-Bus)

## macOS Notes

### SMAppService (Login Items)

The app uses Apple's SMAppService API on macOS 13+ for "Launch at Login":
- Shows "TTAI" in System Settings > General > Login Items
- User approval via system prompt on first enable
- No hidden LaunchAgent plist files

**Requirements** (no entitlements needed for login items):
- Code-signed app bundle
- Valid bundle identifier (`dev.tt-ai.ttai`)
- Running from .app bundle

**Fallback**: macOS 11-12 uses LaunchAgent at `~/Library/LaunchAgents/dev.tt-ai.ttai.plist`

### App Bundle

Info.plist configuration:
- `CFBundleIdentifier`: `dev.tt-ai.ttai`
- `CFBundleName`: `TTAI`
- `LSUIElement`: `true` (menu bar app)
- `LSMinimumSystemVersion`: `11.0`

## Current Implementation Status

### Implemented
- MCP server with stdio/HTTP transports
- System tray GUI app (Fyne)
- Embedded web UI (SvelteKit)
- Platform-specific dock/taskbar hiding
- Launch at Login (SMAppService on macOS 13+, LaunchAgent fallback, Windows registry, Linux XDG)
- HTTPS with certificate fetching from Cloudflare Worker
- Cloudflare Worker for SSL certificate distribution
- Configuration via env vars and CLI
- Credential storage via system keyring
- In-memory TTL cache
- TastyTrade client (OAuth, quotes)
- MCP tools: `ping`, `login`, `logout`, `get_auth_status`, `get_quote`
- GitHub Actions CI/CD with code signing

### Not Yet Implemented
- Full TastyTrade API (positions, option chains, orders)
- AI agents (chart analyst, options analyst)
- Background tasks and monitors
- Database persistence

## Code Style

### Go
- Go 1.22+
- `go fmt` for formatting
- `go vet` and `golangci-lint` for linting

```bash
cd src-go
make fmt && make lint && make test
```

### TypeScript/Svelte
- TypeScript 5.7+
- Prettier for formatting
- ESLint for linting

```bash
cd src-web
npm run lint && npm run check
```

## Maintaining This Document

Keep CLAUDE.md updated as features are implemented:
- Update "Current Implementation Status"
- Add new MCP tools and REST endpoints
- Document new environment variables
- Note changes to project structure
