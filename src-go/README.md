# TTAI Go Implementation

A Go implementation of the TTAI (TastyTrade AI) application with a compact ~18MB binary.

## Building

### Prerequisites

- Go 1.22 or later
- For GUI mode: system libraries for Fyne (see [Fyne prerequisites](https://developer.fyne.io/started/))

### Quick Build

```bash
# Build for current platform
make build

# Build with size optimization
go build -ldflags="-s -w" -o ttai .
```

### Cross-Platform Builds

```bash
# Build all platforms
make build-all

# Build specific platforms
make build-darwin-arm64
make build-darwin-amd64
make build-windows
make build-linux
```

## Running

### GUI Mode (Default)

```bash
./ttai
```

This launches the application with:
- System tray icon with menu
- Settings window (620x400, fixed size)
- HTTP/HTTPS MCP server running in background

### Headless Mode

```bash
# HTTP server on localhost:5180
./ttai --headless

# HTTP server on custom port
./ttai --headless --port 5199

# HTTPS server with SSL (default)
./ttai --headless

# HTTP only (disable SSL)
TTAI_SSL_DOMAIN="" ./ttai --headless --port 5180

# Stdio mode for subprocess/sidecar integration
./ttai --headless --transport stdio
```

## Configuration

### Command Line Arguments

| Flag | Description | Default |
|------|-------------|---------|
| `--headless` | Run without GUI | false |
| `--transport` | Transport mode: `http` or `stdio` | http |
| `--host` | HTTP server host | localhost |
| `--port` | HTTP server port | 5180 |
| `--ssl-domain` | Base domain for SSL | tt-ai.dev |
| `--ssl-port` | HTTPS server port | 5181 |
| `--log-level` | Log level | info |
| `--data-dir` | Data directory | ~/.ttai |

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `TTAI_TRANSPORT` | Transport: `stdio` or `http` | http |
| `TTAI_HOST` | HTTP host | localhost |
| `TTAI_PORT` | HTTP port | 5180 |
| `TTAI_LOG_LEVEL` | Log level | info |
| `TTAI_DATA_DIR` | Data directory | ~/.ttai |
| `TTAI_SSL_DOMAIN` | Base domain for SSL | tt-ai.dev |
| `TTAI_SSL_PORT` | HTTPS port | 5181 |

CLI arguments take precedence over environment variables.

## MCP Tools

The server provides the following MCP tools:

| Tool | Description |
|------|-------------|
| `ping` | Server connectivity check (returns "pong") |
| `login` | Authenticate with TastyTrade OAuth credentials |
| `logout` | Log out and optionally clear stored credentials |
| `get_auth_status` | Check authentication status |
| `get_quote` | Get quote data for a symbol (requires authentication) |

## REST API

For GUI communication, the server also provides REST endpoints:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/health` | GET | Health check |
| `/api/auth-status` | GET | Authentication status |
| `/api/login` | POST | Login with credentials |
| `/api/logout` | POST | Logout |

## Features

### GUI
- System tray icon with context menu
- Settings window with 3 tabs: Connection, Settings, About
- Copy MCP server URL to clipboard
- TastyTrade login/logout via dialog
- Launch at startup setting (platform-specific)

### Security
- Credentials stored in OS keyring (macOS Keychain, Windows Credential Manager, Linux Secret Service)
- SSL certificates auto-fetched from cert API
- Certificate caching with auto-refresh

## Project Structure

```
src-go/
├── main.go                      # Entry point
├── Makefile                     # Build targets
├── go.mod                       # Dependencies
├── internal/
│   ├── app/                     # Application lifecycle
│   ├── cache/                   # In-memory TTL cache
│   ├── config/                  # Configuration management
│   ├── credentials/             # OS keyring credential storage
│   ├── mcp/                     # MCP server and tools
│   ├── ssl/                     # SSL certificate management
│   ├── state/                   # App state and preferences
│   └── tastytrade/              # TastyTrade API client
├── ui/
│   ├── tray.go                  # System tray manager
│   ├── window.go                # Main window
│   ├── pages/                   # UI pages
│   └── dialogs/                 # Dialogs
└── resources/
    ├── icon.png                 # App icon
    └── resources.go             # Embedded resources
```

## Binary Size

| Build | Size |
|-------|------|
| Default | ~24MB |
| Optimized (`-ldflags="-s -w"`) | ~18MB |
