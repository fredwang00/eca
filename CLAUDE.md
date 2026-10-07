# CLAUDE.md — Earnings Call Analyzer repository guide

Fast path for coding agents working in this repo. The design spec for the
claims pipeline is `docs/specs/2026-10-04-mag7-capex-evidence-design.md`; when
code and spec disagree, fix one deliberately.

## Canonical artifacts (source of truth)

```
data/<ticker>/<quarter>/
  transcript.raw.txt      # ingested bytes, never edited
  transcript.txt         # normalized primary transcript text
  transcript.meta.json   # provenance: provider, URL, retrieval date, hashes, fiscal metadata
  facts.json             # CANONICAL structured record (metrics + claims)
  analysis.md            # derived LLM candor analysis (not primary evidence)
data/eca.db              # disposable SQLite index, rebuilt from facts.json
```

- `facts.json` is canonical. `eca.db` is derived: never hand-edit it, rebuild
  it with `eca build-index`.
- The normalized transcript and its metadata are the primary source for
  management statements. A structured claim is authoritative only for what its
  cited quotation supports.
- Provider-written summaries are not management evidence and must not enter
  the normalized transcript body. `transcript.raw.txt` keeps them; recognized
  marked blocks are removed during normalization, unrecognized ones stay and
  raise a warning.
- Generated analysis, ticker briefs, and sector synthesis are derived
  artifacts, never primary evidence.

## Fiscal vs calendar periods

- Quarter directories use the company's **fiscal** quarter label
  (e.g. `msft/q4-2026` is Microsoft FY2026 Q4, which covers Apr–Jun 2026).
  Never infer calendar-year equivalence from a directory name.
- Claims carry their own normalized period label: `CY2026`, `FY2027`,
  `CY2026Q2`, `FY2027Q2`. `CY` and `FY` labels are never interchanged by code;
  a query for `CY2026` does not match `FY2026`.
- Transcript metadata records fiscal year/quarter, period start/end, document
  date, and call date when known. Unknown fields stay `null` and produce
  warnings — they are never guessed from lexical ordering.

## Signs, units, and values

- Claim amounts are **positive spend magnitudes in integer millions** of the
  claim currency (`value_low_m`/`value_high_m`; point values use equal
  low/high). Cash-flow-statement signs live only in `metrics`:
  `capital_expenditure_m` may be negative (as reported), `capex_spend_m` is
  the positive magnitude.
- Open-ended guidance ("more than $25 billion") keeps `value_high_m: null`;
  it is displayed as evidence but excluded from subtotals rather than given
  an invented ceiling.
- Durations (payback, useful life, monetization lag) use explicit
  `duration_*_months` fields. Currency fields are never overloaded.
- "No disclosure found" is distinct from zero. Missing company guidance stays
  missing; aggregates report covered and missing companies.

## Claim classes and authority

`claim_type` is one of: `reported_actual`, `management_guidance`,
`management_directional`, `vendor_estimate`, `agent_extrapolation`,
`scenario`. `analyst_consensus` is reserved in the schema but not ingested.

- **Primary-source** evidence = management statements + reported actuals
  (`reported_actual`, `management_guidance`, `management_directional`).
- Vendor estimates, extrapolations, and scenarios may be displayed as
  clearly-labeled evidence but never enter primary-source totals.
- Directional claims carry no numeric values or durations.
- Claims have stable IDs (`<TICKER>-<FY><Q>-<topic>-<period>-<seq>`), a
  verbatim quote, and a source path + line range that must validate.

## CapEx definitions and aggregation

Every quantitative CapEx claim carries a `capex_definition` from:
`cash_capex`, `purchases_of_property_and_equipment`,
`capex_including_finance_lease_principal`, `capex_including_leases`,
`company_defined_capex`, `non_comparable_or_unspecified`.

- **Strict policy (default):** only claims sharing one definition are totaled;
  mixed definitions produce per-definition subtotals plus a warning — never a
  silent combined total.
- **Broad policy:** a disclosed subtotal across definitions is allowed but
  must list every included definition and be labeled non-comparable.
- Supersession: a claim may declare `supersedes_id`. As of a date, current
  guidance is the latest non-superseded claim on or before that date;
  same-date unresolved duplicates are a conflict that excludes the company
  from totals.
- Currency mismatches prevent aggregation. Open-ended ranges and directional
  claims are excluded from subtotals with reasons.
- Amazon payback / useful-life style return claims stay qualitative or
  month-denominated; never convert narratives into numbers.

## Evidence-first answers

`eca find` retrieves claims deterministically (topic, text, tickers, sector,
period, claim class, as-of date, primary-source status). `eca ask` builds the
evidence packet before any LLM call; `--json` performs no LLM call and returns
the packet plus aggregation. LLM output is interpretation only, clearly
separated from facts, and receives nothing beyond the question and the packet.

## Safe commands

```bash
python -m pytest                 # keep the suite green
eca build-index                  # rebuild data/eca.db from facts.json
eca find capex --period CY2026 --claim-type management_guidance --json
eca ask "..." --tickers AAPL,AMZN,GOOG,META,MSFT,NVDA,TSLA --period CY2026 --json
```

Fail loudly: malformed claims abort `build-index` with the exact artifact
path. Never silently drop or guess. The working tree may carry untracked
`transcripts/` and `memory/` content outside the canonical `data/` pipeline —
leave it alone and don't sweep it into commits.
