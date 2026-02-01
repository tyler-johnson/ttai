//go:build windows

package update

import (
	"fmt"
	"os"
	"os/exec"
	"strings"
	"syscall"
)

// ApplyUpdate applies the downloaded update on Windows.
// It runs the MSI installer which handles the upgrade.
func (u *GitHubUpdater) ApplyUpdate() error {
	u.mu.RLock()
	downloadPath := u.downloadPath
	info := u.updateInfo
	u.mu.RUnlock()

	if downloadPath == "" || info == nil {
		return fmt.Errorf("no update downloaded")
	}

	// Check if it's an MSI file
	if !strings.HasSuffix(strings.ToLower(downloadPath), ".msi") {
		// Not an MSI, check if it's an EXE
		if strings.HasSuffix(strings.ToLower(downloadPath), ".exe") {
			return runExeInstaller(downloadPath)
		}
		// Open browser for manual download
		return openBrowser(info.ReleaseURL)
	}

	// Run msiexec to install the update
	// /i = install, /passive = unattended with progress bar, /norestart = don't auto-restart
	cmd := exec.Command("msiexec", "/i", downloadPath, "/passive", "/norestart")
	cmd.SysProcAttr = &syscall.SysProcAttr{
		CreationFlags: syscall.CREATE_NEW_PROCESS_GROUP,
	}

	if err := cmd.Start(); err != nil {
		return fmt.Errorf("failed to start installer: %w", err)
	}

	// Exit the current application to allow the installer to proceed
	os.Exit(0)
	return nil
}

func runExeInstaller(path string) error {
	cmd := exec.Command(path)
	cmd.SysProcAttr = &syscall.SysProcAttr{
		CreationFlags: syscall.CREATE_NEW_PROCESS_GROUP,
	}

	if err := cmd.Start(); err != nil {
		return fmt.Errorf("failed to start installer: %w", err)
	}

	os.Exit(0)
	return nil
}

func openBrowser(url string) error {
	return exec.Command("rundll32", "url.dll,FileProtocolHandler", url).Start()
}
