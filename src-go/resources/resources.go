// Package resources contains embedded resources for the application.
package resources

import (
	_ "embed"
	"runtime"

	"fyne.io/fyne/v2"
)

//go:embed icon.png
var iconBytes []byte

//go:embed pulse.svg
var trayIconBytes []byte

//go:embed tray_template.png
var trayTemplatePNGBytes []byte

// Icon returns the application icon resource.
func Icon() fyne.Resource {
	return fyne.NewStaticResource("icon.png", iconBytes)
}

// TrayIcon returns the system tray icon resource.
// Returns SVG on macOS/Linux, PNG on Windows (Windows doesn't support SVG in system tray).
func TrayIcon() fyne.Resource {
	if runtime.GOOS == "windows" {
		return fyne.NewStaticResource("tray_template.png", trayTemplatePNGBytes)
	}
	return fyne.NewStaticResource("pulse.svg", trayIconBytes)
}

// TrayIconBytes returns the raw tray icon bytes for use with systray.SetTemplateIcon.
// Returns PNG data which is required for macOS template icons.
func TrayIconBytes() []byte {
	return trayTemplatePNGBytes
}
