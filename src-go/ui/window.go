package ui

import (
	"fyne.io/fyne/v2"
	"fyne.io/fyne/v2/container"
	"fyne.io/fyne/v2/theme"

	"github.com/ttai/ttai/internal/config"
	"github.com/ttai/ttai/internal/state"
	"github.com/ttai/ttai/internal/tastytrade"
	"github.com/ttai/ttai/ui/pages"
)

const (
	windowWidth  = 620
	windowHeight = 400
)

// MainWindow is the main application window.
type MainWindow struct {
	window fyne.Window
	cfg    *config.Config
	client *tastytrade.Client
	state  *state.AppState
	prefs  *state.Preferences

	// Pages
	connectionPage *pages.ConnectionPage
	settingsPage   *pages.SettingsPage
	aboutPage      *pages.AboutPage

	// Tab container
	tabs *container.AppTabs
}

// NewMainWindow creates the main application window.
func NewMainWindow(
	app fyne.App,
	cfg *config.Config,
	client *tastytrade.Client,
	appState *state.AppState,
	prefs *state.Preferences,
	icon fyne.Resource,
) *MainWindow {
	window := app.NewWindow("TTAI")
	window.Resize(fyne.NewSize(windowWidth, windowHeight))
	window.SetFixedSize(true)

	m := &MainWindow{
		window: window,
		cfg:    cfg,
		client: client,
		state:  appState,
		prefs:  prefs,
	}

	m.buildUI(icon)
	m.setupCloseHandler()

	return m
}

func (m *MainWindow) buildUI(icon fyne.Resource) {
	// Create pages
	m.connectionPage = pages.NewConnectionPage(m.cfg, m.client, m.state, m.window)
	m.settingsPage = pages.NewSettingsPage(m.prefs)
	m.aboutPage = pages.NewAboutPage(icon)

	// Create tabs
	m.tabs = container.NewAppTabs(
		container.NewTabItemWithIcon("Connection", theme.ComputerIcon(), m.connectionPage),
		container.NewTabItemWithIcon("Settings", theme.SettingsIcon(), m.settingsPage),
		container.NewTabItemWithIcon("About", theme.InfoIcon(), m.aboutPage),
	)
	m.tabs.SetTabLocation(container.TabLocationTop)

	m.window.SetContent(m.tabs)
}

func (m *MainWindow) setupCloseHandler() {
	m.window.SetCloseIntercept(func() {
		// Hide instead of closing (stay in system tray)
		m.window.Hide()
	})
}

// Show displays and activates the window.
func (m *MainWindow) Show() {
	m.window.Show()
	m.window.RequestFocus()
}

// Hide hides the window.
func (m *MainWindow) Hide() {
	m.window.Hide()
}

// Close forces the window to close.
func (m *MainWindow) Close() {
	m.window.Close()
}

// Window returns the underlying fyne.Window.
func (m *MainWindow) Window() fyne.Window {
	return m.window
}

// SelectTab programmatically selects a tab by index.
func (m *MainWindow) SelectTab(index int) {
	if index >= 0 && index < len(m.tabs.Items) {
		m.tabs.SelectIndex(index)
	}
}
