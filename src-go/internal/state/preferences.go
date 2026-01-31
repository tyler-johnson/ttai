package state

import (
	"log"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
)

// --- Launch at Startup ---

// IsLaunchAtStartupEnabled checks if launch at startup is enabled.
func IsLaunchAtStartupEnabled() bool {
	switch runtime.GOOS {
	case "darwin":
		return isLaunchAtStartupMacOS()
	case "windows":
		return isLaunchAtStartupWindows()
	case "linux":
		return isLaunchAtStartupLinux()
	default:
		return false
	}
}

// SetLaunchAtStartup enables or disables launch at startup.
func SetLaunchAtStartup(enabled bool) bool {
	switch runtime.GOOS {
	case "darwin":
		return setLaunchAtStartupMacOS(enabled)
	case "windows":
		return setLaunchAtStartupWindows(enabled)
	case "linux":
		return setLaunchAtStartupLinux(enabled)
	default:
		log.Printf("Launch at startup not supported on %s", runtime.GOOS)
		return false
	}
}

// IsPlatformSupported returns whether launch at startup is supported on this platform.
func IsPlatformSupported() bool {
	return runtime.GOOS == "darwin" || runtime.GOOS == "windows" || runtime.GOOS == "linux"
}

// --- macOS ---

func getMacOSLaunchAgentPath() string {
	homeDir, _ := os.UserHomeDir()
	return filepath.Join(homeDir, "Library", "LaunchAgents", "dev.tt-ai.ttai.plist")
}

func isLaunchAtStartupMacOS() bool {
	// Use SMAppService on macOS 13+
	if isSMAppServiceAvailable() {
		status := getSMAppServiceStatus()
		// Consider enabled if status is enabled or requires approval (user hasn't approved yet but we registered)
		return status == SMAppServiceStatusEnabled || status == SMAppServiceStatusRequiresApproval
	}

	// Fall back to LaunchAgent for macOS 11-12
	return isLaunchAtStartupMacOSLegacy()
}

func isLaunchAtStartupMacOSLegacy() bool {
	_, err := os.Stat(getMacOSLaunchAgentPath())
	return err == nil
}

// getAppBundlePath returns the .app bundle path if running from one, or empty string otherwise.
// For example, if running from /Applications/TTAI.app/Contents/MacOS/ttai,
// this returns /Applications/TTAI.app
func getAppBundlePath() string {
	exePath, err := os.Executable()
	if err != nil {
		return ""
	}

	// Check if we're inside a .app bundle: .../Something.app/Contents/MacOS/binary
	dir := filepath.Dir(exePath) // MacOS
	if filepath.Base(dir) != "MacOS" {
		return ""
	}
	dir = filepath.Dir(dir) // Contents
	if filepath.Base(dir) != "Contents" {
		return ""
	}
	appDir := filepath.Dir(dir) // Something.app
	if filepath.Ext(appDir) != ".app" {
		return ""
	}

	return appDir
}

func setLaunchAtStartupMacOS(enabled bool) bool {
	// Use SMAppService on macOS 13+
	if isSMAppServiceAvailable() {
		if enabled {
			return registerWithSMAppService()
		}
		return unregisterWithSMAppService()
	}

	// Fall back to LaunchAgent for macOS 11-12
	return setLaunchAtStartupMacOSLegacy(enabled)
}

func setLaunchAtStartupMacOSLegacy(enabled bool) bool {
	plistPath := getMacOSLaunchAgentPath()

	if enabled {
		// Prefer .app bundle path if available, otherwise use executable path
		launchPath := getAppBundlePath()
		useOpen := launchPath != ""

		if launchPath == "" {
			var err error
			launchPath, err = os.Executable()
			if err != nil {
				log.Printf("Failed to get executable path: %v", err)
				return false
			}
		}

		// Ensure directory exists
		dir := filepath.Dir(plistPath)
		if err := os.MkdirAll(dir, 0755); err != nil {
			log.Printf("Failed to create LaunchAgents directory: %v", err)
			return false
		}

		var plistContent string
		if useOpen {
			// Use 'open' command to launch .app bundle - this shows proper app name in Login Items
			plistContent = `<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>dev.tt-ai.ttai</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/bin/open</string>
        <string>` + launchPath + `</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
</dict>
</plist>
`
		} else {
			// Direct binary execution
			plistContent = `<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>dev.tt-ai.ttai</string>
    <key>ProgramArguments</key>
    <array>
        <string>` + launchPath + `</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
</dict>
</plist>
`
		}
		if err := os.WriteFile(plistPath, []byte(plistContent), 0644); err != nil {
			log.Printf("Failed to write launch agent: %v", err)
			return false
		}
		log.Printf("Created launch agent at %s (launching: %s)", plistPath, launchPath)
		return true
	} else {
		if err := os.Remove(plistPath); err != nil && !os.IsNotExist(err) {
			log.Printf("Failed to remove launch agent: %v", err)
			return false
		}
		log.Printf("Removed launch agent at %s", plistPath)
		return true
	}
}

// --- Windows ---

func isLaunchAtStartupWindows() bool {
	// Use reg query to check if the key exists
	cmd := exec.Command("reg", "query", `HKCU\Software\Microsoft\Windows\CurrentVersion\Run`, "/v", "TTAI")
	err := cmd.Run()
	return err == nil
}

func setLaunchAtStartupWindows(enabled bool) bool {
	if enabled {
		exePath, err := os.Executable()
		if err != nil {
			log.Printf("Failed to get executable path: %v", err)
			return false
		}

		cmd := exec.Command("reg", "add", `HKCU\Software\Microsoft\Windows\CurrentVersion\Run`,
			"/v", "TTAI", "/t", "REG_SZ", "/d", `"`+exePath+`"`, "/f")
		if err := cmd.Run(); err != nil {
			log.Printf("Failed to add registry key: %v", err)
			return false
		}
		log.Println("Added TTAI to Windows startup registry")
		return true
	} else {
		cmd := exec.Command("reg", "delete", `HKCU\Software\Microsoft\Windows\CurrentVersion\Run`,
			"/v", "TTAI", "/f")
		if err := cmd.Run(); err != nil {
			log.Printf("Failed to remove registry key: %v", err)
			return false
		}
		log.Println("Removed TTAI from Windows startup registry")
		return true
	}
}

// --- Linux ---

func getLinuxAutostartPath() string {
	homeDir, _ := os.UserHomeDir()
	return filepath.Join(homeDir, ".config", "autostart", "ttai.desktop")
}

func isLaunchAtStartupLinux() bool {
	_, err := os.Stat(getLinuxAutostartPath())
	return err == nil
}

func setLaunchAtStartupLinux(enabled bool) bool {
	desktopPath := getLinuxAutostartPath()

	if enabled {
		exePath, err := os.Executable()
		if err != nil {
			log.Printf("Failed to get executable path: %v", err)
			return false
		}

		// Ensure directory exists
		dir := filepath.Dir(desktopPath)
		if err := os.MkdirAll(dir, 0755); err != nil {
			log.Printf("Failed to create autostart directory: %v", err)
			return false
		}

		desktopContent := `[Desktop Entry]
Type=Application
Name=TTAI
Comment=TastyTrade AI Assistant
Exec=` + exePath + `
Hidden=false
NoDisplay=false
X-GNOME-Autostart-enabled=true
`
		if err := os.WriteFile(desktopPath, []byte(desktopContent), 0644); err != nil {
			log.Printf("Failed to write autostart entry: %v", err)
			return false
		}
		log.Printf("Created autostart entry at %s", desktopPath)
		return true
	} else {
		if err := os.Remove(desktopPath); err != nil && !os.IsNotExist(err) {
			log.Printf("Failed to remove autostart entry: %v", err)
			return false
		}
		log.Printf("Removed autostart entry at %s", desktopPath)
		return true
	}
}
