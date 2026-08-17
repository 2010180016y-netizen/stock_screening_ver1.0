# Provider Keys Setup

Last updated: 2026-06-03 KST

This file explains how to enable the full data version before inviting external users.

Do not paste real API keys into chat. Add them through Vercel Environment Variables or a local `.env` file.

## Current State

- Local `.env`: not present unless the operator creates it.
- Finnhub production key is verified and can be used for the owner trial.
- Alpaca production variables are present, but the live provider returned HTTP 401 during production checks.
- `/api/provider-diagnostics/alpaca` is available for a secret-safe credential check across Paper Trading, Live Trading, and Market Data snapshot endpoints.
- Current owner-trial deployment should use:
  - `VCB_ALT_DATA_PROVIDER=yahoo`
  - `VCB_ALT_RESEARCH_DATA_PROVIDER=finnhub`
  - `VCB_ALT_INTRADAY_DATA_PROVIDER=none`
  - `VCB_ALT_AI_SUMMARY_PROVIDER=template`

That means the app is usable for owner workflow testing, but full live research is not enabled yet.

## Suggested Production Variables

Set these in Vercel Project Settings -> Environment Variables -> Production.

### Core App

```dotenv
VCB_ALT_DATA_PROVIDER=yahoo
VCB_ALT_EXTERNAL_API_ENABLED=true
VCB_ALT_PUBLIC_WEB_ENABLED=true
VCB_ALT_WEB_ACCESS_TOKEN=<ROTATED-SEE-VERCEL-ENV>
VCB_ALT_DATABASE_URL=sqlite:////tmp/vcb_alt.db
VCB_ALT_DATA_DIR=/tmp/vcb_alt_data
VCB_ALT_LOG_DIR=/tmp/vcb_alt_logs
```

### Near-Real-Time Quote Layer

Use Alpaca for latest quote/trade/minute-bar context.

```dotenv
VCB_ALT_INTRADAY_DATA_PROVIDER=alpaca
VCB_ALT_INTRADAY_CACHE_TTL_SECONDS=60
VCB_ALT_ALPACA_DATA_FEED=iex
VCB_ALT_ALPACA_API_KEY=<your-alpaca-key-id>
VCB_ALT_ALPACA_API_SECRET=<your-alpaca-secret-key>
```

Notes:

- `iex` is the conservative default feed.
- Use `sip` only if your Alpaca plan allows SIP data.

### Research Data Layer

Use Finnhub for fundamentals, earnings surprise, news, analyst trend, short interest, options, and insider data.

```dotenv
VCB_ALT_RESEARCH_DATA_PROVIDER=finnhub
VCB_ALT_RESEARCH_DATA_CACHE_TTL_HOURS=12
VCB_ALT_FINNHUB_API_KEY=<your-finnhub-key>
```

Use this instead if you want operator-reviewed CSV overrides after Finnhub:

```dotenv
VCB_ALT_RESEARCH_DATA_PROVIDER=finnhub_csv
```

### SEC Filing Layer

SEC data does not require a secret key, but it requires a real user-agent contact.

```dotenv
VCB_ALT_SEC_COMPANY_FACTS_ENABLED=true
VCB_ALT_SEC_USER_AGENT=vcb-alt-stock-screener your-email@example.com
```

Replace `your-email@example.com` with an operator email address.

### Explanation Summary Layer

Use local deterministic summaries by default:

```dotenv
VCB_ALT_AI_SUMMARY_PROVIDER=template
VCB_ALT_AI_SUMMARY_CACHE_TTL_HOURS=12
```

Use OpenAI only when you want paid explanation summaries. Stock selection remains deterministic scoring and portfolio constraints:

```dotenv
VCB_ALT_AI_SUMMARY_PROVIDER=openai
VCB_ALT_OPENAI_API_KEY=<your-openai-key>
VCB_ALT_OPENAI_MODEL=gpt-4.1-mini
VCB_ALT_AI_SUMMARY_CACHE_TTL_HOURS=12
```

## Safe Vercel Dashboard Method

1. Open Vercel.
2. Go to project `stock_screening_ver1.0`.
3. Open Settings -> Environment Variables.
4. Add each variable above.
5. Set Environment to `Production`.
6. Save.
7. Redeploy production.

After redeploy, check:

```text
https://stockscreeningver10.vercel.app/api/release-status?token=<ROTATED-SEE-VERCEL-ENV>
```

Expected after full keys are configured:

```json
{
  "release_channel": "operator_trial",
  "configured_data": {
    "market_provider": "yahoo",
    "research_provider": "finnhub",
    "research_ready": true,
    "intraday_provider": "alpaca",
    "intraday_ready": true,
    "ai_summary_provider": "openai",
    "ai_summary_ready": true
  }
}
```

## Safe Vercel CLI Method

Run these commands in PowerShell. Vercel will prompt you to paste each value securely.

```powershell
npx.cmd vercel env add VCB_ALT_DATA_PROVIDER production
npx.cmd vercel env add VCB_ALT_EXTERNAL_API_ENABLED production
npx.cmd vercel env add VCB_ALT_PUBLIC_WEB_ENABLED production
npx.cmd vercel env add VCB_ALT_WEB_ACCESS_TOKEN production
npx.cmd vercel env add VCB_ALT_DATABASE_URL production
npx.cmd vercel env add VCB_ALT_DATA_DIR production
npx.cmd vercel env add VCB_ALT_LOG_DIR production

npx.cmd vercel env add VCB_ALT_INTRADAY_DATA_PROVIDER production
npx.cmd vercel env add VCB_ALT_INTRADAY_CACHE_TTL_SECONDS production
npx.cmd vercel env add VCB_ALT_ALPACA_DATA_FEED production
npx.cmd vercel env add VCB_ALT_ALPACA_API_KEY production
npx.cmd vercel env add VCB_ALT_ALPACA_API_SECRET production

npx.cmd vercel env add VCB_ALT_RESEARCH_DATA_PROVIDER production
npx.cmd vercel env add VCB_ALT_RESEARCH_DATA_CACHE_TTL_HOURS production
npx.cmd vercel env add VCB_ALT_FINNHUB_API_KEY production

npx.cmd vercel env add VCB_ALT_SEC_COMPANY_FACTS_ENABLED production
npx.cmd vercel env add VCB_ALT_SEC_USER_AGENT production

npx.cmd vercel env add VCB_ALT_AI_SUMMARY_PROVIDER production
npx.cmd vercel env add VCB_ALT_AI_SUMMARY_CACHE_TTL_HOURS production
npx.cmd vercel env add VCB_ALT_OPENAI_API_KEY production
npx.cmd vercel env add VCB_ALT_OPENAI_MODEL production
```

Then redeploy:

```powershell
npx.cmd vercel --prod --yes
```

## Local `.env` Method

For local testing only, copy `.env.example` to `.env` and fill the same values:

```powershell
Copy-Item .env.example .env
notepad .env
```

Then run:

```powershell
C:\stable-diffusion-ui\installer_files\env\python.exe -m vcb_alt web --host 127.0.0.1 --port 8788
```

Open:

```text
http://127.0.0.1:8788/
```

## Verification Commands

Production:

```powershell
$token='<ROTATED-SEE-VERCEL-ENV>'
$base='https://stockscreeningver10.vercel.app'
Invoke-WebRequest -UseBasicParsing "$base/api/health"
Invoke-WebRequest -UseBasicParsing "$base/api/release-status?token=$token"
Invoke-WebRequest -UseBasicParsing "$base/api/provider-status?token=$token"
Invoke-WebRequest -UseBasicParsing "$base/api/provider-diagnostics/alpaca?token=$token"
Invoke-WebRequest -UseBasicParsing "$base/api/ticker-analysis?ticker=PLTR&token=$token"
```

Security check:

- Provider status must not print actual key values.
- Do not commit `.env`.
- Rotate any key that was pasted into chat, committed, or shown in screenshots.

## Alpaca Troubleshooting

If ticker analysis returns:

```text
Alpaca rejected the request with HTTP 401
```

Check these items:

1. `VCB_ALT_ALPACA_API_KEY` must be the Alpaca `Key ID`.
2. `VCB_ALT_ALPACA_API_SECRET` must be the matching `Secret Key`.
3. Both values must come from the same Alpaca account and same Paper/Live context.
4. Do not add surrounding quotes or spaces.
5. If the Secret Key was lost, regenerate the key pair in Alpaca and update both Vercel variables.
6. Keep `VCB_ALT_ALPACA_DATA_FEED=iex` unless the Alpaca account has SIP access.
7. Run `/api/provider-diagnostics/alpaca` after every Vercel env update. `ready=true` is required before production market-universe scans can be trusted.
8. If diagnostics returns `key_context_mismatch_or_invalid`, replace both `VCB_ALT_ALPACA_API_KEY` and `VCB_ALT_ALPACA_API_SECRET` as a freshly generated pair, then redeploy.
9. If diagnostics returns `feed_forbidden`, set `VCB_ALT_ALPACA_DATA_FEED=iex` unless the account explicitly has SIP access, then redeploy.
