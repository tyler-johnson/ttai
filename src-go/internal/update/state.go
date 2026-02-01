package update

import "sync"

// Status represents the current update status.
type Status string

const (
	// StatusIdle means no update activity.
	StatusIdle Status = "idle"
	// StatusChecking means currently checking for updates.
	StatusChecking Status = "checking"
	// StatusAvailable means an update is available.
	StatusAvailable Status = "available"
	// StatusDownloading means an update is being downloaded.
	StatusDownloading Status = "downloading"
	// StatusReady means an update is downloaded and ready to install.
	StatusReady Status = "ready"
	// StatusError means an error occurred.
	StatusError Status = "error"
)

// State holds the update state with thread-safe access.
type State struct {
	mu         sync.RWMutex
	status     Status
	updateInfo *UpdateInfo
	error      string
	listeners  []func(State)
}

// NewState creates a new update state.
func NewState() *State {
	return &State{
		status:    StatusIdle,
		listeners: make([]func(State), 0),
	}
}

// GetStatus returns the current update status.
func (s *State) GetStatus() Status {
	s.mu.RLock()
	defer s.mu.RUnlock()
	return s.status
}

// GetUpdateInfo returns the current update info.
func (s *State) GetUpdateInfo() *UpdateInfo {
	s.mu.RLock()
	defer s.mu.RUnlock()
	if s.updateInfo == nil {
		return nil
	}
	// Return a copy to prevent external modification
	info := *s.updateInfo
	return &info
}

// GetError returns the current error message.
func (s *State) GetError() string {
	s.mu.RLock()
	defer s.mu.RUnlock()
	return s.error
}

// SetStatus updates the status and notifies listeners.
func (s *State) SetStatus(status Status) {
	s.mu.Lock()
	s.status = status
	s.mu.Unlock()
	s.notifyListeners()
}

// SetUpdateInfo sets the update info and status.
func (s *State) SetUpdateInfo(info *UpdateInfo) {
	s.mu.Lock()
	s.updateInfo = info
	if info != nil {
		s.status = StatusAvailable
		s.error = ""
	} else {
		s.status = StatusIdle
	}
	s.mu.Unlock()
	s.notifyListeners()
}

// SetReady marks the update as downloaded and ready to install.
func (s *State) SetReady() {
	s.mu.Lock()
	if s.updateInfo != nil {
		s.updateInfo.IsDownloaded = true
	}
	s.status = StatusReady
	s.error = ""
	s.mu.Unlock()
	s.notifyListeners()
}

// SetError sets an error state.
func (s *State) SetError(err string) {
	s.mu.Lock()
	s.status = StatusError
	s.error = err
	s.mu.Unlock()
	s.notifyListeners()
}

// Clear resets the state.
func (s *State) Clear() {
	s.mu.Lock()
	s.status = StatusIdle
	s.updateInfo = nil
	s.error = ""
	s.mu.Unlock()
	s.notifyListeners()
}

// Snapshot returns a snapshot of the current state.
func (s *State) Snapshot() StateSnapshot {
	s.mu.RLock()
	defer s.mu.RUnlock()

	snap := StateSnapshot{
		Status: s.status,
		Error:  s.error,
	}
	if s.updateInfo != nil {
		info := *s.updateInfo
		snap.UpdateInfo = &info
	}
	return snap
}

// StateSnapshot is an immutable snapshot of the update state.
type StateSnapshot struct {
	Status     Status      `json:"status"`
	UpdateInfo *UpdateInfo `json:"update_info,omitempty"`
	Error      string      `json:"error,omitempty"`
}

// OnChange registers a callback for state changes.
func (s *State) OnChange(callback func(State)) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.listeners = append(s.listeners, callback)
}

// notifyListeners notifies all registered listeners of a state change.
func (s *State) notifyListeners() {
	s.mu.RLock()
	listeners := make([]func(State), len(s.listeners))
	copy(listeners, s.listeners)
	s.mu.RUnlock()

	for _, listener := range listeners {
		listener(*s)
	}
}
