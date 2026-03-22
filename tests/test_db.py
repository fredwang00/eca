import json
import shutil
import sqlite3
from pathlib import Path

from eca.db import rebuild_index, connect_db


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
