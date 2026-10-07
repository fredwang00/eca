---
id: eca:spec/2026-10-04-mag7-capex-evidence
type: spec
status: proposed
repo: earnings-call-analyzer
created: 2026-10-04
updated: 2026-10-04
tags: [capex, mag7, evidence, claims-schema, fiscal-periods]
links:
  - repo: datacenter-modeling
    path: docs/js/presets.js
    anchor: CALIBRATION_TARGETS
    relation: model-calibration-targets-labeled-source-transcript-should-cite-claim-ids
  - repo: datacenter-modeling
    path: docs/js/engine.js
    anchor: capital-module-creditMarketDepth-ecosystemCashFlow-baseRate
    relation: funding-topic-claims-empirically-anchor-capital-rail-assumptions
  - repo: datacenter-modeling
    path: docs/js/engine.js
    anchor: revenuePaybackYears-monetization-lag
    relation: amazon-disclosed-payback-cross-checks-model-payback-and-lag
  - repo: datacenter-modeling
    path: docs/research/ai-deployment-evidence.csv
    relation: sibling-evidence-methodology-precedent-for-claims-schema
---

# Mag 7 CapEx Evidence Vertical Slice

**Date:** October 4, 2026  
**Status:** Proposed for implementation  
**Related backlog:** `docs/agent-friendly-improvements.md`

## Intent

Enable an investor or coding agent to ask how much the Magnificent Seven expect to spend on capital investment in 2026 and 2027, how that investment is funded, and what management has disclosed about payback—then receive an auditable answer grounded in primary-source transcript evidence.

Success means the system can distinguish known values from unknowns, management guidance from third-party estimates, and compatible from incompatible CapEx definitions. It must never manufacture a complete total from partial disclosure or silently mix fiscal periods, cash CapEx, lease-inclusive CapEx, and vendor forecasts.

## Scope

The first milestone covers AAPL, AMZN, GOOG, META, MSFT, NVDA, and TSLA, and three topics:

1. CapEx actuals, quantitative guidance, and directional guidance.
2. Funding sources, including operating cash flow, debt, leases, joint ventures, supplier participation, and disclosed borrowing capacity.
3. Return evidence, including payback periods, monetization lag, useful life, contracted demand, hurdle rates, and qualitative return claims.

It includes repository guidance, transcript provenance, normalized claim storage, deterministic retrieval and aggregation, evidence-first synthesis, and an end-to-end fixture for the motivating 2026/2027 question.

It does not include analyst consensus ingestion, automated web sourcing, general-purpose semantic search, a web UI, portfolio modeling, or a complete accounting reconciliation of every source and use of capital.

## Considered approaches

### Recommended: normalized claims in `facts.json`, indexed in SQLite

Keep source-backed claims with the existing per-quarter canonical artifact and rebuild the SQLite index from those files. This preserves the repository’s local-first, rebuildable architecture while enabling deterministic filters and compatibility checks. Stable evidence IDs let derived answers cite the canonical claim.

### Alternative: transcript search with LLM synthesis

Search transcript text at question time and let an LLM interpret relevant passages. This is faster to prototype but cannot reliably identify superseded guidance, normalize periods and units, or prevent incompatible values from being totaled. It also repeats extraction cost and makes answers less reproducible.

### Alternative: separate global claims database as source of truth

Write extracted claims directly to SQLite. This simplifies querying but creates two mutable sources of truth and makes reviews, diffs, and recovery harder. It conflicts with the existing convention that SQLite is derived from checked-in JSON artifacts.

## Financial semantics

These rules will be summarized in a new root `CLAUDE.md` and enforced by code where practical.

### Sources and authority

- The normalized transcript and its metadata are the primary source for management statements.
- A structured claim is authoritative only for what its cited quotation supports.
- `facts.json` is the canonical structured record; `data/eca.db` is disposable and rebuilt from it.
- Generated analysis, ticker briefs, and sector synthesis are derived artifacts, not primary evidence.
- Provider-written summaries are not management evidence and must not enter the normalized transcript body.

### Claim classes

Every claim has one of these classes:

- `reported_actual`
- `management_guidance`
- `management_directional`
- `vendor_estimate`
- `agent_extrapolation`
- `scenario`

The schema reserves `analyst_consensus`, but this milestone does not ingest it. Primary-source-only queries include management statements and reported actuals; they exclude vendor estimates, extrapolations, scenarios, and analyst consensus.

### Periods

A source document records its fiscal year, fiscal quarter, period start/end when known, calendar document date, and call date. A claim separately records the period it describes. Annual guidance uses normalized labels such as `CY2026` or `FY2027`; the code must not infer calendar-year equivalence from a fiscal-quarter directory name.

Unknown period fields remain null and produce an explicit warning when needed. They are never guessed from lexical quarter ordering.

### Values and units

Amounts use integer millions in the claim currency. Ranges have `value_low_m` and `value_high_m`; point values use equal low/high values. Directional claims have no numeric value. Durations use explicit month fields rather than overloading currency fields.

CapEx actuals may preserve the cash-flow statement sign, but `capex_spend_m` and claim amounts are positive spend magnitudes.

### CapEx definitions

Each quantitative CapEx claim has a definition from a controlled vocabulary:

- `cash_capex`
- `purchases_of_property_and_equipment`
- `capex_including_finance_lease_principal`
- `capex_including_leases`
- `company_defined_capex`
- `non_comparable_or_unspecified`

Definitions can be totaled only when the query’s compatibility policy allows it. The default strict policy totals claims sharing one definition and reports excluded claims. A user may request a broad disclosed subtotal, but the output must list each included definition and label the result non-comparable when definitions differ.

### Freshness and supersession

A claim has an `as_of` date and may identify a `supersedes_id`. For a company, topic, metric, and described period, current-guidance queries choose the latest non-superseded claim available on or before the requested as-of date. Older claims remain queryable history.

### Missing information

“No disclosure found” is distinct from zero. Missing company guidance must remain missing, and aggregates must report company coverage and excluded companies.

## Canonical artifacts and schema

### Transcript artifacts

Each quarter directory will contain:

```text
data/<ticker>/<quarter>/
  transcript.raw.txt
  transcript.txt
  transcript.meta.json
  facts.json
  analysis.md
```

`transcript.raw.txt` preserves the ingested bytes. `transcript.txt` contains normalized primary transcript text. `transcript.meta.json` records:

```json
{
  "source_provider": "example-provider",
  "source_url": "https://example.invalid/call",
  "retrieved_at": "2026-10-04T12:00:00Z",
  "sha256_raw": "hex-digest",
  "sha256_normalized": "hex-digest",
  "document_date": "2026-07-30",
  "call_date": "2026-07-30",
  "fiscal_year": 2026,
  "fiscal_quarter": 2,
  "period_start": "2026-04-01",
  "period_end": "2026-06-30",
  "normalization_warnings": []
}
```

CLI metadata flags will be optional for backward compatibility. Omitted metadata remains null; the command records a warning instead of inventing values. Re-ingestion preserves existing `facts.json` fields.

### Claim records

`facts.json` gains a `claims` array. Each item has:

```json
{
  "id": "GOOG-2026Q2-capex-CY2026-001",
  "topic": "capex",
  "metric": "capital_expenditure",
  "claim_type": "management_guidance",
  "period": "CY2026",
  "value_low_m": 195000,
  "value_high_m": 205000,
  "currency": "USD",
  "unit": "USD_millions",
  "capex_definition": "company_defined_capex",
  "duration_low_months": null,
  "duration_high_months": null,
  "direction": null,
  "speaker": "Anat Ashkenazi",
  "source_document": "q2-2026 earnings call",
  "source_path": "data/goog/q2-2026/transcript.txt",
  "source_section": "prepared_remarks",
  "line_start": 120,
  "line_end": 123,
  "quote": "We are updating our full year 2026 CapEx guidance...",
  "as_of": "2026-07-30",
  "supersedes_id": null,
  "notes": null
}
```

Topics use `capex`, `funding`, or `return`. Metric and definition vocabularies are validated, while quote text and notes preserve source nuance. IDs are stable within a source document and checked for uniqueness during index rebuild.

### SQLite index

The rebuilt database gains a `claims` table with one row per JSON claim and indexes on:

- `(topic, period, ticker)`
- `(metric, claim_type, as_of)`
- `supersedes_id`

The index stores all fields needed for deterministic filtering and citation rendering. It does not own claim data.

## Components

### Repository guide

A root `CLAUDE.md` gives agents the fast path: canonical artifacts, fiscal/calendar distinctions, sign and unit rules, claim classes, compatibility policy, evidence requirements, and safe commands.

### Provenance-aware ingestion

`eca ingest-transcript` will preserve raw input, produce normalized text, hash both forms, and write metadata. The normalizer will remove only recognized provider-summary blocks with explicit markers. Unrecognized preambles remain in the raw file and generate a warning rather than being silently deleted.

Duplicate normalized hashes will be detected across the data tree and surfaced as warnings. A duplicate does not overwrite another quarter automatically.

### Claim validation and indexing

Schema helpers validate required fields, enum values, ranges, quote/source presence, and stable IDs. `eca build-index` fails with a path-specific error for malformed claims or duplicate IDs rather than silently dropping them.

### Deterministic retrieval

`eca find` filters claims by topic or text, tickers/sector, described period, claim class, as-of date, and primary-source status. Human output includes the value, definition, source, and quote; `--json` returns complete records.

### Compatibility-aware aggregation

A pure aggregation function selects current claims as of a date, excludes superseded records, detects overlapping guidance for the same company and period, and computes low/high subtotals only for eligible records. Its result contains:

- Included claims.
- Excluded claims and reasons.
- Low/high subtotal.
- Covered and missing companies.
- Definitions represented.
- A comparability status and warnings.

The function never treats a missing claim as zero.

### Evidence-first `eca ask`

`eca ask` retrieves claims and builds a structured evidence packet before any LLM call. The answer format has four sections:

1. Source-backed facts.
2. Compatible totals or clearly labeled disclosed subtotals.
3. Unknowns and excluded evidence.
4. Interpretation, explicitly separated from facts.

The model receives only the question, the evidence packet, and strict instructions not to introduce outside facts. `--json` returns the evidence packet and deterministic aggregation without invoking an LLM, making the core answer auditable and testable.

## Data flow

1. Ingest a source transcript and provenance metadata.
2. Preserve raw text, normalize recognized non-transcript sections, and hash both forms.
3. Extract or curate citation-backed claims into the quarter’s `facts.json`.
4. Validate claims and rebuild SQLite.
5. Retrieve claims matching the question, company set, period, class, and as-of date.
6. Resolve supersession and compatibility deterministically.
7. Render evidence and aggregate results.
8. Optionally synthesize narrative from that bounded evidence packet.

The first Mag 7 claim set may be curated from existing transcripts. Automated generalized claim extraction is outside this milestone; the schema and validator are designed so extraction can be added later without changing query semantics.

## Error handling and trust boundaries

- Invalid enums, negative spend magnitudes, inverted ranges, absent quotations, nonexistent source paths, and duplicate evidence IDs fail validation with the exact artifact path.
- Unknown dates, periods, definitions, and providers are represented as null/unspecified plus warnings, not guessed.
- A missing transcript prevents a claim from being indexed.
- A quoted line range outside the source file fails validation.
- Conflicting current guidance for one company and period excludes that company from totals until one claim supersedes the other.
- Currency mismatches prevent aggregation.
- Mixed CapEx definitions are excluded under strict aggregation and prominently labeled under broad aggregation.
- LLM failure does not destroy the deterministic evidence result; the CLI reports the evidence packet and synthesis error separately.

## Testing strategy

### Unit tests

- Period and claim enum validation.
- Numeric range and positive-spend validation.
- Stable evidence ID uniqueness.
- Supersession as of historical dates.
- Strict and broad compatibility policies.
- Currency mismatch behavior.
- Missing-company coverage.
- Transcript hashing and recognized-summary removal.
- Duplicate transcript detection.
- Citation line-range validation.

### CLI tests

- `ingest-transcript` remains backward compatible and writes raw, normalized, and metadata artifacts.
- `find` filters by ticker, period, class, and as-of date and emits valid JSON.
- `ask --json` performs no LLM call and separates included, excluded, and missing companies.
- Malformed claims cause `build-index` to fail with an actionable path.

### End-to-end acceptance fixture

A compact seven-company fixture models the motivating question. It must prove that:

- 2026 point and range guidance produces a range subtotal with explicit company coverage.
- Apple and NVIDIA remain unknown when no comparable guidance exists.
- A 2027 vendor estimate is displayed but excluded from a primary-source management-guidance total.
- Debt, leases, joint-venture funding, cash flow, and borrowing capacity are rendered as distinct evidence, not forced into unsupported percentages.
- Amazon’s disclosed payback and useful-life claims appear with quotations.
- Qualitative return narratives from other companies are not converted into numeric payback periods.
- Incompatible CapEx definitions produce a warning and cannot silently form a strict total.

## Delivery slices

1. Repository semantics and typed claim model.
2. Provenance-aware transcript ingestion.
3. Claim validation and SQLite indexing.
4. Deterministic find, supersession, and aggregation.
5. Evidence-first ask output.
6. Curated Mag 7 evidence and end-to-end acceptance tests.

Each slice is independently testable and retains the current local-first, rebuildable data model.
