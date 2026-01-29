"""Settings page widget with application preferences."""

import logging
import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QFormLayout,
    QFrame,
    QLabel,
    QScrollArea,
    QWidget,
)

from src.gui.preferences import PreferencesManager

logger = logging.getLogger("ttai.gui")


def _get_app_executable() -> str:
    """Get the path to the application executable."""
    if getattr(sys, "frozen", False):
        # Running as PyInstaller bundle
        return sys.executable
    # Running from source - not supported for launch at startup
    return ""


# --- macOS ---


def _get_macos_launch_agent_path() -> Path:
    """Get the path to the macOS launch agent plist file."""
    return Path.home() / "Library" / "LaunchAgents" / "dev.tt-ai.ttai.plist"


def _is_launch_at_startup_enabled_macos() -> bool:
    """Check if launch at startup is enabled on macOS."""
    return _get_macos_launch_agent_path().exists()


def _set_launch_at_startup_macos(enabled: bool) -> bool:
    """Enable or disable launch at startup on macOS."""
    plist_path = _get_macos_launch_agent_path()

    if enabled:
        app_path = _get_app_executable()
        if not app_path:
            logger.warning("Cannot enable launch at startup: not running as bundled app")
            return False

        plist_path.parent.mkdir(parents=True, exist_ok=True)

        plist_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>dev.tt-ai.ttai</string>
    <key>ProgramArguments</key>
    <array>
        <string>{app_path}</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
</dict>
</plist>
"""
        try:
            plist_path.write_text(plist_content)
            logger.info(f"Created launch agent at {plist_path}")
            return True
        except OSError as e:
            logger.error(f"Failed to create launch agent: {e}")
            return False
    else:
        if plist_path.exists():
            try:
                plist_path.unlink()
                logger.info(f"Removed launch agent at {plist_path}")
                return True
            except OSError as e:
                logger.error(f"Failed to remove launch agent: {e}")
                return False
        return True


# --- Windows ---


def _is_launch_at_startup_enabled_windows() -> bool:
    """Check if launch at startup is enabled on Windows."""
    try:
        import winreg

        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0,
            winreg.KEY_READ,
        )
        try:
            winreg.QueryValueEx(key, "TTAI")
            return True
        except FileNotFoundError:
            return False
        finally:
            winreg.CloseKey(key)
    except Exception as e:
        logger.error(f"Failed to check Windows startup registry: {e}")
        return False


def _set_launch_at_startup_windows(enabled: bool) -> bool:
    """Enable or disable launch at startup on Windows."""
    try:
        import winreg

        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0,
            winreg.KEY_SET_VALUE,
        )
        try:
            if enabled:
                app_path = _get_app_executable()
                if not app_path:
                    logger.warning("Cannot enable launch at startup: not running as bundled app")
                    return False
                winreg.SetValueEx(key, "TTAI", 0, winreg.REG_SZ, f'"{app_path}"')
                logger.info("Added TTAI to Windows startup registry")
            else:
                try:
                    winreg.DeleteValue(key, "TTAI")
                    logger.info("Removed TTAI from Windows startup registry")
                except FileNotFoundError:
                    pass  # Already removed
            return True
        finally:
            winreg.CloseKey(key)
    except Exception as e:
        logger.error(f"Failed to modify Windows startup registry: {e}")
        return False


# --- Linux ---


def _get_linux_autostart_path() -> Path:
    """Get the path to the Linux autostart desktop file."""
    return Path.home() / ".config" / "autostart" / "ttai.desktop"


def _is_launch_at_startup_enabled_linux() -> bool:
    """Check if launch at startup is enabled on Linux."""
    return _get_linux_autostart_path().exists()


def _set_launch_at_startup_linux(enabled: bool) -> bool:
    """Enable or disable launch at startup on Linux."""
    desktop_path = _get_linux_autostart_path()

    if enabled:
        app_path = _get_app_executable()
        if not app_path:
            logger.warning("Cannot enable launch at startup: not running as bundled app")
            return False

        desktop_path.parent.mkdir(parents=True, exist_ok=True)

        desktop_content = f"""[Desktop Entry]
Type=Application
Name=TTAI
Comment=TastyTrade AI Assistant
Exec={app_path}
Hidden=false
NoDisplay=false
X-GNOME-Autostart-enabled=true
"""
        try:
            desktop_path.write_text(desktop_content)
            logger.info(f"Created autostart entry at {desktop_path}")
            return True
        except OSError as e:
            logger.error(f"Failed to create autostart entry: {e}")
            return False
    else:
        if desktop_path.exists():
            try:
                desktop_path.unlink()
                logger.info(f"Removed autostart entry at {desktop_path}")
                return True
            except OSError as e:
                logger.error(f"Failed to remove autostart entry: {e}")
                return False
        return True


# --- Platform dispatch ---


def _is_launch_at_startup_enabled() -> bool:
    """Check if launch at startup is currently enabled."""
    if sys.platform == "darwin":
        return _is_launch_at_startup_enabled_macos()
    elif sys.platform == "win32":
        return _is_launch_at_startup_enabled_windows()
    elif sys.platform.startswith("linux"):
        return _is_launch_at_startup_enabled_linux()
    return False


def _set_launch_at_startup(enabled: bool) -> bool:
    """Enable or disable launch at startup."""
    if sys.platform == "darwin":
        return _set_launch_at_startup_macos(enabled)
    elif sys.platform == "win32":
        return _set_launch_at_startup_windows(enabled)
    elif sys.platform.startswith("linux"):
        return _set_launch_at_startup_linux(enabled)
    logger.warning(f"Launch at startup not supported on platform: {sys.platform}")
    return False


def _is_platform_supported() -> bool:
    """Check if the current platform supports launch at startup."""
    return sys.platform in ("darwin", "win32") or sys.platform.startswith("linux")


class SettingsPage(QScrollArea):
    """Settings page with application preferences."""

    def __init__(
        self,
        preferences: PreferencesManager | None = None,
        parent: QWidget | None = None,
    ) -> None:
        """Initialize the settings page.

        Args:
            preferences: Optional preferences manager for persistent settings.
            parent: Parent widget.
        """
        super().__init__(parent)
        self._preferences = preferences
        self._setup_ui()

    def _setup_ui(self) -> None:
        """Set up the settings page UI."""
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setFrameShape(QFrame.Shape.NoFrame)

        content = QWidget()
        self.setWidget(content)

        self._form = QFormLayout(content)
        self._form.setContentsMargins(30, 30, 30, 30)
        self._form.setVerticalSpacing(16)
        self._form.setHorizontalSpacing(16)
        self._form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        # --- Launch at Startup ---
        self._launch_checkbox = QCheckBox("Launch TTAI when you log in")
        self._launch_checkbox.setChecked(_is_launch_at_startup_enabled())
        self._launch_checkbox.stateChanged.connect(self._on_launch_changed)

        # Disable if not running as bundled app or unsupported platform
        if not _get_app_executable():
            self._launch_checkbox.setEnabled(False)
            self._launch_checkbox.setToolTip("Only available when running as a bundled application")
        elif not _is_platform_supported():
            self._launch_checkbox.setEnabled(False)
            self._launch_checkbox.setToolTip(f"Not supported on {sys.platform}")

        self._form.addRow(self._make_section_label("Startup:"), self._launch_checkbox)

        # --- Window Settings ---
        self._show_window_checkbox = QCheckBox("Show settings window on launch")
        if self._preferences:
            self._show_window_checkbox.setChecked(self._preferences.show_window_on_launch)
        else:
            self._show_window_checkbox.setChecked(True)
            self._show_window_checkbox.setEnabled(False)
            self._show_window_checkbox.setToolTip("Preferences not available")
        self._show_window_checkbox.stateChanged.connect(self._on_show_window_changed)

        self._form.addRow(self._make_section_label("Window:"), self._show_window_checkbox)

    def _make_section_label(self, text: str) -> QLabel:
        """Create a bold section label."""
        label = QLabel(text)
        font = label.font()
        font.setBold(True)
        label.setFont(font)
        return label

    def _on_launch_changed(self, state: int) -> None:
        """Handle launch at startup checkbox change."""
        enabled = state == Qt.CheckState.Checked.value
        success = _set_launch_at_startup(enabled)

        if not success:
            # Revert checkbox state on failure
            self._launch_checkbox.blockSignals(True)
            self._launch_checkbox.setChecked(not enabled)
            self._launch_checkbox.blockSignals(False)

    def _on_show_window_changed(self, state: int) -> None:
        """Handle show window on launch checkbox change."""
        if self._preferences:
            enabled = state == Qt.CheckState.Checked.value
            self._preferences.show_window_on_launch = enabled
