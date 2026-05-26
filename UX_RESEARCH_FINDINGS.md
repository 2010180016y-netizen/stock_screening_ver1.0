# UX Research Findings

Research date: 2026-05-19 KST

## Product Direction To Preserve

VCB-Alt should remain a decision-support stock screening desk. It should not become a filter-heavy clone of TradingView or Finviz. The core UX is: fetch market data, evaluate the watchlist, show the few names worth reviewing, explain why, and expose data/operation trust signals.

## External User Pain Signals

1. Screener alerts are a recurring unmet need.
   - TradingView community users repeatedly ask for alerts when a new symbol appears in a screener.
   - Product implication: add alert settings later, but default to quiet behavior so users are not spammed.

2. Saved screen/watchlist continuity matters.
   - TradingView documentation emphasizes saved screens with watchlist filters and saved configuration.
   - Product implication: keep the watchlist stable and make the current decision state obvious after refresh.

3. Filter-heavy products create cognitive load.
   - TradingView and Finviz are powerful, but users must still interpret large tables and many filters.
   - Product implication: prioritize final candidates, rationale, data freshness, and status grouping over adding more filters.

4. Mobile and compact layouts are a differentiator.
   - Finviz reviews and market reviews call out mobile UX limitations.
   - Product implication: use cards for final candidates and keep tables secondary.

5. Notification control must be conservative.
   - App Store reviews for stock scanner apps mention excessive notifications and upgrade prompts.
   - Product implication: future alerts should be opt-in and limited to high-signal events.

## Sources Reviewed

- TradingView Help Center, watchlist and saved-screen scanning: https://www.tradingview.com/support/solutions/43000724549-how-to-scan-watchlist-or-flagged-list/
- TradingView community request for screener alerts: https://www.reddit.com/r/TradingView/comments/1rxxr7t/alerts_on_screener/
- TradingView community pain-point thread: https://www.reddit.com/r/TradingView/comments/1phy727/biggest_pet_peeves_about_tradingview/
- Finviz user reviews: https://www.trustpilot.com/review/finviz.com
- StockBrokers Finviz review: https://www.stockbrokers.com/review/tools/finviz
- Stock scanner app reviews: https://apps.apple.com/us/app/1501485233?platform=iphone&see-all=reviews

## Implemented UI Response

- Added a decision-first layout with final entry candidates at the top of the main workspace.
- Split scan results into `Actionable setups` and `Monitor or excluded`.
- Added data status metadata for provider, data date, and operational status.
- Added candidate rationale cards using real `rationale`, `precision_notes`, and `warnings` from the scoring engine.
- Added score detail modal so users can inspect why a ticker was selected without leaving the workflow.
- Kept the implementation dependency-free: no Tailwind CDN, Google Fonts, Material Symbols, or Chart.js.

## Deferred Improvements

- Opt-in candidate alerts when a ticker enters or leaves final selection.
- Saved screen/history view showing last scan versus current scan.
- Durable user accounts and per-user watchlists before broad public launch.
- Mobile visual regression tests.

## 2026-05-19 Expert Consensus For Ticker Detail UX

The detail page should answer the user's immediate trust questions without becoming a general-purpose financial terminal:

- Why was this ticker selected?
- What market state is the score reading?
- What industry/sector is the company in?
- What did price and volume do over the last five years?
- What is missing from the current provider data?

Required detail page elements:

- Five-year price/volume chart, labeled with provider and data freshness.
- Sector and industry.
- Selection rationale from the scoring engine.
- Score, scoring version, review state, allocation guide, and risk reference.
- Trend metrics such as 12-week return, 12-month return, 52-week drawdown, moving-average distance, trend template score, surge score, and relative strength where available.
- Explicit warning that EOD market data is not tick-by-tick real-time.
