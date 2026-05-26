# Public Web Deployment Guide

## What Is Now Possible

This repository can now run as a token-protected web service that fetches end-of-day market price/volume data from the `yahoo` provider and caches responses locally.

This is suitable for a controlled public demo or private beta. It is not yet a fully multi-user SaaS with accounts, tenant isolation, billing, or legal-reviewed investment disclosures.

## Required Environment

```dotenv
VCB_ALT_DATA_PROVIDER=yahoo
VCB_ALT_EXTERNAL_API_ENABLED=true
VCB_ALT_PUBLIC_WEB_ENABLED=true
VCB_ALT_WEB_ACCESS_TOKEN=<long-random-token-at-least-16-chars>
VCB_ALT_DATABASE_URL=sqlite:///./data/vcb_alt.db
VCB_ALT_DATA_DIR=./data
VCB_ALT_LOG_DIR=./logs
VCB_ALT_MARKET_DATA_CACHE_TTL_HOURS=12
VCB_ALT_MARKET_DATA_TIMEOUT_SECONDS=10
VCB_ALT_AUTO_SEED_SAMPLE=true
```

Open the deployed URL with:

```text
https://your-domain.example/?token=<long-random-token-at-least-16-chars>
```

After the first successful request, the app stores the token in an HTTP-only same-site cookie.

## Current Production Deployment

The current Vercel production alias is:

```text
https://stockscreeningver10.vercel.app
```

Open it with the operator-provided access token:

```text
https://stockscreeningver10.vercel.app/?token=<operator-token>
```

## Local Public-Mode Test

```powershell
$env:VCB_ALT_DATA_PROVIDER="yahoo"
$env:VCB_ALT_EXTERNAL_API_ENABLED="true"
$env:VCB_ALT_PUBLIC_WEB_ENABLED="true"
$env:VCB_ALT_WEB_ACCESS_TOKEN="local-demo-token-123456"
python -m vcb_alt web --host 127.0.0.1 --port 8765
```

Then open:

```text
http://127.0.0.1:8765/?token=local-demo-token-123456
```

## Docker

```powershell
docker build -t vcb-alt-screening .
docker run --rm -p 8765:8765 `
  -e VCB_ALT_DATA_PROVIDER=yahoo `
  -e VCB_ALT_EXTERNAL_API_ENABLED=true `
  -e VCB_ALT_PUBLIC_WEB_ENABLED=true `
  -e VCB_ALT_WEB_ACCESS_TOKEN=local-demo-token-123456 `
  vcb-alt-screening
```

## Render

The included `render.yaml` defines a Docker web service. Set `VCB_ALT_WEB_ACCESS_TOKEN` as a secret in Render before opening the service.

## Vercel Serverless Demo

The included `api/index.py` and `vercel.json` can deploy this app as a Vercel Python serverless demo. Because Vercel serverless storage is ephemeral, use it only for controlled demonstrations unless you connect a persistent database in a future release.

```powershell
$token = "replace-with-a-long-random-token"
npx vercel deploy --prod --yes `
  -e VCB_ALT_DATA_PROVIDER=yahoo `
  -e VCB_ALT_EXTERNAL_API_ENABLED=true `
  -e VCB_ALT_PUBLIC_WEB_ENABLED=true `
  -e VCB_ALT_WEB_ACCESS_TOKEN=$token `
  -e VCB_ALT_DATABASE_URL=sqlite:////tmp/vcb_alt.db `
  -e VCB_ALT_DATA_DIR=/tmp/vcb_alt_data `
  -e VCB_ALT_LOG_DIR=/tmp/vcb_alt_logs
```

## Operational Warnings

- SQLite storage inside a stateless container can be ephemeral unless the platform provides persistent disks.
- Vercel serverless `/tmp` storage is ephemeral and can reset between cold starts.
- The current Vercel deployment is suitable for token-protected private beta verification, not durable multi-user SaaS.
- The current token gate is not a substitute for per-user authentication, audit trails, MFA, or RBAC.
- Automatic market providers supply price/volume history only in this implementation. Fundamentals, news, short interest, options data, and catalysts remain unavailable unless supplied through a future provider or manual data.
- This app is decision support only. It does not provide investment advice and does not place trades.

## 1000-User Path

For 1000 real users, keep the scoring/domain logic but move production state to the architecture in:

- `SAAS_1000_USER_ARCHITECTURE.md`
- `MULTI_TENANT_DATA_MODEL.md`
- `SECURITY_COMPLIANCE_1000_USER.md`
- `LOAD_TEST_PLAN.md`
