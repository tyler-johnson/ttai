// Package config provides configuration management for the TTAI server.
package config

import (
	"os"
	"path/filepath"
	"strconv"
)

// Config holds the server configuration.
type Config struct {
	Transport          string // "http" or "stdio"
	Host               string // Server host (default: "localhost")
	Port               int    // HTTP port (default: 5180)
	LogLevel           string // Log level (default: "info")
	DataDir            string // Data directory (default: ~/.ttai)
	SSLDomain          string // Base domain for SSL (default: "tt-ai.dev")
	SSLPort            int    // HTTPS port (default: 5181)
	SSLCertAPIOverride string // Override cert API URL (for local dev)
}

// DBPath returns the path to the SQLite database.
func (c *Config) DBPath() string {
	return filepath.Join(c.DataDir, "ttai.db")
}

// LogDir returns the path to the log directory.
func (c *Config) LogDir() string {
	return filepath.Join(c.DataDir, "logs")
}

// SSLCertDir returns the path to the SSL certificate directory.
func (c *Config) SSLCertDir() string {
	return filepath.Join(c.DataDir, "ssl")
}

// SSLCertAPI returns the URL for the certificate API.
func (c *Config) SSLCertAPI() string {
	if c.SSLCertAPIOverride != "" {
		return c.SSLCertAPIOverride
	}
	if c.SSLDomain != "" {
		return "https://api." + c.SSLDomain + "/cert"
	}
	return ""
}

// SSLLocalDomain returns the local domain for HTTPS server.
func (c *Config) SSLLocalDomain() string {
	if c.SSLDomain != "" {
		return "local." + c.SSLDomain
	}
	return ""
}

// SSLEnabled returns true if SSL is configured.
func (c *Config) SSLEnabled() bool {
	return c.SSLDomain != ""
}

// HTTPURL returns the HTTP MCP server URL.
func (c *Config) HTTPURL() string {
	return "http://" + c.Host + ":" + strconv.Itoa(c.Port) + "/mcp"
}

// HTTPSURL returns the HTTPS MCP server URL (if SSL is enabled).
func (c *Config) HTTPSURL() string {
	if !c.SSLEnabled() {
		return ""
	}
	return "https://" + c.SSLLocalDomain() + ":" + strconv.Itoa(c.SSLPort) + "/mcp"
}

// DefaultConfig returns the default configuration.
func DefaultConfig() *Config {
	homeDir, _ := os.UserHomeDir()
	return &Config{
		Transport: "http",
		Host:      "localhost",
		Port:      5180,
		LogLevel:  "info",
		DataDir:   filepath.Join(homeDir, ".ttai"),
		SSLDomain: "tt-ai.dev",
		SSLPort:   5181,
	}
}

// FromEnv creates configuration from environment variables.
func FromEnv() *Config {
	cfg := DefaultConfig()

	if v := os.Getenv("TTAI_TRANSPORT"); v != "" {
		cfg.Transport = v
	}
	if v := os.Getenv("TTAI_HOST"); v != "" {
		cfg.Host = v
	}
	if v := os.Getenv("TTAI_PORT"); v != "" {
		if port, err := strconv.Atoi(v); err == nil {
			cfg.Port = port
		}
	}
	if v := os.Getenv("TTAI_LOG_LEVEL"); v != "" {
		cfg.LogLevel = v
	}
	if v := os.Getenv("TTAI_DATA_DIR"); v != "" {
		cfg.DataDir = v
	}
	if v, ok := os.LookupEnv("TTAI_SSL_DOMAIN"); ok {
		cfg.SSLDomain = v // Can be empty to disable SSL
	}
	if v := os.Getenv("TTAI_SSL_PORT"); v != "" {
		if port, err := strconv.Atoi(v); err == nil {
			cfg.SSLPort = port
		}
	}
	if v := os.Getenv("TTAI_SSL_CERT_API"); v != "" {
		cfg.SSLCertAPIOverride = v
	}

	return cfg
}

// EnsureDataDir ensures the data directory exists.
func (c *Config) EnsureDataDir() error {
	return os.MkdirAll(c.DataDir, 0755)
}
