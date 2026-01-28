"""Server configuration management."""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal


@dataclass
class ServerConfig:
    """Configuration for the TTAI MCP server."""

    transport: Literal["stdio", "sse"] = "stdio"
    host: str = "localhost"
    port: int = 8080
    log_level: str = "INFO"
    data_dir: Path = field(default_factory=lambda: Path.home() / ".ttai")

    @property
    def db_path(self) -> Path:
        """Get the path to the SQLite database."""
        return self.data_dir / "ttai.db"

    @property
    def log_dir(self) -> Path:
        """Get the path to the log directory."""
        return self.data_dir / "logs"

    @classmethod
    def from_env(cls) -> "ServerConfig":
        """Create configuration from environment variables.

        Environment variables:
            TTAI_TRANSPORT: "stdio" or "sse" (default: stdio)
            TTAI_HOST: Server host (default: localhost)
            TTAI_PORT: Server port (default: 8080)
            TTAI_LOG_LEVEL: Log level (default: INFO)
            TTAI_DATA_DIR: Data directory (default: ~/.ttai)

        Returns:
            ServerConfig instance with values from environment
        """
        transport_str = os.environ.get("TTAI_TRANSPORT", "stdio").lower()
        transport: Literal["stdio", "sse"] = "sse" if transport_str == "sse" else "stdio"

        return cls(
            transport=transport,
            host=os.environ.get("TTAI_HOST", "localhost"),
            port=int(os.environ.get("TTAI_PORT", "8080")),
            log_level=os.environ.get("TTAI_LOG_LEVEL", "INFO").upper(),
            data_dir=Path(os.environ.get("TTAI_DATA_DIR", str(Path.home() / ".ttai"))),
        )


# Global configuration instance
config = ServerConfig.from_env()
