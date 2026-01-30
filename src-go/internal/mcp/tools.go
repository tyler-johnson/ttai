// Package mcp provides the MCP server implementation.
package mcp

import (
	"encoding/json"

	"github.com/ttai/ttai/internal/tastytrade"
)

// Tool represents an MCP tool definition.
type Tool struct {
	Name        string          `json:"name"`
	Description string          `json:"description"`
	InputSchema json.RawMessage `json:"inputSchema"`
}

// ToolResult represents the result of a tool call.
type ToolResult struct {
	Content []ContentItem `json:"content"`
	IsError bool          `json:"isError,omitempty"`
}

// ContentItem represents a content item in a tool result.
type ContentItem struct {
	Type string `json:"type"`
	Text string `json:"text"`
}

// TextResult creates a text result.
func TextResult(text string) ToolResult {
	return ToolResult{
		Content: []ContentItem{{Type: "text", Text: text}},
	}
}

// JSONResult creates a JSON result.
func JSONResult(v interface{}) ToolResult {
	data, _ := json.Marshal(v)
	return TextResult(string(data))
}

// ErrorResult creates an error result.
func ErrorResult(message string) ToolResult {
	result := JSONResult(map[string]string{"error": message})
	result.IsError = true
	return result
}

// ToolHandler handles MCP tool calls.
type ToolHandler struct {
	client *tastytrade.Client
}

// NewToolHandler creates a new tool handler.
func NewToolHandler(client *tastytrade.Client) *ToolHandler {
	return &ToolHandler{client: client}
}

// ListTools returns all available tools.
func (h *ToolHandler) ListTools() []Tool {
	return []Tool{
		{
			Name:        "ping",
			Description: "Simple ping tool to verify server connectivity",
			InputSchema: json.RawMessage(`{"type":"object","properties":{},"required":[]}`),
		},
		{
			Name:        "login",
			Description: "Authenticate with TastyTrade using OAuth credentials",
			InputSchema: json.RawMessage(`{
				"type": "object",
				"properties": {
					"client_secret": {
						"type": "string",
						"description": "TastyTrade OAuth client secret"
					},
					"refresh_token": {
						"type": "string",
						"description": "TastyTrade OAuth refresh token"
					},
					"remember_me": {
						"type": "boolean",
						"description": "Store credentials for automatic session restore",
						"default": false
					}
				},
				"required": ["client_secret", "refresh_token"]
			}`),
		},
		{
			Name:        "logout",
			Description: "Log out from TastyTrade and clear stored credentials",
			InputSchema: json.RawMessage(`{
				"type": "object",
				"properties": {
					"clear_credentials": {
						"type": "boolean",
						"description": "Whether to remove stored credentials",
						"default": true
					}
				},
				"required": []
			}`),
		},
		{
			Name:        "get_auth_status",
			Description: "Check current TastyTrade authentication status",
			InputSchema: json.RawMessage(`{"type":"object","properties":{},"required":[]}`),
		},
		{
			Name:        "get_quote",
			Description: "Get quote data for a symbol including price, volume, IV, beta, market cap, and earnings",
			InputSchema: json.RawMessage(`{
				"type": "object",
				"properties": {
					"symbol": {
						"type": "string",
						"description": "Ticker symbol (e.g., AAPL, SPY)"
					}
				},
				"required": ["symbol"]
			}`),
		},
	}
}

// CallTool handles a tool call.
func (h *ToolHandler) CallTool(name string, arguments map[string]interface{}) ToolResult {
	switch name {
	case "ping":
		return TextResult("pong")

	case "login":
		clientSecret, _ := arguments["client_secret"].(string)
		refreshToken, _ := arguments["refresh_token"].(string)
		rememberMe, _ := arguments["remember_me"].(bool)

		if clientSecret == "" || refreshToken == "" {
			return ErrorResult("client_secret and refresh_token are required")
		}

		err := h.client.Login(clientSecret, refreshToken, rememberMe)
		if err != nil {
			return JSONResult(map[string]interface{}{
				"success": false,
				"message": "Login failed. Check OAuth credentials.",
			})
		}

		return JSONResult(map[string]interface{}{
			"success": true,
			"message": "Successfully authenticated with TastyTrade",
		})

	case "logout":
		clearCredentials := true
		if v, ok := arguments["clear_credentials"].(bool); ok {
			clearCredentials = v
		}

		h.client.Logout(clearCredentials)
		return JSONResult(map[string]interface{}{
			"success": true,
			"message": "Logged out successfully",
		})

	case "get_auth_status":
		return JSONResult(h.client.GetAuthStatus())

	case "get_quote":
		symbol, _ := arguments["symbol"].(string)
		if symbol == "" {
			return ErrorResult("symbol is required")
		}

		if !h.client.IsAuthenticated() {
			return ErrorResult("Not authenticated. Please login first.")
		}

		quote, err := h.client.GetQuote(symbol)
		if err != nil {
			return ErrorResult("Failed to get quote for " + symbol)
		}

		return JSONResult(quote)

	default:
		return ErrorResult("Unknown tool: " + name)
	}
}
