"""Parse grades and metadata from analysis markdown files."""

from __future__ import annotations

import json
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

    # Dimension grades: **Grade: X** within each "### N. ..." section (bounded
    # by the next "###"-prefixed heading of any kind). Some LLM output states
    # a preliminary grade right after the heading (sometimes split, e.g.
    # "A-/B+"), then restates a single, more considered grade later in the
    # same section's prose -- take the LAST "Grade:" line in the section,
    # which is what the LLM's own composite calculation actually uses.
    dim_section_pattern = re.compile(
        r"###\s+(\d)\.\s+.*?(?=\n###\s|\Z)", re.DOTALL
    )
    dim_grade_line = re.compile(r"\*\*Grade:\s*\**([A-F][+-]?)")
    for section in dim_section_pattern.finditer(text):
        grades = dim_grade_line.findall(section.group())
        if grades:
            result[f"dim{section.group(1)}_grade"] = grades[-1]

    # Composite grade: "### Composite Grade: X", tolerating markdown bold
    # around the letter (e.g. "### Composite Grade: **B**"). Some LLM output
    # repeats this heading (once bare, once with the grade) — take the last
    # match rather than the first. A bare heading (no colon) never matches
    # here, so it's naturally skipped.
    heading_grades = re.findall(
        r"###\s+Composite Grade:\s*\**([A-F][+-]?)\**(?![a-zA-Z])", text
    )
    if heading_grades:
        result["composite_grade"] = heading_grades[-1]
    else:
        # Fall back: the grade sometimes appears inline with no "###" prefix
        # at all, e.g. "**Weighted Score: 3.65 → Composite Grade: A**".
        inline_grade = re.search(
            r"Composite Grade:\s*\**([A-F][+-]?)\**(?![a-zA-Z])", text
        )
        if inline_grade:
            result["composite_grade"] = inline_grade.group(1)

    # Composite score extraction — multiple LLM output formats:
    # 1. "Weighted Total: 3.015 → Composite Grade: B"
    # 2. "Weighted Score: 0.75 + 0.75 + ... = 2.65 → B"
    # 3. "Weighted total: 0.75 + 0.75 + 0.30 + 0.60 + 0.45 = 2.85 → B"
    # 4. "= **2.03** -> C" (inline after Composite Grade heading)
    # Strategy: find the Weighted Total/Score line, then extract the last
    # decimal number on it (which is the total, not a per-dimension weight).
    weighted_line = re.search(
        r"\*?\*?[Ww]eighted (?:[Tt]otal|[Ss]core):?\*?\*?\s*(.+)", text
    )
    if weighted_line:
        numbers = re.findall(r"(\d+\.\d+)", weighted_line.group(1))
        if numbers:
            result["composite_score"] = float(numbers[-1])
    else:
        # Fall back: search only within the Composite Grade section
        comp_section = re.search(
            r"###\s+Composite Grade:.*?(?=\n###|\Z)", text, re.DOTALL
        )
        if comp_section:
            # Find ALL "= X.XX →" patterns and take the last one (the total, not per-dim)
            scores = re.findall(
                r"=\s*\**(\d+\.?\d*)\**\s*[-→>]", comp_section.group()
            )
            if scores:
                result["composite_score"] = float(scores[-1])

    if "composite_score" not in result:
        # Final fallback (e.g. a bare "### Composite Grade" heading followed
        # by a "**Calculation:**" block, with the real grade only restated in
        # a later, separately-anchored heading): scan the whole document for
        # the final "<number> → <grade>" result token, wherever it lands, and
        # take the last one.
        final_result = re.findall(
            r"(\d+\.\d+)\**\s*(?:→|->|-→)\s*\**(?:Composite Grade:\s*)?"
            r"\**[A-F][+-]?(?![a-zA-Z])",
            text,
        )
        if final_result:
            result["composite_score"] = float(final_result[-1])

    return result


def parse_signals(text: str) -> dict | None:
    """Extract the SIGNALS JSON block from analysis markdown.

    Returns the parsed dict, or None if no block found.
    Uses findall+last to handle multiple blocks (takes the last one).
    """
    blocks = re.findall(r"```SIGNALS\s*\n(.*?)```", text, re.DOTALL)
    if not blocks:
        return None
    try:
        return json.loads(blocks[-1].strip())
    except json.JSONDecodeError:
        return None
