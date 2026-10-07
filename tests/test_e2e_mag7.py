"""End-to-end acceptance tests for the Mag 7 CapEx evidence fixture.

The fixture (tests/fixtures/mag7) is a compact, self-contained data tree
modeled on the motivating question: how much the Magnificent Seven expect to
spend on capital investment in 2026 and 2027, how it is funded, and what
management has disclosed about payback. These tests prove the milestone's
definition of done.
"""

import json
import shutil
import sqlite3
from pathlib import Path

import pytest
from click.testing import CliRunner

from eca.cli import cli

FIXTURE = Path(__file__).parent / "fixtures" / "mag7"
MAG7 = ["AAPL", "AMZN", "GOOG", "META", "MSFT", "NVDA", "TSLA"]
AS_OF = "2026-10-07"  # the handoff date; after every fixture call


@pytest.fixture
def mag7_tree(tmp_path, monkeypatch):
    """A private copy of the fixture as the active project tree."""
    tree = tmp_path / "mag7"
    shutil.copytree(FIXTURE, tree)
    monkeypatch.setattr("eca.config.project_root", lambda: tree)
    return tree


@pytest.fixture
def mag7_db(mag7_tree):
    from eca.db import rebuild_index

    db_path = mag7_tree / "data" / "eca.db"
    rebuild_index(db_path)
    return db_path


@pytest.fixture
def mag7_conn(mag7_db):
    conn = sqlite3.connect(mag7_db)
    conn.row_factory = sqlite3.Row
    yield conn
    conn.close()


def _packet(conn, **kwargs):
    from eca.processors.ask import build_evidence_packet

    defaults = dict(
        topics=["capex"], tickers=MAG7, as_of=AS_OF, policy="strict",
    )
    defaults.update(kwargs)
    return build_evidence_packet(
        conn, "How much will the Mag 7 spend on capital investment in 2026 and 2027, how is it funded, and what is disclosed about payback?",
        **defaults,
    )


# --- fixture integrity ---------------------------------------------------------

def test_fixture_indexes_cleanly(mag7_conn):
    count = mag7_conn.execute("SELECT COUNT(*) FROM claims").fetchone()[0]
    assert count == 23
    tickers = {r[0] for r in mag7_conn.execute("SELECT ticker FROM claims")}
    assert tickers == {"GOOG", "AMZN", "META", "MSFT", "TSLA", "NVDA"}


def test_fixture_artifacts_match_ingestion(tmp_path, monkeypatch, mag7_tree):
    """The checked-in raw/normalized/meta artifacts are exactly what
    ingest-transcript produces (hashes included)."""
    monkeypatch.setattr("eca.config.project_root", lambda: tmp_path)
    from eca.processors.ingest_transcript import ingest_transcript

    result = ingest_transcript(
        "GOOG", "q2-2026",
        FIXTURE / "data" / "goog" / "q2-2026" / "transcript.raw.txt",
        meta={
            "source_provider": "fixture-curated",
            "source_url": "https://example.invalid/goog-q2-2026",
            "retrieved_at": "2026-10-07T00:00:00Z",
            "document_date": "2026-07-22", "call_date": "2026-07-22",
            "fiscal_year": 2026, "fiscal_quarter": 2,
            "period_start": "2026-04-01", "period_end": "2026-06-30",
        },
    )
    checked_meta = json.loads(
        (FIXTURE / "data" / "goog" / "q2-2026" / "transcript.meta.json").read_text()
    )
    assert result.meta["sha256_raw"] == checked_meta["sha256_raw"]
    assert result.meta["sha256_normalized"] == checked_meta["sha256_normalized"]
    assert (result.target / "transcript.txt").read_text() == \
        (FIXTURE / "data" / "goog" / "q2-2026" / "transcript.txt").read_text()
    assert result.meta["normalization_warnings"] == \
        checked_meta["normalization_warnings"]


# --- 2026 subtotals with explicit coverage and definition labels ---------------

def test_2026_strict_subtotals_are_per_definition(mag7_conn):
    packet = _packet(mag7_conn, periods=["CY2026"])
    agg = packet["topic_periods"][0]["aggregation"]
    assert agg["comparability"] == "mixed_definitions"
    # no combined strict total across incompatible definitions
    assert agg["total_low_m"] is None
    assert agg["total_high_m"] is None
    by_def = {s["definition"]: s for s in agg["subtotals"]}
    assert by_def["company_defined_capex"] == {
        "definition": "company_defined_capex",
        "low_m": 195000, "high_m": 205000,
        "claim_ids": ["GOOG-2026Q2-capex-CY2026-001"],
        "tickers": ["GOOG"],
    }
    assert by_def["cash_capex"]["low_m"] == 220000
    assert by_def["cash_capex"]["tickers"] == ["AMZN"]
    # META + MSFT share the lease-inclusive definition and total together
    assert by_def["capex_including_finance_lease_principal"]["low_m"] == 305000
    assert by_def["capex_including_finance_lease_principal"]["high_m"] == 320000
    assert by_def["capex_including_finance_lease_principal"]["tickers"] == ["META", "MSFT"]
    # mixed definitions cannot silently form a strict total
    assert any("mixed_definitions" in w for w in agg["warnings"])
    assert agg["definitions"] == [
        "capex_including_finance_lease_principal", "cash_capex",
        "company_defined_capex",
    ]


def test_2026_broad_disclosed_subtotal_labeled_non_comparable(mag7_conn):
    packet = _packet(mag7_conn, periods=["CY2026"], policy="broad")
    agg = packet["topic_periods"][0]["aggregation"]
    assert agg["total_low_m"] == 720000  # 195 + 220 + 130 + 175
    assert agg["total_high_m"] == 745000  # 205 + 220 + 145 + 175
    assert agg["comparability"] == "non_comparable_disclosed"
    # every included definition is listed
    assert agg["definitions"] == [
        "capex_including_finance_lease_principal", "cash_capex",
        "company_defined_capex",
    ]
    assert any("non-comparable" in w for w in agg["warnings"])


def test_2026_company_coverage_is_explicit(mag7_conn):
    packet = _packet(mag7_conn, periods=["CY2026"])
    agg = packet["topic_periods"][0]["aggregation"]
    assert agg["covered_tickers"] == ["AMZN", "GOOG", "META", "MSFT"]
    missing = {m["ticker"]: m["reason"] for m in agg["missing_tickers"]}
    assert set(missing) == {"AAPL", "NVDA", "TSLA"}
    # missing disclosure is never zero and never guessed
    assert missing["AAPL"] == "no_disclosure_found"


def test_open_ended_tesla_guidance_displayed_not_totaled(mag7_conn):
    packet = _packet(mag7_conn, periods=["CY2026"])
    tp = packet["topic_periods"][0]
    tsla_included = any(c["ticker"] == "TSLA" for c in tp["evidence"])
    assert tsla_included  # the >$25B claim is displayed as evidence with its quote
    reasons = {e["claim_id"]: e["reason"] for e in tp["aggregation"]["excluded"]}
    assert reasons["TSLA-2026Q2-capex-CY2026-001"] == "open_ended_range"
    assert "TSLA" not in tp["aggregation"]["covered_tickers"]


# --- Apple and NVIDIA stay unknown ---------------------------------------------

def test_apple_and_nvidia_stay_unknown_for_2026(mag7_conn):
    packet = _packet(mag7_conn, periods=["CY2026"])
    tp = packet["topic_periods"][0]
    unknown = {u["ticker"]: u["reason"] for u in tp["coverage"]["unknown"]}
    assert unknown["AAPL"] == "no_disclosure_found"
    # NVIDIA's only CapEx claims are vendor estimates about hyperscalers
    assert unknown["NVDA"] == "no_primary_source_disclosure"
    assert all(c["ticker"] != "AAPL" for c in tp["evidence"])


def test_nvidia_vendor_estimate_displayed_but_excluded_from_2026_totals(mag7_conn):
    packet = _packet(mag7_conn, periods=["CY2026"])
    tp = packet["topic_periods"][0]
    vendor_ids = {c["id"] for c in tp["non_primary_evidence"]}
    assert "NVDA-2027Q2-capex-CY2026-001" in vendor_ids  # displayed...
    assert "NVDA-2027Q2-capex-CY2026-001" not in tp["aggregation"]["included_claim_ids"]
    # ...and never mistaken for bottom-up company guidance in totals
    assert "NVDA" not in tp["aggregation"]["covered_tickers"]
    reasons = {e["claim_id"]: e["reason"] for e in packet["excluded"]}
    assert reasons["NVDA-2027Q2-capex-CY2026-001"] == "non_primary_source"


# --- 2027: vendor estimate displayed, excluded from guidance totals -------------

def test_2027_vendor_estimate_excluded_from_management_guidance_total(mag7_conn):
    packet = _packet(mag7_conn, periods=["CY2027"])
    tp = packet["topic_periods"][0]
    # NVIDIA's $1.3T industry estimate is displayed as evidence
    vendor = [c for c in tp["non_primary_evidence"]
              if c["id"] == "NVDA-2027Q2-capex-CY2027-001"]
    assert vendor and vendor[0]["value_low_m"] == 1300000
    # but no management-guidance total exists for 2027
    agg = tp["aggregation"]
    assert agg["total_low_m"] is None
    assert agg["comparability"] == "no_comparable_claims"
    assert "NVDA-2027Q2-capex-CY2027-001" not in agg["included_claim_ids"]
    reasons = {e["claim_id"]: e["reason"] for e in packet["excluded"]}
    assert reasons["NVDA-2027Q2-capex-CY2027-001"] == "non_primary_source"
    # GOOG's 2027 statement is directional only
    assert any(c["id"] == "GOOG-2026Q2-capex-CY2027-001" for c in tp["evidence"])
    assert reasons["GOOG-2026Q2-capex-CY2027-001"] == "no_numeric_value"


def test_fiscal_year_guidance_never_leaks_into_calendar_year_results(mag7_conn):
    from eca.retrieval import find_claims

    # MSFT's FY2027 claim is real and queryable on its own label
    fy = find_claims(mag7_conn, period="FY2027", primary_only=True)
    assert [c["id"] for c in fy] == ["MSFT-2026Q4-capex-FY2027-001"]
    # but a CY2027 query never sees it
    cy = find_claims(mag7_conn, period="CY2027")
    assert all(c["period"] == "CY2027" for c in cy)
    assert "MSFT-2026Q4-capex-FY2027-001" not in {c["id"] for c in cy}


# --- supersession --------------------------------------------------------------

def test_goog_guidance_supersession_as_of_historical_dates(mag7_conn):
    # before the July update, April's $180-190B guidance is current
    april = _packet(mag7_conn, periods=["CY2026"], as_of="2026-05-15")
    evidence = april["topic_periods"][0]["evidence"]
    assert [c["id"] for c in evidence if c["ticker"] == "GOOG"] == \
        ["GOOG-2026Q1-capex-CY2026-001"]
    # after the update, July's $195-205B is current and April's is history
    october = _packet(mag7_conn, periods=["CY2026"])
    evidence = october["topic_periods"][0]["evidence"]
    assert [c["id"] for c in evidence if c["ticker"] == "GOOG"] == \
        ["GOOG-2026Q2-capex-CY2026-001"]
    reasons = {e["claim_id"]: e["reason"] for e in october["excluded"]}
    assert reasons["GOOG-2026Q1-capex-CY2026-001"] == "superseded"


# --- funding evidence ----------------------------------------------------------

def test_funding_evidence_renders_as_distinct_sources(mag7_conn):
    from eca.processors.ask import render_packet

    packet = _packet(mag7_conn, topics=["funding"], periods=None)
    rendered = render_packet(packet)
    metrics = set()
    for tp in packet["topic_periods"]:
        metrics |= {c["metric"] for c in tp["evidence"]}
    # debt, leases, JV, cash flow, and borrowing capacity are distinct evidence
    assert metrics == {
        "operating_cash_flow", "joint_venture_funding", "borrowing_capacity",
        "debt_issuance", "lease_funding",
    }
    # each appears with a quote, not a forced percentage
    assert "BlackRock" in rendered
    assert "Cash flow from operations was $55.4 billion" in rendered
    assert "capacity to borrow up to $30 billion" in rendered
    # funding claims carry disclosed money amounts or none at all — never a
    # synthesized funding-mix percentage
    for tp in packet["topic_periods"]:
        for c in tp["evidence"]:
            if c["value_low_m"] is not None:
                assert c["unit"] == "USD_millions"
    # funding is never aggregated into a total
    assert all(tp["aggregation"] is None for tp in packet["topic_periods"])


# --- return evidence -----------------------------------------------------------

def test_amazon_payback_and_useful_life_claims_carry_quotes(mag7_conn):
    from eca.retrieval import find_claims

    claims = find_claims(mag7_conn, tickers=["AMZN"], topic="return")
    by_id = {c["id"]: c for c in claims}
    assert set(by_id) == {
        "AMZN-2026Q2-return-CY2026-001",  # payback
        "AMZN-2026Q2-return-CY2026-002",  # server useful life
        "AMZN-2026Q2-return-CY2026-003",  # data center useful life
        "AMZN-2026Q2-return-CY2026-004",  # monetization lag
    }
    payback = by_id["AMZN-2026Q2-return-CY2026-001"]
    assert payback["metric"] == "payback_period"
    assert payback["duration_high_months"] == 36
    assert payback["duration_low_months"] is None
    assert payback["quote"].startswith("For servers and networking equipment")
    servers = by_id["AMZN-2026Q2-return-CY2026-002"]
    assert servers["duration_low_months"] == 60
    assert servers["duration_high_months"] == 72
    assert "five to six years" in servers["quote"]
    data_centers = by_id["AMZN-2026Q2-return-CY2026-003"]
    assert data_centers["duration_low_months"] == 360
    assert data_centers["duration_high_months"] is None  # "30-plus-year" stays open-ended


def test_qualitative_return_narratives_never_become_numbers(mag7_conn):
    from eca.retrieval import find_claims

    qualitative = find_claims(mag7_conn, topic="return", claim_types=["management_directional"])
    assert {c["id"] for c in qualitative} == {
        "META-2026Q2-return-CY2026-001", "TSLA-2026Q2-return-CY2026-001",
    }
    for claim in qualitative:
        assert claim["value_low_m"] is None
        assert claim["duration_low_months"] is None
        assert claim["duration_high_months"] is None
        assert claim["quote"]  # narrative preserved as quotation


# --- CLI end-to-end ------------------------------------------------------------

def test_cli_ask_json_full_motivating_question(mag7_tree, monkeypatch):
    def no_llm(*args, **kwargs):
        raise AssertionError("ask --json must not call the LLM")

    monkeypatch.setattr("eca.llm.run_analysis", no_llm)
    result = CliRunner().invoke(cli, [
        "ask", "Mag 7 2026-2027 CapEx, funding, and payback?",
        "--sector", "mag7",
        "--topic", "capex", "--topic", "funding", "--topic", "return",
        "--period", "CY2026", "--period", "CY2027",
        "--as-of", AS_OF, "--json",
    ])
    assert result.exit_code == 0, result.output
    packet = json.loads(result.output)
    assert packet["tickers"] == MAG7
    periods = {(tp["topic"], tp["period"]) for tp in packet["topic_periods"]}
    assert ("capex", "CY2026") in periods
    assert ("capex", "CY2027") in periods
    assert ("funding", "CY2026") in periods
    # unknowns are explicit, not zeros
    unknowns = [u for tp in packet["topic_periods"] for u in tp["coverage"]["unknown"]
                if u["ticker"] in ("AAPL", "NVDA")]
    assert unknowns


def test_cli_ask_human_output_sections(mag7_tree, monkeypatch):
    monkeypatch.setattr(
        "eca.llm.run_analysis",
        lambda system, user, model="m": "Interpretation: totals are partial; unknowns dominate 2027.",
    )
    result = CliRunner().invoke(cli, [
        "ask", "How much will the Mag 7 spend in 2026?",
        "--tickers", ",".join(MAG7), "--period", "CY2026",
        "--as-of", AS_OF, "--policy", "broad",
    ])
    assert result.exit_code == 0, result.output
    assert "## 1. Source-backed facts" in result.output
    assert "$720000M-$745000M" in result.output  # broad disclosed subtotal
    assert "NON-COMPARABLE" in result.output
    assert "AAPL (no_disclosure_found)" in result.output
    assert "## 4. Interpretation" in result.output
    assert "unknowns dominate 2027" in result.output


def test_cli_find_on_fixture(mag7_tree):
    result = CliRunner().invoke(cli, [
        "find", "finance leases", "--topic", "capex", "--period", "CY2026",
        "--claim-type", "management_guidance", "--json",
    ])
    assert result.exit_code == 0, result.output
    claims = json.loads(result.output)
    assert [c["id"] for c in claims] == ["META-2026Q2-capex-CY2026-001"]
    assert claims[0]["capex_definition"] == "capex_including_finance_lease_principal"


def test_cli_build_index_on_fixture(mag7_tree):
    result = CliRunner().invoke(cli, ["build-index"])
    assert result.exit_code == 0, result.output
    assert "Index rebuilt" in result.output


def test_cli_build_index_fails_loudly_on_drifted_quote(mag7_tree, monkeypatch):
    """If a fixture transcript is edited without updating its claims, the
    rebuild fails with the exact artifact path — never a silent drop."""
    facts_path = mag7_tree / "data" / "goog" / "q2-2026" / "facts.json"
    facts = json.loads(facts_path.read_text())
    facts["claims"][0]["quote"] = "A quote that no longer matches the transcript."
    facts_path.write_text(json.dumps(facts))
    result = CliRunner().invoke(cli, ["build-index"])
    assert result.exit_code != 0
    assert "quote not found" in result.output
    assert str(facts_path) in result.output
