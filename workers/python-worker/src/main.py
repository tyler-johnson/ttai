"""Python worker entry point for TastyTrade API calls."""

import json
from workers import Response
from tastytrade import TastyTradeClient


async def on_fetch(request, env):
    """Handle incoming requests."""
    url_str = request.url
    # Parse URL path
    path = "/" + url_str.split("/", 3)[-1].split("?")[0] if "/" in url_str else "/"

    # Health check
    if path == "/health":
        return Response.json(
            {
                "status": "healthy",
                "service": "ttai-python-worker",
                "environment": getattr(env, "ENVIRONMENT", "unknown"),
                "has_credentials": bool(
                    getattr(env, "TT_CLIENT_SECRET", None) and
                    getattr(env, "TT_REFRESH_TOKEN", None)
                ),
            }
        )

    # Quote endpoint
    if path == "/quotes":
        if request.method != "POST":
            return Response(
                "Method Not Allowed",
                status=405,
                headers={"Allow": "POST"},
            )

        try:
            # Parse request body
            body_text = await request.text()
            body = json.loads(body_text) if body_text else {}
            symbols = body.get("symbols", [])

            if not symbols:
                return Response.json(
                    {"error": "No symbols provided"},
                    status=400,
                )

            # Normalize symbols
            if isinstance(symbols, str):
                symbols = [symbols]

            # Get credentials from environment
            client_secret = getattr(env, "TT_CLIENT_SECRET", None)
            refresh_token = getattr(env, "TT_REFRESH_TOKEN", None)

            if not client_secret or not refresh_token:
                return Response.json(
                    {"error": "TastyTrade credentials not configured"},
                    status=500,
                )

            # Create client and fetch quotes
            client = TastyTradeClient(client_secret, refresh_token)

            # For single symbol, use get_quote for cleaner response
            if len(symbols) == 1:
                quote = await client.get_quote(symbols[0])
                return Response.json({"data": quote})

            # For multiple symbols, use get_market_metrics directly
            data = await client.get_market_metrics(symbols)
            return Response.json(data)

        except json.JSONDecodeError:
            return Response.json(
                {"error": "Invalid JSON in request body"},
                status=400,
            )
        except Exception as e:
            return Response.json(
                {"error": str(e)},
                status=500,
            )

    # Not found
    return Response("Not Found", status=404)
