/**
 * Authentication middleware for MCP requests.
 * Verifies JWT and retrieves user's TastyTrade tokens.
 */

import type { D1Database } from "@cloudflare/workers-types";
import { verifyJWT, extractBearerToken, type JWTPayload } from "./jwt";
import { decryptTokens, type DecryptedTokens } from "./encryption";

export interface AuthEnv {
  DB: D1Database;
  JWT_SECRET: string;
  TOKEN_ENCRYPTION_KEY: string;
  TT_CLIENT_SECRET: string;
}

export interface AuthContext {
  userId: string;
  email?: string;
  tokens: DecryptedTokens;
}

interface TokenRow {
  access_token_encrypted: string;
  token_iv: string;
  expires_at: number;
}

const TT_TOKEN_URL = "https://api.tastyworks.com/oauth/token";

/**
 * Authenticate a request and return user context.
 * Returns null if authentication fails.
 */
export async function authenticateRequest(
  request: Request,
  env: AuthEnv
): Promise<AuthContext | null> {
  const authHeader = request.headers.get("Authorization");
  const token = extractBearerToken(authHeader);

  if (!token) {
    return null;
  }

  let payload: JWTPayload;
  try {
    payload = await verifyJWT(token, env.JWT_SECRET);
  } catch {
    return null;
  }

  // Get user's encrypted tokens from D1
  const tokenRow = await env.DB.prepare(
    "SELECT access_token_encrypted, token_iv, expires_at FROM user_tokens WHERE user_id = ?"
  )
    .bind(payload.sub)
    .first<TokenRow>();

  if (!tokenRow) {
    return null;
  }

  // Decrypt tokens
  let tokens: DecryptedTokens;
  try {
    tokens = await decryptTokens(
      tokenRow.access_token_encrypted,
      tokenRow.token_iv,
      env.TOKEN_ENCRYPTION_KEY
    );
  } catch {
    return null;
  }

  // Check if TastyTrade access token needs refresh
  const now = Math.floor(Date.now() / 1000);
  if (tokenRow.expires_at < now + 60) {
    // Refresh if expiring in < 1 minute
    const refreshedTokens = await refreshTastyTradeTokens(
      tokens.refreshToken,
      env
    );
    if (refreshedTokens) {
      tokens = refreshedTokens.tokens;
      // Update stored tokens
      const { encryptTokens } = await import("./encryption");
      const encrypted = await encryptTokens(
        tokens.accessToken,
        tokens.refreshToken,
        env.TOKEN_ENCRYPTION_KEY
      );
      await env.DB.prepare(
        `UPDATE user_tokens
         SET access_token_encrypted = ?, token_iv = ?, expires_at = ?, updated_at = ?
         WHERE user_id = ?`
      )
        .bind(
          encrypted.ciphertext,
          encrypted.iv,
          refreshedTokens.expiresAt,
          now,
          payload.sub
        )
        .run();
    }
  }

  return {
    userId: payload.sub,
    email: payload.email,
    tokens,
  };
}

/**
 * Refresh TastyTrade tokens using the refresh token.
 */
async function refreshTastyTradeTokens(
  refreshToken: string,
  env: AuthEnv
): Promise<{ tokens: DecryptedTokens; expiresAt: number } | null> {
  try {
    const response = await fetch(TT_TOKEN_URL, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
      },
      body: JSON.stringify({
        grant_type: "refresh_token",
        client_secret: env.TT_CLIENT_SECRET,
        refresh_token: refreshToken,
      }),
    });

    if (!response.ok) {
      console.error("Failed to refresh TastyTrade tokens:", await response.text());
      return null;
    }

    const data = (await response.json()) as {
      access_token: string;
      refresh_token: string;
      expires_in: number;
    };

    const now = Math.floor(Date.now() / 1000);
    return {
      tokens: {
        accessToken: data.access_token,
        refreshToken: data.refresh_token,
      },
      expiresAt: now + data.expires_in,
    };
  } catch (error) {
    console.error("Error refreshing TastyTrade tokens:", error);
    return null;
  }
}

/**
 * Create an unauthorized response.
 */
export function unauthorizedResponse(message = "Unauthorized"): Response {
  return Response.json(
    {
      error: "unauthorized",
      error_description: message,
    },
    {
      status: 401,
      headers: {
        "WWW-Authenticate": 'Bearer realm="ttai"',
      },
    }
  );
}
