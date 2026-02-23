import json
from pathlib import Path

from eca.processors.query import load_all_facts, query_grades, query_flags


def _create_facts(root: Path, ticker: str, quarter: str, facts: dict):
    d = root / "data" / ticker.lower() / quarter
    d.mkdir(parents=True)
    (d / "facts.json").write_text(json.dumps(facts))


def test_load_all_facts(tmp_path, monkeypatch):
    monkeypatch.setattr("eca.config.project_root", lambda: tmp_path)
    _create_facts(tmp_path, "ROOT", "q1-2025", {"ticker": "ROOT", "quarter": "Q1 2025"})
    _create_facts(tmp_path, "ROOT", "q2-2025", {"ticker": "ROOT", "quarter": "Q2 2025"})
    _create_facts(tmp_path, "LMND", "q1-2025", {"ticker": "LMND", "quarter": "Q1 2025"})

    all_facts = load_all_facts()
    assert len(all_facts) == 3


def test_query_grades(tmp_path, monkeypatch):
    monkeypatch.setattr("eca.config.project_root", lambda: tmp_path)
    _create_facts(tmp_path, "ROOT", "q1-2025", {
        "ticker": "ROOT", "quarter": "Q1 2025",
        "candor": {"dim1_grade": "C+", "composite_grade": "C", "composite_score": 2.355},
    })
    _create_facts(tmp_path, "ROOT", "q2-2025", {
        "ticker": "ROOT", "quarter": "Q2 2025",
        "candor": {"dim1_grade": "C+", "composite_grade": "C", "composite_score": 2.31},
    })

    result = query_grades("ROOT")
    assert len(result) == 2
    assert result[0]["quarter"] == "Q1 2025"
    assert result[0]["composite_grade"] == "C"


def test_query_flags(tmp_path, monkeypatch):
    monkeypatch.setattr("eca.config.project_root", lambda: tmp_path)
    _create_facts(tmp_path, "ROOT", "q1-2025", {
        "ticker": "ROOT", "quarter": "Q1 2025", "flags": ["bvps_absent", "roe_absent"],
    })
    _create_facts(tmp_path, "ROOT", "q2-2025", {
        "ticker": "ROOT", "quarter": "Q2 2025", "flags": ["bvps_absent"],
    })
    _create_facts(tmp_path, "LMND", "q1-2025", {
        "ticker": "LMND", "quarter": "Q1 2025", "flags": [],
    })

    result = query_flags("bvps_absent")
    assert len(result) == 2
    assert all(r["ticker"] == "ROOT" for r in result)


def test_query_grades_unknown_ticker(tmp_path, monkeypatch):
    monkeypatch.setattr("eca.config.project_root", lambda: tmp_path)
    assert query_grades("UNKNOWN") == []
