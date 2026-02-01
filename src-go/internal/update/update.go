// Package update provides auto-update functionality for TTAI.
package update

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"runtime"
	"strings"
	"time"
)

// UpdateInfo contains information about an available update.
type UpdateInfo struct {
	Version      string `json:"version"`
	ReleaseURL   string `json:"release_url"`
	DownloadURL  string `json:"download_url"`
	ReleaseNotes string `json:"release_notes"`
	IsDownloaded bool   `json:"is_downloaded"`
	PublishedAt  string `json:"published_at"`
}

// Updater defines the interface for platform-specific updaters.
type Updater interface {
	// CheckForUpdates checks for available updates.
	CheckForUpdates(ctx context.Context) (*UpdateInfo, error)
	// GetUpdateInfo returns the current update info without checking.
	GetUpdateInfo() *UpdateInfo
	// DownloadUpdate downloads the update to a temporary location.
	DownloadUpdate(ctx context.Context) error
	// ApplyUpdate applies the downloaded update.
	ApplyUpdate() error
	// Platform returns the platform name for this updater.
	Platform() string
}

// GitHubRelease represents a GitHub release response.
type GitHubRelease struct {
	TagName     string        `json:"tag_name"`
	Name        string        `json:"name"`
	Body        string        `json:"body"`
	HTMLURL     string        `json:"html_url"`
	PublishedAt string        `json:"published_at"`
	Assets      []GitHubAsset `json:"assets"`
}

// GitHubAsset represents a GitHub release asset.
type GitHubAsset struct {
	Name               string `json:"name"`
	BrowserDownloadURL string `json:"browser_download_url"`
	Size               int64  `json:"size"`
}

const (
	// GitHubOwner is the repository owner.
	GitHubOwner = "tyler-johnson"
	// GitHubRepo is the repository name.
	GitHubRepo = "ttai"
	// GitHubAPIURL is the GitHub API base URL.
	GitHubAPIURL = "https://api.github.com"
	// UserAgent is the HTTP User-Agent header value.
	UserAgent = "TTAI-Updater/1.0"
)

// CheckGitHubRelease fetches the latest release from GitHub.
func CheckGitHubRelease(ctx context.Context) (*GitHubRelease, error) {
	url := fmt.Sprintf("%s/repos/%s/%s/releases/latest", GitHubAPIURL, GitHubOwner, GitHubRepo)

	req, err := http.NewRequestWithContext(ctx, "GET", url, nil)
	if err != nil {
		return nil, fmt.Errorf("failed to create request: %w", err)
	}

	req.Header.Set("User-Agent", UserAgent)
	req.Header.Set("Accept", "application/vnd.github.v3+json")

	client := &http.Client{Timeout: 30 * time.Second}
	resp, err := client.Do(req)
	if err != nil {
		return nil, fmt.Errorf("failed to fetch release: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode == http.StatusNotFound {
		return nil, fmt.Errorf("no releases found")
	}

	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("unexpected status code: %d", resp.StatusCode)
	}

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, fmt.Errorf("failed to read response: %w", err)
	}

	var release GitHubRelease
	if err := json.Unmarshal(body, &release); err != nil {
		return nil, fmt.Errorf("failed to parse release: %w", err)
	}

	return &release, nil
}

// FindAssetForPlatform finds the appropriate download asset for the current platform.
func FindAssetForPlatform(release *GitHubRelease) *GitHubAsset {
	var patterns []string

	switch runtime.GOOS {
	case "darwin":
		arch := runtime.GOARCH
		if arch == "arm64" {
			patterns = []string{"darwin-arm64.zip", "macos-arm64.zip"}
		} else {
			patterns = []string{"darwin-amd64.zip", "macos-amd64.zip", "darwin-x64.zip"}
		}
	case "windows":
		patterns = []string{".msi", "-Setup.msi", "-windows.exe", "windows-amd64.exe"}
	case "linux":
		patterns = []string{".AppImage", "-x86_64.AppImage", "-linux"}
	}

	for _, pattern := range patterns {
		for i := range release.Assets {
			if strings.Contains(release.Assets[i].Name, pattern) {
				return &release.Assets[i]
			}
		}
	}

	return nil
}

// CompareVersions compares two semantic version strings.
// Returns 1 if v1 > v2, -1 if v1 < v2, 0 if equal.
func CompareVersions(v1, v2 string) int {
	// Remove 'v' prefix if present
	v1 = strings.TrimPrefix(v1, "v")
	v2 = strings.TrimPrefix(v2, "v")

	// Split by '.' and compare each part
	parts1 := strings.Split(v1, ".")
	parts2 := strings.Split(v2, ".")

	// Compare each part
	maxLen := len(parts1)
	if len(parts2) > maxLen {
		maxLen = len(parts2)
	}

	for i := 0; i < maxLen; i++ {
		var n1, n2 int
		if i < len(parts1) {
			fmt.Sscanf(parts1[i], "%d", &n1)
		}
		if i < len(parts2) {
			fmt.Sscanf(parts2[i], "%d", &n2)
		}

		if n1 > n2 {
			return 1
		}
		if n1 < n2 {
			return -1
		}
	}

	return 0
}
