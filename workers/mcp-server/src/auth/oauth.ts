/**
 * OAuth handlers for TastyTrade authentication.
 * Implements OAuth 2.0 with PKCE.
 */

import type { D1Database } from "@cloudflare/workers-types";
import { encryptTokens } from "./encryption";
import { createJWT } from "./jwt";

const TT_AUTH_URL = "https://api.tastyworks.com/oauth/authorize";
const TT_TOKEN_URL = "https://api.tastyworks.com/oauth/token";
const TT_ACCOUNT_URL = "https://api.tastyworks.com/customers/me";
const OAUTH_STATE_TTL = 10 * 60; // 10 minutes

export interface OAuthEnv {
  DB: D1Database;
  TT_CLIENT_ID: string;
  TT_CLIENT_SECRET: string;
  JWT_SECRET: string;
  TOKEN_ENCRYPTION_KEY: string;
}

/**
 * Generate a random string for OAuth state and PKCE.
 */
function generateRandomString(length: number): string {
  const bytes = crypto.getRandomValues(new Uint8Array(length));
  return btoa(String.fromCharCode(...bytes))
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=/g, "")
    .slice(0, length);
}

/**
 * Generate PKCE code verifier and challenge.
 */
async function generatePKCE(): Promise<{
  codeVerifier: string;
  codeChallenge: string;
}> {
  const codeVerifier = generateRandomString(64);
  const encoder = new TextEncoder();
  const data = encoder.encode(codeVerifier);
  const digest = await crypto.subtle.digest("SHA-256", data);
  const codeChallenge = btoa(String.fromCharCode(...new Uint8Array(digest)))
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=/g, "");
  return { codeVerifier, codeChallenge };
}

/**
 * OAuth Authorization Server Metadata (RFC 8414).
 * Used by mcp-remote for automatic discovery.
 */
export function handleOAuthDiscovery(baseUrl: string): Response {
  const metadata = {
    issuer: baseUrl,
    authorization_endpoint: `${baseUrl}/oauth/authorize`,
    token_endpoint: `${baseUrl}/oauth/token`,
    response_types_supported: ["code"],
    grant_types_supported: ["authorization_code", "refresh_token"],
    code_challenge_methods_supported: ["S256"],
    token_endpoint_auth_methods_supported: ["none"],
  };

  return Response.json(metadata, {
    headers: {
      "Cache-Control": "public, max-age=3600",
    },
  });
}

/**
 * Start OAuth authorization flow.
 * Redirects user to TastyTrade login.
 */
export async function handleAuthorize(
  request: Request,
  env: OAuthEnv
): Promise<Response> {
  const url = new URL(request.url);
  const redirectUri = url.searchParams.get("redirect_uri");

  if (!redirectUri) {
    return Response.json(
      { error: "redirect_uri is required" },
      { status: 400 }
    );
  }

  // Generate state and PKCE
  const state = generateRandomString(32);
  const { codeVerifier, codeChallenge } = await generatePKCE();

  // Store state in D1 for verification on callback
  const expiresAt = Math.floor(Date.now() / 1000) + OAUTH_STATE_TTL;
  await env.DB.prepare(
    "INSERT INTO oauth_state (state, code_verifier, redirect_uri, expires_at) VALUES (?, ?, ?, ?)"
  )
    .bind(state, codeVerifier, redirectUri, expiresAt)
    .run();

  // Build TastyTrade authorization URL
  const baseUrl = `${url.protocol}//${url.host}`;
  const callbackUrl = `${baseUrl}/oauth/callback`;

  const authUrl = new URL(TT_AUTH_URL);
  authUrl.searchParams.set("client_id", env.TT_CLIENT_ID);
  authUrl.searchParams.set("redirect_uri", callbackUrl);
  authUrl.searchParams.set("response_type", "code");
  authUrl.searchParams.set("state", state);
  authUrl.searchParams.set("code_challenge", codeChallenge);
  authUrl.searchParams.set("code_challenge_method", "S256");

  return Response.redirect(authUrl.toString(), 302);
}

/**
 * Handle OAuth callback from TastyTrade.
 * Exchanges code for tokens and creates JWT session.
 */
export async function handleCallback(
  request: Request,
  env: OAuthEnv
): Promise<Response> {
  const url = new URL(request.url);
  const code = url.searchParams.get("code");
  const state = url.searchParams.get("state");
  const error = url.searchParams.get("error");

  if (error) {
    const errorDescription = url.searchParams.get("error_description") || error;
    return Response.json({ error: errorDescription }, { status: 400 });
  }

  if (!code || !state) {
    return Response.json(
      { error: "Missing code or state parameter" },
      { status: 400 }
    );
  }

  // Verify state and get code verifier
  const stateRow = await env.DB.prepare(
    "SELECT code_verifier, redirect_uri, expires_at FROM oauth_state WHERE state = ?"
  )
    .bind(state)
    .first<{ code_verifier: string; redirect_uri: string; expires_at: number }>();

  if (!stateRow) {
    return Response.json({ error: "Invalid state" }, { status: 400 });
  }

  // Clean up used state
  await env.DB.prepare("DELETE FROM oauth_state WHERE state = ?")
    .bind(state)
    .run();

  // Check expiration
  const now = Math.floor(Date.now() / 1000);
  if (stateRow.expires_at < now) {
    return Response.json({ error: "State expired" }, { status: 400 });
  }

  // Exchange code for tokens
  const baseUrl = `${url.protocol}//${url.host}`;
  const callbackUrl = `${baseUrl}/oauth/callback`;

  const tokenResponse = await fetch(TT_TOKEN_URL, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "application/json",
    },
    body: JSON.stringify({
      grant_type: "authorization_code",
      code,
      redirect_uri: callbackUrl,
      client_id: env.TT_CLIENT_ID,
      client_secret: env.TT_CLIENT_SECRET,
      code_verifier: stateRow.code_verifier,
    }),
  });

  if (!tokenResponse.ok) {
    const errorData = await tokenResponse.text();
    console.error("Token exchange failed:", errorData);
    return Response.json(
      { error: "Failed to exchange code for tokens" },
      { status: 500 }
    );
  }

  const tokens = (await tokenResponse.json()) as {
    access_token: string;
    refresh_token: string;
    expires_in: number;
  };

  // Get user info from TastyTrade
  const userResponse = await fetch(TT_ACCOUNT_URL, {
    headers: {
      Authorization: `Bearer ${tokens.access_token}`,
      Accept: "application/json",
    },
  });

  let userId: string;
  let email: string | undefined;

  if (userResponse.ok) {
    const userData = (await userResponse.json()) as {
      data: {
        id: string;
        email?: string;
      };
    };
    userId = userData.data.id;
    email = userData.data.email;
  } else {
    // Fallback: generate a unique ID if we can't get user info
    userId = crypto.randomUUID();
  }

  // Store user and encrypted tokens
  await env.DB.prepare(
    "INSERT OR REPLACE INTO users (id, email) VALUES (?, ?)"
  )
    .bind(userId, email || null)
    .run();

  const encrypted = await encryptTokens(
    tokens.access_token,
    tokens.refresh_token,
    env.TOKEN_ENCRYPTION_KEY
  );

  const expiresAt = now + tokens.expires_in;
  await env.DB.prepare(
    `INSERT OR REPLACE INTO user_tokens
     (user_id, access_token_encrypted, refresh_token_encrypted, token_iv, expires_at, updated_at)
     VALUES (?, ?, ?, ?, ?, ?)`
  )
    .bind(
      userId,
      encrypted.ciphertext,
      encrypted.ciphertext, // We store both tokens together in ciphertext
      encrypted.iv,
      expiresAt,
      now
    )
    .run();

  // Create session JWT
  const jwt = await createJWT(userId, email, env.JWT_SECRET);

  // Redirect back to the original client with the JWT
  const redirectUrl = new URL(stateRow.redirect_uri);
  redirectUrl.searchParams.set("access_token", jwt);
  redirectUrl.searchParams.set("token_type", "Bearer");

  return Response.redirect(redirectUrl.toString(), 302);
}

/**
 * Token endpoint for exchanging authorization code.
 * Called by mcp-remote after receiving the callback.
 */
export async function handleToken(
  request: Request,
  env: OAuthEnv
): Promise<Response> {
  if (request.method !== "POST") {
    return Response.json({ error: "Method not allowed" }, { status: 405 });
  }

  const contentType = request.headers.get("content-type") || "";
  let body: Record<string, string>;

  if (contentType.includes("application/json")) {
    body = await request.json();
  } else if (contentType.includes("application/x-www-form-urlencoded")) {
    const formData = await request.formData();
    const entries: [string, string][] = [];
    formData.forEach((value, key) => {
      entries.push([key, String(value)]);
    });
    body = Object.fromEntries(entries);
  } else {
    return Response.json(
      { error: "Unsupported content type" },
      { status: 415 }
    );
  }

  const grantType = body.grant_type;

  if (grantType === "authorization_code") {
    // This is handled via the redirect flow, but we support it for compatibility
    return Response.json(
      { error: "Use the authorization flow via /oauth/authorize" },
      { status: 400 }
    );
  }

  if (grantType === "refresh_token") {
    // Refresh the JWT session (not TastyTrade tokens - those refresh automatically)
    const refreshToken = body.refresh_token;
    if (!refreshToken) {
      return Response.json(
        { error: "refresh_token is required" },
        { status: 400 }
      );
    }

    // For now, we don't support refresh_token grant - sessions last 24h
    return Response.json(
      { error: "Session refresh not supported. Please re-authenticate." },
      { status: 400 }
    );
  }

  return Response.json({ error: "Unsupported grant type" }, { status: 400 });
}

/**
 * Clean up expired OAuth states (call periodically).
 */
export async function cleanupExpiredStates(db: D1Database): Promise<void> {
  const now = Math.floor(Date.now() / 1000);
  await db.prepare("DELETE FROM oauth_state WHERE expires_at < ?").bind(now).run();
}
