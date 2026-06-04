# Legal Review Packet

Last updated: 2026-06-03 KST

## Status

Counsel review status: `NOT_REVIEWED`.

This packet is a handoff to qualified legal counsel. It is not legal advice. Codex/AI cannot approve legal readiness, regulated financial-service posture, data-license posture, privacy posture, marketing copy, or paid/unrestricted external release.

Until written counsel approval is received, the product must remain owner/operator trial only:

- No unrestricted external release.
- No paid launch.
- No investment-advice positioning.
- No personalized trade-instruction claims.
- No investment-action vocabulary, model-trigger wording, or promised-outcome wording before counsel approves final copy.
- No marketing that implies deterministic scoring or AI summaries produce trade instructions.

Allowed wording before approval:

- "decision-support"
- "research candidate"
- "monitoring candidate"
- "screening workspace"
- "deterministic scoring"
- "template summary" when OpenAI is not configured
- "OpenAI/template summary layer" only when it is clear that selection is deterministic and the summary layer is explanation-only

## Product Facts For Counsel

VCB-Alt is a market-wide stock screening decision-support web app. It produces scores, rationale, charts, provider labels, freshness indicators, and risk notes. It does not place trades, connect to brokerage accounts, manage assets, or guarantee outcomes.

Current selection architecture:

- Deterministic scoring selects and ranks candidates.
- Market-universe mode is the intended product direction.
- Manual watchlists are secondary research inputs, not the core candidate-output path.
- OpenAI, when configured, is an explanation/summarization layer only.
- When OpenAI is not configured, the app uses deterministic template summary text.
- In production live-data-required mode, sample/demo fallback must not produce final candidates.

Current operating posture:

- Release channel: owner/operator trial.
- `public_launch_ready=false`.
- `NOT_READY_FOR_1000_USER_SAAS`.
- Terms, Privacy, and Risk Disclosure drafts are not legal-reviewed launch documents.

## Source Materials For Counsel

Review these files before approving any public or paid launch:

- `README.md`
- `TERMS.md`
- `PRIVACY.md`
- `RISK_DISCLOSURE.md`
- `PRODUCT_REQUIREMENTS.md`
- `USER_FLOWS.md`
- `RELEASE_DECISION.md`
- `SECURITY_COMPLIANCE_1000_USER.md`
- `AUTH_MFA_RBAC_PLAN.md`
- `MONITORING_ALERTING_PLAN.md`
- `NEON_BACKUP_RESTORE_DRILL.md`
- `PROVIDER_KEYS_SETUP.md`
- `ALGORITHM_REVIEW.md`
- `API_CONTRACT_V1.md`

## Counsel Review Questions

1. Does deterministic ticker scoring create investment-adviser registration risk if offered to retail users or for compensation?
2. Are the labels "research candidate", "monitoring candidate", and "decision-support" sufficient for the intended jurisdictions and business model?
3. Does any UI, API response, README, marketing copy, or screenshot imply personalized portfolio guidance, trade instruction, or promised performance?
4. Are Terms, Privacy, and Risk Disclosure drafts adequate for owner/operator trial, limited external testing, unrestricted external release, and paid use?
5. What user data, audit logs, provider metadata, and account/session data are personal data under the intended jurisdictions?
6. What retention, export, deletion, breach-notification, and support obligations apply?
7. Do Alpaca, Finnhub, Yahoo, SEC, OpenAI, and any future providers allow this display, caching, redistribution, and summarization pattern?
8. Do options, short interest, analyst revisions, news, and filing summaries require additional risk, suitability, or licensing disclosures?
9. What compliance review is required for social media, landing pages, screenshots, example tickers, or performance-like claims?
10. What disclaimers must appear in-product versus in legal documents?

## Materials Counsel Should Approve Or Reject

Counsel should mark each item:

- Approved for owner/operator trial.
- Approved for limited private beta.
- Approved for public free beta.
- Approved for paid public use.
- Rejected or requires revision.

Items:

- Product positioning.
- UI labels and candidate rationale copy.
- Terms Of Use.
- Privacy Notice.
- Risk Disclosure.
- Data-provider license posture.
- AI/template explanation disclosures.
- Account deletion/export/retention process.
- Monitoring and incident communication process.
- Marketing screenshots and examples.

## Copy Restrictions Before Counsel Approval

Do not use:

- Direct purchase-instruction labels.
- Strong purchase-classification labels.
- Event-trigger labels that imply a trade should happen.
- Regulated-service labels that imply counsel-approved financial-service status.
- Promised-outcome labels.
- "promised outcome"
- "outperform guarantee"
- "1000-user SaaS ready"
- "external release ready"
- "personalized trade instruction"

Use instead:

- "research candidate"
- "monitoring candidate"
- "decision-support output"
- "screening result"
- "deterministic score"
- "review rationale"
- "data freshness"
- "provider coverage"

## Counsel Sign-Off Record

Do not fill this section by AI.

- Counsel name:
- Firm/company:
- Jurisdictions reviewed:
- Date:
- Approved scope:
- Required changes:
- Launch restrictions:
- Follow-up review date:

## Official Reference Points

- SEC/Investor.gov investment adviser overview: https://www.investor.gov/index.php/introduction-investing/getting-started/working-investment-professional/investment-advisers
- SEC staff guidance on investment adviser definition: https://www.sec.gov/interps/legal/slbim11.htm
- FINRA Rule 2210 communications with the public: https://www.finra.org/rules-guidance/rulebooks/finra-rules/2210
- SEC/Investor.gov social-media investing caution: https://www.investor.gov/additional-resources/spotlight/directors-take/finfluencers-celebrities-social-media
- SEC Regulation S-P risk alert: https://www.sec.gov/files/OCIE%20Risk%20Alert%20-%20Regulation%20S-P.pdf

## Launch Decision

Current legal launch decision: `BLOCKED_PENDING_COUNSEL_REVIEW`.

Do not launch as paid, unrestricted public, or investment-advice-adjacent software until counsel provides written approval for registration posture, disclaimers, marketing copy, risk disclosures, privacy policy, data-provider licenses, retention/deletion process, support process, and complaint handling.
