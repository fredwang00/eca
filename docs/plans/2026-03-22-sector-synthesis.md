# Sector Synthesis Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `eca synthesize` and `eca build-index` commands that produce sector-level briefings from cross-company transcript analysis data.

**Architecture:** Map-reduce pipeline. Stage 1 condenses each ticker's full analysis history into a brief. Stage 2 synthesizes briefs + aggregated metrics into a sector-level report extracting 7 signals. SQLite index (derived from facts.json) provides fast metric aggregation.

**Tech Stack:** Python 3.11+, sqlite3 (stdlib), Click CLI, Anthropic/OpenAI SDK (existing)

**Spec:** `docs/specs/2026-03-22-sector-synthesis-design.md`

---

### Task 1: Extract LLM caller to shared module

Move `run_analysis()` and `DEFAULT_MODEL` from `processors/analyze.py` to a new `src/eca/llm.py` so both `analyze` and `synthesize` can use it without cross-processor imports.

**Files:**
- Create: `src/eca/llm.py`
- Modify: `src/eca/processors/analyze.py`
- Modify: `src/eca/cli.py`
- Modify: `evals/jackson_framework/run_eval.py`
- Test: `tests/test_analyze.py`

- [ ] **Step 1: Create `src/eca/llm.py`**

Move `DEFAULT_MODEL` and `run_analysis()` verbatim from `analyze.py`:

```python
"""Shared LLM caller — routes to Hendrix gateway or direct Anthropic SDK."""

from __future__ import annotations

DEFAULT_MODEL = "claude-sonnet-4-6"


def run_analysis(
    system_prompt: str,
    user_message: str,
    model: str = DEFAULT_MODEL,
) -> str:
    """Call LLM API and return text response.

    Routing:
    - ECA_API_KEY set → Hendrix gateway (OpenAI-compatible)
    - ANTHROPIC_API_KEY set → Direct Anthropic SDK
    """
    import os

    api_key = os.environ.get("ECA_API_KEY")
    base_url = os.environ.get(
        "ECA_BASE_URL",
        "https://hendrix-genai.spotify.net/taskforce/anthropic/v1",
    )

    if api_key:
        from openai import OpenAI

        client = OpenAI(
            api_key=api_key,
            base_url=base_url,
            default_headers={"apikey": api_key},
        )
        response = client.chat.completions.create(
            model=model,
            max_tokens=8192,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
        )
        result = response.choices[0].message.content
    else:
        import anthropic

        client = anthropic.Anthropic()
        message = client.messages.create(
            model=model,
            max_tokens=8192,
            system=system_prompt,
            messages=[{"role": "user", "content": user_message}],
        )
        result = message.content[0].text

    if not result:
        raise RuntimeError(f"Model returned no text content (model={model})")
    return result
```

- [ ] **Step 2: Update `processors/analyze.py`**

Remove `DEFAULT_MODEL` and `run_analysis()` definitions. Replace with import:

```python
from eca.llm import run_analysis, DEFAULT_MODEL
```

Keep `build_system_prompt`, `build_user_message`, `find_prior_analysis`, and `extract_and_update_facts` in place — they are analyze-specific.

- [ ] **Step 3: Update `cli.py` import in `query_cmd`**

Change line 147 from:
```python
from eca.processors.analyze import run_analysis
```
to:
```python
from eca.llm import run_analysis
```

- [ ] **Step 4: Update `evals/jackson_framework/run_eval.py`**

Change the import on line 28 from:
```python
from eca.processors.analyze import (
    build_system_prompt, build_user_message, run_analysis,
    extract_and_update_facts, find_prior_analysis,
)
```
to:
```python
from eca.llm import run_analysis
from eca.processors.analyze import (
    build_system_prompt, build_user_message,
    extract_and_update_facts, find_prior_analysis,
)
```

- [ ] **Step 5: Run all tests**

Run: `pytest tests/ -v`
Expected: All 50 tests pass (no behavior change, just module reorganization).

- [ ] **Step 6: Commit**

```bash
git add src/eca/llm.py src/eca/processors/analyze.py src/eca/cli.py evals/jackson_framework/run_eval.py
git commit -m "refactor: extract run_analysis to shared llm.py module"
```

---

### Task 2: Add WATCHLIST_SECTORS to config

**Files:**
- Modify: `src/eca/config.py`
- Test: `tests/test_config.py`

- [ ] **Step 1: Write the failing test**

```python
from eca.config import WATCHLIST_SECTORS


def test_watchlist_sectors_has_infra():
    assert "infra" in WATCHLIST_SECTORS
    assert "IREN" in WATCHLIST_SECTORS["infra"]
    assert "CIFR" in WATCHLIST_SECTORS["infra"]


def test_watchlist_sectors_all_tickers_in_sector_map():
    from eca.config import SECTOR_MAP
    for sector, tickers in WATCHLIST_SECTORS.items():
        for ticker in tickers:
            assert ticker in SECTOR_MAP, f"{ticker} in WATCHLIST_SECTORS[{sector}] but not in SECTOR_MAP"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_config.py::test_watchlist_sectors_has_infra -v`
Expected: FAIL with ImportError

- [ ] **Step 3: Add `WATCHLIST_SECTORS` to `config.py`**

Add after `COMPANY_NAMES`:

```python
WATCHLIST_SECTORS: dict[str, list[str]] = {
    "ai":       ["NVDA", "MSFT", "GOOG", "META", "AMZN", "AAPL", "TSLA", "PLTR"],
    "infra":    ["IREN", "CIFR", "HUT", "WULF", "NBIS", "CRWV"],
    "crypto":   ["MSTR", "BMNR", "COIN", "CRCL"],
    "space":    ["RKLB", "ASTS"],
    "consumer": ["OPEN", "UBER", "ABNB", "SHOP", "LMND", "ROOT"],
    "venture":  ["EOSE"],
    "employer": ["SPOT", "HIMS"],
}
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_config.py -v`
Expected: All pass

- [ ] **Step 5: Commit**

```bash
git add src/eca/config.py tests/test_config.py
git commit -m "feat: add WATCHLIST_SECTORS mapping for synthesis grouping"
```

---

### Task 3: SQLite index — schema and rebuild

**Files:**
- Create: `src/eca/db.py`
- Test: `tests/test_db.py`

- [ ] **Step 1: Write failing tests for index build**

```python
import json
import sqlite3
from pathlib import Path

from eca.db import rebuild_index, connect_db


def _make_facts(tmp_path, ticker, quarter, candor=None, metrics=None, flags=None):
    """Helper to create a facts.json file in the expected directory structure."""
    d = tmp_path / "data" / ticker.lower() / quarter
    d.mkdir(parents=True)
    facts = {"ticker": ticker, "quarter": quarter.replace("-", " ").upper().replace("Q", "Q")}
    if candor:
        facts["candor"] = candor
    if metrics:
        facts["metrics"] = metrics
    if flags:
        facts["flags"] = flags
    (d / "facts.json").write_text(json.dumps(facts))
    return d


def test_rebuild_creates_tables(tmp_path, monkeypatch):
    monkeypatch.setattr("eca.config.project_root", lambda: tmp_path)
    (tmp_path / "data").mkdir()
    db_path = tmp_path / "data" / "eca.db"
    rebuild_index(db_path)
    conn = sqlite3.connect(db_path)
    tables = [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()]
    conn.close()
    assert "quarter_facts" in tables
    assert "quarter_flags" in tables
    assert "sector_map" in tables


def test_rebuild_inserts_facts(tmp_path, monkeypatch):
    monkeypatch.setattr("eca.config.project_root", lambda: tmp_path)
    _make_facts(tmp_path, "IREN", "q1-2025",
                candor={"composite_score": 2.65, "composite_grade": "B"},
                metrics={"revenue_m": 240.0, "capital_expenditure_m": 100.0})
    db_path = tmp_path / "data" / "eca.db"
    rebuild_index(db_path)
    conn = sqlite3.connect(db_path)
    row = conn.execute(
        "SELECT ticker, composite_score, revenue_m, capital_expenditure_m FROM quarter_facts"
    ).fetchone()
    conn.close()
    assert row == ("IREN", 2.65, 240.0, 100.0)


def test_rebuild_inserts_flags(tmp_path, monkeypatch):
    monkeypatch.setattr("eca.config.project_root", lambda: tmp_path)
    _make_facts(tmp_path, "ROOT", "q3-2025", flags=["equity_declining_yoy", "bvps_absent"])
    db_path = tmp_path / "data" / "eca.db"
    rebuild_index(db_path)
    conn = sqlite3.connect(db_path)
    flags = [r[0] for r in conn.execute(
        "SELECT flag FROM quarter_flags WHERE ticker='ROOT' ORDER BY flag"
    ).fetchall()]
    conn.close()
    assert flags == ["bvps_absent", "equity_declining_yoy"]


def test_rebuild_populates_sector_map(tmp_path, monkeypatch):
    monkeypatch.setattr("eca.config.project_root", lambda: tmp_path)
    (tmp_path / "data").mkdir()
    db_path = tmp_path / "data" / "eca.db"
    rebuild_index(db_path)
    conn = sqlite3.connect(db_path)
    row = conn.execute(
        "SELECT sector FROM sector_map WHERE ticker='IREN'"
    ).fetchone()
    conn.close()
    assert row == ("infra",)


def test_rebuild_is_full_rebuild(tmp_path, monkeypatch):
    """Second rebuild removes rows for deleted tickers."""
    monkeypatch.setattr("eca.config.project_root", lambda: tmp_path)
    _make_facts(tmp_path, "IREN", "q1-2025")
    db_path = tmp_path / "data" / "eca.db"
    rebuild_index(db_path)

    # Delete the ticker directory
    import shutil
    shutil.rmtree(tmp_path / "data" / "iren")

    rebuild_index(db_path)
    conn = sqlite3.connect(db_path)
    count = conn.execute("SELECT COUNT(*) FROM quarter_facts").fetchone()[0]
    conn.close()
    assert count == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_db.py -v`
Expected: FAIL with ModuleNotFoundError

- [ ] **Step 3: Implement `src/eca/db.py`**

```python
"""SQLite index — derived from facts.json for fast aggregation queries."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from eca.config import WATCHLIST_SECTORS
from eca.schema import load_facts

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS quarter_facts (
    ticker TEXT NOT NULL,
    quarter TEXT NOT NULL,
    company TEXT,
    call_date TEXT,
    dim1_grade TEXT, dim2_grade TEXT, dim3_grade TEXT,
    dim4_grade TEXT, dim5_grade TEXT,
    composite_grade TEXT, composite_score REAL,
    skill_version TEXT, analyzed_at TEXT,
    revenue_m REAL, gross_profit_m REAL, operating_income_m REAL,
    net_income_m REAL, eps REAL,
    free_cash_flow_m REAL, operating_cash_flow_m REAL,
    capital_expenditure_m REAL,
    cash_and_equivalents_m REAL, total_assets_m REAL,
    total_equity_m REAL, shares_outstanding_m REAL,
    bvps REAL, roe_pct REAL,
    combined_ratio_pct REAL, loss_ratio_pct REAL, expense_ratio_pct REAL,
    PRIMARY KEY (ticker, quarter)
);

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
"""

# Fields to copy from facts.json candor section → quarter_facts columns
_CANDOR_FIELDS = [
    "dim1_grade", "dim2_grade", "dim3_grade", "dim4_grade", "dim5_grade",
    "composite_grade", "composite_score", "skill_version", "analyzed_at",
]

# Fields to copy from facts.json metrics section → quarter_facts columns
_METRIC_FIELDS = [
    "revenue_m", "gross_profit_m", "operating_income_m", "net_income_m", "eps",
    "free_cash_flow_m", "operating_cash_flow_m", "capital_expenditure_m",
    "cash_and_equivalents_m", "total_assets_m", "total_equity_m",
    "shares_outstanding_m", "bvps", "roe_pct",
    "combined_ratio_pct", "loss_ratio_pct", "expense_ratio_pct",
]


def connect_db(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    return conn


def rebuild_index(db_path: Path) -> None:
    """Full rebuild of the SQLite index from facts.json files."""
    from eca.config import data_dir

    conn = connect_db(db_path)
    conn.executescript(SCHEMA_SQL)

    # Clear all data (full rebuild)
    conn.execute("DELETE FROM quarter_flags")
    conn.execute("DELETE FROM quarter_facts")
    conn.execute("DELETE FROM sector_map")

    # Walk data directory
    data = data_dir()
    if data.exists():
        for ticker_dir in sorted(data.iterdir()):
            if not ticker_dir.is_dir() or ticker_dir.name == "synthesis":
                continue
            ticker = ticker_dir.name.upper()
            for quarter_dir in sorted(ticker_dir.iterdir()):
                facts_path = quarter_dir / "facts.json"
                if not quarter_dir.is_dir() or not facts_path.exists():
                    continue
                facts = load_facts(facts_path)
                _insert_quarter(conn, ticker, quarter_dir.name, facts)

    # Populate sector_map from config
    for sector, tickers in WATCHLIST_SECTORS.items():
        for ticker in tickers:
            conn.execute(
                "INSERT OR REPLACE INTO sector_map (ticker, sector) VALUES (?, ?)",
                (ticker, sector),
            )

    conn.commit()
    conn.close()


def _insert_quarter(
    conn: sqlite3.Connection, ticker: str, quarter: str, facts: dict
) -> None:
    candor = facts.get("candor", {})
    metrics = facts.get("metrics", {})

    values = {
        "ticker": ticker,
        "quarter": quarter,
        "company": facts.get("company"),
        "call_date": facts.get("call_date"),
    }
    for f in _CANDOR_FIELDS:
        values[f] = candor.get(f)
    for f in _METRIC_FIELDS:
        values[f] = metrics.get(f)

    cols = ", ".join(values.keys())
    placeholders = ", ".join(["?"] * len(values))
    conn.execute(
        f"INSERT INTO quarter_facts ({cols}) VALUES ({placeholders})",
        list(values.values()),
    )

    # Flags
    for flag in facts.get("flags", []):
        conn.execute(
            "INSERT OR IGNORE INTO quarter_flags (ticker, quarter, flag) VALUES (?, ?, ?)",
            (ticker, quarter, flag),
        )
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_db.py -v`
Expected: All 5 pass

- [ ] **Step 5: Commit**

```bash
git add src/eca/db.py tests/test_db.py
git commit -m "feat: add SQLite index with rebuild from facts.json"
```

---

### Task 4: SQLite aggregation queries

**Files:**
- Modify: `src/eca/db.py`
- Test: `tests/test_db.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_db.py`:

```python
from eca.db import query_sector_financials, query_grade_trajectory, query_flag_frequency


def test_query_sector_financials(tmp_path, monkeypatch):
    monkeypatch.setattr("eca.config.project_root", lambda: tmp_path)
    _make_facts(tmp_path, "IREN", "q1-2025", metrics={"revenue_m": 240.0, "capital_expenditure_m": 100.0})
    _make_facts(tmp_path, "IREN", "q2-2025", metrics={"revenue_m": 300.0, "capital_expenditure_m": 120.0})
    _make_facts(tmp_path, "CIFR", "q1-2025", metrics={"revenue_m": 72.0})
    db_path = tmp_path / "data" / "eca.db"
    rebuild_index(db_path)
    conn = connect_db(db_path)
    rows = query_sector_financials(conn, ["IREN", "CIFR"])
    conn.close()
    iren = [r for r in rows if r["ticker"] == "IREN"][0]
    assert iren["total_revenue"] == 540.0
    assert iren["total_capex"] == 220.0


def test_query_grade_trajectory(tmp_path, monkeypatch):
    monkeypatch.setattr("eca.config.project_root", lambda: tmp_path)
    _make_facts(tmp_path, "IREN", "q3-2023", candor={"composite_score": 2.58, "composite_grade": "C+"})
    _make_facts(tmp_path, "IREN", "q1-2025", candor={"composite_score": 2.65, "composite_grade": "B"})
    db_path = tmp_path / "data" / "eca.db"
    rebuild_index(db_path)
    conn = connect_db(db_path)
    rows = query_grade_trajectory(conn, ["IREN"])
    conn.close()
    assert len(rows) == 2
    assert rows[0]["quarter"] == "q3-2023"  # chronological order
    assert rows[1]["quarter"] == "q1-2025"


def test_query_flag_frequency(tmp_path, monkeypatch):
    monkeypatch.setattr("eca.config.project_root", lambda: tmp_path)
    _make_facts(tmp_path, "IREN", "q1-2025", flags=["equity_declining_yoy"])
    _make_facts(tmp_path, "CIFR", "q1-2025", flags=["equity_declining_yoy", "bvps_absent"])
    db_path = tmp_path / "data" / "eca.db"
    rebuild_index(db_path)
    conn = connect_db(db_path)
    rows = query_flag_frequency(conn, ["IREN", "CIFR"])
    conn.close()
    freqs = {r["flag"]: r["cnt"] for r in rows}
    assert freqs["equity_declining_yoy"] == 2
    assert freqs["bvps_absent"] == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_db.py::test_query_sector_financials -v`
Expected: FAIL with ImportError

- [ ] **Step 3: Add query functions to `db.py`**

```python
def query_sector_financials(
    conn: sqlite3.Connection, tickers: list[str], min_quarter: str | None = None,
) -> list[dict]:
    """Sum financial metrics per ticker across quarters."""
    placeholders = ",".join(["?"] * len(tickers))
    sql = f"""
        SELECT ticker,
               SUM(revenue_m) as total_revenue,
               SUM(capital_expenditure_m) as total_capex,
               SUM(free_cash_flow_m) as total_fcf,
               SUM(operating_income_m) as total_operating_income,
               COUNT(*) as quarter_count
        FROM quarter_facts
        WHERE ticker IN ({placeholders})
        {"AND quarter >= ?" if min_quarter else ""}
        GROUP BY ticker
    """
    params = tickers + ([min_quarter] if min_quarter else [])
    return [dict(r) for r in conn.execute(sql, params).fetchall()]


def query_grade_trajectory(conn: sqlite3.Connection, tickers: list[str]) -> list[dict]:
    """Grade scores per ticker-quarter, sorted chronologically."""
    from eca.config import quarter_sort_key

    placeholders = ",".join(["?"] * len(tickers))
    rows = [
        dict(r) for r in conn.execute(
            f"""SELECT ticker, quarter, composite_score, composite_grade,
                       dim1_grade, dim2_grade, dim3_grade, dim4_grade, dim5_grade
                FROM quarter_facts
                WHERE ticker IN ({placeholders}) AND composite_grade IS NOT NULL
                ORDER BY ticker, quarter""",
            tickers,
        ).fetchall()
    ]
    rows.sort(key=lambda r: (r["ticker"], quarter_sort_key(r["quarter"])))
    return rows


def query_flag_frequency(conn: sqlite3.Connection, tickers: list[str]) -> list[dict]:
    """Count each flag across the given tickers."""
    placeholders = ",".join(["?"] * len(tickers))
    return [
        dict(r) for r in conn.execute(
            f"""SELECT flag, COUNT(*) as cnt
                FROM quarter_flags
                WHERE ticker IN ({placeholders})
                GROUP BY flag ORDER BY cnt DESC""",
            tickers,
        ).fetchall()
    ]
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_db.py -v`
Expected: All 8 pass

- [ ] **Step 5: Commit**

```bash
git add src/eca/db.py tests/test_db.py
git commit -m "feat: add SQLite aggregation queries for synthesis"
```

---

### Task 5: `eca build-index` CLI command

**Files:**
- Modify: `src/eca/cli.py`

- [ ] **Step 1: Add `build-index` command to `cli.py`**

Add before the `query` command:

```python
@cli.command("build-index")
def build_index_cmd():
    """Rebuild SQLite index from facts.json files."""
    from eca.config import data_dir
    from eca.db import rebuild_index

    db_path = data_dir() / "eca.db"
    rebuild_index(db_path)
    click.echo(f"Index rebuilt -> {db_path}")
```

- [ ] **Step 2: Smoke test manually**

Run: `eca build-index`
Expected: `Index rebuilt -> /path/to/data/eca.db`

- [ ] **Step 3: Run full test suite**

Run: `pytest tests/ -v`
Expected: All pass

- [ ] **Step 4: Commit**

```bash
git add src/eca/cli.py
git commit -m "feat: add build-index CLI command"
```

---

### Task 6: Synthesis skill prompts

**Files:**
- Create: `skills/synthesis-brief.md`
- Create: `skills/synthesis-sector.md`

- [ ] **Step 1: Write Stage 1 prompt (`skills/synthesis-brief.md`)**

```markdown
You are a financial analyst condensing a company's earnings call history into a structured brief.

Given all available quarterly analyses and financial metrics for a single company, produce a 500-800 word brief organized into these sections:

## Candor Trajectory
Grade progression across quarters with named inflection points. Note the direction (improving, stagnating, declining) and identify which quarter marked any shift.

## Key Commitments
Two categories, clearly separated:
- **Signed:** Contracts with named counterparties, disclosed values, and specific terms. These are receivables.
- **Aspirational:** Claims about demand, pipeline, or opportunity that lack counterparty names, dollar values, or binding terms. These are hopes.

## Capital Figures
Disclosed capex, revenue, financing amounts, and cash positions attributed to specific quarters. Use the structured financial data provided — do not infer numbers from narrative.

## FOG Patterns
Recurring vague language across quarters. Note whether linguistic precision improved or degraded over time. Cite specific repeated phrases.

## Flags & Risks
Aggregate data quality flags (equity declining, missing metrics) and communication-level risks identified in the analyses.

## Verify Next Quarter
Carry forward the most recent analysis's tracking commitments — what should be checked when the next transcript drops?

Rules:
- Ground every claim in specific transcript evidence or structured data.
- Do not summarize each quarter sequentially. Synthesize across quarters.
- Financial numbers come from the structured metrics, not from your interpretation of the prose.
- Be direct. No filler, no hedging, no "it's worth noting."
```

- [ ] **Step 2: Write Stage 2 prompt (`skills/synthesis-sector.md`)**

```markdown
You are a macro analyst synthesizing individual company briefs into a sector-level intelligence report.

Given ticker briefs and an aggregated financial metrics table for all companies in a sector, produce a sector synthesis organized into these 7 signals:

## 1. Candor Trajectory
Sector-level pattern. How many companies improved, stagnated, or declined in candor scores? Name the outliers and what drove the change.

## 2. Signed vs. Aspirational
Aggregate named, signed contracts (counterparty, value, terms) across the sector. Total dollar value. Separately aggregate aspirational claims lacking specificity. Compute the ratio. A sector where 80% of stated pipeline is aspirational tells a different story than one where 80% is signed.

## 3. Bottleneck Migration
What constraint is the sector discussing now vs. earlier quarters? Power? Chips? Memory? Labor? Permitting? Track how the dominant constraint language shifted. If every company talked about power 4 quarters ago and now talks about chip supply, that's the bottleneck migrating.

## 4. Cross-Company Corroboration
When multiple companies independently confirm the same signal (hyperscaler demand, power scarcity, GPU availability), surface it as corroborated. When a claim appears in only one company's transcript — especially when the counterparty never mentions them — flag it as unverified.

## 5. Sector FOG Index
Are companies converging on the same vague demand language? If 4 of 6 companies use "strong demand" or equivalent without quantification, that uniformity is a red flag — it suggests coordinated narrative rather than independent evidence.

## 6. Aggregated Flags & Risks
Roll up per-company flags and communication risks into a sector-level view. Which risks appear across multiple companies? Which are isolated?

## 7. Capital Deployment Aggregation
Using the financial metrics table provided, present a per-company breakdown of key financials (revenue, capex, FCF) with sector totals. If prior-period data exists, show the delta. This is the "Gerstner check" — does the bottom-up sum of disclosed figures match or challenge pundit claims about sector-level spending?

Rules:
- Use the structured metrics table for all numerical aggregation — do not compute sums from narrative.
- Cross-reference between companies. The value of this report is the connections that no single-company analysis can make.
- Be direct. Lead with the signal, support with evidence.
- Name specific companies, quarters, and figures. No vague sector generalizations.
```

- [ ] **Step 3: Commit**

```bash
git add skills/synthesis-brief.md skills/synthesis-sector.md
git commit -m "feat: add synthesis skill prompts for ticker brief and sector synthesis"
```

---

### Task 7: Synthesize processor — ticker_brief

**Files:**
- Create: `src/eca/processors/synthesize.py`
- Test: `tests/test_synthesize.py`

- [ ] **Step 1: Write failing tests for `build_brief_input`**

```python
from eca.processors.synthesize import build_brief_input


def test_build_brief_input_includes_analyses(tmp_path, monkeypatch):
    monkeypatch.setattr("eca.config.project_root", lambda: tmp_path)
    d = tmp_path / "data" / "iren" / "q1-2025"
    d.mkdir(parents=True)
    (d / "analysis.md").write_text("# Analysis Q1")
    (d / "facts.json").write_text('{"ticker":"IREN","quarter":"Q1 2025"}')

    result = build_brief_input("IREN")
    assert "# Analysis Q1" in result
    assert "Q1 2025" in result


def test_build_brief_input_chronological_order(tmp_path, monkeypatch):
    monkeypatch.setattr("eca.config.project_root", lambda: tmp_path)
    for q in ["q2-2025", "q4-2024", "q1-2025"]:
        d = tmp_path / "data" / "iren" / q
        d.mkdir(parents=True)
        (d / "analysis.md").write_text(f"# Analysis {q}")
        (d / "facts.json").write_text(f'{{"ticker":"IREN","quarter":"{q}"}}')

    result = build_brief_input("IREN")
    # q4-2024 should appear before q1-2025, which appears before q2-2025
    pos_q4 = result.index("q4-2024")
    pos_q1 = result.index("q1-2025")
    pos_q2 = result.index("q2-2025")
    assert pos_q4 < pos_q1 < pos_q2


def test_build_brief_input_skips_unanalyzed(tmp_path, monkeypatch):
    monkeypatch.setattr("eca.config.project_root", lambda: tmp_path)
    d = tmp_path / "data" / "iren" / "q1-2025"
    d.mkdir(parents=True)
    (d / "facts.json").write_text('{"ticker":"IREN"}')  # no analysis.md

    result = build_brief_input("IREN")
    assert result is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_synthesize.py -v`
Expected: FAIL with ModuleNotFoundError

- [ ] **Step 3: Implement `build_brief_input` and `ticker_brief`**

Create `src/eca/processors/synthesize.py`:

```python
"""synthesize processor: sector-level synthesis from per-ticker analyses."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from eca.config import (
    data_dir, skills_dir, quarter_sort_key, WATCHLIST_SECTORS, COMPANY_NAMES,
)
from eca.schema import load_facts


def build_brief_input(ticker: str) -> str | None:
    """Assemble all analyses + metrics for a ticker into a single LLM input.

    Returns None if no analyzed quarters exist.
    """
    ticker_dir = data_dir() / ticker.lower()
    if not ticker_dir.exists():
        return None

    quarters = sorted(
        (d for d in ticker_dir.iterdir()
         if d.is_dir() and (d / "analysis.md").exists()),
        key=lambda d: quarter_sort_key(d.name),
    )

    if not quarters:
        return None

    sections: list[str] = []
    company = COMPANY_NAMES.get(ticker.upper(), ticker.upper())
    sections.append(f"# {company} ({ticker.upper()}) — Full Analysis History\n")

    for q_dir in quarters:
        q = q_dir.name
        facts = load_facts(q_dir / "facts.json")
        analysis = (q_dir / "analysis.md").read_text()

        metrics = facts.get("metrics", {})
        metrics_lines = []
        for field in ["revenue_m", "capital_expenditure_m", "free_cash_flow_m",
                       "operating_income_m", "cash_and_equivalents_m", "total_equity_m"]:
            val = metrics.get(field)
            if val is not None:
                label = field.replace("_m", "").replace("_", " ").title()
                metrics_lines.append(f"- {label}: ${val}M")

        candor = facts.get("candor", {})
        grade_line = ""
        if candor.get("composite_grade"):
            grade_line = f"**Composite: {candor['composite_grade']} ({candor.get('composite_score', '?')})**"

        flags = facts.get("flags", [])
        flags_line = f"Flags: {', '.join(flags)}" if flags else ""

        header = f"## {q} {grade_line}"
        parts = [header]
        if metrics_lines:
            parts.append("Metrics:\n" + "\n".join(metrics_lines))
        if flags_line:
            parts.append(flags_line)
        parts.append(analysis)

        sections.append("\n\n".join(parts))

    return "\n\n---\n\n".join(sections)


def ticker_brief(ticker: str, model: str) -> Path | None:
    """Generate a ticker brief via LLM. Returns path to brief.md or None."""
    from eca.llm import run_analysis

    user_input = build_brief_input(ticker)
    if not user_input:
        return None

    system_prompt = (skills_dir() / "synthesis-brief.md").read_text()
    brief = run_analysis(system_prompt, user_input, model=model)

    out_path = data_dir() / ticker.lower() / "brief.md"
    out_path.write_text(brief)
    return out_path
```

- [ ] **Step 4: Write mock LLM test for `ticker_brief`**

Append to `tests/test_synthesize.py`:

```python
from eca.processors.synthesize import ticker_brief


def test_ticker_brief_writes_output(tmp_path, monkeypatch):
    monkeypatch.setattr("eca.config.project_root", lambda: tmp_path)
    monkeypatch.setattr("eca.llm.run_analysis", lambda sys, usr, model="": "# Mock Brief")

    d = tmp_path / "data" / "iren" / "q1-2025"
    d.mkdir(parents=True)
    (d / "analysis.md").write_text("# Analysis")
    (d / "facts.json").write_text('{"ticker":"IREN"}')

    # Create skills dir with prompt
    skills = tmp_path / "skills"
    skills.mkdir()
    (skills / "synthesis-brief.md").write_text("You are a financial analyst.")

    result = ticker_brief("IREN", model="test-model")
    assert result is not None
    assert result.name == "brief.md"
    assert result.read_text() == "# Mock Brief"
```

- [ ] **Step 5: Run tests**

Run: `pytest tests/test_synthesize.py -v`
Expected: All 4 pass

- [ ] **Step 6: Commit**

```bash
git add src/eca/processors/synthesize.py tests/test_synthesize.py
git commit -m "feat: add ticker_brief with build_brief_input for Stage 1 synthesis"
```

---

### Task 8: Synthesize processor — sector_synthesis

**Files:**
- Modify: `src/eca/processors/synthesize.py`
- Test: `tests/test_synthesize.py`

- [ ] **Step 1: Write failing tests for `build_sector_input`**

Append to `tests/test_synthesize.py`:

```python
from eca.processors.synthesize import build_sector_input


def test_build_sector_input(tmp_path, monkeypatch):
    monkeypatch.setattr("eca.config.project_root", lambda: tmp_path)

    # Create brief files and facts.json with metrics
    for ticker in ["iren", "cifr"]:
        d = tmp_path / "data" / ticker
        d.mkdir(parents=True)
        (d / "brief.md").write_text(f"# {ticker.upper()} Brief\nSome analysis.")
        q = d / "q1-2025"
        q.mkdir()
        (q / "facts.json").write_text(json.dumps({
            "ticker": ticker.upper(),
            "metrics": {"revenue_m": 100.0, "capital_expenditure_m": 50.0},
        }))

    # Create and populate SQLite index
    from eca.db import rebuild_index, connect_db
    db_path = tmp_path / "data" / "eca.db"
    rebuild_index(db_path)

    conn = connect_db(db_path)
    result = build_sector_input("infra", conn)
    conn.close()

    assert "IREN Brief" in result
    assert "CIFR Brief" in result
    assert "Financial Summary" in result
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_synthesize.py::test_build_sector_input -v`
Expected: FAIL with ImportError

- [ ] **Step 3: Add `build_sector_input` and `sector_synthesis` to `synthesize.py`**

```python
def build_sector_input(sector: str, conn) -> str:
    """Assemble ticker briefs + aggregated metrics for a sector."""
    from eca.db import query_sector_financials, query_grade_trajectory, query_flag_frequency

    tickers = WATCHLIST_SECTORS.get(sector, [])
    sections: list[str] = [f"# Sector: {sector}\n"]

    # Ticker briefs
    briefs_found = 0
    for ticker in tickers:
        brief_path = data_dir() / ticker.lower() / "brief.md"
        if brief_path.exists():
            sections.append(brief_path.read_text())
            briefs_found += 1
        else:
            sections.append(f"## {ticker}\nNo analysis data available.\n")

    # Aggregated financial metrics table
    financials = query_sector_financials(conn, tickers)
    def fmt(v):
        return f"${v:.0f}M" if v else "—"

    if financials:
        table_lines = ["## Financial Summary\n",
                       "| Ticker | Quarters | Revenue | CapEx | FCF |",
                       "|--------|----------|---------|-------|-----|"]
        for row in financials:
            table_lines.append(
                f"| {row['ticker']} | {row['quarter_count']} "
                f"| {fmt(row['total_revenue'])} | {fmt(row['total_capex'])} "
                f"| {fmt(row['total_fcf'])} |"
            )
        sections.append("\n".join(table_lines))

    # Grade trajectory
    grades = query_grade_trajectory(conn, tickers)
    if grades:
        grade_lines = ["## Grade Trajectory\n",
                       "| Ticker | Quarter | Grade | Score |",
                       "|--------|---------|-------|-------|"]
        for row in grades:
            grade_lines.append(
                f"| {row['ticker']} | {row['quarter']} "
                f"| {row['composite_grade']} | {row['composite_score'] or '—'} |"
            )
        sections.append("\n".join(grade_lines))

    # Flag frequency
    flags = query_flag_frequency(conn, tickers)
    if flags:
        flag_lines = ["## Flag Frequency\n"]
        for row in flags:
            flag_lines.append(f"- {row['flag']}: {row['cnt']} occurrences")
        sections.append("\n".join(flag_lines))

    return "\n\n---\n\n".join(sections)


def sector_synthesis(sector: str, model: str) -> Path | None:
    """Generate a sector synthesis via LLM. Returns path to output or None."""
    from eca.llm import run_analysis
    from eca.db import connect_db

    db_path = data_dir() / "eca.db"
    if not db_path.exists():
        return None

    conn = connect_db(db_path)
    user_input = build_sector_input(sector, conn)
    conn.close()

    system_prompt = (skills_dir() / "synthesis-sector.md").read_text()
    result = run_analysis(system_prompt, user_input, model=model)

    out_dir = data_dir() / "synthesis"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{sector}-{date.today().isoformat()}.md"
    out_path.write_text(result)
    return out_path
```

- [ ] **Step 4: Write mock LLM test for `sector_synthesis`**

Append to `tests/test_synthesize.py`:

```python
from eca.processors.synthesize import sector_synthesis


def test_sector_synthesis_writes_output(tmp_path, monkeypatch):
    monkeypatch.setattr("eca.config.project_root", lambda: tmp_path)
    monkeypatch.setattr("eca.llm.run_analysis", lambda sys, usr, model="": "# Infra Synthesis")

    # Create brief + facts for one ticker
    d = tmp_path / "data" / "iren"
    d.mkdir(parents=True)
    (d / "brief.md").write_text("# IREN Brief")
    q = d / "q1-2025"
    q.mkdir()
    (q / "facts.json").write_text(json.dumps({"ticker": "IREN", "metrics": {"revenue_m": 240.0}}))

    # Build index
    from eca.db import rebuild_index
    db_path = tmp_path / "data" / "eca.db"
    rebuild_index(db_path)

    # Create skills dir with prompt
    skills = tmp_path / "skills"
    skills.mkdir()
    (skills / "synthesis-sector.md").write_text("You are a macro analyst.")

    result = sector_synthesis("infra", model="test-model")
    assert result is not None
    assert "infra-" in result.name
    assert result.read_text() == "# Infra Synthesis"
```

- [ ] **Step 5: Run tests**

Run: `pytest tests/test_synthesize.py -v`
Expected: All 6 pass

- [ ] **Step 6: Commit**

```bash
git add src/eca/processors/synthesize.py tests/test_synthesize.py
git commit -m "feat: add sector_synthesis with build_sector_input for Stage 2"
```

---

### Task 9: `eca synthesize` CLI command

**Files:**
- Modify: `src/eca/cli.py`

- [ ] **Step 1: Add `synthesize` command**

Add after `build-index`:

```python
@cli.command("synthesize")
@click.option("--sector", help="Sector name (e.g. infra, ai, crypto) or 'all'")
@click.option("--list-sectors", is_flag=True, help="List available sectors and exit")
@click.option("--model", default="claude-sonnet-4-6", help="Model to use")
def synthesize_cmd(sector: str | None, list_sectors: bool, model: str):
    """Generate sector-level synthesis from cross-company analysis data."""
    from eca.config import WATCHLIST_SECTORS, data_dir
    from eca.db import rebuild_index, connect_db
    from eca.processors.synthesize import ticker_brief, sector_synthesis

    if list_sectors:
        for name, tickers in WATCHLIST_SECTORS.items():
            click.echo(f"  {name:12s} {', '.join(tickers)}")
        return

    if not sector:
        raise click.UsageError("Provide --sector <name> or --list-sectors")

    sectors = list(WATCHLIST_SECTORS.keys()) if sector == "all" else [sector]

    for s in sectors:
        if s not in WATCHLIST_SECTORS:
            raise click.UsageError(f"Unknown sector '{s}'. Use --list-sectors to see options.")

    # Rebuild index before synthesis
    db_path = data_dir() / "eca.db"
    click.echo("Rebuilding index...")
    rebuild_index(db_path)

    for s in sectors:
        tickers = WATCHLIST_SECTORS[s]
        click.echo(f"\n=== {s} ({len(tickers)} tickers) ===")

        # Stage 1: ticker briefs
        for ticker in tickers:
            click.echo(f"  {ticker}: generating brief...")
            result = ticker_brief(ticker, model=model)
            if result:
                click.echo(f"    -> {result}")
            else:
                click.echo(f"    (no analyzed data, skipped)")

        # Stage 2: sector synthesis
        click.echo(f"  Synthesizing {s}...")
        result = sector_synthesis(s, model=model)
        if result:
            click.echo(f"  -> {result}")
        else:
            click.echo(f"  (no data for synthesis)")
```

- [ ] **Step 2: Test `--list-sectors` manually**

Run: `eca synthesize --list-sectors`
Expected: Lists all 7 sectors with their tickers

- [ ] **Step 3: Run full test suite**

Run: `pytest tests/ -v`
Expected: All pass

- [ ] **Step 4: Commit**

```bash
git add src/eca/cli.py
git commit -m "feat: add synthesize CLI command with --sector and --list-sectors"
```

---

### Task 10: End-to-end smoke test

**Files:** None (manual verification)

- [ ] **Step 1: Build the index**

Run: `eca build-index`

- [ ] **Step 2: Run synthesis for infra sector**

Run: `eca synthesize --sector infra`

This makes 1 LLM call per ticker with data (IREN, CIFR) + 1 sector synthesis call. Verify:
- `data/iren/brief.md` and `data/cifr/brief.md` are generated
- `data/synthesis/infra-2026-03-22.md` is generated
- The sector synthesis contains all 7 signal sections
- Capital deployment table has real numbers from the SQLite index

- [ ] **Step 3: Verify the output quality**

Read `data/synthesis/infra-2026-03-22.md` and check:
- Does the candor trajectory section reflect IREN's C+ → B+ arc?
- Does the signed vs. aspirational section separate the Microsoft $9.7B from vague demand claims?
- Does the capital deployment table sum correctly?

- [ ] **Step 4: Commit synthesis output (optional)**

```bash
git add data/synthesis/
git commit -m "chore: add first infra sector synthesis"
```

- [ ] **Step 5: Push**

```bash
git push
```
