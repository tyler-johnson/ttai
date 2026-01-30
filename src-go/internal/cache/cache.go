// Package cache provides a thread-safe in-memory cache with TTL support.
package cache

import (
	"sync"
	"time"
)

// Entry represents a cached value with optional expiration.
type Entry struct {
	Value     interface{}
	ExpiresAt *time.Time // nil means no expiration
}

// Cache is a thread-safe in-memory cache with TTL support.
type Cache struct {
	mu    sync.RWMutex
	items map[string]Entry
}

// New creates a new cache instance.
func New() *Cache {
	return &Cache{
		items: make(map[string]Entry),
	}
}

// Get retrieves a value from the cache.
// Returns nil if not found or expired.
func (c *Cache) Get(key string) interface{} {
	c.mu.RLock()
	entry, ok := c.items[key]
	c.mu.RUnlock()

	if !ok {
		return nil
	}

	// Check expiration
	if entry.ExpiresAt != nil && time.Now().After(*entry.ExpiresAt) {
		c.Delete(key)
		return nil
	}

	return entry.Value
}

// Set stores a value in the cache with an optional TTL.
// If ttl is 0 or negative, the value never expires.
func (c *Cache) Set(key string, value interface{}, ttl time.Duration) {
	c.mu.Lock()
	defer c.mu.Unlock()

	entry := Entry{Value: value}
	if ttl > 0 {
		expiresAt := time.Now().Add(ttl)
		entry.ExpiresAt = &expiresAt
	}

	c.items[key] = entry
}

// Delete removes a value from the cache.
// Returns true if the key was deleted, false if not found.
func (c *Cache) Delete(key string) bool {
	c.mu.Lock()
	defer c.mu.Unlock()

	if _, ok := c.items[key]; ok {
		delete(c.items, key)
		return true
	}
	return false
}

// Clear removes all values from the cache.
func (c *Cache) Clear() {
	c.mu.Lock()
	defer c.mu.Unlock()
	c.items = make(map[string]Entry)
}

// CleanupExpired removes all expired entries from the cache.
// Returns the number of entries removed.
func (c *Cache) CleanupExpired() int {
	c.mu.Lock()
	defer c.mu.Unlock()

	now := time.Now()
	count := 0

	for key, entry := range c.items {
		if entry.ExpiresAt != nil && now.After(*entry.ExpiresAt) {
			delete(c.items, key)
			count++
		}
	}

	return count
}
