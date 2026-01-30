// Package ssl provides SSL certificate management for HTTPS support.
package ssl

import (
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"log"
	"net/http"
	"os"
	"path/filepath"
	"time"
)

const refreshThresholdDays = 7

var ErrCertificateFetch = errors.New("certificate fetch failed")

// CertificateBundle represents an SSL certificate bundle.
type CertificateBundle struct {
	Cert      string    `json:"cert"`
	Key       string    `json:"key"`
	Domain    string    `json:"domain"`
	ExpiresAt time.Time `json:"expires_at"`
	IssuedAt  time.Time `json:"issued_at"`
}

// IsExpired returns true if the certificate is expired.
func (b *CertificateBundle) IsExpired() bool {
	return time.Now().After(b.ExpiresAt)
}

// DaysUntilExpiry returns the number of days until the certificate expires.
func (b *CertificateBundle) DaysUntilExpiry() float64 {
	return time.Until(b.ExpiresAt).Hours() / 24
}

// CertificateMeta holds certificate metadata (without cert/key content).
type CertificateMeta struct {
	Domain    string    `json:"domain"`
	ExpiresAt time.Time `json:"expires_at"`
	IssuedAt  time.Time `json:"issued_at"`
}

// Manager manages SSL certificates for the HTTPS server.
type Manager struct {
	certDir    string
	certAPIURL string
	httpClient *http.Client
}

// NewManager creates a new certificate manager.
func NewManager(certDir, certAPIURL string) *Manager {
	return &Manager{
		certDir:    certDir,
		certAPIURL: certAPIURL,
		httpClient: &http.Client{Timeout: 30 * time.Second},
	}
}

func (m *Manager) certPath() string {
	return filepath.Join(m.certDir, "cert.pem")
}

func (m *Manager) keyPath() string {
	return filepath.Join(m.certDir, "key.pem")
}

func (m *Manager) metaPath() string {
	return filepath.Join(m.certDir, "meta.json")
}

func (m *Manager) ensureCertDir() error {
	return os.MkdirAll(m.certDir, 0755)
}

// LoadCachedCert loads a cached certificate from disk.
func (m *Manager) LoadCachedCert() (*CertificateBundle, error) {
	metaPath := m.metaPath()
	if _, err := os.Stat(metaPath); os.IsNotExist(err) {
		return nil, nil
	}

	// Check that PEM files exist
	if _, err := os.Stat(m.certPath()); os.IsNotExist(err) {
		return nil, nil
	}
	if _, err := os.Stat(m.keyPath()); os.IsNotExist(err) {
		return nil, nil
	}

	// Load metadata
	metaData, err := os.ReadFile(metaPath)
	if err != nil {
		return nil, err
	}

	var meta CertificateMeta
	if err := json.Unmarshal(metaData, &meta); err != nil {
		return nil, err
	}

	// Load cert and key
	cert, err := os.ReadFile(m.certPath())
	if err != nil {
		return nil, err
	}

	key, err := os.ReadFile(m.keyPath())
	if err != nil {
		return nil, err
	}

	return &CertificateBundle{
		Cert:      string(cert),
		Key:       string(key),
		Domain:    meta.Domain,
		ExpiresAt: meta.ExpiresAt,
		IssuedAt:  meta.IssuedAt,
	}, nil
}

// SaveCert saves a certificate bundle to disk.
func (m *Manager) SaveCert(bundle *CertificateBundle) error {
	if err := m.ensureCertDir(); err != nil {
		return err
	}

	// Save PEM files
	if err := os.WriteFile(m.certPath(), []byte(bundle.Cert), 0644); err != nil {
		return err
	}

	if err := os.WriteFile(m.keyPath(), []byte(bundle.Key), 0600); err != nil {
		return err
	}

	// Save metadata
	meta := CertificateMeta{
		Domain:    bundle.Domain,
		ExpiresAt: bundle.ExpiresAt,
		IssuedAt:  bundle.IssuedAt,
	}

	metaData, err := json.MarshalIndent(meta, "", "  ")
	if err != nil {
		return err
	}

	if err := os.WriteFile(m.metaPath(), metaData, 0644); err != nil {
		return err
	}

	log.Printf("Saved certificate for %s, expires %s", bundle.Domain, bundle.ExpiresAt.Format(time.RFC3339))
	return nil
}

// FetchFromAPI fetches a certificate from the cert API.
func (m *Manager) FetchFromAPI() (*CertificateBundle, error) {
	log.Printf("Fetching certificate from %s", m.certAPIURL)

	resp, err := m.httpClient.Get(m.certAPIURL)
	if err != nil {
		return nil, fmt.Errorf("%w: %v", ErrCertificateFetch, err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(resp.Body)
		return nil, fmt.Errorf("%w: API returned %d: %s", ErrCertificateFetch, resp.StatusCode, string(body))
	}

	// Parse response
	var apiResp struct {
		Cert      string `json:"cert"`
		Key       string `json:"key"`
		Domain    string `json:"domain"`
		ExpiresAt string `json:"expires_at"`
		IssuedAt  string `json:"issued_at"`
	}

	if err := json.NewDecoder(resp.Body).Decode(&apiResp); err != nil {
		return nil, fmt.Errorf("%w: invalid response: %v", ErrCertificateFetch, err)
	}

	expiresAt, err := time.Parse(time.RFC3339, apiResp.ExpiresAt)
	if err != nil {
		return nil, fmt.Errorf("%w: invalid expires_at: %v", ErrCertificateFetch, err)
	}

	issuedAt, err := time.Parse(time.RFC3339, apiResp.IssuedAt)
	if err != nil {
		return nil, fmt.Errorf("%w: invalid issued_at: %v", ErrCertificateFetch, err)
	}

	return &CertificateBundle{
		Cert:      apiResp.Cert,
		Key:       apiResp.Key,
		Domain:    apiResp.Domain,
		ExpiresAt: expiresAt,
		IssuedAt:  issuedAt,
	}, nil
}

// EnsureCertificate ensures a valid certificate is available.
// Returns the paths to the cert and key files.
func (m *Manager) EnsureCertificate() (certPath, keyPath string, err error) {
	// Check cached certificate
	cached, err := m.LoadCachedCert()
	if err != nil {
		log.Printf("Warning: failed to load cached certificate: %v", err)
	}

	if cached != nil {
		if cached.IsExpired() {
			log.Println("Cached certificate is expired, fetching new one")
		} else if cached.DaysUntilExpiry() < refreshThresholdDays {
			log.Printf("Certificate expires in %.1f days, fetching refresh", cached.DaysUntilExpiry())
		} else {
			log.Printf("Using cached certificate for %s, expires in %.1f days",
				cached.Domain, cached.DaysUntilExpiry())
			return m.certPath(), m.keyPath(), nil
		}
	}

	// Fetch new certificate
	bundle, err := m.FetchFromAPI()
	if err != nil {
		// If we have a cached cert (even if expiring soon), use it
		if cached != nil && !cached.IsExpired() {
			log.Printf("Failed to fetch new certificate, using cached cert (expires in %.1f days): %v",
				cached.DaysUntilExpiry(), err)
			return m.certPath(), m.keyPath(), nil
		}
		return "", "", err
	}

	if err := m.SaveCert(bundle); err != nil {
		return "", "", err
	}

	return m.certPath(), m.keyPath(), nil
}
