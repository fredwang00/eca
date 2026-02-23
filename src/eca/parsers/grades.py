"""Parse grades and metadata from analysis markdown files."""

from __future__ import annotations

import re


def parse_grades(text: str) -> dict:
    """Extract dimension grades, composite grade/score, and header metadata."""
    result = {}

    # Header: ## Company: Name | Quarter: Q3 2025 | Date: November 4, 2025
    header = re.search(
        r"##\s+Company:\s*(.+?)\s*\|\s*Quarter:\s*(.+?)\s*\|\s*Date:\s*(.+)",
        text,
    )
    if header:
        result["company"] = header.group(1).strip()
        result["quarter"] = header.group(2).strip()
        result["call_date"] = header.group(3).strip()

    # Dimension grades: **Grade: X** after ### N. heading
    dim_pattern = re.compile(
        r"###\s+(\d)\.\s+.*?\n\*\*Grade:\s*([A-F][+-]?)\*\*", re.DOTALL
    )
    for match in dim_pattern.finditer(text):
        result[f"dim{match.group(1)}_grade"] = match.group(2)

    # Composite grade: ### Composite Grade: X
    comp = re.search(r"###\s+Composite Grade:\s*([A-F][+-]?)", text)
    if comp:
        result["composite_grade"] = comp.group(1)

    # Composite score: look for the numeric result before the arrow
    # Handles both "= **2.03** -> C" and "= 2.815 -> B" formats
    score = re.search(r"=\s*\**(\d+\.?\d*)\**\s*[-→>]", text)
    if score:
        result["composite_score"] = float(score.group(1))

    return result
