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


def test_ingest_transcript_rejects_bad_quarter(tmp_path, monkeypatch):
    monkeypatch.setattr("eca.config.project_root", lambda: tmp_path)
    src = tmp_path / "transcript.txt"
    src.write_text(SAMPLE_TRANSCRIPT)

    runner = CliRunner()
    result = runner.invoke(cli, ["ingest-transcript", "root", "q3", str(src)])
    assert result.exit_code != 0
    assert "Expected format" in result.output

    result = runner.invoke(cli, ["ingest-transcript", "root", "q5-2025", str(src)])
    assert result.exit_code != 0


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


# --- Provenance-aware ingestion (mag7 evidence spec) -------------------------

RAW_WITH_MARKED_SUMMARY = """----- BEGIN PROVIDER SUMMARY -----
Earnings Call Sentiment
Positive
The call conveyed strong momentum.
----- END PROVIDER SUMMARY -----
Operator: Good day and welcome to the Root Q3 2025 earnings call.

Alex Timm -- CEO

Thank you, operator. Q3 was another strong quarter for Root.
"""

RAW_WITH_UNTERMINATED_BLOCK = """----- BEGIN PROVIDER SUMMARY -----
Earnings Call Sentiment
Positive
Operator: welcome.
"""

RAW_WITH_UNMARKED_SUMMARY = """Earnings Call Date:
Jul 22, 2026
Earnings Call Sentiment
Positive
Operator: welcome.
"""

FULL_META = {
    "source_provider": "example-provider",
    "source_url": "https://example.invalid/call",
    "retrieved_at": "2026-10-04T12:00:00Z",
    "document_date": "2026-07-30",
    "call_date": "2026-07-30",
    "fiscal_year": 2026,
    "fiscal_quarter": 2,
    "period_start": "2026-04-01",
    "period_end": "2026-06-30",
}


def _ingest(tmp_path, monkeypatch, content, quarter="q3-2025", ticker="root", extra_args=None):
    monkeypatch.setattr("eca.config.project_root", lambda: tmp_path)
    src = tmp_path / "source.txt"
    src.write_text(content)
    args = ["ingest-transcript", ticker, quarter, str(src)] + (extra_args or [])
    return CliRunner().invoke(cli, args)


def test_ingest_writes_raw_normalized_and_meta(tmp_path, monkeypatch):
    result = _ingest(tmp_path, monkeypatch, RAW_WITH_MARKED_SUMMARY)
    assert result.exit_code == 0
    target = tmp_path / "data" / "root" / "q3-2025"
    assert (target / "transcript.raw.txt").read_text() == RAW_WITH_MARKED_SUMMARY
    normalized = (target / "transcript.txt").read_text()
    assert "BEGIN PROVIDER SUMMARY" not in normalized
    assert "Earnings Call Sentiment" not in normalized
    assert "Thank you, operator. Q3 was another strong quarter for Root." in normalized
    assert (target / "transcript.meta.json").exists()


def test_meta_records_hashes(tmp_path, monkeypatch):
    import hashlib
    result = _ingest(tmp_path, monkeypatch, RAW_WITH_MARKED_SUMMARY)
    assert result.exit_code == 0
    target = tmp_path / "data" / "root" / "q3-2025"
    meta = json.loads((target / "transcript.meta.json").read_text())
    assert meta["sha256_raw"] == hashlib.sha256(
        RAW_WITH_MARKED_SUMMARY.encode("utf-8")
    ).hexdigest()
    assert meta["sha256_normalized"] == hashlib.sha256(
        (target / "transcript.txt").read_text().encode("utf-8")
    ).hexdigest()
    assert "removed_provider_summary_blocks" in ",".join(meta["normalization_warnings"])


def test_marker_free_transcript_is_unchanged(tmp_path, monkeypatch):
    """Backward compatibility: no markers, no CRLF — normalized == raw text."""
    result = _ingest(tmp_path, monkeypatch, SAMPLE_TRANSCRIPT)
    assert result.exit_code == 0
    target = tmp_path / "data" / "root" / "q3-2025"
    assert (target / "transcript.txt").read_text() == SAMPLE_TRANSCRIPT


def test_metadata_flag_roundtrip(tmp_path, monkeypatch):
    args = ["--source-provider", "example-provider",
            "--source-url", "https://example.invalid/call",
            "--retrieved-at", "2026-10-04T12:00:00Z",
            "--document-date", "2026-07-30", "--call-date", "2026-07-30",
            "--fiscal-year", "2026", "--fiscal-quarter", "2",
            "--period-start", "2026-04-01", "--period-end", "2026-06-30"]
    result = _ingest(tmp_path, monkeypatch, SAMPLE_TRANSCRIPT, extra_args=args)
    assert result.exit_code == 0
    meta = json.loads(
        (tmp_path / "data" / "root" / "q3-2025" / "transcript.meta.json").read_text()
    )
    assert meta["source_provider"] == "example-provider"
    assert meta["fiscal_year"] == 2026
    assert meta["fiscal_quarter"] == 2
    assert meta["period_start"] == "2026-04-01"
    assert meta["call_date"] == "2026-07-30"
    assert meta["normalization_warnings"] == []


def test_omitted_metadata_stays_null_with_warning(tmp_path, monkeypatch):
    result = _ingest(tmp_path, monkeypatch, SAMPLE_TRANSCRIPT)
    assert result.exit_code == 0
    meta = json.loads(
        (tmp_path / "data" / "root" / "q3-2025" / "transcript.meta.json").read_text()
    )
    assert meta["call_date"] is None
    assert meta["source_provider"] is None
    warnings = meta["normalization_warnings"]
    assert "metadata_missing:call_date" in warnings
    assert "metadata_missing:source_provider" in warnings
    # the CLI surfaces warnings
    assert "metadata_missing:call_date" in result.output


def test_unmarked_provider_summary_warning_without_deletion(tmp_path, monkeypatch):
    result = _ingest(tmp_path, monkeypatch, RAW_WITH_UNMARKED_SUMMARY)
    assert result.exit_code == 0
    target = tmp_path / "data" / "root" / "q3-2025"
    normalized = (target / "transcript.txt").read_text()
    assert "Earnings Call Sentiment" in normalized  # not silently deleted
    meta = json.loads((target / "transcript.meta.json").read_text())
    assert any("unrecognized_provider_summary_content" in w for w in meta["normalization_warnings"])


def test_unterminated_marker_block_retained_with_warning(tmp_path, monkeypatch):
    result = _ingest(tmp_path, monkeypatch, RAW_WITH_UNTERMINATED_BLOCK)
    assert result.exit_code == 0
    target = tmp_path / "data" / "root" / "q3-2025"
    normalized = (target / "transcript.txt").read_text()
    assert "Operator: welcome." in normalized  # content kept, not lost
    meta = json.loads((target / "transcript.meta.json").read_text())
    assert any("unterminated_provider_summary_block" in w for w in meta["normalization_warnings"])


def test_crlf_normalized(tmp_path, monkeypatch):
    result = _ingest(tmp_path, monkeypatch, "Operator: hello.\r\nSpeaker: thanks.\r\n")
    assert result.exit_code == 0
    assert (tmp_path / "data" / "root" / "q3-2025" / "transcript.txt").read_text() == \
        "Operator: hello.\nSpeaker: thanks.\n"


def test_duplicate_normalized_hash_detected(tmp_path, monkeypatch):
    monkeypatch.setattr("eca.config.project_root", lambda: tmp_path)
    src = tmp_path / "source.txt"
    src.write_text(SAMPLE_TRANSCRIPT)
    CliRunner().invoke(cli, ["ingest-transcript", "root", "q3-2025", str(src)])
    result = CliRunner().invoke(cli, ["ingest-transcript", "lmnd", "q3-2025", str(src)])
    assert result.exit_code == 0
    meta = json.loads(
        (tmp_path / "data" / "lmnd" / "q3-2025" / "transcript.meta.json").read_text()
    )
    dupes = [w for w in meta["normalization_warnings"] if w.startswith("duplicate_normalized_transcript:")]
    assert len(dupes) == 1
    assert "root/q3-2025" in dupes[0]
    assert "duplicate_normalized_transcript" in result.output


def test_invalid_metadata_rejected(tmp_path, monkeypatch):
    result = _ingest(tmp_path, monkeypatch, SAMPLE_TRANSCRIPT,
                     extra_args=["--document-date", "July 30"])
    assert result.exit_code != 0
    assert "document_date" in result.output


def test_reingest_preserves_raw_bytes(tmp_path, monkeypatch):
    first = _ingest(tmp_path, monkeypatch, RAW_WITH_MARKED_SUMMARY)
    assert first.exit_code == 0
    target = tmp_path / "data" / "root" / "q3-2025"
    # add a facts field, then re-ingest the same source
    facts_path = target / "facts.json"
    facts = json.loads(facts_path.read_text())
    facts["metrics"] = {"revenue_m": 387.8}
    facts_path.write_text(json.dumps(facts))
    second = _ingest(tmp_path, monkeypatch, RAW_WITH_MARKED_SUMMARY)
    assert second.exit_code == 0
    facts = json.loads(facts_path.read_text())
    assert facts["metrics"]["revenue_m"] == 387.8  # preserved
    assert (target / "transcript.raw.txt").read_text() == RAW_WITH_MARKED_SUMMARY
