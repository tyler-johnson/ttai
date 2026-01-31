# TTAI Go Build Makefile

# Use bash for cross-platform compatibility (available via Git for Windows on Windows)
SHELL := bash

APP_NAME := ttai
DISPLAY_NAME := TTAI
VERSION := 1.0.0
BUNDLE_ID := dev.tt-ai.ttai
BUILD_FLAGS := -ldflags="-s -w -X main.Version=$(VERSION)"

# Directories
DIST_DIR := dist
RESOURCES_DIR := resources

# Code signing identity (set via environment or CLI)
# Example: CODESIGN_IDENTITY="Developer ID Application: Your Name (TEAMID)"
CODESIGN_IDENTITY ?=
ENTITLEMENTS := $(RESOURCES_DIR)/entitlements.plist
WEB_DIR := ../src-web
WEBUI_DIST := internal/webui/dist

# Default target
all: build

# Build web assets (SvelteKit)
web:
	@echo "Building web UI..."
	cd $(WEB_DIR) && npm install && npm run build
	rm -rf $(WEBUI_DIST)
	cp -r $(WEB_DIR)/build $(WEBUI_DIST)
	@echo "Web UI built successfully"

# Development build (current platform)
build: web
	go build $(BUILD_FLAGS) -o $(APP_NAME) .

# Build for all platforms
build-all: build-darwin build-windows build-linux

# =============================================================================
# macOS Builds
# =============================================================================

build-darwin: build-darwin-arm64 build-darwin-amd64

build-darwin-arm64: web
	GOOS=darwin GOARCH=arm64 CGO_ENABLED=1 go build $(BUILD_FLAGS) -o $(DIST_DIR)/$(APP_NAME)-darwin-arm64 .

build-darwin-amd64: web
	GOOS=darwin GOARCH=amd64 CGO_ENABLED=1 go build $(BUILD_FLAGS) -o $(DIST_DIR)/$(APP_NAME)-darwin-amd64 .

# Create macOS .app bundle
# Usage: make bundle-darwin-arm64 or make bundle-darwin-amd64
bundle-darwin-arm64: build-darwin-arm64
	$(call create-app-bundle,darwin-arm64,arm64)

bundle-darwin-amd64: build-darwin-amd64
	$(call create-app-bundle,darwin-amd64,x86_64)

bundle-darwin: bundle-darwin-arm64 bundle-darwin-amd64

# Function to create macOS app bundle
define create-app-bundle
	@echo "Creating $(DISPLAY_NAME).app bundle for $(1)..."
	@mkdir -p $(DIST_DIR)/$(DISPLAY_NAME)-$(1).app/Contents/MacOS
	@mkdir -p $(DIST_DIR)/$(DISPLAY_NAME)-$(1).app/Contents/Resources
	@cp $(DIST_DIR)/$(APP_NAME)-$(1) $(DIST_DIR)/$(DISPLAY_NAME)-$(1).app/Contents/MacOS/$(APP_NAME)
	@cp $(RESOURCES_DIR)/icon.png $(DIST_DIR)/$(DISPLAY_NAME)-$(1).app/Contents/Resources/icon.png
	@echo '<?xml version="1.0" encoding="UTF-8"?>' > $(DIST_DIR)/$(DISPLAY_NAME)-$(1).app/Contents/Info.plist
	@echo '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">' >> $(DIST_DIR)/$(DISPLAY_NAME)-$(1).app/Contents/Info.plist
	@echo '<plist version="1.0">' >> $(DIST_DIR)/$(DISPLAY_NAME)-$(1).app/Contents/Info.plist
	@echo '<dict>' >> $(DIST_DIR)/$(DISPLAY_NAME)-$(1).app/Contents/Info.plist
	@echo '    <key>CFBundleExecutable</key>' >> $(DIST_DIR)/$(DISPLAY_NAME)-$(1).app/Contents/Info.plist
	@echo '    <string>$(APP_NAME)</string>' >> $(DIST_DIR)/$(DISPLAY_NAME)-$(1).app/Contents/Info.plist
	@echo '    <key>CFBundleIconFile</key>' >> $(DIST_DIR)/$(DISPLAY_NAME)-$(1).app/Contents/Info.plist
	@echo '    <string>icon.png</string>' >> $(DIST_DIR)/$(DISPLAY_NAME)-$(1).app/Contents/Info.plist
	@echo '    <key>CFBundleIdentifier</key>' >> $(DIST_DIR)/$(DISPLAY_NAME)-$(1).app/Contents/Info.plist
	@echo '    <string>$(BUNDLE_ID)</string>' >> $(DIST_DIR)/$(DISPLAY_NAME)-$(1).app/Contents/Info.plist
	@echo '    <key>CFBundleName</key>' >> $(DIST_DIR)/$(DISPLAY_NAME)-$(1).app/Contents/Info.plist
	@echo '    <string>$(DISPLAY_NAME)</string>' >> $(DIST_DIR)/$(DISPLAY_NAME)-$(1).app/Contents/Info.plist
	@echo '    <key>CFBundlePackageType</key>' >> $(DIST_DIR)/$(DISPLAY_NAME)-$(1).app/Contents/Info.plist
	@echo '    <string>APPL</string>' >> $(DIST_DIR)/$(DISPLAY_NAME)-$(1).app/Contents/Info.plist
	@echo '    <key>CFBundleShortVersionString</key>' >> $(DIST_DIR)/$(DISPLAY_NAME)-$(1).app/Contents/Info.plist
	@echo '    <string>$(VERSION)</string>' >> $(DIST_DIR)/$(DISPLAY_NAME)-$(1).app/Contents/Info.plist
	@echo '    <key>CFBundleVersion</key>' >> $(DIST_DIR)/$(DISPLAY_NAME)-$(1).app/Contents/Info.plist
	@echo '    <string>$(VERSION)</string>' >> $(DIST_DIR)/$(DISPLAY_NAME)-$(1).app/Contents/Info.plist
	@echo '    <key>LSMinimumSystemVersion</key>' >> $(DIST_DIR)/$(DISPLAY_NAME)-$(1).app/Contents/Info.plist
	@echo '    <string>11.0</string>' >> $(DIST_DIR)/$(DISPLAY_NAME)-$(1).app/Contents/Info.plist
	@echo '    <key>LSUIElement</key>' >> $(DIST_DIR)/$(DISPLAY_NAME)-$(1).app/Contents/Info.plist
	@echo '    <true/>' >> $(DIST_DIR)/$(DISPLAY_NAME)-$(1).app/Contents/Info.plist
	@echo '    <key>NSHighResolutionCapable</key>' >> $(DIST_DIR)/$(DISPLAY_NAME)-$(1).app/Contents/Info.plist
	@echo '    <true/>' >> $(DIST_DIR)/$(DISPLAY_NAME)-$(1).app/Contents/Info.plist
	@echo '    <key>LSArchitecturePriority</key>' >> $(DIST_DIR)/$(DISPLAY_NAME)-$(1).app/Contents/Info.plist
	@echo '    <array>' >> $(DIST_DIR)/$(DISPLAY_NAME)-$(1).app/Contents/Info.plist
	@echo '        <string>$(2)</string>' >> $(DIST_DIR)/$(DISPLAY_NAME)-$(1).app/Contents/Info.plist
	@echo '    </array>' >> $(DIST_DIR)/$(DISPLAY_NAME)-$(1).app/Contents/Info.plist
	@echo '</dict>' >> $(DIST_DIR)/$(DISPLAY_NAME)-$(1).app/Contents/Info.plist
	@echo '</plist>' >> $(DIST_DIR)/$(DISPLAY_NAME)-$(1).app/Contents/Info.plist
	@echo "Created $(DIST_DIR)/$(DISPLAY_NAME)-$(1).app"
endef

# Sign macOS app bundles (only runs if CODESIGN_IDENTITY is set)
sign-darwin-arm64: bundle-darwin-arm64
ifneq ($(CODESIGN_IDENTITY),)
	@echo "Signing $(DISPLAY_NAME)-darwin-arm64.app with identity: $(CODESIGN_IDENTITY)"
	codesign --force --options runtime --entitlements $(ENTITLEMENTS) \
		--sign "$(CODESIGN_IDENTITY)" \
		--timestamp \
		$(DIST_DIR)/$(DISPLAY_NAME)-darwin-arm64.app
	@echo "Signed $(DIST_DIR)/$(DISPLAY_NAME)-darwin-arm64.app"
else
	@echo "Skipping code signing (CODESIGN_IDENTITY not set)"
endif

sign-darwin-amd64: bundle-darwin-amd64
ifneq ($(CODESIGN_IDENTITY),)
	@echo "Signing $(DISPLAY_NAME)-darwin-amd64.app with identity: $(CODESIGN_IDENTITY)"
	codesign --force --options runtime --entitlements $(ENTITLEMENTS) \
		--sign "$(CODESIGN_IDENTITY)" \
		--timestamp \
		$(DIST_DIR)/$(DISPLAY_NAME)-darwin-amd64.app
	@echo "Signed $(DIST_DIR)/$(DISPLAY_NAME)-darwin-amd64.app"
else
	@echo "Skipping code signing (CODESIGN_IDENTITY not set)"
endif

sign-darwin: sign-darwin-arm64 sign-darwin-amd64

# Zip macOS app bundles for distribution (use ditto to preserve bundle structure)
# Signing is performed before zipping if CODESIGN_IDENTITY is set
zip-darwin-arm64: sign-darwin-arm64
	cd $(DIST_DIR) && ditto -c -k --keepParent $(DISPLAY_NAME)-darwin-arm64.app $(DISPLAY_NAME)-darwin-arm64.zip
	@echo "Created $(DIST_DIR)/$(DISPLAY_NAME)-darwin-arm64.zip"

zip-darwin-amd64: sign-darwin-amd64
	cd $(DIST_DIR) && ditto -c -k --keepParent $(DISPLAY_NAME)-darwin-amd64.app $(DISPLAY_NAME)-darwin-amd64.zip
	@echo "Created $(DIST_DIR)/$(DISPLAY_NAME)-darwin-amd64.zip"

zip-darwin: zip-darwin-arm64 zip-darwin-amd64

# =============================================================================
# Windows Build
# =============================================================================

# Windows build flags: -H windowsgui hides the console window
WINDOWS_BUILD_FLAGS := -ldflags="-s -w -X main.Version=$(VERSION) -H windowsgui"

build-windows: web
	GOOS=windows GOARCH=amd64 CGO_ENABLED=1 go build $(WINDOWS_BUILD_FLAGS) -o $(DIST_DIR)/$(DISPLAY_NAME)-windows.exe .

# =============================================================================
# Linux Build
# =============================================================================

build-linux: web
	GOOS=linux GOARCH=amd64 CGO_ENABLED=1 go build $(BUILD_FLAGS) -o $(DIST_DIR)/$(DISPLAY_NAME)-linux .

# =============================================================================
# Development Commands
# =============================================================================

# Run in GUI mode
run:
	go run .

# Run in headless mode
run-headless:
	go run . --headless --port 5180

# Run in stdio mode
run-stdio:
	go run . --headless --transport stdio

# Run with SSL
run-ssl:
	TTAI_SSL_DOMAIN=tt-ai.dev go run . --headless

# =============================================================================
# Maintenance
# =============================================================================

# Clean build artifacts
clean:
	rm -f $(APP_NAME)
	rm -rf $(DIST_DIR)
	rm -rf $(WEBUI_DIST)

# Run tests
test:
	go test -v ./...

# Format code
fmt:
	go fmt ./...

# Run linter
lint:
	go vet ./...
	@command -v golangci-lint >/dev/null 2>&1 && golangci-lint run || echo "golangci-lint not installed, skipping"

# Install dependencies
deps:
	go mod tidy
	go mod download

.PHONY: all build build-all web \
	build-darwin build-darwin-arm64 build-darwin-amd64 \
	bundle-darwin bundle-darwin-arm64 bundle-darwin-amd64 \
	sign-darwin sign-darwin-arm64 sign-darwin-amd64 \
	zip-darwin zip-darwin-arm64 zip-darwin-amd64 \
	build-windows build-linux \
	run run-headless run-stdio run-ssl \
	clean test fmt lint deps
