# Build and Distribution

## Overview

TTAI supports two distribution methods for the Python MCP server:

- **Desktop Distribution**: Native desktop application built with Tauri v2, with the Python MCP server packaged as a PyInstaller sidecar binary
- **Headless Distribution**: Run directly from the source repository with Python, requiring no special packaging

Both methods use the same codebase and provide identical functionality.

## Distribution Methods

| Method | Target Users | Packaging | Prerequisites |
|--------|--------------|-----------|---------------|
| Desktop (Tauri) | End users | .dmg, .msi, .deb, .AppImage | None |
| Headless | Developers, power users | Source repository | Python 3.11+, git |

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                      Build & Distribution                            │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  Source Code                                                         │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐                     │
│  │   Svelte   │  │   Rust     │  │   Python   │                     │
│  │  Frontend  │  │   Tauri    │  │ MCP Server │                     │
│  │   (src/)   │  │(src-tauri/)│  │(src-python/)                     │
│  └─────┬──────┘  └─────┬──────┘  └─────┬──────┘                     │
│        │               │               │                             │
│        │               │               ├──────────────────┐          │
│        │               │               │                  │          │
│        ▼               ▼               ▼                  ▼          │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐   ┌────────────┐    │
│  │   Vite     │  │   Cargo    │  │ PyInstaller│   │  Run from  │    │
│  │   Build    │  │   Build    │  │   Build    │   │   Source   │    │
│  └─────┬──────┘  └─────┬──────┘  └─────┬──────┘   └─────┬──────┘    │
│        │               │               │                 │           │
│        └───────────────┼───────────────┘                 │           │
│                        ▼                                 ▼           │
│  ┌──────────────────────────────────────┐   ┌────────────────────┐  │
│  │          Desktop Distribution         │   │ Headless Distrib.  │  │
│  │  ┌──────────┐  ┌──────────┐          │   │                    │  │
│  │  │  macOS   │  │ Windows  │  ...     │   │  git clone + pip   │  │
│  │  │  .dmg    │  │  .msi    │          │   │                    │  │
│  │  └──────────┘  └──────────┘          │   └────────────────────┘  │
│  └──────────────────────────────────────┘                           │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

## Headless Distribution

Headless mode runs the Python MCP server directly from source. This is the simplest way to use TTAI for developers and users comfortable with Python.

### Prerequisites

- Python 3.11 or later
- Git
- pip (Python package manager)

### Installation

```bash
# Clone the repository
git clone https://github.com/your-org/ttai.git
cd ttai

# Set up Python environment
cd src-python
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -e .

# Return to project root
cd ..
```

### Running Headless

```bash
# Activate the virtual environment
cd src-python
source .venv/bin/activate

# Run with HTTP/SSE transport (headless mode)
python -m src.server.main --transport sse --port 8080

# Or use environment variables
TTAI_TRANSPORT=sse TTAI_PORT=8080 python -m src.server.main
```

The server will start and listen on `http://localhost:8080/sse` for MCP client connections.

### Connecting External MCP Clients

#### Claude Desktop Configuration

Add to your Claude Desktop MCP config (`~/.config/claude/mcp.json` or equivalent):

```json
{
  "mcpServers": {
    "ttai": {
      "url": "http://localhost:8080/sse"
    }
  }
}
```

#### Custom MCP Clients

Connect to the SSE endpoint at `http://localhost:8080/sse` and send messages to `http://localhost:8080/messages`.

### Environment Configuration

Create a `.env` file in `src-python/` for headless configuration:

```bash
# src-python/.env

# Transport configuration
TTAI_TRANSPORT=sse
TTAI_HOST=localhost
TTAI_PORT=8080

# Data directory
TTAI_DATA_DIR=~/.ttai

# Logging
TTAI_LOG_LEVEL=INFO

# TastyTrade API (use sandbox for testing)
TASTYTRADE_API_URL=https://api.cert.tastyworks.com

# Notifications (optional webhook for headless mode)
TTAI_WEBHOOK_URL=https://your-webhook-endpoint.com/notifications

# LLM API keys
ANTHROPIC_API_KEY=sk-ant-xxx
```

## Desktop Distribution (Tauri)

The desktop application bundles the Python MCP server as a PyInstaller binary alongside the Tauri app.

### Project Structure

```
ttai/
├── package.json                     # Root package.json
├── pnpm-workspace.yaml              # pnpm workspace config
│
├── src/                             # Svelte frontend (Settings UI)
│   ├── app.html                     # HTML template
│   ├── app.css                      # Tailwind directives + DaisyUI
│   ├── lib/
│   │   ├── components/              # Shared UI components
│   │   │   └── settings/            # Settings-specific components
│   │   ├── stores/                  # Svelte stores
│   │   └── api.ts                   # MCP client wrapper
│   └── routes/
│       ├── +layout.svelte           # App layout with DaisyUI theme
│       ├── +page.svelte             # Redirects to /settings
│       └── settings/
│           └── +page.svelte         # Settings page
│
├── src-tauri/                       # Tauri application
│   ├── Cargo.toml                   # Rust dependencies
│   ├── tauri.conf.json              # Tauri configuration
│   ├── capabilities/                # Permission capabilities
│   ├── icons/                       # App icons
│   ├── binaries/                    # Sidecar binaries (build output)
│   │   ├── ttai-server-x86_64-apple-darwin
│   │   ├── ttai-server-aarch64-apple-darwin
│   │   ├── ttai-server-x86_64-pc-windows-msvc.exe
│   │   └── ttai-server-x86_64-unknown-linux-gnu
│   └── src/
│       ├── main.rs                  # Entry point
│       ├── lib.rs                   # Library module
│       ├── commands.rs              # IPC commands
│       ├── sidecar.rs               # Sidecar management
│       └── notifications.rs         # Notification handling
│
├── src-python/                      # Python MCP server
│   ├── pyproject.toml               # Python project config
│   ├── requirements.txt             # Dependencies
│   ├── src/                         # Python source
│   └── scripts/
│       └── build.py                 # PyInstaller build script
│
├── docs/                            # Documentation
│   └── architecture/
│
├── .github/
│   └── workflows/
│       ├── ci.yml                   # CI workflow
│       └── release.yml              # Release workflow
│
├── vite.config.ts                   # Vite configuration
├── svelte.config.js                 # Svelte configuration
├── tsconfig.json                    # TypeScript configuration
└── package.json                     # Dependencies (includes tailwindcss, daisyui)
```

### Tauri Configuration

```json
// src-tauri/tauri.conf.json
{
  "$schema": "https://schema.tauri.app/config/2",
  "productName": "TTAI",
  "version": "0.1.0",
  "identifier": "com.ttai.app",
  "build": {
    "beforeBuildCommand": "pnpm run build",
    "beforeDevCommand": "pnpm run dev",
    "devUrl": "http://localhost:5173",
    "frontendDist": "../build"
  },
  "app": {
    "withGlobalTauri": true,
    "windows": [
      {
        "title": "TTAI - Trading Analysis",
        "width": 1200,
        "height": 800,
        "minWidth": 800,
        "minHeight": 600,
        "resizable": true,
        "fullscreen": false
      }
    ],
    "security": {
      "csp": null
    },
    "trayIcon": {
      "iconPath": "icons/icon.png",
      "iconAsTemplate": true
    }
  },
  "bundle": {
    "active": true,
    "icon": [
      "icons/32x32.png",
      "icons/128x128.png",
      "icons/128x128@2x.png",
      "icons/icon.icns",
      "icons/icon.ico"
    ],
    "targets": "all",
    "externalBin": ["binaries/ttai-server"],
    "macOS": {
      "minimumSystemVersion": "10.15",
      "signingIdentity": null,
      "providerShortName": null,
      "entitlements": null
    },
    "windows": {
      "certificateThumbprint": null,
      "digestAlgorithm": "sha256",
      "timestampUrl": ""
    },
    "linux": {
      "appimage": {
        "bundleMediaFramework": false
      },
      "deb": {
        "depends": []
      }
    }
  },
  "plugins": {
    "notification": {
      "all": true
    },
    "shell": {
      "sidecar": true
    }
  }
}
```

### Frontend Dependencies

The frontend uses Tailwind CSS v4 with CSS-based configuration and DaisyUI for components:

```json
{
  "devDependencies": {
    "@sveltejs/adapter-static": "^3.0.0",
    "@sveltejs/kit": "^2.0.0",
    "@sveltejs/vite-plugin-svelte": "^4.0.0",
    "svelte": "^5.0.0",
    "tailwindcss": "^4.0.0",
    "daisyui": "^5.0.0",
    "typescript": "^5.0.0",
    "vite": "^6.0.0"
  }
}
```

### Cargo.toml

```toml
[package]
name = "ttai"
version = "0.1.0"
description = "AI-Assisted Trading Analysis"
authors = ["TTAI Team"]
license = "MIT"
repository = ""
edition = "2021"

[build-dependencies]
tauri-build = { version = "2", features = [] }

[dependencies]
tauri = { version = "2", features = ["tray-icon", "protocol-asset"] }
tauri-plugin-notification = "2"
tauri-plugin-shell = "2"
tauri-plugin-process = "2"
serde = { version = "1", features = ["derive"] }
serde_json = "1"
tokio = { version = "1", features = ["full"] }
log = "0.4"
env_logger = "0.10"

[features]
default = ["custom-protocol"]
custom-protocol = ["tauri/custom-protocol"]

[profile.release]
panic = "abort"
codegen-units = 1
lto = true
opt-level = "s"
strip = true
```

## PyInstaller Build

### Build Script

```python
# src-python/scripts/build.py
"""
Build script for creating PyInstaller sidecar binaries.
"""
import os
import platform
import subprocess
import sys
from pathlib import Path

# Project paths
PROJECT_ROOT = Path(__file__).parent.parent
SRC_DIR = PROJECT_ROOT / "src"
DIST_DIR = PROJECT_ROOT / "dist"
TAURI_BINARIES = PROJECT_ROOT.parent / "src-tauri" / "binaries"

def get_target_triple() -> str:
    """Get the Rust target triple for the current platform."""
    system = platform.system().lower()
    machine = platform.machine().lower()

    if system == "darwin":
        if machine == "arm64":
            return "aarch64-apple-darwin"
        return "x86_64-apple-darwin"
    elif system == "windows":
        return "x86_64-pc-windows-msvc"
    elif system == "linux":
        return "x86_64-unknown-linux-gnu"
    else:
        raise ValueError(f"Unsupported platform: {system}")

def build_sidecar():
    """Build the Python sidecar binary."""
    target = get_target_triple()
    output_name = f"ttai-server-{target}"

    if platform.system() == "Windows":
        output_name += ".exe"

    print(f"Building sidecar for target: {target}")
    print(f"Output name: {output_name}")

    # PyInstaller command
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",
        "--name", "ttai-server",
        "--specpath", str(DIST_DIR),
        "--distpath", str(DIST_DIR),
        "--workpath", str(DIST_DIR / "build"),
        # Hidden imports that PyInstaller might miss
        "--hidden-import", "mcp",
        "--hidden-import", "tastytrade",
        "--hidden-import", "litellm",
        "--hidden-import", "sentence_transformers",
        "--hidden-import", "aiosqlite",
        "--hidden-import", "starlette",
        "--hidden-import", "uvicorn",
        # Data files
        "--add-data", f"{SRC_DIR}:src",
        # Entry point
        str(SRC_DIR / "__main__.py"),
    ]

    # Add platform-specific options
    if platform.system() == "Darwin":
        cmd.extend(["--target-arch", machine])
    elif platform.system() == "Windows":
        cmd.extend(["--noconsole"])  # Hide console window

    print(f"Running: {' '.join(cmd)}")
    subprocess.run(cmd, check=True, cwd=PROJECT_ROOT)

    # Rename and copy to Tauri binaries directory
    TAURI_BINARIES.mkdir(parents=True, exist_ok=True)

    src_binary = DIST_DIR / "ttai-server"
    if platform.system() == "Windows":
        src_binary = src_binary.with_suffix(".exe")

    dst_binary = TAURI_BINARIES / output_name

    print(f"Copying {src_binary} to {dst_binary}")
    import shutil
    shutil.copy2(src_binary, dst_binary)

    # Make executable on Unix
    if platform.system() != "Windows":
        os.chmod(dst_binary, 0o755)

    print(f"Sidecar built successfully: {dst_binary}")

if __name__ == "__main__":
    build_sidecar()
```

### PyInstaller Spec (Optional)

```python
# src-python/ttai-server.spec
# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

a = Analysis(
    ['src/__main__.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('src', 'src'),
    ],
    hiddenimports=[
        'mcp',
        'mcp.server',
        'mcp.server.stdio',
        'mcp.server.sse',
        'tastytrade',
        'litellm',
        'sentence_transformers',
        'aiosqlite',
        'cryptography',
        'pydantic',
        'starlette',
        'uvicorn',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter',
        'matplotlib',
        'PIL',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='ttai-server',
    debug=False,
    bootloader_ignore_signals=False,
    strip=True,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
```

## GitHub Actions CI/CD

### CI Workflow

```yaml
# .github/workflows/ci.yml
name: CI

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main]

jobs:
  lint-frontend:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: pnpm/action-setup@v2
        with:
          version: 8

      - uses: actions/setup-node@v4
        with:
          node-version: '20'
          cache: 'pnpm'

      - run: pnpm install
      - run: pnpm run lint
      - run: pnpm run check

  lint-python:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: |
          cd src-python
          pip install -e ".[dev]"

      - name: Run linters
        run: |
          cd src-python
          ruff check src/
          black --check src/
          mypy src/

  test-python:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: |
          cd src-python
          pip install -e ".[dev]"

      - name: Run tests
        run: |
          cd src-python
          pytest tests/ -v --cov=src

  build-tauri:
    needs: [lint-frontend, lint-python, test-python]
    strategy:
      fail-fast: false
      matrix:
        include:
          - platform: macos-latest
            target: aarch64-apple-darwin
          - platform: macos-latest
            target: x86_64-apple-darwin
          - platform: ubuntu-22.04
            target: x86_64-unknown-linux-gnu
          - platform: windows-latest
            target: x86_64-pc-windows-msvc

    runs-on: ${{ matrix.platform }}
    steps:
      - uses: actions/checkout@v4

      - uses: pnpm/action-setup@v2
        with:
          version: 8

      - uses: actions/setup-node@v4
        with:
          node-version: '20'
          cache: 'pnpm'

      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install Rust
        uses: dtolnay/rust-action@stable
        with:
          targets: ${{ matrix.target }}

      - name: Install Linux dependencies
        if: matrix.platform == 'ubuntu-22.04'
        run: |
          sudo apt-get update
          sudo apt-get install -y \
            libgtk-3-dev \
            libwebkit2gtk-4.1-dev \
            libappindicator3-dev \
            librsvg2-dev \
            patchelf

      - name: Install frontend dependencies
        run: pnpm install

      - name: Install Python dependencies
        run: |
          cd src-python
          pip install -e ".[dev]"
          pip install pyinstaller

      - name: Build Python sidecar
        run: |
          cd src-python
          python scripts/build.py

      - name: Build Tauri app
        uses: tauri-apps/tauri-action@v0
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        with:
          args: --target ${{ matrix.target }}
```

### Release Workflow

```yaml
# .github/workflows/release.yml
name: Release

on:
  push:
    tags:
      - 'v*'

permissions:
  contents: write

jobs:
  release:
    strategy:
      fail-fast: false
      matrix:
        include:
          - platform: macos-latest
            target: aarch64-apple-darwin
          - platform: macos-latest
            target: x86_64-apple-darwin
          - platform: ubuntu-22.04
            target: x86_64-unknown-linux-gnu
          - platform: windows-latest
            target: x86_64-pc-windows-msvc

    runs-on: ${{ matrix.platform }}
    steps:
      - uses: actions/checkout@v4

      - uses: pnpm/action-setup@v2
        with:
          version: 8

      - uses: actions/setup-node@v4
        with:
          node-version: '20'
          cache: 'pnpm'

      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install Rust
        uses: dtolnay/rust-action@stable
        with:
          targets: ${{ matrix.target }}

      - name: Install Linux dependencies
        if: matrix.platform == 'ubuntu-22.04'
        run: |
          sudo apt-get update
          sudo apt-get install -y \
            libgtk-3-dev \
            libwebkit2gtk-4.1-dev \
            libappindicator3-dev \
            librsvg2-dev \
            patchelf

      - name: Install frontend dependencies
        run: pnpm install

      - name: Install Python dependencies
        run: |
          cd src-python
          pip install -e ".[dev]"
          pip install pyinstaller

      - name: Build Python sidecar
        run: |
          cd src-python
          python scripts/build.py

      - name: Build and release
        uses: tauri-apps/tauri-action@v0
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          APPLE_CERTIFICATE: ${{ secrets.APPLE_CERTIFICATE }}
          APPLE_CERTIFICATE_PASSWORD: ${{ secrets.APPLE_CERTIFICATE_PASSWORD }}
          APPLE_SIGNING_IDENTITY: ${{ secrets.APPLE_SIGNING_IDENTITY }}
          APPLE_ID: ${{ secrets.APPLE_ID }}
          APPLE_PASSWORD: ${{ secrets.APPLE_PASSWORD }}
          APPLE_TEAM_ID: ${{ secrets.APPLE_TEAM_ID }}
        with:
          tagName: ${{ github.ref_name }}
          releaseName: 'TTAI v__VERSION__'
          releaseBody: 'See the changelog for details.'
          releaseDraft: true
          prerelease: false
          args: --target ${{ matrix.target }}
```

## Auto-Update

### Tauri Updater Configuration

```json
// In tauri.conf.json, add to "plugins":
{
  "plugins": {
    "updater": {
      "endpoints": [
        "https://github.com/your-org/ttai/releases/latest/download/latest.json"
      ],
      "pubkey": "YOUR_PUBLIC_KEY_HERE"
    }
  }
}
```

### Update Manifest

The release workflow automatically generates `latest.json`:

```json
{
  "version": "0.1.0",
  "notes": "Release notes here",
  "pub_date": "2024-01-15T00:00:00Z",
  "platforms": {
    "darwin-aarch64": {
      "signature": "...",
      "url": "https://github.com/.../TTAI_0.1.0_aarch64.dmg"
    },
    "darwin-x86_64": {
      "signature": "...",
      "url": "https://github.com/.../TTAI_0.1.0_x64.dmg"
    },
    "linux-x86_64": {
      "signature": "...",
      "url": "https://github.com/.../TTAI_0.1.0_amd64.AppImage"
    },
    "windows-x86_64": {
      "signature": "...",
      "url": "https://github.com/.../TTAI_0.1.0_x64-setup.exe"
    }
  }
}
```

## Local Build Commands

### Desktop Build

```bash
# Install all dependencies
pnpm install
cd src-python && pip install -e ".[dev]" && cd ..

# Development mode (Tauri app with hot reload)
pnpm tauri dev

# Build Python sidecar only
cd src-python && python scripts/build.py

# Build release (all platforms available on current OS)
pnpm tauri build

# Build for specific target
pnpm tauri build --target aarch64-apple-darwin
```

### Headless Setup

```bash
# Clone and setup
git clone https://github.com/your-org/ttai.git
cd ttai/src-python

# Create virtual environment
python -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -e .

# Run headless server
python -m src.server.main --transport sse --port 8080
```

## Cross-References

- [MCP Server Design](./01-mcp-server-design.md) - Dual-mode architecture
- [Python Server](./03-python-server.md) - Python project structure, running modes
- [Integration Patterns](./09-integration-patterns.md) - Sidecar communication
- [Local Development](./10-local-development.md) - Development setup
- [Frontend Architecture](./11-frontend.md) - Settings UI, Tailwind CSS, DaisyUI
