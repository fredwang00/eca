"""Evidence-first ask: a deterministic evidence packet precedes any LLM call.

The packet separates source-backed facts, compatible (or clearly labeled
non-comparable) totals, and unknowns/excluded evidence. The LLM — when used
at all — receives only the question and this packet, and its output is
interpretation, explicitly separated from facts.
"""

from __future__ import annotations

import sqlite3
from typing import Any

from eca.claims import is_primary_source
from eca.retrieval import (
    REASON_NON_PRIMARY,
    aggregate_claims,
    find_claims,
    format_claim,
    resolve_current,
)

SYNTHESIS_SYSTEM_PROMPT = """You answer investor questions strictly from the supplied evidence packet.

Rules:
- Use ONLY facts present in the packet. Never introduce outside knowledge, \
estimates, or numbers you compute beyond simple sums the packet already \
labels as compatible.
- Never treat a vendor estimate, agent extrapolation, or scenario as \
management guidance; they are displayed but excluded from primary-source totals.
- Never sum across different CapEx definitions or currencies; the packet's \
subtotals are the only totals you may state.
- Report unknowns as unknown. Missing disclosure is not zero.
- Structure your answer in four sections: "1. Source-backed facts", \
"2. Totals", "3. Unknowns and excluded evidence", "4. Interpretation". \
Section 4 must clearly separate interpretation from facts and must flag \
every material unknown.
Output markdown only."""


def _unknown_reason(ticker: str, claims_for_period: list[dict], current_ids: set[str]) -> str:
    """Why a ticker is unknown for a topic-period (never 'zero')."""
    ticker_claims = [c for c in claims_for_period if c["ticker"] == ticker]
    if not ticker_claims:
        return "no_disclosure_found"
    if any(c["id"] in current_ids for c in ticker_claims):
        return "no_comparable_guidance"
    if any(is_primary_source(c["claim_type"]) for c in ticker_claims):
        return "no_current_guidance"
    return "no_primary_source_disclosure"


def build_evidence_packet(
    conn: sqlite3.Connection,
    question: str,
    *,
    topics: tuple[str, ...] | list[str] = ("capex",),
    periods: list[str] | None = None,
    tickers: list[str] | None = None,
    sector: str | None = None,
    as_of: str | None = None,
    policy: str = "strict",
    primary_only: bool = False,
) -> dict[str, Any]:
    """Retrieve claims and aggregate them deterministically into a packet."""
    from eca.config import WATCHLIST_SECTORS

    if tickers is not None:
        scope_tickers: set[str] | None = {t.upper() for t in tickers}
    elif sector is not None:
        if sector not in WATCHLIST_SECTORS:
            raise ValueError(f"Unknown sector {sector!r}")
        scope_tickers = set(WATCHLIST_SECTORS[sector])
    else:
        scope_tickers = None

    topic_periods: list[dict[str, Any]] = []
    all_warnings: list[str] = []
    all_excluded: list[dict] = []

    per_topic_claims: dict[str, list[dict]] = {}
    for topic in topics:
        topic_claims = find_claims(
            conn, topic=topic, tickers=tickers, sector=sector, as_of=as_of,
        )
        if topic_claims:
            per_topic_claims[topic] = topic_claims
    if scope_tickers is None:
        scope_tickers = {
            c["ticker"] for claims in per_topic_claims.values() for c in claims
        }

    for topic, topic_claims in per_topic_claims.items():
        topic_periods_for_topic = periods
        if topic_periods_for_topic is None:
            topic_periods_for_topic = sorted({c["period"] for c in topic_claims})

        for period in topic_periods_for_topic:
            claims_tp = [c for c in topic_claims if c["period"] == period]
            if not claims_tp:
                continue

            primary = [c for c in claims_tp if is_primary_source(c["claim_type"])]
            non_primary = [c for c in claims_tp if not is_primary_source(c["claim_type"])]

            resolution = resolve_current(primary, as_of)
            evidence = resolution["current"]
            all_excluded.extend(resolution["excluded"])
            if not primary_only:
                for claim in non_primary:
                    all_excluded.append({
                        "claim_id": claim["id"],
                        "ticker": claim["ticker"],
                        "reason": REASON_NON_PRIMARY,
                        "detail": f"{claim['claim_type']}: displayed as evidence, "
                                  "excluded from primary-source totals",
                    })

            aggregation = None
            coverage: dict[str, Any]
            if topic == "capex":
                capex_claims = [c for c in primary if c["metric"] == "capital_expenditure"]
                expected = sorted(scope_tickers) if scope_tickers is not None else None
                aggregation = aggregate_claims(
                    capex_claims, as_of=as_of, policy=policy, expected_tickers=expected,
                )
                all_warnings.extend(aggregation["warnings"])
                all_excluded.extend(aggregation["excluded"])
                current_ids = {c["id"] for c in evidence}
                covered = aggregation["covered_tickers"]
                unknown = []
                expected_set = scope_tickers if scope_tickers is not None else set(covered)
                for ticker in sorted(expected_set - set(covered)):
                    unknown.append({
                        "ticker": ticker,
                        "reason": _unknown_reason(ticker, claims_tp, current_ids),
                    })
                coverage = {"covered": covered, "unknown": unknown}
            else:
                current_ids = {c["id"] for c in evidence}
                covered = sorted({c["ticker"] for c in evidence})
                unknown = []
                expected_set = scope_tickers if scope_tickers is not None else set(covered)
                for ticker in sorted(expected_set - set(covered)):
                    unknown.append({
                        "ticker": ticker,
                        "reason": _unknown_reason(ticker, claims_tp, current_ids),
                    })
                coverage = {"covered": covered, "unknown": unknown}

            topic_periods.append({
                "topic": topic,
                "period": period,
                "evidence": evidence,
                "non_primary_evidence": [] if primary_only else non_primary,
                "aggregation": aggregation,
                "coverage": coverage,
            })

    # Deduplicate exclusion entries (a claim can be excluded once per view).
    seen_excluded: set[tuple] = set()
    deduped: list[dict] = []
    for entry in all_excluded:
        key = (entry["claim_id"], entry["reason"])
        if key not in seen_excluded:
            seen_excluded.add(key)
            deduped.append(entry)

    return {
        "question": question,
        "as_of": as_of,
        "policy": policy,
        "primary_sources_only": primary_only,
        "tickers": sorted(scope_tickers) if scope_tickers is not None else [],
        "topics": list(topics),
        "topic_periods": topic_periods,
        "excluded": deduped,
        "warnings": sorted(set(all_warnings)),
    }


def render_packet(packet: dict[str, Any]) -> str:
    """Render the deterministic sections (1-3) of the answer."""
    lines: list[str] = ["# Evidence packet", ""]
    lines.append(f"Question: {packet['question']}")
    lines.append(f"As of: {packet['as_of'] if packet['as_of'] else 'unspecified (latest available)'}")
    lines.append(f"Policy: {packet['policy']}")
    if packet["primary_sources_only"]:
        lines.append("Scope: primary sources only (management statements and reported actuals)")
    lines.append("")

    # Section 1 — source-backed facts
    lines.append("## 1. Source-backed facts")
    lines.append("")
    for tp in packet["topic_periods"]:
        lines.append(f"### {tp['topic']} — {tp['period']}")
        lines.append("")
        if tp["evidence"]:
            for claim in tp["evidence"]:
                lines.append(format_claim(claim))
                lines.append("")
        else:
            lines.append("No current primary-source claims for this topic and period.")
            lines.append("")
        if tp["non_primary_evidence"]:
            lines.append("Non-primary evidence (displayed; excluded from primary-source totals):")
            lines.append("")
            for claim in tp["non_primary_evidence"]:
                label = claim["claim_type"].replace("_", " ")
                rendered = format_claim(claim)
                lines.append(f"[{label.upper()}] {rendered}")
                lines.append("")

    # Section 2 — totals
    lines.append("## 2. Totals")
    lines.append("")
    totals_emitted = False
    for tp in packet["topic_periods"]:
        agg = tp["aggregation"]
        if agg is None:
            continue
        totals_emitted = True
        label = f"{tp['topic']} — {tp['period']}"
        if not agg["subtotals"]:
            lines.append(f"- {label}: no compatible total (see unknowns and warnings below)")
            continue
        for subtotal in agg["subtotals"]:
            definition = subtotal["definition"] or "unspecified definition"
            tickers = ", ".join(subtotal["tickers"])
            lines.append(
                f"- {label} [{definition}]: ${subtotal['low_m']}M-${subtotal['high_m']}M "
                f"(companies: {tickers})"
            )
        if agg["comparability"] == "mixed_definitions":
            lines.append(f"  - {label}: mixed CapEx definitions — no combined strict total")
        elif agg["comparability"] == "non_comparable_disclosed":
            lines.append(f"  - {label}: disclosed subtotal labeled NON-COMPARABLE "
                         f"(definitions: {', '.join(agg['definitions'])})")
    if not totals_emitted:
        lines.append("No totals computed for the requested topics.")
    lines.append("")

    # Section 3 — unknowns and excluded evidence
    lines.append("## 3. Unknowns and excluded evidence")
    lines.append("")
    for tp in packet["topic_periods"]:
        unknown = tp["coverage"]["unknown"]
        if unknown:
            listed = ", ".join(f"{u['ticker']} ({u['reason']})" for u in unknown)
            lines.append(f"- {tp['topic']} — {tp['period']}: no comparable disclosure for {listed}")
    for entry in packet["excluded"]:
        detail = f"; {entry['detail']}" if entry.get("detail") else ""
        lines.append(f"- {entry['ticker']} {entry['claim_id']}: {entry['reason']}{detail}")
    if not packet["excluded"] and not any(
        tp["coverage"]["unknown"] for tp in packet["topic_periods"]
    ):
        lines.append("None.")
    lines.append("")

    if packet["warnings"]:
        lines.append("Warnings:")
        for warning in packet["warnings"]:
            lines.append(f"- {warning}")
        lines.append("")

    lines.append("(Section 4, Interpretation, is generated separately from this packet "
                 "and is never mixed into the facts above.)")
    return "\n".join(lines)
