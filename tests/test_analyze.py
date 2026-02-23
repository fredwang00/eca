import json
from pathlib import Path

from eca.processors.analyze import (
    build_system_prompt,
    build_user_message,
    extract_and_update_facts,
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


def test_extract_and_update_facts(tmp_path):
    facts_path = tmp_path / "facts.json"
    facts_path.write_text(json.dumps({"ticker": "ROOT", "quarter": "Q3 2025"}))

    extract_and_update_facts(facts_path, MOCK_OUTPUT, "base+insurtech")

    facts = json.loads(facts_path.read_text())
    assert facts["candor"]["dim1_grade"] == "C"
    assert facts["candor"]["composite_grade"] == "C"
    assert facts["candor"]["composite_score"] == 2.03
    assert facts["candor"]["skill_version"] == "base+insurtech"
