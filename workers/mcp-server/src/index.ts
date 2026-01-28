import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { WebStandardStreamableHTTPServerTransport } from "@modelcontextprotocol/sdk/server/webStandardStreamableHttp.js";
import { z } from "zod";
import type { D1Database } from "@cloudflare/workers-types";
import {
  handleOAuthDiscovery,
  handleAuthorize,
  handleCallback,
  handleToken,
  cleanupExpiredStates,
} from "./auth/oauth";
import {
  authenticateRequest,
  unauthorizedResponse,
  type AuthContext,
} from "./auth/middleware";

export interface Env {
  ENVIRONMENT: string;
  PYTHON_WORKER: Fetcher;
  DB: D1Database;
  JWT_SECRET: string;
  TOKEN_ENCRYPTION_KEY: string;
  TT_CLIENT_ID: string;
  TT_CLIENT_SECRET: string;
}

interface QuoteResponse {
  data?: Record<string, unknown>;
  error?: string;
}

function createMcpServer(env: Env, authContext: AuthContext | null): McpServer {
  const server = new McpServer({
    name: "ttai-mcp-server",
    version: "0.1.0",
  });

  // Register the get_quote tool
  server.tool(
    "get_quote",
    "Get a stock quote with bid/ask/last prices and market metrics (IV rank, beta, etc.) from TastyTrade.",
    {
      symbol: z
        .string()
        .describe("The stock symbol to get a quote for (e.g., AAPL, GOOGL)"),
    },
    async ({ symbol }) => {
      try {
        // Build headers for Python worker
        const headers: Record<string, string> = {
          "Content-Type": "application/json",
        };

        // If authenticated, pass the user's access token
        if (authContext?.tokens) {
          headers["X-TT-Access-Token"] = authContext.tokens.accessToken;
        }

        // Call the Python worker via service binding
        const response = await env.PYTHON_WORKER.fetch(
          "http://python-worker/quotes",
          {
            method: "POST",
            headers,
            body: JSON.stringify({ symbols: [symbol.toUpperCase()] }),
          }
        );

        if (!response.ok) {
          const errorData = (await response.json()) as QuoteResponse;
          return {
            content: [
              {
                type: "text" as const,
                text: `Error fetching quote for ${symbol}: ${errorData.error || response.statusText}`,
              },
            ],
            isError: true,
          };
        }

        const data = (await response.json()) as QuoteResponse;

        return {
          content: [
            {
              type: "text" as const,
              text: JSON.stringify(data.data || data, null, 2),
            },
          ],
        };
      } catch (error) {
        const message = error instanceof Error ? error.message : "Unknown error";
        return {
          content: [
            {
              type: "text" as const,
              text: `Error fetching quote for ${symbol}: ${message}`,
            },
          ],
          isError: true,
        };
      }
    }
  );

  return server;
}

export default {
  async fetch(
    request: Request,
    env: Env,
    ctx: ExecutionContext
  ): Promise<Response> {
    const url = new URL(request.url);
    const baseUrl = `${url.protocol}//${url.host}`;

    // OAuth discovery endpoint (RFC 8414)
    if (url.pathname === "/.well-known/oauth-authorization-server") {
      return handleOAuthDiscovery(baseUrl);
    }

    // OAuth authorize endpoint
    if (url.pathname === "/oauth/authorize") {
      return handleAuthorize(request, env);
    }

    // OAuth callback endpoint
    if (url.pathname === "/oauth/callback") {
      return handleCallback(request, env);
    }

    // OAuth token endpoint
    if (url.pathname === "/oauth/token") {
      return handleToken(request, env);
    }

    // Health check endpoint
    if (url.pathname === "/health") {
      return Response.json({
        status: "healthy",
        environment: env.ENVIRONMENT,
        timestamp: new Date().toISOString(),
        auth_enabled: true,
      });
    }

    // Debug endpoint to test Python worker connection
    if (url.pathname === "/debug/python-worker") {
      try {
        const response = await env.PYTHON_WORKER.fetch(
          "http://python-worker/health"
        );
        const data = await response.json();
        return Response.json({
          status: "connected",
          python_worker: data,
        });
      } catch (error) {
        return Response.json(
          {
            status: "error",
            error: error instanceof Error ? error.message : String(error),
          },
          { status: 500 }
        );
      }
    }

    // HEAD request returns protocol version (required by Claude.ai)
    if (request.method === "HEAD") {
      return new Response(null, {
        headers: { "MCP-Protocol-Version": "2025-06-18" },
      });
    }

    // MCP endpoints - require authentication
    try {
      // Authenticate the request
      const authContext = await authenticateRequest(request, env);

      // For MCP requests, we require authentication
      // But allow unauthenticated for backward compatibility if no JWT_SECRET configured
      if (!authContext && env.JWT_SECRET) {
        return unauthorizedResponse(
          "Authentication required. Please authenticate via /oauth/authorize"
        );
      }

      const server = createMcpServer(env, authContext);

      // Create a Web Standard Streamable HTTP transport for this request
      const transport = new WebStandardStreamableHTTPServerTransport({
        sessionIdGenerator: undefined, // Stateless mode
        enableJsonResponse: true, // Return JSON instead of SSE for simple requests
      });

      // Connect the server to the transport
      await server.connect(transport);

      // Handle the request and return the response
      return await transport.handleRequest(request);
    } catch (error) {
      console.error("MCP error:", error);
      return Response.json(
        {
          jsonrpc: "2.0",
          error: {
            code: -32603,
            message: "Internal error",
          },
          id: null,
        },
        { status: 500 }
      );
    }
  },

  // Scheduled task to clean up expired OAuth states
  async scheduled(
    _controller: ScheduledController,
    env: Env,
    _ctx: ExecutionContext
  ): Promise<void> {
    await cleanupExpiredStates(env.DB);
  },
};
