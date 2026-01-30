package pages

import (
	"fyne.io/fyne/v2"
	"fyne.io/fyne/v2/canvas"
	"fyne.io/fyne/v2/container"
	"fyne.io/fyne/v2/widget"
)

// Version is the application version.
const Version = "1.0.0"

// AboutPage displays information about the application.
type AboutPage struct {
	widget.BaseWidget

	content fyne.CanvasObject
}

// NewAboutPage creates a new about page.
func NewAboutPage(icon fyne.Resource) *AboutPage {
	p := &AboutPage{}
	p.ExtendBaseWidget(p)
	p.buildUI(icon)
	return p
}

func (p *AboutPage) buildUI(icon fyne.Resource) {
	var iconWidget fyne.CanvasObject
	if icon != nil {
		img := canvas.NewImageFromResource(icon)
		img.SetMinSize(fyne.NewSize(96, 96))
		img.FillMode = canvas.ImageFillContain
		iconWidget = img
	}

	// App name - larger font
	title := widget.NewRichTextFromMarkdown("# TTAI")
	title.Wrapping = fyne.TextWrapOff

	// Subtitle
	subtitle := widget.NewLabel("TastyTrade AI Assistant")
	subtitle.Alignment = fyne.TextAlignCenter

	// Version
	version := widget.NewLabel("Version " + Version)
	version.Alignment = fyne.TextAlignCenter
	version.Importance = widget.LowImportance

	// Description - single line to avoid wrapping
	desc1 := widget.NewLabel("AI-powered trading analysis using the TastyTrade API.")
	desc1.Alignment = fyne.TextAlignCenter
	desc2 := widget.NewLabel("Connect via MCP for intelligent insights.")
	desc2.Alignment = fyne.TextAlignCenter

	// Build content column
	contentItems := []fyne.CanvasObject{}

	if iconWidget != nil {
		contentItems = append(contentItems, container.NewCenter(iconWidget))
		contentItems = append(contentItems, widget.NewSeparator())
	}

	contentItems = append(contentItems,
		container.NewCenter(title),
		container.NewCenter(subtitle),
		widget.NewSeparator(),
		container.NewCenter(version),
		widget.NewSeparator(),
		container.NewCenter(desc1),
		container.NewCenter(desc2),
	)

	content := container.NewVBox(contentItems...)

	// Wrap in padded container that fills available space
	p.content = container.NewPadded(container.NewCenter(content))
}

// CreateRenderer implements fyne.Widget.
func (p *AboutPage) CreateRenderer() fyne.WidgetRenderer {
	return widget.NewSimpleRenderer(p.content)
}
