# Operator-Trial Web Deployment Guide

## What Is Now Possible

This repository can run as a token-protected owner/operator trial web service. The current deployment is for controlled verification, not unrestricted public operation.

Current status: `public_launch_ready=false`, `/api/saas-readiness` returns `NOT_READY_FOR_1000_USER_SAAS`, and production market-universe scans remain blocked until Alpaca diagnostics return `ready=true`.

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

## Local Token-Mode Test

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

## Vercel Operator-Trial Deployment

The included `api/index.py` and `vercel.json` can deploy this app as a Vercel Python serverless operator-trial build. Keep it token-gated and do not open unrestricted signup until the release blockers are cleared.

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
- The current Vercel deployment is suitable for token-protected owner/operator verification, not unrestricted multi-user SaaS.
- Alpaca diagnostics must return `ready=true` before representing market-universe scans as live provider-backed results.
- The current token gate is not a substitute for per-user authentication, audit trails, MFA, or RBAC.
- Automatic market providers supply price/volume history only in this implementation. Fundamentals, news, short interest, options data, and catalysts remain unavailable unless supplied through a future provider or manual data.
- This app is decision support only. It does not provide trading instructions and does not place trades.

## Future 1000-User Path

For a future 1000-user public SaaS release, keep the scoring/domain logic but complete the architecture, legal, monitoring, backup/restore, auth, and live-provider gates in:

- `SAAS_1000_USER_ARCHITECTURE.md`
- `MULTI_TENANT_DATA_MODEL.md`
- `SECURITY_COMPLIANCE_1000_USER.md`
- `LOAD_TEST_PLAN.md`
