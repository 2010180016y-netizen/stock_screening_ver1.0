# Setup Guide

## 1. Requirements

- Python 3.11+
- Windows PowerShell, macOS shell, or Linux shell
- Local write access to the project directory

## 2. Install

```powershell
python -m pip install -r requirements.txt
```

If `python` is unavailable on this machine:

```powershell
& 'C:\stable-diffusion-ui\installer_files\env\python.exe' -m pip install -r requirements.txt
```

## 3. Configure

```powershell
Copy-Item .env.example .env
```

The MVP works without editing `.env`. Safe defaults:

- SQLite DB: `./data/vcb_alt.db`
- Logs: `./logs/app.log`
- Data provider: `sample`
- External APIs: disabled
- Public web mode: disabled

## 4. Initialize

```powershell
python -m vcb_alt init-db --seed
```

Expected result:

- `data/vcb_alt.db` exists.
- Sample tickers are added.
- `logs/app.log` is created after commands that write file logs.

## 5. Smoke Check

```powershell
python -m vcb_alt doctor
python -m vcb_alt evaluate PLTR
python -m vcb_alt scan
python -m vcb_alt select
python -m vcb_alt admin logs
```

## 6. Manual Data Mode

Use this when you want the screener to run on your own current snapshots.

```powershell
Copy-Item data\snapshots.example.csv data\snapshots.csv
```

Then edit `.env`:

```dotenv
VCB_ALT_DATA_PROVIDER=manual
```

Run:

```powershell
python -m vcb_alt scan
python -m vcb_alt select
```

## 7. Automatic Market Data Mode

Use this when you want the program to fetch end-of-day market price/volume data itself.

```dotenv
VCB_ALT_DATA_PROVIDER=yahoo
VCB_ALT_EXTERNAL_API_ENABLED=true
VCB_ALT_MARKET_DATA_CACHE_TTL_HOURS=12
```

Run:

```powershell
python -m vcb_alt evaluate AAPL
python -m vcb_alt scan
python -m vcb_alt select
```

Automatic market-data mode needs network access. If network fetch fails, the app returns a friendly provider error and records failures in `admin failures`.

## 8. Public Web Mode

```dotenv
VCB_ALT_PUBLIC_WEB_ENABLED=true
VCB_ALT_WEB_ACCESS_TOKEN=replace-with-a-long-random-token
```

Start:

```powershell
python -m vcb_alt web --host 0.0.0.0 --port 8765
```

Open:

```text
http://localhost:8765/?token=replace-with-a-long-random-token
```

## 9. Common Setup Problems

- `python` not found: use the verified fallback runtime path above or install Python 3.11+.
- `Database is not initialized`: run `python -m vcb_alt init-db`.
- Empty watchlist: run `python -m vcb_alt watchlist seed` or add tickers manually.
- Market data fetch fails: check network access, provider symbol support, and `VCB_ALT_EXTERNAL_API_ENABLED=true`.
- Manual provider error: create `data/snapshots.csv` from `data/snapshots.example.csv`.
- Public web mode fails at startup: use a `VCB_ALT_WEB_ACCESS_TOKEN` with at least 16 characters.
