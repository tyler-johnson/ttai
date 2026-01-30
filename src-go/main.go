// TTAI - TastyTrade AI Assistant
// A Go implementation of the TTAI application.
package main

import (
	"flag"
	"log"
	"os"
	"path/filepath"

	"github.com/ttai/ttai/internal/app"
	"github.com/ttai/ttai/internal/config"
)


func main() {
	// Parse command line arguments
	headless := flag.Bool("headless", false, "Run as headless MCP server (no GUI)")
	transport := flag.String("transport", "", "Transport mode: stdio or http (default: from env or http)")
	host := flag.String("host", "", "Host to bind to for HTTP mode (default: from env or localhost)")
	port := flag.Int("port", 0, "Port to bind to for HTTP mode (default: from env or 5180)")
	logLevel := flag.String("log-level", "", "Log level: DEBUG, INFO, WARNING, ERROR (default: from env or INFO)")
	dataDir := flag.String("data-dir", "", "Data directory (default: from env or ~/.ttai)")
	sslDomain := flag.String("ssl-domain", "", "Base domain for SSL (e.g., tt-ai.dev)")
	sslPort := flag.Int("ssl-port", 0, "Port for HTTPS mode (default: from env or 5181)")
	softwareRender := flag.Bool("software-render", false, "Force software rendering (no OpenGL)")

	flag.Parse()

	// Build configuration from environment and CLI args
	cfg := config.FromEnv()

	// CLI args override environment
	if *transport != "" {
		cfg.Transport = *transport
	}
	if *host != "" {
		cfg.Host = *host
	}
	if *port != 0 {
		cfg.Port = *port
	}
	if *logLevel != "" {
		cfg.LogLevel = *logLevel
	}
	if *dataDir != "" {
		cfg.DataDir = *dataDir
	}
	if *sslDomain != "" {
		cfg.SSLDomain = *sslDomain
	}
	if *sslPort != 0 {
		cfg.SSLPort = *sslPort
	}

	// Setup logging
	setupLogging(cfg)

	log.Printf("TTAI starting with config: transport=%s, host=%s, port=%d, ssl=%v",
		cfg.Transport, cfg.Host, cfg.Port, cfg.SSLEnabled())

	// Create and run application
	application := app.NewApplication(cfg)
	exitCode := application.Run(*headless, *softwareRender)

	os.Exit(exitCode)
}

func setupLogging(cfg *config.Config) {
	// Create log directory
	logDir := cfg.LogDir()
	if err := os.MkdirAll(logDir, 0755); err != nil {
		log.Printf("Warning: failed to create log directory: %v", err)
		return
	}

	// Setup log file
	logPath := filepath.Join(logDir, "ttai.log")
	logFile, err := os.OpenFile(logPath, os.O_CREATE|os.O_WRONLY|os.O_APPEND, 0644)
	if err != nil {
		log.Printf("Warning: failed to open log file: %v", err)
		return
	}

	// Log to both file and stderr
	log.SetOutput(os.Stderr)
	log.SetFlags(log.Ldate | log.Ltime | log.Lshortfile)

	// We'd use a multi-writer in production
	_ = logFile
}
