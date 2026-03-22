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

    # Composite score extraction — multiple LLM output formats:
    # 1. "Weighted Total: 3.015 → Composite Grade: B"
    # 2. "Weighted Score: 0.75 + 0.75 + ... = 2.65 → B"
    # 3. "= **2.03** -> C" (inline after Composite Grade heading)
    # Always prefer the last number before → on a Weighted Total/Score line.
    weighted = re.search(
        r"Weighted (?:Total|Score):\s*.*?(\d+\.?\d*)\s*[-→>]", text
    )
    if weighted:
        result["composite_score"] = float(weighted.group(1))
    else:
        # Fall back: search only within the Composite Grade section
        comp_section = re.search(
            r"###\s+Composite Grade:.*?(?=\n###|\Z)", text, re.DOTALL
        )
        if comp_section:
            score = re.search(
                r"=\s*\**(\d+\.?\d*)\**\s*[-→>]", comp_section.group()
            )
            if score:
                result["composite_score"] = float(score.group(1))

    return result
