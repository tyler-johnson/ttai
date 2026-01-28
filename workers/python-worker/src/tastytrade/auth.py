"""TastyTrade OAuth authentication."""

import httpx

API_URL = "https://api.tastyworks.com"
API_VERSION = "20251101"


async def get_access_token(client_secret: str, refresh_token: str) -> str:
    """
    Get an access token using client_secret and refresh_token.

    Args:
        client_secret: OAuth client secret for your provider
        refresh_token: Refresh token for the user

    Returns:
        Access token string

    Raises:
        httpx.HTTPStatusError: If the authentication request fails
    """
    async with httpx.AsyncClient(base_url=API_URL) as client:
        response = await client.post(
            "/oauth/token",
            json={
                "grant_type": "refresh_token",
                "client_secret": client_secret,
                "refresh_token": refresh_token,
            },
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
        )
        response.raise_for_status()
        data = response.json()
        return data["access_token"]
