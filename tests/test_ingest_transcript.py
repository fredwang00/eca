import json
from pathlib import Path
from click.testing import CliRunner

from eca.cli import cli

SAMPLE_TRANSCRIPT = """Operator: Good day and welcome to the Root Q3 2025 earnings call.

Alex Timm -- CEO

Thank you, operator. Q3 was another strong quarter for Root.
"""


def test_ingest_transcript_creates_files(tmp_path, monkeypatch):
    monkeypatch.setattr("eca.config.project_root", lambda: tmp_path)
    src = tmp_path / "transcript.txt"
    src.write_text(SAMPLE_TRANSCRIPT)

    runner = CliRunner()
    result = runner.invoke(cli, ["ingest-transcript", "root", "q3-2025", str(src)])

    assert result.exit_code == 0
    target = tmp_path / "data" / "root" / "q3-2025"
    assert (target / "transcript.txt").exists()
    assert (target / "facts.json").exists()


def test_ingest_transcript_copies_content(tmp_path, monkeypatch):
    monkeypatch.setattr("eca.config.project_root", lambda: tmp_path)
    src = tmp_path / "transcript.txt"
    src.write_text(SAMPLE_TRANSCRIPT)

    CliRunner().invoke(cli, ["ingest-transcript", "root", "q3-2025", str(src)])

    target = tmp_path / "data" / "root" / "q3-2025" / "transcript.txt"
    assert target.read_text() == SAMPLE_TRANSCRIPT


def test_ingest_transcript_creates_facts_stub(tmp_path, monkeypatch):
    monkeypatch.setattr("eca.config.project_root", lambda: tmp_path)
    src = tmp_path / "transcript.txt"
    src.write_text(SAMPLE_TRANSCRIPT)

    CliRunner().invoke(cli, ["ingest-transcript", "root", "q3-2025", str(src)])

    facts = json.loads(
        (tmp_path / "data" / "root" / "q3-2025" / "facts.json").read_text()
    )
    assert facts["ticker"] == "ROOT"
    assert facts["quarter"] == "Q3 2025"


def test_ingest_transcript_preserves_existing_facts(tmp_path, monkeypatch):
    monkeypatch.setattr("eca.config.project_root", lambda: tmp_path)

    # Pre-populate facts with metrics
    target_dir = tmp_path / "data" / "root" / "q3-2025"
    target_dir.mkdir(parents=True)
    (target_dir / "facts.json").write_text(
        json.dumps({"ticker": "ROOT", "metrics": {"revenue_m": 387.8}})
    )

    src = tmp_path / "transcript.txt"
    src.write_text(SAMPLE_TRANSCRIPT)

    CliRunner().invoke(cli, ["ingest-transcript", "root", "q3-2025", str(src)])

    facts = json.loads((target_dir / "facts.json").read_text())
    assert facts["metrics"]["revenue_m"] == 387.8  # preserved
    assert facts["quarter"] == "Q3 2025"  # added
