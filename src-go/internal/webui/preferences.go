// Package webui provides a web-based settings UI for the TTAI application.
package webui

import (
	"encoding/json"
	"log"
	"os"
	"path/filepath"
	"sync"
)

// Preferences holds user preferences stored in a JSON file.
type Preferences struct {
	ShowWindowOnLaunch bool `json:"open_settings_on_launch"`
	IsFirstRun         bool `json:"is_first_run"`
	AutoUpdateEnabled  bool `json:"auto_update_enabled"`
}

// PreferencesManager manages file-based preferences.
type PreferencesManager struct {
	path  string
	prefs Preferences
	mu    sync.RWMutex
}

// NewPreferencesManager creates a new preferences manager.
func NewPreferencesManager(dataDir string) *PreferencesManager {
	pm := &PreferencesManager{
		path: filepath.Join(dataDir, "preferences.json"),
		prefs: Preferences{
			ShowWindowOnLaunch: true,
			IsFirstRun:         true,
			AutoUpdateEnabled:  true,
		},
	}
	pm.load()
	return pm
}

// load reads preferences from disk.
func (pm *PreferencesManager) load() {
	pm.mu.Lock()
	defer pm.mu.Unlock()

	data, err := os.ReadFile(pm.path)
	if err != nil {
		if !os.IsNotExist(err) {
			log.Printf("Failed to read preferences: %v", err)
		}
		return
	}

	if err := json.Unmarshal(data, &pm.prefs); err != nil {
		log.Printf("Failed to parse preferences: %v", err)
	}
}

// save writes preferences to disk.
func (pm *PreferencesManager) save() error {
	// Ensure directory exists
	dir := filepath.Dir(pm.path)
	if err := os.MkdirAll(dir, 0755); err != nil {
		return err
	}

	data, err := json.MarshalIndent(pm.prefs, "", "  ")
	if err != nil {
		return err
	}

	return os.WriteFile(pm.path, data, 0644)
}

// ShowWindowOnLaunch returns whether to open browser on launch.
func (pm *PreferencesManager) ShowWindowOnLaunch() bool {
	pm.mu.RLock()
	defer pm.mu.RUnlock()
	return pm.prefs.ShowWindowOnLaunch
}

// SetShowWindowOnLaunch sets whether to open browser on launch.
func (pm *PreferencesManager) SetShowWindowOnLaunch(show bool) {
	pm.mu.Lock()
	pm.prefs.ShowWindowOnLaunch = show
	pm.mu.Unlock()

	if err := pm.save(); err != nil {
		log.Printf("Failed to save preferences: %v", err)
	}
}

// IsFirstRun returns whether this is the first run.
func (pm *PreferencesManager) IsFirstRun() bool {
	pm.mu.RLock()
	defer pm.mu.RUnlock()
	return pm.prefs.IsFirstRun
}

// SetFirstRunComplete marks the first run as complete.
func (pm *PreferencesManager) SetFirstRunComplete() {
	pm.mu.Lock()
	pm.prefs.IsFirstRun = false
	pm.mu.Unlock()

	if err := pm.save(); err != nil {
		log.Printf("Failed to save preferences: %v", err)
	}
}

// AutoUpdateEnabled returns whether auto-update is enabled.
func (pm *PreferencesManager) AutoUpdateEnabled() bool {
	pm.mu.RLock()
	defer pm.mu.RUnlock()
	return pm.prefs.AutoUpdateEnabled
}

// SetAutoUpdateEnabled sets whether auto-update is enabled.
func (pm *PreferencesManager) SetAutoUpdateEnabled(enabled bool) {
	pm.mu.Lock()
	pm.prefs.AutoUpdateEnabled = enabled
	pm.mu.Unlock()

	if err := pm.save(); err != nil {
		log.Printf("Failed to save preferences: %v", err)
	}
}

// GetAll returns all preferences.
func (pm *PreferencesManager) GetAll() Preferences {
	pm.mu.RLock()
	defer pm.mu.RUnlock()
	return pm.prefs
}

// Update applies partial updates to preferences.
func (pm *PreferencesManager) Update(updates map[string]interface{}) {
	pm.mu.Lock()
	defer pm.mu.Unlock()

	if v, ok := updates["open_settings_on_launch"].(bool); ok {
		pm.prefs.ShowWindowOnLaunch = v
	}
	if v, ok := updates["is_first_run"].(bool); ok {
		pm.prefs.IsFirstRun = v
	}
	if v, ok := updates["auto_update_enabled"].(bool); ok {
		pm.prefs.AutoUpdateEnabled = v
	}

	if err := pm.save(); err != nil {
		log.Printf("Failed to save preferences: %v", err)
	}
}
