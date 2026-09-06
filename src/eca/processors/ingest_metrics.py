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


def _merge_metric_values(old: dict, new: dict) -> dict:
    """Merge a quarter's metric fields, preferring the fresh fetch but falling
    back to the previously-stored value where the fresh fetch returned None.

    Yahoo Finance's quarterly-financials endpoint only serves a limited
    trailing window, and individual fields (e.g. Basic EPS) can silently come
    back None on a later fetch even for a quarter that previously had a real
    value. Without this, a routine metrics refresh permanently destroys
    historical data.
    """
    merged = dict(old)
    for key, value in new.items():
        if value is not None or key not in merged:
            merged[key] = value
    return merged


def ingest_metrics(ticker: str) -> Path:
    ticker_upper = ticker.upper()
    ticker_dir = data_dir() / ticker.lower()
    ticker_dir.mkdir(parents=True, exist_ok=True)

    quarters = fetch_quarterly_metrics(ticker_upper)

    raw_path = ticker_dir / "metrics-raw.json"
    existing_raw = {}
    if raw_path.exists():
        try:
            existing_raw = json.loads(raw_path.read_text())
        except json.JSONDecodeError:
            existing_raw = {}
    existing_quarters = existing_raw.get("quarters", {})

    merged_quarters = dict(existing_quarters)
    for q_label, metrics in quarters.items():
        merged_quarters[q_label] = _merge_metric_values(existing_quarters.get(q_label, {}), metrics)

    raw = {
        "source": "yfinance",
        "ticker": ticker_upper,
        "fetched_at": date.today().isoformat(),
        "quarters": merged_quarters,
    }
    raw_path.write_text(json.dumps(raw, indent=2) + "\n")

    for q_label, metrics in quarters.items():
        slug = _quarter_slug(q_label)
        q_dir = ticker_dir / slug
        if not q_dir.exists():
            continue

        merged_metrics = merged_quarters[q_label]

        facts_path = q_dir / "facts.json"
        facts = load_facts(facts_path)
        facts["metrics"] = {"source": "yfinance", "ingested_at": date.today().isoformat(), **merged_metrics}

        flags = facts.get("flags", [])
        prior_label = _find_yoy_quarter(q_label, merged_quarters)
        if prior_label:
            prior_equity = merged_quarters[prior_label].get("total_equity_m")
            current_equity = merged_metrics.get("total_equity_m")
            if (prior_equity is not None and current_equity is not None
                    and current_equity < prior_equity
                    and "equity_declining_yoy" not in flags):
                flags.append("equity_declining_yoy")
        facts["flags"] = flags
        save_facts(facts_path, facts)

    return raw_path
