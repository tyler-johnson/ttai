# TTAI - TastyTrade AI

An AI-assisted trading analysis system that provides tools for portfolio analysis, options strategies, and market research via the [Model Context Protocol](https://modelcontextprotocol.io/).

## Components

| Directory | Description |
|-----------|-------------|
| [`src-go/`](src-go/) | Go MCP server with system tray GUI (primary implementation) |
| [`src-web/`](src-web/) | SvelteKit web UI embedded in the Go app |
| [`src-python/`](src-python/) | Python MCP server (reference implementation) |
| [`cert-api/`](cert-api/) | Cloudflare Worker for SSL certificate distribution |

## Features

- **MCP Server**: Exposes TastyTrade trading tools to AI assistants like Claude
- **Multiple Transports**: HTTP, HTTPS, and stdio modes for flexible integration
- **System Tray App**: Native GUI with settings window (macOS, Windows, Linux)
- **Secure Credentials**: Stores OAuth tokens in system keyring
- **Cross-Platform**: Builds for macOS (Intel/Apple Silicon), Windows, and Linux

## Quick Start

### Go (Recommended)

```bash
cd src-go
make build
./ttai
```

See [src-go/README.md](src-go/README.md) for full documentation.

### Python

```bash
cd src-python
pip install -e ".[dev]"
ttai-server
```

See [src-python/README.md](src-python/README.md) for full documentation.

## MCP Tools

| Tool | Description |
|------|-------------|
| `ping` | Verify server connectivity |
| `login` | Authenticate with TastyTrade OAuth |
| `logout` | Log out and clear credentials |
| `get_auth_status` | Check authentication status |
| `get_quote` | Get quote data (price, volume, IV, beta, etc.) |

## Claude Desktop Integration

### Stdio Mode (Subprocess)

```json
{
  "mcpServers": {
    "ttai": {
      "command": "/path/to/ttai",
      "args": ["--headless", "--transport", "stdio"]
    }
  }
}
```

### HTTP Mode

```json
{
  "mcpServers": {
    "ttai": {
      "url": "http://localhost:5180/sse"
    }
  }
}
```

## SSL Support

The project includes a Cloudflare Worker (`cert-api/`) that provides SSL certificates for running the MCP server over HTTPS. See [cert-api/SETUP.md](cert-api/SETUP.md) for deployment instructions.

## Data Storage

- **Config/Logs**: `~/.ttai/`
- **Credentials**: System keyring (macOS Keychain, Windows Credential Manager, Linux Secret Service)

## Requirements

- Go 1.22+ (for building from source)
- Node.js 20+ (for building the web UI)
- TastyTrade account with OAuth credentials

## Releases

Pre-built binaries are available on the [Releases](../../releases) page:

| Platform | File |
|----------|------|
| macOS (Apple Silicon) | `TTAI-darwin-arm64.zip` |
| macOS (Intel) | `TTAI-darwin-amd64.zip` |
| Windows | `TTAI-windows.exe` |
| Linux | `TTAI-linux` |

macOS releases are signed and notarized - no Gatekeeper warnings.

## License

[MIT License](LICENSE)
