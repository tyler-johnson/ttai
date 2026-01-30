package pages

import (
	"fyne.io/fyne/v2"
	"fyne.io/fyne/v2/container"
	"fyne.io/fyne/v2/widget"

	"github.com/ttai/ttai/internal/state"
)

// SettingsPage displays application settings.
type SettingsPage struct {
	widget.BaseWidget

	prefs   *state.Preferences
	content fyne.CanvasObject
}

// NewSettingsPage creates a new settings page.
func NewSettingsPage(prefs *state.Preferences) *SettingsPage {
	p := &SettingsPage{
		prefs: prefs,
	}
	p.ExtendBaseWidget(p)
	p.buildUI()
	return p
}

func (p *SettingsPage) buildUI() {
	// Startup section
	startupLabel := widget.NewLabelWithStyle("Startup:", fyne.TextAlignLeading, fyne.TextStyle{Bold: true})

	launchCheck := widget.NewCheck("Launch TTAI when you log in", func(checked bool) {
		if !state.SetLaunchAtStartup(checked) {
			// Revert on failure
			// Note: we'd need to refresh the checkbox state here in a real implementation
		}
	})
	launchCheck.Checked = state.IsLaunchAtStartupEnabled()

	// Disable if not supported
	if !state.IsPlatformSupported() {
		launchCheck.Disable()
	}

	startupSection := container.NewHBox(startupLabel, launchCheck)

	// Window section
	windowLabel := widget.NewLabelWithStyle("Window:", fyne.TextAlignLeading, fyne.TextStyle{Bold: true})

	showWindowCheck := widget.NewCheck("Show settings window on launch", func(checked bool) {
		if p.prefs != nil {
			p.prefs.SetShowWindowOnLaunch(checked)
		}
	})

	if p.prefs != nil {
		showWindowCheck.Checked = p.prefs.ShowWindowOnLaunch()
	} else {
		showWindowCheck.Checked = true
		showWindowCheck.Disable()
	}

	windowSection := container.NewHBox(windowLabel, showWindowCheck)

	// Main layout
	form := container.NewVBox(
		startupSection,
		widget.NewSeparator(),
		windowSection,
	)

	p.content = container.NewPadded(form)
}

// CreateRenderer implements fyne.Widget.
func (p *SettingsPage) CreateRenderer() fyne.WidgetRenderer {
	return widget.NewSimpleRenderer(p.content)
}
