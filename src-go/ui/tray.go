// Package ui provides the user interface for the TTAI application.
package ui

import (
	"fmt"
	"log"
	"runtime"

	"fyne.io/fyne/v2"
	"fyne.io/fyne/v2/driver/desktop"
	"fyne.io/fyne/v2/theme"

	"github.com/tyler-johnson/ttai/internal/config"
	"github.com/tyler-johnson/ttai/internal/update"
	"github.com/tyler-johnson/ttai/internal/webui"
	"github.com/tyler-johnson/ttai/resources"
)

// TrayManager manages the system tray icon and menu using Fyne.
type TrayManager struct {
	app           fyne.App
	cfg           *config.Config
	onShow        func()
	onQuit        func()
	menu          *fyne.Menu
	updateItem    *fyne.MenuItem
	updateManager *update.Manager
}

// NewTrayManager creates a new system tray manager.
func NewTrayManager(app fyne.App, cfg *config.Config, onShow, onQuit func()) *TrayManager {
	return &TrayManager{
		app:    app,
		cfg:    cfg,
		onShow: onShow,
		onQuit: onQuit,
	}
}

// SetUpdateManager sets the update manager and subscribes to state changes.
func (t *TrayManager) SetUpdateManager(um *update.Manager) {
	t.updateManager = um

	// Subscribe to update state changes
	um.State().OnChange(func(s update.State) {
		t.updateTrayMenu()
	})
}

// Setup configures the system tray icon and menu.
func (t *TrayManager) Setup() {
	// Check if we're on a desktop with system tray support
	desk, ok := t.app.(desktop.App)
	if !ok {
		log.Println("System tray not available on this platform")
		return
	}

	// Set the tray icon using ThemedResource for proper dark/light mode adaptation on macOS
	trayIcon := resources.TrayIcon()
	if runtime.GOOS == "darwin" {
		trayIcon = theme.NewThemedResource(trayIcon)
	}
	desk.SetSystemTrayIcon(trayIcon)

	// Build menu - Fyne automatically adds a "Quit" item on all platforms
	copyURLItem := fyne.NewMenuItem("Copy MCP Server URL", t.onCopyURL)
	showItem := fyne.NewMenuItem("Open Settings", t.onShow)

	// Update item (hidden by default)
	t.updateItem = fyne.NewMenuItem("Check for Updates", t.onCheckForUpdates)

	t.menu = fyne.NewMenu("TTAI",
		copyURLItem,
		showItem,
		fyne.NewMenuItemSeparator(),
		t.updateItem,
	)

	desk.SetSystemTrayMenu(t.menu)
	log.Println("System tray configured")
}

// updateTrayMenu updates the tray menu based on update state.
func (t *TrayManager) updateTrayMenu() {
	if t.updateManager == nil || t.updateItem == nil {
		return
	}

	snap := t.updateManager.State().Snapshot()

	switch snap.Status {
	case update.StatusAvailable:
		if snap.UpdateInfo != nil {
			t.updateItem.Label = fmt.Sprintf("Update Available (v%s)", snap.UpdateInfo.Version)
		} else {
			t.updateItem.Label = "Update Available"
		}
		t.updateItem.Action = t.onOpenSettings
	case update.StatusReady:
		if snap.UpdateInfo != nil {
			t.updateItem.Label = fmt.Sprintf("Install Update (v%s)", snap.UpdateInfo.Version)
		} else {
			t.updateItem.Label = "Install Update"
		}
		t.updateItem.Action = t.onInstallUpdate
	case update.StatusChecking:
		t.updateItem.Label = "Checking for Updates..."
		t.updateItem.Action = nil
	case update.StatusDownloading:
		t.updateItem.Label = "Downloading Update..."
		t.updateItem.Action = nil
	default:
		t.updateItem.Label = "Check for Updates"
		t.updateItem.Action = t.onCheckForUpdates
	}

	// Refresh the menu
	if desk, ok := t.app.(desktop.App); ok {
		desk.SetSystemTrayMenu(t.menu)
	}
}

func (t *TrayManager) onCheckForUpdates() {
	if t.updateManager != nil {
		go t.updateManager.CheckForUpdates()
	}
}

func (t *TrayManager) onOpenSettings() {
	if t.onShow != nil {
		t.onShow()
	}
}

func (t *TrayManager) onInstallUpdate() {
	if t.updateManager != nil {
		go func() {
			if err := t.updateManager.ApplyUpdate(); err != nil {
				log.Printf("Failed to apply update: %v", err)
			}
		}()
	}
}

func (t *TrayManager) onCopyURL() {
	// Get the appropriate URL
	url := webui.GetMCPURL(t.cfg)

	// Copy to clipboard using system command
	if err := webui.CopyToClipboard(url); err != nil {
		log.Printf("Failed to copy to clipboard: %v", err)
		return
	}
	log.Printf("Copied URL to clipboard: %s", url)
}
