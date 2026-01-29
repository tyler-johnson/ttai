"""Login dialog for TastyTrade authentication."""

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

TASTYTRADE_API_URL = "https://my.tastytrade.com/app.html#/manage/api-access"


class LoginDialog(QDialog):
    """Native dialog for TastyTrade login credentials."""

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialize the login dialog."""
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self) -> None:
        """Set up the dialog UI."""
        self.setWindowTitle("Connect to TastyTrade")
        self.setModal(True)
        self.setFixedWidth(450)

        layout = QVBoxLayout(self)
        layout.setSpacing(16)

        # Instructions
        instructions = QLabel("Enter your TastyTrade API credentials:")
        layout.addWidget(instructions)

        # Form
        form = QFormLayout()
        form.setSpacing(8)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)

        self.client_secret_input = QLineEdit()
        self.client_secret_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.client_secret_input.setPlaceholderText("Enter client secret")
        form.addRow("Client Secret:", self.client_secret_input)

        self.refresh_token_input = QLineEdit()
        self.refresh_token_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.refresh_token_input.setPlaceholderText("Enter refresh token")
        form.addRow("Refresh Token:", self.refresh_token_input)

        layout.addLayout(form)

        # Error label
        self.error_label = QLabel()
        self.error_label.setWordWrap(True)
        self.error_label.setStyleSheet("color: red;")
        self.error_label.hide()
        layout.addWidget(self.error_label)

        # Buttons row: Get Credentials... | spacer | Cancel | Connect
        btn_layout = QHBoxLayout()

        self.get_creds_btn = QPushButton("Get Credentials...")
        self.get_creds_btn.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl(TASTYTRADE_API_URL))
        )
        btn_layout.addWidget(self.get_creds_btn)

        btn_layout.addStretch()

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(self.cancel_btn)

        self.connect_btn = QPushButton("Connect")
        self.connect_btn.setDefault(True)
        btn_layout.addWidget(self.connect_btn)

        layout.addLayout(btn_layout)

        self.client_secret_input.setFocus()

    def get_credentials(self) -> tuple[str, str]:
        """Get the entered credentials."""
        return (
            self.client_secret_input.text().strip(),
            self.refresh_token_input.text().strip(),
        )

    def set_error(self, error: str) -> None:
        """Display an error message."""
        if error:
            self.error_label.setText(error)
            self.error_label.show()
        else:
            self.error_label.hide()

    def set_loading(self, loading: bool) -> None:
        """Set the loading state."""
        self.connect_btn.setEnabled(not loading)
        self.connect_btn.setText("Connecting..." if loading else "Connect")
        self.cancel_btn.setEnabled(not loading)
        self.get_creds_btn.setEnabled(not loading)
        self.client_secret_input.setEnabled(not loading)
        self.refresh_token_input.setEnabled(not loading)

    def clear(self) -> None:
        """Clear the form."""
        self.client_secret_input.clear()
        self.refresh_token_input.clear()
        self.error_label.hide()
