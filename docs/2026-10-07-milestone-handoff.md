---
id: eca:note/2026-10-07-milestone-handoff
type: note
status: active
repo: earnings-call-analyzer
created: 2026-10-07
tags: [session-handoff, milestone-kickoff]
links:
  - repo: earnings-call-analyzer
    path: docs/specs/2026-10-04-mag7-capex-evidence-design.md
    relation: approved-spec-to-implement
  - repo: earnings-call-analyzer
    path: docs/agent-friendly-improvements.md
    relation: full-backlog-context
---

# Milestone handoff — Mag 7 CapEx evidence slice

Context for a fresh session starting the implementation. The design was
reviewed and approved by the owner on 2026-10-04/06. Do not re-derive it.

## What to do

Implement the six delivery slices from
`docs/specs/2026-10-04-mag7-capex-evidence-design.md`, in order:

1. Repository semantics + typed claim model (root `CLAUDE.md` first).
2. Provenance-aware transcript ingestion (raw + normalized + meta + hashes).
3. Claim validation and SQLite indexing (`facts.json` remains canonical;
   `data/eca.db` is disposable and rebuilt).
4. Deterministic `find`, supersession, and compatibility-aware aggregation.
5. Evidence-first `ask` (evidence packet before any LLM call; `--json`
   performs no LLM call).
6. Curated Mag 7 evidence fixture + end-to-end acceptance tests for the
   motivating question (2026/2027 totals, funding, payback).

## Working agreements from the originating session

- TDD: tests first or with each slice; the suite must stay green
  (`python -m pytest`); no TODO/TBD placeholders in shipped code.
- The spec is the source of truth for schema, enums, and semantics
  (claim classes, period normalization, CapEx definitions, strict vs
  broad aggregation). If code and spec disagree, fix one deliberately.
- Fail loudly with artifact paths on malformed claims; never silently
  drop or guess.
- Check `git status` before starting: the working tree has historically
  carried untracked `transcripts/` and `memory/` content outside the
  canonical `data/` pipeline — leave it alone, don't sweep it into
  commits.

## Cross-repo seams already in place (do not redo)

- `datacenter-modeling` main now carries `sourceClaimId: null` slots on
  its transcript-sourced calibration targets
  (`docs/js/presets.js`, commit 56620e1) — the future claims index can
  fill them; nothing to build here beyond stable claim IDs.
- `cashflow` (the pattern donor) has validated conventions worth
  copying: JSON output flags on read-only CLI commands, docs whose SQL
  is tested against the schema, and a `possible_dupes`-style advisory
  review layer. Its `CLAUDE.md` is the model for this repo's slice 1.

## Definition of done for the milestone

The end-to-end fixture proves: 2026 subtotals with explicit company
coverage and definition labels; Apple/NVIDIA stay unknown where no
comparable guidance exists; the 2027 vendor estimate is displayed but
excluded from management-guidance totals; funding evidence renders as
distinct sources (debt, leases, JV, cash flow, borrowing capacity)
without forced percentages; Amazon's payback claims appear with quotes;
incompatible CapEx definitions cannot silently form a strict total.
