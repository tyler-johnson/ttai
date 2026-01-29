/**
 * Cloudflare Worker for SSL certificate distribution.
 *
 * HTTP Endpoints:
 *   GET /cert   - Returns current certificate bundle
 *   GET /health - Health check
 *
 * Cron Trigger:
 *   Daily at 3:00 AM UTC - Check and renew certificate if needed
 */

import { AcmeClient, CertificateBundle } from "./acme";
import { CloudflareDns } from "./dns";

export interface Env {
  CERT_STORE: KVNamespace;
  CERT_DOMAIN: string;
  ACME_DIRECTORY: string;
  CF_API_TOKEN: string;
  CF_ZONE_ID: string;
}

// KV keys
const KV_CERT = "certificate";
const KV_ACCOUNT_KEY = "account_key";

// Renew when cert has less than this many days remaining
const RENEWAL_THRESHOLD_DAYS = 30;

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    // CORS headers for all responses
    const corsHeaders = {
      "Access-Control-Allow-Origin": "*",
      "Access-Control-Allow-Methods": "GET, OPTIONS",
      "Access-Control-Allow-Headers": "Content-Type",
    };

    // Handle CORS preflight
    if (request.method === "OPTIONS") {
      return new Response(null, { headers: corsHeaders });
    }

    try {
      switch (url.pathname) {
        case "/cert":
          return await handleGetCert(env, corsHeaders);
        case "/health":
          return handleHealth(corsHeaders);
        default:
          return new Response("Not Found", { status: 404, headers: corsHeaders });
      }
    } catch (error) {
      console.error("Request error:", error);
      return new Response(
        JSON.stringify({
          error: error instanceof Error ? error.message : "Internal error",
        }),
        {
          status: 500,
          headers: { ...corsHeaders, "Content-Type": "application/json" },
        }
      );
    }
  },

  async scheduled(event: ScheduledEvent, env: Env, ctx: ExecutionContext): Promise<void> {
    ctx.waitUntil(handleCronRenewal(env));
  },
};

/**
 * GET /cert - Return current certificate bundle
 */
async function handleGetCert(
  env: Env,
  corsHeaders: Record<string, string>
): Promise<Response> {
  const certJson = await env.CERT_STORE.get(KV_CERT);

  if (!certJson) {
    return new Response(
      JSON.stringify({
        error: "No certificate available. Certificate will be generated on next cron run.",
      }),
      {
        status: 503,
        headers: { ...corsHeaders, "Content-Type": "application/json" },
      }
    );
  }

  const cert = JSON.parse(certJson) as CertificateBundle;

  // Check if cert is expired
  const expiresAt = new Date(cert.expires_at);
  if (expiresAt < new Date()) {
    return new Response(
      JSON.stringify({
        error: "Certificate expired. Renewal pending.",
        expires_at: cert.expires_at,
      }),
      {
        status: 503,
        headers: { ...corsHeaders, "Content-Type": "application/json" },
      }
    );
  }

  return new Response(JSON.stringify(cert), {
    headers: { ...corsHeaders, "Content-Type": "application/json" },
  });
}

/**
 * GET /health - Health check endpoint
 */
function handleHealth(corsHeaders: Record<string, string>): Response {
  return new Response(
    JSON.stringify({
      status: "ok",
      timestamp: new Date().toISOString(),
    }),
    {
      headers: { ...corsHeaders, "Content-Type": "application/json" },
    }
  );
}

/**
 * Cron handler - Check certificate expiry and renew if needed
 */
async function handleCronRenewal(env: Env): Promise<void> {
  console.log("Starting certificate renewal check");

  // Check current certificate
  const certJson = await env.CERT_STORE.get(KV_CERT);
  if (certJson) {
    const cert = JSON.parse(certJson) as CertificateBundle;
    const expiresAt = new Date(cert.expires_at);
    const daysUntilExpiry = (expiresAt.getTime() - Date.now()) / (1000 * 60 * 60 * 24);

    console.log(`Current cert expires in ${daysUntilExpiry.toFixed(1)} days`);

    if (daysUntilExpiry > RENEWAL_THRESHOLD_DAYS) {
      console.log("Certificate still valid, skipping renewal");
      return;
    }

    console.log("Certificate expiring soon, starting renewal");
  } else {
    console.log("No certificate found, starting initial issuance");
  }

  // Initialize ACME client
  const dns = new CloudflareDns(env.CF_API_TOKEN, env.CF_ZONE_ID);
  const acme = new AcmeClient(env.ACME_DIRECTORY, dns);

  // Load or generate account key
  const accountKeyJson = await env.CERT_STORE.get(KV_ACCOUNT_KEY);
  let accountKey: JsonWebKey | undefined;
  if (accountKeyJson) {
    accountKey = JSON.parse(accountKeyJson) as JsonWebKey;
  }

  const exportedKey = await acme.init(accountKey);

  // Save account key if newly generated
  if (!accountKeyJson) {
    await env.CERT_STORE.put(KV_ACCOUNT_KEY, JSON.stringify(exportedKey));
    console.log("Generated and saved new ACME account key");
  }

  // Register/fetch account
  await acme.registerAccount();
  console.log("ACME account ready");

  // Request certificate
  console.log(`Requesting certificate for ${env.CERT_DOMAIN}`);
  const cert = await acme.requestCertificate(env.CERT_DOMAIN);

  // Store certificate
  await env.CERT_STORE.put(KV_CERT, JSON.stringify(cert));
  console.log(`Certificate issued, expires at ${cert.expires_at}`);
}
