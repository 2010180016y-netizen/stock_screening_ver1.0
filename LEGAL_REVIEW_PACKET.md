# Legal Review Packet

Last updated: 2026-05-22 KST

## Scope

This packet is for qualified legal counsel. It is not legal advice and does not clear the product for public launch.

VCB-Alt is a stock screening decision-support web app. It produces scores, rationale, charts, provider labels, and risk warnings. It does not place trades.

## Product Claims To Review

- "Decision support only."
- "No automatic trading."
- "Not investment advice."
- "High-priority review candidate."
- "Review candidate."
- "Monitor only."
- "AI summary" when the default is deterministic template text unless OpenAI is explicitly configured.

## Key Legal Questions

1. Whether scoring and ticker selection create investment-adviser registration risk when offered for compensation.
2. Whether current labels, scoring explanations, and UI copy are sufficient to avoid personalized investment advice claims.
3. Whether public marketing pages, screenshots, and candidate examples are retail communications requiring broker-dealer/FINRA review in any planned business model.
4. Whether Terms, Privacy, and Risk Disclosure drafts are adequate for the intended jurisdictions.
5. Whether the product may collect personal data subject to privacy, retention, deletion, or security obligations.
6. Whether AI-generated or template-generated summaries require additional disclosures.
7. Whether provider data licenses allow redistribution/display in the planned public product.
8. Whether options/short-interest/news/analyst data creates special suitability, risk, or licensing obligations.

## Source Materials For Counsel

- `README.md`
- `TERMS.md`
- `PRIVACY.md`
- `RISK_DISCLOSURE.md`
- `PRODUCT_REQUIREMENTS.md`
- `USER_FLOWS.md`
- `SECURITY_COMPLIANCE_1000_USER.md`
- `AUTH_MFA_RBAC_PLAN.md`
- `MONITORING_ALERTING_PLAN.md`
- `PROVIDER_KEYS_SETUP.md`
- `RELEASE_DECISION.md`

## Official Reference Points

- SEC/Investor.gov investment adviser overview: https://www.investor.gov/index.php/introduction-investing/getting-started/working-investment-professional/investment-advisers
- SEC staff guidance on investment adviser definition: https://www.sec.gov/interps/legal/slbim11.htm
- FINRA Rule 2210 communications with the public: https://www.finra.org/rules-guidance/rulebooks/finra-rules/2210
- SEC/Investor.gov finfluencer caution: https://www.investor.gov/index.php/additional-resources/spotlight/directors-take/finfluencers-celebrities-social-media
- SEC Regulation S-P risk alert: https://www.sec.gov/files/OCIE%20Risk%20Alert%20-%20Regulation%20S-P.pdf

## Launch Decision

Current status: legal review pending.

Do not launch as a paid or unrestricted public investment product until counsel signs off on:

- Registration posture.
- Disclaimers.
- Marketing copy.
- Risk disclosures.
- Privacy policy.
- Data-provider licenses.
- User data retention/deletion.
- Support and complaint handling.
