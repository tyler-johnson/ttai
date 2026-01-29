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
import tempfile
from pathlib import Path

# Application name
APP_NAME = "TTAI"

# Icon sizes required for macOS .icns
ICNS_SIZES = [16, 32, 64, 128, 256, 512, 1024]


def create_icns(png_path: Path, output_path: Path) -> bool:
    """Create macOS .icns file from PNG using sips and iconutil."""
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            iconset_dir = Path(tmpdir) / "icon.iconset"
            iconset_dir.mkdir()

            # Generate all required sizes
            for size in ICNS_SIZES:
                # Standard resolution
                out_file = iconset_dir / f"icon_{size}x{size}.png"
                subprocess.run(
                    ["sips", "-z", str(size), str(size), str(png_path), "--out", str(out_file)],
                    capture_output=True,
                    check=True,
                )
                # Retina (@2x) - only for sizes up to 512
                if size <= 512:
                    out_file_2x = iconset_dir / f"icon_{size}x{size}@2x.png"
                    size_2x = size * 2
                    subprocess.run(
                        ["sips", "-z", str(size_2x), str(size_2x), str(png_path), "--out", str(out_file_2x)],
                        capture_output=True,
                        check=True,
                    )

            # Convert iconset to icns
            subprocess.run(
                ["iconutil", "-c", "icns", str(iconset_dir), "-o", str(output_path)],
                capture_output=True,
                check=True,
            )
            return True
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        print(f"Warning: Could not create .icns file: {e}")
        return False


def create_ico(png_path: Path, output_path: Path) -> bool:
    """Create Windows .ico file from PNG using Pillow."""
    try:
        from PIL import Image

        img = Image.open(png_path)
        # Windows ico typically includes these sizes
        sizes = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
        img.save(output_path, format="ICO", sizes=sizes)
        return True
    except ImportError:
        print("Warning: Pillow not installed, cannot create .ico file")
        return False
    except Exception as e:
        print(f"Warning: Could not create .ico file: {e}")
        return False


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
        # pyobjc for macOS integration
        "objc",
        "AppKit",
        "Foundation",
        "Cocoa",
        "PyObjCTools",
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
    icon_png = resources_dir / "icon.png"

    # Path separator for --add-data differs by platform
    path_sep = ";" if system == "windows" else ":"

    print(f"Building {APP_NAME} for {target_triple}...")
    print(f"Entry point: {entry_point}")

    # Generate platform-specific icon
    icon_path: Path | None = None
    if icon_png.exists():
        if system == "darwin":
            icon_path = build_dir / "icon.icns"
            build_dir.mkdir(parents=True, exist_ok=True)
            if create_icns(icon_png, icon_path):
                print(f"Created macOS icon: {icon_path}")
            else:
                icon_path = None
        elif system == "windows":
            icon_path = build_dir / "icon.ico"
            build_dir.mkdir(parents=True, exist_ok=True)
            if create_ico(icon_png, icon_path):
                print(f"Created Windows icon: {icon_path}")
            else:
                icon_path = None

    # Large PySide6/Qt modules we don't need
    excluded_modules = [
        # Web engine is huge (~200MB)
        "PySide6.QtWebEngine",
        "PySide6.QtWebEngineCore",
        "PySide6.QtWebEngineWidgets",
        "PySide6.QtWebChannel",
        # 3D modules
        "PySide6.Qt3DCore",
        "PySide6.Qt3DRender",
        "PySide6.Qt3DInput",
        "PySide6.Qt3DLogic",
        "PySide6.Qt3DAnimation",
        "PySide6.Qt3DExtras",
        # Multimedia
        "PySide6.QtMultimedia",
        "PySide6.QtMultimediaWidgets",
        # QML/Quick (we use widgets)
        "PySide6.QtQml",
        "PySide6.QtQuick",
        "PySide6.QtQuickWidgets",
        "PySide6.QtQuickControls2",
        # Other unused modules
        "PySide6.QtBluetooth",
        "PySide6.QtNfc",
        "PySide6.QtPositioning",
        "PySide6.QtLocation",
        "PySide6.QtSensors",
        "PySide6.QtSerialPort",
        "PySide6.QtWebSockets",
        "PySide6.QtPdf",
        "PySide6.QtPdfWidgets",
        "PySide6.QtCharts",
        "PySide6.QtDataVisualization",
        "PySide6.QtNetworkAuth",
        "PySide6.QtRemoteObjects",
        "PySide6.QtScxml",
        "PySide6.QtSql",
        "PySide6.QtTest",
        "PySide6.QtXml",
        "PySide6.QtDesigner",
        "PySide6.QtHelp",
        "PySide6.QtOpenGL",
        "PySide6.QtOpenGLWidgets",
        "PySide6.QtStateMachine",
        "PySide6.QtUiTools",
        "PySide6.QtSpatialAudio",
        "PySide6.QtHttpServer",
        "PySide6.QtVirtualKeyboard",
        "PySide6.QtTextToSpeech",
        "PySide6.QtSerialBus",
        "PySide6.QtShaderTools",
    ]

    # Base PyInstaller command
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--name", APP_NAME,
        "--distpath", str(dist_dir),
        "--workpath", str(build_dir),
        "--specpath", str(build_dir),
        # Collect PySide6 but we'll exclude unused modules
        "--collect-all", "PySide6",
        # Add GUI resources
        "--add-data", f"{resources_dir}{path_sep}src/gui/resources",
        # Clean build
        "--clean",
        "--noconfirm",
    ]

    # Exclude large unused modules
    for module in excluded_modules:
        cmd.extend(["--exclude-module", module])

    # Add icon if available
    if icon_path and icon_path.exists():
        cmd.extend(["--icon", str(icon_path)])

    # Platform-specific options
    if system == "darwin":
        # macOS: Create .app bundle
        cmd.extend([
            "--windowed",  # Creates .app bundle
            "--onedir",    # Required for .app structure
            # Collect pyobjc for macOS integration (tray, dock hiding)
            "--collect-submodules", "objc",
            "--collect-submodules", "AppKit",
            "--collect-submodules", "Foundation",
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
