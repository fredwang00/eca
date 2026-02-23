import json
from pathlib import Path
from click.testing import CliRunner

from eca.cli import cli
from eca.processors.migrate import discover_files, migrate

SAMPLE_ANALYSIS = """# Earnings Call Candor Analysis
## Company: Root, Inc. | Quarter: Q1 2025 | Date: May 6, 2025

### 1. Capital Stewardship & Financial Candor
**Grade: C+**

### 2. Strategic Clarity & Accountability
**Grade: B-**

### 3. Stakeholder Balance & Culture Signals
**Grade: C**

### 4. FOG Index -- Linguistic Quality of Disclosure
**Grade: C+**

### 5. Vision, Leadership & Long-Term Orientation
**Grade: C+**

---

### Composite Grade: C
**Calculation:** (C+ [2.3] x 0.25) + (B- [2.7] x 0.25) + (C [2.0] x 0.15) + (C+ [2.3] x 0.20) + (C+ [2.3] x 0.15) = **2.355** -> C
"""


def _setup_old_layout(root: Path):
    """Create old-style directory layout for testing."""
    # Regular transcript
    t = root / "transcripts" / "root" / "2025"
    t.mkdir(parents=True)
    (t / "q1.txt").write_text("Transcript Q1")
    # Irregular: q4-2024 transcript in 2025/ directory
    (t / "q4-2024.txt").write_text("Transcript Q4 2024")

    # Regular analysis
    a = root / "analyses" / "root" / "2025"
    a.mkdir(parents=True)
    (a / "q1.md").write_text(SAMPLE_ANALYSIS)
    # Irregular: analysis at root level (not in year subdir)
    (root / "analyses" / "root" / "q4-2024.md").write_text(
        SAMPLE_ANALYSIS.replace("Q1 2025", "Q4 2024").replace("May 6, 2025", "February 12, 2025")
    )

    # Skills
    (root / "SKILL.md").write_text("Base skill content")
    (root / "SKILL-insurtech.md").write_text("Insurtech supplement")


def test_discover_finds_all_files(tmp_path):
    _setup_old_layout(tmp_path)
    files = discover_files(tmp_path)
    slugs = {f["quarter_slug"] for f in files}
    assert "q1-2025" in slugs
    assert "q4-2024" in slugs


def test_migrate_creates_new_layout(tmp_path, monkeypatch):
    monkeypatch.setattr("eca.config.project_root", lambda: tmp_path)
    _setup_old_layout(tmp_path)
    migrate(tmp_path)

    assert (tmp_path / "data" / "root" / "q1-2025" / "transcript.txt").exists()
    assert (tmp_path / "data" / "root" / "q4-2024" / "transcript.txt").exists()
    assert (tmp_path / "data" / "root" / "q1-2025" / "analysis.md").exists()


def test_migrate_generates_facts(tmp_path, monkeypatch):
    monkeypatch.setattr("eca.config.project_root", lambda: tmp_path)
    _setup_old_layout(tmp_path)
    migrate(tmp_path)

    facts = json.loads(
        (tmp_path / "data" / "root" / "q1-2025" / "facts.json").read_text()
    )
    assert facts["ticker"] == "ROOT"
    assert facts["candor"]["dim1_grade"] == "C+"
    assert facts["candor"]["composite_grade"] == "C"


def test_migrate_moves_skills(tmp_path, monkeypatch):
    monkeypatch.setattr("eca.config.project_root", lambda: tmp_path)
    _setup_old_layout(tmp_path)
    migrate(tmp_path)

    assert (tmp_path / "skills" / "base.md").exists()
    assert (tmp_path / "skills" / "insurtech.md").exists()
