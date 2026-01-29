# Local Development

## Overview

Local development for TTAI supports two workflows:

- **Sidecar Mode**: Full Tauri desktop app with Python MCP server as a subprocess
- **Headless Mode**: Python MCP server running standalone, accessed by external clients

This guide covers prerequisites, project setup, and development workflows for both modes.

## Development Modes

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    Local Development Options                                 │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  SIDECAR MODE (Full Desktop App)         HEADLESS MODE (Server Only)        │
│  ┌────────────────────────────────┐     ┌────────────────────────────────┐  │
│  │     pnpm tauri dev             │     │  python -m src.server.main     │  │
│  │                                │     │     --transport sse            │  │
│  │  ┌──────────────────────────┐  │     │                                │  │
│  │  │      Vite Dev Server     │  │     │  ┌──────────────────────────┐  │  │
│  │  │      localhost:5173      │  │     │  │     HTTP/SSE Server      │  │  │
│  │  └──────────────────────────┘  │     │  │     localhost:5180       │  │  │
│  │              │                 │     │  └──────────────────────────┘  │  │
│  │  ┌──────────────────────────┐  │     │              │                 │  │
│  │  │      Tauri Window        │  │     │              │                 │  │
│  │  │       (WebView)          │  │     │              │                 │  │
│  │  └──────────────────────────┘  │     │              ▼                 │  │
│  │              │                 │     │  ┌──────────────────────────┐  │  │
│  │              │ stdio           │     │  │   Claude Desktop         │  │  │
│  │  ┌──────────────────────────┐  │     │  │   or other MCP client   │  │  │
│  │  │    Python MCP Server     │  │     │  └──────────────────────────┘  │  │
│  │  │      (Sidecar)           │  │     │                                │  │
│  │  └──────────────────────────┘  │     └────────────────────────────────┘  │
│  └────────────────────────────────┘                                          │
│                                                                              │
│  Use case: Desktop app development       Use case: Server/API development   │
│            Full system testing                      Testing with Claude      │
│            Settings UI iteration                    Quick iteration          │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Prerequisites

### Required Tools

| Tool | Version | Purpose |
|------|---------|---------|
| Python | 3.11+ | MCP server |
| Git | 2.x | Version control |
| Node.js | 20+ | Frontend tooling (sidecar mode only) |
| pnpm | 8+ | Package manager (sidecar mode only) |
| Rust | 1.75+ | Tauri backend (sidecar mode only) |

### Platform-Specific Requirements

#### macOS

```bash
# Install Xcode Command Line Tools
xcode-select --install

# Install Homebrew (if not installed)
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Install Python via pyenv
brew install pyenv
pyenv install 3.11
pyenv global 3.11

# For sidecar mode only:
# Install Rust
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh

# Install Node.js via nvm
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.0/install.sh | bash
nvm install 20
nvm use 20

# Install pnpm
npm install -g pnpm
```

#### Windows

```powershell
# Install Python
# Download from https://python.org
# Ensure "Add to PATH" is checked during installation

# For sidecar mode only:
# Install Visual Studio Build Tools
# Download from: https://visualstudio.microsoft.com/visual-cpp-build-tools/
# Select "Desktop development with C++"

# Install Rust
# Download rustup-init.exe from https://rustup.rs

# Install Node.js
# Download from https://nodejs.org (LTS version)

# Install pnpm
npm install -g pnpm
```

#### Linux (Ubuntu/Debian)

```bash
# Install Python
sudo apt-get update
sudo apt-get install -y python3.11 python3.11-venv python3-pip

# For sidecar mode only:
# Install system dependencies
sudo apt-get install -y \
    build-essential \
    curl \
    wget \
    file \
    libssl-dev \
    libgtk-3-dev \
    libayatana-appindicator3-dev \
    librsvg2-dev \
    libwebkit2gtk-4.1-dev

# Install Rust
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
source $HOME/.cargo/env

# Install Node.js via nvm
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.0/install.sh | bash
source ~/.bashrc
nvm install 20

# Install pnpm
npm install -g pnpm
```

## Project Setup

### 1. Clone the Repository

```bash
git clone https://github.com/your-org/ttai.git
cd ttai
```

### 2. Install Python Dependencies

```bash
# Create and activate virtual environment
cd src-python
python -m venv .venv

# Activate venv
# macOS/Linux:
source .venv/bin/activate
# Windows:
.venv\Scripts\activate

# Install dependencies in development mode
pip install -e ".[dev]"

# Return to project root
cd ..
```

### 3. Install Frontend Dependencies (Sidecar Mode Only)

```bash
# Install Node.js dependencies
pnpm install
```

### 4. Verify Installation

```bash
# Check Python
python --version
pip --version

# For sidecar mode:
# Check Rust
rustc --version
cargo --version

# Check Node.js/pnpm
node --version
pnpm --version

# Check Tauri CLI
pnpm tauri --version
```

## Headless Development Workflow

Headless mode is the simplest way to develop and test the Python MCP server. Run the server standalone and connect with external MCP clients.

### Running the Headless Server

```bash
cd src-python
source .venv/bin/activate

# Run with HTTP/SSE transport
python -m src.server.main --transport sse --port 5180

# With debug logging
TTAI_LOG_LEVEL=DEBUG python -m src.server.main --transport sse --port 5180

# Or use environment variables
TTAI_TRANSPORT=sse TTAI_PORT=5180 python -m src.server.main
```

The server will be available at `http://localhost:5180/sse`.

### Connecting Claude Desktop

Configure Claude Desktop to connect to your local server:

```json
// ~/.config/claude/mcp.json (macOS/Linux)
// %APPDATA%\Claude\mcp.json (Windows)
{
  "mcpServers": {
    "ttai-dev": {
      "url": "http://localhost:5180/sse",
      "description": "TTAI Development Server"
    }
  }
}
```

Restart Claude Desktop to pick up the configuration.

### Testing with curl

```bash
# Check server health
curl http://localhost:5180/health

# List available tools
curl -X POST http://localhost:5180/messages \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'

# Call a tool
curl -X POST http://localhost:5180/messages \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"get_quote","arguments":{"symbol":"AAPL"}}}'
```

### Headless Environment Variables

Create a `.env` file in `src-python/`:

```bash
# src-python/.env

# Transport
TTAI_TRANSPORT=sse
TTAI_HOST=localhost
TTAI_PORT=5180

# Data directory (separate from production)
TTAI_DATA_DIR=~/.ttai-dev

# Logging
TTAI_LOG_LEVEL=DEBUG

# TastyTrade sandbox (for testing without real money)
TASTYTRADE_API_URL=https://api.cert.tastyworks.com

# Notifications (optional - for webhook testing)
# TTAI_WEBHOOK_URL=http://localhost:9000/webhook

# LLM provider (for AI agents)
ANTHROPIC_API_KEY=sk-ant-xxx
```

## Sidecar Development Workflow

Sidecar mode runs the full desktop application with hot-reload for frontend development. The frontend is a Settings interface for configuring credentials, preferences, and testing connections—trading analysis happens via MCP tools in external clients like Claude Desktop.

### Running in Sidecar Mode

```bash
# Start the full development environment
pnpm tauri dev
```

This command:
1. Starts Vite dev server on http://localhost:5173
2. Compiles the Rust code
3. Launches the Tauri window
4. Spawns the Python MCP server as sidecar (stdio transport)
5. Enables hot reload for Svelte changes

### Component-Specific Development

#### Frontend Only (no Tauri)

```bash
# Run just the Svelte frontend
pnpm dev
```

Access at http://localhost:5173. Useful for UI development without backend.

#### Using a Separate Terminal for Python

For easier Python debugging, run the Python server separately:

```bash
# Terminal 1: Frontend + Tauri (without auto-spawning sidecar)
TTAI_SKIP_SIDECAR=true pnpm tauri dev

# Terminal 2: Python server with verbose logging
cd src-python
source .venv/bin/activate
TTAI_LOG_LEVEL=DEBUG python -m src.server.main
```

### Sidecar Environment Configuration

Create a `.env.local` file in the project root:

```bash
# .env.local (not committed to git)

# TastyTrade sandbox (for testing without real money)
TASTYTRADE_API_URL=https://api.cert.tastyworks.com

# LLM provider (for AI agents)
ANTHROPIC_API_KEY=sk-ant-xxx

# Debug mode
TTAI_DEBUG=true
TTAI_LOG_LEVEL=DEBUG

# Development data directory (separate from production)
TTAI_DATA_DIR=~/.ttai-dev
```

## Testing

### Python Tests

```bash
cd src-python

# Run all tests
pytest tests/ -v

# Run with coverage
pytest tests/ -v --cov=src --cov-report=html

# Run specific test file
pytest tests/test_services/test_tastytrade.py -v

# Run tests matching pattern
pytest tests/ -v -k "test_quote"
```

### Frontend Tests (Sidecar Mode)

```bash
# Run Svelte/TypeScript tests
pnpm test

# Run with coverage
pnpm test:coverage

# Run in watch mode
pnpm test:watch
```

### Rust Tests (Sidecar Mode)

```bash
cd src-tauri

# Run Rust tests
cargo test

# Run with output
cargo test -- --nocapture
```

## Debugging

### Python Debugging

#### VS Code Debugger

```json
// .vscode/launch.json
{
  "version": "0.2.0",
  "configurations": [
    {
      "name": "Debug Python Server (Headless)",
      "type": "python",
      "request": "launch",
      "module": "src.server.main",
      "args": ["--transport", "sse", "--port", "5180"],
      "cwd": "${workspaceFolder}/src-python",
      "env": {
        "TTAI_LOG_LEVEL": "DEBUG"
      },
      "console": "integratedTerminal"
    },
    {
      "name": "Debug Python Server (stdio)",
      "type": "python",
      "request": "launch",
      "module": "src.server.main",
      "cwd": "${workspaceFolder}/src-python",
      "env": {
        "TTAI_LOG_LEVEL": "DEBUG"
      },
      "console": "integratedTerminal"
    }
  ]
}
```

#### Debug with pdb

```python
# Add breakpoint in Python code
import pdb; pdb.set_trace()

# Or use built-in breakpoint() (Python 3.7+)
breakpoint()
```

### Frontend Debugging (Sidecar Mode)

1. **Browser DevTools**: Right-click in the Tauri window → "Inspect Element"
2. **VS Code Debugger**: Use the "Debug Tauri" launch configuration

```json
// .vscode/launch.json
{
  "version": "0.2.0",
  "configurations": [
    {
      "type": "chrome",
      "request": "attach",
      "name": "Debug Tauri",
      "url": "http://localhost:5173",
      "webRoot": "${workspaceFolder}/src"
    }
  ]
}
```

### Viewing Logs

```bash
# Python server logs (when running separately)
tail -f ~/.ttai-dev/logs/ttai-*.log

# Tauri logs (macOS)
tail -f ~/Library/Logs/com.ttai.app/main.log

# All logs in one terminal
multitail ~/.ttai-dev/logs/*.log
```

## Common Development Tasks

### Adding a New MCP Tool

1. Define the tool in `src-python/src/server/tools.py`:

```python
@server.tool()
async def my_new_tool(param1: str, param2: int = 10) -> list[TextContent]:
    """Description of what this tool does."""
    result = await some_service.do_something(param1, param2)
    return [TextContent(type="text", text=json.dumps(result))]
```

2. Test with headless server:

```bash
# Start server
python -m src.server.main --transport sse --port 5180

# Test the tool
curl -X POST http://localhost:5180/messages \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"my_new_tool","arguments":{"param1":"test"}}}'
```

3. For sidecar mode, add Tauri command in `src-tauri/src/commands.rs`:

```rust
#[tauri::command]
pub async fn my_new_tool(
    mcp: State<'_, McpClient>,
    param1: String,
    param2: Option<i32>,
) -> Result<Value, String> {
    let args = serde_json::json!({
        "param1": param1,
        "param2": param2.unwrap_or(10),
    });
    mcp.call_tool("my_new_tool", args).await
}
```

4. Export from frontend API in `src/lib/api.ts`:

```typescript
export async function myNewTool(param1: string, param2?: number): Promise<Result> {
  return invoke('my_new_tool', { param1, param2 });
}
```

### Testing Webhooks (Headless Mode)

For testing notifications with webhooks:

```bash
# Terminal 1: Start a simple webhook receiver
python -c "
from http.server import HTTPServer, BaseHTTPRequestHandler
import json

class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers['Content-Length'])
        data = json.loads(self.rfile.read(length))
        print(json.dumps(data, indent=2))
        self.send_response(200)
        self.end_headers()

HTTPServer(('', 9000), Handler).serve_forever()
"

# Terminal 2: Start TTAI server with webhook
TTAI_WEBHOOK_URL=http://localhost:9000/webhook \
python -m src.server.main --transport sse --port 5180
```

### Updating Dependencies

```bash
# Python dependencies
cd src-python
pip install --upgrade -e ".[dev]"

# Frontend dependencies (sidecar mode)
pnpm update

# Rust dependencies (sidecar mode)
cd src-tauri
cargo update
```

### Running Linters

```bash
# Python
cd src-python
ruff check src/
black src/
mypy src/

# Frontend (sidecar mode)
pnpm lint
pnpm format

# Rust (sidecar mode)
cd src-tauri
cargo clippy
cargo fmt
```

## Troubleshooting

### Common Issues

#### "Address already in use" (Headless Mode)

Another process is using port 5180:

```bash
# Find the process
lsof -i :5180

# Use a different port
python -m src.server.main --transport sse --port 8081
```

#### "Sidecar not found" (Sidecar Mode)

The Python sidecar binary is missing. Build it:

```bash
cd src-python
python scripts/build.py
```

#### Python import errors

Ensure you're using the virtual environment:

```bash
cd src-python
source .venv/bin/activate
pip install -e ".[dev]"
```

#### "Cannot connect to TastyTrade"

Check your credentials and network. For development, use the sandbox API:

```bash
export TASTYTRADE_API_URL=https://api.cert.tastyworks.com
```

#### WebKit errors on Linux (Sidecar Mode)

Install WebKit dependencies:

```bash
sudo apt-get install libwebkit2gtk-4.1-dev
```

### Getting Help

- Check existing issues on GitHub
- Review the architecture docs in `/docs/architecture/`
- Join the Discord community (link in README)

## Cross-References

- [MCP Server Design](./01-mcp-server-design.md) - Dual-mode architecture
- [Python Server](./03-python-server.md) - Python project structure, running modes
- [Background Tasks](./06-background-tasks.md) - Notification backends for both modes
- [Build and Distribution](./08-build-distribution.md) - Building release versions
- [Integration Patterns](./09-integration-patterns.md) - Tauri ↔ Python and HTTP/SSE communication
- [Frontend Architecture](./11-frontend.md) - Settings UI, Tailwind CSS, DaisyUI
