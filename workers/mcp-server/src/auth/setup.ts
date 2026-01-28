/**
 * Credential setup flow for TastyTrade authentication.
 * Users input their client_secret + refresh_token from TastyTrade dashboard.
 */

import type { D1Database } from "@cloudflare/workers-types";
import { encryptTokens } from "./encryption";
import { createJWT } from "./jwt";

const TT_TOKEN_URL = "https://api.tastyworks.com/oauth/token";
const TT_ACCOUNT_URL = "https://api.tastyworks.com/customers/me";

export interface SetupEnv {
  DB: D1Database;
  JWT_SECRET: string;
  TOKEN_ENCRYPTION_KEY: string;
}

/**
 * Serve the credential setup form.
 */
export function handleSetupForm(baseUrl: string): Response {
  const html = `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>TTAI - TastyTrade Setup</title>
  <style>
    * { box-sizing: border-box; }
    body {
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
      max-width: 500px;
      margin: 40px auto;
      padding: 20px;
      background: #f5f5f5;
    }
    .card {
      background: white;
      border-radius: 8px;
      padding: 24px;
      box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    }
    h1 { margin-top: 0; color: #333; }
    p { color: #666; line-height: 1.5; }
    label {
      display: block;
      margin-bottom: 4px;
      font-weight: 500;
      color: #333;
    }
    input {
      width: 100%;
      padding: 10px;
      margin-bottom: 16px;
      border: 1px solid #ddd;
      border-radius: 4px;
      font-size: 14px;
    }
    input:focus {
      outline: none;
      border-color: #007bff;
    }
    button {
      width: 100%;
      padding: 12px;
      background: #007bff;
      color: white;
      border: none;
      border-radius: 4px;
      font-size: 16px;
      cursor: pointer;
    }
    button:hover { background: #0056b3; }
    .help {
      margin-top: 16px;
      padding: 12px;
      background: #f8f9fa;
      border-radius: 4px;
      font-size: 13px;
    }
    .help a { color: #007bff; }
    .error {
      background: #fee;
      color: #c00;
      padding: 12px;
      border-radius: 4px;
      margin-bottom: 16px;
    }
  </style>
</head>
<body>
  <div class="card">
    <h1>Connect TastyTrade</h1>
    <p>Enter your TastyTrade API credentials to connect your account.</p>

    <form method="POST" action="${baseUrl}/auth/setup">
      <label for="client_secret">Client Secret</label>
      <input type="password" id="client_secret" name="client_secret" required
             placeholder="Your OAuth app client secret">

      <label for="refresh_token">Refresh Token</label>
      <input type="password" id="refresh_token" name="refresh_token" required
             placeholder="Your refresh token">

      <button type="submit">Connect Account</button>
    </form>

    <div class="help">
      <strong>Where do I get these?</strong><br>
      1. Go to <a href="https://my.tastytrade.com/app.html#/manage/api-access/oauth-applications" target="_blank">TastyTrade API Access</a><br>
      2. Create or select your OAuth application<br>
      3. Copy the Client Secret<br>
      4. Generate a Refresh Token
    </div>
  </div>
</body>
</html>`;

  return new Response(html, {
    headers: { "Content-Type": "text/html" },
  });
}

/**
 * Handle credential form submission.
 */
export async function handleSetupSubmit(
  request: Request,
  env: SetupEnv
): Promise<Response> {
  const formData = await request.formData();
  const clientSecret = formData.get("client_secret") as string;
  const refreshToken = formData.get("refresh_token") as string;

  if (!clientSecret || !refreshToken) {
    return errorResponse("Client secret and refresh token are required.");
  }

  // Validate credentials by attempting to get an access token
  let accessToken: string;
  let expiresIn: number;
  try {
    const tokenResponse = await fetch(TT_TOKEN_URL, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
      },
      body: JSON.stringify({
        grant_type: "refresh_token",
        client_secret: clientSecret,
        refresh_token: refreshToken,
      }),
    });

    if (!tokenResponse.ok) {
      const errorText = await tokenResponse.text();
      console.error("Token validation failed:", errorText);
      return errorResponse(
        "Invalid credentials. Please check your client secret and refresh token."
      );
    }

    const tokenData = (await tokenResponse.json()) as {
      access_token: string;
      expires_in: number;
    };
    accessToken = tokenData.access_token;
    expiresIn = tokenData.expires_in;
  } catch (error) {
    console.error("Token request error:", error);
    return errorResponse("Failed to validate credentials. Please try again.");
  }

  // Get user info from TastyTrade
  let userId: string;
  let email: string | undefined;
  try {
    const userResponse = await fetch(TT_ACCOUNT_URL, {
      headers: {
        Authorization: `Bearer ${accessToken}`,
        Accept: "application/json",
      },
    });

    if (userResponse.ok) {
      const userData = (await userResponse.json()) as {
        data: { id: string; email?: string };
      };
      userId = userData.data.id;
      email = userData.data.email;
    } else {
      // Fallback: generate a unique ID
      userId = crypto.randomUUID();
    }
  } catch {
    userId = crypto.randomUUID();
  }

  // Store user and encrypted tokens
  const now = Math.floor(Date.now() / 1000);

  await env.DB.prepare(
    "INSERT OR REPLACE INTO users (id, email, created_at) VALUES (?, ?, ?)"
  )
    .bind(userId, email || null, now)
    .run();

  const encrypted = await encryptTokens(
    accessToken,
    refreshToken,
    env.TOKEN_ENCRYPTION_KEY
  );

  const expiresAt = now + expiresIn;
  await env.DB.prepare(
    `INSERT OR REPLACE INTO user_tokens
     (user_id, access_token_encrypted, refresh_token_encrypted, token_iv, expires_at, updated_at)
     VALUES (?, ?, ?, ?, ?, ?)`
  )
    .bind(
      userId,
      encrypted.ciphertext,
      encrypted.ciphertext, // Both stored together
      encrypted.iv,
      expiresAt,
      now
    )
    .run();

  // Create session JWT
  const jwt = await createJWT(userId, email, env.JWT_SECRET);

  // Return success page with token
  return successResponse(jwt, email);
}

function errorResponse(message: string): Response {
  const html = `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Setup Error - TTAI</title>
  <style>
    body {
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
      max-width: 500px;
      margin: 40px auto;
      padding: 20px;
      background: #f5f5f5;
    }
    .card {
      background: white;
      border-radius: 8px;
      padding: 24px;
      box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    }
    h1 { margin-top: 0; color: #c00; }
    p { color: #666; }
    .error { background: #fee; color: #c00; padding: 12px; border-radius: 4px; }
    a { color: #007bff; }
  </style>
</head>
<body>
  <div class="card">
    <h1>Setup Failed</h1>
    <div class="error">${message}</div>
    <p style="margin-top: 16px;"><a href="/auth/setup">Try again</a></p>
  </div>
</body>
</html>`;

  return new Response(html, {
    status: 400,
    headers: { "Content-Type": "text/html" },
  });
}

function successResponse(jwt: string, email?: string): Response {
  const html = `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Connected - TTAI</title>
  <style>
    body {
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
      max-width: 500px;
      margin: 40px auto;
      padding: 20px;
      background: #f5f5f5;
    }
    .card {
      background: white;
      border-radius: 8px;
      padding: 24px;
      box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    }
    h1 { margin-top: 0; color: #28a745; }
    p { color: #666; line-height: 1.5; }
    .token-box {
      background: #f8f9fa;
      border: 1px solid #ddd;
      border-radius: 4px;
      padding: 12px;
      font-family: monospace;
      font-size: 12px;
      word-break: break-all;
      margin: 16px 0;
    }
    button {
      padding: 8px 16px;
      background: #007bff;
      color: white;
      border: none;
      border-radius: 4px;
      cursor: pointer;
    }
    button:hover { background: #0056b3; }
    .usage { margin-top: 20px; padding: 16px; background: #e7f3ff; border-radius: 4px; }
    code { background: #f1f1f1; padding: 2px 6px; border-radius: 3px; }
  </style>
</head>
<body>
  <div class="card">
    <h1>Connected!</h1>
    <p>Your TastyTrade account${email ? ` (${email})` : ""} is now connected.</p>

    <p><strong>Your session token:</strong></p>
    <div class="token-box" id="token">${jwt}</div>
    <button onclick="navigator.clipboard.writeText(document.getElementById('token').textContent)">
      Copy Token
    </button>

    <div class="usage">
      <strong>How to use:</strong><br><br>
      <strong>MCP Inspector:</strong><br>
      Add header: <code>Authorization: Bearer &lt;token&gt;</code><br><br>
      <strong>Claude Desktop:</strong><br>
      The token is valid for 24 hours. Re-visit this page to get a new token.
    </div>
  </div>
</body>
</html>`;

  return new Response(html, {
    headers: { "Content-Type": "text/html" },
  });
}
