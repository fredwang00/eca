"""ingest-transcript processor: provenance-aware transcript ingestion.

Preserves the raw ingested bytes, writes a normalized transcript (removing
only recognized, explicitly marked provider-summary blocks), hashes both
forms, and records provenance metadata. Unknown metadata stays null and
produces a warning — values are never invented.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
from pathlib import Path
from typing import Any, NamedTuple

from eca.config import COMPANY_NAMES, data_dir, quarter_dir
from eca.schema import load_facts, save_facts

PROVIDER_SUMMARY_BEGIN_RE = re.compile(
    r"^[-=]{3,}\s*BEGIN PROVIDER SUMMARY\s*[-=]{3,}\s*$", re.IGNORECASE
)
PROVIDER_SUMMARY_END_RE = re.compile(
    r"^[-=]{3,}\s*END PROVIDER SUMMARY\s*[-=]{3,}\s*$", re.IGNORECASE
)

# Unmarked provider-summary indicators: recognized as third-party content but
# never deleted. They remain in the normalized transcript and raise a warning
# so a human curates them explicitly.
UNMARKED_PROVIDER_SUMMARY_RE = re.compile(
    r"^(Summary|Highlights|Lowlights|Company Guidance|"
    r"Earnings Call Date:|Next Earnings Date:|Change Since:|"
    r"Earnings Call Sentiment)\s*$",
    re.IGNORECASE,
)

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# Optional metadata fields; omitted ones stay null and are recorded as
# warnings in transcript.meta.json.
META_FIELDS = (
    "source_provider",
    "source_url",
    "retrieved_at",
    "document_date",
    "call_date",
    "fiscal_year",
    "fiscal_quarter",
    "period_start",
    "period_end",
)

_DATE_FIELDS = ("document_date", "call_date", "period_start", "period_end")
_INT_FIELDS = ("fiscal_year", "fiscal_quarter")


class IngestResult(NamedTuple):
    target: Path
    meta: dict[str, Any]


def validate_quarter_slug(quarter_slug: str) -> None:
    """Raise ValueError if quarter slug is not in 'q1-2025' format."""
    if not re.match(r"^q[1-4]-\d{4}$", quarter_slug.lower()):
        raise ValueError(
            f"Invalid quarter '{quarter_slug}'. Expected format: q1-2025"
        )


def normalize_quarter_label(quarter_slug: str) -> str:
    """Convert 'q3-2025' to 'Q3 2025'."""
    validate_quarter_slug(quarter_slug)
    parts = quarter_slug.lower().split("-")
    return f"{parts[0].upper()} {parts[1]}"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def normalize_transcript_text(raw_text: str) -> tuple[str, list[str]]:
    """Normalize a raw transcript, returning (normalized_text, warnings).

    Only provider-summary blocks delimited by explicit BEGIN/END PROVIDER
    SUMMARY markers are removed. Unmarked provider-looking content stays in
    place and raises a warning instead of being silently deleted.
    """
    warnings: list[str] = []
    text = raw_text.replace("\r\n", "\n").replace("\r", "\n")
    lines = text.split("\n")

    out: list[str] = []
    removed_blocks = 0
    i = 0
    while i < len(lines):
        if PROVIDER_SUMMARY_BEGIN_RE.match(lines[i]):
            j = i + 1
            while j < len(lines) and not PROVIDER_SUMMARY_END_RE.match(lines[j]):
                j += 1
            if j >= len(lines):
                warnings.append(
                    "unterminated_provider_summary_block: BEGIN marker without "
                    "END marker; content retained — add an END marker or remove "
                    "the block manually"
                )
                out.extend(lines[i:])
                break
            removed_blocks += 1
            i = j + 1
            continue
        out.append(lines[i])
        i += 1

    if removed_blocks:
        warnings.append(f"removed_provider_summary_blocks: {removed_blocks}")

    if any(UNMARKED_PROVIDER_SUMMARY_RE.match(line) for line in out):
        warnings.append(
            "unrecognized_provider_summary_content: provider-summary content "
            "without BEGIN/END markers remains in transcript.txt; curate manually"
        )

    return "\n".join(out), warnings


def validate_meta(meta: dict[str, Any]) -> None:
    """Raise ValueError for malformed metadata; never guess or repair."""
    for field in _DATE_FIELDS:
        value = meta.get(field)
        if value is not None and (not isinstance(value, str) or not DATE_RE.match(value)):
            raise ValueError(f"{field} must be an ISO date (YYYY-MM-DD), got {value!r}")
    for field in _INT_FIELDS:
        value = meta.get(field)
        if value is None:
            continue
        if not isinstance(value, int) or isinstance(value, bool):
            raise ValueError(f"{field} must be an integer, got {value!r}")
    if meta.get("fiscal_quarter") is not None and not 1 <= meta["fiscal_quarter"] <= 4:
        raise ValueError(f"fiscal_quarter must be 1-4, got {meta['fiscal_quarter']!r}")
    for field in ("source_provider", "source_url", "retrieved_at"):
        value = meta.get(field)
        if value is not None and (not isinstance(value, str) or not value.strip()):
            raise ValueError(f"{field} must be a non-empty string or null")


def find_duplicate_normalized(target_dir: Path, sha256_normalized: str) -> list[str]:
    """Return relative paths of other quarters with the same normalized hash."""
    duplicates: list[str] = []
    root = data_dir()
    if not root.exists():
        return duplicates
    for meta_path in sorted(root.glob("*/*/transcript.meta.json")):
        if meta_path.parent == target_dir:
            continue
        try:
            other = json.loads(meta_path.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        if other.get("sha256_normalized") == sha256_normalized:
            duplicates.append(str(meta_path.parent.relative_to(root)))
    return duplicates


def ingest_transcript(
    ticker: str,
    quarter_slug: str,
    source_path: Path,
    meta: dict[str, Any] | None = None,
) -> IngestResult:
    """Ingest a transcript with provenance: raw + normalized + meta + hashes."""
    validate_quarter_slug(quarter_slug)
    meta = dict(meta or {})
    validate_meta(meta)

    ticker_upper = ticker.upper()
    target = quarter_dir(ticker_upper, quarter_slug)
    target.mkdir(parents=True, exist_ok=True)

    raw_bytes = source_path.read_bytes()
    raw_text = raw_bytes.decode("utf-8")
    normalized, warnings = normalize_transcript_text(raw_text)

    # Preserve the raw bytes exactly; write the normalized primary text.
    shutil.copy2(source_path, target / "transcript.raw.txt")
    (target / "transcript.txt").write_text(normalized, encoding="utf-8")

    sha_raw = sha256_bytes(raw_bytes)
    sha_normalized = sha256_text(normalized)

    for field in META_FIELDS:
        if meta.get(field) is None:
            warnings.append(f"metadata_missing:{field}")

    for dup in find_duplicate_normalized(target, sha_normalized):
        warnings.append(f"duplicate_normalized_transcript:{dup}")

    meta_doc = {
        "source_provider": meta.get("source_provider"),
        "source_url": meta.get("source_url"),
        "retrieved_at": meta.get("retrieved_at"),
        "sha256_raw": sha_raw,
        "sha256_normalized": sha_normalized,
        "document_date": meta.get("document_date"),
        "call_date": meta.get("call_date"),
        "fiscal_year": meta.get("fiscal_year"),
        "fiscal_quarter": meta.get("fiscal_quarter"),
        "period_start": meta.get("period_start"),
        "period_end": meta.get("period_end"),
        "normalization_warnings": warnings,
    }
    (target / "transcript.meta.json").write_text(
        json.dumps(meta_doc, indent=2) + "\n", encoding="utf-8"
    )

    # Re-ingestion preserves existing facts.json fields.
    facts_path = target / "facts.json"
    facts = load_facts(facts_path)
    facts["ticker"] = ticker_upper
    facts["quarter"] = normalize_quarter_label(quarter_slug)
    if ticker_upper in COMPANY_NAMES:
        facts["company"] = COMPANY_NAMES[ticker_upper]
    save_facts(facts_path, facts)

    return IngestResult(target, meta_doc)
