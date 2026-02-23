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
