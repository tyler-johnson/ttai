"""Credential management with Fernet encryption."""

import json
import logging
import os
import stat
from dataclasses import dataclass
from pathlib import Path

from cryptography.fernet import Fernet

logger = logging.getLogger("ttai.auth")


@dataclass
class Credentials:
    """Stored TastyTrade OAuth credentials."""

    client_secret: str
    refresh_token: str


class CredentialManager:
    """Manages encrypted credential storage for TastyTrade authentication."""

    def __init__(self, data_dir: Path) -> None:
        """Initialize the credential manager.

        Args:
            data_dir: Directory to store credentials and key files
        """
        self._data_dir = data_dir
        self._key_path = data_dir / ".key"
        self._credentials_path = data_dir / ".credentials"
        self._fernet: Fernet | None = None

    def _ensure_data_dir(self) -> None:
        """Ensure the data directory exists with proper permissions."""
        self._data_dir.mkdir(parents=True, exist_ok=True)

    def _get_or_create_key(self) -> bytes:
        """Get existing key or generate a new one.

        Returns:
            The encryption key bytes
        """
        self._ensure_data_dir()

        if self._key_path.exists():
            return self._key_path.read_bytes()

        key = Fernet.generate_key()
        self._key_path.write_bytes(key)
        os.chmod(self._key_path, stat.S_IRUSR | stat.S_IWUSR)  # 0o600
        logger.info(f"Generated new encryption key at {self._key_path}")
        return key

    def _get_fernet(self) -> Fernet:
        """Get or create the Fernet instance.

        Returns:
            Fernet instance for encryption/decryption
        """
        if self._fernet is None:
            key = self._get_or_create_key()
            self._fernet = Fernet(key)
        return self._fernet

    def store_credentials(
        self,
        client_secret: str,
        refresh_token: str,
    ) -> None:
        """Store OAuth credentials encrypted on disk.

        Args:
            client_secret: TastyTrade OAuth client secret
            refresh_token: TastyTrade OAuth refresh token
        """
        self._ensure_data_dir()
        fernet = self._get_fernet()

        data = {
            "client_secret": client_secret,
            "refresh_token": refresh_token,
        }
        encrypted = fernet.encrypt(json.dumps(data).encode())
        self._credentials_path.write_bytes(encrypted)
        os.chmod(self._credentials_path, stat.S_IRUSR | stat.S_IWUSR)  # 0o600
        logger.info("Credentials stored successfully")

    def load_credentials(self) -> Credentials | None:
        """Load credentials from encrypted storage.

        Returns:
            Credentials if found, None otherwise
        """
        if not self._credentials_path.exists():
            return None

        try:
            fernet = self._get_fernet()
            encrypted = self._credentials_path.read_bytes()
            decrypted = fernet.decrypt(encrypted)
            data = json.loads(decrypted.decode())
            return Credentials(
                client_secret=data["client_secret"],
                refresh_token=data["refresh_token"],
            )
        except Exception as e:
            logger.error(f"Failed to load credentials: {e}")
            return None

    def clear_credentials(self) -> None:
        """Remove stored credentials."""
        if self._credentials_path.exists():
            self._credentials_path.unlink()
            logger.info("Credentials cleared")

    def has_credentials(self) -> bool:
        """Check if credentials are stored.

        Returns:
            True if credentials exist, False otherwise
        """
        return self._credentials_path.exists()
