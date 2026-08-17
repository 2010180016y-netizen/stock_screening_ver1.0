# Privacy Notice

Status: owner/operator-trial draft only. Not legal-reviewed. Do not use as a public, paid, or unrestricted launch document until qualified counsel approves it.

VCB-Alt currently stores the minimum data needed for an owner/operator-trial screening workflow.

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

Before open signup, VCB-Alt needs per-user accounts, tenant isolation, export/delete workflows, retention policy, audit-safe anonymization, and qualified legal review.

## Launch Requirement

This notice must be reviewed and approved by qualified counsel before public, paid, or trading-instruction-adjacent launch.
