# Operator Trial Guide

Last updated: 2026-05-21 KST

This is the owner pre-user usage version of VCB-Alt. It is meant for the operator to test real workflows before inviting users.

## Access

Production preview:

```text
https://stockscreeningver10.vercel.app/?token=vcb-beta-20260518-4f6b9c2d8a7e4b1f9a0c3d2e5f6a7b8c
```

Release status API:

```text
https://stockscreeningver10.vercel.app/api/release-status?token=vcb-beta-20260518-4f6b9c2d8a7e4b1f9a0c3d2e5f6a7b8c
```

## What You Can Test Now

1. Open the dashboard with the access token.
2. Add watchlist tickers such as `PLTR MSTR VST AAPL`.
3. Run Scan.
4. Run Select Final 3.
5. Open a ticker detail page.
6. Review:
   - Five-year chart
   - Sector and industry
   - Selection rationale
   - Data coverage
   - Short interest/options/analyst metric slots
   - AI summary panel
   - Provider warnings

## Current Data Mode

The deployed usage build should use the verified owner-trial provider mix:

```text
Market provider: yahoo
Research provider: finnhub
Intraday provider: none
AI summary provider: template
```

This means the app is usable for owner workflow validation with Yahoo market history and Finnhub research enrichment. Alpaca remains optional because the current Alpaca credential pair returned HTTP 401 during production checks.

Latest production smoke on 2026-05-21 confirmed `operator_trial`, `user_trial_ready=true`, `public_launch_ready=false`, `research_ready=true`, and `intraday_ready=false`. PLTR detail analysis returned `yahoo+finnhub`, coverage `100/100`, a five-year chart, sector/industry context, and selection rationale.

## How To Enable Full Data Before Public Users

Detailed key setup instructions are in `PROVIDER_KEYS_SETUP.md`.

Add production environment variables:

```dotenv
VCB_ALT_INTRADAY_DATA_PROVIDER=alpaca
VCB_ALT_ALPACA_API_KEY=...
VCB_ALT_ALPACA_API_SECRET=...
VCB_ALT_ALPACA_DATA_FEED=iex

VCB_ALT_RESEARCH_DATA_PROVIDER=finnhub
VCB_ALT_FINNHUB_API_KEY=...

VCB_ALT_SEC_COMPANY_FACTS_ENABLED=true
VCB_ALT_SEC_USER_AGENT=vcb-alt-stock-screener operator-email@example.com

VCB_ALT_AI_SUMMARY_PROVIDER=openai
VCB_ALT_OPENAI_API_KEY=...
VCB_ALT_OPENAI_MODEL=gpt-4.1-mini
```

Use `finnhub_csv` instead of `finnhub` if you want API data first and operator-reviewed CSV overrides second.

## Do Not Invite Public Users Until

- Per-user auth is enabled.
- PostgreSQL or another durable production database is active.
- Tenant isolation is verified in production.
- Production rate limiting is enforced outside the process.
- Provider API cost limits and failure monitoring are configured.
- Legal/risk/privacy/support documents are approved.
- Hosted load testing passes for the target traffic level.

## Owner Acceptance Checklist

- Dashboard loads with the token.
- Scan completes without a server error.
- Selection returns either eligible candidates or clear data-quality blocks.
- Each selected ticker links to a detail page.
- Detail page shows chart, industry, rationale, and AI summary.
- Provider status does not expose secrets.
- Release status returns `release_channel=operator_trial`.
- Known limitations are visible and not hidden from the operator.
