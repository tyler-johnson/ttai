//go:build darwin

package ui

/*
#cgo CFLAGS: -x objective-c
#cgo LDFLAGS: -framework Cocoa
#import <Cocoa/Cocoa.h>

static inline void ttaiHideFromDock() {
    [NSApp setActivationPolicy:NSApplicationActivationPolicyAccessory];
}

static inline void ttaiShowInDock() {
    [NSApp setActivationPolicy:NSApplicationActivationPolicyRegular];
}
*/
import "C"

import "log"

// HideFromDock hides the application from the macOS Dock.
// This makes the app a "menu bar only" app that doesn't appear in the Dock or Cmd+Tab.
func HideFromDock() {
	C.ttaiHideFromDock()
	log.Println("macOS: Hidden from dock")
}

// ShowInDock shows the application in the macOS Dock.
func ShowInDock() {
	C.ttaiShowInDock()
	log.Println("macOS: Shown in dock")
}
