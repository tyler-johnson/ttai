"""Main application window."""

import sys
from pathlib import Path

from PySide6.QtCore import QByteArray, Qt
from PySide6.QtGui import QAction, QCloseEvent, QIcon, QPalette, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (
    QButtonGroup,
    QHBoxLayout,
    QMainWindow,
    QSizePolicy,
    QStackedWidget,
    QToolBar,
    QToolButton,
    QWidget,
)

from src.auth.credentials import CredentialManager
from src.gui.preferences import PreferencesManager
from src.gui.state import AppState
from src.gui.widgets.about_page import AboutPage
from src.gui.widgets.connection_page import ConnectionPage
from src.gui.widgets.settings_page import SettingsPage
from src.server.config import ServerConfig
from src.services.tastytrade import TastyTradeService


def _get_resources_dir() -> Path:
    """Get resources directory, handling PyInstaller frozen apps."""
    if getattr(sys, "frozen", False):
        # Running as PyInstaller bundle - resources are in _MEIPASS
        return Path(sys._MEIPASS) / "src" / "gui" / "resources"  # type: ignore[attr-defined]
    return Path(__file__).parent / "resources"


RESOURCES_DIR = _get_resources_dir()


def _load_themed_icon(svg_path: Path, palette: QPalette) -> QIcon:
    """Load an SVG icon with currentColor replaced by the palette text color."""
    text_color = palette.color(QPalette.ColorRole.WindowText).name()

    svg_content = svg_path.read_text()
    svg_content = svg_content.replace("currentColor", text_color)

    # Render SVG to pixmap
    svg_data = QByteArray(svg_content.encode())
    renderer = QSvgRenderer(svg_data)

    pixmap = QPixmap(24, 24)
    pixmap.fill(Qt.GlobalColor.transparent)

    from PySide6.QtGui import QPainter

    painter = QPainter(pixmap)
    renderer.render(painter)
    painter.end()

    return QIcon(pixmap)


class MainWindow(QMainWindow):
    """Main application window with unified title bar and tabs."""

    def __init__(
        self,
        state: AppState,
        tastytrade_service: TastyTradeService,
        credential_manager: CredentialManager,
        config: ServerConfig,
        preferences: PreferencesManager | None = None,
    ) -> None:
        """Initialize the main window."""
        super().__init__()
        self.state = state
        self.tastytrade_service = tastytrade_service
        self.credential_manager = credential_manager
        self.config = config
        self.preferences = preferences

        # Flag for force quit (actual exit vs hide to tray)
        self._force_quit = False

        self._setup_window()
        self._setup_menu()
        self._setup_toolbar()
        self._setup_ui()

    def _setup_window(self) -> None:
        """Configure window properties."""
        self.setWindowTitle("TTAI")
        # Fixed size, non-resizable
        self.setFixedSize(620, 400)

        # On Windows/Linux, use Tool window flag to hide from taskbar
        # macOS uses a different approach (NSApplicationActivationPolicyAccessory)
        if sys.platform != "darwin":
            self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.Tool)

        # Unified title bar on macOS
        self.setUnifiedTitleAndToolBarOnMac(True)

    def _setup_menu(self) -> None:
        """Set up the menu bar."""
        menubar = self.menuBar()

        # Help menu
        help_menu = menubar.addMenu("Help")

        docs_action = QAction("Documentation", self)
        docs_action.triggered.connect(self._open_docs)
        help_menu.addAction(docs_action)

        help_menu.addSeparator()

        about_action = QAction("About TTAI", self)
        about_action.triggered.connect(lambda: self._select_tab(2))
        help_menu.addAction(about_action)

    def _setup_toolbar(self) -> None:
        """Set up the toolbar with centered tab-style buttons."""
        toolbar = QToolBar()
        toolbar.setMovable(False)
        toolbar.setFloatable(False)

        # Left spacer
        left_spacer = QWidget()
        left_spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        toolbar.addWidget(left_spacer)

        # Tab buttons container
        tab_container = QWidget()
        tab_layout = QHBoxLayout(tab_container)
        tab_layout.setContentsMargins(0, 0, 0, 0)
        tab_layout.setSpacing(4)

        # Button group for exclusive selection
        self.tab_group = QButtonGroup(self)
        self.tab_group.setExclusive(True)

        # Fixed width for consistent tab sizing
        tab_width = 80

        # Load icons with system text color
        palette = self.palette()
        connection_icon = _load_themed_icon(RESOURCES_DIR / "plug.svg", palette)
        settings_icon = _load_themed_icon(RESOURCES_DIR / "settings.svg", palette)
        about_icon = _load_themed_icon(RESOURCES_DIR / "info.svg", palette)

        # Connection button
        self.connection_btn = QToolButton()
        self.connection_btn.setText("Connection")
        self.connection_btn.setIcon(connection_icon)
        self.connection_btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        self.connection_btn.setCheckable(True)
        self.connection_btn.setChecked(True)
        self.connection_btn.setAutoRaise(True)
        self.connection_btn.setFixedWidth(tab_width)
        self.tab_group.addButton(self.connection_btn, 0)
        tab_layout.addWidget(self.connection_btn)

        # Settings button
        self.settings_btn = QToolButton()
        self.settings_btn.setText("Settings")
        self.settings_btn.setIcon(settings_icon)
        self.settings_btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        self.settings_btn.setCheckable(True)
        self.settings_btn.setAutoRaise(True)
        self.settings_btn.setFixedWidth(tab_width)
        self.tab_group.addButton(self.settings_btn, 1)
        tab_layout.addWidget(self.settings_btn)

        # About button
        self.about_btn = QToolButton()
        self.about_btn.setText("About")
        self.about_btn.setIcon(about_icon)
        self.about_btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        self.about_btn.setCheckable(True)
        self.about_btn.setAutoRaise(True)
        self.about_btn.setFixedWidth(tab_width)
        self.tab_group.addButton(self.about_btn, 2)
        tab_layout.addWidget(self.about_btn)

        self.tab_group.idClicked.connect(self._on_tab_changed)
        toolbar.addWidget(tab_container)

        # Right spacer
        right_spacer = QWidget()
        right_spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        toolbar.addWidget(right_spacer)

        self.addToolBar(toolbar)

    def _setup_ui(self) -> None:
        """Set up the user interface."""
        # Content stack
        self.content_stack = QStackedWidget()
        self.setCentralWidget(self.content_stack)

        # Connection page
        self.connection_page = ConnectionPage(
            state=self.state,
            tastytrade_service=self.tastytrade_service,
            credential_manager=self.credential_manager,
            config=self.config,
        )
        self.content_stack.addWidget(self.connection_page)

        # Settings page
        self.settings_page = SettingsPage(preferences=self.preferences)
        self.content_stack.addWidget(self.settings_page)

        # About page
        self.about_page = AboutPage()
        self.content_stack.addWidget(self.about_page)

    def _on_tab_changed(self, index: int) -> None:
        """Handle tab selection change."""
        self.content_stack.setCurrentIndex(index)

    def _select_tab(self, index: int) -> None:
        """Programmatically select a tab."""
        if index == 0:
            self.connection_btn.setChecked(True)
        elif index == 1:
            self.settings_btn.setChecked(True)
        else:
            self.about_btn.setChecked(True)
        self.content_stack.setCurrentIndex(index)

    def _open_docs(self) -> None:
        """Open documentation URL."""
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices

        QDesktopServices.openUrl(QUrl("https://github.com/your-repo/ttai"))

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802 - Qt override
        """Handle window close event.

        Instead of quitting, hide the window to the system tray.
        The app continues running in the background.
        """
        if self._force_quit:
            event.accept()
        else:
            event.ignore()
            self.hide()

    def force_quit(self) -> None:
        """Force quit the application (called from tray quit action)."""
        self._force_quit = True
        self.close()

    def show_and_activate(self) -> None:
        """Show and bring window to front."""
        self.show()
        self.raise_()
        self.activateWindow()
