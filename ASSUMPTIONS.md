# Assumptions

## 2026-05-20 Full Data Provider Work

- Real Alpaca, Finnhub, SEC, and OpenAI production credentials were not present in the workspace, so implementation uses disabled-by-default provider switches and local cache fixtures for verification.
- Alpaca is treated as the near-real-time quote/snapshot layer, while Yahoo/Stooq remain daily chart and technical-history providers.
- SEC submissions metadata is used for filing context; deep filing text analysis remains a later licensed/queued ingestion task.
- The default AI explanation layer is deterministic template output so public users still get an explanation without triggering external AI cost.

Last updated: 2026-05-16

## Current 0.2.0 Context

1. The repository now contains a runnable local CLI private-beta product plus 1000-user SaaS design documents.
2. The CLI is still not a shared service and must not be exposed directly to 1000 users.
3. The 1000-user design assumes a new web/API platform using authenticated multi-tenant storage, workers, cache, and observability while reusing only domain-safe scoring and validation logic from the CLI.
4. Any public distribution of scoring language such as `BUY_CANDIDATE`, suggested size, or stop loss requires legal review and likely product-copy changes before launch.

## Historical 0.1.0 Starting Assumptions

1. This repository currently contains product and architecture documents only. There is no runnable application code, package manifest, database migration, test suite, or deployment configuration.
2. The intended launchable product for this iteration is a local-first personal US stock screening CLI, not a public multi-user SaaS.
3. The product must not place trades automatically. It can generate screening results, suggested position sizing, risk notes, and logs, but final investment decisions remain with the user.
4. External market-data and LLM APIs are disabled by default to avoid unexpected cost, rate-limit, privacy, and legal risks. The first production-grade baseline uses deterministic local/sample data and clear operator prompts.
5. Authentication for this iteration is interpreted as local operator control: no remote web surface is exposed, admin commands run locally, and any future SaaS authentication is explicitly out of scope until a web/API backend exists.
6. Because the existing Markdown files show mojibake/encoding corruption in Korean text, the new operational docs use clean UTF-8 Korean/English and leave the original source documents untouched.
7. "Build" for this Python CLI product means bytecode compilation and package import verification. There is no frontend bundle unless a future dashboard is added.
