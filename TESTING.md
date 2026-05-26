# Testing Guide

## Commands

Dependency install:

```powershell
python -m pip install -r requirements.txt
```

Type/syntax/build check:

```powershell
python -m compileall vcb_alt tests tools
```

Type-hint import check:

```powershell
python tools\typecheck.py
```

Lint:

```powershell
python tools\lint.py
```

Tests:

```powershell
python -m unittest discover -s tests -v
```

Local smoke flow:

```powershell
python -m vcb_alt init-db --seed
python -m vcb_alt doctor
python -m vcb_alt evaluate PLTR
python -m vcb_alt scan --limit 3
python -m vcb_alt select
python -m vcb_alt benchmark --repeat 1000
python -m vcb_alt admin logs
python -m vcb_alt admin failures
```

Automatic market-data provider smoke flow:

```powershell
$env:VCB_ALT_DATA_PROVIDER="yahoo"
$env:VCB_ALT_EXTERNAL_API_ENABLED="true"
python -m vcb_alt evaluate AAPL --json
```

Local web dashboard:

```powershell
python -m vcb_alt web --host 127.0.0.1 --port 8765
```

Verified page/API targets:

- `GET /`
- `GET /api/health`
- `GET /api/scan`
- `GET /api/select`

1000-user SaaS blocker check:

```powershell
python -m vcb_alt saas-readiness
```

Expected current result: `NOT_READY_FOR_1000_USER_SAAS`.

## Coverage By Test File

- `tests/test_validation.py`: ticker, numeric, destructive confirmation validation.
- `tests/test_scoring.py`: sample-data scoring and bounded archetype scores.
- `tests/test_db.py`: SQLite init, watchlist, evaluation save, redacted logs, export, delete.
- `tests/test_cli.py`: end-to-end CLI init/seed/scan/logs and friendly errors.
- `tests/test_saas_readiness.py`: confirms the current CLI cannot be accidentally marked ready for 1000-user SaaS.
- `tests/test_providers.py`: manual CSV provider parsing and validation.
- `tests/test_stooq_provider.py`: Stooq/Yahoo cache parsing plus price/volume-derived precision metrics.
- `tests/test_portfolio.py`: final candidate selection constraints.
- `tests/test_web.py`: web API scan/select, scoring benchmark, and public token guard.

## Manual QA Notes

- Use `--json` when integrating CLI output into scripts.
- Invalid tickers should return `VALIDATION_ERROR`.
- Missing DB should return `NOT_FOUND` with `init-db` recovery guidance.
- Logs must not expose API keys or tokens.
- In public web mode, `/api/health` should remain public and other APIs should require a valid token.
- Automatic market-data mode should not silently fall back to sample data when network/provider fetch fails.
