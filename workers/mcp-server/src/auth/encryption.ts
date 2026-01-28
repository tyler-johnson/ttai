/**
 * Token encryption utilities using AES-GCM.
 * Encrypts TastyTrade tokens at rest in D1.
 */

const ALGORITHM = "AES-GCM";
const IV_LENGTH = 12; // 96 bits for AES-GCM

export interface EncryptedData {
  ciphertext: string; // Base64 encoded
  iv: string; // Base64 encoded
}

export interface DecryptedTokens {
  accessToken: string;
  refreshToken: string;
}

/**
 * Import the encryption key from a base64-encoded secret.
 */
async function importKey(keyBase64: string): Promise<CryptoKey> {
  const keyBytes = Uint8Array.from(atob(keyBase64), (c) => c.charCodeAt(0));
  return crypto.subtle.importKey(
    "raw",
    keyBytes,
    { name: ALGORITHM },
    false,
    ["encrypt", "decrypt"]
  );
}

/**
 * Encrypt tokens for storage in D1.
 */
export async function encryptTokens(
  accessToken: string,
  refreshToken: string,
  encryptionKey: string
): Promise<EncryptedData> {
  const key = await importKey(encryptionKey);

  // Generate random IV
  const iv = crypto.getRandomValues(new Uint8Array(IV_LENGTH));

  // Combine tokens with a separator
  const plaintext = JSON.stringify({ accessToken, refreshToken });
  const plaintextBytes = new TextEncoder().encode(plaintext);

  // Encrypt
  const ciphertextBytes = await crypto.subtle.encrypt(
    { name: ALGORITHM, iv },
    key,
    plaintextBytes
  );

  return {
    ciphertext: btoa(String.fromCharCode(...new Uint8Array(ciphertextBytes))),
    iv: btoa(String.fromCharCode(...iv)),
  };
}

/**
 * Decrypt tokens from D1 storage.
 */
export async function decryptTokens(
  ciphertext: string,
  iv: string,
  encryptionKey: string
): Promise<DecryptedTokens> {
  const key = await importKey(encryptionKey);

  const ciphertextBytes = Uint8Array.from(atob(ciphertext), (c) =>
    c.charCodeAt(0)
  );
  const ivBytes = Uint8Array.from(atob(iv), (c) => c.charCodeAt(0));

  const plaintextBytes = await crypto.subtle.decrypt(
    { name: ALGORITHM, iv: ivBytes },
    key,
    ciphertextBytes
  );

  const plaintext = new TextDecoder().decode(plaintextBytes);
  return JSON.parse(plaintext) as DecryptedTokens;
}

/**
 * Generate a new encryption key (for initial setup).
 * Run this once and store the result as TOKEN_ENCRYPTION_KEY secret.
 */
export function generateEncryptionKey(): string {
  const keyBytes = crypto.getRandomValues(new Uint8Array(32)); // 256 bits
  return btoa(String.fromCharCode(...keyBytes));
}
