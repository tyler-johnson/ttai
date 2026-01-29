"""About page widget."""

import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import QFrame, QLabel, QScrollArea, QVBoxLayout, QWidget


def _get_resources_dir() -> Path:
    """Get resources directory, handling PyInstaller frozen apps."""
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / "src" / "gui" / "resources"  # type: ignore[attr-defined]
    return Path(__file__).parent.parent / "resources"


def _load_rounded_icon(path: Path, size: int, radius: int, device_pixel_ratio: float) -> QPixmap:
    """Load an icon and apply rounded corners, handling high-DPI displays."""
    # Scale up for Retina/high-DPI displays
    scaled_size = int(size * device_pixel_ratio)
    scaled_radius = int(radius * device_pixel_ratio)

    source = QPixmap(str(path)).scaled(
        scaled_size, scaled_size,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )

    rounded = QPixmap(scaled_size, scaled_size)
    rounded.fill(Qt.GlobalColor.transparent)

    painter = QPainter(rounded)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    path_rect = QPainterPath()
    path_rect.addRoundedRect(0, 0, scaled_size, scaled_size, scaled_radius, scaled_radius)
    painter.setClipPath(path_rect)
    painter.drawPixmap(0, 0, source)
    painter.end()

    # Tell Qt about the device pixel ratio so it displays at correct size
    rounded.setDevicePixelRatio(device_pixel_ratio)

    return rounded


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

        # App icon
        icon_path = _get_resources_dir() / "icon.png"
        if icon_path.exists():
            icon_label = QLabel()
            dpr = self.devicePixelRatio()
            icon_label.setPixmap(_load_rounded_icon(icon_path, 96, 20, dpr))
            icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(icon_label)
            layout.addSpacing(16)

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
            "Connect via MCP for intelligent insights."
        )
        description.setAlignment(Qt.AlignmentFlag.AlignCenter)
        description.setWordWrap(True)
        layout.addWidget(description)

        layout.addStretch()
