# ECA Data Flywheel Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build `eca` CLI tool that turns markdown-based earnings call analysis into an atomic, multi-source data pipeline with shared JSON fact files.

**Architecture:** Independent processors (ingest-metrics, ingest-transcript, analyze, query) each own a top-level key in a shared `facts.json` per company-quarter. No database, no coordination layer. The JSON fact file is the only coupling point.

**Tech Stack:** Python 3.11+, Click (CLI framework), Anthropic SDK (analysis), yfinance (financial data), pytest (testing)

---

### Task 1: Project Scaffolding

**Files:**
- Create: `pyproject.toml`
- Create: `src/eca/__init__.py`
- Create: `src/eca/cli.py`

**Step 1: Create pyproject.toml**

```toml
[project]
name = "eca"
version = "0.1.0"
description = "Earnings Call Analyzer - atomic data pipeline for candor analysis"
requires-python = ">=3.11"
dependencies = [
    "click>=8.0",
    "anthropic>=0.40.0",
    "yfinance>=0.2.0",
]

[project.optional-dependencies]
dev = ["pytest>=8.0"]

[project.scripts]
eca = "eca.cli:cli"

[build-system]
requires = ["setuptools>=68.0"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
where = ["src"]
```

**Step 2: Create src/eca/__init__.py**

```python
"""Earnings Call Analyzer."""
```

**Step 3: Create src/eca/cli.py**

```python
import click


@click.group()
def cli():
    """Earnings Call Analyzer - atomic data pipeline for candor analysis."""
    pass
```

**Step 4: Install in development mode**

Run: `pip install -e ".[dev]"`

**Step 5: Verify CLI works**

Run: `eca --help`
Expected: Shows help text with "Earnings Call Analyzer" description

**Step 6: Commit**

```bash
git add pyproject.toml src/
git commit -m "feat: scaffold eca CLI project"
```

---

### Task 2: Schema Module

**Files:**
- Create: `tests/test_schema.py`
- Create: `src/eca/schema.py`

**Step 1: Write failing tests**

```python
import json
from pathlib import Path

from eca.schema import Facts, load_facts, save_facts


def test_load_facts_missing_file(tmp_path):
    path = tmp_path / "facts.json"
    result = load_facts(path)
    assert result == {}


def test_save_and_load_round_trip(tmp_path):
    path = tmp_path / "sub" / "facts.json"
    facts: Facts = {
        "company": "Root, Inc.",
        "ticker": "ROOT",
        "quarter": "Q3 2025",
        "call_date": "2025-11-04",
        "metrics": {"source": "yfinance", "revenue_m": 387.8},
        "candor": {"composite_grade": "C", "composite_score": 2.03},
        "flags": ["bvps_absent"],
        "tracking": ["Monitor BVPS trajectory"],
    }
    save_facts(path, facts)
    loaded = load_facts(path)
    assert loaded["ticker"] == "ROOT"
    assert loaded["metrics"]["revenue_m"] == 387.8
    assert loaded["flags"] == ["bvps_absent"]


def test_save_creates_parent_dirs(tmp_path):
    path = tmp_path / "a" / "b" / "c" / "facts.json"
    save_facts(path, {"ticker": "TEST"})
    assert path.exists()


def test_save_overwrites_existing(tmp_path):
    path = tmp_path / "facts.json"
    save_facts(path, {"ticker": "OLD"})
    save_facts(path, {"ticker": "NEW"})
    loaded = load_facts(path)
    assert loaded["ticker"] == "NEW"
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_schema.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'eca.schema'`

**Step 3: Implement schema.py**

```python
"""facts.json schema and I/O helpers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, TypedDict


class QuarterMetrics(TypedDict, total=False):
    source: str
    ingested_at: str
    revenue_m: float | None
    gross_profit_m: float | None
    operating_income_m: float | None
    net_income_m: float | None
    eps: float | None
    free_cash_flow_m: float | None
    operating_cash_flow_m: float | None
    capital_expenditure_m: float | None
    cash_and_equivalents_m: float | None
    total_assets_m: float | None
    total_equity_m: float | None
    shares_outstanding_m: float | None
    bvps: float | None
    roe_pct: float | None
    combined_ratio_pct: float | None
    loss_ratio_pct: float | None
    expense_ratio_pct: float | None


class CandorGrades(TypedDict, total=False):
    analyzed_at: str
    skill_version: str
    dim1_grade: str
    dim2_grade: str
    dim3_grade: str
    dim4_grade: str
    dim5_grade: str
    composite_score: float
    composite_grade: str


class Facts(TypedDict, total=False):
    company: str
    ticker: str
    quarter: str
    call_date: str
    metrics: QuarterMetrics
    candor: CandorGrades
    flags: list[str]
    tracking: list[str]


def load_facts(path: Path) -> dict[str, Any]:
    """Load facts.json, returning empty dict if file doesn't exist."""
    if path.exists():
        return json.loads(path.read_text())
    return {}


def save_facts(path: Path, facts: dict[str, Any]) -> None:
    """Write facts.json, creating parent directories as needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(facts, indent=2) + "\n")
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_schema.py -v`
Expected: 4 passed

**Step 5: Commit**

```bash
git add src/eca/schema.py tests/test_schema.py
git commit -m "feat: add facts.json schema and I/O helpers"
```

---

### Task 3: Config Module

**Files:**
- Create: `tests/test_config.py`
- Create: `src/eca/config.py`

**Step 1: Write failing tests**

```python
from eca.config import get_sector, data_dir, skills_dir, quarter_dir, COMPANY_NAMES


def test_get_sector_insurtech():
    assert get_sector("ROOT") == "insurtech"
    assert get_sector("LMND") == "insurtech"


def test_get_sector_default():
    assert get_sector("SPOT") == "base"
    assert get_sector("UNKNOWN") == "base"


def test_get_sector_case_insensitive():
    assert get_sector("root") == "insurtech"


def test_data_dir_resolves():
    d = data_dir()
    assert d.name == "data"


def test_skills_dir_resolves():
    d = skills_dir()
    assert d.name == "skills"


def test_quarter_dir():
    d = quarter_dir("ROOT", "q3-2025")
    assert d.parts[-1] == "q3-2025"
    assert d.parts[-2] == "root"


def test_company_names():
    assert "ROOT" in COMPANY_NAMES
    assert "LMND" in COMPANY_NAMES
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_config.py -v`
Expected: FAIL

**Step 3: Implement config.py**

```python
"""Project configuration: ticker mappings, directory resolution."""

from pathlib import Path

SECTOR_MAP: dict[str, str] = {
    "ROOT": "insurtech",
    "LMND": "insurtech",
    "HIMS": "base",
    "SPOT": "base",
    "GOOG": "base",
    "TSLA": "base",
}

COMPANY_NAMES: dict[str, str] = {
    "ROOT": "Root, Inc.",
    "LMND": "Lemonade, Inc.",
    "HIMS": "Hims & Hers Health, Inc.",
    "SPOT": "Spotify Technology S.A.",
    "GOOG": "Alphabet Inc.",
    "TSLA": "Tesla, Inc.",
}


def project_root() -> Path:
    """Walk up from this file to find pyproject.toml."""
    current = Path(__file__).resolve().parent
    while current != current.parent:
        if (current / "pyproject.toml").exists():
            return current
        current = current.parent
    raise FileNotFoundError("Could not find project root")


def data_dir() -> Path:
    return project_root() / "data"


def skills_dir() -> Path:
    return project_root() / "skills"


def quarter_dir(ticker: str, quarter: str) -> Path:
    return data_dir() / ticker.lower() / quarter


def get_sector(ticker: str) -> str:
    return SECTOR_MAP.get(ticker.upper(), "base")
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_config.py -v`
Expected: 7 passed

**Step 5: Commit**

```bash
git add src/eca/config.py tests/test_config.py
git commit -m "feat: add config module with ticker/sector mappings"
```

---

### Task 4: yfinance Fetcher

**Files:**
- Create: `tests/test_yfinance_fetcher.py`
- Create: `src/eca/parsers/__init__.py`
- Create: `src/eca/parsers/yfinance_fetcher.py`

yfinance provides quarterly financials, balance sheet, and cash flow as pandas DataFrames. Field names vary by company type (e.g. insurance companies have `Loss Adjustment Expense` instead of `Gross Profit`). The fetcher normalizes these into our schema.

**Step 1: Write failing tests**

```python
from unittest.mock import patch, MagicMock
import pandas as pd

from eca.parsers.yfinance_fetcher import fetch_quarterly_metrics, normalize_quarter_label


def _make_df(data: dict, dates: list[str]) -> pd.DataFrame:
    """Helper to build a DataFrame matching yfinance's format."""
    cols = pd.to_datetime(dates)
    return pd.DataFrame(data, index=cols).T


def test_normalize_quarter_label():
    assert normalize_quarter_label("2025-09-30") == "Q3 2025"
    assert normalize_quarter_label("2025-03-31") == "Q1 2025"
    assert normalize_quarter_label("2024-12-31") == "Q4 2024"
    assert normalize_quarter_label("2025-06-30") == "Q2 2025"


def test_fetch_maps_revenue():
    financials = _make_df(
        {"Total Revenue": [387.8e6, 348.6e6]},
        ["2025-09-30", "2025-06-30"],
    )
    balance = _make_df(
        {"Common Stock Equity": [265e6, 235e6]},
        ["2025-09-30", "2025-06-30"],
    )
    cashflow = _make_df(
        {"Free Cash Flow": [53.7e6, 25.3e6]},
        ["2025-09-30", "2025-06-30"],
    )

    with patch("eca.parsers.yfinance_fetcher.yf") as mock_yf:
        mock_ticker = MagicMock()
        mock_ticker.quarterly_financials = financials
        mock_ticker.quarterly_balance_sheet = balance
        mock_ticker.quarterly_cashflow = cashflow
        mock_ticker.info = {"sharesOutstanding": 15_500_000}
        mock_yf.Ticker.return_value = mock_ticker

        result = fetch_quarterly_metrics("ROOT")

    assert "Q3 2025" in result
    assert abs(result["Q3 2025"]["revenue_m"] - 387.8) < 0.1
    assert abs(result["Q2 2025"]["revenue_m"] - 348.6) < 0.1


def test_fetch_computes_gross_profit_for_insurance():
    """Insurance companies lack Gross Profit; compute from Revenue - Loss Adjustment Expense."""
    financials = _make_df(
        {
            "Total Revenue": [387.8e6],
            "Loss Adjustment Expense": [306.4e6],
        },
        ["2025-09-30"],
    )
    balance = _make_df({"Common Stock Equity": [265e6]}, ["2025-09-30"])
    cashflow = _make_df({"Free Cash Flow": [53.7e6]}, ["2025-09-30"])

    with patch("eca.parsers.yfinance_fetcher.yf") as mock_yf:
        mock_ticker = MagicMock()
        mock_ticker.quarterly_financials = financials
        mock_ticker.quarterly_balance_sheet = balance
        mock_ticker.quarterly_cashflow = cashflow
        mock_ticker.info = {}
        mock_yf.Ticker.return_value = mock_ticker

        result = fetch_quarterly_metrics("ROOT")

    assert abs(result["Q3 2025"]["gross_profit_m"] - 81.4) < 0.1


def test_fetch_maps_balance_sheet_fields():
    financials = _make_df({"Total Revenue": [100e6]}, ["2025-09-30"])
    balance = _make_df(
        {
            "Common Stock Equity": [265e6],
            "Total Assets": [1500e6],
            "Cash And Cash Equivalents": [654e6],
            "Ordinary Shares Number": [15_528_458],
        },
        ["2025-09-30"],
    )
    cashflow = _make_df({}, ["2025-09-30"])

    with patch("eca.parsers.yfinance_fetcher.yf") as mock_yf:
        mock_ticker = MagicMock()
        mock_ticker.quarterly_financials = financials
        mock_ticker.quarterly_balance_sheet = balance
        mock_ticker.quarterly_cashflow = cashflow
        mock_ticker.info = {}
        mock_yf.Ticker.return_value = mock_ticker

        result = fetch_quarterly_metrics("ROOT")

    q = result["Q3 2025"]
    assert abs(q["total_equity_m"] - 265.0) < 0.1
    assert abs(q["cash_and_equivalents_m"] - 654.0) < 0.1
    assert abs(q["shares_outstanding_m"] - 15.53) < 0.1
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_yfinance_fetcher.py -v`
Expected: FAIL

**Step 3: Implement the fetcher**

```python
"""Fetch quarterly financial metrics from Yahoo Finance via yfinance."""

from __future__ import annotations

import math
from datetime import date

import yfinance as yf


def normalize_quarter_label(date_str: str | date) -> str:
    """Convert '2025-09-30' or a date object to 'Q3 2025'."""
    d = date.fromisoformat(date_str) if isinstance(date_str, str) else date_str
    quarter = (d.month - 1) // 3 + 1
    return f"Q{quarter} {d.year}"


def _safe_get(df, field: str, col) -> float | None:
    """Safely extract a value from a DataFrame, returning None for NaN/missing."""
    if df is None or df.empty or field not in df.index:
        return None
    val = df.loc[field, col]
    if val is None or (isinstance(val, float) and math.isnan(val)):
        return None
    return float(val)


def _to_millions(val: float | None) -> float | None:
    if val is None:
        return None
    return round(val / 1_000_000, 1)


def fetch_quarterly_metrics(ticker: str) -> dict[str, dict[str, float | None]]:
    """Fetch quarterly metrics from yfinance and return normalized dict.

    Returns dict mapping quarter labels (e.g. 'Q3 2025') to metric dicts.
    """
    t = yf.Ticker(ticker.upper())

    financials = t.quarterly_financials
    balance = t.quarterly_balance_sheet
    cashflow = t.quarterly_cashflow

    if financials is None or financials.empty:
        return {}

    result: dict[str, dict[str, float | None]] = {}

    for col in financials.columns:
        q_label = normalize_quarter_label(col.date())
        metrics: dict[str, float | None] = {}

        # Income statement
        metrics["revenue_m"] = _to_millions(_safe_get(financials, "Total Revenue", col))

        gross = _safe_get(financials, "Gross Profit", col)
        if gross is None:
            # Insurance companies: compute from Revenue - Loss Adjustment Expense
            rev = _safe_get(financials, "Total Revenue", col)
            lae = _safe_get(financials, "Loss Adjustment Expense", col)
            if rev is not None and lae is not None:
                gross = rev - lae
        metrics["gross_profit_m"] = _to_millions(gross)

        op_inc = _safe_get(financials, "Operating Income", col)
        if op_inc is None:
            op_inc = _safe_get(financials, "EBIT", col)
        metrics["operating_income_m"] = _to_millions(op_inc)

        metrics["net_income_m"] = _to_millions(_safe_get(financials, "Net Income", col))
        metrics["eps"] = _safe_get(financials, "Basic EPS", col)

        # Balance sheet (columns may not align exactly, find nearest)
        if balance is not None and not balance.empty:
            bcol = _nearest_col(balance, col)
            if bcol is not None:
                equity_raw = _safe_get(balance, "Common Stock Equity", bcol)
                if equity_raw is None:
                    equity_raw = _safe_get(balance, "Total Equity Gross Minority Interest", bcol)
                metrics["total_equity_m"] = _to_millions(equity_raw)
                metrics["total_assets_m"] = _to_millions(
                    _safe_get(balance, "Total Assets", bcol)
                )
                metrics["cash_and_equivalents_m"] = _to_millions(
                    _safe_get(balance, "Cash And Cash Equivalents", bcol)
                )
                shares = _safe_get(balance, "Ordinary Shares Number", bcol)
                metrics["shares_outstanding_m"] = round(shares / 1_000_000, 2) if shares is not None else None

        # Cash flow
        if cashflow is not None and not cashflow.empty:
            ccol = _nearest_col(cashflow, col)
            if ccol is not None:
                metrics["free_cash_flow_m"] = _to_millions(
                    _safe_get(cashflow, "Free Cash Flow", ccol)
                )
                metrics["operating_cash_flow_m"] = _to_millions(
                    _safe_get(cashflow, "Operating Cash Flow", ccol)
                )
                metrics["capital_expenditure_m"] = _to_millions(
                    _safe_get(cashflow, "Capital Expenditure", ccol)
                )

        # Derived metrics
        equity = metrics.get("total_equity_m")
        shares_m = metrics.get("shares_outstanding_m")
        if equity is not None and shares_m is not None and shares_m > 0:
            metrics["bvps"] = round(equity / shares_m, 2)

        result[q_label] = metrics

    return result


def _nearest_col(df, target_col):
    """Find the column in df closest to target_col by date."""
    if target_col in df.columns:
        return target_col
    # Find nearest date
    target_ts = target_col.timestamp() if hasattr(target_col, "timestamp") else 0
    best = None
    best_diff = float("inf")
    for c in df.columns:
        diff = abs(c.timestamp() - target_ts)
        if diff < best_diff:
            best_diff = diff
            best = c
    # Only match within 45 days
    return best if best_diff < 45 * 86400 else None
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_yfinance_fetcher.py -v`
Expected: 4 passed

**Step 5: Commit**

```bash
git add src/eca/parsers/ tests/test_yfinance_fetcher.py
git commit -m "feat: add yfinance quarterly metrics fetcher"
```

---

### Task 5: ingest-transcript Command

**Files:**
- Create: `tests/test_ingest_transcript.py`
- Create: `src/eca/processors/__init__.py`
- Create: `src/eca/processors/ingest_transcript.py`
- Modify: `src/eca/cli.py`

**Step 1: Write failing tests**

```python
import json
from pathlib import Path
from click.testing import CliRunner

from eca.cli import cli

SAMPLE_TRANSCRIPT = """Operator: Good day and welcome to the Root Q3 2025 earnings call.

Alex Timm -- CEO

Thank you, operator. Q3 was another strong quarter for Root.
"""


def test_ingest_transcript_creates_files(tmp_path, monkeypatch):
    monkeypatch.setattr("eca.config.project_root", lambda: tmp_path)
    src = tmp_path / "transcript.txt"
    src.write_text(SAMPLE_TRANSCRIPT)

    runner = CliRunner()
    result = runner.invoke(cli, ["ingest-transcript", "root", "q3-2025", str(src)])

    assert result.exit_code == 0
    target = tmp_path / "data" / "root" / "q3-2025"
    assert (target / "transcript.txt").exists()
    assert (target / "facts.json").exists()


def test_ingest_transcript_copies_content(tmp_path, monkeypatch):
    monkeypatch.setattr("eca.config.project_root", lambda: tmp_path)
    src = tmp_path / "transcript.txt"
    src.write_text(SAMPLE_TRANSCRIPT)

    CliRunner().invoke(cli, ["ingest-transcript", "root", "q3-2025", str(src)])

    target = tmp_path / "data" / "root" / "q3-2025" / "transcript.txt"
    assert target.read_text() == SAMPLE_TRANSCRIPT


def test_ingest_transcript_creates_facts_stub(tmp_path, monkeypatch):
    monkeypatch.setattr("eca.config.project_root", lambda: tmp_path)
    src = tmp_path / "transcript.txt"
    src.write_text(SAMPLE_TRANSCRIPT)

    CliRunner().invoke(cli, ["ingest-transcript", "root", "q3-2025", str(src)])

    facts = json.loads(
        (tmp_path / "data" / "root" / "q3-2025" / "facts.json").read_text()
    )
    assert facts["ticker"] == "ROOT"
    assert facts["quarter"] == "Q3 2025"


def test_ingest_transcript_preserves_existing_facts(tmp_path, monkeypatch):
    monkeypatch.setattr("eca.config.project_root", lambda: tmp_path)

    # Pre-populate facts with metrics
    target_dir = tmp_path / "data" / "root" / "q3-2025"
    target_dir.mkdir(parents=True)
    (target_dir / "facts.json").write_text(
        json.dumps({"ticker": "ROOT", "metrics": {"revenue_m": 387.8}})
    )

    src = tmp_path / "transcript.txt"
    src.write_text(SAMPLE_TRANSCRIPT)

    CliRunner().invoke(cli, ["ingest-transcript", "root", "q3-2025", str(src)])

    facts = json.loads((target_dir / "facts.json").read_text())
    assert facts["metrics"]["revenue_m"] == 387.8  # preserved
    assert facts["quarter"] == "Q3 2025"  # added
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_ingest_transcript.py -v`
Expected: FAIL

**Step 3: Implement the processor**

Create `src/eca/processors/__init__.py` (empty).

Create `src/eca/processors/ingest_transcript.py`:

```python
"""ingest-transcript processor: register a transcript and initialize the quarter."""

from __future__ import annotations

import shutil
from pathlib import Path

from eca.config import quarter_dir, COMPANY_NAMES
from eca.schema import load_facts, save_facts


def normalize_quarter_label(quarter_slug: str) -> str:
    """Convert 'q3-2025' to 'Q3 2025'."""
    parts = quarter_slug.lower().split("-")
    return f"{parts[0].upper()} {parts[1]}"


def ingest_transcript(ticker: str, quarter_slug: str, source_path: Path) -> Path:
    """Copy transcript to data dir and create/update facts.json."""
    ticker_upper = ticker.upper()
    target = quarter_dir(ticker_upper, quarter_slug)
    target.mkdir(parents=True, exist_ok=True)

    shutil.copy2(source_path, target / "transcript.txt")

    facts_path = target / "facts.json"
    facts = load_facts(facts_path)
    facts["ticker"] = ticker_upper
    facts["quarter"] = normalize_quarter_label(quarter_slug)
    if ticker_upper in COMPANY_NAMES:
        facts["company"] = COMPANY_NAMES[ticker_upper]
    save_facts(facts_path, facts)

    return target
```

**Step 4: Wire to CLI**

Replace `src/eca/cli.py` with:

```python
import click
from pathlib import Path


@click.group()
def cli():
    """Earnings Call Analyzer - atomic data pipeline for candor analysis."""
    pass


@cli.command("ingest-transcript")
@click.argument("ticker")
@click.argument("quarter")
@click.argument("source", type=click.Path(exists=True, path_type=Path))
def ingest_transcript_cmd(ticker: str, quarter: str, source: Path):
    """Register a transcript and initialize the quarter."""
    from eca.processors.ingest_transcript import ingest_transcript

    target = ingest_transcript(ticker, quarter, source)
    click.echo(f"Ingested transcript -> {target}")
```

**Step 5: Run tests to verify they pass**

Run: `pytest tests/test_ingest_transcript.py -v`
Expected: 4 passed

**Step 6: Commit**

```bash
git add src/eca/processors/ src/eca/cli.py tests/test_ingest_transcript.py
git commit -m "feat: add ingest-transcript command"
```

---

### Task 6: ingest-metrics Command

> **Updated:** Now uses yfinance instead of thefly.com. No clipboard/file input needed -- fetches directly from Yahoo Finance API.

**Files:**
- Create: `tests/test_ingest_metrics.py`
- Create: `src/eca/processors/ingest_metrics.py`
- Modify: `src/eca/cli.py`

**Step 1: Write failing tests**

```python
import json
from pathlib import Path
from click.testing import CliRunner

from eca.cli import cli

MOCK_QUARTERS = {
    "Q3 2024": {
        "revenue_m": 387.8, "gross_profit_m": 81.4, "operating_income_m": -5.0,
        "total_equity_m": 265.0, "shares_outstanding_m": 15.53,
        "free_cash_flow_m": 53.7, "bvps": 17.06,
    },
    "Q4 2024": {
        "revenue_m": 405.0, "gross_profit_m": 110.0, "operating_income_m": 0.3,
        "total_equity_m": 270.0, "shares_outstanding_m": 15.6,
        "free_cash_flow_m": 40.0, "bvps": 17.31,
    },
    "Q3 2023": {
        "revenue_m": 250.0, "total_equity_m": 300.0,
    },
}


def test_ingest_metrics_creates_raw_file(tmp_path, monkeypatch):
    monkeypatch.setattr("eca.config.project_root", lambda: tmp_path)
    monkeypatch.setattr(
        "eca.processors.ingest_metrics.fetch_quarterly_metrics",
        lambda ticker: MOCK_QUARTERS,
    )
    result = CliRunner().invoke(cli, ["ingest-metrics", "root"])
    assert result.exit_code == 0
    raw_path = tmp_path / "data" / "root" / "metrics-raw.json"
    assert raw_path.exists()
    raw = json.loads(raw_path.read_text())
    assert raw["ticker"] == "ROOT"
    assert "Q3 2024" in raw["quarters"]


def test_ingest_metrics_updates_existing_facts(tmp_path, monkeypatch):
    monkeypatch.setattr("eca.config.project_root", lambda: tmp_path)
    monkeypatch.setattr(
        "eca.processors.ingest_metrics.fetch_quarterly_metrics",
        lambda ticker: MOCK_QUARTERS,
    )
    qdir = tmp_path / "data" / "root" / "q3-2024"
    qdir.mkdir(parents=True)
    (qdir / "facts.json").write_text(json.dumps({"ticker": "ROOT", "quarter": "Q3 2024"}))
    CliRunner().invoke(cli, ["ingest-metrics", "root"])
    facts = json.loads((qdir / "facts.json").read_text())
    assert facts["metrics"]["revenue_m"] == 387.8
    assert facts["ticker"] == "ROOT"


def test_ingest_metrics_adds_equity_declining_flag(tmp_path, monkeypatch):
    monkeypatch.setattr("eca.config.project_root", lambda: tmp_path)
    monkeypatch.setattr(
        "eca.processors.ingest_metrics.fetch_quarterly_metrics",
        lambda ticker: MOCK_QUARTERS,
    )
    qdir = tmp_path / "data" / "root" / "q3-2024"
    qdir.mkdir(parents=True)
    (qdir / "facts.json").write_text(json.dumps({"ticker": "ROOT", "quarter": "Q3 2024"}))
    CliRunner().invoke(cli, ["ingest-metrics", "root"])
    facts = json.loads((qdir / "facts.json").read_text())
    assert "equity_declining_yoy" in facts.get("flags", [])
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_ingest_metrics.py -v`
Expected: FAIL

**Step 3: Implement the processor**

```python
"""ingest-metrics processor: fetch financial data from Yahoo Finance."""

from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path

from eca.config import data_dir
from eca.parsers.yfinance_fetcher import fetch_quarterly_metrics
from eca.schema import load_facts, save_facts


def _quarter_slug(quarter_label: str) -> str:
    parts = quarter_label.strip().split()
    return f"{parts[0].lower()}-{parts[1]}"


def _find_yoy_quarter(quarter_label: str, all_quarters: dict) -> str | None:
    match = re.match(r"(Q\d)\s+(\d{4})", quarter_label)
    if not match:
        return None
    q, year = match.group(1), int(match.group(2))
    prior = f"{q} {year - 1}"
    return prior if prior in all_quarters else None


def ingest_metrics(ticker: str) -> Path:
    ticker_upper = ticker.upper()
    ticker_dir = data_dir() / ticker.lower()
    ticker_dir.mkdir(parents=True, exist_ok=True)

    quarters = fetch_quarterly_metrics(ticker_upper)

    raw_path = ticker_dir / "metrics-raw.json"
    raw = {
        "source": "yfinance",
        "ticker": ticker_upper,
        "fetched_at": date.today().isoformat(),
        "quarters": quarters,
    }
    raw_path.write_text(json.dumps(raw, indent=2) + "\n")

    for q_label, metrics in quarters.items():
        slug = _quarter_slug(q_label)
        q_dir = ticker_dir / slug
        if not q_dir.exists():
            continue

        facts_path = q_dir / "facts.json"
        facts = load_facts(facts_path)
        facts["metrics"] = {"source": "yfinance", "ingested_at": date.today().isoformat(), **metrics}

        flags = facts.get("flags", [])
        prior_label = _find_yoy_quarter(q_label, quarters)
        if prior_label:
            prior_equity = quarters[prior_label].get("total_equity_m")
            current_equity = metrics.get("total_equity_m")
            if (prior_equity is not None and current_equity is not None
                    and current_equity < prior_equity
                    and "equity_declining_yoy" not in flags):
                flags.append("equity_declining_yoy")
        facts["flags"] = flags
        save_facts(facts_path, facts)

    return raw_path
```

**Step 4: Wire to CLI**

Add to `src/eca/cli.py`:

```python
@cli.command("ingest-metrics")
@click.argument("ticker")
def ingest_metrics_cmd(ticker: str):
    """Fetch quarterly financial metrics from Yahoo Finance."""
    from eca.processors.ingest_metrics import ingest_metrics
    click.echo(f"Fetching metrics for {ticker.upper()} from Yahoo Finance...")
    raw_path = ingest_metrics(ticker)
    click.echo(f"Wrote metrics -> {raw_path}")
```

**Step 5: Run tests to verify they pass**

Run: `pytest tests/test_ingest_metrics.py -v`
Expected: 3 passed

**Step 6: Commit**

```bash
git add src/eca/processors/ingest_metrics.py src/eca/cli.py tests/test_ingest_metrics.py
git commit -m "feat: add ingest-metrics command with yfinance fetcher"
```

---

### Task 7: Analysis Markdown Grade Parser

**Files:**
- Create: `tests/test_grade_parser.py`
- Create: `src/eca/parsers/grades.py`

Used by both the migration script (Task 8) and the analyze command (Task 9).

**Step 1: Write failing tests**

```python
from eca.parsers.grades import parse_grades

SAMPLE_ROOT = """# Earnings Call Candor Analysis
## Company: Root, Inc. | Quarter: Q3 2025 | Date: November 4, 2025

### Executive Summary
Some text here.

### 1. Capital Stewardship & Financial Candor
**Grade: C**

Some analysis.

### 2. Strategic Clarity & Accountability
**Grade: C+**

Some analysis.

### 3. Stakeholder Balance & Culture Signals
**Grade: C-**

Some analysis.

### 4. FOG Index -- Linguistic Quality of Disclosure
**Grade: C**

Some analysis.

### 5. Vision, Leadership & Long-Term Orientation
**Grade: C**

Some analysis.

---

### Composite Grade: C
**Calculation:** (C [2.0] x 0.25) + (C+ [2.3] x 0.25) + (C- [1.7] x 0.15) + (C [2.0] x 0.20) + (C [2.0] x 0.15) = **2.03** -> C
"""

SAMPLE_LMND = """### 1. Capital Stewardship & Financial Candor
**Grade: B+**

### 2. Strategic Clarity & Accountability
**Grade: A**

### 3. Stakeholder Balance & Culture Signals
**Grade: B**

### 4. FOG Index -- Linguistic Quality of Disclosure
**Grade: B**

### 5. Vision, Leadership & Long-Term Orientation
**Grade: B**

---

### Composite Grade: B
**Calculation:** (B+ [3.3] x 0.25) + (A [4.0] x 0.25) + (B [3.0] x 0.15) + (B [3.0] x 0.20) + (B [3.0] x 0.15) = **3.325** -> B
"""

SAMPLE_SPOT = """### Composite Grade: B
**Calculation:** (B 3.0 x 0.25) + (B 3.0 x 0.25) + (B- 2.7 x 0.15) + (C+ 2.3 x 0.20) + (B 3.0 x 0.15) = 2.815 -> B
"""


def test_parse_dimension_grades():
    result = parse_grades(SAMPLE_ROOT)
    assert result["dim1_grade"] == "C"
    assert result["dim2_grade"] == "C+"
    assert result["dim3_grade"] == "C-"
    assert result["dim4_grade"] == "C"
    assert result["dim5_grade"] == "C"


def test_parse_composite():
    result = parse_grades(SAMPLE_ROOT)
    assert result["composite_grade"] == "C"
    assert result["composite_score"] == 2.03


def test_parse_lmnd_grades():
    result = parse_grades(SAMPLE_LMND)
    assert result["dim1_grade"] == "B+"
    assert result["dim2_grade"] == "A"
    assert result["composite_grade"] == "B"
    assert result["composite_score"] == 3.325


def test_parse_spot_score_format():
    """Score without bold markers, arrow format varies."""
    result = parse_grades(SAMPLE_SPOT)
    assert result["composite_grade"] == "B"
    assert result["composite_score"] == 2.815


def test_parse_header_metadata():
    result = parse_grades(SAMPLE_ROOT)
    assert result["company"] == "Root, Inc."
    assert result["quarter"] == "Q3 2025"
    assert result["call_date"] == "November 4, 2025"
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_grade_parser.py -v`
Expected: FAIL

**Step 3: Implement the parser**

```python
"""Parse grades and metadata from analysis markdown files."""

from __future__ import annotations

import re


def parse_grades(text: str) -> dict:
    """Extract dimension grades, composite grade/score, and header metadata."""
    result = {}

    # Header: ## Company: Name | Quarter: Q3 2025 | Date: November 4, 2025
    header = re.search(
        r"##\s+Company:\s*(.+?)\s*\|\s*Quarter:\s*(.+?)\s*\|\s*Date:\s*(.+)",
        text,
    )
    if header:
        result["company"] = header.group(1).strip()
        result["quarter"] = header.group(2).strip()
        result["call_date"] = header.group(3).strip()

    # Dimension grades: **Grade: X** after ### N. heading
    dim_pattern = re.compile(
        r"###\s+(\d)\.\s+.*?\n\*\*Grade:\s*([A-F][+-]?)\*\*", re.DOTALL
    )
    for match in dim_pattern.finditer(text):
        result[f"dim{match.group(1)}_grade"] = match.group(2)

    # Composite grade: ### Composite Grade: X
    comp = re.search(r"###\s+Composite Grade:\s*([A-F][+-]?)", text)
    if comp:
        result["composite_grade"] = comp.group(1)

    # Composite score: look for the numeric result before the arrow
    # Handles both "= **2.03** -> C" and "= 2.815 -> B" formats
    score = re.search(r"=\s*\**(\d+\.?\d*)\**\s*[-→>]", text)
    if score:
        result["composite_score"] = float(score.group(1))

    return result
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_grade_parser.py -v`
Expected: 5 passed

**Step 5: Commit**

```bash
git add src/eca/parsers/grades.py tests/test_grade_parser.py
git commit -m "feat: add analysis markdown grade parser"
```

---

### Task 8: Migration Script

**Files:**
- Create: `tests/test_migration.py`
- Create: `src/eca/processors/migrate.py`
- Modify: `src/eca/cli.py`

**Step 1: Write failing tests**

```python
import json
from pathlib import Path
from click.testing import CliRunner

from eca.cli import cli
from eca.processors.migrate import discover_files, migrate

SAMPLE_ANALYSIS = """# Earnings Call Candor Analysis
## Company: Root, Inc. | Quarter: Q1 2025 | Date: May 6, 2025

### 1. Capital Stewardship & Financial Candor
**Grade: C+**

### 2. Strategic Clarity & Accountability
**Grade: B-**

### 3. Stakeholder Balance & Culture Signals
**Grade: C**

### 4. FOG Index -- Linguistic Quality of Disclosure
**Grade: C+**

### 5. Vision, Leadership & Long-Term Orientation
**Grade: C+**

---

### Composite Grade: C
**Calculation:** (C+ [2.3] x 0.25) + (B- [2.7] x 0.25) + (C [2.0] x 0.15) + (C+ [2.3] x 0.20) + (C+ [2.3] x 0.15) = **2.355** -> C
"""


def _setup_old_layout(root: Path):
    """Create old-style directory layout for testing."""
    # Regular transcript
    t = root / "transcripts" / "root" / "2025"
    t.mkdir(parents=True)
    (t / "q1.txt").write_text("Transcript Q1")
    # Irregular: q4-2024 transcript in 2025/ directory
    (t / "q4-2024.txt").write_text("Transcript Q4 2024")

    # Regular analysis
    a = root / "analyses" / "root" / "2025"
    a.mkdir(parents=True)
    (a / "q1.md").write_text(SAMPLE_ANALYSIS)
    # Irregular: analysis at root level (not in year subdir)
    (root / "analyses" / "root" / "q4-2024.md").write_text(
        SAMPLE_ANALYSIS.replace("Q1 2025", "Q4 2024").replace("May 6, 2025", "February 12, 2025")
    )

    # Skills
    (root / "SKILL.md").write_text("Base skill content")
    (root / "SKILL-insurtech.md").write_text("Insurtech supplement")


def test_discover_finds_all_files(tmp_path):
    _setup_old_layout(tmp_path)
    files = discover_files(tmp_path)
    slugs = {f["quarter_slug"] for f in files}
    assert "q1-2025" in slugs
    assert "q4-2024" in slugs


def test_migrate_creates_new_layout(tmp_path, monkeypatch):
    monkeypatch.setattr("eca.config.project_root", lambda: tmp_path)
    _setup_old_layout(tmp_path)
    migrate(tmp_path)

    assert (tmp_path / "data" / "root" / "q1-2025" / "transcript.txt").exists()
    assert (tmp_path / "data" / "root" / "q4-2024" / "transcript.txt").exists()
    assert (tmp_path / "data" / "root" / "q1-2025" / "analysis.md").exists()


def test_migrate_generates_facts(tmp_path, monkeypatch):
    monkeypatch.setattr("eca.config.project_root", lambda: tmp_path)
    _setup_old_layout(tmp_path)
    migrate(tmp_path)

    facts = json.loads(
        (tmp_path / "data" / "root" / "q1-2025" / "facts.json").read_text()
    )
    assert facts["ticker"] == "ROOT"
    assert facts["candor"]["dim1_grade"] == "C+"
    assert facts["candor"]["composite_grade"] == "C"


def test_migrate_moves_skills(tmp_path, monkeypatch):
    monkeypatch.setattr("eca.config.project_root", lambda: tmp_path)
    _setup_old_layout(tmp_path)
    migrate(tmp_path)

    assert (tmp_path / "skills" / "base.md").exists()
    assert (tmp_path / "skills" / "insurtech.md").exists()
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_migration.py -v`
Expected: FAIL

**Step 3: Implement migration**

```python
"""Migration: restructure old layout to new data/ layout."""

from __future__ import annotations

import re
import shutil
from pathlib import Path

from eca.parsers.grades import parse_grades
from eca.schema import load_facts, save_facts


def _path_to_quarter_slug(path: Path) -> str | None:
    """Extract quarter slug from old-layout file path.

    Handles:
      transcripts/root/2025/q1.txt -> q1-2025
      transcripts/root/2025/q4-2024.txt -> q4-2024
      analyses/root/q4-2024.md -> q4-2024
    """
    stem = path.stem
    if re.match(r"q\d-\d{4}", stem):
        return stem

    # Check immediate parent directory name for a year
    parent_name = path.parent.name
    year_match = re.match(r"\d{4}$", parent_name)
    quarter_match = re.match(r"(q\d)", stem)
    if year_match and quarter_match:
        return f"{quarter_match.group(1)}-{parent_name}"

    return None


def discover_files(project_root: Path) -> list[dict]:
    """Discover all transcripts and analyses in the old layout."""
    entries: dict[tuple[str, str], dict] = {}

    transcripts_dir = project_root / "transcripts"
    if transcripts_dir.exists():
        for txt_path in transcripts_dir.rglob("*.txt"):
            ticker = txt_path.parts[len(transcripts_dir.parts)].upper()
            slug = _path_to_quarter_slug(txt_path)
            if slug:
                key = (ticker, slug)
                entries.setdefault(key, {"ticker": ticker, "quarter_slug": slug})
                entries[key]["transcript_path"] = txt_path

    analyses_dir = project_root / "analyses"
    if analyses_dir.exists():
        for md_path in analyses_dir.rglob("*.md"):
            ticker = md_path.parts[len(analyses_dir.parts)].upper()
            slug = _path_to_quarter_slug(md_path)
            if slug:
                key = (ticker, slug)
                entries.setdefault(key, {"ticker": ticker, "quarter_slug": slug})
                entries[key]["analysis_path"] = md_path

    return list(entries.values())


def migrate(project_root: Path) -> None:
    """Migrate old layout to new data/ layout."""
    entries = discover_files(project_root)
    data_root = project_root / "data"

    for entry in entries:
        ticker = entry["ticker"].lower()
        slug = entry["quarter_slug"]
        target_dir = data_root / ticker / slug
        target_dir.mkdir(parents=True, exist_ok=True)

        if "transcript_path" in entry:
            shutil.copy2(entry["transcript_path"], target_dir / "transcript.txt")

        if "analysis_path" in entry:
            analysis_path = entry["analysis_path"]
            shutil.copy2(analysis_path, target_dir / "analysis.md")

            grades = parse_grades(analysis_path.read_text())

            facts_path = target_dir / "facts.json"
            facts = load_facts(facts_path)
            facts["ticker"] = entry["ticker"]

            parts = slug.split("-")
            facts["quarter"] = f"{parts[0].upper()} {parts[1]}"

            for key in ("company", "call_date"):
                if key in grades:
                    facts[key] = grades[key]

            candor = {}
            for key in ("dim1_grade", "dim2_grade", "dim3_grade", "dim4_grade",
                        "dim5_grade", "composite_score", "composite_grade"):
                if key in grades:
                    candor[key] = grades[key]
            if candor:
                facts["candor"] = candor

            save_facts(facts_path, facts)

    # Copy skill files
    skills_dir = project_root / "skills"
    skills_dir.mkdir(exist_ok=True)
    for src_name, dst_name in [("SKILL.md", "base.md"), ("SKILL-insurtech.md", "insurtech.md")]:
        src = project_root / src_name
        if src.exists():
            shutil.copy2(src, skills_dir / dst_name)
```

**Step 4: Wire to CLI**

Add to `src/eca/cli.py`:

```python
@cli.command("migrate")
@click.option("--dry-run", is_flag=True, help="Show what would be migrated")
def migrate_cmd(dry_run: bool):
    """Migrate old directory layout to new data/ layout."""
    from eca.config import project_root
    from eca.processors.migrate import discover_files, migrate

    root = project_root()
    if dry_run:
        entries = discover_files(root)
        for entry in entries:
            click.echo(f"  {entry['ticker']} {entry['quarter_slug']}")
        click.echo(f"\n{len(entries)} quarters to migrate")
        return

    migrate(root)
    click.echo("Migration complete.")
```

**Step 5: Run tests to verify they pass**

Run: `pytest tests/test_migration.py -v`
Expected: 4 passed

**Step 6: Commit**

```bash
git add src/eca/processors/migrate.py src/eca/cli.py tests/test_migration.py
git commit -m "feat: add migration script for old-to-new layout"
```

---

### Task 9: analyze Command

**Files:**
- Create: `tests/test_analyze.py`
- Create: `src/eca/processors/analyze.py`
- Modify: `src/eca/cli.py`

**Step 1: Write failing tests**

```python
import json
from pathlib import Path

from eca.processors.analyze import (
    build_system_prompt,
    build_user_message,
    extract_and_update_facts,
)

MOCK_OUTPUT = """# Earnings Call Candor Analysis
## Company: Root, Inc. | Quarter: Q3 2025 | Date: November 4, 2025

### 1. Capital Stewardship & Financial Candor
**Grade: C**

### 2. Strategic Clarity & Accountability
**Grade: C+**

### 3. Stakeholder Balance & Culture Signals
**Grade: C-**

### 4. FOG Index -- Linguistic Quality of Disclosure
**Grade: C**

### 5. Vision, Leadership & Long-Term Orientation
**Grade: C**

---

### Composite Grade: C
**Calculation:** (C [2.0] x 0.25) + (C+ [2.3] x 0.25) + (C- [1.7] x 0.15) + (C [2.0] x 0.20) + (C [2.0] x 0.15) = **2.03** -> C
"""


def test_build_system_prompt_base_only(tmp_path):
    skills = tmp_path / "skills"
    skills.mkdir()
    (skills / "base.md").write_text("Base instructions.")

    prompt = build_system_prompt(skills, "base")
    assert "Base instructions." in prompt


def test_build_system_prompt_with_supplement(tmp_path):
    skills = tmp_path / "skills"
    skills.mkdir()
    (skills / "base.md").write_text("Base.")
    (skills / "insurtech.md").write_text("Insurtech supplement.")

    prompt = build_system_prompt(skills, "insurtech")
    assert "Base." in prompt
    assert "Insurtech supplement." in prompt


def test_build_user_message_without_metrics():
    msg = build_user_message("Transcript text.", None)
    assert msg == "Transcript text."


def test_build_user_message_with_metrics():
    metrics = {"revenue_m": 387.8, "operating_income_m": -5.0}
    msg = build_user_message("Transcript.", metrics)
    assert "Financial ground truth" in msg
    assert "387.8" in msg
    assert "Transcript." in msg


def test_extract_and_update_facts(tmp_path):
    facts_path = tmp_path / "facts.json"
    facts_path.write_text(json.dumps({"ticker": "ROOT", "quarter": "Q3 2025"}))

    extract_and_update_facts(facts_path, MOCK_OUTPUT, "base+insurtech")

    facts = json.loads(facts_path.read_text())
    assert facts["candor"]["dim1_grade"] == "C"
    assert facts["candor"]["composite_grade"] == "C"
    assert facts["candor"]["composite_score"] == 2.03
    assert facts["candor"]["skill_version"] == "base+insurtech"
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_analyze.py -v`
Expected: FAIL

**Step 3: Implement the processor**

```python
"""analyze processor: run Rittenhouse candor analysis via Anthropic API."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from eca.parsers.grades import parse_grades
from eca.schema import load_facts, save_facts


def build_system_prompt(skills_dir: Path, sector: str) -> str:
    """Construct system prompt from base skill + optional sector supplement."""
    base = (skills_dir / "base.md").read_text()
    if sector != "base":
        supplement = skills_dir / f"{sector}.md"
        if supplement.exists():
            return f"{base}\n\n---\n\n{supplement.read_text()}"
    return base


def build_user_message(transcript: str, metrics: dict | None) -> str:
    """Construct user message with optional metrics context injection."""
    if not metrics:
        return transcript

    dollar_millions = {
        "revenue_m": "Revenue",
        "gross_profit_m": "Gross Profit",
        "operating_income_m": "GAAP Operating Income",
        "free_cash_flow_m": "Free Cash Flow",
        "operating_cash_flow_m": "Operating Cash Flow",
        "cash_and_equivalents_m": "Cash & Equivalents",
        "total_equity_m": "Total Equity",
    }
    other_fields = {
        "shares_outstanding_m": ("Shares Outstanding", "{val}M"),
        "bvps": ("Book Value Per Share", "${val}"),
    }

    parts = ["Financial ground truth for verification:"]
    for field, label in dollar_millions.items():
        val = metrics.get(field)
        if val is not None:
            parts.append(f"- {label}: ${val}M")
    for field, (label, fmt) in other_fields.items():
        val = metrics.get(field)
        if val is not None:
            parts.append(f"- {label}: {fmt.replace('{val}', str(val))}")

    parts.append("\nUse these figures to verify management's claims and flag discrepancies.")
    return "\n".join(parts) + "\n\n---\n\n" + transcript


def run_analysis(
    system_prompt: str,
    user_message: str,
    model: str = "claude-sonnet-4-20250514",
) -> str:
    """Call Anthropic API to produce the candor analysis."""
    import anthropic

    client = anthropic.Anthropic()
    message = client.messages.create(
        model=model,
        max_tokens=8192,
        system=system_prompt,
        messages=[{"role": "user", "content": user_message}],
    )
    return message.content[0].text


def extract_and_update_facts(
    facts_path: Path,
    analysis_text: str,
    skill_version: str,
) -> None:
    """Parse grades from analysis output and update facts.json."""
    facts = load_facts(facts_path)
    grades = parse_grades(analysis_text)

    candor = {
        "analyzed_at": date.today().isoformat(),
        "skill_version": skill_version,
    }
    for key in ("dim1_grade", "dim2_grade", "dim3_grade", "dim4_grade",
                "dim5_grade", "composite_score", "composite_grade"):
        if key in grades:
            candor[key] = grades[key]

    facts["candor"] = candor
    save_facts(facts_path, facts)
```

**Step 4: Wire to CLI**

Add to `src/eca/cli.py`:

```python
@cli.command("analyze")
@click.argument("ticker")
@click.argument("quarter", required=False)
@click.option("--all", "analyze_all", is_flag=True, help="Analyze all quarters missing analysis")
@click.option("--model", default="claude-sonnet-4-20250514", help="Anthropic model to use")
def analyze_cmd(ticker: str, quarter: str | None, analyze_all: bool, model: str):
    """Run Rittenhouse candor analysis via Anthropic API."""
    from eca.config import data_dir, skills_dir, get_sector, quarter_dir
    from eca.processors.analyze import (
        build_system_prompt, build_user_message, run_analysis, extract_and_update_facts,
    )
    from eca.schema import load_facts

    ticker_upper = ticker.upper()
    sector = get_sector(ticker_upper)
    skill_version = f"base+{sector}" if sector != "base" else "base"
    system_prompt = build_system_prompt(skills_dir(), sector)

    if analyze_all:
        ticker_path = data_dir() / ticker.lower()
        if not ticker_path.exists():
            raise click.UsageError(f"No data directory for {ticker_upper}. Run ingest-transcript first.")
        quarters_to_analyze = [
            d.name for d in sorted(ticker_path.iterdir())
            if d.is_dir() and not (d / "analysis.md").exists()
        ]
    elif quarter:
        quarters_to_analyze = [quarter]
    else:
        raise click.UsageError("Provide a quarter or use --all")

    for q in quarters_to_analyze:
        q_dir = quarter_dir(ticker_upper, q)
        transcript_path = q_dir / "transcript.txt"
        if not transcript_path.exists():
            click.echo(f"Skipping {q}: no transcript.txt")
            continue

        click.echo(f"Analyzing {ticker_upper} {q}...")
        transcript = transcript_path.read_text()

        facts = load_facts(q_dir / "facts.json")
        metrics = facts.get("metrics")
        user_message = build_user_message(transcript, metrics)

        analysis = run_analysis(system_prompt, user_message, model=model)

        (q_dir / "analysis.md").write_text(analysis)
        extract_and_update_facts(q_dir / "facts.json", analysis, skill_version)
        click.echo(f"  -> {q_dir / 'analysis.md'}")
```

**Step 5: Run tests to verify they pass**

Run: `pytest tests/test_analyze.py -v`
Expected: 5 passed

**Step 6: Commit**

```bash
git add src/eca/processors/analyze.py src/eca/cli.py tests/test_analyze.py
git commit -m "feat: add analyze command with Anthropic API integration"
```

---

### Task 10: query Command

**Files:**
- Create: `tests/test_query.py`
- Create: `src/eca/processors/query.py`
- Modify: `src/eca/cli.py`

**Step 1: Write failing tests**

```python
import json
from pathlib import Path

from eca.processors.query import load_all_facts, query_grades, query_flags


def _create_facts(root: Path, ticker: str, quarter: str, facts: dict):
    d = root / "data" / ticker.lower() / quarter
    d.mkdir(parents=True)
    (d / "facts.json").write_text(json.dumps(facts))


def test_load_all_facts(tmp_path, monkeypatch):
    monkeypatch.setattr("eca.config.project_root", lambda: tmp_path)
    _create_facts(tmp_path, "ROOT", "q1-2025", {"ticker": "ROOT", "quarter": "Q1 2025"})
    _create_facts(tmp_path, "ROOT", "q2-2025", {"ticker": "ROOT", "quarter": "Q2 2025"})
    _create_facts(tmp_path, "LMND", "q1-2025", {"ticker": "LMND", "quarter": "Q1 2025"})

    all_facts = load_all_facts()
    assert len(all_facts) == 3


def test_query_grades(tmp_path, monkeypatch):
    monkeypatch.setattr("eca.config.project_root", lambda: tmp_path)
    _create_facts(tmp_path, "ROOT", "q1-2025", {
        "ticker": "ROOT", "quarter": "Q1 2025",
        "candor": {"dim1_grade": "C+", "composite_grade": "C", "composite_score": 2.355},
    })
    _create_facts(tmp_path, "ROOT", "q2-2025", {
        "ticker": "ROOT", "quarter": "Q2 2025",
        "candor": {"dim1_grade": "C+", "composite_grade": "C", "composite_score": 2.31},
    })

    result = query_grades("ROOT")
    assert len(result) == 2
    assert result[0]["quarter"] == "Q1 2025"
    assert result[0]["composite_grade"] == "C"


def test_query_flags(tmp_path, monkeypatch):
    monkeypatch.setattr("eca.config.project_root", lambda: tmp_path)
    _create_facts(tmp_path, "ROOT", "q1-2025", {
        "ticker": "ROOT", "quarter": "Q1 2025", "flags": ["bvps_absent", "roe_absent"],
    })
    _create_facts(tmp_path, "ROOT", "q2-2025", {
        "ticker": "ROOT", "quarter": "Q2 2025", "flags": ["bvps_absent"],
    })
    _create_facts(tmp_path, "LMND", "q1-2025", {
        "ticker": "LMND", "quarter": "Q1 2025", "flags": [],
    })

    result = query_flags("bvps_absent")
    assert len(result) == 2
    assert all(r["ticker"] == "ROOT" for r in result)


def test_query_grades_unknown_ticker(tmp_path, monkeypatch):
    monkeypatch.setattr("eca.config.project_root", lambda: tmp_path)
    assert query_grades("UNKNOWN") == []
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_query.py -v`
Expected: FAIL

**Step 3: Implement the processor**

```python
"""query processor: read and query across fact files."""

from __future__ import annotations

from eca.config import data_dir
from eca.schema import load_facts


def load_all_facts() -> list[dict]:
    """Load all facts.json files across the data tree."""
    root = data_dir()
    if not root.exists():
        return []
    return [
        facts for facts_path in sorted(root.rglob("facts.json"))
        if (facts := load_facts(facts_path))
    ]


def query_grades(ticker: str) -> list[dict]:
    """Return grade summaries for a ticker, sorted by quarter."""
    ticker_upper = ticker.upper()
    results = []
    for facts in load_all_facts():
        if facts.get("ticker") != ticker_upper:
            continue
        candor = facts.get("candor", {})
        if not candor:
            continue
        results.append({"ticker": ticker_upper, "quarter": facts.get("quarter", ""), **candor})
    results.sort(key=lambda r: r.get("quarter", ""))
    return results


def query_flags(flag: str) -> list[dict]:
    """Return all quarters that have a specific flag."""
    return [
        {"ticker": f.get("ticker"), "quarter": f.get("quarter"), "flags": f.get("flags", [])}
        for f in load_all_facts()
        if flag in f.get("flags", [])
    ]


def format_grades_table(grades: list[dict]) -> str:
    """Format grades as a readable table."""
    if not grades:
        return "No grades found."
    lines = [
        f"{'Quarter':<12} {'Dim1':<5} {'Dim2':<5} {'Dim3':<5} {'Dim4':<5} {'Dim5':<5} {'Comp':<5} {'Score'}"
    ]
    lines.append("-" * 60)
    for g in grades:
        lines.append(
            f"{g.get('quarter', ''):<12} "
            f"{g.get('dim1_grade', '-'):<5} "
            f"{g.get('dim2_grade', '-'):<5} "
            f"{g.get('dim3_grade', '-'):<5} "
            f"{g.get('dim4_grade', '-'):<5} "
            f"{g.get('dim5_grade', '-'):<5} "
            f"{g.get('composite_grade', '-'):<5} "
            f"{g.get('composite_score', '-')}"
        )
    return "\n".join(lines)
```

**Step 4: Wire to CLI**

Add to `src/eca/cli.py`:

```python
@cli.command("query")
@click.argument("query_text")
@click.option("--ticker", help="Filter by ticker")
def query_cmd(query_text: str, ticker: str | None):
    """Query across the data tree."""
    from eca.processors.query import query_grades, query_flags, format_grades_table, load_all_facts

    lowered = query_text.lower()

    # Structured: grades
    if "grades" in lowered or "grade" in lowered:
        target = ticker or query_text.split()[-1].upper()
        click.echo(format_grades_table(query_grades(target)))
        return

    # Structured: flags
    if "flag" in lowered:
        for word in query_text.split():
            if "_" in word:
                for r in query_flags(word):
                    click.echo(f"  {r['ticker']} {r['quarter']}: {', '.join(r['flags'])}")
                return

    # Fallback: natural language query via Claude
    import json
    from eca.processors.analyze import run_analysis

    all_facts = load_all_facts()
    if not all_facts:
        click.echo("No data found.")
        return

    context = json.dumps(all_facts, indent=2)
    system = "You are a financial data analyst. Answer questions based on the provided earnings call analysis data. Be concise."
    answer = run_analysis(system, f"Data:\n{context}\n\nQuestion: {query_text}")
    click.echo(answer)
```

**Step 5: Run tests to verify they pass**

Run: `pytest tests/test_query.py -v`
Expected: 4 passed

**Step 6: Run full test suite**

Run: `pytest tests/ -v`
Expected: All tests pass (40 tests)

**Step 7: Commit**

```bash
git add src/eca/processors/query.py src/eca/cli.py tests/test_query.py
git commit -m "feat: add query command for cross-data analysis"
```
