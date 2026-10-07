"""SQLite index — derived from facts.json for fast aggregation queries.

The database is disposable: it is fully rebuilt from the canonical facts.json
files. Claim rows are validated before any rebuild happens, so malformed
claims abort the rebuild with the exact artifact path instead of being
silently dropped.
"""

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
    capital_expenditure_m REAL, capex_spend_m REAL,
    cash_and_equivalents_m REAL, total_assets_m REAL,
    total_equity_m REAL, shares_outstanding_m REAL,
    bvps REAL, roe_pct REAL,
    combined_ratio_pct REAL, loss_ratio_pct REAL, expense_ratio_pct REAL,
    consumer_stress_tier TEXT, credit_quality_trend TEXT,
    auto_credit_trend TEXT, housing_demand TEXT,
    services_demand TEXT, capex_direction TEXT,
    pricing_power TEXT, management_tone_shift TEXT,
    signals_extracted_at TEXT,
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

CREATE TABLE IF NOT EXISTS claims (
    id TEXT PRIMARY KEY,
    ticker TEXT NOT NULL,
    quarter TEXT NOT NULL,
    topic TEXT NOT NULL,
    metric TEXT NOT NULL,
    claim_type TEXT NOT NULL,
    period TEXT NOT NULL,
    value_low_m INTEGER,
    value_high_m INTEGER,
    currency TEXT,
    unit TEXT,
    capex_definition TEXT,
    duration_low_months INTEGER,
    duration_high_months INTEGER,
    direction TEXT,
    speaker TEXT,
    source_document TEXT,
    source_path TEXT NOT NULL,
    source_section TEXT NOT NULL,
    line_start INTEGER NOT NULL,
    line_end INTEGER NOT NULL,
    quote TEXT NOT NULL,
    as_of TEXT NOT NULL,
    supersedes_id TEXT,
    notes TEXT,
    facts_path TEXT NOT NULL,
    FOREIGN KEY (ticker, quarter) REFERENCES quarter_facts(ticker, quarter)
);

CREATE INDEX IF NOT EXISTS idx_claims_topic_period_ticker ON claims (topic, period, ticker);
CREATE INDEX IF NOT EXISTS idx_claims_metric_type_asof ON claims (metric, claim_type, as_of);
CREATE INDEX IF NOT EXISTS idx_claims_supersedes ON claims (supersedes_id);
"""

_CANDOR_FIELDS = [
    "dim1_grade", "dim2_grade", "dim3_grade", "dim4_grade", "dim5_grade",
    "composite_grade", "composite_score", "skill_version", "analyzed_at",
]

_METRIC_FIELDS = [
    "revenue_m", "gross_profit_m", "operating_income_m", "net_income_m", "eps",
    "free_cash_flow_m", "operating_cash_flow_m", "capital_expenditure_m",
    "capex_spend_m",
    "cash_and_equivalents_m", "total_assets_m", "total_equity_m",
    "shares_outstanding_m", "bvps", "roe_pct",
    "combined_ratio_pct", "loss_ratio_pct", "expense_ratio_pct",
]

_SIGNAL_FIELDS = [
    "consumer_stress_tier", "credit_quality_trend",
    "auto_credit_trend", "housing_demand",
    "services_demand", "capex_direction",
    "pricing_power", "management_tone_shift",
]


def connect_db(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    return conn


def rebuild_index(db_path: Path) -> None:
    """Full rebuild of the SQLite index from facts.json files.

    Claims are validated against the schema and their cited sources before
    any table is touched; malformed claims or duplicate IDs abort the
    rebuild with the offending artifact path.
    """
    from eca.claims import validate_claim_references, validate_claims_in_facts
    from eca.config import data_dir, project_root

    root = project_root()
    data = data_dir()

    quarters: list[tuple[str, str, dict, Path]] = []
    claim_items: list[tuple[dict, Path]] = []
    if data.exists():
        for ticker_dir in sorted(data.iterdir()):
            if not ticker_dir.is_dir() or ticker_dir.name == "synthesis":
                continue
            ticker = ticker_dir.name.upper()
            for quarter_path in sorted(ticker_dir.iterdir()):
                facts_path = quarter_path / "facts.json"
                if not quarter_path.is_dir() or not facts_path.exists():
                    continue
                facts = load_facts(facts_path)
                claims = validate_claims_in_facts(
                    facts, source_root=root, facts_path=facts_path
                )
                quarters.append((ticker, quarter_path.name, facts, facts_path))
                claim_items.extend((claim, facts_path) for claim in claims)

    validate_claim_references(claim_items)

    conn = connect_db(db_path)

    # Drop and recreate to pick up schema changes
    conn.executescript("""
        DROP TABLE IF EXISTS claims;
        DROP TABLE IF EXISTS quarter_flags;
        DROP TABLE IF EXISTS quarter_facts;
        DROP TABLE IF EXISTS sector_map;
    """)
    conn.executescript(SCHEMA_SQL)

    for ticker, quarter, facts, facts_path in quarters:
        _insert_quarter(conn, ticker, quarter, facts)
        _insert_claims(conn, ticker, quarter, facts.get("claims", []), facts_path)

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
    signals = facts.get("signals", {})

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
    for f in _SIGNAL_FIELDS:
        values[f] = signals.get(f)
    values["signals_extracted_at"] = signals.get("extracted_at")

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


_CLAIM_COLUMNS = [
    "id", "ticker", "quarter", "topic", "metric", "claim_type", "period",
    "value_low_m", "value_high_m", "currency", "unit", "capex_definition",
    "duration_low_months", "duration_high_months", "direction", "speaker",
    "source_document", "source_path", "source_section", "line_start", "line_end",
    "quote", "as_of", "supersedes_id", "notes", "facts_path",
]


def _insert_claims(
    conn: sqlite3.Connection,
    ticker: str,
    quarter: str,
    claims: list[dict],
    facts_path: Path,
) -> None:
    """Insert validated claim rows; the index stores fields for deterministic
    filtering and citation rendering but owns no claim data."""
    for claim in claims:
        row = {
            "id": claim["id"],
            "ticker": ticker,
            "quarter": quarter,
            "topic": claim["topic"],
            "metric": claim["metric"],
            "claim_type": claim["claim_type"],
            "period": claim["period"],
            "value_low_m": claim.get("value_low_m"),
            "value_high_m": claim.get("value_high_m"),
            "currency": claim.get("currency"),
            "unit": claim.get("unit"),
            "capex_definition": claim.get("capex_definition"),
            "duration_low_months": claim.get("duration_low_months"),
            "duration_high_months": claim.get("duration_high_months"),
            "direction": claim.get("direction"),
            "speaker": claim.get("speaker"),
            "source_document": claim.get("source_document"),
            "source_path": claim["source_path"],
            "source_section": claim["source_section"],
            "line_start": claim["line_start"],
            "line_end": claim["line_end"],
            "quote": claim["quote"],
            "as_of": claim["as_of"],
            "supersedes_id": claim.get("supersedes_id"),
            "notes": claim.get("notes"),
            "facts_path": str(facts_path),
        }
        cols = ", ".join(_CLAIM_COLUMNS)
        placeholders = ", ".join(["?"] * len(_CLAIM_COLUMNS))
        conn.execute(
            f"INSERT INTO claims ({cols}) VALUES ({placeholders})",
            [row[c] for c in _CLAIM_COLUMNS],
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
