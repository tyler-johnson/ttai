// Package resources contains embedded resources for the application.
package resources

import (
	_ "embed"

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

// TrayIcon returns the system tray icon resource (monochrome SVG).
func TrayIcon() fyne.Resource {
	return fyne.NewStaticResource("pulse.svg", trayIconBytes)
}

// TrayIconBytes returns the raw tray icon bytes for use with systray.SetTemplateIcon.
// Returns PNG data which is required for macOS template icons.
func TrayIconBytes() []byte {
	return trayTemplatePNGBytes
}
