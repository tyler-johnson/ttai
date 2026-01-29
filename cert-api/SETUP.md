# Cloudflare Worker Setup Guide

Complete guide to deploying the TTAI Certificate API on Cloudflare Workers.

## Prerequisites

- A Cloudflare account (free tier works)
- A domain managed by Cloudflare DNS (e.g., `tt-ai.dev`)
- Node.js 18+ installed locally
- Wrangler CLI (installed via npm)

## Overview

This worker provides SSL certificates for the TTAI MCP server to run over HTTPS. It:

- Automatically obtains certificates from Let's Encrypt using ACME DNS-01 validation
- Stores certificates in Cloudflare KV
- Renews certificates automatically via daily cron trigger
- Serves certificates via a simple HTTP API

**Architecture:**

```
api.tt-ai.dev (Worker)       → Serves certificates, runs ACME renewal
local.tt-ai.dev → 127.0.0.1  → Where the TTAI server runs locally
```

---

## Step 1: Install Dependencies

```bash
cd cert-api
npm install
```

This installs:

- `wrangler` - Cloudflare Workers CLI
- `typescript` - TypeScript compiler
- `@cloudflare/workers-types` - Type definitions

## Step 2: Authenticate Wrangler

```bash
npx wrangler login
```

This opens a browser window to authenticate with your Cloudflare account.

Verify authentication:

```bash
npx wrangler whoami
```

## Step 3: Get Your Zone ID

1. Go to [Cloudflare Dashboard](https://dash.cloudflare.com)
2. Select your domain (e.g., `tt-ai.dev`)
3. On the **Overview** page, scroll down to the **API** section on the right sidebar
4. Copy the **Zone ID**

Save this for later - you'll need it as `CF_ZONE_ID`.

## Step 4: Create a Cloudflare API Token

The worker needs an API token to create DNS TXT records for ACME validation.

1. Go to [Cloudflare API Tokens](https://dash.cloudflare.com/profile/api-tokens)
2. Click **Create Token**
3. Click **Create Custom Token**
4. Configure the token:

   | Setting            | Value                                 |
   | ------------------ | ------------------------------------- |
   | **Token name**     | `ttai-cert-api-dns`                   |
   | **Permissions**    | Zone → DNS → Edit                     |
   | **Zone Resources** | Include → Specific zone → `tt-ai.dev` |
   | **TTL**            | (optional) Set an expiry date         |

5. Click **Continue to summary** → **Create Token**
6. **Copy the token immediately** - it won't be shown again

Save this as `CF_API_TOKEN`.

## Step 5: Create KV Namespace

Create a KV namespace to store certificates and ACME account keys:

```bash
npx wrangler kv namespace create CERT_STORE
```

Output will look like:

```
🌀 Creating namespace with title "ttai-cert-api-CERT_STORE"
✨ Success!
Add the following to your configuration file in your kv_namespaces array:
[[kv_namespaces]]
binding = "CERT_STORE"
id = "abc123def456..."
```

**Copy the `id` value.**

## Step 6: Update wrangler.toml

Edit `wrangler.toml` with your KV namespace ID and domain:

```toml
name = "ttai-cert-api"
main = "src/index.ts"
compatibility_date = "2024-11-01"

# KV namespace for certificate storage
[[kv_namespaces]]
binding = "CERT_STORE"
id = "YOUR_KV_NAMESPACE_ID"  # ← Replace with ID from Step 5

# Cron trigger for daily certificate renewal check
[triggers]
crons = ["0 3 * * *"]  # 3:00 AM UTC daily

# Environment variables (non-secret)
[vars]
CERT_DOMAIN = "local.tt-ai.dev"  # ← Domain for the certificate
ACME_DIRECTORY = "https://acme-v02.api.letsencrypt.org/directory"
```

**For testing**, use the Let's Encrypt staging server to avoid rate limits:

```toml
ACME_DIRECTORY = "https://acme-staging-v02.api.letsencrypt.org/directory"
```

## Step 7: Configure Secrets

Add the API token and zone ID as encrypted secrets:

```bash
# Add the Cloudflare API token
npx wrangler secret put CF_API_TOKEN
# Paste your API token when prompted

# Add the Zone ID
npx wrangler secret put CF_ZONE_ID
# Paste your Zone ID when prompted
```

Verify secrets are set:

```bash
npx wrangler secret list
```

## Step 8: Configure DNS Records

In the Cloudflare Dashboard, add these DNS records:

### A Record for Local Server

| Type | Name    | Content     | Proxy                    |
| ---- | ------- | ----------- | ------------------------ |
| A    | `local` | `127.0.0.1` | ❌ DNS only (grey cloud) |

This makes `local.tt-ai.dev` resolve to `127.0.0.1` (localhost).

**Important:** This record must be "DNS only" (grey cloud), not proxied, because:

- It points to localhost (127.0.0.1)
- The TTAI server runs on the user's machine, not Cloudflare

### Worker Route (created automatically)

The worker will be deployed to `ttai-cert-api.<your-subdomain>.workers.dev` by default. We'll add a custom domain in Step 10.

## Step 9: Deploy the Worker

```bash
npx wrangler deploy
```

Output:

```
⛅️ wrangler 3.x.x
-------------------
Total Upload: 15.23 KiB / gzip: 4.56 KiB
Uploaded ttai-cert-api (1.23 sec)
Published ttai-cert-api (0.45 sec)
  https://ttai-cert-api.YOUR_SUBDOMAIN.workers.dev
  schedule: 0 3 * * *
```

Test the deployment:

```bash
curl https://ttai-cert-api.YOUR_SUBDOMAIN.workers.dev/health
```

Expected response:

```json
{ "status": "ok", "timestamp": "2025-01-28T12:00:00.000Z" }
```

## Step 10: Add Custom Domain (api.tt-ai.dev)

To use `api.tt-ai.dev` instead of the workers.dev subdomain:

### Option A: Via Cloudflare Dashboard

1. Go to **Workers & Pages** in the Cloudflare Dashboard
2. Click on your worker (`ttai-cert-api`)
3. Go to **Settings** → **Triggers**
4. Under **Custom Domains**, click **Add Custom Domain**
5. Enter: `api.tt-ai.dev`
6. Click **Add Custom Domain**

Cloudflare will automatically:

- Create the DNS record
- Provision an SSL certificate for the worker endpoint

### Option B: Via wrangler.toml

Add to `wrangler.toml`:

```toml
# Custom domain
routes = [
  { pattern = "api.tt-ai.dev", custom_domain = true }
]
```

Then redeploy:

```bash
npx wrangler deploy
```

### Verify Custom Domain

Wait a minute for DNS propagation, then test:

```bash
curl https://api.tt-ai.dev/health
```

## Step 11: Generate Initial Certificate

The certificate is generated on the first cron run (3 AM UTC daily). To generate it immediately:

### Option A: Trigger Cron Manually (Recommended)

Use the Cloudflare Dashboard:

1. Go to **Workers & Pages** → `ttai-cert-api`
2. Go to **Logs** → **Cron Logs**
3. Click **Trigger scheduled event**

Or use wrangler:

```bash
# In local dev mode, you can trigger cron events
npx wrangler dev --test-scheduled
# Then in another terminal:
curl "http://localhost:8787/__scheduled?cron=0+3+*+*+*"
```

### Option B: Wait for Scheduled Run

The cron runs daily at 3:00 AM UTC. Check back after that time.

### Verify Certificate

After the cron runs successfully:

```bash
curl https://api.tt-ai.dev/cert
```

Expected response:

```json
{
  "cert": "-----BEGIN CERTIFICATE-----\n...",
  "key": "-----BEGIN PRIVATE KEY-----\n...",
  "domain": "local.tt-ai.dev",
  "expires_at": "2025-04-28T00:00:00.000Z",
  "issued_at": "2025-01-28T00:00:00.000Z"
}
```

If you get a 503 error, check the worker logs for ACME errors.

## Step 12: Test with TTAI Server

```bash
cd ../src-python

# Sync dependencies (includes httpx for cert fetching)
uv sync

# Run with HTTPS enabled
TTAI_SSL_DOMAIN=tt-ai.dev uv run python -m src.server.main --transport sse
```

Expected output:

```
INFO ttai.ssl: Fetching certificate from https://api.tt-ai.dev/cert
INFO ttai.ssl: Saved certificate for local.tt-ai.dev, expires 2025-04-28
INFO ttai.server: Starting MCP server in HTTPS mode at https://local.tt-ai.dev:5181/mcp
```

Test the HTTPS endpoint:

```bash
curl https://local.tt-ai.dev:5181/api/health
```

---

## Troubleshooting

### "No certificate available" (503 error)

The certificate hasn't been generated yet. Either:

- Wait for the daily cron (3 AM UTC)
- Trigger the cron manually (see Step 11)

### ACME errors in worker logs

Check the worker logs:

```bash
npx wrangler tail
```

Common issues:

- **DNS propagation**: DNS TXT record may not have propagated. The worker waits 5 seconds, but some DNS providers are slower.
- **Rate limits**: Let's Encrypt has rate limits. Use staging server for testing.
- **Invalid API token**: Verify `CF_API_TOKEN` has DNS edit permission for the correct zone.

### Certificate not trusted locally

If using Let's Encrypt staging, certificates won't be trusted by browsers. Switch to production:

```toml
ACME_DIRECTORY = "https://acme-v02.api.letsencrypt.org/directory"
```

Then delete the cached cert and re-run the cron to get a production certificate.

### Worker deployment fails

Verify wrangler is authenticated:

```bash
npx wrangler whoami
```

Check that your `wrangler.toml` has the correct KV namespace ID.

### DNS record for local.tt-ai.dev not working

1. Verify the record exists in Cloudflare DNS
2. Ensure it's set to "DNS only" (grey cloud), not proxied
3. Test DNS resolution:
   ```bash
   dig local.tt-ai.dev
   ```
   Should return `127.0.0.1`

---

## Maintenance

### View Worker Logs

Real-time logs:

```bash
npx wrangler tail
```

### Check Certificate Expiry

```bash
curl -s https://api.tt-ai.dev/cert | jq '.expires_at'
```

### Force Certificate Renewal

Delete the cached certificate to force renewal on next cron:

```bash
# List KV keys
npx wrangler kv:key list --namespace-id YOUR_KV_NAMESPACE_ID

# Delete certificate (forces renewal)
npx wrangler kv:key delete --namespace-id YOUR_KV_NAMESPACE_ID "certificate"
```

Then trigger the cron or wait for scheduled run.

### Update Worker Code

After making changes:

```bash
npx wrangler deploy
```

---

## Security Notes

1. **Private key exposure**: The `/cert` endpoint returns the private key. This is acceptable because:
   - The certificate is only valid for `local.tt-ai.dev` which resolves to `127.0.0.1`
   - An attacker with the key could only impersonate localhost to localhost
   - No sensitive traffic is exposed

2. **API token security**: The `CF_API_TOKEN` is stored as an encrypted secret and never exposed in logs or responses.

3. **ACME account key**: Stored in KV and reused for all certificate requests. Don't delete the `account_key` entry unless you want to create a new ACME account.

---

## Cost

All Cloudflare services used are available on the **free tier**:

- Workers: 100,000 requests/day free
- KV: 100,000 reads/day, 1,000 writes/day free
- Cron Triggers: Included
- Custom domains: Included

Let's Encrypt certificates are free.

---

## Quick Reference

| Resource               | Value                   |
| ---------------------- | ----------------------- |
| Worker URL             | `https://api.tt-ai.dev` |
| Cert endpoint          | `GET /cert`             |
| Health endpoint        | `GET /health`           |
| Cron schedule          | Daily at 3:00 AM UTC    |
| Certificate validity   | 90 days (Let's Encrypt) |
| Auto-renewal threshold | 30 days before expiry   |
| Local server domain    | `local.tt-ai.dev`       |
| Local server port      | `5181` (HTTPS)          |
