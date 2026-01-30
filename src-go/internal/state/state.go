// Package state provides application state management.
package state

import "sync"

// AppState holds the application state with thread-safe access.
type AppState struct {
	mu            sync.RWMutex
	authenticated bool
	listeners     []func(authenticated bool)
}

// New creates a new application state.
func New() *AppState {
	return &AppState{
		listeners: make([]func(authenticated bool), 0),
	}
}

// IsAuthenticated returns the current authentication state.
func (s *AppState) IsAuthenticated() bool {
	s.mu.RLock()
	defer s.mu.RUnlock()
	return s.authenticated
}

// SetAuthenticated updates the authentication state and notifies listeners.
func (s *AppState) SetAuthenticated(authenticated bool) {
	s.mu.Lock()
	s.authenticated = authenticated
	listeners := make([]func(bool), len(s.listeners))
	copy(listeners, s.listeners)
	s.mu.Unlock()

	// Notify listeners outside the lock
	for _, listener := range listeners {
		listener(authenticated)
	}
}

// OnAuthChanged registers a callback for authentication state changes.
func (s *AppState) OnAuthChanged(callback func(authenticated bool)) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.listeners = append(s.listeners, callback)
}
