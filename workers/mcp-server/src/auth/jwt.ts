/**
 * JWT utilities for session management.
 * Uses HMAC-SHA256 for signing.
 */

const ALGORITHM = { name: "HMAC", hash: "SHA-256" };
const JWT_EXPIRY_SECONDS = 24 * 60 * 60; // 24 hours

export interface JWTPayload {
  sub: string; // User ID (TastyTrade account ID)
  email?: string;
  iat: number; // Issued at
  exp: number; // Expiration
}

/**
 * Import the JWT secret as a CryptoKey.
 */
async function importKey(secret: string): Promise<CryptoKey> {
  const keyBytes = new TextEncoder().encode(secret);
  return crypto.subtle.importKey("raw", keyBytes, ALGORITHM, false, [
    "sign",
    "verify",
  ]);
}

/**
 * Base64url encode (URL-safe base64 without padding).
 */
function base64urlEncode(data: Uint8Array | string): string {
  const bytes =
    typeof data === "string" ? new TextEncoder().encode(data) : data;
  return btoa(String.fromCharCode(...bytes))
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=/g, "");
}

/**
 * Base64url decode.
 */
function base64urlDecode(str: string): Uint8Array {
  const padded = str + "=".repeat((4 - (str.length % 4)) % 4);
  const base64 = padded.replace(/-/g, "+").replace(/_/g, "/");
  return Uint8Array.from(atob(base64), (c) => c.charCodeAt(0));
}

/**
 * Create a signed JWT.
 */
export async function createJWT(
  userId: string,
  email: string | undefined,
  jwtSecret: string
): Promise<string> {
  const now = Math.floor(Date.now() / 1000);

  const header = { alg: "HS256", typ: "JWT" };
  const payload: JWTPayload = {
    sub: userId,
    email,
    iat: now,
    exp: now + JWT_EXPIRY_SECONDS,
  };

  const headerEncoded = base64urlEncode(JSON.stringify(header));
  const payloadEncoded = base64urlEncode(JSON.stringify(payload));
  const message = `${headerEncoded}.${payloadEncoded}`;

  const key = await importKey(jwtSecret);
  const signature = await crypto.subtle.sign(
    ALGORITHM,
    key,
    new TextEncoder().encode(message)
  );

  const signatureEncoded = base64urlEncode(new Uint8Array(signature));
  return `${message}.${signatureEncoded}`;
}

/**
 * Verify and decode a JWT.
 * Returns the payload if valid, throws if invalid or expired.
 */
export async function verifyJWT(
  token: string,
  jwtSecret: string
): Promise<JWTPayload> {
  const parts = token.split(".");
  if (parts.length !== 3) {
    throw new Error("Invalid JWT format");
  }

  const [headerEncoded, payloadEncoded, signatureEncoded] = parts;
  const message = `${headerEncoded}.${payloadEncoded}`;

  // Verify signature
  const key = await importKey(jwtSecret);
  const signature = base64urlDecode(signatureEncoded);
  const valid = await crypto.subtle.verify(
    ALGORITHM,
    key,
    signature.buffer as ArrayBuffer,
    new TextEncoder().encode(message)
  );

  if (!valid) {
    throw new Error("Invalid JWT signature");
  }

  // Decode payload
  const payloadBytes = base64urlDecode(payloadEncoded);
  const payload = JSON.parse(
    new TextDecoder().decode(payloadBytes)
  ) as JWTPayload;

  // Check expiration
  const now = Math.floor(Date.now() / 1000);
  if (payload.exp < now) {
    throw new Error("JWT expired");
  }

  return payload;
}

/**
 * Extract JWT from Authorization header.
 * Expects: "Bearer <token>"
 */
export function extractBearerToken(authHeader: string | null): string | null {
  if (!authHeader?.startsWith("Bearer ")) {
    return null;
  }
  return authHeader.slice(7);
}
