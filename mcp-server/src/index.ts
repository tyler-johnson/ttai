import { createServer, IncomingMessage, ServerResponse } from "http";

const PORT = process.env.PORT || 3000;

/**
 * Minimal MCP server stub with health check endpoint.
 * This will be expanded to include full MCP functionality.
 */

function handleRequest(req: IncomingMessage, res: ServerResponse): void {
  const url = req.url || "/";

  if (url === "/health" && req.method === "GET") {
    res.writeHead(200, { "Content-Type": "application/json" });
    res.end(JSON.stringify({ status: "healthy", timestamp: new Date().toISOString() }));
    return;
  }

  if (url === "/" && req.method === "GET") {
    res.writeHead(200, { "Content-Type": "application/json" });
    res.end(JSON.stringify({
      name: "ttai-mcp-server",
      version: "0.1.0",
      status: "running"
    }));
    return;
  }

  // TODO: Implement MCP SSE endpoint at /sse
  if (url === "/sse") {
    res.writeHead(501, { "Content-Type": "application/json" });
    res.end(JSON.stringify({ error: "MCP SSE endpoint not yet implemented" }));
    return;
  }

  res.writeHead(404, { "Content-Type": "application/json" });
  res.end(JSON.stringify({ error: "Not found" }));
}

const server = createServer(handleRequest);

server.listen(PORT, () => {
  console.log(`MCP server listening on port ${PORT}`);
  console.log(`Health check: http://localhost:${PORT}/health`);
});

// Graceful shutdown
process.on("SIGTERM", () => {
  console.log("SIGTERM received, shutting down gracefully...");
  server.close(() => {
    console.log("Server closed");
    process.exit(0);
  });
});
