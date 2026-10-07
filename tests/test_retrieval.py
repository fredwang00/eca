"""Unit tests for deterministic find, supersession, and aggregation."""

import json
import sqlite3

import pytest

from eca.retrieval import aggregate_claims, find_claims, resolve_current


def make_claim(claim_id, ticker="GOOG", *, quarter="q2-2026", topic="capex", metric="capital_expenditure",
               claim_type="management_guidance", period="CY2026",
               value_low=195000, value_high=205000, currency="USD",
               definition="company_defined_capex", direction=None, unit=None,
               durations=(None, None), as_of="2026-07-22", supersedes=None,
               quote="We guide to CapEx."):
    low_m, high_m = value_low, value_high
    dur_low, dur_high = durations
    return {
        "id": claim_id, "ticker": ticker, "quarter": quarter,
        "topic": topic, "metric": metric, "claim_type": claim_type,
        "period": period, "value_low_m": low_m, "value_high_m": high_m,
        "currency": currency if low_m is not None else None,
        "unit": unit or ("USD_millions" if low_m is not None else None),
        "capex_definition": definition, "duration_low_months": dur_low,
        "duration_high_months": dur_high, "direction": direction,
        "speaker": "CFO", "source_document": "earnings call",
        "source_path": f"data/{ticker.lower()}/{quarter}/transcript.txt",
        "source_section": "prepared_remarks", "line_start": 2, "line_end": 2,
        "quote": quote, "as_of": as_of, "supersedes_id": supersedes,
        "notes": None, "facts_path": f"data/{ticker.lower()}/{quarter}/facts.json",
    }


# --- resolve_current ---------------------------------------------------------

def test_supersession_as_of_historical_date():
    old = make_claim("G1", as_of="2026-04-29", value_low=180000, value_high=190000)
    new = make_claim("G2", as_of="2026-07-22", value_low=195000, value_high=205000,
                     supersedes="G1")
    # before the update: old guidance is current
    res = resolve_current([old, new], as_of="2026-05-01")
    assert [c["id"] for c in res["current"]] == ["G1"]
    # after the update: new guidance is current, old is superseded
    res = resolve_current([old, new], as_of="2026-10-07")
    assert [c["id"] for c in res["current"]] == ["G2"]
    reasons = {e["claim_id"]: e["reason"] for e in res["excluded"]}
    assert reasons["G1"] == "superseded"


def test_superseding_claim_after_as_of_keeps_older_current():
    old = make_claim("G1", as_of="2026-04-29")
    new = make_claim("G2", as_of="2026-07-22", supersedes="G1")
    res = resolve_current([old, new], as_of="2026-05-01")
    assert [c["id"] for c in res["current"]] == ["G1"]


def test_older_unsuperseded_guidance_becomes_history():
    a = make_claim("A", as_of="2026-04-29")
    b = make_claim("B", as_of="2026-07-22")  # no supersedes declared
    res = resolve_current([a, b], as_of="2026-10-07")
    assert [c["id"] for c in res["current"]] == ["B"]
    reasons = {e["claim_id"]: e["reason"] for e in res["excluded"]}
    assert reasons["A"] == "not_current"


def test_conflicting_current_guidance_excluded_until_superseded():
    a = make_claim("A", as_of="2026-07-22", value_low=100)
    b = make_claim("B", as_of="2026-07-22", value_low=110)
    res = resolve_current([a, b], as_of="2026-10-07")
    assert res["current"] == []
    reasons = {e["claim_id"]: e["reason"] for e in res["excluded"]}
    assert reasons == {"A": "conflicting_current_guidance",
                       "B": "conflicting_current_guidance"}
    # declaring supersession resolves the conflict
    b2 = {**b, "supersedes_id": "A"}
    res = resolve_current([a, b2], as_of="2026-10-07")
    assert [c["id"] for c in res["current"]] == ["B2".replace("2", "")] or \
        [c["id"] for c in res["current"]] == ["B"]


def test_groups_kept_separate_by_period_and_metric():
    annual = make_claim("A", period="CY2026")
    quarterly = make_claim("Q", period="CY2026Q2", metric="capital_expenditure",
                           value_low=44000, value_high=44000)
    res = resolve_current([annual, quarterly], as_of="2026-10-07")
    assert {c["id"] for c in res["current"]} == {"A", "Q"}


# --- aggregate_claims --------------------------------------------------------

def test_strict_single_definition_total():
    goog = make_claim("G", ticker="GOOG", value_low=195000, value_high=205000)
    amzn = make_claim("A", ticker="AMZN", definition="company_defined_capex",
                      value_low=220000, value_high=220000)
    result = aggregate_claims([goog, amzn], as_of="2026-10-07", policy="strict")
    assert result["comparability"] == "comparable"
    assert result["total_low_m"] == 415000
    assert result["total_high_m"] == 425000
    assert result["covered_tickers"] == ["AMZN", "GOOG"]
    assert result["definitions"] == ["company_defined_capex"]


def test_strict_mixed_definitions_never_combine():
    goog = make_claim("G", definition="company_defined_capex",
                      value_low=195000, value_high=205000)
    amzn = make_claim("A", ticker="AMZN", definition="cash_capex",
                      value_low=220000, value_high=220000)
    result = aggregate_claims([goog, amzn], as_of="2026-10-07", policy="strict")
    assert result["comparability"] == "mixed_definitions"
    assert result["total_low_m"] is None
    assert result["total_high_m"] is None
    assert {s["definition"] for s in result["subtotals"]} == {
        "company_defined_capex", "cash_capex"}
    by_def = {s["definition"]: s for s in result["subtotals"]}
    assert by_def["company_defined_capex"]["low_m"] == 195000
    assert by_def["cash_capex"]["low_m"] == 220000
    assert any("mixed_definitions" in w for w in result["warnings"])


def test_broad_policy_labels_non_comparable():
    goog = make_claim("G", definition="company_defined_capex",
                      value_low=195000, value_high=205000)
    amzn = make_claim("A", ticker="AMZN", definition="cash_capex",
                      value_low=220000, value_high=220000)
    result = aggregate_claims([goog, amzn], as_of="2026-10-07", policy="broad")
    assert result["total_low_m"] == 415000
    assert result["total_high_m"] == 425000
    assert result["comparability"] == "non_comparable_disclosed"
    assert result["definitions"] == ["cash_capex", "company_defined_capex"]
    assert any("non-comparable" in w for w in result["warnings"])


def test_broad_policy_comparable_when_definitions_match():
    claims = [
        make_claim("G", definition="cash_capex", value_low=195000, value_high=205000),
        make_claim("A", ticker="AMZN", definition="cash_capex",
                   value_low=220000, value_high=220000),
    ]
    result = aggregate_claims(claims, as_of="2026-10-07", policy="broad")
    assert result["comparability"] == "comparable"


def test_currency_mismatch_prevents_aggregation():
    goog = make_claim("G", value_low=195000, value_high=205000)
    msft = make_claim("M", ticker="MSFT", value_low=175000, value_high=175000,
                      definition="company_defined_capex")
    other = make_claim("X", ticker="XSHE", value_low=1000, value_high=1000,
                       currency="EUR", definition="company_defined_capex")
    result = aggregate_claims([goog, msft, other], as_of="2026-10-07", policy="broad")
    # plurality currency (USD) is totaled; the EUR claim is excluded, never converted
    assert result["total_low_m"] == 370000
    reasons = {(e["claim_id"], e["reason"]) for e in result["excluded"]}
    assert ("X", "currency_mismatch") in reasons
    assert any("currency_mismatch" in w for w in result["warnings"])


def test_missing_company_is_not_zero():
    goog = make_claim("G")
    result = aggregate_claims([goog], as_of="2026-10-07",
                              expected_tickers=["AAPL", "AMZN", "GOOG"])
    assert result["missing_tickers"] == [
        {"ticker": "AAPL", "reason": "no_disclosure_found"},
        {"ticker": "AMZN", "reason": "no_disclosure_found"},
    ]
    assert result["total_low_m"] == 195000  # missing companies don't pad the total


def test_directional_claims_excluded_from_totals():
    directional = make_claim("D", ticker="MSFT", claim_type="management_directional",
                             value_low=None, value_high=None, currency=None,
                             unit=None, definition=None, direction="increase",
                             quote="We expect CapEx to increase.")
    numeric = make_claim("N")
    result = aggregate_claims([directional, numeric], as_of="2026-10-07")
    reasons = {e["claim_id"]: e["reason"] for e in result["excluded"]}
    assert reasons["D"] == "no_numeric_value"
    assert result["total_low_m"] == 195000


def test_open_ended_range_excluded_from_subtotals():
    open_ended = make_claim("O", value_low=25000, value_high=None,
                            definition="cash_capex")
    result = aggregate_claims([open_ended], as_of="2026-10-07")
    assert result["total_low_m"] is None
    assert result["subtotals"] == []
    reasons = {e["claim_id"]: e["reason"] for e in result["excluded"]}
    assert reasons["O"] == "open_ended_range"
    assert any("open_ended_range" in w for w in result["warnings"])


def test_vendor_estimates_are_evidence_but_not_primary():
    vendor = make_claim("V", claim_type="vendor_estimate",
                        definition="non_comparable_or_unspecified",
                        value_low=800000, value_high=800000)
    result = aggregate_claims([vendor], as_of="2026-10-07")
    # aggregation itself does not filter by class; callers pass primary claims.
    assert result["total_low_m"] == 800000
    from eca.claims import is_primary_source
    assert not is_primary_source("vendor_estimate")


def test_aggregate_rejects_mixed_scopes():
    a = make_claim("A", period="CY2026")
    b = make_claim("B", period="CY2027")
    with pytest.raises(ValueError, match="one topic/metric/period"):
        aggregate_claims([a, b])


def test_aggregate_rejects_unknown_policy():
    with pytest.raises(ValueError, match="policy"):
        aggregate_claims([make_claim("A")], policy="loose")


def test_no_comparable_claims_result():
    directional = make_claim("D", claim_type="management_directional",
                             value_low=None, value_high=None, currency=None,
                             unit=None, definition=None, direction="increase")
    result = aggregate_claims([directional], as_of="2026-10-07")
    assert result["comparability"] == "no_comparable_claims"
    assert result["total_low_m"] is None


# --- find_claims (SQL filters) -----------------------------------------------

@pytest.fixture
def claim_db(tmp_path, monkeypatch):
    monkeypatch.setattr("eca.config.project_root", lambda: tmp_path)
    from eca.db import rebuild_index

    quarters = {
        "GOOG": {
            "G-OLD": make_claim("GOOG-2026Q1-capex-CY2026-001", quarter="q1-2026",
                                value_low=180000, value_high=190000,
                                as_of="2026-04-29",
                                quote="We are updating our full year 2026 CapEx guidance range to $180 billion to $190 billion."),
            "G-NEW": make_claim("GOOG-2026Q2-capex-CY2026-001", as_of="2026-07-22",
                                supersedes="GOOG-2026Q1-capex-CY2026-001",
                                quote="We are updating our full year 2026 CapEx guidance range to $195 billion to $205 billion."),
            "G-2027": make_claim("GOOG-2026Q2-capex-CY2027-001", period="CY2027",
                                 claim_type="management_directional", value_low=None,
                                 value_high=None, currency=None, unit=None,
                                 definition=None, direction="increase",
                                 quote="we expect our CapEx to increase significantly in 2027"),
            "G-FUND": make_claim("GOOG-2026Q2-funding-CY2026Q2-001", topic="funding",
                                 metric="operating_cash_flow", claim_type="reported_actual",
                                 period="CY2026Q2", value_low=39100, value_high=39100,
                                 definition=None,
                                 quote="We generated strong operating cash flow."),
        },
        "AMZN": {
            "A-2026": make_claim("AMZN-2026Q2-capex-CY2026-001", ticker="AMZN",
                                 definition="cash_capex", value_low=220000,
                                 value_high=220000, as_of="2026-07-30",
                                 quote="cash CapEx in 2026"),
            "A-VENDOR": make_claim("AMZN-2026Q2-capex-CY2027-001", ticker="AMZN",
                                   claim_type="vendor_estimate", period="CY2027",
                                   definition="non_comparable_or_unspecified",
                                   value_low=265000, value_high=265000,
                                   quote="We model Amazon calendar 2027 capital expenditures."),
        },
        "NVDA": {
            "N-VENDOR": make_claim("NVDA-2027Q2-capex-CY2026-001", ticker="NVDA",
                                   claim_type="vendor_estimate",
                                   definition="non_comparable_or_unspecified",
                                   value_low=800000, value_high=800000,
                                   quote="CapEx by the top 5 hyperscalers."),
        },
    }
    data = tmp_path / "data"
    by_quarter: dict[tuple[str, str], list[dict]] = {}
    for ticker, claims in quarters.items():
        for claim in claims.values():
            by_quarter.setdefault((ticker, claim["quarter"]), []).append(claim)

    for (ticker, qslug), claims in by_quarter.items():
        qdir = data / ticker.lower() / qslug
        qdir.mkdir(parents=True, exist_ok=True)
        lines = ["Operator: welcome."]
        stored_claims = []
        for claim in claims:
            lines.append(claim["quote"])
            claim["line_start"] = claim["line_end"] = len(lines)
            stored = {k: v for k, v in claim.items()
                      if k not in ("ticker", "quarter", "facts_path")}
            stored_claims.append(stored)
        lines.append("End of remarks.")
        (qdir / "transcript.txt").write_text("\n".join(lines) + "\n")
        (qdir / "facts.json").write_text(json.dumps({
            "ticker": ticker, "quarter": "Q2 2026", "claims": stored_claims,
        }))

    db_path = data / "eca.db"
    rebuild_index(db_path)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    yield conn
    conn.close()


def test_find_by_ticker_and_period(claim_db):
    claims = find_claims(claim_db, tickers=["GOOG"], period="CY2026")
    assert {c["id"] for c in claims} == {
        "GOOG-2026Q1-capex-CY2026-001", "GOOG-2026Q2-capex-CY2026-001"}


def test_find_by_claim_type(claim_db):
    claims = find_claims(claim_db, claim_types=["vendor_estimate"])
    assert {c["id"] for c in claims} == {
        "AMZN-2026Q2-capex-CY2027-001", "NVDA-2027Q2-capex-CY2026-001"}


def test_find_primary_only_excludes_vendor_estimates(claim_db):
    claims = find_claims(claim_db, primary_only=True)
    ids = {c["id"] for c in claims}
    assert "NVDA-2027Q2-capex-CY2026-001" not in ids
    assert "AMZN-2026Q2-capex-CY2027-001" not in ids
    assert "GOOG-2026Q2-capex-CY2026-001" in ids


def test_find_as_of_date(claim_db):
    claims = find_claims(claim_db, tickers=["GOOG"], period="CY2026", as_of="2026-05-01")
    assert {c["id"] for c in claims} == {"GOOG-2026Q1-capex-CY2026-001"}


def test_find_by_text(claim_db):
    claims = find_claims(claim_db, text="hyperscalers")
    assert {c["id"] for c in claims} == {"NVDA-2027Q2-capex-CY2026-001"}


def test_find_by_topic(claim_db):
    claims = find_claims(claim_db, topic="funding")
    assert {c["id"] for c in claims} == {"GOOG-2026Q2-funding-CY2026Q2-001"}


def test_find_by_sector(claim_db):
    claims = find_claims(claim_db, sector="mag7", period="CY2026")
    assert "GOOG-2026Q2-capex-CY2026-001" in {c["id"] for c in claims}
    assert all(c["ticker"] != "XSHE" for c in claims)


def test_find_by_definition(claim_db):
    claims = find_claims(claim_db, definition="cash_capex")
    assert {c["id"] for c in claims} == {"AMZN-2026Q2-capex-CY2026-001"}


def test_find_unknown_sector_rejected(claim_db):
    with pytest.raises(ValueError, match="Unknown sector"):
        find_claims(claim_db, sector="nope")


def test_current_resolution_via_find(claim_db):
    from eca.retrieval import resolve_current
    claims = find_claims(claim_db, tickers=["GOOG"], period="CY2026", primary_only=True)
    res = resolve_current(claims, as_of="2026-10-07")
    assert [c["id"] for c in res["current"]] == ["GOOG-2026Q2-capex-CY2026-001"]


def test_format_claim_rendering():
    claim = make_claim("G", quote="We are updating our full year 2026 CapEx guidance.")
    rendered = __import__("eca.retrieval", fromlist=["format_claim"]).format_claim(claim)
    assert "[GOOG] capital_expenditure CY2026" in rendered
    assert "$195000M-$205000M USD" in rendered
    assert "(company_defined_capex)" in rendered
    assert "management_guidance" in rendered
    assert '"We are updating our full year 2026 CapEx guidance."' in rendered
    assert "data/goog/q2-2026/transcript.txt lines 2-2" in rendered
