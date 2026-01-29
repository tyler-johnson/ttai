#!/usr/bin/env python3
"""PyInstaller build script for TTAI.

Builds platform-specific GUI applications:
- macOS: TTAI.app bundle (can also run from CLI with flags)
- Windows: TTAI.exe (GUI app that accepts CLI flags)
- Linux: ttai executable

Usage:
    cd src-python
    uv run python scripts/build.py
"""

import platform
import shutil
import subprocess
import sys
from pathlib import Path

# Application name
APP_NAME = "TTAI"


def get_target_triple() -> str:
    """Determine the target triple for the current platform."""
    machine = platform.machine().lower()
    system = platform.system().lower()

    if system == "darwin":
        if machine in ("arm64", "aarch64"):
            return "aarch64-apple-darwin"
        return "x86_64-apple-darwin"
    elif system == "windows":
        return "x86_64-pc-windows-msvc"
    elif system == "linux":
        if machine in ("arm64", "aarch64"):
            return "aarch64-unknown-linux-gnu"
        return "x86_64-unknown-linux-gnu"
    else:
        raise RuntimeError(f"Unsupported platform: {system} {machine}")


def get_hidden_imports() -> list[str]:
    """Get list of hidden imports required for PyInstaller."""
    return [
        # MCP
        "mcp",
        "mcp.server",
        "mcp.server.stdio",
        "mcp.server.streamable_http_manager",
        "mcp.types",
        # ASGI/HTTP
        "starlette",
        "starlette.applications",
        "starlette.requests",
        "starlette.responses",
        "starlette.routing",
        "uvicorn",
        "uvicorn.config",
        "uvicorn.server",
        "uvicorn.lifespan",
        "uvicorn.lifespan.on",
        "uvicorn.protocols",
        "uvicorn.protocols.http",
        "uvicorn.protocols.http.auto",
        "uvicorn.protocols.http.h11_impl",
        "uvicorn.protocols.websockets",
        "uvicorn.protocols.websockets.auto",
        "uvicorn.loops",
        "uvicorn.loops.auto",
        # TastyTrade
        "tastytrade",
        "tastytrade.instruments",
        "tastytrade.market_data",
        "tastytrade.session",
        "tastytrade.account",
        # Qt/PySide6
        "PySide6",
        "PySide6.QtCore",
        "PySide6.QtGui",
        "PySide6.QtWidgets",
        "PySide6.QtSvg",
        "qasync",
        # Cryptography
        "cryptography",
        "cryptography.fernet",
        "cryptography.hazmat.primitives.kdf.pbkdf2",
        # Database
        "aiosqlite",
        "sqlite3",
        # HTTP client
        "httpx",
        "httpx._transports",
        "httpx._transports.default",
        # Pydantic
        "pydantic",
        "pydantic.fields",
        "pydantic_core",
        # Anyio (used by MCP)
        "anyio",
        "anyio._backends",
        "anyio._backends._asyncio",
        # SSE
        "sse_starlette",
        "sse_starlette.sse",
        # JSON
        "json",
        # Logging
        "logging.handlers",
    ]


def build() -> None:
    """Run PyInstaller to build the TTAI application."""
    system = platform.system().lower()
    target_triple = get_target_triple()

    # Determine paths
    src_python_dir = Path(__file__).parent.parent.resolve()
    entry_point = src_python_dir / "src" / "server" / "main.py"
    resources_dir = src_python_dir / "src" / "gui" / "resources"
    dist_dir = src_python_dir / "dist"
    build_dir = src_python_dir / "build"

    # Path separator for --add-data differs by platform
    path_sep = ";" if system == "windows" else ":"

    print(f"Building {APP_NAME} for {target_triple}...")
    print(f"Entry point: {entry_point}")

    # Base PyInstaller command
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--name", APP_NAME,
        "--distpath", str(dist_dir),
        "--workpath", str(build_dir),
        "--specpath", str(build_dir),
        # Collect all PySide6 components
        "--collect-all", "PySide6",
        # Add GUI resources
        "--add-data", f"{resources_dir}{path_sep}src/gui/resources",
        # Clean build
        "--clean",
        "--noconfirm",
    ]

    # Platform-specific options
    if system == "darwin":
        # macOS: Create .app bundle
        cmd.extend([
            "--windowed",  # Creates .app bundle
            "--onedir",    # Required for .app structure
        ])
        output_desc = f"{APP_NAME}.app bundle"
    elif system == "windows":
        # Windows: Single GUI executable
        cmd.extend([
            "--windowed",  # No console window on double-click
            "--onefile",   # Single .exe file
        ])
        output_desc = f"{APP_NAME}.exe"
    else:
        # Linux: Single executable
        cmd.extend([
            "--onefile",
        ])
        output_desc = f"{APP_NAME} executable"

    # Add hidden imports
    for imp in get_hidden_imports():
        cmd.extend(["--hidden-import", imp])

    # Add entry point
    cmd.append(str(entry_point))

    print(f"Output: {output_desc}")
    print(f"\nRunning PyInstaller...")

    # Run PyInstaller
    result = subprocess.run(cmd, cwd=src_python_dir)

    if result.returncode != 0:
        print(f"\nBuild failed with exit code {result.returncode}")
        sys.exit(result.returncode)

    # Determine output path and create final artifact
    if system == "darwin":
        app_bundle = dist_dir / f"{APP_NAME}.app"
        final_output = dist_dir / f"{APP_NAME}-{target_triple}.app"

        if app_bundle.exists():
            # Rename to include target triple
            if final_output.exists():
                shutil.rmtree(final_output)
            app_bundle.rename(final_output)

            # Also create a zip for distribution
            zip_path = dist_dir / f"{APP_NAME}-{target_triple}"
            shutil.make_archive(str(zip_path), "zip", dist_dir, f"{APP_NAME}-{target_triple}.app")

            print(f"\nBuild successful!")
            print(f"App bundle: {final_output}")
            print(f"Distribution: {zip_path}.zip")
            print(f"\nTo run from CLI: {final_output}/Contents/MacOS/{APP_NAME} --help")
        else:
            print(f"\nBuild completed but app bundle not found")
            sys.exit(1)

    elif system == "windows":
        exe_path = dist_dir / f"{APP_NAME}.exe"
        final_output = dist_dir / f"{APP_NAME}-{target_triple}.exe"

        if exe_path.exists():
            if final_output.exists():
                final_output.unlink()
            exe_path.rename(final_output)

            size_mb = final_output.stat().st_size / (1024 * 1024)
            print(f"\nBuild successful!")
            print(f"Output: {final_output}")
            print(f"Size: {size_mb:.1f} MB")
        else:
            print(f"\nBuild completed but exe not found")
            sys.exit(1)

    else:  # Linux
        exe_path = dist_dir / APP_NAME
        final_output = dist_dir / f"{APP_NAME}-{target_triple}"

        if exe_path.exists():
            if final_output.exists():
                final_output.unlink()
            exe_path.rename(final_output)

            size_mb = final_output.stat().st_size / (1024 * 1024)
            print(f"\nBuild successful!")
            print(f"Output: {final_output}")
            print(f"Size: {size_mb:.1f} MB")
        else:
            print(f"\nBuild completed but executable not found")
            sys.exit(1)


if __name__ == "__main__":
    build()
