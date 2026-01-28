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
    """Stored TastyTrade credentials."""

    username: str
    password: str
    remember_token: str | None = None


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
        username: str,
        password: str,
        remember_token: str | None = None,
    ) -> None:
        """Store credentials encrypted on disk.

        Args:
            username: TastyTrade username
            password: TastyTrade password
            remember_token: Optional remember token for session restore
        """
        self._ensure_data_dir()
        fernet = self._get_fernet()

        data = {
            "username": username,
            "password": password,
            "remember_token": remember_token,
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
                username=data["username"],
                password=data["password"],
                remember_token=data.get("remember_token"),
            )
        except Exception as e:
            logger.error(f"Failed to load credentials: {e}")
            return None

    def update_remember_token(self, remember_token: str) -> bool:
        """Update the stored remember token.

        Args:
            remember_token: New remember token

        Returns:
            True if successful, False otherwise
        """
        credentials = self.load_credentials()
        if credentials is None:
            return False

        self.store_credentials(
            username=credentials.username,
            password=credentials.password,
            remember_token=remember_token,
        )
        return True

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
