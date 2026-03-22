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


def build_user_message(
    transcript: str,
    metrics: dict | None,
    prior_analysis: str | None = None,
) -> str:
    """Construct user message with optional metrics and prior analysis context."""
    sections: list[str] = []

    if prior_analysis:
        sections.append(
            "Prior quarter analysis (use for cross-quarter comparison — "
            "look for evolution in candor, specificity, and accountability; "
            "flag stasis or regression):\n\n"
            + prior_analysis
        )

    if metrics:
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
        parts.append(
            "\nUse these figures to verify management's claims and flag discrepancies."
        )
        sections.append("\n".join(parts))

    sections.append(transcript)
    return "\n\n---\n\n".join(sections)


def find_prior_analysis(ticker: str, current_quarter: str) -> str | None:
    """Find the most recent analysis.md before current_quarter.

    Quarter slugs are sorted lexically (e.g., q1-2025, q2-2025, q3-2025).
    Returns the analysis text or None.
    """
    from eca.config import data_dir

    ticker_dir = data_dir() / ticker.lower()
    if not ticker_dir.exists():
        return None

    quarters = sorted(
        d.name for d in ticker_dir.iterdir()
        if d.is_dir() and (d / "analysis.md").exists()
    )

    prior = [q for q in quarters if q < current_quarter]
    if not prior:
        return None

    return (ticker_dir / prior[-1] / "analysis.md").read_text()


def run_analysis(
    system_prompt: str,
    user_message: str,
    model: str = "claude-sonnet-4-5",
) -> str:
    """Call LLM API to produce the candor analysis.

    Supports two modes:
    - Hendrix gateway (Spotify): set ECA_API_KEY and optionally ECA_BASE_URL
    - Direct Anthropic: set ANTHROPIC_API_KEY
    """
    import os

    api_key = os.environ.get("ECA_API_KEY")
    base_url = os.environ.get("ECA_BASE_URL", "https://hendrix-genai.spotify.net/taskforce/anthropic/v1")

    if api_key:
        # Hendrix gateway -- OpenAI-compatible endpoint with custom apikey header
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
        return response.choices[0].message.content
    else:
        # Direct Anthropic SDK -- uses ANTHROPIC_API_KEY env var
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
