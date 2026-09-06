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


def test_ingest_metrics_preserves_values_yfinance_later_drops(tmp_path, monkeypatch):
    """Regression: Yahoo Finance's quarterly-financials window can silently
    return None for a field a previous fetch had already captured (e.g. Basic
    EPS aging out of the trailing window). A second ingest-metrics run must
    not let that None overwrite the previously-good value, in either
    metrics-raw.json or a quarter's facts.json."""
    qdir = tmp_path / "data" / "root" / "q3-2024"
    qdir.mkdir(parents=True)
    (qdir / "facts.json").write_text(json.dumps({"ticker": "ROOT", "quarter": "Q3 2024"}))

    monkeypatch.setattr("eca.config.project_root", lambda: tmp_path)
    monkeypatch.setattr(
        "eca.processors.ingest_metrics.fetch_quarterly_metrics",
        lambda ticker: MOCK_QUARTERS,
    )
    CliRunner().invoke(cli, ["ingest-metrics", "root"])

    stale_fetch = {
        "Q3 2024": {
            "revenue_m": 390.0,  # a real, updated value -- should win
            "gross_profit_m": None,  # dropped by yfinance this time -- must NOT overwrite 81.4
            "operating_income_m": -5.0,
            "total_equity_m": 265.0, "shares_outstanding_m": 15.53,
            "free_cash_flow_m": 53.7, "bvps": 17.06,
        },
    }
    monkeypatch.setattr(
        "eca.processors.ingest_metrics.fetch_quarterly_metrics",
        lambda ticker: stale_fetch,
    )
    CliRunner().invoke(cli, ["ingest-metrics", "root"])

    facts = json.loads((qdir / "facts.json").read_text())
    assert facts["metrics"]["revenue_m"] == 390.0
    assert facts["metrics"]["gross_profit_m"] == 81.4

    raw = json.loads((tmp_path / "data" / "root" / "metrics-raw.json").read_text())
    assert raw["quarters"]["Q3 2024"]["gross_profit_m"] == 81.4
    assert raw["quarters"]["Q3 2024"]["revenue_m"] == 390.0
    # Q4 2024 was in the first fetch but absent from the second -- must survive untouched.
    assert raw["quarters"]["Q4 2024"]["revenue_m"] == 405.0


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
