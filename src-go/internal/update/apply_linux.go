//go:build linux

package update

import (
	"fmt"
	"io"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"syscall"
)

// ApplyUpdate applies the downloaded update on Linux.
// It replaces the current AppImage/binary and restarts.
func (u *GitHubUpdater) ApplyUpdate() error {
	u.mu.RLock()
	downloadPath := u.downloadPath
	info := u.updateInfo
	u.mu.RUnlock()

	if downloadPath == "" || info == nil {
		return fmt.Errorf("no update downloaded")
	}

	// Get the current executable path
	execPath, err := os.Executable()
	if err != nil {
		return fmt.Errorf("failed to get executable path: %w", err)
	}

	// Resolve symlinks
	execPath, err = filepath.EvalSymlinks(execPath)
	if err != nil {
		return fmt.Errorf("failed to resolve executable path: %w", err)
	}

	// Check if running from an AppImage
	appImagePath := os.Getenv("APPIMAGE")
	if appImagePath != "" {
		execPath = appImagePath
	}

	// If download is an AppImage, replace the current one
	if strings.HasSuffix(downloadPath, ".AppImage") {
		return u.replaceAndRestart(downloadPath, execPath)
	}

	// If it's a regular binary, also replace
	if !strings.Contains(downloadPath, ".") || strings.HasSuffix(downloadPath, "-linux") {
		return u.replaceAndRestart(downloadPath, execPath)
	}

	// Unknown format, open browser
	return openBrowser(info.ReleaseURL)
}

func (u *GitHubUpdater) replaceAndRestart(newPath, currentPath string) error {
	// Create backup
	backupPath := currentPath + ".backup"
	if err := copyFile(currentPath, backupPath); err != nil {
		return fmt.Errorf("failed to create backup: %w", err)
	}

	// Copy new version to current location
	if err := copyFile(newPath, currentPath); err != nil {
		// Restore backup
		copyFile(backupPath, currentPath)
		return fmt.Errorf("failed to install update: %w", err)
	}

	// Make executable
	if err := os.Chmod(currentPath, 0755); err != nil {
		return fmt.Errorf("failed to set permissions: %w", err)
	}

	// Clean up
	os.Remove(backupPath)
	os.Remove(newPath)

	// Restart the application
	// Use syscall.Exec to replace the current process
	return syscall.Exec(currentPath, []string{currentPath}, os.Environ())
}

func copyFile(src, dst string) error {
	source, err := os.Open(src)
	if err != nil {
		return err
	}
	defer source.Close()

	destination, err := os.Create(dst)
	if err != nil {
		return err
	}
	defer destination.Close()

	_, err = io.Copy(destination, source)
	return err
}

func openBrowser(url string) error {
	return exec.Command("xdg-open", url).Start()
}
