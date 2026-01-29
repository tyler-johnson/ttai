"""Server configuration management."""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal


@dataclass
class ServerConfig:
    """Configuration for the TTAI MCP server."""

    transport: Literal["stdio", "http"] = "http"
    host: str = "localhost"
    port: int = 5180
    log_level: str = "INFO"
    data_dir: Path = field(default_factory=lambda: Path.home() / ".ttai")

    # SSL configuration
    ssl_domain: str = "tt-ai.dev"  # Base domain for SSL
    ssl_port: int = 5181  # HTTPS port
    ssl_cert_api_override: str = ""  # Override cert API URL (for local dev)

    @property
    def db_path(self) -> Path:
        """Get the path to the SQLite database."""
        return self.data_dir / "ttai.db"

    @property
    def log_dir(self) -> Path:
        """Get the path to the log directory."""
        return self.data_dir / "logs"

    @property
    def ssl_cert_dir(self) -> Path:
        """Get the path to the SSL certificate directory."""
        return self.data_dir / "ssl"

    @property
    def ssl_cert_api(self) -> str:
        """Get the URL for the certificate API."""
        if self.ssl_cert_api_override:
            return self.ssl_cert_api_override
        return f"https://api.{self.ssl_domain}/cert" if self.ssl_domain else ""

    @property
    def ssl_local_domain(self) -> str:
        """Get the local domain for HTTPS server."""
        return f"local.{self.ssl_domain}" if self.ssl_domain else ""

    @property
    def ssl_enabled(self) -> bool:
        """Check if SSL is configured."""
        return bool(self.ssl_domain)

    @classmethod
    def from_env(cls) -> "ServerConfig":
        """Create configuration from environment variables.

        Environment variables:
            TTAI_TRANSPORT: "stdio" or "http" (default: http)
            TTAI_HOST: Server host (default: localhost)
            TTAI_PORT: Server port (default: 5180)
            TTAI_LOG_LEVEL: Log level (default: INFO)
            TTAI_DATA_DIR: Data directory (default: ~/.ttai)
            TTAI_SSL_DOMAIN: Base domain for SSL (default: tt-ai.dev)
            TTAI_SSL_PORT: HTTPS port (default: 5181)

        Returns:
            ServerConfig instance with values from environment
        """
        transport_str = os.environ.get("TTAI_TRANSPORT", "http").lower()
        transport: Literal["stdio", "http"] = "stdio" if transport_str == "stdio" else "http"

        return cls(
            transport=transport,
            host=os.environ.get("TTAI_HOST", "localhost"),
            port=int(os.environ.get("TTAI_PORT", "5180")),
            log_level=os.environ.get("TTAI_LOG_LEVEL", "INFO").upper(),
            data_dir=Path(os.environ.get("TTAI_DATA_DIR", str(Path.home() / ".ttai"))),
            ssl_domain=os.environ.get("TTAI_SSL_DOMAIN", "tt-ai.dev"),
            ssl_port=int(os.environ.get("TTAI_SSL_PORT", "5181")),
            ssl_cert_api_override=os.environ.get("TTAI_SSL_CERT_API", ""),
        )


# Global configuration instance
config = ServerConfig.from_env()
