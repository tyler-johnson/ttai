// Package ui provides the user interface for the TTAI application.
package ui

import (
	"log"
	"runtime"

	"fyne.io/fyne/v2"
	"fyne.io/fyne/v2/driver/desktop"
	"fyne.io/fyne/v2/theme"

	"github.com/ttai/ttai/internal/config"
	"github.com/ttai/ttai/resources"
)

// TrayManager manages the system tray icon and menu using Fyne.
// On macOS, use NativeTray instead for better compatibility with menu bar managers.
type TrayManager struct {
	app    fyne.App
	cfg    *config.Config
	onShow func()
	onQuit func()
	menu   *fyne.Menu
	window fyne.Window
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

// SetWindow sets the window reference for clipboard access.
func (t *TrayManager) SetWindow(w fyne.Window) {
	t.window = w
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

	// Build menu - Note: Fyne automatically adds "Quit" on macOS,
	// so we only add our own quit item on other platforms
	copyURLItem := fyne.NewMenuItem("Copy MCP Server URL", t.onCopyURL)
	showItem := fyne.NewMenuItem("Show Settings", t.onShow)

	if runtime.GOOS == "darwin" {
		// On macOS, Fyne adds its own Quit item automatically
		t.menu = fyne.NewMenu("TTAI",
			copyURLItem,
			showItem,
		)
	} else {
		// On other platforms, add our own quit item
		quitItem := fyne.NewMenuItem("Quit TTAI", t.onQuit)
		t.menu = fyne.NewMenu("TTAI",
			copyURLItem,
			showItem,
			fyne.NewMenuItemSeparator(),
			quitItem,
		)
	}

	desk.SetSystemTrayMenu(t.menu)
	log.Println("System tray configured")
}

func (t *TrayManager) onCopyURL() {
	// Get the appropriate URL
	var url string
	if t.cfg.SSLEnabled() {
		url = t.cfg.HTTPSURL()
	} else {
		url = t.cfg.HTTPURL()
	}

	// Copy to clipboard using the window
	if t.window != nil {
		t.window.Clipboard().SetContent(url)
		log.Printf("Copied URL to clipboard: %s", url)
		return
	}

	// Fallback: store in global for retrieval
	clipboardContent = url
	log.Printf("Copied URL to clipboard (fallback): %s", url)
}

// clipboardContent is a temporary storage for clipboard content
// This is a workaround since Fyne needs a window for clipboard access
var clipboardContent string

// GetClipboardContent returns the last content copied via the tray.
func GetClipboardContent() string {
	return clipboardContent
}

