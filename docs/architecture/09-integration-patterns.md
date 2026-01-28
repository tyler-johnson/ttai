# Integration Patterns

## Overview

TTAI supports two integration modes, both using the MCP protocol:

- **Sidecar Mode**: Tauri desktop app spawns Python MCP server, communicating via stdio
- **Headless Mode**: External clients connect to Python MCP server via HTTP/SSE

Both modes provide the same MCP tools, resources, and prompts—the only difference is the transport layer.

## Integration Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                      TTAI Integration Patterns                               │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  SIDECAR MODE                              HEADLESS MODE                    │
│  ┌─────────────────────────────┐          ┌─────────────────────────────┐  │
│  │     Tauri Desktop App       │          │   External MCP Clients      │  │
│  │  ┌───────────────────────┐  │          │  ┌───────────────────────┐  │  │
│  │  │   Settings UI         │  │          │  │   Claude Desktop      │  │  │
│  │  └───────────┬───────────┘  │          │  │   Custom Apps         │  │  │
│  │              │ IPC          │          │  │   Scripts             │  │  │
│  │  ┌───────────┴───────────┐  │          │  └───────────┬───────────┘  │  │
│  │  │   Rust Shell          │  │          │              │ HTTP         │  │
│  │  │   (Sidecar Manager)   │  │          │              │              │  │
│  │  └───────────┬───────────┘  │          └──────────────┼──────────────┘  │
│  │              │ stdio        │                         │                  │
│  └──────────────┼──────────────┘                         │                  │
│                 │                                        │                  │
│                 ▼                                        ▼                  │
│  ┌──────────────────────────────────────────────────────────────────────┐  │
│  │                      Python MCP Server                                │  │
│  │  ┌──────────────────────┐        ┌──────────────────────┐            │  │
│  │  │   stdio Transport    │        │   HTTP/SSE Transport │            │  │
│  │  │   (Sidecar mode)     │        │   (Headless mode)    │            │  │
│  │  └──────────────────────┘        └──────────────────────┘            │  │
│  │                                                                       │  │
│  │  ┌────────────────────────────────────────────────────────────────┐  │  │
│  │  │                    MCP Protocol Layer                           │  │  │
│  │  │  Tools | Resources | Prompts | Notifications                    │  │  │
│  │  └────────────────────────────────────────────────────────────────┘  │  │
│  └──────────────────────────────────────────────────────────────────────┘  │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Sidecar Mode (Tauri ↔ Python)

### Architecture

In sidecar mode, the Tauri Rust shell spawns the Python MCP server as a subprocess and communicates via stdio using JSON-RPC messages.

```
┌──────────────────────────────────────────────────────────────────────┐
│                    Tauri Desktop Application                          │
├──────────────────────────────────────────────────────────────────────┤
│                                                                       │
│  ┌─────────────────────────────────────────────────────────────────┐ │
│  │                  Settings UI (WebView)                           │ │
│  │                                                                   │ │
│  │  invoke('mcp_call_tool', { name: 'get_quote', args: {...} })    │ │
│  │                              │                                    │ │
│  └──────────────────────────────┼────────────────────────────────────┘ │
│                                 │ Tauri IPC                           │
│  ┌──────────────────────────────┼────────────────────────────────────┐ │
│  │                  Rust Core   │                                    │ │
│  │                              ▼                                    │ │
│  │  ┌────────────────────────────────────────────────────────────┐  │ │
│  │  │                   Sidecar Manager                          │  │ │
│  │  │  - Spawn Python process                                    │  │ │
│  │  │  - Route MCP requests via stdio                           │  │ │
│  │  │  - Parse stderr for notifications                         │  │ │
│  │  │  - Handle process lifecycle                               │  │ │
│  │  └────────────────────────────────────────────────────────────┘  │ │
│  │                              │                                    │ │
│  │                              │ stdin/stdout (JSON-RPC)            │ │
│  │                              │ stderr (notifications)             │ │
│  └──────────────────────────────┼────────────────────────────────────┘ │
│                                 │                                      │
└─────────────────────────────────┼──────────────────────────────────────┘
                                  │
                                  ▼
┌──────────────────────────────────────────────────────────────────────┐
│                    Python MCP Server (Sidecar)                        │
│                                                                       │
│  stdin ──► MCP Protocol Handler ──► Tool Execution                   │
│                                           │                           │
│  stdout ◄─────────── Response ◄──────────┘                           │
│                                                                       │
│  stderr ◄─────────── Notifications (JSON lines)                      │
│                                                                       │
└──────────────────────────────────────────────────────────────────────┘
```

### Rust Sidecar Manager

```rust
// src-tauri/src/sidecar.rs
use tauri::plugin::TauriPlugin;
use tauri::{AppHandle, Runtime, Manager};
use tauri_plugin_shell::ShellExt;
use std::sync::Arc;
use tokio::sync::RwLock;
use tokio::io::{AsyncBufReadExt, AsyncWriteExt, BufReader};
use serde::{Deserialize, Serialize};
use serde_json::Value;

#[derive(Debug, Serialize, Deserialize)]
struct McpRequest {
    jsonrpc: String,
    id: u64,
    method: String,
    params: Option<Value>,
}

#[derive(Debug, Serialize, Deserialize)]
struct McpResponse {
    jsonrpc: String,
    id: u64,
    result: Option<Value>,
    error: Option<McpError>,
}

#[derive(Debug, Serialize, Deserialize)]
struct McpError {
    code: i32,
    message: String,
    data: Option<Value>,
}

#[derive(Debug, Serialize, Deserialize)]
struct Notification {
    #[serde(rename = "type")]
    notification_type: String,
    title: String,
    body: String,
    data: Option<Value>,
}

pub struct SidecarManager {
    process: Option<tokio::process::Child>,
    stdin: Option<tokio::process::ChildStdin>,
    request_id: u64,
}

impl SidecarManager {
    pub fn new() -> Self {
        Self {
            process: None,
            stdin: None,
            request_id: 0,
        }
    }

    pub async fn start<R: Runtime>(
        &mut self,
        app: &AppHandle<R>
    ) -> Result<(), String> {
        let shell = app.shell();

        // Spawn the sidecar process
        let sidecar = shell
            .sidecar("ttai-server")
            .map_err(|e| format!("Failed to create sidecar command: {}", e))?
            .spawn()
            .map_err(|e| format!("Failed to spawn sidecar: {}", e))?;

        let (mut rx, child) = sidecar;

        // Store process handle
        self.process = Some(child);

        // Handle stdout (MCP responses)
        let app_handle = app.clone();
        tokio::spawn(async move {
            while let Some(event) = rx.recv().await {
                match event {
                    tauri_plugin_shell::process::CommandEvent::Stdout(line) => {
                        // Parse and handle MCP response
                        if let Ok(response) = serde_json::from_slice::<McpResponse>(&line) {
                            // Route response to waiting caller
                            app_handle.emit_all("mcp:response", response).ok();
                        }
                    }
                    tauri_plugin_shell::process::CommandEvent::Stderr(line) => {
                        // Parse notifications from stderr
                        if let Ok(text) = String::from_utf8(line) {
                            if let Ok(notification) = serde_json::from_str::<Notification>(&text) {
                                handle_notification(&app_handle, notification);
                            }
                        }
                    }
                    tauri_plugin_shell::process::CommandEvent::Error(e) => {
                        log::error!("Sidecar error: {}", e);
                    }
                    tauri_plugin_shell::process::CommandEvent::Terminated(status) => {
                        log::info!("Sidecar terminated with status: {:?}", status);
                        break;
                    }
                    _ => {}
                }
            }
        });

        Ok(())
    }

    pub async fn call_tool(
        &mut self,
        name: &str,
        arguments: Value
    ) -> Result<Value, String> {
        self.request_id += 1;

        let request = McpRequest {
            jsonrpc: "2.0".to_string(),
            id: self.request_id,
            method: "tools/call".to_string(),
            params: Some(serde_json::json!({
                "name": name,
                "arguments": arguments
            })),
        };

        self.send_request(request).await
    }

    pub async fn read_resource(&mut self, uri: &str) -> Result<Value, String> {
        self.request_id += 1;

        let request = McpRequest {
            jsonrpc: "2.0".to_string(),
            id: self.request_id,
            method: "resources/read".to_string(),
            params: Some(serde_json::json!({
                "uri": uri
            })),
        };

        self.send_request(request).await
    }

    async fn send_request(&mut self, request: McpRequest) -> Result<Value, String> {
        let stdin = self.stdin.as_mut()
            .ok_or("Sidecar not started")?;

        let request_json = serde_json::to_string(&request)
            .map_err(|e| format!("Failed to serialize request: {}", e))?;

        stdin.write_all(request_json.as_bytes()).await
            .map_err(|e| format!("Failed to write to sidecar: {}", e))?;
        stdin.write_all(b"\n").await
            .map_err(|e| format!("Failed to write newline: {}", e))?;
        stdin.flush().await
            .map_err(|e| format!("Failed to flush: {}", e))?;

        // Response will come via the stdout handler
        // In practice, you'd use a channel to wait for the response
        Ok(serde_json::json!({"status": "pending", "id": request.id}))
    }

    pub async fn stop(&mut self) -> Result<(), String> {
        if let Some(mut process) = self.process.take() {
            process.kill().await
                .map_err(|e| format!("Failed to kill sidecar: {}", e))?;
        }
        self.stdin = None;
        Ok(())
    }
}

fn handle_notification<R: Runtime>(app: &AppHandle<R>, notification: Notification) {
    use tauri_plugin_notification::NotificationExt;

    // Show OS notification
    app.notification()
        .builder()
        .title(&notification.title)
        .body(&notification.body)
        .show()
        .ok();

    // Also emit to frontend for in-app display
    app.emit_all("ttai:notification", &notification).ok();
}
```

### Tauri Commands

```rust
// src-tauri/src/commands.rs
use tauri::{command, State, AppHandle, Runtime};
use std::sync::Arc;
use tokio::sync::RwLock;
use serde_json::Value;

use crate::sidecar::SidecarManager;

pub type SidecarState = Arc<RwLock<SidecarManager>>;

#[command]
pub async fn mcp_call_tool(
    state: State<'_, SidecarState>,
    name: String,
    arguments: Value
) -> Result<Value, String> {
    let mut sidecar = state.write().await;
    sidecar.call_tool(&name, arguments).await
}

#[command]
pub async fn mcp_read_resource(
    state: State<'_, SidecarState>,
    uri: String
) -> Result<Value, String> {
    let mut sidecar = state.write().await;
    sidecar.read_resource(&uri).await
}

#[command]
pub async fn mcp_get_prompt(
    state: State<'_, SidecarState>,
    name: String,
    arguments: Option<Value>
) -> Result<Value, String> {
    // Similar implementation
    todo!()
}

#[command]
pub async fn start_mcp_server(
    app: AppHandle,
    state: State<'_, SidecarState>
) -> Result<(), String> {
    let mut sidecar = state.write().await;
    sidecar.start(&app).await
}

#[command]
pub async fn stop_mcp_server(
    state: State<'_, SidecarState>
) -> Result<(), String> {
    let mut sidecar = state.write().await;
    sidecar.stop().await
}
```

### Frontend Integration

The Settings UI uses the MCP client to manage configuration and test connections. Trading analysis happens via external MCP clients (like Claude Desktop), not through the desktop app's UI.

```typescript
// src/lib/mcp-client.ts
import { invoke } from '@tauri-apps/api/core';
import { listen } from '@tauri-apps/api/event';

export interface McpToolResult {
  content: Array<{
    type: 'text' | 'image';
    text?: string;
    data?: string;
    mimeType?: string;
  }>;
}

export interface McpNotification {
  type: string;
  title: string;
  body: string;
  data?: Record<string, unknown>;
}

class McpClient {
  private notificationListeners: Array<(n: McpNotification) => void> = [];

  constructor() {
    // Listen for notifications from Python server
    listen<McpNotification>('ttai:notification', (event) => {
      this.notificationListeners.forEach(fn => fn(event.payload));
    });
  }

  async callTool(name: string, arguments: Record<string, unknown>): Promise<McpToolResult> {
    return invoke('mcp_call_tool', { name, arguments });
  }

  async readResource(uri: string): Promise<string> {
    return invoke('mcp_read_resource', { uri });
  }

  async getPrompt(name: string, arguments?: Record<string, unknown>): Promise<unknown> {
    return invoke('mcp_get_prompt', { name, arguments });
  }

  onNotification(callback: (notification: McpNotification) => void): () => void {
    this.notificationListeners.push(callback);
    return () => {
      const idx = this.notificationListeners.indexOf(callback);
      if (idx >= 0) this.notificationListeners.splice(idx, 1);
    };
  }

  // Configuration methods (used by Settings UI)
  async getConfig(): Promise<McpToolResult> {
    return this.callTool('get_config', {});
  }

  async updateConfig(config: Record<string, unknown>): Promise<McpToolResult> {
    return this.callTool('update_config', { config });
  }

  async testConnection(): Promise<McpToolResult> {
    return this.callTool('test_connection', {});
  }
}

export const mcpClient = new McpClient();
```

## Headless Mode (HTTP/SSE)

### Architecture

In headless mode, the Python MCP server runs standalone and accepts connections via HTTP/SSE from any MCP-compatible client.

```
┌──────────────────────────────────────────────────────────────────────┐
│                    External MCP Clients                               │
├──────────────────────────────────────────────────────────────────────┤
│                                                                       │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐       │
│  │  Claude Desktop │  │  Custom App     │  │  CLI Script     │       │
│  │                 │  │                 │  │                 │       │
│  │  MCP Client     │  │  MCP Client     │  │  MCP Client     │       │
│  └────────┬────────┘  └────────┬────────┘  └────────┬────────┘       │
│           │                    │                    │                 │
│           └────────────────────┼────────────────────┘                 │
│                                │ HTTP/SSE                             │
└────────────────────────────────┼──────────────────────────────────────┘
                                 │
                                 ▼
┌──────────────────────────────────────────────────────────────────────┐
│                Python MCP Server (Headless Mode)                      │
│                                                                       │
│  ┌────────────────────────────────────────────────────────────────┐  │
│  │                     HTTP/SSE Transport                          │  │
│  │                                                                 │  │
│  │  GET /sse ───────────► SSE Connection ───────────► Events      │  │
│  │  POST /messages ─────► Handle Message ───────────► Response    │  │
│  │                                                                 │  │
│  └────────────────────────────────────────────────────────────────┘  │
│                                                                       │
│  ┌────────────────────────────────────────────────────────────────┐  │
│  │                    MCP Protocol Layer                           │  │
│  │                    (Same as sidecar mode)                       │  │
│  └────────────────────────────────────────────────────────────────┘  │
│                                                                       │
└──────────────────────────────────────────────────────────────────────┘
```

### HTTP/SSE Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/sse` | GET | SSE connection endpoint for receiving events |
| `/messages` | POST | Send MCP messages to the server |
| `/health` | GET | Health check endpoint |

### SSE Transport Implementation

```python
# src/server/transport/sse.py
from mcp.server.sse import SseServerTransport
from starlette.applications import Starlette
from starlette.routing import Route
from starlette.responses import JSONResponse
import uvicorn

class SseTransportManager:
    """Manages HTTP/SSE transport for headless mode."""

    def __init__(self, server, host: str = "localhost", port: int = 8080):
        self.server = server
        self.host = host
        self.port = port
        self.sse = SseServerTransport("/messages")

    async def handle_sse(self, request):
        """Handle SSE connection requests."""
        async with self.sse.connect_sse(
            request.scope, request.receive, request._send
        ) as streams:
            await self.server.run(
                streams[0], streams[1],
                self.server.create_initialization_options()
            )

    async def handle_health(self, request):
        """Health check endpoint."""
        return JSONResponse({"status": "healthy"})

    def create_app(self) -> Starlette:
        """Create the ASGI application."""
        return Starlette(
            routes=[
                Route("/sse", endpoint=self.handle_sse),
                Route("/messages", endpoint=self.sse.handle_post_message, methods=["POST"]),
                Route("/health", endpoint=self.handle_health),
            ]
        )

    async def run(self):
        """Start the SSE server."""
        app = self.create_app()
        config = uvicorn.Config(
            app,
            host=self.host,
            port=self.port,
            log_level="info"
        )
        server = uvicorn.Server(config)
        await server.serve()
```

### Claude Desktop Configuration

To connect Claude Desktop to the headless TTAI server:

```json
// ~/.config/claude/mcp.json (macOS/Linux)
// %APPDATA%\Claude\mcp.json (Windows)
{
  "mcpServers": {
    "ttai": {
      "url": "http://localhost:8080/sse",
      "description": "TTAI Trading Analysis Server"
    }
  }
}
```

### Custom Client Example

```python
# Example: Custom Python client connecting to headless server
import httpx
import json
from sseclient import SSEClient

class TtaiClient:
    """Simple client for the TTAI MCP server."""

    def __init__(self, base_url: str = "http://localhost:8080"):
        self.base_url = base_url
        self.client = httpx.Client()
        self.request_id = 0

    def call_tool(self, name: str, arguments: dict) -> dict:
        """Call an MCP tool."""
        self.request_id += 1

        message = {
            "jsonrpc": "2.0",
            "id": self.request_id,
            "method": "tools/call",
            "params": {
                "name": name,
                "arguments": arguments
            }
        }

        response = self.client.post(
            f"{self.base_url}/messages",
            json=message
        )
        response.raise_for_status()
        return response.json()

    def get_quote(self, symbol: str) -> dict:
        """Get a quote for a symbol."""
        return self.call_tool("get_quote", {"symbol": symbol})

    def get_positions(self) -> dict:
        """Get current positions."""
        return self.call_tool("get_positions", {})

    def analyze(self, symbol: str, strategy: str = "csp") -> dict:
        """Run full analysis on a symbol."""
        return self.call_tool("run_full_analysis", {
            "symbol": symbol,
            "strategy": strategy
        })


# Usage example
if __name__ == "__main__":
    client = TtaiClient()

    # Get a quote
    quote = client.get_quote("AAPL")
    print(f"AAPL: ${quote['result']['content'][0]['text']}")

    # Run analysis
    analysis = client.analyze("NVDA")
    print(f"Analysis: {analysis['result']['content'][0]['text']}")
```

## Authentication

### Headless Mode Authentication

For headless deployments, the server supports API key authentication:

```python
# src/server/auth.py
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
import os

class ApiKeyMiddleware(BaseHTTPMiddleware):
    """Middleware for API key authentication in headless mode."""

    def __init__(self, app, api_key: str | None = None):
        super().__init__(app)
        self.api_key = api_key or os.getenv("TTAI_API_KEY")

    async def dispatch(self, request, call_next):
        # Skip auth for health endpoint
        if request.url.path == "/health":
            return await call_next(request)

        # Skip if no API key configured (development mode)
        if not self.api_key:
            return await call_next(request)

        # Check API key
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            return JSONResponse(
                {"error": "Missing or invalid Authorization header"},
                status_code=401
            )

        token = auth_header[7:]  # Remove "Bearer " prefix
        if token != self.api_key:
            return JSONResponse(
                {"error": "Invalid API key"},
                status_code=403
            )

        return await call_next(request)
```

### Using Authentication

```bash
# Set API key
export TTAI_API_KEY=your-secret-key

# Start server
python -m src.server.main --transport sse --port 8080

# Client request with authentication
curl -X POST http://localhost:8080/messages \
  -H "Authorization: Bearer your-secret-key" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'
```

## Data Flow Comparison

### Sidecar Mode Data Flow

```
User Action (Settings UI)
        │
        ▼
┌───────────────────┐
│  Settings Page    │
│  invoke('mcp_call_tool', {...})
└─────────┬─────────┘
          │ Tauri IPC
          ▼
┌───────────────────┐
│   Rust Command    │
│   mcp_call_tool() │
└─────────┬─────────┘
          │ Write to stdin
          ▼
┌───────────────────┐
│  Python MCP       │
│  Server (stdio)   │
└─────────┬─────────┘
          │ Tool execution
          ▼
┌───────────────────┐
│  TastyTrade API   │
└─────────┬─────────┘
          │ Response
          ▼
┌───────────────────┐
│  Python MCP       │
│  (writes stdout)  │
└─────────┬─────────┘
          │ Read stdout
          ▼
┌───────────────────┐
│   Rust Handler    │
│   (emit event)    │
└─────────┬─────────┘
          │ Tauri IPC
          ▼
┌───────────────────┐
│  Settings Page    │
│  (update UI)      │
└───────────────────┘
```

### Headless Mode Data Flow

```
External MCP Client
        │
        ▼
┌───────────────────┐
│  HTTP POST        │
│  /messages        │
└─────────┬─────────┘
          │
          ▼
┌───────────────────┐
│  Python MCP       │
│  Server (SSE)     │
└─────────┬─────────┘
          │ Tool execution
          ▼
┌───────────────────┐
│  TastyTrade API   │
└─────────┬─────────┘
          │ Response
          ▼
┌───────────────────┐
│  Python MCP       │
│  (HTTP response)  │
└─────────┬─────────┘
          │
          ▼
┌───────────────────┐
│  External Client  │
│  (receives JSON)  │
└───────────────────┘
```

## Notification Handling

### Sidecar Mode (stderr → Tauri → OS)

In sidecar mode, notifications flow from Python to the OS via Tauri:

```python
# Python side - write to stderr
print(json.dumps(notification.to_dict()), file=sys.stderr, flush=True)
```

```rust
// Rust side - read stderr and show OS notification
fn handle_notification<R: Runtime>(app: &AppHandle<R>, notification: Notification) {
    app.notification()
        .builder()
        .title(&notification.title)
        .body(&notification.body)
        .show()
        .ok();
}
```

### Headless Mode (Webhooks)

In headless mode, notifications are delivered via HTTP webhooks:

```python
# Python side - POST to webhook URL
async with httpx.AsyncClient() as client:
    await client.post(webhook_url, json=notification.to_dict())
```

See [Background Tasks](./06-background-tasks.md) for the full notification backend implementation.

## Error Handling

### Transport-Agnostic Errors

The MCP server uses the same error types regardless of transport:

```python
# src/server/errors.py
from enum import Enum
from typing import Any

class ErrorCode(int, Enum):
    """MCP-compatible error codes."""
    PARSE_ERROR = -32700
    INVALID_REQUEST = -32600
    METHOD_NOT_FOUND = -32601
    INVALID_PARAMS = -32602
    INTERNAL_ERROR = -32603

    # Application-specific codes
    AUTHENTICATION_ERROR = -32000
    TASTYTRADE_ERROR = -32001
    ANALYSIS_ERROR = -32002
    RATE_LIMIT = -32003

class McpError(Exception):
    """MCP-compatible error."""

    def __init__(
        self,
        code: ErrorCode,
        message: str,
        data: dict[str, Any] | None = None
    ):
        self.code = code
        self.message = message
        self.data = data or {}

    def to_dict(self) -> dict:
        return {
            "code": self.code.value,
            "message": self.message,
            "data": self.data
        }
```

### Error Flow

```
Python Exception
    ↓
TTAIError (with code, message, retryable)
    ↓
MCP Tool returns error in JSON-RPC response
    ↓
                    ┌────────────────────┬────────────────────┐
                    │                    │                    │
            SIDECAR MODE           HEADLESS MODE
                    │                    │
                    ▼                    ▼
        Rust McpClient          HTTP Response
        extracts error          with error JSON
                    │                    │
                    ▼                    │
        Tauri Command                    │
        returns Err                      │
                    │                    │
                    ▼                    ▼
        Frontend invoke()        Client handles
        rejects Promise          error response
```

## Cross-References

- [MCP Server Design](./01-mcp-server-design.md) - Dual-mode architecture, transport selection
- [Python Server](./03-python-server.md) - Entry point, SSE transport
- [Background Tasks](./06-background-tasks.md) - Notifications via stderr/webhooks
- [Build and Distribution](./08-build-distribution.md) - Sidecar bundling
- [Local Development](./10-local-development.md) - Running both modes
- [Frontend Architecture](./11-frontend.md) - Settings UI, Tailwind CSS, DaisyUI
