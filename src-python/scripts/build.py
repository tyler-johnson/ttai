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


def cleanup_bundle(bundle_path: Path) -> None:
    """Remove unnecessary files from the app bundle to reduce size."""
    # Patterns to remove (Qt frameworks and files we don't need)
    # We only need: QtCore, QtGui, QtWidgets, QtSvg, QtDBus, QtNetwork (for API calls)
    remove_patterns = [
        # Massive WebEngine (280MB+)
        "QtWebEngine*",
        # PDF support (8MB)
        "QtPdf*",
        # QML/Quick (we use widgets) - many MB
        "QtQml*",
        "QtQuick*",
        # 3D modules
        "Qt3D*",
        # Designer tools
        "QtDesigner*",
        # Multimedia
        "QtMultimedia*",
        "QtSpatialAudio*",
        # Other unused
        "QtBluetooth*",
        "QtCharts*",
        "QtDataVisualization*",
        "QtGraphs*",
        "QtLocation*",
        "QtNfc*",
        "QtPositioning*",
        "QtRemoteObjects*",
        "QtSensors*",
        "QtSerialBus*",
        "QtSerialPort*",
        "QtShaderTools*",
        "QtSql*",
        "QtTest*",
        "QtVirtualKeyboard*",
        "QtWebChannel*",
        "QtWebSockets*",
        "QtTextToSpeech*",
        "QtHttpServer*",
        "QtScxml*",
        "QtStateMachine*",
        # OpenGL (not needed for basic widgets)
        "QtOpenGL*",
    ]

    # Directories to completely remove
    remove_dirs = [
        "PySide6/Qt/qml",  # QML files (~19MB)
        "PySide6/Qt/translations",  # Translation files (~15MB)
        "PySide6/Qt/metatypes",  # Meta type info (~14MB)
        "PySide6/Assistant.app",
        "PySide6/Assistant__dot__app",
        "PySide6/Linguist.app",
        "PySide6/Linguist__dot__app",
        "PySide6/Designer.app",
        "PySide6/Designer__dot__app",
        "PySide6/include",  # Header files
        "PySide6/typesystems",  # Type system files
        "PySide6/glue",  # Glue code
        # Dev tools that leaked in
        "mypy",
        "pytest",
        "ruff",
        "black",
    ]

    frameworks_dir = bundle_path / "Contents" / "Frameworks"
    if not frameworks_dir.exists():
        # Try alternate location for non-macOS
        frameworks_dir = bundle_path / "_internal" if (bundle_path / "_internal").exists() else bundle_path
        if not frameworks_dir.exists():
            return

    removed_size = 0

    # Remove Qt frameworks matching patterns
    qt_lib_dir = frameworks_dir / "PySide6" / "Qt" / "lib"
    if qt_lib_dir.exists():
        import fnmatch
        for pattern in remove_patterns:
            for item in qt_lib_dir.iterdir():
                if fnmatch.fnmatch(item.name, pattern) or fnmatch.fnmatch(item.name, f"{pattern}.framework"):
                    if item.exists() or item.is_symlink():
                        if item.is_symlink():
                            item.unlink()
                            print(f"  Removed symlink: {item.name}")
                        elif item.is_dir():
                            size = sum(f.stat().st_size for f in item.rglob("*") if f.is_file())
                            removed_size += size
                            shutil.rmtree(item)
                            print(f"  Removed: {item.name} ({size / 1024 / 1024:.1f} MB)")
                        else:
                            size = item.stat().st_size
                            removed_size += size
                            item.unlink()
                            print(f"  Removed: {item.name} ({size / 1024 / 1024:.1f} MB)")

    # Remove Qt plugins we don't need
    qt_plugins_dir = frameworks_dir / "PySide6" / "Qt" / "plugins"
    if qt_plugins_dir.exists():
        plugins_to_remove = [
            "multimedia", "qmltooling", "scenegraph", "qmllint",
            "designer", "sqldrivers", "webview", "position",
            "sensors", "texttospeech", "canbus", "virtualkeyboard",
            "geometryloaders", "sceneparsers", "renderers",
        ]
        for plugin_name in plugins_to_remove:
            plugin_dir = qt_plugins_dir / plugin_name
            if plugin_dir.exists() or plugin_dir.is_symlink():
                if plugin_dir.is_symlink():
                    plugin_dir.unlink()
                    print(f"  Removed plugin symlink: {plugin_name}")
                else:
                    size = sum(f.stat().st_size for f in plugin_dir.rglob("*") if f.is_file())
                    removed_size += size
                    shutil.rmtree(plugin_dir)
                    print(f"  Removed plugin: {plugin_name} ({size / 1024 / 1024:.1f} MB)")

    # Remove complete directories
    for dir_pattern in remove_dirs:
        dir_path = frameworks_dir / dir_pattern
        if dir_path.exists() or dir_path.is_symlink():
            if dir_path.is_symlink():
                dir_path.unlink()
                print(f"  Removed symlink: {dir_pattern}")
            else:
                size = sum(f.stat().st_size for f in dir_path.rglob("*") if f.is_file())
                removed_size += size
                shutil.rmtree(dir_path)
                print(f"  Removed: {dir_pattern} ({size / 1024 / 1024:.1f} MB)")

    print(f"\nTotal removed: {removed_size / 1024 / 1024:.1f} MB")


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

    # Modules to exclude from the build
    excluded_modules = [
        # Large PySide6/Qt modules we don't need
        "PySide6.QtWebEngine",
        "PySide6.QtWebEngineCore",
        "PySide6.QtWebEngineWidgets",
        "PySide6.QtWebChannel",
        "PySide6.Qt3DCore",
        "PySide6.Qt3DRender",
        "PySide6.Qt3DInput",
        "PySide6.Qt3DLogic",
        "PySide6.Qt3DAnimation",
        "PySide6.Qt3DExtras",
        "PySide6.QtMultimedia",
        "PySide6.QtMultimediaWidgets",
        "PySide6.QtQml",
        "PySide6.QtQuick",
        "PySide6.QtQuickWidgets",
        "PySide6.QtQuickControls2",
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
        # Dev tools that shouldn't be bundled
        "mypy",
        "pytest",
        "ruff",
        "black",
        # Not needed at runtime
        "PIL",
        "pillow",
        "numpy.testing",
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

            # Clean up unnecessary Qt frameworks to reduce size
            print("\nCleaning up unnecessary files...")
            cleanup_bundle(final_output)

            # Calculate and show final size
            total_size = sum(f.stat().st_size for f in final_output.rglob("*") if f.is_file())
            print(f"\nFinal app size: {total_size / 1024 / 1024:.1f} MB")

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
