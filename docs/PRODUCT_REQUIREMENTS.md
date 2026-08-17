# Product Requirements

## 1. Product Purpose

Provide a stock screening assistant that scans a configured US-equity market universe, discovers high-scoring candidates from live/near-live market data plus research enrichment, reviews portfolio-risk constraints, and maintains auditable screening logs without making trades automatically.

## 2. Target Users

- MVP target: one local operator with basic command-line familiarity.
- Future target: retail investors using a managed dashboard.
- Admin/operator: the same local user who manages data, logs, and configuration.

## 3. User Problems

- The user needs a repeatable daily/weekly process for identifying candidate US stocks.
- The user needs risk constraints to prevent over-concentration, high-volatility stacking, and repeated impulsive entries.
- The user needs records of why a ticker was accepted, rejected, or flagged.
- The user needs a tool that can run locally without leaking portfolio details or triggering paid APIs by surprise.

## 4. Core Features

- Local SQLite initialization.
- Market-universe scan mode that does not depend on user-entered ticker lists.
- Watchlist add/list/remove commands for manual research lists.
- Single ticker evaluation with validation and risk notes.
- Market scan with empty/loading/error/success states represented in CLI output.
- Offline sample data provider for deterministic first-run use.
- Manual CSV data provider for operator-supplied current snapshots.
- Automatic Yahoo/Stooq end-of-day price/volume data providers with explicit opt-in and local cache.
- Technical Momentum scoring for automatic price/volume data, gated so chart-only candidates cannot become final selections.
- Optional enrichment CSV overlay for operator-verified fundamentals, catalysts, short/options, insider, float, and related context.
- Optional research-data API enrichment for fundamentals, earnings surprise, news catalysts, analyst trends, short interest, options, and insider activity.
- Optional Alpaca active-asset universe and near-real-time quote/snapshot layer for market-wide prefiltering when licensed credentials are configured.
- Optional SEC filing metadata layer for recent disclosure context.
- Explanation summary layer that explains why deterministic scoring and portfolio constraints surfaced a ticker, including key factors, risk flags, and data-quality limitations.
- Data coverage scoring across market, fundamental, catalyst, and positioning groups.
- Final candidate selection with max-position, total-exposure, duplicate-archetype, and high-volatility limits.
- Brief selection explanation on each selected candidate.
- Click-through ticker detail page with current analysis, five-year chart, sector/industry, and selection rationale.
- Responsive dashboard and ticker detail pages that remain usable on mobile and browser zoom.
- Korean/English language selection for the public dashboard and ticker analysis experience.
- Operator logs and failed-job inspection.
- Token-protected local/public-demo web dashboard.
- Local data export/delete command.
- Environment sample and friendly missing-config behavior.
- Tests and documented verification commands.

## 5. Non-Core Features

- Open public signup and full multi-user authentication.
- Payment processing.
- Automatic broker trading.
- Real-time streaming prices.
- Licensed paid production data provider integrations.
- LLM transcript scoring.

## 6. MVP Scope

This improvement ships a Python 3.11+ local CLI package and token-protected web dashboard that can scan a market universe, prefilter live movers, enrich top names, and produce constrained research candidate output. It preserves the original archetype product direction by allowing price/volume data to support timing while requiring enrichment coverage before final selection.

## 7. Excluded From This Improvement

- Any unrestricted public SaaS or account signup flow.
- Any broker integration or automatic order placement.
- Any paid external API calls by default.
- Any trading-instruction claims or promised outcome claims.
- Any collection of third-party personal information.

## 8. Success Criteria

- A new operator can follow README/SETUP and run the product locally.
- `init-db`, `watchlist`, `evaluate`, `scan`, `admin logs`, and `admin failures` work.
- `scan` and `select` produce a constrained final candidate list from the market universe when `VCB_ALT_SCAN_MODE=market_universe`.
- Automatic market-data mode can fetch/cache EOD data without silently falling back to sample data.
- Research-data API enrichment only runs when explicitly configured with a provider and API key.
- Intraday quote and OpenAI explanation-summary providers only run when explicitly configured with credentials.
- Chart-only automatic data is blocked from final selection until enrichment coverage reaches the minimum data-quality gate.
- Token-protected web mode can run as a controlled demo.
- A selected ticker explains why it was selected and links to a detail page with chart, industry, current status, and rationale.
- Users can switch between Korean and English without losing scan or selection state.
- Text inside cards, metric boxes, badges, buttons, and table rows wraps inside its container on mobile.
- Invalid input produces friendly errors without crashing.
- Tests pass.
- Build/import verification passes.
- Logs and failed jobs are available for troubleshooting.
- No secrets are committed or printed.

## 9. Failure Criteria

- The app cannot be installed or imported.
- The database cannot initialize.
- A malformed ticker or data row crashes the app.
- The app implies automatic trading or promised outcomes.
- The app calls external APIs without explicit opt-in.
- Logs expose API keys, tokens, credentials, or private notes.
- The app silently treats stale/manual data as verified live market data.
- The app promotes price-only chart factors as final selections without fundamentals, catalysts, or positioning coverage.
