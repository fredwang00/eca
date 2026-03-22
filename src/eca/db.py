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

_CANDOR_FIELDS = [
    "dim1_grade", "dim2_grade", "dim3_grade", "dim4_grade", "dim5_grade",
    "composite_grade", "composite_score", "skill_version", "analyzed_at",
]

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

    # Full rebuild: clear everything first
    conn.execute("DELETE FROM quarter_flags")
    conn.execute("DELETE FROM quarter_facts")
    conn.execute("DELETE FROM sector_map")

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

    for sector, tickers in WATCHLIST_SECTORS.items():
        for ticker in tickers:
            conn.execute(
                "INSERT OR REPLACE INTO sector_map (ticker, sector) VALUES (?, ?)",
                (ticker, sector),
            )

    conn.commit()
    conn.close()


def _insert_quarter(conn: sqlite3.Connection, ticker: str, quarter: str, facts: dict) -> None:
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

    for flag in facts.get("flags", []):
        conn.execute(
            "INSERT OR IGNORE INTO quarter_flags (ticker, quarter, flag) VALUES (?, ?, ?)",
            (ticker, quarter, flag),
        )


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
