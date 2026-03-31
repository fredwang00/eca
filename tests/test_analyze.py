import json
from pathlib import Path

from eca.processors.analyze import (
    build_system_prompt,
    build_user_message,
    extract_and_update_facts,
    find_prior_analysis,
)

MOCK_OUTPUT = """# Earnings Call Candor Analysis
## Company: Root, Inc. | Quarter: Q3 2025 | Date: November 4, 2025

### 1. Capital Stewardship & Financial Candor
**Grade: C**

### 2. Strategic Clarity & Accountability
**Grade: C+**

### 3. Stakeholder Balance & Culture Signals
**Grade: C-**

### 4. FOG Index -- Linguistic Quality of Disclosure
**Grade: C**

### 5. Vision, Leadership & Long-Term Orientation
**Grade: C**

---

### Composite Grade: C
**Calculation:** (C [2.0] x 0.25) + (C+ [2.3] x 0.25) + (C- [1.7] x 0.15) + (C [2.0] x 0.20) + (C [2.0] x 0.15) = **2.03** -> C
"""


def test_build_system_prompt_base_only(tmp_path):
    skills = tmp_path / "skills"
    skills.mkdir()
    (skills / "base.md").write_text("Base instructions.")

    prompt = build_system_prompt(skills, "base")
    assert "Base instructions." in prompt


def test_build_system_prompt_with_supplement(tmp_path):
    skills = tmp_path / "skills"
    skills.mkdir()
    (skills / "base.md").write_text("Base.")
    (skills / "insurtech.md").write_text("Insurtech supplement.")

    prompt = build_system_prompt(skills, "insurtech")
    assert "Base." in prompt
    assert "Insurtech supplement." in prompt


def test_build_user_message_without_metrics():
    msg = build_user_message("Transcript text.", None)
    assert msg == "Transcript text."


def test_build_user_message_with_metrics():
    metrics = {"revenue_m": 387.8, "operating_income_m": -5.0}
    msg = build_user_message("Transcript.", metrics)
    assert "Financial ground truth" in msg
    assert "387.8" in msg
    assert "Transcript." in msg


def test_build_user_message_with_prior_analysis():
    prior = "### Composite Grade: C\nPrior quarter was rough."
    msg = build_user_message("New transcript.", None, prior_analysis=prior)
    assert "Prior quarter analysis" in msg
    assert "cross-quarter comparison" in msg
    assert "Composite Grade: C" in msg
    assert "New transcript." in msg


def test_build_user_message_with_metrics_and_prior():
    metrics = {"revenue_m": 500.0}
    prior = "### Composite Grade: B\nGood quarter."
    msg = build_user_message("Transcript.", metrics, prior_analysis=prior)
    assert "Prior quarter analysis" in msg
    assert "Financial ground truth" in msg
    assert "Transcript." in msg
    # Prior comes before metrics, metrics before transcript
    prior_pos = msg.index("Prior quarter")
    metrics_pos = msg.index("Financial ground truth")
    transcript_pos = msg.index("Transcript.")
    assert prior_pos < metrics_pos < transcript_pos


def test_find_prior_analysis(tmp_path, monkeypatch):
    monkeypatch.setattr("eca.config.data_dir", lambda: tmp_path)

    ticker_dir = tmp_path / "root"
    for q, content in [
        ("q1-2025", "Q1 analysis"),
        ("q2-2025", "Q2 analysis"),
        ("q3-2025", None),  # no analysis yet
    ]:
        d = ticker_dir / q
        d.mkdir(parents=True)
        if content:
            (d / "analysis.md").write_text(content)

    # q3 should find q2 as prior
    assert find_prior_analysis("ROOT", "q3-2025") == "Q2 analysis"

    # q2 should find q1 as prior
    assert find_prior_analysis("ROOT", "q2-2025") == "Q1 analysis"

    # q1 has no prior
    assert find_prior_analysis("ROOT", "q1-2025") is None


def test_find_prior_analysis_no_data(tmp_path, monkeypatch):
    monkeypatch.setattr("eca.config.data_dir", lambda: tmp_path)
    assert find_prior_analysis("MISSING", "q1-2025") is None


def test_extract_and_update_facts(tmp_path):
    facts_path = tmp_path / "facts.json"
    facts_path.write_text(json.dumps({"ticker": "ROOT", "quarter": "Q3 2025"}))

    extract_and_update_facts(facts_path, MOCK_OUTPUT, "base+insurtech")

    facts = json.loads(facts_path.read_text())
    assert facts["candor"]["dim1_grade"] == "C"
    assert facts["candor"]["composite_grade"] == "C"
    assert facts["candor"]["composite_score"] == 2.03
    assert facts["candor"]["skill_version"] == "base+insurtech"


MOCK_OUTPUT_WITH_SIGNALS = MOCK_OUTPUT + """
### Tracking Notes for Future Evaluations
Watch for continued trade-down behavior next quarter.

```SIGNALS
{
  "consumer_stress_tier": "trade_down",
  "credit_quality_trend": null,
  "auto_credit_trend": null,
  "housing_demand": null,
  "services_demand": null,
  "capex_direction": null,
  "pricing_power": "moderate",
  "management_tone_shift": "more_cautious",
  "signal_evidence": {
    "consumer_stress_tier": "Guests are stretching budgets...",
    "pricing_power": "We lowered prices on thousands of items...",
    "management_tone_shift": "Sentiment is at a 3-year low..."
  }
}
```
"""


def test_extract_and_update_facts_with_signals(tmp_path):
    facts_path = tmp_path / "facts.json"
    facts_path.write_text(json.dumps({"ticker": "ROOT", "quarter": "Q3 2025"}))

    extract_and_update_facts(facts_path, MOCK_OUTPUT_WITH_SIGNALS, "base")

    facts = json.loads(facts_path.read_text())
    assert "signals" in facts
    assert facts["signals"]["consumer_stress_tier"] == "trade_down"
    assert facts["signals"]["credit_quality_trend"] is None
    assert facts["signals"]["pricing_power"] == "moderate"
    assert "extracted_at" in facts["signals"]
    assert "consumer_stress_tier" in facts["signals"]["signal_evidence"]


def test_extract_and_update_facts_no_signals(tmp_path):
    """When analysis has no SIGNALS block, signals key should not be added."""
    facts_path = tmp_path / "facts.json"
    facts_path.write_text(json.dumps({"ticker": "IREN", "quarter": "Q1 2026"}))

    extract_and_update_facts(facts_path, MOCK_OUTPUT, "base")

    facts = json.loads(facts_path.read_text())
    assert "signals" not in facts
