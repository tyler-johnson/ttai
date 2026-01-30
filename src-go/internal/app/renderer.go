package app

import (
	"log"
	"os"
	"runtime"
)

// ConfigureRenderer sets up the appropriate renderer for the platform.
// On Windows, it detects if OpenGL is likely unavailable (VM, RDP) and
// falls back to software rendering.
func ConfigureRenderer() {
	// Skip if user explicitly set a renderer
	if os.Getenv("FYNE_RENDERER") != "" {
		return
	}

	// Only need special handling on Windows
	if runtime.GOOS != "windows" {
		return
	}

	// Check if we're in an environment where OpenGL typically doesn't work
	if isRemoteDesktop() || isVirtualMachine() {
		log.Println("Detected VM or Remote Desktop - using software rendering")
		os.Setenv("FYNE_RENDERER", "software")
	}
}

// isRemoteDesktop checks if running in a Windows Remote Desktop session
func isRemoteDesktop() bool {
	// Check for RDP session environment variable
	if os.Getenv("SESSIONNAME") != "" && os.Getenv("SESSIONNAME") != "Console" {
		return true
	}
	return false
}

// isVirtualMachine tries to detect if running in a VM
func isVirtualMachine() bool {
	// Check common VM-related environment variables and indicators
	// This is a heuristic and won't catch all VMs

	// Check for common VM vendor strings in COMPUTERNAME or other env vars
	vmIndicators := []string{
		"VBOX",
		"VIRTUALBOX",
		"VMWARE",
		"HYPERV",
		"QEMU",
		"XEN",
	}

	computerName := os.Getenv("COMPUTERNAME")
	for _, indicator := range vmIndicators {
		if containsIgnoreCase(computerName, indicator) {
			return true
		}
	}

	// Check if running under WSL (Windows Subsystem for Linux)
	if os.Getenv("WSL_DISTRO_NAME") != "" {
		return true
	}

	return false
}

func containsIgnoreCase(s, substr string) bool {
	if len(s) < len(substr) {
		return false
	}
	// Simple case-insensitive contains check
	sLower := make([]byte, len(s))
	substrLower := make([]byte, len(substr))
	for i := 0; i < len(s); i++ {
		if s[i] >= 'A' && s[i] <= 'Z' {
			sLower[i] = s[i] + 32
		} else {
			sLower[i] = s[i]
		}
	}
	for i := 0; i < len(substr); i++ {
		if substr[i] >= 'A' && substr[i] <= 'Z' {
			substrLower[i] = substr[i] + 32
		} else {
			substrLower[i] = substr[i]
		}
	}
	return containsBytes(sLower, substrLower)
}

func containsBytes(s, substr []byte) bool {
	for i := 0; i <= len(s)-len(substr); i++ {
		match := true
		for j := 0; j < len(substr); j++ {
			if s[i+j] != substr[j] {
				match = false
				break
			}
		}
		if match {
			return true
		}
	}
	return false
}
