from eca.parsers.grades import parse_grades

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


def test_parse_header_metadata():
    result = parse_grades(SAMPLE_ROOT)
    assert result["company"] == "Root, Inc."
    assert result["quarter"] == "Q3 2025"
    assert result["call_date"] == "November 4, 2025"
