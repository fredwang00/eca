---
id: eca:roadmap/2026-10-04-agent-friendly-improvements
type: roadmap
status: backlog
repo: earnings-call-analyzer
created: 2026-10-04
updated: 2026-10-04
tags: [agent-usability, claims-schema, cli, capex]
links:
  - repo: earnings-call-analyzer
    path: docs/specs/2026-10-04-mag7-capex-evidence-design.md
    relation: first-milestone-extracted-from-this-backlog
  - repo: cashflow
    path: docs/adhoc-queries.md
    relation: proven-pattern-for-agent-query-docs-and-json-output
  - repo: datacenter-modeling
    path: docs/research/ai-deployment-evidence.csv
    relation: existing-evidence-tracker-precedent-for-claims-methodology
---

# Agent-Friendly Improvement Suggestions

This document preserves the improvement ideas identified during the October 4, 2026 review of the repository. The immediate implementation milestone is documented separately; this list remains the broader backlog so later work does not lose context.

## 1. Add a `CLAUDE.md` fast path

Create a short repository guide that states the financial semantics and source-of-truth rules an agent must follow:

- Whether quarters mean fiscal or calendar quarters.
- CapEx sign conventions.
- Cash CapEx versus PP&E purchases versus CapEx including finance leases.
- Whether guidance, analyst estimates, and vendor forecasts may be aggregated.
- Currency and unit handling.
- Which artifacts are authoritative.
- How to distinguish company guidance from extrapolation.
- Required citation and freshness rules.

## 2. Make investment claims structured data

Replace prose-only investment signals such as `"capex_direction": "accelerating"` with normalized, citation-backed claim records. A claim should capture the topic, metric, period, value or range, currency, definition, claim type, company, speaker, source document, source location, exact quotation, as-of date, and any claim it supersedes.

Initial topics should include:

- CapEx guidance and actuals.
- Funding sources and debt capacity.
- Debt issuance.
- Finance and operating leases.
- Customer commitments and prepayments.
- Payback periods and monetization lags.
- Asset useful lives.
- ROIC or hurdle rates.
- Free-cash-flow guidance.
- Capacity constraints.

## 3. Add a dedicated `eca find` and evidence-first `eca ask`

The current natural-language fallback sends all `facts.json` objects to an LLM, but those facts omit much of the evidence needed for capital-allocation questions. Add deterministic retrieval before synthesis, for example:

```bash
eca find capex \
  --tickers AAPL,AMZN,GOOG,META,MSFT,NVDA,TSLA \
  --period CY2026 \
  --claim-type management_guidance \
  --json

eca find "payback period" --sector ai --since 2024 --with-quotes

eca ask "How will Mag 7 fund 2026–2027 CapEx?" \
  --primary-sources-only \
  --as-of 2026-09-07
```

`eca ask` should retrieve and display evidence records before generating narrative synthesis.

## 4. Separate actuals, guidance, estimates, and extrapolation

Every quantitative claim should have an explicit classification:

- `reported_actual`
- `management_guidance`
- `management_directional`
- `analyst_consensus`
- `vendor_estimate`
- `agent_extrapolation`
- `scenario`

Any aggregate must disclose exactly which classes it includes. In particular, a vendor forecast such as a top-five-hyperscaler estimate must not be presented as bottom-up company guidance.

## 5. Fix period semantics before doing more aggregation

The current metrics ingestion derives quarter labels from calendar months while transcript directories use company fiscal-quarter labels. Add explicit fields for:

- Fiscal year and quarter.
- Period start and end.
- Calendar year.
- Document date.
- Guidance period and guidance period type.

Queries should compare normalized dates and periods rather than lexically comparing labels such as `q2-2026`.

## 6. Normalize CapEx signs and definitions

Store both the cash-flow statement sign and the positive spend magnitude, for example:

- `capex_cash_flow_m = -44924`
- `capex_spend_m = 44924`

Also preserve the CapEx definition. Cash CapEx, PP&E purchases, CapEx including finance-lease principal, and supplier-funded investment are not automatically comparable and must not be summed blindly.

## 7. Add a capital-funding model

Support a source-and-use analysis with structured fields for:

- Operating cash flow.
- Cash and marketable securities.
- Debt issued and repaid.
- Net debt.
- Finance-lease additions.
- Operating-lease commitments.
- Supplier financing.
- Project or joint-venture capital.
- Equity issuance.
- Buybacks and dividends.
- CapEx spend.
- Contracted customer prepayments when disclosed.

This should answer financing questions directly instead of inferring funding from whether quarterly free cash flow is positive or negative.

## 8. Preserve citations through every derived artifact

Assign each source-backed claim a stable evidence ID. Ticker briefs, sector reports, and conversational answers should cite those IDs so an agent can distinguish transcript evidence from generated analysis, ticker-level synthesis, and model inference.

## 9. Validate and clean transcript inputs

`eca ingest-transcript` should:

- Record source URL or provider and retrieval date.
- Preserve the raw source separately.
- Remove or quarantine provider-generated summaries from normalized transcript text.
- Detect speaker boundaries and prepared-remarks/Q&A sections.
- Hash inputs.
- Flag duplicate or suspiciously similar transcripts.
- Reject dates or company names inconsistent with the requested period.

This prevents generated provider summaries from being treated as management statements and catches duplicate or mislabeled calls.

## 10. Add `eca audit` / `eca doctor`

Add repository and data-quality checks such as:

```bash
eca doctor
eca coverage --sector mag7
eca audit-claims --topic capex
```

Checks should cover missing quarters, uningested transcript files, facts without source documents, duplicate hashes, future or inconsistent dates, missing call dates, currency mismatches, conflicting or superseded guidance, fiscal/calendar mismatches, and aggregates built from incompatible CapEx definitions.

## Recommended milestone order

1. Build the Mag 7 CapEx/funding/payback evidence slice described in `docs/specs/2026-10-04-mag7-capex-evidence-design.md`.
2. Generalize transcript validation and claim extraction beyond the Mag 7.
3. Add capital-funding reconciliation and broader metrics.
4. Add repository-wide audit and coverage commands.
5. Extend evidence-backed querying to other investment themes.
