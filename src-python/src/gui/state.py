"""Reactive application state using Qt signals."""

from PySide6.QtCore import QObject, Signal


class AppState(QObject):
    """Application state with Qt signals for reactive updates."""

    authenticated_changed = Signal(bool)
    has_stored_credentials_changed = Signal(bool)
    is_logging_in_changed = Signal(bool)
    login_error_changed = Signal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        """Initialize application state.

        Args:
            parent: Optional parent QObject
        """
        super().__init__(parent)
        self._authenticated = False
        self._has_stored_credentials = False
        self._is_logging_in = False
        self._login_error: str | None = None

    @property
    def authenticated(self) -> bool:
        """Get authentication status."""
        return self._authenticated

    @authenticated.setter
    def authenticated(self, value: bool) -> None:
        """Set authentication status and emit signal if changed."""
        if self._authenticated != value:
            self._authenticated = value
            self.authenticated_changed.emit(value)

    @property
    def has_stored_credentials(self) -> bool:
        """Get whether credentials are stored."""
        return self._has_stored_credentials

    @has_stored_credentials.setter
    def has_stored_credentials(self, value: bool) -> None:
        """Set stored credentials status and emit signal if changed."""
        if self._has_stored_credentials != value:
            self._has_stored_credentials = value
            self.has_stored_credentials_changed.emit(value)

    @property
    def is_logging_in(self) -> bool:
        """Get login in progress status."""
        return self._is_logging_in

    @is_logging_in.setter
    def is_logging_in(self, value: bool) -> None:
        """Set login in progress status and emit signal if changed."""
        if self._is_logging_in != value:
            self._is_logging_in = value
            self.is_logging_in_changed.emit(value)

    @property
    def login_error(self) -> str | None:
        """Get login error message."""
        return self._login_error

    @login_error.setter
    def login_error(self, value: str | None) -> None:
        """Set login error message and emit signal if changed."""
        if self._login_error != value:
            self._login_error = value
            self.login_error_changed.emit(value or "")

    def update_from_auth_status(self, status: dict) -> None:
        """Update state from TastyTradeService.get_auth_status().

        Args:
            status: Dictionary with 'authenticated' and 'has_stored_credentials' keys
        """
        self.authenticated = status.get("authenticated", False)
        self.has_stored_credentials = status.get("has_stored_credentials", False)
