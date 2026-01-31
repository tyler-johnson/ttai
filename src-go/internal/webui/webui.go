// Package webui provides a web-based settings UI for the TTAI application.
package webui

import (
	"embed"
	"encoding/json"
	"log"
	"net/http"
	"net/url"
	"os/exec"
	"runtime"
	"strconv"
	"strings"

	"github.com/ttai/ttai/internal/config"
	"github.com/ttai/ttai/internal/state"
	"github.com/ttai/ttai/internal/tastytrade"
)

//go:embed dist/*
var assets embed.FS

// Version is the application version.
const Version = "1.0.0"

// Handler provides HTTP handlers for the web UI.
type Handler struct {
	cfg    *config.Config
	client *tastytrade.Client
	prefs  *PreferencesManager
}

// NewHandler creates a new web UI handler.
func NewHandler(cfg *config.Config, client *tastytrade.Client, prefs *PreferencesManager) *Handler {
	return &Handler{
		cfg:    cfg,
		client: client,
		prefs:  prefs,
	}
}

// RegisterRoutes registers all web UI routes on the given mux.
func (h *Handler) RegisterRoutes(mux *http.ServeMux) {
	// API routes (must be registered before static file handler)
	mux.HandleFunc("/api/server-info", h.ServerInfoHandler)
	mux.HandleFunc("/api/settings", h.SettingsHandler)
	mux.HandleFunc("/api/tastytrade", h.TastyTradeHandler)

	// Static file handler for SPA
	mux.HandleFunc("/", h.StaticHandler)
}

// StaticHandler serves static files from the embedded dist/ directory.
// For SPA routing, it falls back to index.html for unknown paths.
func (h *Handler) StaticHandler(w http.ResponseWriter, r *http.Request) {
	path := r.URL.Path
	if path == "/" {
		path = "/index.html"
	}

	// Try to serve the requested file
	filePath := "dist" + path
	data, err := assets.ReadFile(filePath)
	if err != nil {
		// For SPA routing, serve index.html for unknown paths
		data, err = assets.ReadFile("dist/index.html")
		if err != nil {
			http.Error(w, "Failed to load UI", http.StatusInternalServerError)
			return
		}
		w.Header().Set("Content-Type", "text/html; charset=utf-8")
		w.Write(data)
		return
	}

	// Set content type based on file extension
	contentType := "application/octet-stream"
	switch {
	case strings.HasSuffix(path, ".html"):
		contentType = "text/html; charset=utf-8"
	case strings.HasSuffix(path, ".css"):
		contentType = "text/css; charset=utf-8"
	case strings.HasSuffix(path, ".js"):
		contentType = "application/javascript; charset=utf-8"
	case strings.HasSuffix(path, ".json"):
		contentType = "application/json; charset=utf-8"
	case strings.HasSuffix(path, ".png"):
		contentType = "image/png"
	case strings.HasSuffix(path, ".svg"):
		contentType = "image/svg+xml"
	case strings.HasSuffix(path, ".ico"):
		contentType = "image/x-icon"
	case strings.HasSuffix(path, ".woff"):
		contentType = "font/woff"
	case strings.HasSuffix(path, ".woff2"):
		contentType = "font/woff2"
	}

	w.Header().Set("Content-Type", contentType)
	w.Write(data)
}

// ServerInfoHandler handles GET /api/server-info.
func (h *Handler) ServerInfoHandler(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
		return
	}

	info := map[string]interface{}{
		"version":     Version,
		"http_url":    h.cfg.HTTPURL(),
		"ssl_enabled": h.cfg.SSLEnabled(),
	}

	if h.cfg.SSLEnabled() {
		info["https_url"] = h.cfg.HTTPSURL()
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(info)
}

// SettingsHandler handles GET/PATCH /api/settings.
func (h *Handler) SettingsHandler(w http.ResponseWriter, r *http.Request) {
	switch r.Method {
	case http.MethodGet:
		h.getSettings(w, r)
	case http.MethodPatch:
		h.updateSettings(w, r)
	default:
		http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
	}
}

func (h *Handler) getSettings(w http.ResponseWriter, r *http.Request) {
	prefs := h.prefs.GetAll()
	response := map[string]interface{}{
		"launch_at_startup":       state.IsLaunchAtStartupEnabled(),
		"open_settings_on_launch": prefs.ShowWindowOnLaunch,
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(response)
}

func (h *Handler) updateSettings(w http.ResponseWriter, r *http.Request) {
	var updates map[string]interface{}
	if err := json.NewDecoder(r.Body).Decode(&updates); err != nil {
		http.Error(w, "Invalid request body", http.StatusBadRequest)
		return
	}

	// Handle launch_at_startup separately (system-level setting)
	if v, ok := updates["launch_at_startup"].(bool); ok {
		state.SetLaunchAtStartup(v)
		delete(updates, "launch_at_startup")
	}

	// Handle other preferences
	h.prefs.Update(updates)

	// Return updated settings
	h.getSettings(w, r)
}

// TastyTradeHandler handles GET/POST/DELETE /api/tastytrade.
func (h *Handler) TastyTradeHandler(w http.ResponseWriter, r *http.Request) {
	switch r.Method {
	case http.MethodGet:
		h.getTastyTradeStatus(w, r)
	case http.MethodPost:
		h.loginTastyTrade(w, r)
	case http.MethodDelete:
		h.logoutTastyTrade(w, r)
	default:
		http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
	}
}

func (h *Handler) getTastyTradeStatus(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]interface{}{
		"authenticated": h.client.IsAuthenticated(),
	})
}

func (h *Handler) loginTastyTrade(w http.ResponseWriter, r *http.Request) {
	var body struct {
		ClientSecret string `json:"client_secret"`
		RefreshToken string `json:"refresh_token"`
	}

	if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
		w.WriteHeader(http.StatusBadRequest)
		json.NewEncoder(w).Encode(map[string]interface{}{
			"authenticated": false,
			"error":         "Invalid request body",
		})
		return
	}

	if body.ClientSecret == "" || body.RefreshToken == "" {
		w.WriteHeader(http.StatusBadRequest)
		json.NewEncoder(w).Encode(map[string]interface{}{
			"authenticated": false,
			"error":         "client_secret and refresh_token are required",
		})
		return
	}

	err := h.client.Login(body.ClientSecret, body.RefreshToken, true)
	w.Header().Set("Content-Type", "application/json")

	if err != nil {
		json.NewEncoder(w).Encode(map[string]interface{}{
			"authenticated": false,
			"error":         "Login failed",
		})
		return
	}

	json.NewEncoder(w).Encode(map[string]interface{}{
		"authenticated": true,
	})
}

func (h *Handler) logoutTastyTrade(w http.ResponseWriter, r *http.Request) {
	h.client.Logout(true)

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]interface{}{
		"authenticated": false,
	})
}

// OpenBrowser opens the default browser to the given URL.
func OpenBrowser(urlStr string) error {
	var cmd *exec.Cmd

	switch runtime.GOOS {
	case "darwin":
		cmd = exec.Command("open", urlStr)
	case "windows":
		cmd = exec.Command("rundll32", "url.dll,FileProtocolHandler", urlStr)
	default: // linux, freebsd, etc.
		cmd = exec.Command("xdg-open", urlStr)
	}

	return cmd.Start()
}

// OpenSettingsInBrowser opens the settings UI in the default browser.
func OpenSettingsInBrowser(cfg *config.Config) {
	var urlStr string
	if cfg.SSLEnabled() {
		// For HTTPS, use the local domain
		urlStr = "https://" + cfg.SSLLocalDomain() + ":" + strconv.Itoa(cfg.SSLPort) + "/"
	} else {
		urlStr = "http://" + cfg.Host + ":" + strconv.Itoa(cfg.Port) + "/"
	}

	log.Printf("Opening settings in browser: %s", urlStr)
	if err := OpenBrowser(urlStr); err != nil {
		log.Printf("Failed to open browser: %v", err)
	}
}

// CopyToClipboard copies text to the system clipboard.
func CopyToClipboard(text string) error {
	var cmd *exec.Cmd

	switch runtime.GOOS {
	case "darwin":
		cmd = exec.Command("pbcopy")
	case "windows":
		cmd = exec.Command("cmd", "/c", "echo|set/p="+text+"|clip")
		return cmd.Run()
	default: // linux
		// Try xclip first, then xsel
		cmd = exec.Command("xclip", "-selection", "clipboard")
	}

	pipe, err := cmd.StdinPipe()
	if err != nil {
		return err
	}

	if err := cmd.Start(); err != nil {
		return err
	}

	pipe.Write([]byte(text))
	pipe.Close()

	return cmd.Wait()
}

// GetMCPURL returns the appropriate MCP URL based on SSL configuration.
func GetMCPURL(cfg *config.Config) string {
	if cfg.SSLEnabled() {
		return cfg.HTTPSURL()
	}
	return cfg.HTTPURL()
}

// ParseURL parses a URL string.
func ParseURL(urlStr string) (*url.URL, error) {
	return url.Parse(urlStr)
}
