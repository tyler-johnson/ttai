package update

import (
	"context"
	"log"
	"sync"
	"time"
)

const (
	// StartupDelay is the delay before the first update check.
	StartupDelay = 30 * time.Second
	// CheckInterval is the interval between update checks.
	CheckInterval = 24 * time.Hour
)

// Manager coordinates update checking and application.
type Manager struct {
	currentVersion string
	state          *State
	updater        Updater
	autoCheck      func() bool // Function to check if auto-update is enabled

	mu       sync.Mutex
	ctx      context.Context
	cancel   context.CancelFunc
	running  bool
	stopChan chan struct{}
}

// NewManager creates a new update manager.
func NewManager(currentVersion string, autoCheckEnabled func() bool) *Manager {
	return &Manager{
		currentVersion: currentVersion,
		state:          NewState(),
		autoCheck:      autoCheckEnabled,
	}
}

// State returns the update state.
func (m *Manager) State() *State {
	return m.state
}

// SetUpdater sets the platform-specific updater.
func (m *Manager) SetUpdater(updater Updater) {
	m.mu.Lock()
	defer m.mu.Unlock()
	m.updater = updater
}

// Start begins periodic update checking.
func (m *Manager) Start() {
	m.mu.Lock()
	defer m.mu.Unlock()

	if m.running {
		return
	}

	m.ctx, m.cancel = context.WithCancel(context.Background())
	m.stopChan = make(chan struct{})
	m.running = true

	go m.run()
}

// Stop stops periodic update checking.
func (m *Manager) Stop() {
	m.mu.Lock()
	defer m.mu.Unlock()

	if !m.running {
		return
	}

	m.cancel()
	close(m.stopChan)
	m.running = false
}

// run is the main loop for periodic update checking.
func (m *Manager) run() {
	// Initial delay before first check
	select {
	case <-time.After(StartupDelay):
	case <-m.stopChan:
		return
	}

	// Do initial check if auto-update is enabled
	if m.autoCheck() {
		m.CheckForUpdates()
	}

	// Periodic checks
	ticker := time.NewTicker(CheckInterval)
	defer ticker.Stop()

	for {
		select {
		case <-ticker.C:
			if m.autoCheck() {
				m.CheckForUpdates()
			}
		case <-m.stopChan:
			return
		}
	}
}

// CheckForUpdates manually triggers an update check.
func (m *Manager) CheckForUpdates() {
	m.mu.Lock()
	updater := m.updater
	ctx := m.ctx
	m.mu.Unlock()

	if updater == nil {
		log.Println("Update: No updater configured")
		return
	}

	if ctx == nil {
		ctx = context.Background()
	}

	m.state.SetStatus(StatusChecking)
	log.Println("Update: Checking for updates...")

	info, err := updater.CheckForUpdates(ctx)
	if err != nil {
		log.Printf("Update: Check failed: %v", err)
		m.state.SetError(err.Error())
		return
	}

	if info == nil {
		log.Println("Update: No updates available")
		m.state.Clear()
		return
	}

	// Compare versions
	if CompareVersions(info.Version, m.currentVersion) <= 0 {
		log.Printf("Update: Current version %s is up to date (latest: %s)", m.currentVersion, info.Version)
		m.state.Clear()
		return
	}

	log.Printf("Update: New version available: %s (current: %s)", info.Version, m.currentVersion)
	m.state.SetUpdateInfo(info)
}

// DownloadUpdate downloads the available update.
func (m *Manager) DownloadUpdate() error {
	m.mu.Lock()
	updater := m.updater
	ctx := m.ctx
	m.mu.Unlock()

	if updater == nil {
		return nil
	}

	if ctx == nil {
		ctx = context.Background()
	}

	m.state.SetStatus(StatusDownloading)
	log.Println("Update: Downloading update...")

	if err := updater.DownloadUpdate(ctx); err != nil {
		log.Printf("Update: Download failed: %v", err)
		m.state.SetError(err.Error())
		return err
	}

	log.Println("Update: Download complete")
	m.state.SetReady()
	return nil
}

// ApplyUpdate applies the downloaded update.
func (m *Manager) ApplyUpdate() error {
	m.mu.Lock()
	updater := m.updater
	m.mu.Unlock()

	if updater == nil {
		return nil
	}

	log.Println("Update: Applying update...")
	return updater.ApplyUpdate()
}

// GetCurrentVersion returns the current application version.
func (m *Manager) GetCurrentVersion() string {
	return m.currentVersion
}
