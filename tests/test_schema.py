import json
from pathlib import Path

from eca.schema import Facts, load_facts, save_facts


def test_load_facts_missing_file(tmp_path):
    path = tmp_path / "facts.json"
    result = load_facts(path)
    assert result == {}


def test_save_and_load_round_trip(tmp_path):
    path = tmp_path / "sub" / "facts.json"
    facts: Facts = {
        "company": "Root, Inc.",
        "ticker": "ROOT",
        "quarter": "Q3 2025",
        "call_date": "2025-11-04",
        "metrics": {"source": "yfinance", "revenue_m": 387.8},
        "candor": {"composite_grade": "C", "composite_score": 2.03},
        "flags": ["bvps_absent"],
        "tracking": ["Monitor BVPS trajectory"],
    }
    save_facts(path, facts)
    loaded = load_facts(path)
    assert loaded["ticker"] == "ROOT"
    assert loaded["metrics"]["revenue_m"] == 387.8
    assert loaded["flags"] == ["bvps_absent"]


def test_save_creates_parent_dirs(tmp_path):
    path = tmp_path / "a" / "b" / "c" / "facts.json"
    save_facts(path, {"ticker": "TEST"})
    assert path.exists()


def test_save_overwrites_existing(tmp_path):
    path = tmp_path / "facts.json"
    save_facts(path, {"ticker": "OLD"})
    save_facts(path, {"ticker": "NEW"})
    loaded = load_facts(path)
    assert loaded["ticker"] == "NEW"
