// Package pages provides the UI pages for the TTAI application.
package pages

import (
	"log"
	"time"

	"fyne.io/fyne/v2"
	"fyne.io/fyne/v2/canvas"
	"fyne.io/fyne/v2/container"
	"fyne.io/fyne/v2/layout"
	"fyne.io/fyne/v2/theme"
	"fyne.io/fyne/v2/widget"

	"github.com/ttai/ttai/internal/config"
	"github.com/ttai/ttai/internal/state"
	"github.com/ttai/ttai/internal/tastytrade"
	"github.com/ttai/ttai/ui/dialogs"
)

// ConnectionPage displays MCP server URLs and TastyTrade connection status.
type ConnectionPage struct {
	widget.BaseWidget

	cfg    *config.Config
	client *tastytrade.Client
	state  *state.AppState
	window fyne.Window

	statusIcon    *canvas.Circle
	statusLabel   *widget.Label
	connectBtn    *widget.Button
	disconnectBtn *widget.Button

	content fyne.CanvasObject
}

// NewConnectionPage creates a new connection page.
func NewConnectionPage(cfg *config.Config, client *tastytrade.Client, appState *state.AppState, window fyne.Window) *ConnectionPage {
	p := &ConnectionPage{
		cfg:    cfg,
		client: client,
		state:  appState,
		window: window,
	}
	p.ExtendBaseWidget(p)
	p.buildUI()
	p.updateAuthView()

	// Listen for auth state changes
	appState.OnAuthChanged(func(authenticated bool) {
		p.updateAuthView()
	})

	return p
}

func (p *ConnectionPage) buildUI() {
	// MCP Server URLs section
	mcpLabel := widget.NewLabelWithStyle("MCP Server:", fyne.TextAlignLeading, fyne.TextStyle{Bold: true})
	mcpLabel.Resize(fyne.NewSize(100, mcpLabel.MinSize().Height))

	urlsContainer := container.NewVBox()

	// HTTPS URL (if SSL enabled)
	if p.cfg.SSLEnabled() {
		httpsURL := p.cfg.HTTPSURL()
		urlsContainer.Add(p.makeURLRow(httpsURL))
	}

	// HTTP URL
	httpURL := p.cfg.HTTPURL()
	urlsContainer.Add(p.makeURLRow(httpURL))

	// Description
	desc := widget.NewLabel("Add this URL to your MCP client configuration")
	desc.Importance = widget.LowImportance
	urlsContainer.Add(desc)

	mcpSection := container.NewBorder(nil, nil, mcpLabel, nil, urlsContainer)

	// TastyTrade section
	tastyLabel := widget.NewLabelWithStyle("TastyTrade:", fyne.TextAlignLeading, fyne.TextStyle{Bold: true})

	// Status indicator - colored circle with fixed size, vertically centered
	p.statusIcon = canvas.NewCircle(theme.ErrorColor())
	p.statusIcon.StrokeWidth = 0
	iconSize := float32(10)
	p.statusIcon.Resize(fyne.NewSize(iconSize, iconSize))
	// Wrap in a center container to vertically align with text
	statusIconContainer := container.NewCenter(container.New(&fixedSizeLayout{width: iconSize, height: iconSize}, p.statusIcon))

	p.statusLabel = widget.NewLabel("Not Connected")

	p.connectBtn = widget.NewButton("Connect...", p.showLoginDialog)
	p.disconnectBtn = widget.NewButton("Disconnect", p.handleDisconnect)
	p.disconnectBtn.Hide()

	statusRow := container.NewHBox(
		statusIconContainer,
		p.statusLabel,
		layout.NewSpacer(),
		p.connectBtn,
		p.disconnectBtn,
	)

	tastySection := container.NewBorder(nil, nil, tastyLabel, nil, statusRow)

	// Main layout with proper spacing
	form := container.NewVBox(
		mcpSection,
		widget.NewSeparator(),
		tastySection,
	)

	p.content = container.NewPadded(container.NewPadded(form))
}

func (p *ConnectionPage) makeURLRow(urlStr string) fyne.CanvasObject {
	urlLabel := widget.NewLabel(urlStr)
	urlLabel.Wrapping = fyne.TextWrapOff

	copyBtn := widget.NewButton("Copy", nil)
	copyBtn.OnTapped = func() {
		p.window.Clipboard().SetContent(urlStr)
		copyBtn.SetText("Copied!")
		copyBtn.Disable()
		go func() {
			time.Sleep(1500 * time.Millisecond)
			copyBtn.SetText("Copy")
			copyBtn.Enable()
		}()
	}

	// Use Border layout: URL expands, button stays fixed on right
	return container.NewBorder(nil, nil, nil, copyBtn, urlLabel)
}

func (p *ConnectionPage) updateAuthView() {
	if p.state.IsAuthenticated() {
		p.statusIcon.FillColor = theme.SuccessColor()
		p.statusLabel.SetText("Connected")
		p.connectBtn.Hide()
		p.disconnectBtn.Show()
	} else {
		p.statusIcon.FillColor = theme.ErrorColor()
		p.statusLabel.SetText("Not Connected")
		p.connectBtn.Show()
		p.disconnectBtn.Hide()
	}
	p.statusIcon.Refresh()
}

func (p *ConnectionPage) showLoginDialog() {
	dlg := dialogs.NewLoginDialog(p.window, func(clientSecret, refreshToken string) {
		// Attempt login
		err := p.client.Login(clientSecret, refreshToken, true)
		if err != nil {
			log.Printf("Login failed: %v", err)
			return
		}
		p.state.SetAuthenticated(true)
	})
	dlg.Show()
}

func (p *ConnectionPage) handleDisconnect() {
	p.client.Logout(true)
	p.state.SetAuthenticated(false)
}

// CreateRenderer implements fyne.Widget.
func (p *ConnectionPage) CreateRenderer() fyne.WidgetRenderer {
	return widget.NewSimpleRenderer(p.content)
}

// fixedSizeLayout is a layout that gives all children a fixed size.
type fixedSizeLayout struct {
	width, height float32
}

func (l *fixedSizeLayout) MinSize(_ []fyne.CanvasObject) fyne.Size {
	return fyne.NewSize(l.width, l.height)
}

func (l *fixedSizeLayout) Layout(objects []fyne.CanvasObject, _ fyne.Size) {
	for _, o := range objects {
		o.Resize(fyne.NewSize(l.width, l.height))
		o.Move(fyne.NewPos(0, 0))
	}
}
