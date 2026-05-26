# User Flows

## 1. First Visit / First Run

1. User reads README.
2. User creates a virtual environment and installs the package.
3. User copies `.env.example` to `.env`.
4. User runs `python -m vcb_alt init-db`.
5. System creates local directories and SQLite tables.
6. System reports next suggested command.

Empty state: if no watchlist exists, the CLI tells the user how to add tickers or seed sample tickers.

## 2. Signup or Login

MVP decision: no remote signup/login exists because the product is local-first and single-operator. Controlled public-demo mode uses a shared deployment token, not user accounts.

1. User runs commands on their own machine.
2. If public web mode is enabled, user opens `/?token=<access-token>` once and receives an HTTP-only same-site cookie.
3. Admin/operator actions remain local commands or token-protected dashboard actions.
4. Future SaaS login is blocked from release scope until authentication, RBAC, privacy policy, and legal review exist.

## 3. Core Feature Use

1. User adds tickers with `python -m vcb_alt watchlist add PLTR MSTR`.
2. User evaluates one ticker with `python -m vcb_alt evaluate PLTR`.
3. System validates ticker format.
4. System loads deterministic sample, manual CSV, or explicitly enabled automatic EOD market data.
5. System scores archetype fit, setup strength, risk constraints, and suggested action.
6. System logs the action without secrets.

## 4. Result Review

1. User sees ticker, combined score, setup status, primary archetype, can-enter flag, suggested size, stop loss, and rationale.
2. User sees risk and legal disclaimer that this is decision support, not investment advice.
3. User can request JSON output for automation.

## 5. Error Recovery

1. If ticker is malformed, system returns a 400-style validation error.
2. If DB is missing, system tells the user to run `init-db`.
3. If watchlist is empty, system returns an empty state and add command.
4. If data is missing or a provider fails, system records a failed job and returns a clear message.
5. System never prints secrets in error text.

## 6. Settings Change

1. User edits `.env` or `config.yaml`.
2. User runs `python -m vcb_alt doctor`.
3. System validates paths, log level, timezone, DB URL, and external API opt-in flags.
4. System reports warnings for disabled external providers as safe defaults.

## 7. Data Deletion / Account Deletion

There is no remote account in MVP.

1. User runs `python -m vcb_alt admin export --out exports/export.json`.
2. User runs `python -m vcb_alt admin delete-data --confirm DELETE_LOCAL_DATA`.
3. System deletes local DB rows and reports what was removed.
4. System keeps no cloud copy.

## 8. Operator Check Flow

1. Operator runs `python -m vcb_alt admin logs`.
2. Operator reviews recent actions.
3. Operator runs `python -m vcb_alt admin failures`.
4. Operator sees failed command, safe error message, and timestamp.
5. Operator follows OPERATIONS.md for recovery.
