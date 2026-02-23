import json
from pathlib import Path
from click.testing import CliRunner

from eca.cli import cli

MOCK_QUARTERS = {
    "Q3 2024": {
        "revenue_m": 387.8, "gross_profit_m": 81.4, "operating_income_m": -5.0,
        "total_equity_m": 265.0, "shares_outstanding_m": 15.53,
        "free_cash_flow_m": 53.7, "bvps": 17.06,
    },
    "Q4 2024": {
        "revenue_m": 405.0, "gross_profit_m": 110.0, "operating_income_m": 0.3,
        "total_equity_m": 270.0, "shares_outstanding_m": 15.6,
        "free_cash_flow_m": 40.0, "bvps": 17.31,
    },
    "Q3 2023": {
        "revenue_m": 250.0, "total_equity_m": 300.0,
    },
}


def test_ingest_metrics_creates_raw_file(tmp_path, monkeypatch):
    monkeypatch.setattr("eca.config.project_root", lambda: tmp_path)
    monkeypatch.setattr(
        "eca.processors.ingest_metrics.fetch_quarterly_metrics",
        lambda ticker: MOCK_QUARTERS,
    )
    result = CliRunner().invoke(cli, ["ingest-metrics", "root"])
    assert result.exit_code == 0
    raw_path = tmp_path / "data" / "root" / "metrics-raw.json"
    assert raw_path.exists()
    raw = json.loads(raw_path.read_text())
    assert raw["ticker"] == "ROOT"
    assert "Q3 2024" in raw["quarters"]


def test_ingest_metrics_updates_existing_facts(tmp_path, monkeypatch):
    monkeypatch.setattr("eca.config.project_root", lambda: tmp_path)
    monkeypatch.setattr(
        "eca.processors.ingest_metrics.fetch_quarterly_metrics",
        lambda ticker: MOCK_QUARTERS,
    )
    qdir = tmp_path / "data" / "root" / "q3-2024"
    qdir.mkdir(parents=True)
    (qdir / "facts.json").write_text(json.dumps({"ticker": "ROOT", "quarter": "Q3 2024"}))
    CliRunner().invoke(cli, ["ingest-metrics", "root"])
    facts = json.loads((qdir / "facts.json").read_text())
    assert facts["metrics"]["revenue_m"] == 387.8
    assert facts["ticker"] == "ROOT"


def test_ingest_metrics_adds_equity_declining_flag(tmp_path, monkeypatch):
    monkeypatch.setattr("eca.config.project_root", lambda: tmp_path)
    monkeypatch.setattr(
        "eca.processors.ingest_metrics.fetch_quarterly_metrics",
        lambda ticker: MOCK_QUARTERS,
    )
    qdir = tmp_path / "data" / "root" / "q3-2024"
    qdir.mkdir(parents=True)
    (qdir / "facts.json").write_text(json.dumps({"ticker": "ROOT", "quarter": "Q3 2024"}))
    CliRunner().invoke(cli, ["ingest-metrics", "root"])
    facts = json.loads((qdir / "facts.json").read_text())
    assert "equity_declining_yoy" in facts.get("flags", [])
