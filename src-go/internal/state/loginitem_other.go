//go:build !darwin

package state

// SMAppService status constants (for API compatibility)
const (
	SMAppServiceStatusNotRegistered    = 0
	SMAppServiceStatusEnabled          = 1
	SMAppServiceStatusRequiresApproval = 2
	SMAppServiceStatusNotFound         = 3
	SMAppServiceStatusUnavailable      = -1
)

// isSMAppServiceAvailable returns false on non-Darwin platforms
func isSMAppServiceAvailable() bool {
	return false
}

// registerWithSMAppService is a no-op on non-Darwin platforms
func registerWithSMAppService() bool {
	return false
}

// unregisterWithSMAppService is a no-op on non-Darwin platforms
func unregisterWithSMAppService() bool {
	return false
}

// getSMAppServiceStatus returns unavailable on non-Darwin platforms
func getSMAppServiceStatus() int {
	return SMAppServiceStatusUnavailable
}
