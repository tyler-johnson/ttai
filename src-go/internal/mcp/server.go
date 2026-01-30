package mcp

import (
	"bufio"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/http"
	"os"
	"sync"
)

// JSONRPCRequest represents a JSON-RPC 2.0 request.
type JSONRPCRequest struct {
	JSONRPC string          `json:"jsonrpc"`
	ID      interface{}     `json:"id,omitempty"`
	Method  string          `json:"method"`
	Params  json.RawMessage `json:"params,omitempty"`
}

// JSONRPCResponse represents a JSON-RPC 2.0 response.
type JSONRPCResponse struct {
	JSONRPC string        `json:"jsonrpc"`
	ID      interface{}   `json:"id,omitempty"`
	Result  interface{}   `json:"result,omitempty"`
	Error   *JSONRPCError `json:"error,omitempty"`
}

// JSONRPCError represents a JSON-RPC error.
type JSONRPCError struct {
	Code    int         `json:"code"`
	Message string      `json:"message"`
	Data    interface{} `json:"data,omitempty"`
}

// Server is an MCP server.
type Server struct {
	toolHandler *ToolHandler
	serverInfo  ServerInfo
}

// ServerInfo contains server metadata.
type ServerInfo struct {
	Name    string `json:"name"`
	Version string `json:"version"`
}

// NewServer creates a new MCP server.
func NewServer(handler *ToolHandler) *Server {
	return &Server{
		toolHandler: handler,
		serverInfo: ServerInfo{
			Name:    "ttai-server",
			Version: "1.0.0",
		},
	}
}

// HandleRequest processes an MCP JSON-RPC request.
func (s *Server) HandleRequest(req *JSONRPCRequest) *JSONRPCResponse {
	switch req.Method {
	case "initialize":
		return s.handleInitialize(req)
	case "tools/list":
		return s.handleToolsList(req)
	case "tools/call":
		return s.handleToolsCall(req)
	case "notifications/initialized":
		// Client notification, no response needed
		return nil
	default:
		return &JSONRPCResponse{
			JSONRPC: "2.0",
			ID:      req.ID,
			Error: &JSONRPCError{
				Code:    -32601,
				Message: "Method not found: " + req.Method,
			},
		}
	}
}

func (s *Server) handleInitialize(req *JSONRPCRequest) *JSONRPCResponse {
	return &JSONRPCResponse{
		JSONRPC: "2.0",
		ID:      req.ID,
		Result: map[string]interface{}{
			"protocolVersion": "2024-11-05",
			"serverInfo":      s.serverInfo,
			"capabilities": map[string]interface{}{
				"tools": map[string]interface{}{},
			},
		},
	}
}

func (s *Server) handleToolsList(req *JSONRPCRequest) *JSONRPCResponse {
	tools := s.toolHandler.ListTools()
	return &JSONRPCResponse{
		JSONRPC: "2.0",
		ID:      req.ID,
		Result: map[string]interface{}{
			"tools": tools,
		},
	}
}

func (s *Server) handleToolsCall(req *JSONRPCRequest) *JSONRPCResponse {
	var params struct {
		Name      string                 `json:"name"`
		Arguments map[string]interface{} `json:"arguments"`
	}

	if err := json.Unmarshal(req.Params, &params); err != nil {
		return &JSONRPCResponse{
			JSONRPC: "2.0",
			ID:      req.ID,
			Error: &JSONRPCError{
				Code:    -32602,
				Message: "Invalid params: " + err.Error(),
			},
		}
	}

	result := s.toolHandler.CallTool(params.Name, params.Arguments)
	return &JSONRPCResponse{
		JSONRPC: "2.0",
		ID:      req.ID,
		Result:  result,
	}
}

// RunStdio runs the server in stdio mode.
func (s *Server) RunStdio() error {
	log.Println("Starting MCP server in stdio mode")

	reader := bufio.NewReader(os.Stdin)
	encoder := json.NewEncoder(os.Stdout)

	for {
		line, err := reader.ReadBytes('\n')
		if err != nil {
			if err == io.EOF {
				return nil
			}
			return err
		}

		var req JSONRPCRequest
		if err := json.Unmarshal(line, &req); err != nil {
			log.Printf("Failed to parse request: %v", err)
			continue
		}

		resp := s.HandleRequest(&req)
		if resp != nil {
			if err := encoder.Encode(resp); err != nil {
				log.Printf("Failed to write response: %v", err)
			}
		}
	}
}

// HTTPHandler returns an HTTP handler for the MCP server.
func (s *Server) HTTPHandler() http.Handler {
	return &httpHandler{server: s}
}

type httpHandler struct {
	server   *Server
	sessions sync.Map // session_id -> session state
}

func (h *httpHandler) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	// Handle CORS
	w.Header().Set("Access-Control-Allow-Origin", "*")
	w.Header().Set("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
	w.Header().Set("Access-Control-Allow-Headers", "Content-Type")

	if r.Method == "OPTIONS" {
		w.WriteHeader(http.StatusOK)
		return
	}

	if r.Method == "GET" {
		// SSE endpoint for server-sent events
		h.handleSSE(w, r)
		return
	}

	if r.Method == "POST" {
		// JSON-RPC endpoint
		h.handleJSONRPC(w, r)
		return
	}

	http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
}

func (h *httpHandler) handleJSONRPC(w http.ResponseWriter, r *http.Request) {
	var req JSONRPCRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		http.Error(w, "Invalid JSON", http.StatusBadRequest)
		return
	}

	resp := h.server.HandleRequest(&req)
	if resp == nil {
		w.WriteHeader(http.StatusNoContent)
		return
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(resp)
}

func (h *httpHandler) handleSSE(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "text/event-stream")
	w.Header().Set("Cache-Control", "no-cache")
	w.Header().Set("Connection", "keep-alive")

	flusher, ok := w.(http.Flusher)
	if !ok {
		http.Error(w, "SSE not supported", http.StatusInternalServerError)
		return
	}

	// Send initial endpoint event
	sessionID := fmt.Sprintf("session-%d", r.Context().Value("session_id"))
	fmt.Fprintf(w, "event: endpoint\ndata: %s\n\n", r.URL.Path)
	flusher.Flush()

	// Keep connection alive
	<-r.Context().Done()
	log.Printf("SSE session %s closed", sessionID)
}

// TastyTradeClient is the interface for the TastyTrade client needed by REST handlers.
type TastyTradeClient interface {
	GetAuthStatus() interface{}
	Login(clientSecret, refreshToken string, rememberMe bool) error
	Logout(clearCredentials bool) error
}

// tastyTradeClientAdapter adapts the tastytrade.Client to the TastyTradeClient interface.
type tastyTradeClientAdapter struct {
	client interface {
		GetAuthStatus() interface{}
		Login(clientSecret, refreshToken string, rememberMe bool) error
		Logout(clearCredentials bool) error
	}
}

// RESTHandler provides REST API endpoints for the GUI.
type RESTHandler struct {
	client interface {
		GetAuthStatus() interface{}
		Login(clientSecret, refreshToken string, rememberMe bool) error
		Logout(clearCredentials bool) error
	}
}

// NewRESTHandler creates a new REST handler.
func NewRESTHandler(client interface {
	GetAuthStatus() interface{}
	Login(clientSecret, refreshToken string, rememberMe bool) error
	Logout(clearCredentials bool) error
}) *RESTHandler {
	return &RESTHandler{client: client}
}

// HealthHandler handles GET /api/health.
func (h *RESTHandler) HealthHandler(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]string{"status": "ok"})
}

// AuthStatusHandler handles GET /api/auth-status.
func (h *RESTHandler) AuthStatusHandler(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(h.client.GetAuthStatus())
}

// LoginHandler handles POST /api/login.
func (h *RESTHandler) LoginHandler(w http.ResponseWriter, r *http.Request) {
	var body struct {
		ClientSecret string `json:"client_secret"`
		RefreshToken string `json:"refresh_token"`
		RememberMe   bool   `json:"remember_me"`
	}

	if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
		w.WriteHeader(http.StatusBadRequest)
		json.NewEncoder(w).Encode(map[string]interface{}{
			"success": false,
			"error":   "Invalid request body",
		})
		return
	}

	if body.ClientSecret == "" || body.RefreshToken == "" {
		w.WriteHeader(http.StatusBadRequest)
		json.NewEncoder(w).Encode(map[string]interface{}{
			"success": false,
			"error":   "client_secret and refresh_token are required",
		})
		return
	}

	err := h.client.Login(body.ClientSecret, body.RefreshToken, body.RememberMe)
	w.Header().Set("Content-Type", "application/json")

	if err != nil {
		json.NewEncoder(w).Encode(map[string]interface{}{
			"success": false,
			"error":   "Login failed",
		})
		return
	}

	json.NewEncoder(w).Encode(map[string]interface{}{
		"success": true,
	})
}

// LogoutHandler handles POST /api/logout.
func (h *RESTHandler) LogoutHandler(w http.ResponseWriter, r *http.Request) {
	var body struct {
		ClearCredentials bool `json:"clear_credentials"`
	}

	json.NewDecoder(r.Body).Decode(&body)
	h.client.Logout(body.ClearCredentials)

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]interface{}{
		"success": true,
	})
}
