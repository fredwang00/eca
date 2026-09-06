from eca.parsers.grades import parse_grades, parse_signals

SAMPLE_ROOT = """# Earnings Call Candor Analysis
## Company: Root, Inc. | Quarter: Q3 2025 | Date: November 4, 2025

### Executive Summary
Some text here.

### 1. Capital Stewardship & Financial Candor
**Grade: C**

Some analysis.

### 2. Strategic Clarity & Accountability
**Grade: C+**

Some analysis.

### 3. Stakeholder Balance & Culture Signals
**Grade: C-**

Some analysis.

### 4. FOG Index -- Linguistic Quality of Disclosure
**Grade: C**

Some analysis.

### 5. Vision, Leadership & Long-Term Orientation
**Grade: C**

Some analysis.

---

### Composite Grade: C
**Calculation:** (C [2.0] x 0.25) + (C+ [2.3] x 0.25) + (C- [1.7] x 0.15) + (C [2.0] x 0.20) + (C [2.0] x 0.15) = **2.03** -> C
"""

SAMPLE_LMND = """### 1. Capital Stewardship & Financial Candor
**Grade: B+**

### 2. Strategic Clarity & Accountability
**Grade: A**

### 3. Stakeholder Balance & Culture Signals
**Grade: B**

### 4. FOG Index -- Linguistic Quality of Disclosure
**Grade: B**

### 5. Vision, Leadership & Long-Term Orientation
**Grade: B**

---

### Composite Grade: B
**Calculation:** (B+ [3.3] x 0.25) + (A [4.0] x 0.25) + (B [3.0] x 0.15) + (B [3.0] x 0.20) + (B [3.0] x 0.15) = **3.325** -> B
"""

SAMPLE_SPOT = """### Composite Grade: B
**Calculation:** (B 3.0 x 0.25) + (B 3.0 x 0.25) + (B- 2.7 x 0.15) + (C+ 2.3 x 0.20) + (B 3.0 x 0.15) = 2.815 -> B
"""


def test_parse_dimension_grades():
    result = parse_grades(SAMPLE_ROOT)
    assert result["dim1_grade"] == "C"
    assert result["dim2_grade"] == "C+"
    assert result["dim3_grade"] == "C-"
    assert result["dim4_grade"] == "C"
    assert result["dim5_grade"] == "C"


def test_parse_composite():
    result = parse_grades(SAMPLE_ROOT)
    assert result["composite_grade"] == "C"
    assert result["composite_score"] == 2.03


def test_parse_lmnd_grades():
    result = parse_grades(SAMPLE_LMND)
    assert result["dim1_grade"] == "B+"
    assert result["dim2_grade"] == "A"
    assert result["composite_grade"] == "B"
    assert result["composite_score"] == 3.325


def test_parse_spot_score_format():
    """Score without bold markers, arrow format varies."""
    result = parse_grades(SAMPLE_SPOT)
    assert result["composite_grade"] == "B"
    assert result["composite_score"] == 2.815


SAMPLE_IREN = """### 1. Capital Stewardship & Financial Candor
**Grade: B+**

### 2. Strategic Clarity & Accountability
**Grade: B**

### 3. Stakeholder Balance & Culture Signals
**Grade: C+**

### 4. FOG Index
**Grade: B-**

### 5. Vision, Leadership & Long-Term Orientation
**Grade: A-**

---

### Composite Grade: B+

**Calculation:**
- Dimension 1 (Capital Stewardship): B+ → scored as 3.3 × 0.25 = 0.825
- Dimension 2 (Strategic Clarity): B → 3.0 × 0.25 = 0.750
- Dimension 3 (Stakeholder Balance): C+ → scored as 2.3 × 0.15 = 0.345
- Dimension 4 (FOG Index): B- → scored as 2.7 × 0.20 = 0.540
- Dimension 5 (Vision & Leadership): A- → scored as 3.7 × 0.15 = 0.555

**Weighted Total: 3.015 → Composite Grade: B**
"""


SAMPLE_WEIGHTED_SCORE = """### 1. Capital Stewardship & Financial Candor
**Grade: B**

### 2. Strategic Clarity & Accountability
**Grade: B**

### 3. Stakeholder Balance & Culture Signals
**Grade: C**

### 4. FOG Index
**Grade: C**

### 5. Vision, Leadership & Long-Term Orientation
**Grade: B**

---

### Composite Grade: B

**Weighted Score: 0.75 + 0.75 + 0.30 + 0.40 + 0.45 = 2.65 → B**
"""


def test_parse_weighted_total_format():
    """'Weighted Total:' should extract the final score,
    not individual dimension contributions."""
    result = parse_grades(SAMPLE_IREN)
    assert result["composite_grade"] == "B+"
    assert result["composite_score"] == 3.015
    assert result["dim1_grade"] == "B+"
    assert result["dim5_grade"] == "A-"


def test_parse_weighted_score_sum_format():
    """'Weighted Score: x + y + ... = total →' should extract the total after =."""
    result = parse_grades(SAMPLE_WEIGHTED_SCORE)
    assert result["composite_grade"] == "B"
    assert result["composite_score"] == 2.65


SAMPLE_BOLD_WRAPPED_GRADE = """### 1. Capital Stewardship & Financial Candor
**Grade: A-**

### 2. Strategic Clarity & Accountability
**Grade: B-**

### 3. Stakeholder Balance & Culture Signals
**Grade: B**

### 4. FOG Index
**Grade: C**

### 5. Vision, Leadership & Long-Term Orientation
**Grade: B**

---

### Composite Grade

| Dimension | Grade | Score | Weight | Weighted |
|-----------|-------|-------|--------|---------|
| 1. Capital Stewardship & Financial Candor | B | 3.0 | 25% | 0.75 |
| 2. Strategic Clarity & Accountability | B | 3.0 | 25% | 0.75 |
| 3. Stakeholder Balance & Culture Signals | B | 3.0 | 15% | 0.45 |
| 4. FOG Index | C | 2.0 | 20% | 0.40 |
| 5. Vision, Leadership & Long-Term Orientation | B | 3.0 | 15% | 0.45 |

**Calculation:** (3.0 x 0.25) + (3.0 x 0.25) + (3.0 x 0.15) + (2.0 x 0.20) + (3.0 x 0.15) = 0.75 + 0.75 + 0.45 + 0.40 + 0.45 = **2.80 -> B**

### Composite Grade: **B**

---

### Communication-Level Risks
"""


def test_parse_bold_wrapped_composite_grade():
    """Real-world regression (GOOG q2-2026): a duplicate, bare '### Composite
    Grade' heading precedes the calculation, and the actual letter grade only
    appears later wrapped in markdown bold ('### Composite Grade: **B**').
    Both the grade and the score (buried in a '**Calculation:**' line, not a
    'Weighted Total/Score' line) must still be extracted."""
    result = parse_grades(SAMPLE_BOLD_WRAPPED_GRADE)
    assert result["composite_grade"] == "B"
    assert result["composite_score"] == 2.80


SAMPLE_INLINE_GRADE_NO_HEADING = """### 1. Capital Stewardship & Financial Candor
**Grade: A**

### 2. Strategic Clarity & Accountability
**Grade: A**

### 3. Stakeholder Balance & Culture Signals
**Grade: B**

### 4. FOG Index
**Grade: B**

### 5. Vision, Leadership & Long-Term Orientation
**Grade: A**

---

### Composite Grade
**Calculation:**
- Dim1 (Capital Stewardship): A = 4.0 x 0.25 = 1.000
- Dim2 (Strategic Clarity): A = 4.0 x 0.25 = 1.000
- Dim3 (Stakeholder Balance): B = 3.0 x 0.15 = 0.450
- Dim4 (FOG Index): B = 3.0 x 0.20 = 0.600
- Dim5 (Vision & Leadership): A = 4.0 x 0.15 = 0.600

**Weighted Score: 3.65 -> Composite Grade: A**

---

### Communication-Level Risks
"""


def test_parse_inline_composite_grade_no_heading():
    """Real-world regression (MSFT q3-2026): the '### Composite Grade' heading
    is bare (no colon, no grade), and the actual grade only appears inline
    later in a '**Weighted Score: X -> Composite Grade: Y**' line with no
    '###' prefix at all."""
    result = parse_grades(SAMPLE_INLINE_GRADE_NO_HEADING)
    assert result["composite_grade"] == "A"
    assert result["composite_score"] == 3.65


SAMPLE_RESTATED_DIM_GRADE = """### 1. Capital Stewardship & Financial Candor
**Grade: A-/B+**

The CFO provides specific, anchored financial data throughout. However, there
is no explicit revisiting of prior-quarter guidance. The absence of a bridge
from prior commitments to current results costs them the top grade.

**Grade: B+**

### 2. Strategic Clarity & Accountability
**Grade: B**

Some analysis.

### 3. Stakeholder Balance & Culture Signals
**Grade: C+**

Some analysis.

### 4. FOG Index
**Grade: C+**

Some analysis.

### 5. Vision, Leadership & Long-Term Orientation
**Grade: B-**

Some analysis.

---

### Composite Grade: B
**Calculation:**

| Dimension | Grade | Score | Weight | Weighted |
|-----------|-------|-------|--------|----------|
| 1. Capital Stewardship | B+ | 3.3 | 0.25 | 0.825 |
| 2. Strategic Clarity | B | 3.0 | 0.25 | 0.750 |
| 3. Stakeholder Balance | C+ | 2.3 | 0.15 | 0.345 |
| 4. FOG Index | C+ | 2.3 | 0.20 | 0.460 |
| 5. Vision & Leadership | B- | 2.7 | 0.15 | 0.405 |

**Composite = 0.825 + 0.750 + 0.345 + 0.460 + 0.405 = 2.785 --> B**
"""


def test_parse_restated_dimension_grade_takes_last():
    """Real-world regression (GOOG q4-2025, SPOT q3-2025): a dimension section
    states a preliminary (sometimes split, e.g. 'A-/B+') grade right after the
    heading, then restates a single, more considered grade at the end of the
    same section's prose. The LLM's own composite calculation always uses the
    later, restated grade -- so the parser must take the LAST 'Grade:' line
    within a dimension's section, not the first."""
    result = parse_grades(SAMPLE_RESTATED_DIM_GRADE)
    assert result["dim1_grade"] == "B+"
    assert result["dim2_grade"] == "B"
    assert result["dim3_grade"] == "C+"
    assert result["dim4_grade"] == "C+"
    assert result["dim5_grade"] == "B-"
    assert result["composite_grade"] == "B"
    assert result["composite_score"] == 2.785


def test_parse_header_metadata():
    result = parse_grades(SAMPLE_ROOT)
    assert result["company"] == "Root, Inc."
    assert result["quarter"] == "Q3 2025"
    assert result["call_date"] == "November 4, 2025"


# --- Signal parser tests ---

SAMPLE_SIGNALS_BLOCK = """### Tracking Notes for Future Evaluations
Some tracking notes here.

```SIGNALS
{
  "consumer_stress_tier": "trade_down",
  "credit_quality_trend": null,
  "auto_credit_trend": null,
  "housing_demand": null,
  "services_demand": null,
  "capex_direction": "stable",
  "pricing_power": "moderate",
  "management_tone_shift": "more_cautious",
  "signal_evidence": {
    "consumer_stress_tier": "Guests are choiceful, stretching budgets...",
    "capex_direction": "We plan to maintain our current capital expenditure run-rate...",
    "pricing_power": "We recently lowered prices on thousands of items...",
    "management_tone_shift": "Sentiment is at a 3-year low..."
  }
}
```
"""

SAMPLE_NO_SIGNALS = """### Tracking Notes
Just some notes, no signals block.
"""

SAMPLE_SIGNALS_NULLS_ONLY = """```SIGNALS
{
  "consumer_stress_tier": null,
  "credit_quality_trend": null,
  "auto_credit_trend": null,
  "housing_demand": null,
  "services_demand": null,
  "capex_direction": "accelerating",
  "pricing_power": "strong",
  "management_tone_shift": "more_confident",
  "signal_evidence": {
    "capex_direction": "We are doubling our GPU fleet...",
    "pricing_power": "We raised prices 10% with no churn impact...",
    "management_tone_shift": "We have never been more optimistic..."
  }
}
```
"""


def test_parse_signals_full():
    result = parse_signals(SAMPLE_SIGNALS_BLOCK)
    assert result is not None
    assert result["consumer_stress_tier"] == "trade_down"
    assert result["credit_quality_trend"] is None
    assert result["capex_direction"] == "stable"
    assert result["pricing_power"] == "moderate"
    assert result["management_tone_shift"] == "more_cautious"
    assert "consumer_stress_tier" in result["signal_evidence"]
    assert "Guests are choiceful" in result["signal_evidence"]["consumer_stress_tier"]


def test_parse_signals_missing():
    result = parse_signals(SAMPLE_NO_SIGNALS)
    assert result is None


def test_parse_signals_nulls():
    result = parse_signals(SAMPLE_SIGNALS_NULLS_ONLY)
    assert result is not None
    assert result["consumer_stress_tier"] is None
    assert result["capex_direction"] == "accelerating"
    assert result["pricing_power"] == "strong"


def test_parse_signals_uses_last_block():
    """If multiple SIGNALS blocks exist, take the last one (findall+last pattern)."""
    text = """```SIGNALS
{"consumer_stress_tier": "neutral", "pricing_power": "strong", "signal_evidence": {}}
```

Some text.

```SIGNALS
{"consumer_stress_tier": "trade_down", "pricing_power": "weak", "signal_evidence": {}}
```
"""
    result = parse_signals(text)
    assert result is not None
    assert result["consumer_stress_tier"] == "trade_down"
    assert result["pricing_power"] == "weak"
