"""TTAI PySide6 application with asyncio integration."""

import asyncio
import logging
import signal
import sys
from typing import TYPE_CHECKING

from PySide6.QtWidgets import QApplication
from qasync import QEventLoop

from src.auth.credentials import CredentialManager
from src.gui.main_window import MainWindow
from src.gui.state import AppState
from src.server.config import ServerConfig
from src.services.cache import CacheService
from src.services.tastytrade import TastyTradeService

if TYPE_CHECKING:
    from mcp.server import Server

logger = logging.getLogger("ttai.gui")


class TTAIApplication:
    """Main application class managing Qt app and services."""

    def __init__(
        self,
        config: ServerConfig,
        mcp_server: "Server | None" = None,
        tastytrade_service: "TastyTradeService | None" = None,
    ) -> None:
        """Initialize the TTAI application.

        Args:
            config: Server configuration
            mcp_server: Optional MCP server to run alongside the GUI
            tastytrade_service: Optional shared TastyTrade service instance
        """
        self.config = config
        self.mcp_server = mcp_server
        self._server_task: asyncio.Task | None = None
        self._shutting_down = False

        # Initialize Qt application
        self.app = QApplication(sys.argv)
        self.app.setApplicationName("TTAI")
        self.app.setOrganizationName("TTAI")
        self.app.aboutToQuit.connect(self._on_about_to_quit)

        # Set up asyncio event loop with Qt integration
        self.loop = QEventLoop(self.app)
        asyncio.set_event_loop(self.loop)

        # Use shared service if provided, otherwise create new
        if tastytrade_service is not None:
            self.tastytrade_service = tastytrade_service
            self.credential_manager = tastytrade_service._credential_manager
        else:
            self.credential_manager = CredentialManager(config.data_dir)
            self.cache_service = CacheService()
            self.tastytrade_service = TastyTradeService(
                self.credential_manager, self.cache_service
            )

        # Initialize state
        self.state = AppState()

        # Initialize main window
        self.main_window = MainWindow(
            state=self.state,
            tastytrade_service=self.tastytrade_service,
            credential_manager=self.credential_manager,
            config=self.config,
        )

    def run(self) -> int:
        """Run the application.

        Returns:
            Exit code
        """
        # Update initial state
        self.state.update_from_auth_status(self.tastytrade_service.get_auth_status())

        # Show the main window
        self.main_window.show()

        # Schedule session restore
        asyncio.ensure_future(self._restore_session())

        # Start MCP server if provided
        if self.mcp_server is not None:
            self._server_task = asyncio.ensure_future(self._run_mcp_server())

        # Handle Ctrl+C gracefully
        for sig in (signal.SIGINT, signal.SIGTERM):
            self.loop.add_signal_handler(sig, self._handle_signal)

        # Run the event loop
        with self.loop:
            try:
                return self.loop.run_forever()
            finally:
                self._cleanup()

    def _handle_signal(self) -> None:
        """Handle SIGINT/SIGTERM for graceful shutdown."""
        logger.info("Received shutdown signal")
        self.app.quit()

    def _on_about_to_quit(self) -> None:
        """Handle Qt app about to quit."""
        self._shutting_down = True
        if self._server_task and not self._server_task.done():
            self._server_task.cancel()

    def _cleanup(self) -> None:
        """Clean up resources on shutdown."""
        # Cancel any pending tasks
        for task in asyncio.all_tasks(self.loop):
            if not task.done():
                task.cancel()

    async def _run_mcp_server(self) -> None:
        """Run the MCP server in the background."""
        from src.server.main import _run_http_with_ssl

        logger.info("Starting MCP server in background...")
        try:
            await _run_http_with_ssl(self.mcp_server, self.config)
        except asyncio.CancelledError:
            logger.info("MCP server stopped")
        except Exception as e:
            if not self._shutting_down:
                logger.error(f"MCP server error: {e}")

    async def _restore_session(self) -> None:
        """Attempt to restore session from stored credentials."""
        if self.credential_manager.has_credentials():
            logger.info("Attempting to restore session from stored credentials")
            self.state.is_logging_in = True
            try:
                success = await self.tastytrade_service.restore_session()
                if success:
                    logger.info("Session restored successfully")
                else:
                    logger.warning("Failed to restore session")
            except Exception as e:
                logger.error(f"Error restoring session: {e}")
            finally:
                self.state.is_logging_in = False
                self.state.update_from_auth_status(
                    self.tastytrade_service.get_auth_status()
                )


def run_gui(
    config: ServerConfig,
    mcp_server: "Server | None" = None,
    tastytrade_service: "TastyTradeService | None" = None,
) -> int:
    """Run the TTAI GUI application.

    Args:
        config: Server configuration
        mcp_server: Optional MCP server to run alongside the GUI
        tastytrade_service: Optional shared TastyTrade service instance

    Returns:
        Exit code
    """
    app = TTAIApplication(config, mcp_server, tastytrade_service)
    return app.run()
