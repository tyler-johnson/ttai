"""TastyTrade API service using the official SDK."""

import logging
from dataclasses import dataclass

from tastytrade import Session
from tastytrade.dxfeed import Quote

from src.auth.credentials import CredentialManager
from src.services.cache import CacheService

logger = logging.getLogger("ttai.tastytrade")

QUOTE_CACHE_TTL = 60.0  # seconds


@dataclass
class QuoteData:
    """Simplified quote data."""

    symbol: str
    bid: float | None
    ask: float | None
    last: float | None


class TastyTradeService:
    """Service for interacting with TastyTrade API."""

    def __init__(
        self,
        credential_manager: CredentialManager,
        cache: CacheService,
    ) -> None:
        """Initialize the TastyTrade service.

        Args:
            credential_manager: Manager for credential storage
            cache: Cache service for quote caching
        """
        self._credential_manager = credential_manager
        self._cache = cache
        self._session: Session | None = None

    @property
    def is_authenticated(self) -> bool:
        """Check if we have an active session."""
        return self._session is not None

    @property
    def username(self) -> str | None:
        """Get the current session username."""
        if self._session is None:
            return None
        credentials = self._credential_manager.load_credentials()
        return credentials.username if credentials else None

    async def login(
        self,
        username: str,
        password: str,
        remember_me: bool = False,
    ) -> bool:
        """Authenticate with TastyTrade.

        Args:
            username: TastyTrade username
            password: TastyTrade password
            remember_me: Whether to store credentials for session restore

        Returns:
            True if login successful, False otherwise
        """
        try:
            self._session = Session(username, password, remember_me=remember_me)
            logger.info(f"Successfully logged in as {username}")

            if remember_me:
                remember_token = self._session.remember_token
                self._credential_manager.store_credentials(
                    username=username,
                    password=password,
                    remember_token=remember_token,
                )

            return True
        except Exception as e:
            logger.error(f"Login failed: {e}")
            self._session = None
            return False

    async def restore_session(self) -> bool:
        """Attempt to restore session from stored credentials.

        Returns:
            True if session restored successfully, False otherwise
        """
        credentials = self._credential_manager.load_credentials()
        if credentials is None:
            return False

        # Try remember token first
        if credentials.remember_token:
            try:
                self._session = Session(
                    credentials.username,
                    remember_token=credentials.remember_token,
                )
                logger.info(f"Session restored for {credentials.username} using remember token")
                return True
            except Exception as e:
                logger.warning(f"Failed to restore session with remember token: {e}")

        # Fall back to username/password
        try:
            self._session = Session(credentials.username, credentials.password)
            logger.info(f"Session restored for {credentials.username} using password")
            return True
        except Exception as e:
            logger.error(f"Failed to restore session: {e}")
            return False

    async def logout(self, clear_credentials: bool = True) -> None:
        """Log out and optionally clear stored credentials.

        Args:
            clear_credentials: Whether to remove stored credentials
        """
        if self._session:
            try:
                self._session.destroy()
            except Exception as e:
                logger.warning(f"Error destroying session: {e}")

        self._session = None

        if clear_credentials:
            self._credential_manager.clear_credentials()

        logger.info("Logged out successfully")

    async def get_quote(self, symbol: str) -> QuoteData | None:
        """Get quote data for a symbol.

        Args:
            symbol: The ticker symbol

        Returns:
            QuoteData if successful, None otherwise
        """
        if not self.is_authenticated:
            logger.error("Not authenticated")
            return None

        symbol = symbol.upper()
        cache_key = f"quote:{symbol}"

        # Check cache first
        cached = self._cache.get(cache_key)
        if cached is not None:
            logger.debug(f"Cache hit for {symbol}")
            return cached

        try:
            # Get quote from API
            quotes = Quote.get_quotes(self._session, [symbol])

            if not quotes or symbol not in quotes:
                logger.warning(f"No quote data for {symbol}")
                return None

            quote = quotes[symbol]
            quote_data = QuoteData(
                symbol=symbol,
                bid=quote.bid_price if hasattr(quote, "bid_price") else None,
                ask=quote.ask_price if hasattr(quote, "ask_price") else None,
                last=quote.last_price if hasattr(quote, "last_price") else None,
            )

            # Cache the result
            self._cache.set(cache_key, quote_data, ttl=QUOTE_CACHE_TTL)
            logger.debug(f"Fetched quote for {symbol}: {quote_data}")

            return quote_data
        except Exception as e:
            logger.error(f"Failed to get quote for {symbol}: {e}")
            return None

    def get_auth_status(self) -> dict:
        """Get current authentication status.

        Returns:
            Dictionary with authentication status details
        """
        return {
            "authenticated": self.is_authenticated,
            "username": self.username,
            "has_stored_credentials": self._credential_manager.has_credentials(),
        }
