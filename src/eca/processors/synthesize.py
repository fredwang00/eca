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

        quarter_label = facts.get("quarter", q)
        header = f"## {quarter_label} {grade_line}"
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
