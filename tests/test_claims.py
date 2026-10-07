"""Unit tests for the typed claim model and validator."""

import json
from pathlib import Path

import pytest

from eca.claims import (
    CAPEX_DEFINITIONS,
    CLAIM_TYPES,
    ClaimValidationError,
    is_primary_source,
    validate_claim,
    validate_claim_references,
    validate_claims_in_facts,
    validate_period_label,
)


def make_source(tmp_path: Path, lines: list[str]) -> Path:
    src = tmp_path / "data" / "goog" / "q2-2026"
    src.mkdir(parents=True)
    (src / "transcript.txt").write_text("\n".join(lines) + "\n")
    return src / "transcript.txt"


def base_claim(source_rel: str = "data/goog/q2-2026/transcript.txt") -> dict:
    return {
        "id": "GOOG-2026Q2-capex-CY2026-001",
        "topic": "capex",
        "metric": "capital_expenditure",
        "claim_type": "management_guidance",
        "period": "CY2026",
        "value_low_m": 195000,
        "value_high_m": 205000,
        "currency": "USD",
        "unit": "USD_millions",
        "capex_definition": "company_defined_capex",
        "duration_low_months": None,
        "duration_high_months": None,
        "direction": None,
        "speaker": "Anat Ashkenazi",
        "source_document": "q2-2026 earnings call",
        "source_path": source_rel,
        "source_section": "prepared_remarks",
        "line_start": 2,
        "line_end": 2,
        "quote": "We are updating our full year 2026 CapEx guidance.",
        "as_of": "2026-07-22",
        "supersedes_id": None,
        "notes": None,
    }


SOURCE_LINES = [
    "Operator: Welcome to the call.",
    "We are updating our full year 2026 CapEx guidance.",
    "That concludes our remarks.",
]


@pytest.fixture
def source_file(tmp_path):
    return make_source(tmp_path, SOURCE_LINES)


@pytest.fixture
def facts_path(tmp_path):
    return tmp_path / "data" / "goog" / "q2-2026" / "facts.json"


def test_valid_claim_passes(tmp_path, source_file, facts_path):
    claim = base_claim()
    validate_claim(claim, source_root=tmp_path, facts_path=facts_path)


def test_period_label_validation():
    assert validate_period_label("CY2026") == ("CY", 2026, None)
    assert validate_period_label("FY2027") == ("FY", 2027, None)
    assert validate_period_label("CY2026Q2") == ("CY", 2026, 2)
    assert validate_period_label("FY2027Q4") == ("FY", 2027, 4)
    for bad in ("2026", "cy2026", "CY26", "CY2026Q5", "Q2-2026", None, "CY2020Q"):
        with pytest.raises(ValueError):
            validate_period_label(bad)


def test_claim_type_enum_enforced(tmp_path, source_file, facts_path):
    claim = base_claim()
    claim["claim_type"] = "analyst_guess"
    with pytest.raises(ClaimValidationError, match="claim_type"):
        validate_claim(claim, source_root=tmp_path, facts_path=facts_path)


def test_reserved_claim_type_rejected(tmp_path, source_file, facts_path):
    claim = base_claim()
    claim["claim_type"] = "analyst_consensus"
    with pytest.raises(ClaimValidationError, match="reserved"):
        validate_claim(claim, source_root=tmp_path, facts_path=facts_path)


def test_topic_metric_vocabulary(tmp_path, source_file, facts_path):
    claim = base_claim()
    claim["metric"] = "payback_period"  # not a capex metric
    with pytest.raises(ClaimValidationError, match="not valid for topic"):
        validate_claim(claim, source_root=tmp_path, facts_path=facts_path)


def test_invalid_period_rejected(tmp_path, source_file, facts_path):
    claim = base_claim()
    claim["period"] = "q2-2026"
    with pytest.raises(ClaimValidationError, match="period label"):
        validate_claim(claim, source_root=tmp_path, facts_path=facts_path)


def test_negative_spend_rejected(tmp_path, source_file, facts_path):
    claim = base_claim()
    claim["value_low_m"] = -44924
    with pytest.raises(ClaimValidationError, match="positive spend"):
        validate_claim(claim, source_root=tmp_path, facts_path=facts_path)


def test_inverted_range_rejected(tmp_path, source_file, facts_path):
    claim = base_claim()
    claim["value_low_m"], claim["value_high_m"] = 205000, 195000
    with pytest.raises(ClaimValidationError, match="inverted range"):
        validate_claim(claim, source_root=tmp_path, facts_path=facts_path)


def test_open_ended_high_allowed(tmp_path, source_file, facts_path):
    claim = base_claim()
    claim["value_high_m"] = None
    validate_claim(claim, source_root=tmp_path, facts_path=facts_path)


def test_high_without_low_rejected(tmp_path, source_file, facts_path):
    claim = base_claim()
    claim["value_low_m"] = None
    with pytest.raises(ClaimValidationError, match="anchor"):
        validate_claim(claim, source_root=tmp_path, facts_path=facts_path)


def test_quantitative_claim_requires_currency_and_unit(tmp_path, source_file, facts_path):
    claim = base_claim()
    claim["currency"] = None
    with pytest.raises(ClaimValidationError, match="currency"):
        validate_claim(claim, source_root=tmp_path, facts_path=facts_path)
    claim = base_claim()
    claim["unit"] = "billions"
    with pytest.raises(ClaimValidationError, match="unit"):
        validate_claim(claim, source_root=tmp_path, facts_path=facts_path)


def test_currency_without_value_rejected(tmp_path, source_file, facts_path):
    claim = base_claim()
    claim["value_low_m"] = None
    claim["value_high_m"] = None
    with pytest.raises(ClaimValidationError, match="without a numeric value"):
        validate_claim(claim, source_root=tmp_path, facts_path=facts_path)


def test_quantitative_capex_requires_definition(tmp_path, source_file, facts_path):
    claim = base_claim()
    claim["capex_definition"] = None
    with pytest.raises(ClaimValidationError, match="capex_definition"):
        validate_claim(claim, source_root=tmp_path, facts_path=facts_path)


def test_capex_definition_vocabulary(tmp_path, source_file, facts_path):
    claim = base_claim()
    claim["capex_definition"] = "capex_including_stuff"
    with pytest.raises(ClaimValidationError, match="capex_definition"):
        validate_claim(claim, source_root=tmp_path, facts_path=facts_path)


def test_definition_rejected_on_non_capex_topic(tmp_path, source_file, facts_path):
    claim = base_claim()
    claim["topic"] = "return"
    claim["metric"] = "payback_period"
    claim["value_low_m"] = claim["value_high_m"] = None
    claim["currency"] = claim["unit"] = None
    claim["duration_low_months"], claim["duration_high_months"] = 24, 36
    claim["capex_definition"] = "cash_capex"
    with pytest.raises(ClaimValidationError, match="only applies to"):
        validate_claim(claim, source_root=tmp_path, facts_path=facts_path)


def test_directional_claims_cannot_carry_values(tmp_path, source_file, facts_path):
    claim = base_claim()
    claim["claim_type"] = "management_directional"
    with pytest.raises(ClaimValidationError, match="directional claims"):
        validate_claim(claim, source_root=tmp_path, facts_path=facts_path)


def test_direction_enum(tmp_path, source_file, facts_path):
    claim = base_claim()
    claim["direction"] = "skyward"
    with pytest.raises(ClaimValidationError, match="direction"):
        validate_claim(claim, source_root=tmp_path, facts_path=facts_path)


def test_duration_validation(tmp_path, source_file, facts_path):
    claim = {
        **base_claim(),
        "topic": "return",
        "metric": "useful_life",
        "value_low_m": None, "value_high_m": None,
        "currency": None, "unit": None, "capex_definition": None,
        "duration_low_months": 60, "duration_high_months": 72,
    }
    validate_claim(claim, source_root=tmp_path, facts_path=facts_path)

    bad = {**claim, "duration_low_months": 72, "duration_high_months": 60}
    with pytest.raises(ClaimValidationError, match="inverted duration"):
        validate_claim(bad, source_root=tmp_path, facts_path=facts_path)

    bad = {**claim, "duration_low_months": 0, "duration_high_months": None}
    with pytest.raises(ClaimValidationError, match="positive number of months"):
        validate_claim(bad, source_root=tmp_path, facts_path=facts_path)

    bad = {**claim, "duration_high_months": None, "duration_low_months": 36,
           "metric": "capital_expenditure", "topic": "capex"}
    with pytest.raises(ClaimValidationError, match="durations only apply"):
        validate_claim(bad, source_root=tmp_path, facts_path=facts_path)


def test_missing_quote_rejected(tmp_path, source_file, facts_path):
    claim = base_claim()
    claim["quote"] = "  "
    with pytest.raises(ClaimValidationError, match="quote"):
        validate_claim(claim, source_root=tmp_path, facts_path=facts_path)


def test_quote_must_appear_in_cited_lines(tmp_path, source_file, facts_path):
    claim = base_claim()
    claim["line_start"] = claim["line_end"] = 3  # quote is on line 2
    with pytest.raises(ClaimValidationError, match="quote not found"):
        validate_claim(claim, source_root=tmp_path, facts_path=facts_path)


def test_quote_whitespace_insensitive(tmp_path, facts_path):
    src = make_source(tmp_path, ["Operator.", "  We are updating our   full year 2026", "CapEx guidance.  ", "End."])
    claim = base_claim()
    claim["line_start"], claim["line_end"] = 2, 3
    validate_claim(claim, source_root=tmp_path, facts_path=facts_path)


def test_line_range_outside_file_rejected(tmp_path, source_file, facts_path):
    claim = base_claim()
    claim["line_start"], claim["line_end"] = 2, 99
    with pytest.raises(ClaimValidationError, match="outside source file"):
        validate_claim(claim, source_root=tmp_path, facts_path=facts_path)


def test_inverted_line_range_rejected(tmp_path, source_file, facts_path):
    claim = base_claim()
    claim["line_start"], claim["line_end"] = 3, 2
    with pytest.raises(ClaimValidationError, match="invalid line range"):
        validate_claim(claim, source_root=tmp_path, facts_path=facts_path)


def test_missing_source_file_rejected(tmp_path, facts_path):
    claim = base_claim("data/goog/q9-2026/transcript.txt")
    with pytest.raises(ClaimValidationError, match="source transcript missing"):
        validate_claim(claim, source_root=tmp_path, facts_path=facts_path)


def test_unknown_field_rejected(tmp_path, source_file, facts_path):
    claim = base_claim()
    claim["value_low"] = 195  # typo of value_low_m
    with pytest.raises(ClaimValidationError, match="unknown field"):
        validate_claim(claim, source_root=tmp_path, facts_path=facts_path)


def test_missing_required_field_rejected(tmp_path, source_file, facts_path):
    claim = base_claim()
    del claim["as_of"]
    with pytest.raises(ClaimValidationError, match="as_of"):
        validate_claim(claim, source_root=tmp_path, facts_path=facts_path)


def test_self_supersession_rejected(tmp_path, source_file, facts_path):
    claim = base_claim()
    claim["supersedes_id"] = claim["id"]
    with pytest.raises(ClaimValidationError, match="supersede itself"):
        validate_claim(claim, source_root=tmp_path, facts_path=facts_path)


def test_error_message_carries_artifact_path(tmp_path, source_file, facts_path):
    claim = base_claim()
    claim["period"] = "bogus"
    with pytest.raises(ClaimValidationError) as excinfo:
        validate_claim(claim, source_root=tmp_path, facts_path=facts_path)
    assert str(facts_path) in str(excinfo.value)
    assert claim["id"] in str(excinfo.value)


def test_validate_claims_in_facts_roundtrip(tmp_path, source_file, facts_path):
    facts = {"ticker": "GOOG", "claims": [base_claim()]}
    claims = validate_claims_in_facts(facts, source_root=tmp_path, facts_path=facts_path)
    assert len(claims) == 1
    assert validate_claims_in_facts({"ticker": "GOOG"}, source_root=tmp_path, facts_path=facts_path) == []


def test_claims_must_be_array(tmp_path, source_file, facts_path):
    with pytest.raises(ClaimValidationError, match="JSON array"):
        validate_claims_in_facts({"claims": {"id": "x"}}, source_root=tmp_path, facts_path=facts_path)


def test_duplicate_ids_within_document_rejected(tmp_path, source_file, facts_path):
    facts = {"claims": [base_claim(), base_claim()]}
    with pytest.raises(ClaimValidationError, match="duplicate claim id"):
        validate_claims_in_facts(facts, source_root=tmp_path, facts_path=facts_path)


def test_reference_validation(tmp_path, source_file, facts_path):
    other_path = tmp_path / "data" / "goog" / "q1-2026" / "facts.json"
    a, b = base_claim(), base_claim()
    b["id"] = "GOOG-2026Q2-capex-CY2026-002"
    # duplicate ids across documents
    with pytest.raises(ClaimValidationError, match="duplicate claim id"):
        validate_claim_references([(a, facts_path), (a, other_path)])
    # dangling supersedes_id
    b["supersedes_id"] = "GOOG-NOWHERE-001"
    with pytest.raises(ClaimValidationError, match="does not match any indexed claim"):
        validate_claim_references([(a, facts_path), (b, other_path)])
    # valid cross-document supersession
    b["supersedes_id"] = a["id"]
    validate_claim_references([(a, facts_path), (b, other_path)])


def test_primary_source_classification():
    for t in ("reported_actual", "management_guidance", "management_directional"):
        assert is_primary_source(t)
    for t in ("vendor_estimate", "agent_extrapolation", "scenario", "analyst_consensus"):
        assert not is_primary_source(t)


def test_vocabularies_match_spec():
    assert CLAIM_TYPES == [
        "reported_actual", "management_guidance", "management_directional",
        "vendor_estimate", "agent_extrapolation", "scenario",
    ]
    assert CAPEX_DEFINITIONS == [
        "cash_capex", "purchases_of_property_and_equipment",
        "capex_including_finance_lease_principal", "capex_including_leases",
        "company_defined_capex", "non_comparable_or_unspecified",
    ]


def test_json_serializable_claim_shape(source_file):
    claim = base_claim()
    json.dumps(claim)  # canonical shape must round-trip through facts.json
