# Privacy Notice

Status: starter public-beta draft, not legal-reviewed.

VCB-Alt currently stores the minimum data needed for a token-protected screening workflow.

## Data Stored In The Current Beta

- Watchlist tickers
- Evaluation outputs
- Operation logs
- Failed-job records
- Local or serverless cache data from configured market-data providers

The current app does not require brokerage credentials and should not be used to store private brokerage, banking, tax, or identity documents.

## Secrets

Access tokens and provider credentials must be configured as environment variables. They must not be committed to the repository or written to logs.

## Future Public SaaS Requirements

Before open signup, VCB-Alt needs per-user accounts, tenant isolation, export/delete workflows, retention policy, audit-safe anonymization, and legal review.

## Launch Requirement

This notice must be reviewed by qualified counsel before broad public launch.
