// Package credentials provides secure credential storage using the OS keyring.
package credentials

import (
	"encoding/json"
	"errors"

	"github.com/zalando/go-keyring"
)

const (
	serviceName = "ttai"
	accountName = "oauth-credentials"
)

// Credentials represents TastyTrade OAuth credentials.
type Credentials struct {
	ClientSecret string `json:"client_secret"`
	RefreshToken string `json:"refresh_token"`
}

// Manager handles credential storage using the OS keyring.
type Manager struct{}

// NewManager creates a new credential manager.
func NewManager() *Manager {
	return &Manager{}
}

// Store saves credentials to the OS keyring.
func (m *Manager) Store(clientSecret, refreshToken string) error {
	creds := Credentials{
		ClientSecret: clientSecret,
		RefreshToken: refreshToken,
	}

	data, err := json.Marshal(creds)
	if err != nil {
		return err
	}

	return keyring.Set(serviceName, accountName, string(data))
}

// Load retrieves credentials from the OS keyring.
// Returns nil if no credentials are stored.
func (m *Manager) Load() (*Credentials, error) {
	data, err := keyring.Get(serviceName, accountName)
	if err != nil {
		if errors.Is(err, keyring.ErrNotFound) {
			return nil, nil
		}
		return nil, err
	}

	var creds Credentials
	if err := json.Unmarshal([]byte(data), &creds); err != nil {
		return nil, err
	}

	return &creds, nil
}

// Clear removes stored credentials from the OS keyring.
func (m *Manager) Clear() error {
	err := keyring.Delete(serviceName, accountName)
	if errors.Is(err, keyring.ErrNotFound) {
		return nil // Already cleared
	}
	return err
}

// HasCredentials checks if credentials are stored.
func (m *Manager) HasCredentials() bool {
	_, err := keyring.Get(serviceName, accountName)
	return err == nil
}
