//go:build !darwin

package ui

// HideFromDock is a no-op on non-macOS platforms.
func HideFromDock() {}

// ShowInDock is a no-op on non-macOS platforms.
func ShowInDock() {}
