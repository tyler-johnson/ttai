"""About page widget."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QLabel, QScrollArea, QVBoxLayout, QWidget


class AboutPage(QScrollArea):
    """About page showing app information."""

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialize the about page."""
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self) -> None:
        """Set up the about page UI."""
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setFrameShape(QFrame.Shape.NoFrame)

        content = QWidget()
        self.setWidget(content)

        layout = QVBoxLayout(content)
        layout.setContentsMargins(40, 40, 40, 40)

        # App name
        title = QLabel("TTAI")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        font = title.font()
        font.setPointSize(24)
        font.setBold(True)
        title.setFont(font)
        layout.addWidget(title)

        # Subtitle
        subtitle = QLabel("TastyTrade AI Assistant")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(subtitle)

        layout.addSpacing(20)

        # Version
        version = QLabel("Version 0.1.0")
        version.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(version)

        layout.addSpacing(10)

        # Description
        description = QLabel(
            "AI-powered trading analysis using the TastyTrade API.\n"
            "Connect with Claude Desktop via MCP for intelligent insights."
        )
        description.setAlignment(Qt.AlignmentFlag.AlignCenter)
        description.setWordWrap(True)
        layout.addWidget(description)

        layout.addStretch()
