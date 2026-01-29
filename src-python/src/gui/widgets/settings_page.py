"""Settings page widget with Tailscale-style form layout."""

import logging

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)
from qasync import asyncSlot

from src.auth.credentials import CredentialManager
from src.gui.state import AppState
from src.gui.widgets.login_dialog import LoginDialog
from src.server.config import ServerConfig
from src.services.tastytrade import TastyTradeService

logger = logging.getLogger("ttai.gui")


class SettingsPage(QScrollArea):
    """Settings page with form-style layout."""

    def __init__(
        self,
        state: AppState,
        tastytrade_service: TastyTradeService,
        credential_manager: CredentialManager,
        config: ServerConfig,
        parent: QWidget | None = None,
    ) -> None:
        """Initialize the settings page."""
        super().__init__(parent)
        self.state = state
        self.tastytrade_service = tastytrade_service
        self.credential_manager = credential_manager
        self.config = config
        self._login_dialog: LoginDialog | None = None
        self._setup_ui()
        self._connect_signals()
        self._update_auth_view()

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

        # --- Claude Desktop ---
        claude_field = QWidget()
        claude_vbox = QVBoxLayout(claude_field)
        claude_vbox.setContentsMargins(0, 0, 0, 0)
        claude_vbox.setSpacing(2)

        claude_vbox.addWidget(self._make_url_row())

        desc = QLabel("Start with --transport sse flag for Claude Desktop")
        desc.setEnabled(False)
        claude_vbox.addWidget(desc)

        self._form.addRow(self._make_section_label("Claude Desktop:"), claude_field)

        # --- TastyTrade ---
        tasty_row = QWidget()
        tasty_layout = QHBoxLayout(tasty_row)
        tasty_layout.setContentsMargins(0, 0, 0, 0)
        tasty_layout.setSpacing(8)

        self.auth_status_label = QLabel("Not Connected")
        tasty_layout.addWidget(self.auth_status_label)

        # Connect button (shown when disconnected)
        self.connect_btn = QPushButton("Connect...")
        self.connect_btn.clicked.connect(self._show_login_dialog)
        tasty_layout.addWidget(self.connect_btn)

        # Disconnect button (shown when connected)
        self.disconnect_btn = QPushButton("Disconnect")
        self.disconnect_btn.clicked.connect(self._on_disconnect)
        self.disconnect_btn.hide()
        tasty_layout.addWidget(self.disconnect_btn)

        tasty_layout.addStretch()

        self._form.addRow(self._make_section_label("TastyTrade:"), tasty_row)

    def _make_section_label(self, text: str) -> QLabel:
        """Create a bold section label."""
        label = QLabel(text)
        font = label.font()
        font.setBold(True)
        label.setFont(font)
        return label

    def _get_server_url(self) -> str:
        """Get the server URL based on SSL configuration."""
        if self.config.ssl_enabled:
            return f"https://{self.config.ssl_local_domain}:{self.config.ssl_port}/mcp"
        return f"http://{self.config.host}:{self.config.port}/mcp"

    def _make_url_row(self) -> QWidget:
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)

        server_url = self._get_server_url()
        url_label = QLabel(server_url)
        url_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(url_label, 0, Qt.AlignmentFlag.AlignVCenter)

        copy_btn = QPushButton("Copy")
        copy_btn.clicked.connect(lambda: self._copy_url(copy_btn))
        layout.addWidget(copy_btn, 0, Qt.AlignmentFlag.AlignVCenter)

        layout.addStretch()

        return widget

    def _connect_signals(self) -> None:
        """Connect state signals."""
        self.state.authenticated_changed.connect(self._update_auth_view)

    def _update_auth_view(self) -> None:
        """Update the view based on authentication state."""
        if self.state.authenticated:
            self.auth_status_label.setText("Connected")
            self.connect_btn.hide()
            self.disconnect_btn.show()
        else:
            self.auth_status_label.setText("Not Connected")
            self.connect_btn.show()
            self.disconnect_btn.hide()

    def _copy_url(self, btn: QPushButton) -> None:
        """Copy the server URL to clipboard."""
        clipboard = QGuiApplication.clipboard()
        if clipboard:
            clipboard.setText(self._get_server_url())
            btn.setText("Copied!")
            QTimer.singleShot(1500, lambda: btn.setText("Copy"))

    def _show_login_dialog(self) -> None:
        """Show the login dialog."""
        if self._login_dialog is None:
            self._login_dialog = LoginDialog(self.window())
            self._login_dialog.connect_btn.clicked.connect(self._on_dialog_connect)

        self._login_dialog.clear()
        self._login_dialog.show()
        self._login_dialog.raise_()

    @asyncSlot()
    async def _on_dialog_connect(self) -> None:
        """Handle connect from dialog."""
        if self._login_dialog is None:
            return

        client_secret, refresh_token = self._login_dialog.get_credentials()

        if not client_secret or not refresh_token:
            self._login_dialog.set_error("Please enter both client secret and refresh token")
            return

        self._login_dialog.set_error("")
        self._login_dialog.set_loading(True)

        try:
            success = await self.tastytrade_service.login(
                client_secret=client_secret,
                refresh_token=refresh_token,
                remember_me=True,
            )

            if success:
                self._login_dialog.accept()
                self.state.update_from_auth_status(
                    self.tastytrade_service.get_auth_status()
                )
            else:
                self._login_dialog.set_error("Login failed. Check your credentials.")
        except Exception as e:
            logger.exception("Login error")
            self._login_dialog.set_error(f"Error: {e}")
        finally:
            self._login_dialog.set_loading(False)

    @asyncSlot()
    async def _on_disconnect(self) -> None:
        """Handle disconnect button click."""
        await self.tastytrade_service.logout(clear_credentials=True)
        self.state.update_from_auth_status(self.tastytrade_service.get_auth_status())
