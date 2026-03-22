---
date: 2026-03-22
title: Sector Synthesis — Cross-Company Signal Extraction
status: approved
---

# Sector Synthesis Design

Adds a `synthesize` command to ECA that produces sector-level briefings by analyzing transcript evidence across all companies in a sector. Uses a map-reduce architecture: per-ticker briefs (Stage 1) feed into a sector synthesis (Stage 2) that extracts cross-company signals. A SQLite index provides fast aggregation of financial metrics across tickers and quarters.

## Problem

ECA analyzes transcripts one at a time. After grading 10 IREN quarters and 2 CIFR quarters, there's no way to see the cross-company picture — whether the AI infrastructure sector's candor is improving, whether disclosed capex adds up to the "$600B" pundits claim, or whether all companies are using the same vague demand language. The synthesis should derive macro-level insights bottom-up from primary sources rather than relying on pundit conclusions.

## Command Interface

```bash
eca synthesize --sector "Digital Infrastructure & Power"
eca synthesize --sector all
eca synthesize --list-sectors
eca build-index          # rebuild SQLite from facts.json files
```

## Sector Groupings

New `WATCHLIST_SECTORS` mapping in config.py, mirroring the macro watchlist categories:

```python
WATCHLIST_SECTORS = {
    "AI Infrastructure": ["NVDA", "MSFT", "GOOG", "META", "AMZN", "AAPL", "TSLA", "PLTR"],
    "Digital Infrastructure & Power": ["IREN", "CIFR", "HUT", "WULF", "NBIS", "CRWV"],
    "Crypto & Digital Assets": ["MSTR", "BMNR", "COIN", "CRCL"],
    "Space Economy": ["RKLB", "ASTS"],
    "Consumer & Real Economy": ["OPEN", "UBER", "ABNB", "SHOP", "LMND", "ROOT"],
    "High Variance / Venture": ["EOSE"],
    "Employer & Correlated": ["SPOT", "HIMS"],
}
```

**Relationship to `SECTOR_MAP`:** These serve different purposes. `SECTOR_MAP` controls which analysis skill prompt is used (e.g., `"ROOT": "insurtech"` adds insurance-specific grading criteria). `WATCHLIST_SECTORS` groups tickers for cross-company synthesis by investment thesis. A ticker can be in both — ROOT uses the insurtech skill for analysis but belongs to "Consumer & Real Economy" for synthesis. `--list-sectors` prints sector names with their ticker lists.

## Data Flow

```
facts.json + analysis.md (per ticker, all quarters)
    │
    ├──► build-index ──► SQLite (derived, aggregation queries)
    │
    ▼
Stage 1: ticker_brief() — one LLM call per ticker
    → reads all analysis.md + facts.json for the ticker
    → produces data/{ticker}/brief.md
    │
    ▼
Stage 2: sector_synthesis() — one LLM call per sector
    → reads all ticker briefs for the sector
    → reads aggregated metrics from SQLite
    → produces data/synthesis/{sector-slug}-{date}.md
```

## SQLite Index

Derived database rebuilt from facts.json files. JSON remains source of truth (human-readable, git-tracked). SQLite is a computed index for fast aggregation.

**Location:** `data/eca.db` (gitignored)

**Tables:**

```sql
CREATE TABLE IF NOT EXISTS quarter_facts (
    ticker TEXT NOT NULL,
    quarter TEXT NOT NULL,
    company TEXT,
    call_date TEXT,
    -- candor grades
    dim1_grade TEXT,
    dim2_grade TEXT,
    dim3_grade TEXT,
    dim4_grade TEXT,
    dim5_grade TEXT,
    composite_grade TEXT,
    composite_score REAL,
    skill_version TEXT,
    analyzed_at TEXT,
    -- financial metrics (mirrors all QuarterMetrics fields from schema.py)
    revenue_m REAL,
    gross_profit_m REAL,
    operating_income_m REAL,
    net_income_m REAL,
    eps REAL,
    free_cash_flow_m REAL,
    operating_cash_flow_m REAL,
    capital_expenditure_m REAL,
    cash_and_equivalents_m REAL,
    total_assets_m REAL,
    total_equity_m REAL,
    shares_outstanding_m REAL,
    bvps REAL,
    roe_pct REAL,
    -- insurtech-specific (nullable for non-insurance tickers)
    combined_ratio_pct REAL,
    loss_ratio_pct REAL,
    expense_ratio_pct REAL,
    PRIMARY KEY (ticker, quarter)
);

-- Normalized flags table for per-flag aggregation queries
CREATE TABLE IF NOT EXISTS quarter_flags (
    ticker TEXT NOT NULL,
    quarter TEXT NOT NULL,
    flag TEXT NOT NULL,
    PRIMARY KEY (ticker, quarter, flag),
    FOREIGN KEY (ticker, quarter) REFERENCES quarter_facts(ticker, quarter)
);

CREATE TABLE IF NOT EXISTS sector_map (
    ticker TEXT NOT NULL,
    sector TEXT NOT NULL,
    PRIMARY KEY (ticker, sector)
);
```

**Rebuild semantics:** `eca build-index` does a full rebuild — DELETE all rows, re-walk `data/*/*/facts.json`, re-insert. This is simpler than upsert and handles removed tickers/quarters cleanly. The database is small enough that a full rebuild takes milliseconds. Quarters with no `candor` or `metrics` sections are still inserted (with NULLs for missing fields) so they appear in coverage queries.

**Aggregation queries used by synthesis:**

```sql
-- Sector capex/revenue totals for trailing N quarters
SELECT ticker,
       SUM(revenue_m) as total_revenue,
       SUM(capital_expenditure_m) as total_capex,
       SUM(free_cash_flow_m) as total_fcf
FROM quarter_facts
WHERE ticker IN (?, ?, ...) AND quarter >= ?
GROUP BY ticker;

-- Grade trajectory per ticker
SELECT ticker, quarter, composite_score, composite_grade
FROM quarter_facts
WHERE ticker IN (?, ?, ...)
ORDER BY ticker, quarter;

-- Sector-wide flag frequency
SELECT flag, COUNT(*) as cnt
FROM quarter_flags
WHERE ticker IN (?, ?, ...)
GROUP BY flag
ORDER BY cnt DESC;
```

## Stage 1: Ticker Brief

One LLM call per ticker. Input: all analysis.md files and facts.json data for that ticker, chronologically ordered. Output: `data/{ticker}/brief.md` (~500-800 words).

**System prompt instructs extraction of:**

1. **Candor trajectory** — grade progression with named inflection points
2. **Key commitments** — signed contracts (counterparty, value, terms) vs. aspirational claims
3. **Capital figures** — disclosed capex, revenue, financing, cash positions with quarter attribution
4. **FOG patterns** — recurring vague language and any evolution in precision
5. **Flags** — from facts.json (equity declining, missing metrics, etc.)
6. **Communication risks** — most important red flags across all analyses
7. **What to verify next quarter** — carried forward from most recent analysis

Financial metrics from facts.json are injected as structured context alongside the analyses. The model synthesizes narrative; numbers come from structured data.

The brief is a derived artifact — overwritten each run, not committed to git.

## Stage 2: Sector Synthesis

One LLM call per sector. Input: all ticker briefs + aggregated metrics table from SQLite. Output: `data/synthesis/{sector-slug}-{date}.md`.

**Seven signals extracted:**

1. **Candor trajectory** — sector-level pattern. How many companies improved, stagnated, or declined in candor scores? Where are the outliers?

2. **Signed vs. aspirational ratio** — aggregate named contracts with dollar values vs. unsubstantiated demand claims across the sector. Dollar totals for each.

3. **Bottleneck migration** — which constraint is the sector discussing now vs. prior quarters? Power, chips, labor, permitting, memory? Track how the language shifts over time.

4. **Cross-company corroboration** — when multiple companies independently confirm the same signal (hyperscaler demand, power scarcity), surface it. When a claim is one-sided (only the seller mentions the buyer), flag it.

5. **Sector FOG index** — are companies converging on the same vague language? Uniformity of FOG across competitors is a red flag.

6. **Aggregated flags and risks** — roll up per-company flags and communication risks into a sector view.

7. **Capital deployment aggregation** — sum disclosed capex, contract values, and financing across all tickers. Present as a table with per-company breakdown and sector total. Compare to prior period if data exists.

## Output Format

Timestamped markdown files in `data/synthesis/`:

```
data/synthesis/
    digital-infrastructure-power-2026-03-22.md
    ai-infrastructure-2026-03-22.md
    ...
```

Accumulates over time so you can diff across earnings seasons.

## File Changes

| File | Change |
|------|--------|
| `src/eca/llm.py` | New module — extract `run_analysis()` from analyze.py as shared LLM caller |
| `src/eca/config.py` | Add `WATCHLIST_SECTORS` mapping |
| `src/eca/db.py` | New module — SQLite schema, connection, rebuild, aggregation queries |
| `src/eca/processors/analyze.py` | Import `run_analysis` from `llm.py` instead of defining locally |
| `src/eca/processors/synthesize.py` | New module — `ticker_brief()`, `sector_synthesis()`, prompt construction |
| `src/eca/cli.py` | Add `synthesize` and `build-index` commands |
| `skills/synthesis-brief.md` | System prompt for Stage 1 (ticker brief) |
| `skills/synthesis-sector.md` | System prompt for Stage 2 (sector synthesis) |
| `.gitignore` | Add `data/eca.db` |
| `tests/test_db.py` | Index build, aggregation queries |
| `tests/test_synthesize.py` | Prompt construction, end-to-end with mock LLM |

## Implementation Notes

**LLM caller extraction:** The existing `run_analysis()` in `processors/analyze.py` handles Hendrix/Anthropic routing but lives inside a specific processor. Extract it to `src/eca/llm.py` as a shared module so both `analyze` and `synthesize` can use it without cross-processor imports. The processors should remain independent.

**Model:** Both stages use the same `--model` flag as `analyze` (defaults to `claude-sonnet-4-6`). Stage 2 input for the largest sector (AI Infrastructure, 8 tickers × ~700 words) is ~6K words of briefs plus a metrics table — well within context limits for any Claude model.

**Concurrency:** `--sector all` processes sectors sequentially. Parallelism is a future optimization, not needed for v1 with 7 sectors.

**No new dependencies:** SQLite is in Python's standard library (`sqlite3`). No packages to add.

## Dependencies

- Works with whatever data exists. Tickers without analyses are skipped with a note in the output.
- Uses the same LLM routing as `analyze` (Hendrix or direct Anthropic), extracted to a shared `llm.py` module.
- `brief.md` files are ephemeral/derived — regenerated on each run, not committed.
- SQLite database is derived — rebuilt from JSON, gitignored.

## Future Roadmap (not in scope)

- **Financial Datasets API** (`financialdatasets.ai`) — institutional-grade income statements, balance sheets, cash flow, analyst estimates, revenue segments. Richer than yfinance. Dexter (`/Users/fwang/code/dexter`) has a working integration pattern. Natural replacement for `ingest-metrics` or a new `ingest-financials` processor.
- **EDGAR 10-K/10-Q ingestion** — SEC filing section extraction, especially Risk Factors for cross-quarter diffing. Dexter's SEC tool has a pattern for this.
- **Finviz screening** — alternative/supplementary financial data source.
- **Macro briefing** — composes sector briefings into a single economy-level synthesis.
- **Regime signal layer** — earnings signals feed into trading regime framework.
- **Thesis tracker** — formalize hypotheses (e.g., "bottleneck migrates from power to chips by mid-2026") and track validation against quarterly data.
- **Automatic scheduling** — trigger synthesis after earnings season.
