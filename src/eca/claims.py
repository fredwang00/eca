"""Typed claim model and validation for citation-backed claims.

A claim is a structured, source-backed statement curated from a primary
transcript (or, for vendor estimates, another cited document). ``facts.json``
is the canonical structured record; the SQLite index is derived from it and
owns no claim data.

Semantics (see root CLAUDE.md):
- Claim amounts are positive spend magnitudes in integer millions of the
  claim currency. The cash-flow statement sign is not stored here.
- Ranges use ``value_low_m``/``value_high_m``; point values use equal
  low/high. ``value_high_m`` may be null for open-ended guidance
  ("more than $X"), which excludes a claim from subtotals rather than
  inventing an upper bound.
- Directional claims (``management_directional``) never carry numeric
  values or durations.
- Durations use explicit month fields; currency fields are never overloaded.
- Unknown metadata stays null; nothing is guessed.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

# --- Controlled vocabularies -------------------------------------------------

CLAIM_TYPES = [
    "reported_actual",
    "management_guidance",
    "management_directional",
    "vendor_estimate",
    "agent_extrapolation",
    "scenario",
]

# Reserved in the schema for future ingestion; using it fails validation so a
# curator cannot silently treat consensus as primary evidence.
RESERVED_CLAIM_TYPES = ["analyst_consensus"]

# Management statements and reported actuals are primary-source evidence.
# Vendor estimates, extrapolations, and scenarios are not.
PRIMARY_SOURCE_TYPES = [
    "reported_actual",
    "management_guidance",
    "management_directional",
]

TOPICS = ["capex", "funding", "return"]

CAPEX_DEFINITIONS = [
    "cash_capex",
    "purchases_of_property_and_equipment",
    "capex_including_finance_lease_principal",
    "capex_including_leases",
    "company_defined_capex",
    "non_comparable_or_unspecified",
]

CURRENCIES = ["USD"]
UNITS = ["USD_millions"]

DIRECTIONS = ["increase", "decrease", "stable"]

SOURCE_SECTIONS = [
    "prepared_remarks",
    "qa",
    "guidance",
    "press_release",
    "research_note",
    "other",
]

TOPIC_METRICS: dict[str, list[str]] = {
    "capex": [
        "capital_expenditure",
    ],
    "funding": [
        "operating_cash_flow",
        "debt_issuance",
        "lease_funding",
        "joint_venture_funding",
        "supplier_participation",
        "borrowing_capacity",
        "cash_balance",
    ],
    "return": [
        "payback_period",
        "monetization_lag",
        "useful_life",
        "contracted_demand",
        "hurdle_rate",
        "qualitative_return",
    ],
}

# Metrics expressed in months rather than currency amounts.
DURATION_METRICS = {"payback_period", "monetization_lag", "useful_life"}

CLAIM_FIELDS = frozenset({
    "id", "topic", "metric", "claim_type", "period",
    "value_low_m", "value_high_m", "currency", "unit",
    "capex_definition", "duration_low_months", "duration_high_months",
    "direction", "speaker", "source_document", "source_path",
    "source_section", "line_start", "line_end", "quote",
    "as_of", "supersedes_id", "notes",
})

REQUIRED_FIELDS = (
    "id", "topic", "metric", "claim_type", "period", "quote",
    "source_document", "source_path", "source_section",
    "line_start", "line_end", "as_of",
)

PERIOD_RE = re.compile(r"^(CY|FY)(\d{4})(?:Q([1-4]))?$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class ClaimValidationError(Exception):
    """Raised with the exact artifact path so malformed claims fail loudly."""

    def __init__(self, message: str, *, facts_path: Path | str, claim_id: str | None = None):
        self.facts_path = Path(facts_path)
        self.claim_id = claim_id
        prefix = str(self.facts_path)
        if claim_id:
            prefix = f"{prefix} (claim {claim_id})"
        super().__init__(f"{prefix}: {message}")


def is_primary_source(claim_type: str | None) -> bool:
    """Management statements and reported actuals are primary-source evidence."""
    return claim_type in PRIMARY_SOURCE_TYPES


def validate_period_label(label: Any) -> tuple[str, int, int | None]:
    """Validate a normalized period label such as ``CY2026`` or ``FY2027Q2``.

    Returns (kind, year, quarter). Fiscal labels are never treated as
    calendar years; the caller decides comparability, not the label parser.
    """
    match = PERIOD_RE.match(label) if isinstance(label, str) else None
    if match is None:
        raise ValueError(
            f"Invalid period label {label!r}. Expected a normalized label "
            "such as CY2026, FY2027, CY2026Q2, or FY2027Q2."
        )
    kind = match.group(1)
    year = int(match.group(2))
    quarter = int(match.group(3)) if match.group(3) else None
    return kind, year, quarter


def _is_int_like(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _collapse(text: str) -> str:
    return " ".join(text.split())


def validate_claim(claim: Any, *, source_root: Path, facts_path: Path) -> None:
    """Validate one claim record, raising ClaimValidationError on any problem.

    ``source_root`` is the project root; claim ``source_path`` values are
    resolved against it so citations always point inside the repository.
    """
    if not isinstance(claim, dict):
        raise ClaimValidationError("claim must be a JSON object", facts_path=facts_path)

    claim_id = claim.get("id") if isinstance(claim.get("id"), str) else None

    def fail(message: str) -> ClaimValidationError:
        return ClaimValidationError(message, facts_path=facts_path, claim_id=claim_id)

    unknown = set(claim) - CLAIM_FIELDS
    if unknown:
        raise fail(f"unknown field(s): {', '.join(sorted(unknown))}")
    missing = [f for f in REQUIRED_FIELDS if f not in claim or claim[f] is None]
    if missing:
        raise fail(f"missing required field(s): {', '.join(missing)}")

    if not isinstance(claim["id"], str) or not claim["id"].strip():
        raise fail("id must be a non-empty string")
    claim_id = claim["id"]

    topic = claim["topic"]
    if topic not in TOPICS:
        raise fail(f"topic {topic!r} not in {TOPICS}")
    metric = claim["metric"]
    if metric not in TOPIC_METRICS[topic]:
        raise fail(f"metric {metric!r} not valid for topic {topic!r} "
                   f"(allowed: {TOPIC_METRICS[topic]})")

    claim_type = claim["claim_type"]
    if claim_type in RESERVED_CLAIM_TYPES:
        raise fail("claim_type 'analyst_consensus' is reserved in the schema and "
                   "is not ingested in this milestone")
    if claim_type not in CLAIM_TYPES:
        raise fail(f"claim_type {claim_type!r} not in {CLAIM_TYPES}")

    try:
        validate_period_label(claim["period"])
    except ValueError as e:
        raise fail(str(e))

    if not isinstance(claim["as_of"], str) or not DATE_RE.match(claim["as_of"]):
        raise fail("as_of must be an ISO date string (YYYY-MM-DD)")

    source_section = claim["source_section"]
    if source_section not in SOURCE_SECTIONS:
        raise fail(f"source_section {source_section!r} not in {SOURCE_SECTIONS}")

    for field in ("speaker", "notes", "source_document"):
        value = claim.get(field)
        if value is not None and (not isinstance(value, str) or not value.strip()):
            raise fail(f"{field} must be a non-empty string or null")

    supersedes = claim.get("supersedes_id")
    if supersedes is not None:
        if not isinstance(supersedes, str) or not supersedes.strip():
            raise fail("supersedes_id must be a non-empty string or null")
        if supersedes == claim_id:
            raise fail("claim cannot supersede itself")

    # --- citation integrity --------------------------------------------------
    quote = claim["quote"]
    if not isinstance(quote, str) or not quote.strip():
        raise fail("quote must be a non-empty string")

    line_start, line_end = claim["line_start"], claim["line_end"]
    if not _is_int_like(line_start) or not _is_int_like(line_end):
        raise fail("line_start and line_end must be integers")
    if line_start < 1 or line_end < line_start:
        raise fail(f"invalid line range {line_start}-{line_end}")

    source_path_str = claim["source_path"]
    if not isinstance(source_path_str, str) or not source_path_str.strip():
        raise fail("source_path must be a non-empty string relative to the project root")
    source_path = source_root / source_path_str
    if not source_path.is_file():
        raise fail(f"source transcript missing: {source_path}")
    lines = source_path.read_text(encoding="utf-8").splitlines()
    if line_end > len(lines):
        raise fail(f"line range {line_start}-{line_end} outside source file "
                   f"{source_path} (file has {len(lines)} lines)")
    range_text = _collapse(" ".join(lines[line_start - 1:line_end]))
    if _collapse(quote) not in range_text:
        raise fail(f"quote not found in {source_path} lines {line_start}-{line_end}")

    # --- values, units, and durations ----------------------------------------
    low, high = claim.get("value_low_m"), claim.get("value_high_m")
    dur_low, dur_high = claim.get("duration_low_months"), claim.get("duration_high_months")
    currency, unit = claim.get("currency"), claim.get("unit")
    has_value = low is not None or high is not None
    has_duration = dur_low is not None or dur_high is not None

    for name, value in (("value_low_m", low), ("value_high_m", high),
                        ("duration_low_months", dur_low), ("duration_high_months", dur_high)):
        if value is not None and not _is_int_like(value):
            raise fail(f"{name} must be an integer (millions / months), got {value!r}")

    if claim_type == "management_directional" and (has_value or has_duration):
        raise fail("directional claims must not carry numeric values or durations; "
                   "curate them as a separate quantitative claim if the source supports it")

    if has_value:
        if low is None:
            raise fail("value_high_m without value_low_m; anchor ranges at the low end")
        if low < 0:
            raise fail("claim amounts are positive spend magnitudes; "
                       f"got value_low_m={low}")
        if high is not None and high < low:
            raise fail(f"inverted range: value_low_m={low} > value_high_m={high}")
        if currency is None or currency not in CURRENCIES:
            raise fail(f"quantitative claims require currency in {CURRENCIES}")
        if unit is None or unit not in UNITS:
            raise fail(f"quantitative claims require unit in {UNITS}")
    else:
        if currency is not None or unit is not None:
            raise fail("currency/unit set on a claim without a numeric value")
        if high is not None:
            raise fail("value_high_m without value_low_m")

    if has_duration:
        if metric not in DURATION_METRICS:
            raise fail(f"durations only apply to {sorted(DURATION_METRICS)}, "
                       f"not metric {metric!r}")
        for name, value in (("duration_low_months", dur_low), ("duration_high_months", dur_high)):
            if value is not None and value <= 0:
                raise fail(f"{name} must be a positive number of months")
        if dur_low is not None and dur_high is not None and dur_low > dur_high:
            raise fail(f"inverted duration range: {dur_low} > {dur_high} months")
        if currency is not None:
            raise fail("durations use month fields; currency must stay null")

    definition = claim.get("capex_definition")
    if definition is not None:
        if topic != "capex" or metric != "capital_expenditure":
            raise fail("capex_definition only applies to capex/capital_expenditure claims")
        if definition not in CAPEX_DEFINITIONS:
            raise fail(f"capex_definition {definition!r} not in {CAPEX_DEFINITIONS}")
    elif topic == "capex" and metric == "capital_expenditure" and has_value:
        raise fail("quantitative CapEx claims require capex_definition")

    direction = claim.get("direction")
    if direction is not None and direction not in DIRECTIONS:
        raise fail(f"direction {direction!r} not in {DIRECTIONS}")


def validate_claim_references(items: list[tuple[dict, Path]]) -> None:
    """Cross-document checks: duplicate IDs and dangling supersedes_id.

    ``items`` is a list of (claim, facts_path) pairs across the whole tree.
    """
    seen: dict[str, Path] = {}
    for claim, facts_path in items:
        claim_id = claim["id"]
        if claim_id in seen:
            raise ClaimValidationError(
                f"duplicate claim id {claim_id!r}; first seen in {seen[claim_id]}",
                facts_path=facts_path,
                claim_id=claim_id,
            )
        seen[claim_id] = Path(facts_path)

    all_ids = set(seen)
    for claim, facts_path in items:
        target = claim.get("supersedes_id")
        if target is not None and target not in all_ids:
            raise ClaimValidationError(
                f"supersedes_id {target!r} does not match any indexed claim",
                facts_path=facts_path,
                claim_id=claim["id"],
            )


def validate_claims_in_facts(facts: dict, *, source_root: Path, facts_path: Path) -> list[dict]:
    """Validate the ``claims`` array of a facts.json document.

    Returns the claim list (possibly empty). Raises ClaimValidationError with
    the artifact path on the first problem; claims are never silently dropped.
    """
    claims = facts.get("claims")
    if claims is None:
        return []
    if not isinstance(claims, list):
        raise ClaimValidationError("'claims' must be a JSON array", facts_path=facts_path)
    for claim in claims:
        validate_claim(claim, source_root=source_root, facts_path=facts_path)
    ids = [c.get("id") for c in claims if isinstance(c, dict)]
    dupes = {i for i in ids if ids.count(i) > 1}
    if dupes:
        raise ClaimValidationError(
            f"duplicate claim id(s) within document: {', '.join(sorted(str(d) for d in dupes))}",
            facts_path=facts_path,
        )
    return claims
