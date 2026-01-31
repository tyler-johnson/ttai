package mcp

import (
	"encoding/json"
	"net/http"

	"github.com/tyler-johnson/ttai/internal/tastytrade"
)

// RESTHandlerV2 provides REST API endpoints for the GUI using the concrete TastyTrade client.
type RESTHandlerV2 struct {
	client *tastytrade.Client
}

// NewRESTHandlerV2 creates a new REST handler for the TastyTrade client.
func NewRESTHandlerV2(client *tastytrade.Client) *RESTHandlerV2 {
	return &RESTHandlerV2{client: client}
}

// HealthHandler handles GET /api/health.
func (h *RESTHandlerV2) HealthHandler(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]string{"status": "ok"})
}

// AuthStatusHandler handles GET /api/auth-status.
func (h *RESTHandlerV2) AuthStatusHandler(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(h.client.GetAuthStatus())
}

// LoginHandler handles POST /api/login.
func (h *RESTHandlerV2) LoginHandler(w http.ResponseWriter, r *http.Request) {
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
func (h *RESTHandlerV2) LogoutHandler(w http.ResponseWriter, r *http.Request) {
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
