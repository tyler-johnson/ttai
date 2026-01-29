"""SSL certificate management for HTTPS support."""

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import httpx

logger = logging.getLogger("ttai.ssl")


@dataclass
class CertificateBundle:
    """SSL certificate bundle from the cert API."""

    cert: str
    key: str
    domain: str
    expires_at: datetime
    issued_at: datetime

    @classmethod
    def from_dict(cls, data: dict) -> "CertificateBundle":
        """Create from API response dictionary."""
        return cls(
            cert=data["cert"],
            key=data["key"],
            domain=data["domain"],
            expires_at=datetime.fromisoformat(data["expires_at"].replace("Z", "+00:00")),
            issued_at=datetime.fromisoformat(data["issued_at"].replace("Z", "+00:00")),
        )

    def to_dict(self) -> dict:
        """Convert to dictionary for caching."""
        return {
            "cert": self.cert,
            "key": self.key,
            "domain": self.domain,
            "expires_at": self.expires_at.isoformat(),
            "issued_at": self.issued_at.isoformat(),
        }

    def is_expired(self) -> bool:
        """Check if the certificate is expired."""
        return datetime.now(timezone.utc) >= self.expires_at

    def days_until_expiry(self) -> float:
        """Get the number of days until the certificate expires."""
        delta = self.expires_at - datetime.now(timezone.utc)
        return delta.total_seconds() / (24 * 60 * 60)


class CertificateManager:
    """Manages SSL certificates for HTTPS server.

    Fetches certificates from the cert API and caches them locally.
    """

    # Minimum days remaining before considering a cert "expiring soon"
    REFRESH_THRESHOLD_DAYS = 7

    def __init__(self, cert_dir: Path, cert_api_url: str):
        """Initialize the certificate manager.

        Args:
            cert_dir: Directory to store certificate files
            cert_api_url: URL of the certificate API (e.g., https://api.tt-ai.dev/cert)
        """
        self.cert_dir = cert_dir
        self.cert_api_url = cert_api_url
        self._cert_path = cert_dir / "cert.pem"
        self._key_path = cert_dir / "key.pem"
        self._meta_path = cert_dir / "meta.json"

    def _ensure_cert_dir(self) -> None:
        """Ensure the certificate directory exists."""
        self.cert_dir.mkdir(parents=True, exist_ok=True)

    def _load_cached_cert(self) -> CertificateBundle | None:
        """Load cached certificate from disk.

        Returns:
            CertificateBundle if a valid cached cert exists, None otherwise
        """
        if not self._meta_path.exists():
            return None

        try:
            with open(self._meta_path) as f:
                meta = json.load(f)

            # Also verify the PEM files exist
            if not self._cert_path.exists() or not self._key_path.exists():
                return None

            # Load the cert and key content
            meta["cert"] = self._cert_path.read_text()
            meta["key"] = self._key_path.read_text()

            return CertificateBundle.from_dict(meta)
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            logger.warning(f"Failed to load cached certificate: {e}")
            return None

    def _save_cert(self, bundle: CertificateBundle) -> None:
        """Save certificate bundle to disk.

        Args:
            bundle: Certificate bundle to save
        """
        self._ensure_cert_dir()

        # Save PEM files
        self._cert_path.write_text(bundle.cert)
        self._key_path.write_text(bundle.key)

        # Save metadata (without the actual cert/key content)
        meta = {
            "domain": bundle.domain,
            "expires_at": bundle.expires_at.isoformat(),
            "issued_at": bundle.issued_at.isoformat(),
        }
        with open(self._meta_path, "w") as f:
            json.dump(meta, f, indent=2)

        # Set restrictive permissions on key file
        self._key_path.chmod(0o600)

        logger.info(f"Saved certificate for {bundle.domain}, expires {bundle.expires_at}")

    async def _fetch_from_api(self) -> CertificateBundle:
        """Fetch certificate from the cert API.

        Returns:
            CertificateBundle from the API

        Raises:
            CertificateFetchError: If the fetch fails
        """
        logger.info(f"Fetching certificate from {self.cert_api_url}")

        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.get(self.cert_api_url)
                response.raise_for_status()
                data = response.json()
                return CertificateBundle.from_dict(data)
            except httpx.HTTPStatusError as e:
                error_msg = f"Certificate API returned {e.response.status_code}"
                try:
                    error_data = e.response.json()
                    if "error" in error_data:
                        error_msg += f": {error_data['error']}"
                except Exception:
                    pass
                raise CertificateFetchError(error_msg) from e
            except httpx.RequestError as e:
                raise CertificateFetchError(f"Failed to connect to cert API: {e}") from e
            except (json.JSONDecodeError, KeyError) as e:
                raise CertificateFetchError(f"Invalid response from cert API: {e}") from e

    async def ensure_certificate(self) -> tuple[Path, Path]:
        """Ensure a valid certificate is available.

        Checks the cached certificate and fetches a new one if:
        - No cached cert exists
        - Cached cert is expired or expiring soon

        Returns:
            Tuple of (cert_path, key_path) for the PEM files

        Raises:
            CertificateFetchError: If no valid certificate can be obtained
        """
        # Check cached certificate
        cached = self._load_cached_cert()

        if cached:
            if cached.is_expired():
                logger.warning("Cached certificate is expired, fetching new one")
            elif cached.days_until_expiry() < self.REFRESH_THRESHOLD_DAYS:
                logger.info(
                    f"Certificate expires in {cached.days_until_expiry():.1f} days, "
                    "fetching refresh"
                )
            else:
                logger.info(
                    f"Using cached certificate for {cached.domain}, "
                    f"expires in {cached.days_until_expiry():.1f} days"
                )
                return self._cert_path, self._key_path

        # Fetch new certificate
        try:
            bundle = await self._fetch_from_api()
            self._save_cert(bundle)
            return self._cert_path, self._key_path
        except CertificateFetchError:
            # If we have a cached cert (even if expiring soon), use it
            if cached and not cached.is_expired():
                logger.warning(
                    "Failed to fetch new certificate, using cached cert "
                    f"(expires in {cached.days_until_expiry():.1f} days)"
                )
                return self._cert_path, self._key_path
            raise


class CertificateFetchError(Exception):
    """Error fetching certificate from the API."""

    pass
