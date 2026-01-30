// Package app provides application lifecycle management.
package app

import (
	"context"
	"crypto/tls"
	"fmt"
	"log"
	"net/http"
	"os"
	"os/signal"
	"syscall"

	"fyne.io/fyne/v2"
	fyneapp "fyne.io/fyne/v2/app"

	"github.com/ttai/ttai/internal/cache"
	"github.com/ttai/ttai/internal/config"
	"github.com/ttai/ttai/internal/credentials"
	"github.com/ttai/ttai/internal/mcp"
	"github.com/ttai/ttai/internal/ssl"
	"github.com/ttai/ttai/internal/state"
	"github.com/ttai/ttai/internal/tastytrade"
	"github.com/ttai/ttai/resources"
	"github.com/ttai/ttai/ui"
)

// Application represents the TTAI application.
type Application struct {
	cfg         *config.Config
	fyneApp     fyne.App
	mainWindow  *ui.MainWindow
	trayManager *ui.TrayManager
	appState    *state.AppState
	prefs       *state.Preferences
	client      *tastytrade.Client
	mcpServer   *mcp.Server
	httpServer  *http.Server

	ctx    context.Context
	cancel context.CancelFunc
}

// NewApplication creates a new TTAI application.
func NewApplication(cfg *config.Config) *Application {
	ctx, cancel := context.WithCancel(context.Background())

	return &Application{
		cfg:    cfg,
		ctx:    ctx,
		cancel: cancel,
	}
}

// Run starts the application.
func (a *Application) Run(headless bool) int {
	// Ensure data directory exists
	if err := a.cfg.EnsureDataDir(); err != nil {
		log.Printf("Failed to create data directory: %v", err)
		return 1
	}

	// Initialize services
	credManager := credentials.NewManager()
	cacheService := cache.New()
	a.client = tastytrade.NewClient(credManager, cacheService)
	a.appState = state.New()

	// Create MCP server
	toolHandler := mcp.NewToolHandler(a.client)
	a.mcpServer = mcp.NewServer(toolHandler)

	// Try to restore session
	if err := a.client.RestoreSession(); err == nil {
		a.appState.SetAuthenticated(true)
		log.Println("Session restored from stored credentials")
	}

	if headless {
		return a.runHeadless()
	}

	return a.runGUI()
}

func (a *Application) runHeadless() int {
	log.Println("Running in headless mode")

	// Setup signal handling
	sigCh := make(chan os.Signal, 1)
	signal.Notify(sigCh, syscall.SIGINT, syscall.SIGTERM)

	go func() {
		<-sigCh
		log.Println("Received shutdown signal")
		a.shutdown()
	}()

	if a.cfg.Transport == "stdio" {
		return a.runStdio()
	}

	return a.runHTTPServer()
}

func (a *Application) runStdio() int {
	if err := a.mcpServer.RunStdio(); err != nil {
		log.Printf("Stdio server error: %v", err)
		return 1
	}
	return 0
}

func (a *Application) runHTTPServer() int {
	// Setup HTTP server
	mux := http.NewServeMux()

	// MCP endpoint
	mux.Handle("/mcp", a.mcpServer.HTTPHandler())
	mux.Handle("/mcp/", a.mcpServer.HTTPHandler())

	// REST API endpoints
	restHandler := mcp.NewRESTHandlerV2(a.client)
	mux.HandleFunc("/api/health", restHandler.HealthHandler)
	mux.HandleFunc("/api/auth-status", restHandler.AuthStatusHandler)
	mux.HandleFunc("/api/login", restHandler.LoginHandler)
	mux.HandleFunc("/api/logout", restHandler.LogoutHandler)

	// Determine host and port
	host := a.cfg.Host
	port := a.cfg.Port
	var tlsConfig *tls.Config

	// Try SSL if enabled
	if a.cfg.SSLEnabled() {
		certManager := ssl.NewManager(a.cfg.SSLCertDir(), a.cfg.SSLCertAPI())
		certPath, keyPath, err := certManager.EnsureCertificate()
		if err == nil {
			cert, err := tls.LoadX509KeyPair(certPath, keyPath)
			if err == nil {
				tlsConfig = &tls.Config{
					Certificates: []tls.Certificate{cert},
				}
				host = "127.0.0.1"
				port = a.cfg.SSLPort
				log.Printf("Starting HTTPS server on %s:%d", host, port)
			} else {
				log.Printf("Failed to load SSL certificate: %v, falling back to HTTP", err)
			}
		} else {
			log.Printf("Failed to ensure SSL certificate: %v, falling back to HTTP", err)
		}
	}

	a.httpServer = &http.Server{
		Addr:      fmt.Sprintf("%s:%d", host, port),
		Handler:   mux,
		TLSConfig: tlsConfig,
	}

	var err error
	if tlsConfig != nil {
		log.Printf("MCP server listening on https://%s:%d/mcp", a.cfg.SSLLocalDomain(), port)
		err = a.httpServer.ListenAndServeTLS("", "")
	} else {
		log.Printf("MCP server listening on http://%s:%d/mcp", host, port)
		err = a.httpServer.ListenAndServe()
	}

	if err != nil && err != http.ErrServerClosed {
		log.Printf("HTTP server error: %v", err)
		return 1
	}

	return 0
}

func (a *Application) runGUI() int {
	// Create Fyne app
	a.fyneApp = fyneapp.NewWithID("dev.tt-ai.ttai")

	// Load icon
	icon := loadIcon()

	// Set app icon
	if icon != nil {
		a.fyneApp.SetIcon(icon)
	}

	// Create preferences manager
	a.prefs = state.NewPreferences(a.fyneApp)

	// Create main window
	a.mainWindow = ui.NewMainWindow(a.fyneApp, a.cfg, a.client, a.appState, a.prefs, icon)

	// Create system tray
	a.trayManager = ui.NewTrayManager(
		a.fyneApp,
		a.cfg,
		func() { a.mainWindow.Show() },
		func() { a.quit() },
	)
	a.trayManager.SetWindow(a.mainWindow.Window())
	a.trayManager.Setup()

	// Start HTTP server in background
	go a.runHTTPServer()

	// Show window if configured or first run
	if a.prefs.ShowWindowOnLaunch() || a.prefs.IsFirstRun() {
		a.mainWindow.Show()
		if a.prefs.IsFirstRun() {
			a.prefs.SetFirstRunComplete()
		}
	}

	// Run the Fyne event loop
	a.fyneApp.Run()

	return 0
}

func (a *Application) quit() {
	a.shutdown()
	if a.fyneApp != nil {
		a.fyneApp.Quit()
	}
}

func (a *Application) shutdown() {
	a.cancel()

	if a.httpServer != nil {
		ctx, cancel := context.WithTimeout(context.Background(), 5)
		defer cancel()
		a.httpServer.Shutdown(ctx)
	}

	// Logout and cleanup
	if a.client != nil && a.client.IsAuthenticated() {
		a.client.Logout(false) // Don't clear credentials on shutdown
	}

	log.Println("Application shutdown complete")
}

func loadIcon() fyne.Resource {
	return resources.Icon()
}
