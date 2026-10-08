"""Tests for the evidence-first ask: packet, rendering, and CLI behavior."""

import json
import sqlite3

import pytest
from click.testing import CliRunner

from eca.cli import cli
from eca.processors.ask import build_evidence_packet, render_packet

from tests.test_retrieval import make_claim


@pytest.fixture
def claim_db(tmp_path, monkeypatch):
    monkeypatch.setattr("eca.config.project_root", lambda: tmp_path)
    from eca.db import rebuild_index

    claims = [
        # GOOG guidance history + current
        make_claim("GOOG-2026Q1-capex-CY2026-001", quarter="q1-2026",
                   value_low=180000, value_high=190000, as_of="2026-04-29",
                   quote="We are updating our full year 2026 CapEx guidance range to $180 billion to $190 billion."),
        make_claim("GOOG-2026Q2-capex-CY2026-001", value_low=195000,
                   value_high=205000, as_of="2026-07-22",
                   supersedes="GOOG-2026Q1-capex-CY2026-001",
                   quote="We are updating our full year 2026 CapEx guidance range to $195 billion to $205 billion."),
        # AMZN, different CapEx definition
        make_claim("AMZN-2026Q2-capex-CY2026-001", ticker="AMZN",
                   definition="cash_capex", value_low=220000, value_high=220000,
                   as_of="2026-07-30", quote="We now believe we will spend approximately $220 billion in cash CapEx in 2026."),
        # AMZN vendor estimate for 2027 (displayed, never totaled as guidance)
        make_claim("AMZN-2026Q2-capex-CY2027-001", ticker="AMZN",
                   claim_type="vendor_estimate", period="CY2027",
                   definition="non_comparable_or_unspecified",
                   value_low=265000, value_high=265000, as_of="2026-10-05",
                   quote="We model Amazon calendar 2027 capital expenditures at approximately $265 billion."),
        # GOOG 2027 directional
        make_claim("GOOG-2026Q2-capex-CY2027-001", period="CY2027",
                   claim_type="management_directional", value_low=None,
                   value_high=None, currency=None, unit=None, definition=None,
                   direction="increase", as_of="2026-07-22",
                   quote="we expect our CapEx to increase significantly in 2027"),
        # funding evidence
        make_claim("MSFT-2026Q4-funding-CY2026Q2-001", ticker="MSFT",
                   quarter="q4-2026", topic="funding",
                   metric="operating_cash_flow", claim_type="reported_actual",
                   period="CY2026Q2", value_low=55400, value_high=55400,
                   definition=None, as_of="2026-07-29",
                   quote="Cash flow from operations was $55.4 billion, up 30%."),
        # return evidence (duration claim)
        make_claim("AMZN-2026Q2-return-CY2026-001", ticker="AMZN",
                   topic="return", metric="useful_life",
                   claim_type="reported_actual", period="CY2026",
                   value_low=None, value_high=None, currency=None, unit=None,
                   definition=None, durations=(60, 72), as_of="2026-07-30",
                   quote="The servers currently have a useful life of at least five to six years."),
    ]

    data = tmp_path / "data"
    by_quarter: dict[tuple, list[dict]] = {}
    for claim in claims:
        by_quarter.setdefault((claim["ticker"], claim["quarter"]), []).append(claim)
    for (ticker, qslug), group in by_quarter.items():
        qdir = data / ticker.lower() / qslug
        qdir.mkdir(parents=True, exist_ok=True)
        lines = ["Operator: welcome."]
        stored = []
        for claim in group:
            lines.append(claim["quote"])
            claim["line_start"] = claim["line_end"] = len(lines)
            stored.append({k: v for k, v in claim.items()
                           if k not in ("ticker", "quarter", "facts_path")})
        lines.append("End of remarks.")
        (qdir / "transcript.txt").write_text("\n".join(lines) + "\n")
        (qdir / "facts.json").write_text(json.dumps({
            "ticker": ticker, "quarter": "Q2 2026", "claims": stored,
        }))

    db_path = data / "eca.db"
    rebuild_index(db_path)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    yield conn
    conn.close()


MAG7 = ["AAPL", "AMZN", "GOOG", "META", "MSFT", "NVDA", "TSLA"]


def test_packet_structure(claim_db):
    packet = build_evidence_packet(
        claim_db, "How much will the Mag 7 spend on CapEx in 2026 and 2027?",
        topics=["capex"], periods=["CY2026", "CY2027"], tickers=MAG7,
        as_of="2026-10-07", policy="strict",
    )
    assert packet["policy"] == "strict"
    assert packet["as_of"] == "2026-10-07"
    assert packet["tickers"] == MAG7
    by_period = {tp["period"]: tp for tp in packet["topic_periods"]}
    assert set(by_period) == {"CY2026", "CY2027"}

    cy26 = by_period["CY2026"]
    # GOOG current claim is the superseding one; the Q1 claim is history
    evidence_ids = {c["id"] for c in cy26["evidence"]}
    assert "GOOG-2026Q2-capex-CY2026-001" in evidence_ids
    assert "GOOG-2026Q1-capex-CY2026-001" not in evidence_ids
    # vendor estimates stay out of primary evidence
    assert all(c["claim_type"] != "vendor_estimate" for c in cy26["evidence"])

    agg = cy26["aggregation"]
    assert agg["comparability"] == "mixed_definitions"
    assert agg["total_low_m"] is None  # never a silent combined strict total
    covered = set(agg["covered_tickers"])
    assert covered == {"GOOG", "AMZN"}
    missing = {m["ticker"] for m in agg["missing_tickers"]}
    assert missing == {"AAPL", "META", "MSFT", "NVDA", "TSLA"}


def test_packet_vendor_estimate_displayed_but_excluded(claim_db):
    packet = build_evidence_packet(
        claim_db, "2027 CapEx?", topics=["capex"], periods=["CY2027"],
        tickers=MAG7, as_of="2026-10-07",
    )
    cy27 = packet["topic_periods"][0]
    vendor_ids = {c["id"] for c in cy27["non_primary_evidence"]}
    assert "AMZN-2026Q2-capex-CY2027-001" in vendor_ids
    agg = cy27["aggregation"]
    assert "AMZN-2026Q2-capex-CY2027-001" not in agg["included_claim_ids"]
    assert agg["total_low_m"] is None  # CY2027 has only directional + vendor evidence
    # exclusion is auditable
    reasons = {e["claim_id"]: e["reason"] for e in packet["excluded"]}
    assert reasons["AMZN-2026Q2-capex-CY2027-001"] == "non_primary_source"


def test_packet_primary_only_hides_non_primary(claim_db):
    packet = build_evidence_packet(
        claim_db, "2027?", topics=["capex"], periods=["CY2027"],
        tickers=MAG7, as_of="2026-10-07", primary_only=True,
    )
    cy27 = packet["topic_periods"][0]
    assert cy27["non_primary_evidence"] == []
    assert not any(e["reason"] == "non_primary_source" for e in packet["excluded"])


def test_packet_funding_topic_has_no_aggregation(claim_db):
    packet = build_evidence_packet(
        claim_db, "How is CapEx funded?", topics=["funding"], tickers=MAG7,
        as_of="2026-10-07",
    )
    tp = packet["topic_periods"][0]
    assert tp["topic"] == "funding"
    assert tp["aggregation"] is None
    assert tp["evidence"][0]["metric"] == "operating_cash_flow"


def test_packet_derives_periods_when_unspecified(claim_db):
    packet = build_evidence_packet(
        claim_db, "CapEx question", topics=["capex"], tickers=MAG7,
        as_of="2026-10-07",
    )
    periods = [tp["period"] for tp in packet["topic_periods"]]
    assert "CY2026" in periods and "CY2027" in periods


def test_render_packet_sections(claim_db):
    packet = build_evidence_packet(
        claim_db, "How much will the Mag 7 spend in 2026?",
        topics=["capex"], periods=["CY2026"], tickers=MAG7,
        as_of="2026-10-07", policy="broad",
    )
    rendered = render_packet(packet)
    assert "## 1. Source-backed facts" in rendered
    assert "## 2. Totals" in rendered
    assert "## 3. Unknowns and excluded evidence" in rendered
    assert "$415000M-$425000M" in rendered  # broad disclosed subtotal GOOG+AMZN
    assert "NON-COMPARABLE" in rendered
    assert "definitions: cash_capex, company_defined_capex" in rendered
    assert "AAPL (no_disclosure_found)" in rendered
    assert "$220 billion in cash CapEx" in rendered  # quotes preserved
    assert "superseded by GOOG-2026Q2-capex-CY2026-001" in rendered


def test_render_packet_duration_claim(claim_db):
    packet = build_evidence_packet(
        claim_db, "Payback?", topics=["return"], tickers=["AMZN"],
        as_of="2026-10-07",
    )
    rendered = render_packet(packet)
    assert "useful_life" in rendered
    assert "60-72 months" in rendered
    assert "five to six years" in rendered


# --- CLI -----------------------------------------------------------------------

def test_cli_ask_json_performs_no_llm_call(tmp_path, monkeypatch, claim_db):
    def no_llm(*args, **kwargs):
        raise AssertionError("ask --json must not call the LLM")

    monkeypatch.setattr("eca.llm.run_analysis", no_llm)
    # point the CLI at the fixture tree
    root = tmp_path
    monkeypatch.setattr("eca.config.project_root", lambda: root)
    result = CliRunner().invoke(cli, [
        "ask", "Mag 7 2026-2027 CapEx?",
        "--tickers", ",".join(MAG7), "--period", "CY2026", "--period", "CY2027",
        "--as-of", "2026-10-07", "--json",
    ])
    assert result.exit_code == 0, result.output
    packet = json.loads(result.output)
    assert {tp["period"] for tp in packet["topic_periods"]} == {"CY2026", "CY2027"}
    assert packet["question"] == "Mag 7 2026-2027 CapEx?"


def test_cli_ask_separates_interpretation(tmp_path, monkeypatch, claim_db):
    captured = {}

    def fake_llm(system, user, model="m"):
        captured["system"] = system
        captured["user"] = user
        return "Interpretation: evidence is strong but 2027 is largely unknown."

    monkeypatch.setattr("eca.llm.run_analysis", fake_llm)
    monkeypatch.setattr("eca.config.project_root", lambda: tmp_path)
    result = CliRunner().invoke(cli, [
        "ask", "How much will the Mag 7 spend in 2026?",
        "--tickers", ",".join(MAG7), "--period", "CY2026",
        "--as-of", "2026-10-07", "--policy", "broad",
    ])
    assert result.exit_code == 0, result.output
    assert "## 1. Source-backed facts" in result.output
    assert "## 2. Totals" in result.output
    assert "## 3. Unknowns and excluded evidence" in result.output
    assert "## 4. Interpretation" in result.output
    assert "2027 is largely unknown" in result.output
    # the model receives only the question context and the packet
    assert "evidence packet" in captured["system"].lower()
    assert "Question: " in captured["user"] or "question" in json.loads(captured["user"])


def test_cli_ask_llm_failure_preserves_evidence(tmp_path, monkeypatch, claim_db):
    def boom(*args, **kwargs):
        raise RuntimeError("API unavailable")

    monkeypatch.setattr("eca.llm.run_analysis", boom)
    monkeypatch.setattr("eca.config.project_root", lambda: tmp_path)
    result = CliRunner().invoke(cli, [
        "ask", "How much in 2026?", "--tickers", "GOOG", "--period", "CY2026",
        "--as-of", "2026-10-07",
    ])
    assert result.exit_code == 1
    assert "## 1. Source-backed facts" in result.output  # evidence intact
    assert "Synthesis error" in result.output


def test_cli_find_json_valid_records(tmp_path, monkeypatch, claim_db):
    monkeypatch.setattr("eca.config.project_root", lambda: tmp_path)
    result = CliRunner().invoke(cli, [
        "find", "cash CapEx", "--tickers", "AMZN", "--period", "CY2026", "--json",
    ])
    assert result.exit_code == 0, result.output
    claims = json.loads(result.output)
    assert len(claims) == 1
    assert claims[0]["id"] == "AMZN-2026Q2-capex-CY2026-001"
    assert claims[0]["quote"].startswith("We now believe")


def test_cli_find_current_flag(tmp_path, monkeypatch, claim_db):
    monkeypatch.setattr("eca.config.project_root", lambda: tmp_path)
    result = CliRunner().invoke(cli, [
        "find", "--tickers", "GOOG", "--period", "CY2026", "--current",
        "--as-of", "2026-10-07",
    ])
    assert result.exit_code == 0, result.output
    assert "GOOG-2026Q2-capex-CY2026-001" in result.output
    assert "GOOG-2026Q1-capex-CY2026-001" not in result.output


def test_cli_find_primary_only(tmp_path, monkeypatch, claim_db):
    monkeypatch.setattr("eca.config.project_root", lambda: tmp_path)
    result = CliRunner().invoke(cli, [
        "find", "--period", "CY2027", "--primary-only", "--json",
    ])
    assert result.exit_code == 0, result.output
    claims = json.loads(result.output)
    assert all(c["claim_type"] != "vendor_estimate" for c in claims)
    assert len(claims) == 1  # only GOOG directional
