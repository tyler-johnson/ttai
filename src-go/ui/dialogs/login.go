// Package dialogs provides dialog windows for the TTAI application.
package dialogs

import (
	"net/url"

	"fyne.io/fyne/v2"
	"fyne.io/fyne/v2/container"
	"fyne.io/fyne/v2/dialog"
	"fyne.io/fyne/v2/layout"
	"fyne.io/fyne/v2/widget"
)

// TastyTradeAPIURL is the URL for getting API credentials.
const TastyTradeAPIURL = "https://my.tastytrade.com/app.html#/manage/api-access"

// LoginDialog is a dialog for TastyTrade login credentials.
type LoginDialog struct {
	window            fyne.Window
	onConnect         func(clientSecret, refreshToken string)
	clientSecretEntry *widget.Entry
	refreshTokenEntry *widget.Entry
	errorLabel        *widget.Label
	getCredsBtn       *widget.Button
	dlg               dialog.Dialog
}

// NewLoginDialog creates a new login dialog.
func NewLoginDialog(parent fyne.Window, onConnect func(clientSecret, refreshToken string)) *LoginDialog {
	d := &LoginDialog{
		window:    parent,
		onConnect: onConnect,
	}
	d.buildUI()
	return d
}

func (d *LoginDialog) buildUI() {
	// Instructions
	instructions := widget.NewLabel("Enter your TastyTrade API credentials:")

	// Client Secret - use form item for proper layout
	d.clientSecretEntry = widget.NewPasswordEntry()
	d.clientSecretEntry.SetPlaceHolder("Enter client secret")

	// Refresh Token
	d.refreshTokenEntry = widget.NewPasswordEntry()
	d.refreshTokenEntry.SetPlaceHolder("Enter refresh token")

	// Create a form for proper alignment
	form := widget.NewForm(
		widget.NewFormItem("Client Secret", d.clientSecretEntry),
		widget.NewFormItem("Refresh Token", d.refreshTokenEntry),
	)

	// Error label
	d.errorLabel = widget.NewLabel("")
	d.errorLabel.Importance = widget.DangerImportance
	d.errorLabel.Hide()

	// Get Credentials button
	d.getCredsBtn = widget.NewButton("Get Credentials...", func() {
		// Open browser to TastyTrade API page
		u, _ := url.Parse(TastyTradeAPIURL)
		fyne.CurrentApp().OpenURL(u)
	})

	// Spacer to enforce minimum width (~450px worth of content)
	// Using a label with spaces as a width hint
	widthSpacer := layout.NewSpacer()

	// Form content with proper spacing
	formContent := container.NewVBox(
		instructions,
		form,
		d.errorLabel,
		container.NewHBox(d.getCredsBtn, widthSpacer),
	)

	// Wrap in a container with minimum size
	// Fyne dialogs size to content, so we add padding and structure
	paddedContent := container.NewPadded(formContent)

	// Create dialog with custom content
	d.dlg = dialog.NewCustomConfirm(
		"Connect to TastyTrade",
		"Connect",
		"Cancel",
		paddedContent,
		func(confirmed bool) {
			if confirmed {
				d.handleConnect()
			}
		},
		d.window,
	)

	// Resize dialog to a reasonable minimum
	d.dlg.Resize(fyne.NewSize(450, 250))
}

func (d *LoginDialog) handleConnect() {
	clientSecret := d.clientSecretEntry.Text
	refreshToken := d.refreshTokenEntry.Text

	if clientSecret == "" || refreshToken == "" {
		d.SetError("Please enter both client secret and refresh token")
		d.dlg.Show() // Re-show the dialog
		return
	}

	d.SetError("")
	d.onConnect(clientSecret, refreshToken)
}

// Show displays the login dialog.
func (d *LoginDialog) Show() {
	d.Clear()
	d.dlg.Show()
}

// Hide closes the login dialog.
func (d *LoginDialog) Hide() {
	d.dlg.Hide()
}

// SetError displays an error message.
func (d *LoginDialog) SetError(message string) {
	if message == "" {
		d.errorLabel.Hide()
	} else {
		d.errorLabel.SetText(message)
		d.errorLabel.Show()
	}
}

// SetLoading sets the loading state.
func (d *LoginDialog) SetLoading(loading bool) {
	if loading {
		d.clientSecretEntry.Disable()
		d.refreshTokenEntry.Disable()
		d.getCredsBtn.Disable()
	} else {
		d.clientSecretEntry.Enable()
		d.refreshTokenEntry.Enable()
		d.getCredsBtn.Enable()
	}
}

// Clear resets the form.
func (d *LoginDialog) Clear() {
	d.clientSecretEntry.SetText("")
	d.refreshTokenEntry.SetText("")
	d.errorLabel.Hide()
}
