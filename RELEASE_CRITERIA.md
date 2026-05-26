# Release Criteria

## Minimum Release Conditions

- Local install works from a clean checkout.
- `.env.example` exists and documents required versus optional variables.
- `python -m vcb_alt init-db` creates the local SQLite database.
- Core user flow works: initialize, add watchlist, evaluate ticker, scan watchlist, inspect logs.
- Auth/permission risk is controlled by local execution by default and token-gated public-demo mode when explicitly enabled.
- User input validation exists for tickers, scores, prices, sizes, and destructive confirmations.
- Error handling produces consistent success/failure responses.
- Loading, empty, error, and success states are represented in CLI output.
- Basic security controls exist: no hardcoded secrets, redacted logging, external APIs disabled by default.
- Tests pass.
- README explains setup, environment, test, build, and known limitations.
- Operator logs and failed jobs are available.

## Private Beta Criteria

- All P0 items closed.
- No known crash in core CLI flow.
- Tests and bytecode build pass.
- Remaining P1 items are documented and not safety-critical.
- The product is clearly labeled as local decision-support, not investment advice.

## Public Beta Criteria

- Optional real-data integrations are implemented behind explicit opt-in.
- External provider rate limits, retries, and failures are tested.
- Security review is complete for any unrestricted network-accessible surface.
- Data deletion/export is verified on representative data.
- UX has been tested with a non-developer operator.

## Not Ready Conditions

- Any command required for core use fails.
- Invalid input crashes the app.
- Secret values are logged.
- The app performs unexpected external API calls.
- The app exposes a public web/API surface without at least token-gated access.
- The app suggests guaranteed returns or automatic trading.
