import json
from pathlib import Path

from eca.processors.dashboard import (
    load_latest_signals,
    render_waterfall_section,
    render_phase_x_section,
    render_score_trajectories,
    render_capex_landscape,
    render_signal_detail,
    render_dashboard,
)


def _write_facts(data_dir, ticker, quarter, facts):
    d = data_dir / ticker.lower() / quarter
    d.mkdir(parents=True)
    (d / "facts.json").write_text(json.dumps(facts))


def test_load_latest_signals(tmp_path, monkeypatch):
    monkeypatch.setattr("eca.config.project_root", lambda: tmp_path)
    data = tmp_path / "data"

    _write_facts(data, "WMT", "q3-2025", {
        "ticker": "WMT",
        "signals": {"consumer_stress_tier": "neutral", "pricing_power": "strong"},
    })
    _write_facts(data, "WMT", "q4-2025", {
        "ticker": "WMT",
        "signals": {"consumer_stress_tier": "trade_down", "pricing_power": "moderate"},
    })
    _write_facts(data, "COST", "q4-2025", {
        "ticker": "COST",
        "candor": {"composite_score": 3.0},
    })

    result = load_latest_signals()
    # Should pick q4-2025 for WMT (latest with signals)
    assert "WMT" in result
    assert result["WMT"]["signals"]["consumer_stress_tier"] == "trade_down"
    # COST has no signals, should not be in result
    assert "COST" not in result


def test_render_waterfall_section():
    from eca.engine.waterfall import StageResult
    stages = [
        StageResult("stage_1", "Discretionary Cuts", True, ["TGT", "ABNB"], {}, "2/3"),
        StageResult("stage_2", "Essential Trade-Down", False, [], {}, "0/2"),
    ]
    output = render_waterfall_section(stages)
    assert "FIRING" in output
    assert "Discretionary Cuts" in output
    assert "TGT, ABNB" in output
    assert "NOT FIRING" in output


def test_render_phase_x_section():
    output = render_phase_x_section(False, 2, 7)
    assert "Pre-stress" in output
    assert "2/7" in output

    output_px = render_phase_x_section(True, 5, 7)
    assert "Phase X" in output_px


def test_render_score_trajectories(tmp_path, monkeypatch):
    monkeypatch.setattr("eca.config.project_root", lambda: tmp_path)
    data = tmp_path / "data"
    _write_facts(data, "WMT", "q1-2025", {
        "ticker": "WMT",
        "candor": {"composite_score": 2.5, "composite_grade": "B"},
    })
    _write_facts(data, "WMT", "q2-2025", {
        "ticker": "WMT",
        "candor": {"composite_score": 2.8, "composite_grade": "B"},
    })

    from eca.db import rebuild_index
    db_path = data / "eca.db"
    rebuild_index(db_path)

    output = render_score_trajectories(db_path)
    assert "WMT" in output


def test_render_capex_landscape(tmp_path, monkeypatch):
    monkeypatch.setattr("eca.config.project_root", lambda: tmp_path)
    data = tmp_path / "data"
    _write_facts(data, "NVDA", "q4-2025", {
        "ticker": "NVDA",
        "metrics": {"capital_expenditure_m": 5000.0},
    })

    from eca.db import rebuild_index
    db_path = data / "eca.db"
    rebuild_index(db_path)

    output = render_capex_landscape(db_path)
    assert "NVDA" in output


def test_render_signal_detail():
    facts = {
        "WMT": {"signals": {
            "consumer_stress_tier": "trade_down",
            "pricing_power": "moderate",
            "management_tone_shift": "consistent",
            "signal_evidence": {
                "consumer_stress_tier": "Guests are stretching budgets",
                "pricing_power": "We lowered prices on thousands of items",
            },
        }},
    }
    output = render_signal_detail(facts)
    assert "WMT" in output
    assert "trade_down" in output
    assert "Guests are stretching" in output


def test_render_dashboard_full(tmp_path, monkeypatch):
    monkeypatch.setattr("eca.config.project_root", lambda: tmp_path)
    data = tmp_path / "data"
    _write_facts(data, "WMT", "q4-2025", {
        "ticker": "WMT",
        "candor": {"composite_score": 3.0, "composite_grade": "B"},
        "signals": {
            "consumer_stress_tier": "trade_down",
            "pricing_power": "moderate",
            "management_tone_shift": "consistent",
            "signal_evidence": {"consumer_stress_tier": "Budget-stretching behavior noted"},
        },
    })

    from eca.db import rebuild_index
    db_path = data / "eca.db"
    rebuild_index(db_path)

    output = render_dashboard(db_path)
    assert "Consumer Health Dashboard" in output
    assert "Distress Waterfall" in output
    assert "Phase X Assessment" in output
    assert "Market Context" in output
