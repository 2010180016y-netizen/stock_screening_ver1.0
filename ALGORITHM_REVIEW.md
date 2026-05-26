# Algorithm Review

Date: 2026-05-26 KST

## One-Line Summary

VCB-Alt scans the configured market universe, prefilters live/near-live movers, enriches the strongest candidates, ranks them by seven opportunity archetypes, blocks final selection when data coverage is too weak, then selects up to three candidates with portfolio-level exposure and volatility limits.

## End-To-End Flow

1. The UI or CLI starts the configured scan mode. The product default is now `market_universe`; `watchlist` remains as a legacy/manual research mode.
2. `vcb_alt.market_universe.load_market_universe()` loads active US equities from Alpaca assets when credentials are available, otherwise `data/universe.csv`, otherwise a clearly labeled sample fallback.
3. `vcb_alt.market_universe.prefilter_market_candidates()` calls Alpaca multi-symbol stock snapshots in batches and ranks the universe by live price change, relative volume, dollar liquidity, and spread.
4. The top prefilter names are normalized into `StockSnapshot` objects and enriched through Finnhub or `data/enrichment.csv`.
5. `vcb_alt.scoring.evaluate_snapshot()` validates the ticker and price, scores all archetypes, applies a complexity modifier, checks data coverage, and returns an `EvaluationResult`.
6. `vcb_alt.portfolio.select_portfolio()` filters to `can_enter=true`, sorts the eligible results, applies portfolio constraints, and returns the final selection.
7. `vcb_alt.web` renders the result as decision-support copy, not trade instructions.

## Current AI And Data Acquisition

- Stock selection itself is deterministic scoring, not an LLM call.
- OpenAI is used only for optional explanation summaries when `VCB_ALT_AI_SUMMARY_PROVIDER=openai`; otherwise the app uses deterministic template summaries.
- The app does not browser-scrape arbitrary websites. It uses provider APIs: Alpaca `/v2/assets` for the market universe, Alpaca `/v2/stocks/snapshots` for live/near-live prefilter data, Finnhub REST endpoints for research enrichment, Yahoo/Stooq chart endpoints for detail/history when configured, and optional SEC JSON metadata.

## Data Inputs

The snapshot model supports these groups:

- Market data: price, 12-week return, 12-month return, 52-week drawdown, moving-average distance, breakout volume, volume z-score, relative strength versus benchmark.
- Fundamentals and earnings: market cap, revenue surprise, earnings surprise, revenue acceleration, EPS revision, analyst revision score, raised guidance.
- Catalysts and narrative: news catalyst, headline count, SEC filing catalyst, FDA milestone, data-center narrative, Bitcoin return, mining capacity, peer return.
- Positioning: float, insider buys, short interest, days to cover, borrow rate, call/put open interest, put-call ratio, call open-interest change.
- Intraday overlay: optional Alpaca quote/trade/minute data.
- Enrichment overlay: optional Finnhub or operator CSV research data.

## Archetype Scores

All archetype scores are clamped between `0` and `100`.

- `A_AI_TECH`: earnings/revenue surprise, revenue acceleration, sector relative strength, insider buying, breakout volume, raised guidance, analyst revisions, trend bonus.
- `B_CRYPTO_PIVOT`: Bitcoin strength, catalyst, mining capacity, 200DMA recovery, volume z-score, drawdown recovery, surge bonus.
- `C_QUANTUM`: low float, small market cap, catalyst, peer return, volume z-score, low nominal price, surge bonus.
- `D_BIOTECH`: FDA milestone, insider buying, moderate short interest, market-cap range, news catalyst, trend score.
- `E_SHORT_SQUEEZE`: short interest, days to cover, borrow rate, call open-interest change, volume z-score, catalyst, surge bonus.
- `F_PICK_SHOVEL`: data-center narrative, sector relative strength, 200DMA status, EPS/analyst revision, revenue acceleration, breakout volume, trend bonus.
- `G_TECHNICAL_MOMENTUM`: Yahoo/Stooq EOD trend metrics plus Alpaca intraday surge/relative-volume momentum. Stale sources are disabled.

## Complexity Modifier

The selected primary archetype receives a modifier from `-25` to `+25`.

Positive factors:

- 30-day news catalyst.
- Call open-interest change above `200%`.
- Short interest at least `25%`.
- Volume z-score at least `2.5`.
- Extra crypto bonus when Bitcoin six-month return is at least `50%`.

Negative factors:

- Biotech with short interest at least `20%`.
- AI/Tech or Pick-and-Shovel names with sector relative strength below `-5pp`.

## Entry Gate

A ticker can enter final selection only when both are true:

- Combined score is at least `55`.
- Data coverage score is at least `60`.

Data coverage is calculated by group:

- Market price/volume present: `35` points.
- Fundamentals/earnings present: `25` points.
- Catalyst/news present: `20` points.
- Float/short/options/insider positioning present: `20` points.

Coverage labels:

- `80+`: multi-source.
- `60-79`: enriched.
- `35-59`: price-volume-only.
- `<35`: insufficient.

This is why price/volume-only market sweeps can show monitoring results but are blocked from final selection until fundamentals/catalyst/positioning enrichment exists.

## Portfolio Selection

Final selection uses these constraints:

- Maximum positions: `3`.
- Maximum total suggested exposure: `75%`.
- Maximum high-volatility archetypes: `1`.
- Duplicate primary archetypes are avoided, except `G_TECHNICAL_MOMENTUM` can fill multiple slots.

2026-05-24 improvement:

- Equal-score candidates now prefer higher `data_coverage_score` before portfolio ergonomics. This prevents equally scored but weaker-evidence names from outranking stronger-evidence names solely because of input order.

Sort order is now:

1. Higher combined score.
2. Higher data coverage.
3. Lower high-volatility penalty.
4. Higher suggested size.
5. Ticker as deterministic final tie-breaker.

## Important Limitations

- The app is decision support only and does not execute trades.
- Sample data is intentionally useful for demo verification but should not be treated as live market evidence.
- Yahoo/Stooq chart data is end-of-day or delayed, not tick-by-tick real time.
- AI summaries explain the deterministic score; they do not replace the scoring engine.
- Production accuracy depends on configured and monitored data providers.

## UI Localization Finding

Before this review, Korean mode translated static labels but still exposed dynamic English strings from API fields, including archetype names, public labels, rationale, precision notes, data-quality notes, AI summary headings, and expert consensus text.

Fix applied:

- English mode remains unchanged.
- Korean mode now translates dynamic status labels, archetypes, coverage labels, source names, rationale bullets, precision notes, warnings, detail-page metric labels, AI summary sections, and expert consensus copy.
- Ticker symbols and company/security names remain unchanged as requested.
