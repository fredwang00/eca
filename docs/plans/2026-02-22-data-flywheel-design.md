# Data Flywheel Design

A CLI tool (`eca`) that turns the earnings call analyzer from a single-skill markdown workflow into an atomic, multi-source data pipeline. Each processor is an independent command that reads/writes JSON fact files. The flywheel effect: each processor enriches shared context that makes subsequent processors more powerful.

## Architecture

### Approach: Shared schema, independent processors

Every company-quarter gets a directory with a `facts.json` file that accumulates structured data from all processors. Each processor owns its own top-level key in facts.json and only writes to that key. Processors discover each other's output by reading the shared file.

No database, no coordination layer, no shared runtime. The JSON fact file is the only coupling point.

### Upgrade path

If the dataset grows past ~50 company-quarters, add an `eca index` command that builds a SQLite database from the fact files. The JSON remains the source of truth; SQLite is a read-only query cache.

## CLI Commands (Phase 1)

### `eca ingest-metrics`

Fetches quarterly financial data from Yahoo Finance via yfinance.

```bash
eca ingest-metrics root
eca ingest-metrics lmnd
```

Input: ticker symbol (fetches directly from Yahoo Finance API -- no manual data entry).

Output:
- `data/{ticker}/metrics-raw.json` -- full quarterly time series for the ticker
- Updates `facts.json` in each existing quarter directory with current-quarter metrics snapshot

Behavior:
- Fetches quarterly income statement, balance sheet, and cash flow from yfinance
- Normalizes field names to schema (Total Revenue -> revenue_m, Common Stock Equity -> total_equity_m, etc.)
- Handles insurance companies that lack standard Gross Profit by computing Revenue - Loss Adjustment Expense
- Computes derived metrics where possible (bvps = total_equity / shares_outstanding)
- Appends flags like `equity_declining_yoy` when total equity is lower than the prior year's same quarter
- Insurance-specific metrics (combined_ratio, loss_ratio, expense_ratio, roe) stay null if the source doesn't provide them -- future processors fill the gaps

### `eca ingest-transcript`

Registers a transcript and initializes the quarter.

```bash
eca ingest-transcript root q3-2025 ~/Downloads/q3-2025-root-cc.txt
```

Output:
- `data/{ticker}/{quarter}/transcript.txt` -- copy of the raw transcript
- Creates or updates `facts.json` with company/quarter metadata (call_date is populated later by the analyze processor)

### `eca analyze`

Runs the Rittenhouse candor analysis via Anthropic API.

```bash
eca analyze root q3-2025
eca analyze root --all        # analyze all quarters missing an analysis
```

Behavior:
1. Reads transcript.txt and facts.json for the quarter
2. Selects skills: base skill + sector supplement (e.g., insurtech for ROOT/LMND). Mapping is in config.
3. Constructs prompt, injecting financial metrics from facts.json as ground truth if available. Example injection: "Financial ground truth: Revenue $387.8M, FCF $53.7M, Operating Cash Flow $57.6M. GAAP operating income is $0.3M vs reported adjusted EBITDA of $34M. Use these to verify management's claims."
4. Calls Claude API (anthropic Python SDK) with the skill prompt + transcript + metrics context
5. Writes analysis.md
6. Parses grades from the output, updates facts.json candor section
7. Extracts flags and tracking items, appends to facts.json

Sector supplement selection: a dict mapping tickers to supplement files. ROOT -> insurtech, LMND -> insurtech, SPOT -> base, etc.

### `eca query`

Queries across the data tree. Read-only, produces stdout.

```bash
eca query "compare ROOT and LMND dim1 grades across all quarters"
eca query "which quarters have bvps_absent flag"
eca query "show ROOT total equity trend"
```

Behavior:
- Reads all facts.json files across the data tree
- Structured queries (flag filters, grade comparisons) resolved directly from JSON
- Natural language queries: aggregates facts as context and calls Claude to answer
- Time series queries: reads metrics-raw.json files

## Data Schema

### Directory layout

```
data/
  {ticker}/
    metrics-raw.json                # full time series from yfinance
    {quarter}/                      # e.g. q3-2025
      facts.json                    # accumulated structured data
      transcript.txt                # raw transcript
      analysis.md                   # rendered candor analysis
```

### facts.json

```json
{
  "company": "Root, Inc.",
  "ticker": "ROOT",
  "quarter": "Q3 2025",
  "call_date": "2025-11-04",

  "metrics": {
    "source": "yfinance",
    "ingested_at": "2025-02-22",
    "revenue_m": 387.8,
    "gross_profit_m": 81.4,
    "operating_income_m": 0.3,
    "net_income_m": -5.4,
    "free_cash_flow_m": 53.7,
    "operating_cash_flow_m": 57.6,
    "cash_and_equivalents_m": 654.4,
    "total_equity_m": 265.0,
    "shares_outstanding_m": 15.53,
    "bvps": 17.06,
    "roe_pct": null,
    "combined_ratio_pct": null,
    "loss_ratio_pct": null,
    "expense_ratio_pct": null
  },

  "candor": {
    "analyzed_at": "2025-02-22",
    "skill_version": "base+insurtech",
    "dim1_grade": "C",
    "dim2_grade": "C+",
    "dim3_grade": "C-",
    "dim4_grade": "C",
    "dim5_grade": "C",
    "composite_score": 2.03,
    "composite_grade": "C"
  },

  "flags": [
    "bvps_absent",
    "roe_absent",
    "combined_ratio_absent",
    "adj_ebitda_gaap_gap_large"
  ],

  "tracking": [
    "Monitor BVPS trajectory",
    "Track whether adjusted EBITDA construction is disclosed"
  ]
}
```

Null means "not available from this source." A future processor can fill nulls without touching other fields.

Flags are a flat list of descriptive strings. Both metrics and candor processors can append flags.

Insurance-specific metrics are in the base schema with nulls. Non-insurance companies leave them null. No separate schema per sector.

### metrics-raw.json

Full quarterly time series per ticker. Lives at `data/{ticker}/metrics-raw.json` (not per-quarter).

```json
{
  "source": "yfinance",
  "ticker": "ROOT",
  "fetched_at": "2025-02-22",
  "quarters": {
    "Q3 2024": {"revenue_m": 387.8, "gross_profit_m": 81.4, "...": "..."},
    "Q4 2024": {"revenue_m": 405.0, "gross_profit_m": 110.0, "...": "..."},
    "Q1 2025": {"revenue_m": 420.0, "gross_profit_m": 115.0, "...": "..."}
  }
}
```

> yfinance returns approximately 5 quarters of history. For deeper historical data, a future processor could integrate a different data source.

## Project Structure

```
earnings-call-analyzer/
  pyproject.toml
  src/
    eca/
      __init__.py
      cli.py                  # click entry point
      processors/
        __init__.py
        ingest_metrics.py
        ingest_transcript.py
        analyze.py
        query.py
        migrate.py
      parsers/
        __init__.py
        yfinance_fetcher.py   # Yahoo Finance data fetcher
      schema.py               # facts.json schema (dataclass/TypedDict)
      config.py               # ticker->sector mapping, API config
  skills/
    base.md                   # moved from SKILL.md
    insurtech.md              # moved from SKILL-insurtech.md
  data/                       # replaces analyses/ + transcripts/
    root/
      metrics-raw.json
      q4-2024/
        facts.json
        transcript.txt
        analysis.md
      q3-2025/
        ...
    lmnd/
      ...
  tests/
    test_yfinance_fetcher.py
    test_schema.py
  docs/
    plans/
```

## Migration

One-time script to restructure existing files:
- `transcripts/{ticker}/2025/q3.txt` -> `data/{ticker}/q3-2025/transcript.txt`
- `analyses/{ticker}/2025/q3.md` -> `data/{ticker}/q3-2025/analysis.md`
- Generate initial facts.json for each existing analysis by parsing grades from the markdown
- Move SKILL.md -> skills/base.md, SKILL-insurtech.md -> skills/insurtech.md

## What This Design Does Not Include

- No database (SQLite is a future upgrade, not phase 1)
- No web UI or dashboard
- No scheduled or automated scraping (manual invocation only)
- No multi-user concerns
- No `eca reconcile` (cross-checking call claims vs filing numbers -- future processor)
- No external commentary ingestion (future processor)
- No 10-Q/10-K filing parsing (future processor)
- No investor presentation analysis (future processor)

## The Flywheel

The value compounds as more processors run:

1. `ingest-metrics` alone: you have structured financial data you can query
2. `ingest-transcript` alone: you have organized transcripts
3. `analyze` alone: same as today's skill, but with structured output
4. `ingest-metrics` + `analyze`: the candor analysis gets financial ground truth injected -- it can flag when management's claims diverge from actual numbers
5. Future: `ingest-filing` + `analyze`: the analysis gets risk factors and reserve tables as context
6. Future: `ingest-commentary` + `analyze`: external critiques inform what to scrutinize
7. Future: `reconcile` reads everything and produces a cross-source consistency report

Each processor is atomic and useful on its own. Together they create a dataset that is greater than the sum of its parts.
