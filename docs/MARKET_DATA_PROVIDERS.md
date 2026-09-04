# Market Data Provider Options

Researched 2026-08-25, when production had been blocked for weeks on an Alpaca `HTTP 401`.
The question this answers: what else can supply the market scan, and what does each option
cost in money, effort and data quality.

## What the app actually needs

The scan has three provider-shaped jobs, and they are not interchangeable.

| Job | What it needs | Today |
| --- | --- | --- |
| **Universe** | A list of tradable US equities | Alpaca assets, or an operator CSV (`data/universe.csv`) |
| **Prefilter** | Rank thousands of symbols down to ~30, cheaply | Alpaca snapshots, **or the end-of-day path added 2026-08-25** |
| **Enrichment** | Fundamentals, news, short interest per candidate | Finnhub (already working in production) |

The prefilter is the demanding one. Alpaca returns hundreds of symbols per request, so a
5,000-symbol sweep costs tens of calls. Providers that quote one symbol per request cannot
do that sweep at any sane rate limit — which is why the fallback added here is capped and
meant for a curated universe rather than the whole market.

## Options

| Provider | Bulk quotes | Universe list | Free tier | Fit |
| --- | --- | --- | --- | --- |
| **Alpaca** (current) | Yes — multi-symbol snapshots | Yes | Yes, with account | Best fit; blocked only by credentials |
| **Yahoo** (already integrated) | No — one request per symbol | No | Keyless | **Now wired as the fallback prefilter.** End-of-day only |
| **Finnhub** (already integrated) | No — `/quote` is one symbol | Yes (`/stock/symbol?exchange=US`) | 60 req/min | Already used for enrichment; could replace Alpaca for the *universe* |
| **Polygon.io** | Yes — full-market snapshot in one call | Yes | Basic tier is reference/EOD; snapshots are paid | Best paid replacement for the prefilter |
| **Financial Modeling Prep** | Yes — batch quote endpoint | Yes | Limited | Reasonable paid alternative |
| **Twelve Data** | Yes — comma-separated symbols | Yes | ~800 req/day, 8/min | Workable at small universe sizes |
| **Tiingo** | `GET /iex` returns all tickers at once | Yes | Usable free tier | Strong shape, but IEX changed its data agreement in Feb 2025: without a signed agreement you get derived reference prices, not the full feed |
| **Stooq** (already integrated) | No | No | Keyless | End-of-day CSV; some downloads need a key/captcha |
| **IEX Cloud** | — | — | — | **Discontinued.** Do not plan around it |

## Running without Alpaca (verified 2026-08-25)

If an Alpaca key is not available, the product still works. Alpaca is only required for
one job - ranking thousands of symbols on intraday quotes - and nothing else depends on
it. Yahoo covers the market group, Finnhub covers the other three coverage groups, and
the watchlist supplies the universe from the dashboard sidebar.

```dotenv
VCB_ALT_SCAN_MODE=market_universe
VCB_ALT_EXTERNAL_API_ENABLED=true

# Market data and ranking, no key required
VCB_ALT_DATA_PROVIDER=yahoo
VCB_ALT_MARKET_PREFILTER_PROVIDER=yahoo
VCB_ALT_MARKET_UNIVERSE_PROVIDER=auto      # uses the watchlist when no CSV/Alpaca universe exists

# Enrichment - this is what lifts data coverage past the selection gate
VCB_ALT_RESEARCH_DATA_PROVIDER=finnhub
VCB_ALT_FINNHUB_API_KEY=your-existing-finnhub-key

# Alpaca stays off
VCB_ALT_INTRADAY_DATA_PROVIDER=none
```

Then add tickers in the dashboard sidebar and press **Scan full market**.

Why this reaches a selection, measured rather than assumed:

| Stage | Result |
| --- | --- |
| Yahoo end-of-day snapshot alone | coverage 35/100, `can_enter=false` - below the 60 gate |
| Plus Finnhub enrichment | coverage 100/100, `can_enter=true`, score 71 |

This matches what production already recorded before the credential broke: a PLTR
analysis returned `yahoo+finnhub` with data coverage `100/100`.

### The whole path was verified against the real network (2026-09-02)

Stub tests passing is not the same as the path working - that mistake was already made
once on this exact feature. So the preset above was run with real Yahoo requests, with
`VCB_ALT_MARKET_SCAN_REQUIRES_LIVE_DATA=true`, and with no Alpaca or Finnhub key at all:

```
OK [200] Market-universe scan completed.
Selected: 0/3
- NVDA: Data coverage 35/100 is below the 60 required for selection; add research enrichment.
```

The scan completes and reports per-symbol reasons. Nothing is selected, which is correct
without enrichment. Before the fail-closed gate stopped requiring an `alpaca:` source, the
same run was discarded entirely with "not backed by Alpaca stock snapshots".

### How long a scan takes

One request per symbol, so wall-clock is set by how many run at once
(`VCB_ALT_PROVIDER_FETCH_WORKERS`). Measured on 15 real symbols:

| Workers | 15 symbols | Implied per symbol | 150 symbols |
| --- | --- | --- | --- |
| 1 | 20.4s | 1.36s | about 200s |
| 8 (default) | 5.8s | 0.32s | about 50s |

The practical effect is how much of the universe gets ranked before
`VCB_ALT_PREFILTER_TIME_BUDGET_SECONDS` stops the run: roughly 15 symbols serially versus
60 at the default width, in the same 20 seconds.

### What you give up without Alpaca

- **Whole-market discovery.** Yahoo answers one symbol per request, so the universe has
  to be a watchlist or CSV of a few hundred names, not 5,000. `VCB_ALT_PREFILTER_TIME_BUDGET_SECONDS`
  stops a run that would overrun a serverless limit and the scan reports how far it got.
- **Intraday freshness.** Ranking uses the last two daily bars, so a scan reflects
  yesterday's close rather than a live move.

Neither blocks research use. If whole-market intraday discovery becomes necessary later,
Polygon.io's full-market snapshot is the closest replacement in shape, at a paid tier.

## Recommendation

1. **If you cannot get an Alpaca key, use the preset above.** Yahoo plus your existing
   Finnhub key reaches full data coverage and a real selection; Alpaca is only needed for
   whole-market intraday discovery.
2. **Fix Alpaca when you can.** It is the only option that does the whole-market sweep on
   a free tier, the integration is written and tested, and the failure is a credential
   mismatch rather than anything structural. [GO_LIVE_RUNBOOK.md](GO_LIVE_RUNBOOK.md) Step 3
   covers it.
3. **Details of the end-of-day prefilter.** Set `VCB_ALT_MARKET_PREFILTER_PROVIDER=yahoo`
   with an operator universe in `universe.csv` under `VCB_ALT_DATA_DIR`. No account, no key,
   no payment. Verified end to end on 2026-08-25: a five-symbol universe scored 58-96 and
   the portfolio selected three names totalling 62.95%.

   Two things this path needs, both of which the scan reports:
   - **Enrichment is mandatory for selection.** Price and volume alone reach only 35/100
     data coverage, below the 60 gate, so nothing is selectable. Supply `enrichment.csv`
     (also under `VCB_ALT_DATA_DIR`) or configure Finnhub. This gate is deliberate.
   - **It costs roughly a second per symbol**, since Yahoo answers one symbol per request.
     `VCB_ALT_PREFILTER_TIME_BUDGET_SECONDS` stops the run before it overruns a serverless
     execution limit and reports how many symbols were skipped.
4. **If whole-market discovery is required,** Polygon.io's full-market snapshot is the closest
   replacement in shape, at a paid tier. Twelve Data is the cheapest workable option for a
   universe of a few hundred symbols.

## What was deliberately not done

No account was created and no API key was entered on the operator's behalf. Those steps
require the account holder. The code-side work — making the prefilter pluggable and adding
a path that needs no credential — is complete and tested.

Sources: [Tiingo IEX documentation](https://www.tiingo.com/documentation/iex),
[Polygon full market snapshot](https://polygon.io/docs/rest/crypto/snapshots/full-market-snapshot),
[FMP developer docs](https://site.financialmodelingprep.com/developer/docs),
[2026 free stock API comparison](https://thenextgennexus.com/2026/05/15/10-best-free-stock-market-apis-2026/)
