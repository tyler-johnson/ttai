//go:build darwin

package state

/*
#cgo CFLAGS: -x objective-c
#cgo LDFLAGS: -framework ServiceManagement -framework Foundation

#import <Foundation/Foundation.h>
#import <ServiceManagement/ServiceManagement.h>

// Check if SMAppService is available (macOS 13+)
static bool smappservice_available() {
    if (@available(macOS 13.0, *)) {
        return true;
    }
    return false;
}

// Register as login item using SMAppService
static bool smappservice_register() {
    if (@available(macOS 13.0, *)) {
        SMAppService *service = [SMAppService mainAppService];
        NSError *error = nil;
        BOOL success = [service registerAndReturnError:&error];
        if (!success && error) {
            NSLog(@"SMAppService register error: %@", error);
        }
        return success;
    }
    return false;
}

// Unregister as login item using SMAppService
static bool smappservice_unregister() {
    if (@available(macOS 13.0, *)) {
        SMAppService *service = [SMAppService mainAppService];
        NSError *error = nil;
        BOOL success = [service unregisterAndReturnError:&error];
        if (!success && error) {
            NSLog(@"SMAppService unregister error: %@", error);
        }
        return success;
    }
    return false;
}

// Get SMAppService status
// Returns: 0=notRegistered, 1=enabled, 2=requiresApproval, 3=notFound, -1=unavailable
static int smappservice_status() {
    if (@available(macOS 13.0, *)) {
        SMAppService *service = [SMAppService mainAppService];
        return (int)[service status];
    }
    return -1;
}
*/
import "C"

import "log"

// SMAppService status constants
const (
	SMAppServiceStatusNotRegistered    = 0
	SMAppServiceStatusEnabled          = 1
	SMAppServiceStatusRequiresApproval = 2
	SMAppServiceStatusNotFound         = 3
	SMAppServiceStatusUnavailable      = -1
)

// isSMAppServiceAvailable returns true if SMAppService is available (macOS 13+)
func isSMAppServiceAvailable() bool {
	return bool(C.smappservice_available())
}

// registerWithSMAppService registers the app as a login item using SMAppService
func registerWithSMAppService() bool {
	success := bool(C.smappservice_register())
	if success {
		log.Println("macOS: Registered with SMAppService")
	} else {
		status := getSMAppServiceStatus()
		if status == SMAppServiceStatusRequiresApproval {
			log.Println("macOS: SMAppService registration requires user approval in System Settings")
		} else {
			log.Printf("macOS: Failed to register with SMAppService (status: %d)", status)
		}
	}
	return success
}

// unregisterWithSMAppService unregisters the app as a login item using SMAppService
func unregisterWithSMAppService() bool {
	success := bool(C.smappservice_unregister())
	if success {
		log.Println("macOS: Unregistered from SMAppService")
	} else {
		log.Println("macOS: Failed to unregister from SMAppService")
	}
	return success
}

// getSMAppServiceStatus returns the current SMAppService status
func getSMAppServiceStatus() int {
	return int(C.smappservice_status())
}
