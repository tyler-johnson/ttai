//go:build darwin

package update

import (
	"archive/zip"
	"fmt"
	"io"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
)

// ApplyUpdate applies the downloaded update on macOS.
// It extracts the .app bundle from the zip and replaces the current app.
func (u *GitHubUpdater) ApplyUpdate() error {
	u.mu.RLock()
	downloadPath := u.downloadPath
	info := u.updateInfo
	u.mu.RUnlock()

	if downloadPath == "" || info == nil {
		return fmt.Errorf("no update downloaded")
	}

	// Check if it's a zip file (macOS .app bundles are distributed as zips)
	if !strings.HasSuffix(downloadPath, ".zip") {
		// Not a zip, just open the release URL in browser
		return openBrowser(info.ReleaseURL)
	}

	// Get the current executable path
	execPath, err := os.Executable()
	if err != nil {
		return fmt.Errorf("failed to get executable path: %w", err)
	}

	// Resolve symlinks to get the real path
	execPath, err = filepath.EvalSymlinks(execPath)
	if err != nil {
		return fmt.Errorf("failed to resolve executable path: %w", err)
	}

	// Check if we're running from an .app bundle
	// Path would be: /Applications/TTAI.app/Contents/MacOS/ttai
	if !strings.Contains(execPath, ".app/Contents/MacOS") {
		// Not running from .app bundle, open browser instead
		return openBrowser(info.ReleaseURL)
	}

	// Get the .app bundle path
	appPath := execPath
	for !strings.HasSuffix(appPath, ".app") && appPath != "/" {
		appPath = filepath.Dir(appPath)
	}

	if appPath == "/" {
		return fmt.Errorf("could not find .app bundle")
	}

	// Extract zip to temp directory
	tempDir, err := os.MkdirTemp("", "ttai-update-*")
	if err != nil {
		return fmt.Errorf("failed to create temp directory: %w", err)
	}

	if err := extractZip(downloadPath, tempDir); err != nil {
		os.RemoveAll(tempDir)
		return fmt.Errorf("failed to extract update: %w", err)
	}

	// Find the .app bundle in the extracted files
	var newAppPath string
	entries, err := os.ReadDir(tempDir)
	if err != nil {
		os.RemoveAll(tempDir)
		return fmt.Errorf("failed to read temp directory: %w", err)
	}

	for _, entry := range entries {
		if strings.HasSuffix(entry.Name(), ".app") {
			newAppPath = filepath.Join(tempDir, entry.Name())
			break
		}
	}

	if newAppPath == "" {
		os.RemoveAll(tempDir)
		return fmt.Errorf("no .app bundle found in update")
	}

	// Get the parent directory of the current app
	appDir := filepath.Dir(appPath)
	appName := filepath.Base(appPath)

	// Create a backup of the current app
	backupPath := appPath + ".backup"
	os.RemoveAll(backupPath) // Remove any existing backup

	if err := os.Rename(appPath, backupPath); err != nil {
		os.RemoveAll(tempDir)
		return fmt.Errorf("failed to backup current app: %w", err)
	}

	// Move the new app into place
	destPath := filepath.Join(appDir, appName)
	if err := os.Rename(newAppPath, destPath); err != nil {
		// Restore backup
		os.Rename(backupPath, appPath)
		os.RemoveAll(tempDir)
		return fmt.Errorf("failed to install update: %w", err)
	}

	// Clean up
	os.RemoveAll(tempDir)
	os.RemoveAll(backupPath)
	os.Remove(downloadPath)

	// Relaunch the app
	cmd := exec.Command("open", destPath)
	if err := cmd.Start(); err != nil {
		return fmt.Errorf("failed to relaunch app: %w", err)
	}

	// Exit current instance
	os.Exit(0)
	return nil
}

func extractZip(src, dest string) error {
	r, err := zip.OpenReader(src)
	if err != nil {
		return err
	}
	defer r.Close()

	for _, f := range r.File {
		fpath := filepath.Join(dest, f.Name)

		// Check for ZipSlip vulnerability
		if !strings.HasPrefix(fpath, filepath.Clean(dest)+string(os.PathSeparator)) {
			return fmt.Errorf("invalid file path: %s", fpath)
		}

		if f.FileInfo().IsDir() {
			os.MkdirAll(fpath, os.ModePerm)
			continue
		}

		if err := os.MkdirAll(filepath.Dir(fpath), os.ModePerm); err != nil {
			return err
		}

		outFile, err := os.OpenFile(fpath, os.O_WRONLY|os.O_CREATE|os.O_TRUNC, f.Mode())
		if err != nil {
			return err
		}

		rc, err := f.Open()
		if err != nil {
			outFile.Close()
			return err
		}

		_, err = io.Copy(outFile, rc)
		outFile.Close()
		rc.Close()

		if err != nil {
			return err
		}
	}

	return nil
}

func openBrowser(url string) error {
	return exec.Command("open", url).Start()
}
