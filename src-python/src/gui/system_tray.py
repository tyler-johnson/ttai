"""System tray / menu bar icon management."""

import logging
import sys
from pathlib import Path

from PySide6.QtCore import QByteArray, QObject, Qt, Signal
from PySide6.QtGui import QAction, QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

logger = logging.getLogger("ttai.gui")


def _get_resources_dir() -> Path:
    """Get resources directory, handling PyInstaller frozen apps."""
    if getattr(sys, "frozen", False):
        # Running as PyInstaller bundle - resources are in _MEIPASS
        return Path(sys._MEIPASS) / "src" / "gui" / "resources"  # type: ignore[attr-defined]
    return Path(__file__).parent / "resources"


def _load_tray_icon(svg_path: Path) -> QIcon:
    """Load an SVG as a system tray icon.

    On macOS, renders as a template image (black) so the system can
    handle light/dark menu bar automatically. On other platforms,
    renders with a visible color.
    """
    # macOS menu bar icons should be black (system applies template mask)
    # Other platforms need a visible color
    if sys.platform == "darwin":
        stroke_color = "#000000"
    else:
        stroke_color = "#FFFFFF"

    svg_content = svg_path.read_text()
    svg_content = svg_content.replace("currentColor", stroke_color)

    # Render SVG to pixmap at higher resolution for crisp display
    # Qt will scale down as needed for the system tray
    size = 128
    svg_data = QByteArray(svg_content.encode())
    renderer = QSvgRenderer(svg_data)

    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    renderer.render(painter)
    painter.end()

    icon = QIcon(pixmap)

    # On macOS, mark as template image so system handles light/dark mode
    if sys.platform == "darwin":
        icon.setIsMask(True)

    return icon


class SystemTrayManager(QObject):
    """Manages the system tray icon and its context menu.

    Signals:
        show_window_requested: Emitted when user wants to show the settings window.
        quit_requested: Emitted when user wants to quit the application.
    """

    show_window_requested = Signal()
    quit_requested = Signal()

    def __init__(self, app: QApplication) -> None:
        """Initialize the system tray manager.

        Args:
            app: The QApplication instance.
        """
        super().__init__()
        self._app = app
        self._tray_icon: QSystemTrayIcon | None = None
        self._available = QSystemTrayIcon.isSystemTrayAvailable()

        if not self._available:
            logger.warning("System tray is not available on this platform")
            return

        self._setup_tray_icon()

    def _setup_tray_icon(self) -> None:
        """Set up the system tray icon and context menu."""
        self._tray_icon = QSystemTrayIcon(self._app)

        # Load icon from resources
        resources_dir = _get_resources_dir()
        icon_path = resources_dir / "pulse.svg"

        if icon_path.exists():
            icon = _load_tray_icon(icon_path)
        else:
            # Fallback to application icon if specific tray icon not found
            logger.warning(f"Tray icon not found at {icon_path}, using fallback")
            icon = self._app.windowIcon()
            if icon.isNull():
                icon = QIcon.fromTheme("application-default-icon")

        self._tray_icon.setIcon(icon)
        self._tray_icon.setToolTip("TTAI - TastyTrade AI")

        # Create context menu
        menu = QMenu()

        show_action = QAction("Show Settings", menu)
        show_action.triggered.connect(self._on_show_requested)
        menu.addAction(show_action)

        menu.addSeparator()

        quit_action = QAction("Quit TTAI", menu)
        quit_action.triggered.connect(self._on_quit_requested)
        menu.addAction(quit_action)

        self._tray_icon.setContextMenu(menu)

        # Handle tray icon activation (double-click on Windows/Linux, click on macOS)
        self._tray_icon.activated.connect(self._on_tray_activated)

    def show(self) -> None:
        """Show the tray icon."""
        if self._tray_icon:
            self._tray_icon.show()
            logger.debug("System tray icon shown")

    def hide(self) -> None:
        """Hide the tray icon."""
        if self._tray_icon:
            self._tray_icon.hide()

    def is_available(self) -> bool:
        """Check if system tray is available on this platform."""
        return self._available

    def _on_show_requested(self) -> None:
        """Handle show settings menu action."""
        self.show_window_requested.emit()

    def _on_quit_requested(self) -> None:
        """Handle quit menu action."""
        self.quit_requested.emit()

    def _on_tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        """Handle tray icon activation.

        On macOS, single click shows the menu automatically.
        On Windows/Linux, double-click should show the window.
        """
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.show_window_requested.emit()
        elif reason == QSystemTrayIcon.ActivationReason.Trigger:
            # Single click - on macOS this is handled by the menu,
            # on other platforms we show the window
            if sys.platform != "darwin":
                self.show_window_requested.emit()
