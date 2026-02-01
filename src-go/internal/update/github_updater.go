package update

import (
	"context"
	"fmt"
	"io"
	"net/http"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"time"
)

// GitHubUpdater is a cross-platform updater that uses GitHub releases.
type GitHubUpdater struct {
	currentVersion string
	dataDir        string

	mu           sync.RWMutex
	updateInfo   *UpdateInfo
	downloadPath string
}

// NewGitHubUpdater creates a new GitHub-based updater.
func NewGitHubUpdater(currentVersion, dataDir string) *GitHubUpdater {
	return &GitHubUpdater{
		currentVersion: currentVersion,
		dataDir:        dataDir,
	}
}

// CheckForUpdates checks GitHub for a newer release.
func (u *GitHubUpdater) CheckForUpdates(ctx context.Context) (*UpdateInfo, error) {
	release, err := CheckGitHubRelease(ctx)
	if err != nil {
		return nil, err
	}

	// Parse version from tag (remove 'v' prefix if present)
	version := strings.TrimPrefix(release.TagName, "v")

	// Check if this is actually newer
	if CompareVersions(version, u.currentVersion) <= 0 {
		return nil, nil
	}

	// Find the appropriate asset for this platform
	asset := FindAssetForPlatform(release)
	if asset == nil {
		return nil, fmt.Errorf("no compatible download found for this platform")
	}

	info := &UpdateInfo{
		Version:      version,
		ReleaseURL:   release.HTMLURL,
		DownloadURL:  asset.BrowserDownloadURL,
		ReleaseNotes: release.Body,
		PublishedAt:  release.PublishedAt,
		IsDownloaded: false,
	}

	u.mu.Lock()
	u.updateInfo = info
	u.mu.Unlock()

	return info, nil
}

// GetUpdateInfo returns the current update info.
func (u *GitHubUpdater) GetUpdateInfo() *UpdateInfo {
	u.mu.RLock()
	defer u.mu.RUnlock()
	if u.updateInfo == nil {
		return nil
	}
	info := *u.updateInfo
	return &info
}

// DownloadUpdate downloads the update to a temporary location.
func (u *GitHubUpdater) DownloadUpdate(ctx context.Context) error {
	u.mu.RLock()
	info := u.updateInfo
	u.mu.RUnlock()

	if info == nil {
		return fmt.Errorf("no update available")
	}

	// Create updates directory
	updatesDir := filepath.Join(u.dataDir, "updates")
	if err := os.MkdirAll(updatesDir, 0755); err != nil {
		return fmt.Errorf("failed to create updates directory: %w", err)
	}

	// Determine filename from URL
	urlParts := strings.Split(info.DownloadURL, "/")
	filename := urlParts[len(urlParts)-1]
	downloadPath := filepath.Join(updatesDir, filename)

	// Download the file
	req, err := http.NewRequestWithContext(ctx, "GET", info.DownloadURL, nil)
	if err != nil {
		return fmt.Errorf("failed to create request: %w", err)
	}
	req.Header.Set("User-Agent", UserAgent)

	client := &http.Client{Timeout: 10 * time.Minute}
	resp, err := client.Do(req)
	if err != nil {
		return fmt.Errorf("failed to download: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return fmt.Errorf("download failed with status: %d", resp.StatusCode)
	}

	// Create the file
	file, err := os.Create(downloadPath)
	if err != nil {
		return fmt.Errorf("failed to create file: %w", err)
	}
	defer file.Close()

	// Copy the response body to the file
	_, err = io.Copy(file, resp.Body)
	if err != nil {
		os.Remove(downloadPath)
		return fmt.Errorf("failed to write file: %w", err)
	}

	u.mu.Lock()
	u.downloadPath = downloadPath
	if u.updateInfo != nil {
		u.updateInfo.IsDownloaded = true
	}
	u.mu.Unlock()

	return nil
}

// GetDownloadPath returns the path to the downloaded update.
func (u *GitHubUpdater) GetDownloadPath() string {
	u.mu.RLock()
	defer u.mu.RUnlock()
	return u.downloadPath
}

// Platform returns the platform identifier.
func (u *GitHubUpdater) Platform() string {
	return "github"
}
