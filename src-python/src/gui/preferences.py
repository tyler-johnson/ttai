"""Persistent preferences using QSettings."""

from PySide6.QtCore import QSettings


class PreferencesManager:
    """Manages persistent application preferences using QSettings.

    QSettings automatically stores preferences in platform-appropriate locations:
    - macOS: ~/Library/Preferences/com.ttai.TTAI.plist
    - Windows: HKEY_CURRENT_USER\\Software\\TTAI\\TTAI
    - Linux: ~/.config/TTAI/TTAI.conf
    """

    # Setting keys
    KEY_SHOW_WINDOW_ON_LAUNCH = "window/show_on_launch"
    KEY_IS_FIRST_RUN = "app/is_first_run"

    def __init__(self) -> None:
        """Initialize the preferences manager.

        Note: QSettings uses the application name and organization name
        set on QApplication, so ensure those are set before creating this.
        """
        self._settings = QSettings()

    @property
    def show_window_on_launch(self) -> bool:
        """Whether to show the settings window when the app launches.

        Defaults to True for first run, then remembers user preference.
        """
        if self.is_first_run:
            return True
        return self._settings.value(self.KEY_SHOW_WINDOW_ON_LAUNCH, True, type=bool)

    @show_window_on_launch.setter
    def show_window_on_launch(self, value: bool) -> None:
        """Set whether to show the settings window on launch."""
        self._settings.setValue(self.KEY_SHOW_WINDOW_ON_LAUNCH, value)

    @property
    def is_first_run(self) -> bool:
        """Whether this is the first time the app has been run."""
        return self._settings.value(self.KEY_IS_FIRST_RUN, True, type=bool)

    def mark_first_run_complete(self) -> None:
        """Mark that the first run is complete."""
        self._settings.setValue(self.KEY_IS_FIRST_RUN, False)

    def sync(self) -> None:
        """Force sync settings to disk."""
        self._settings.sync()
