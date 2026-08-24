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

## Recommendation

1. **Fix Alpaca.** It is the only option that does the whole-market sweep on a free tier,
   the integration is written and tested, and the failure is a credential mismatch rather
   than anything structural. [GO_LIVE_RUNBOOK.md](GO_LIVE_RUNBOOK.md) Step 3 covers it.
2. **Until then, run the end-of-day prefilter.** Set `VCB_ALT_MARKET_PREFILTER_PROVIDER=yahoo`
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
3. **If Alpaca cannot be recovered,** Polygon.io's full-market snapshot is the closest
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
