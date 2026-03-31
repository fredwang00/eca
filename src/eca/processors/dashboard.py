"""Dashboard processor: renders standing view and generates markdown."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from eca.config import data_dir, quarter_sort_key, WATCHLIST_SECTORS
from eca.db import connect_db, query_grade_trajectory
from eca.engine.waterfall import (
    assess_waterfall,
    phase_x_status,
    regime_label,
    StageResult,
)
from eca.schema import load_facts, SIGNAL_ENUMS


def load_latest_signals() -> dict[str, dict]:
    """Load the most recent quarter's signals per ticker.

    Returns {ticker: facts_dict} for tickers that have signals.
    """
    root = data_dir()
    result = {}
    if not root.exists():
        return result

    for ticker_dir in sorted(root.iterdir()):
        if not ticker_dir.is_dir() or ticker_dir.name == "synthesis":
            continue
        ticker = ticker_dir.name.upper()

        # Find most recent quarter with signals
        quarters = sorted(
            (d for d in ticker_dir.iterdir() if d.is_dir()),
            key=lambda d: quarter_sort_key(d.name),
            reverse=True,
        )
        for q_dir in quarters:
            facts_path = q_dir / "facts.json"
            if not facts_path.exists():
                continue
            facts = load_facts(facts_path)
            if facts.get("signals"):
                result[ticker] = facts
                break

    return result


def render_waterfall_section(stages: list[StageResult]) -> str:
    """Render the 7-stage distress waterfall."""
    lines = ["## Distress Waterfall", ""]
    lines.append("| # | Stage | Status | Triggering Tickers | Count |")
    lines.append("|---|-------|--------|--------------------|-------|")
    for i, s in enumerate(stages, 1):
        status = "FIRING" if s.firing else "NOT FIRING"
        tickers = ", ".join(s.triggered_by) if s.triggered_by else "-"
        lines.append(f"| {i} | {s.label} | {status} | {tickers} | {s.count} |")
    return "\n".join(lines)


def render_phase_x_section(is_px: bool, stages_firing: int, total: int) -> str:
    """Render the Phase X assessment."""
    label = regime_label(stages_firing, is_px)
    lines = [
        "## Phase X Assessment",
        "",
        f"- **Stages firing:** {stages_firing}/{total}",
        f"- **Regime:** {label}",
    ]
    if is_px:
        lines.append("- **STATUS: PHASE X ACTIVE**")
    return "\n".join(lines)


def render_score_trajectories(db_path: Path) -> str:
    """Render score trajectories grouped by sector."""
    conn = connect_db(db_path)
    lines = ["## Score Trajectories", ""]

    for sector, tickers in WATCHLIST_SECTORS.items():
        rows = query_grade_trajectory(conn, tickers)
        if not rows:
            continue

        lines.append(f"### {sector}")
        lines.append("")
        lines.append("| Ticker | Quarter | Score | Grade |")
        lines.append("|--------|---------|-------|-------|")

        # Group by ticker, show last 4 quarters
        by_ticker: dict[str, list] = {}
        for r in rows:
            by_ticker.setdefault(r["ticker"], []).append(r)

        for ticker in tickers:
            t_rows = by_ticker.get(ticker, [])
            recent = t_rows[-4:] if len(t_rows) > 4 else t_rows
            for r in recent:
                score = r["composite_score"]
                score_str = f"{score:.2f}" if score is not None else "-"
                grade = r["composite_grade"] or "-"
                lines.append(f"| {r['ticker']} | {r['quarter']} | {score_str} | {grade} |")

            if len(recent) >= 2:
                scores = [r["composite_score"] for r in recent if r["composite_score"] is not None]
                if len(scores) >= 2:
                    trend = "^" if scores[-1] > scores[0] else ("v" if scores[-1] < scores[0] else "=")
                    avg = sum(scores) / len(scores)
                    lines.append(f"| {ticker} | *trend* | {avg:.2f} | {trend} |")

        lines.append("")

    conn.close()
    return "\n".join(lines)


def render_capex_landscape(db_path: Path) -> str:
    """Render capex data for infrastructure/AI tickers."""
    from eca.db import query_sector_financials

    conn = connect_db(db_path)
    capex_tickers = ["NVDA", "MSFT", "GOOG", "META", "AMZN", "AAPL", "TSLA",
                     "IREN", "CIFR", "WULF", "RKLB"]

    lines = ["## Capex Landscape", ""]
    lines.append("| Ticker | Total Capex ($M) | Quarters |")
    lines.append("|--------|-----------------|----------|")

    rows = query_sector_financials(conn, capex_tickers)
    mag4_total = 0.0
    mag4_quarters = 0
    for r in sorted(rows, key=lambda x: -(x.get("total_capex") or 0)):
        capex = r.get("total_capex")
        if capex is None:
            continue
        capex_str = f"{capex:,.0f}"
        lines.append(f"| {r['ticker']} | {capex_str} | {r['quarter_count']} |")
        if r["ticker"] in ("MSFT", "GOOG", "META", "AMZN"):
            mag4_total += capex
            mag4_quarters = max(mag4_quarters, r["quarter_count"])

    if mag4_total > 0:
        lines.append("")
        lines.append(f"**Mag 4 aggregate capex:** ${mag4_total:,.0f}M across {mag4_quarters} quarter(s)")

    conn.close()
    return "\n".join(lines)


def render_market_context() -> str:
    """Render the manually-updated market context section."""
    return """## Market Context (external -- update manually)

| Signal | Value | Last Updated | Source |
|--------|-------|-------------|--------|
| HY OAS | ___ | ___ | ICE BofA US High Yield Index |
| Fed Funds | ___ | ___ | FRED |
| VIX | ___ | ___ | CBOE |
| 10Y Yield | ___ | ___ | FRED |"""


def render_signal_detail(facts_by_ticker: dict) -> str:
    """Render per-ticker signal values with evidence."""
    lines = ["## Signal Detail", ""]

    for ticker in sorted(facts_by_ticker):
        signals = facts_by_ticker[ticker].get("signals", {})
        if not signals:
            continue

        evidence = signals.get("signal_evidence", {})
        non_neutral = []
        for field in SIGNAL_ENUMS:
            val = signals.get(field)
            if val is None:
                continue
            # Check if non-neutral (severity > 0)
            values = SIGNAL_ENUMS[field]
            if val in values and values.index(val) > 0:
                ev = evidence.get(field, "")
                non_neutral.append((field, val, ev))

        if not non_neutral:
            continue

        lines.append(f"### {ticker}")
        lines.append("")
        lines.append("| Signal | Value | Evidence |")
        lines.append("|--------|-------|----------|")
        for field, val, ev in non_neutral:
            ev_safe = ev.replace("|", "\\|")
            ev_short = ev_safe[:80] + "..." if len(ev_safe) > 80 else ev_safe
            lines.append(f"| {field} | {val} | {ev_short} |")
        lines.append("")

    return "\n".join(lines)


def render_dashboard(db_path: Path) -> str:
    """Render the full standing-view dashboard markdown (no LLM call)."""
    facts_by_ticker = load_latest_signals()
    stages = assess_waterfall(facts_by_ticker)
    is_px, firing, total = phase_x_status(stages)

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")

    sections = [
        "# Consumer Health Dashboard",
        f"*Generated: {timestamp}*",
        "",
        render_waterfall_section(stages),
        "",
        render_phase_x_section(is_px, firing, total),
        "",
        render_score_trajectories(db_path),
        "",
        render_capex_landscape(db_path),
        "",
        render_market_context(),
        "",
        render_signal_detail(facts_by_ticker),
    ]

    return "\n".join(sections)
