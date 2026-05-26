# Operations Runbook

## Daily Flow

```powershell
python -m vcb_alt scan
python -m vcb_alt select
python -m vcb_alt admin failures
```

Review candidates manually. The system does not place trades.

## Web Dashboard

Run:

```powershell
python -m vcb_alt web --host 127.0.0.1 --port 8765
```

Open `http://127.0.0.1:8765`.

The dashboard auto-loads watchlist, scan results, final 3-candidate selection, failure count, and SaaS readiness status.

For a controlled public demo, set `VCB_ALT_PUBLIC_WEB_ENABLED=true` and a long `VCB_ALT_WEB_ACCESS_TOKEN`, then run behind HTTPS:

```powershell
python -m vcb_alt web --host 0.0.0.0 --port 8765
```

Do not treat the token gate as full SaaS authentication.

## Performance Check

```powershell
python -m vcb_alt benchmark --repeat 1000
```

This measures local scoring throughput without external market data calls.

## Add Or Remove Tickers

```powershell
python -m vcb_alt watchlist add PLTR MSTR RGTI
python -m vcb_alt watchlist remove AAPL
python -m vcb_alt watchlist list
```

## Run With Current Manual Data

1. Update `data/snapshots.csv`.
2. Confirm `.env` has `VCB_ALT_DATA_PROVIDER=manual`.
3. Run:

```powershell
python -m vcb_alt scan
python -m vcb_alt select
```

If a watchlist ticker has no row in `data/snapshots.csv`, the scan records a failed job instead of inventing a score.

## Run With Automatic Market Data

Set:

```dotenv
VCB_ALT_DATA_PROVIDER=yahoo
VCB_ALT_EXTERNAL_API_ENABLED=true
```

Then run the normal daily flow. The provider caches responses under `data/market_cache/` for `VCB_ALT_MARKET_DATA_CACHE_TTL_HOURS`.

If provider fetches fail, check:

- Network/DNS access from the host
- Unsupported ticker symbols
- Cache directory write permissions
- `admin failures` for the provider error

## Investigate A Failure

```powershell
python -m vcb_alt admin failures --json
python -m vcb_alt admin logs --json
```

Check:

- Error code
- Failed command
- Timestamp
- Whether the database was initialized
- Whether ticker input was valid

## Export Data

```powershell
python -m vcb_alt admin export --out exports\vcb_export.json
```

## Delete Local Data

```powershell
python -m vcb_alt admin delete-data --confirm DELETE_LOCAL_DATA
```

This clears watchlist, evaluations, operation logs, and failed jobs from the SQLite DB. It does not remove `.env`, source files, or exported files.

## Security Rules

- Keep `.env` local.
- Enable external APIs only when the intended provider is configured and cache settings are understood.
- Rotate `VCB_ALT_WEB_ACCESS_TOKEN` if it is shared too widely or appears in logs, screenshots, or messages.
- Do not paste API keys into ticker notes or command arguments.
- Treat results as decision support only.

## Incident Checklist

1. Stop repeated runs if failures are growing.
2. Export data if possible.
3. Review `admin failures`.
4. Review `logs/app.log`.
5. Restore DB from backup if corruption is suspected.
6. Re-run `doctor` and `self-test`.
