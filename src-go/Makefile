# TTAI Go Build Makefile

APP_NAME := ttai
VERSION := 1.0.0
BUILD_FLAGS := -ldflags="-s -w -X main.Version=$(VERSION)"

# Default target
all: build

# Development build
build:
	go build $(BUILD_FLAGS) -o $(APP_NAME) .

# Build for all platforms
build-all: build-darwin build-windows build-linux

# macOS builds
build-darwin: build-darwin-arm64 build-darwin-amd64

build-darwin-arm64:
	GOOS=darwin GOARCH=arm64 go build $(BUILD_FLAGS) -o $(APP_NAME)-darwin-arm64 .

build-darwin-amd64:
	GOOS=darwin GOARCH=amd64 go build $(BUILD_FLAGS) -o $(APP_NAME)-darwin-amd64 .

# Windows build
build-windows:
	GOOS=windows GOARCH=amd64 go build $(BUILD_FLAGS) -o $(APP_NAME)-windows.exe .

# Linux build
build-linux:
	GOOS=linux GOARCH=amd64 go build $(BUILD_FLAGS) -o $(APP_NAME)-linux .

# Run in GUI mode
run:
	go run .

# Run in headless mode
run-headless:
	go run . --headless --port 5180

# Run in stdio mode
run-stdio:
	go run . --headless --transport stdio

# Clean build artifacts
clean:
	rm -f $(APP_NAME) $(APP_NAME)-darwin-* $(APP_NAME)-windows.exe $(APP_NAME)-linux

# Run tests
test:
	go test -v ./...

# Format code
fmt:
	go fmt ./...

# Run linter
lint:
	go vet ./...
	@command -v golangci-lint >/dev/null 2>&1 && golangci-lint run || echo "golangci-lint not installed"

# Install dependencies
deps:
	go mod tidy
	go mod download

.PHONY: all build build-all build-darwin build-darwin-arm64 build-darwin-amd64 build-windows build-linux run run-headless run-stdio clean test fmt lint deps
