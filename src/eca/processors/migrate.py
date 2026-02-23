"""Migration: restructure old layout to new data/ layout."""

from __future__ import annotations

import re
import shutil
from pathlib import Path

from eca.parsers.grades import parse_grades
from eca.schema import load_facts, save_facts


def _path_to_quarter_slug(path: Path) -> str | None:
    """Extract quarter slug from old-layout file path.

    Handles:
      transcripts/root/2025/q1.txt -> q1-2025
      transcripts/root/2025/q4-2024.txt -> q4-2024
      analyses/root/q4-2024.md -> q4-2024
    """
    stem = path.stem
    if re.match(r"q\d-\d{4}", stem):
        return stem

    # Check immediate parent directory name for a year
    parent_name = path.parent.name
    year_match = re.match(r"\d{4}$", parent_name)
    quarter_match = re.match(r"(q\d)", stem)
    if year_match and quarter_match:
        return f"{quarter_match.group(1)}-{parent_name}"

    return None


def discover_files(project_root: Path) -> list[dict]:
    """Discover all transcripts and analyses in the old layout."""
    entries: dict[tuple[str, str], dict] = {}

    transcripts_dir = project_root / "transcripts"
    if transcripts_dir.exists():
        for txt_path in transcripts_dir.rglob("*.txt"):
            ticker = txt_path.parts[len(transcripts_dir.parts)].upper()
            slug = _path_to_quarter_slug(txt_path)
            if slug:
                key = (ticker, slug)
                entries.setdefault(key, {"ticker": ticker, "quarter_slug": slug})
                entries[key]["transcript_path"] = txt_path

    analyses_dir = project_root / "analyses"
    if analyses_dir.exists():
        for md_path in analyses_dir.rglob("*.md"):
            ticker = md_path.parts[len(analyses_dir.parts)].upper()
            slug = _path_to_quarter_slug(md_path)
            if slug:
                key = (ticker, slug)
                entries.setdefault(key, {"ticker": ticker, "quarter_slug": slug})
                entries[key]["analysis_path"] = md_path

    return list(entries.values())


def migrate(project_root: Path) -> None:
    """Migrate old layout to new data/ layout."""
    entries = discover_files(project_root)
    data_root = project_root / "data"

    for entry in entries:
        ticker = entry["ticker"].lower()
        slug = entry["quarter_slug"]
        target_dir = data_root / ticker / slug
        target_dir.mkdir(parents=True, exist_ok=True)

        if "transcript_path" in entry:
            shutil.copy2(entry["transcript_path"], target_dir / "transcript.txt")

        if "analysis_path" in entry:
            analysis_path = entry["analysis_path"]
            shutil.copy2(analysis_path, target_dir / "analysis.md")

            grades = parse_grades(analysis_path.read_text())

            facts_path = target_dir / "facts.json"
            facts = load_facts(facts_path)
            facts["ticker"] = entry["ticker"]

            parts = slug.split("-")
            facts["quarter"] = f"{parts[0].upper()} {parts[1]}"

            for key in ("company", "call_date"):
                if key in grades:
                    facts[key] = grades[key]

            candor = {}
            for key in ("dim1_grade", "dim2_grade", "dim3_grade", "dim4_grade",
                        "dim5_grade", "composite_score", "composite_grade"):
                if key in grades:
                    candor[key] = grades[key]
            if candor:
                facts["candor"] = candor

            save_facts(facts_path, facts)

    # Copy skill files
    skills_dir = project_root / "skills"
    skills_dir.mkdir(exist_ok=True)
    for src_name, dst_name in [("SKILL.md", "base.md"), ("SKILL-insurtech.md", "insurtech.md")]:
        src = project_root / src_name
        if src.exists():
            shutil.copy2(src, skills_dir / dst_name)
