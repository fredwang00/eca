import json
import shutil
import sqlite3
from pathlib import Path

import pytest

from eca.db import rebuild_index, connect_db, query_sector_financials, query_grade_trajectory, query_flag_frequency


def _make_facts(tmp_path, ticker, quarter, candor=None, metrics=None, flags=None):
    """Helper to create a facts.json file in the expected directory structure."""
    d = tmp_path / "data" / ticker.lower() / quarter
    d.mkdir(parents=True)
    facts = {"ticker": ticker, "quarter": quarter}
    if candor:
        facts["candor"] = candor
    if metrics:
        facts["metrics"] = metrics
    if flags:
        facts["flags"] = flags
    (d / "facts.json").write_text(json.dumps(facts))
    return d


def test_rebuild_creates_tables(tmp_path, monkeypatch):
    monkeypatch.setattr("eca.config.project_root", lambda: tmp_path)
    (tmp_path / "data").mkdir()
    db_path = tmp_path / "data" / "eca.db"
    rebuild_index(db_path)
    conn = sqlite3.connect(db_path)
    tables = [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()]
    conn.close()
    assert "quarter_facts" in tables
    assert "quarter_flags" in tables
    assert "sector_map" in tables


def test_rebuild_inserts_facts(tmp_path, monkeypatch):
    monkeypatch.setattr("eca.config.project_root", lambda: tmp_path)
    _make_facts(tmp_path, "IREN", "q1-2025",
                candor={"composite_score": 2.65, "composite_grade": "B"},
                metrics={"revenue_m": 240.0, "capital_expenditure_m": 100.0})
    db_path = tmp_path / "data" / "eca.db"
    rebuild_index(db_path)
    conn = sqlite3.connect(db_path)
    row = conn.execute(
        "SELECT ticker, composite_score, revenue_m, capital_expenditure_m FROM quarter_facts"
    ).fetchone()
    conn.close()
    assert row == ("IREN", 2.65, 240.0, 100.0)


def test_rebuild_inserts_flags(tmp_path, monkeypatch):
    monkeypatch.setattr("eca.config.project_root", lambda: tmp_path)
    _make_facts(tmp_path, "ROOT", "q3-2025", flags=["equity_declining_yoy", "bvps_absent"])
    db_path = tmp_path / "data" / "eca.db"
    rebuild_index(db_path)
    conn = sqlite3.connect(db_path)
    flags = [r[0] for r in conn.execute(
        "SELECT flag FROM quarter_flags WHERE ticker='ROOT' ORDER BY flag"
    ).fetchall()]
    conn.close()
    assert flags == ["bvps_absent", "equity_declining_yoy"]


def test_rebuild_populates_sector_map(tmp_path, monkeypatch):
    monkeypatch.setattr("eca.config.project_root", lambda: tmp_path)
    (tmp_path / "data").mkdir()
    db_path = tmp_path / "data" / "eca.db"
    rebuild_index(db_path)
    conn = sqlite3.connect(db_path)
    row = conn.execute(
        "SELECT sector FROM sector_map WHERE ticker='IREN'"
    ).fetchone()
    conn.close()
    assert row == ("infra",)


def test_rebuild_is_full_rebuild(tmp_path, monkeypatch):
    monkeypatch.setattr("eca.config.project_root", lambda: tmp_path)
    _make_facts(tmp_path, "IREN", "q1-2025")
    db_path = tmp_path / "data" / "eca.db"
    rebuild_index(db_path)
    shutil.rmtree(tmp_path / "data" / "iren")
    rebuild_index(db_path)
    conn = sqlite3.connect(db_path)
    count = conn.execute("SELECT COUNT(*) FROM quarter_facts").fetchone()[0]
    conn.close()
    assert count == 0


def test_query_sector_financials(tmp_path, monkeypatch):
    monkeypatch.setattr("eca.config.project_root", lambda: tmp_path)
    _make_facts(tmp_path, "IREN", "q1-2025", metrics={"revenue_m": 240.0, "capital_expenditure_m": 100.0})
    _make_facts(tmp_path, "IREN", "q2-2025", metrics={"revenue_m": 300.0, "capital_expenditure_m": 120.0})
    _make_facts(tmp_path, "CIFR", "q1-2025", metrics={"revenue_m": 72.0})
    db_path = tmp_path / "data" / "eca.db"
    rebuild_index(db_path)
    conn = connect_db(db_path)
    rows = query_sector_financials(conn, ["IREN", "CIFR"])
    conn.close()
    iren = [r for r in rows if r["ticker"] == "IREN"][0]
    assert iren["total_revenue"] == 540.0
    assert iren["total_capex"] == 220.0


def test_query_grade_trajectory(tmp_path, monkeypatch):
    monkeypatch.setattr("eca.config.project_root", lambda: tmp_path)
    _make_facts(tmp_path, "IREN", "q3-2023", candor={"composite_score": 2.58, "composite_grade": "C+"})
    _make_facts(tmp_path, "IREN", "q1-2025", candor={"composite_score": 2.65, "composite_grade": "B"})
    db_path = tmp_path / "data" / "eca.db"
    rebuild_index(db_path)
    conn = connect_db(db_path)
    rows = query_grade_trajectory(conn, ["IREN"])
    conn.close()
    assert len(rows) == 2
    assert rows[0]["quarter"] == "q3-2023"
    assert rows[1]["quarter"] == "q1-2025"


def test_query_flag_frequency(tmp_path, monkeypatch):
    monkeypatch.setattr("eca.config.project_root", lambda: tmp_path)
    _make_facts(tmp_path, "IREN", "q1-2025", flags=["equity_declining_yoy"])
    _make_facts(tmp_path, "CIFR", "q1-2025", flags=["equity_declining_yoy", "bvps_absent"])
    db_path = tmp_path / "data" / "eca.db"
    rebuild_index(db_path)
    conn = connect_db(db_path)
    rows = query_flag_frequency(conn, ["IREN", "CIFR"])
    conn.close()
    freqs = {r["flag"]: r["cnt"] for r in rows}
    assert freqs["equity_declining_yoy"] == 2
    assert freqs["bvps_absent"] == 1


def test_rebuild_inserts_signals(tmp_path, monkeypatch):
    monkeypatch.setattr("eca.config.project_root", lambda: tmp_path)
    _make_facts(tmp_path, "WMT", "q4-2025",
                candor={"composite_score": 3.0},
                metrics={"revenue_m": 164000.0})
    # Add signals to the facts file
    d = tmp_path / "data" / "wmt" / "q4-2025"
    facts = json.loads((d / "facts.json").read_text())
    facts["signals"] = {
        "consumer_stress_tier": "trade_down",
        "pricing_power": "moderate",
        "extracted_at": "2026-03-30",
    }
    (d / "facts.json").write_text(json.dumps(facts))

    db_path = tmp_path / "data" / "eca.db"
    rebuild_index(db_path)
    conn = sqlite3.connect(db_path)
    row = conn.execute(
        "SELECT consumer_stress_tier, pricing_power, signals_extracted_at FROM quarter_facts WHERE ticker='WMT'"
    ).fetchone()
    conn.close()
    assert row == ("trade_down", "moderate", "2026-03-30")


# --- Claims indexing (mag7 evidence spec) ------------------------------------

def _claim(claim_id, source_rel="data/goog/q2-2026/transcript.txt", **overrides):
    from tests.test_claims import base_claim  # reuse canonical shape
    claim = base_claim(source_rel)
    claim["id"] = claim_id
    claim.update(overrides)
    return claim


def _make_transcript(tmp_path, ticker, quarter, lines):
    d = tmp_path / "data" / ticker.lower() / quarter
    d.mkdir(parents=True, exist_ok=True)
    (d / "transcript.txt").write_text("\n".join(lines) + "\n")
    return d


def _make_claim_facts(tmp_path, ticker, quarter, claims, lines=None):
    d = _make_transcript(tmp_path, ticker, quarter, lines or [
        "Operator: welcome.",
        "We are updating our full year 2026 CapEx guidance.",
    ])
    (d / "facts.json").write_text(json.dumps({
        "ticker": ticker, "quarter": "Q2 2026", "claims": claims,
    }))
    return d


def _rebuild(tmp_path, monkeypatch):
    monkeypatch.setattr("eca.config.project_root", lambda: tmp_path)
    db_path = tmp_path / "data" / "eca.db"
    rebuild_index(db_path)
    return db_path


def test_rebuild_indexes_claims(tmp_path, monkeypatch):
    claim = _claim("GOOG-2026Q2-capex-CY2026-001")
    _make_claim_facts(tmp_path, "GOOG", "q2-2026", [claim])
    db_path = _rebuild(tmp_path, monkeypatch)
    conn = sqlite3.connect(db_path)
    row = conn.execute("SELECT * FROM claims WHERE id=?", (claim["id"],)).fetchone()
    cols = [c[0] for c in conn.execute("SELECT * FROM claims LIMIT 1").description]
    conn.close()
    d = dict(zip(cols, row))
    assert d["ticker"] == "GOOG"
    assert d["quarter"] == "q2-2026"
    assert d["topic"] == "capex"
    assert d["value_low_m"] == 195000
    assert d["quote"].startswith("We are updating")
    assert d["facts_path"].endswith("facts.json")


def test_claims_indexes_exist(tmp_path, monkeypatch):
    claim = _claim("GOOG-2026Q2-capex-CY2026-001")
    _make_claim_facts(tmp_path, "GOOG", "q2-2026", [claim])
    db_path = _rebuild(tmp_path, monkeypatch)
    conn = sqlite3.connect(db_path)
    indexes = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index'").fetchall()}
    conn.close()
    assert {"idx_claims_topic_period_ticker",
            "idx_claims_metric_type_asof",
            "idx_claims_supersedes"} <= indexes


def test_malformed_claim_fails_rebuild_with_path(tmp_path, monkeypatch):
    claim = _claim("GOOG-2026Q2-capex-CY2026-001")
    claim["period"] = "whenever"
    facts_dir = _make_claim_facts(tmp_path, "GOOG", "q2-2026", [claim])
    monkeypatch.setattr("eca.config.project_root", lambda: tmp_path)
    db_path = tmp_path / "data" / "eca.db"
    from eca.claims import ClaimValidationError
    with pytest.raises(ClaimValidationError) as excinfo:
        rebuild_index(db_path)
    assert str(facts_dir / "facts.json") in str(excinfo.value)
    # nothing was indexed
    assert not db_path.exists() or sqlite3.connect(db_path).execute(
        "SELECT COUNT(*) FROM claims").fetchone()[0] == 0


def test_duplicate_claim_ids_across_tree_fail_rebuild(tmp_path, monkeypatch):
    claim = _claim("GOOG-2026Q2-capex-CY2026-001")
    _make_claim_facts(tmp_path, "GOOG", "q1-2026", [claim])
    _make_claim_facts(tmp_path, "GOOG", "q2-2026", [claim])
    monkeypatch.setattr("eca.config.project_root", lambda: tmp_path)
    from eca.claims import ClaimValidationError
    with pytest.raises(ClaimValidationError, match="duplicate claim id"):
        rebuild_index(tmp_path / "data" / "eca.db")


def test_missing_transcript_prevents_indexing(tmp_path, monkeypatch):
    claim = _claim("GOOG-2026Q2-capex-CY2026-001")
    d = tmp_path / "data" / "goog" / "q2-2026"
    d.mkdir(parents=True)
    (d / "facts.json").write_text(json.dumps({"ticker": "GOOG", "claims": [claim]}))
    monkeypatch.setattr("eca.config.project_root", lambda: tmp_path)
    from eca.claims import ClaimValidationError
    with pytest.raises(ClaimValidationError, match="source transcript missing"):
        rebuild_index(tmp_path / "data" / "eca.db")


def test_supersession_chain_indexed(tmp_path, monkeypatch):
    older = _claim("GOOG-2026Q1-capex-CY2026-001", value_low_m=180000, value_high_m=190000,
                   as_of="2026-04-29", source_path="data/goog/q1-2026/transcript.txt")
    _make_claim_facts(tmp_path, "GOOG", "q1-2026", [older])
    newer = _claim("GOOG-2026Q2-capex-CY2026-001", supersedes_id=older["id"])
    _make_claim_facts(tmp_path, "GOOG", "q2-2026", [newer])
    db_path = _rebuild(tmp_path, monkeypatch)
    conn = sqlite3.connect(db_path)
    sup = conn.execute(
        "SELECT ticker, id FROM claims WHERE supersedes_id IS NOT NULL").fetchall()
    target = conn.execute(
        "SELECT id FROM claims WHERE id = ?", (older["id"],)).fetchone()
    conn.close()
    assert sup == [("GOOG", newer["id"])]
    assert target == (older["id"],)
