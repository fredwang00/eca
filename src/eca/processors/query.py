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
