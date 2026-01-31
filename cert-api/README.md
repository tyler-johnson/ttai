# TTAI Certificate API

Cloudflare Worker that provides SSL certificates for the TTAI MCP server to run over HTTPS.

## How It Works

1. Worker obtains certificates from Let's Encrypt using ACME DNS-01 validation
2. Certificates are stored in Cloudflare KV
3. Daily cron trigger checks for renewal (30 days before expiry)
4. TTAI server fetches certificate via HTTP API

**Architecture:**

```
api.tt-ai.dev (this Worker)  →  Serves certificates, runs ACME renewal
local.tt-ai.dev → 127.0.0.1  →  Where the TTAI server runs locally
```

## API Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /health` | Health check |
| `GET /cert` | Get certificate (cert, key, metadata) |

## Development

```bash
# Install dependencies
npm install

# Run locally
npm run dev

# Deploy to Cloudflare
npm run deploy

# View live logs
npm run tail
```

## Deployment

See [SETUP.md](SETUP.md) for complete deployment instructions including:

- Cloudflare account setup
- API token creation
- KV namespace configuration
- DNS record setup
- Initial certificate generation

## Project Structure

```
cert-api/
├── src/
│   ├── index.ts    # HTTP routes + cron handler
│   ├── acme.ts     # ACME client for Let's Encrypt
│   └── dns.ts      # Cloudflare DNS API helper
├── wrangler.toml   # Cloudflare Worker config
└── package.json
```

## Cost

All services used are on Cloudflare's free tier:
- Workers: 100,000 requests/day
- KV: 100,000 reads/day, 1,000 writes/day
- Let's Encrypt certificates: Free
