import json
from pathlib import Path

from eca.processors.synthesize import build_brief_input, ticker_brief


def test_build_brief_input_includes_analyses(tmp_path, monkeypatch):
    monkeypatch.setattr("eca.config.project_root", lambda: tmp_path)
    d = tmp_path / "data" / "iren" / "q1-2025"
    d.mkdir(parents=True)
    (d / "analysis.md").write_text("# Analysis Q1")
    (d / "facts.json").write_text('{"ticker":"IREN","quarter":"Q1 2025"}')

    result = build_brief_input("IREN")
    assert "# Analysis Q1" in result
    assert "Q1 2025" in result


def test_build_brief_input_chronological_order(tmp_path, monkeypatch):
    monkeypatch.setattr("eca.config.project_root", lambda: tmp_path)
    for q in ["q2-2025", "q4-2024", "q1-2025"]:
        d = tmp_path / "data" / "iren" / q
        d.mkdir(parents=True)
        (d / "analysis.md").write_text(f"# Analysis {q}")
        (d / "facts.json").write_text(f'{{"ticker":"IREN","quarter":"{q}"}}')

    result = build_brief_input("IREN")
    pos_q4 = result.index("q4-2024")
    pos_q1 = result.index("q1-2025")
    pos_q2 = result.index("q2-2025")
    assert pos_q4 < pos_q1 < pos_q2


def test_build_brief_input_skips_unanalyzed(tmp_path, monkeypatch):
    monkeypatch.setattr("eca.config.project_root", lambda: tmp_path)
    d = tmp_path / "data" / "iren" / "q1-2025"
    d.mkdir(parents=True)
    (d / "facts.json").write_text('{"ticker":"IREN"}')

    result = build_brief_input("IREN")
    assert result is None


def test_ticker_brief_writes_output(tmp_path, monkeypatch):
    monkeypatch.setattr("eca.config.project_root", lambda: tmp_path)
    monkeypatch.setattr("eca.llm.run_analysis", lambda sys, usr, model="": "# Mock Brief")

    d = tmp_path / "data" / "iren" / "q1-2025"
    d.mkdir(parents=True)
    (d / "analysis.md").write_text("# Analysis")
    (d / "facts.json").write_text('{"ticker":"IREN"}')

    skills = tmp_path / "skills"
    skills.mkdir()
    (skills / "synthesis-brief.md").write_text("You are a financial analyst.")

    result = ticker_brief("IREN", model="test-model")
    assert result is not None
    assert result.name == "brief.md"
    assert result.read_text() == "# Mock Brief"


from eca.processors.synthesize import build_sector_input, sector_synthesis


def test_build_sector_input(tmp_path, monkeypatch):
    monkeypatch.setattr("eca.config.project_root", lambda: tmp_path)

    for ticker in ["iren", "cifr"]:
        d = tmp_path / "data" / ticker
        d.mkdir(parents=True)
        (d / "brief.md").write_text(f"# {ticker.upper()} Brief\nSome analysis.")
        q = d / "q1-2025"
        q.mkdir()
        (q / "facts.json").write_text(json.dumps({
            "ticker": ticker.upper(),
            "metrics": {"revenue_m": 100.0, "capital_expenditure_m": 50.0},
        }))

    from eca.db import rebuild_index, connect_db
    db_path = tmp_path / "data" / "eca.db"
    rebuild_index(db_path)

    conn = connect_db(db_path)
    result = build_sector_input("infra", conn)
    conn.close()

    assert "IREN Brief" in result
    assert "CIFR Brief" in result
    assert "Financial Summary" in result


def test_sector_synthesis_writes_output(tmp_path, monkeypatch):
    monkeypatch.setattr("eca.config.project_root", lambda: tmp_path)
    monkeypatch.setattr("eca.llm.run_analysis", lambda sys, usr, model="": "# Infra Synthesis")

    d = tmp_path / "data" / "iren"
    d.mkdir(parents=True)
    (d / "brief.md").write_text("# IREN Brief")
    q = d / "q1-2025"
    q.mkdir()
    (q / "facts.json").write_text(json.dumps({"ticker": "IREN", "metrics": {"revenue_m": 240.0}}))

    from eca.db import rebuild_index
    db_path = tmp_path / "data" / "eca.db"
    rebuild_index(db_path)

    skills = tmp_path / "skills"
    skills.mkdir()
    (skills / "synthesis-sector.md").write_text("You are a macro analyst.")

    result = sector_synthesis("infra", model="test-model")
    assert result is not None
    assert "infra-" in result.name
    assert result.read_text() == "# Infra Synthesis"
