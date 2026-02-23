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
