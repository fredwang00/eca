"""Deterministic claim retrieval, supersession resolution, and aggregation.

Everything in this module is pure with respect to its inputs: the same claim
rows and parameters always produce the same answer, with no LLM involvement.
Missing information stays missing — a company without guidance is never
treated as zero, and incompatible claims are never silently totaled.
"""

from __future__ import annotations

import sqlite3
from typing import Any

from eca.claims import PRIMARY_SOURCE_TYPES

# Exclusion reasons surfaced in aggregation results.
REASON_AFTER_AS_OF = "after_as_of"
REASON_SUPERSEDED = "superseded"
REASON_NOT_CURRENT = "not_current"
REASON_CONFLICT = "conflicting_current_guidance"
REASON_NO_VALUE = "no_numeric_value"
REASON_OPEN_ENDED = "open_ended_range"
REASON_CURRENCY = "currency_mismatch"
REASON_NON_PRIMARY = "non_primary_source"


def _excluded(claim: dict, reason: str, detail: str | None = None) -> dict:
    entry = {
        "claim_id": claim["id"],
        "ticker": claim["ticker"],
        "reason": reason,
    }
    if detail:
        entry["detail"] = detail
    return entry


def find_claims(
    conn: sqlite3.Connection,
    *,
    text: str | None = None,
    topic: str | None = None,
    tickers: list[str] | None = None,
    sector: str | None = None,
    period: str | None = None,
    claim_types: list[str] | None = None,
    definition: str | None = None,
    as_of: str | None = None,
    primary_only: bool = False,
) -> list[dict]:
    """Deterministic claim retrieval with complete records as output.

    Filters are combined with AND. ``as_of`` keeps claims known on or before
    the date; ``primary_only`` restricts to management statements and
    reported actuals (never vendor estimates or extrapolations).
    """
    from eca.config import WATCHLIST_SECTORS

    where: list[str] = []
    params: list[Any] = []

    if text:
        where.append("(quote LIKE ? OR notes LIKE ? OR metric LIKE ? OR topic LIKE ? OR id LIKE ?)")
        like = f"%{text}%"
        params.extend([like, like, like, like, like])
    if topic:
        where.append("topic = ?")
        params.append(topic)
    if period:
        where.append("period = ?")
        params.append(period)
    if definition:
        where.append("capex_definition = ?")
        params.append(definition)
    if as_of:
        where.append("as_of <= ?")
        params.append(as_of)
    if primary_only:
        where.append(f"claim_type IN ({','.join('?' * len(PRIMARY_SOURCE_TYPES))})")
        params.extend(PRIMARY_SOURCE_TYPES)
    if claim_types:
        where.append(f"claim_type IN ({','.join('?' * len(claim_types))})")
        params.extend(claim_types)

    resolved_tickers: list[str] | None = None
    if sector:
        if sector not in WATCHLIST_SECTORS:
            raise ValueError(f"Unknown sector {sector!r}")
        resolved_tickers = list(WATCHLIST_SECTORS[sector])
    if tickers:
        # explicit tickers replace the sector list when both are given
        resolved_tickers = [t.upper() for t in tickers]
    if resolved_tickers:
        where.append(f"ticker IN ({','.join('?' * len(resolved_tickers))})")
        params.extend(resolved_tickers)

    sql = "SELECT * FROM claims"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY ticker, period, as_of, id"
    return [dict(row) for row in conn.execute(sql, params).fetchall()]


def _group_key(claim: dict) -> tuple[str, str, str, str]:
    return (claim["ticker"], claim["topic"], claim["metric"], claim["period"])


def resolve_current(claims: list[dict], as_of: str | None = None) -> dict:
    """Resolve supersession and recency for each (ticker, topic, metric, period).

    Returns {"current": [...], "excluded": [{"claim_id", "ticker", "reason"}]}.

    Rules, in order:
    - Claims dated after ``as_of`` are not eligible yet.
    - A claim superseded by an *eligible* claim is history (reason
      ``superseded``). If the superseding claim is dated after ``as_of``, the
      older claim is still current as of that date.
    - Among the remaining claims for a group, the latest ``as_of`` is current.
      Older, non-superseded claims stay queryable history (``not_current``).
    - Two or more non-superseded claims tied at the latest ``as_of`` are a
      conflict: the company is excluded from totals until one claim
      supersedes the other.
    """
    excluded: list[dict] = []
    eligible: list[dict] = []
    for claim in claims:
        if as_of is not None and claim["as_of"] > as_of:
            excluded.append(_excluded(claim, REASON_AFTER_AS_OF))
        else:
            eligible.append(claim)

    superseded_by: dict[str, str] = {}
    for claim in eligible:
        target = claim.get("supersedes_id")
        if target:
            superseded_by[target] = claim["id"]

    remaining: list[dict] = []
    for claim in eligible:
        if claim["id"] in superseded_by:
            excluded.append(_excluded(claim, REASON_SUPERSEDED,
                                       detail=f"superseded by {superseded_by[claim['id']]}"))
        else:
            remaining.append(claim)

    current: list[dict] = []
    groups: dict[tuple, list[dict]] = {}
    for claim in remaining:
        groups.setdefault(_group_key(claim), []).append(claim)

    for group in groups.values():
        if len(group) == 1:
            current.append(group[0])
            continue
        latest = max(c["as_of"] for c in group)
        top = [c for c in group if c["as_of"] == latest]
        if len(top) == 1:
            current.append(top[0])
            for claim in group:
                if claim is not top[0]:
                    excluded.append(_excluded(claim, REASON_NOT_CURRENT,
                                               detail=f"older guidance retained as history"))
        else:
            for claim in group:
                excluded.append(_excluded(
                    claim, REASON_CONFLICT,
                    detail="multiple current claims for the same company and period; "
                           "declare supersedes_id to resolve",
                ))

    current.sort(key=lambda c: (c["ticker"], c["period"], c["as_of"], c["id"]))
    return {"current": current, "excluded": excluded}


def aggregate_claims(
    claims: list[dict],
    *,
    as_of: str | None = None,
    policy: str = "strict",
    expected_tickers: list[str] | None = None,
) -> dict:
    """Compatibility-aware aggregation for one topic/metric/period question.

    Strict policy (default): only claims sharing one CapEx definition are
    totaled; mixed definitions yield per-definition subtotals plus a warning —
    never a silent combined total. Broad policy: a disclosed subtotal across
    definitions is computed but labeled non-comparable with every definition
    listed.

    A missing company is reported in ``missing_tickers``; it is never summed
    as zero.
    """
    if policy not in ("strict", "broad"):
        raise ValueError(f"policy must be 'strict' or 'broad', got {policy!r}")

    scopes = {_group_key(c)[1:] for c in claims}  # (topic, metric, period)
    if len(scopes) > 1:
        raise ValueError(
            "aggregate_claims handles one topic/metric/period at a time; "
            f"got {sorted(scopes)}"
        )

    warnings: list[str] = []
    resolution = resolve_current(claims, as_of)
    excluded: list[dict] = list(resolution["excluded"])
    current = resolution["current"]

    # Directional and qualitative claims are evidence, never subtotals.
    quantitative: list[dict] = []
    for claim in current:
        if claim.get("value_low_m") is None:
            excluded.append(_excluded(claim, REASON_NO_VALUE,
                                       detail="directional or qualitative claim"))
        else:
            quantitative.append(claim)

    # Open-ended guidance ("more than $X") has no inventable ceiling.
    bounded: list[dict] = []
    for claim in quantitative:
        if claim.get("value_high_m") is None:
            excluded.append(_excluded(claim, REASON_OPEN_ENDED,
                                       detail="no disclosed upper bound"))
        else:
            bounded.append(claim)
    if len(bounded) != len(quantitative):
        warnings.append(
            "open_ended_range: guidance without an upper bound is displayed "
            "as evidence but excluded from subtotals"
        )

    # Currency mismatches prevent aggregation; keep the plurality currency
    # (ties broken alphabetically for determinism).
    by_currency: dict[str, list[dict]] = {}
    for claim in bounded:
        by_currency.setdefault(claim.get("currency") or "USD", []).append(claim)
    if len(by_currency) > 1:
        primary = sorted(by_currency.items(), key=lambda kv: (-len(kv[1]), kv[0]))[0][0]
        for currency, group in by_currency.items():
            if currency != primary:
                for claim in group:
                    excluded.append(_excluded(claim, REASON_CURRENCY,
                                              detail=f"totals computed in {primary}"))
                warnings.append(
                    f"currency_mismatch: claims in {', '.join(sorted(set(by_currency) - {primary}))} "
                    f"excluded; totals computed in {primary}"
                )
        bounded = by_currency[primary]

    definitions = sorted({c["capex_definition"] for c in bounded if c.get("capex_definition")})

    subtotals: list[dict] = []
    total_low: int | None = None
    total_high: int | None = None
    if policy == "strict":
        by_definition: dict[str | None, list[dict]] = {}
        for claim in bounded:
            by_definition.setdefault(claim.get("capex_definition"), []).append(claim)
        for definition in sorted(by_definition, key=lambda d: (d is None, d or "")):
            group = by_definition[definition]
            subtotals.append({
                "definition": definition,
                "low_m": sum(c["value_low_m"] for c in group),
                "high_m": sum(c["value_high_m"] for c in group),
                "claim_ids": [c["id"] for c in group],
                "tickers": sorted({c["ticker"] for c in group}),
            })
        if len(by_definition) > 1:
            comparability = "mixed_definitions"
            total_low = total_high = None
            warnings.append(
                "mixed_definitions: strict policy totals only claims sharing one "
                f"CapEx definition; {len(by_definition)} definitions present "
                f"({', '.join(str(d) for d in definitions)})"
            )
        elif len(by_definition) == 1:
            comparability = "comparable"
            total_low = subtotals[0]["low_m"]
            total_high = subtotals[0]["high_m"]
        else:
            comparability = "no_comparable_claims"
            warnings.append("no_comparable_claims: no eligible quantitative claims")
    else:  # broad
        if bounded:
            total_low = sum(c["value_low_m"] for c in bounded)
            total_high = sum(c["value_high_m"] for c in bounded)
            subtotals.append({
                "definition": "disclosed_mixed" if len(definitions) > 1
                              else (definitions[0] if definitions else None),
                "low_m": total_low,
                "high_m": total_high,
                "claim_ids": [c["id"] for c in bounded],
                "tickers": sorted({c["ticker"] for c in bounded}),
            })
            comparability = "non_comparable_disclosed" if len(definitions) > 1 else "comparable"
            if len(definitions) > 1:
                warnings.append(
                    "broad_disclosed_subtotal: mixes CapEx definitions "
                    f"({', '.join(definitions)}); labeled non-comparable"
                )
        else:
            comparability = "no_comparable_claims"
            warnings.append("no_comparable_claims: no eligible quantitative claims")

    covered = sorted({c["ticker"] for c in bounded})
    missing: list[dict] = []
    if expected_tickers is not None:
        for ticker in sorted(set(expected_tickers) - set(covered)):
            missing.append({"ticker": ticker, "reason": "no_disclosure_found"})

    return {
        "policy": policy,
        "as_of": as_of,
        "subtotals": subtotals,
        "total_low_m": total_low,
        "total_high_m": total_high,
        "included_claim_ids": [c["id"] for c in bounded],
        "excluded": excluded,
        "covered_tickers": covered,
        "missing_tickers": missing,
        "definitions": definitions,
        "comparability": comparability,
        "warnings": warnings,
    }


def format_claim(claim: dict) -> str:
    """Human-readable one-claim-per-line rendering with citation."""
    parts = [f"[{claim['ticker']}] {claim['metric']} {claim['period']}"]
    low, high = claim.get("value_low_m"), claim.get("value_high_m")
    if low is not None:
        if high is None:
            value = f">${low}M"
        elif high == low:
            value = f"${low}M"
        else:
            value = f"${low}M-${high}M"
        parts.append(f"{value} {claim.get('currency') or ''}".strip())
        if high is None:
            parts.append("(open-ended)")
        if claim.get("capex_definition"):
            parts.append(f"({claim['capex_definition']})")
    dur_low, dur_high = claim.get("duration_low_months"), claim.get("duration_high_months")
    if dur_low is not None or dur_high is not None:
        if dur_low is not None and dur_high is not None:
            parts.append(f"{dur_low}-{dur_high} months")
        elif dur_high is not None:
            parts.append(f"up to {dur_high} months")
        else:
            parts.append(f"at least {dur_low} months")
    if claim.get("direction"):
        parts.append(f"direction: {claim['direction']}")
    if low is None and dur_low is None and dur_high is None and not claim.get("direction"):
        parts.append("(qualitative)")
    parts.append(claim["claim_type"])
    parts.append(f"[{claim['id']}]")
    header = " ".join(parts)

    speaker = claim.get("speaker") or "speaker unknown"
    citation = (f"\"{claim['quote']}\" — {speaker}, {claim['source_path']} "
                f"lines {claim['line_start']}-{claim['line_end']}, as of {claim['as_of']}")
    return f"{header}\n  {citation}"
