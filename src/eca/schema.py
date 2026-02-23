"""facts.json schema and I/O helpers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, TypedDict


class QuarterMetrics(TypedDict, total=False):
    source: str
    ingested_at: str
    revenue_m: float | None
    gross_profit_m: float | None
    operating_income_m: float | None
    net_income_m: float | None
    eps: float | None
    free_cash_flow_m: float | None
    operating_cash_flow_m: float | None
    capital_expenditure_m: float | None
    cash_and_equivalents_m: float | None
    total_assets_m: float | None
    total_equity_m: float | None
    shares_outstanding_m: float | None
    bvps: float | None
    roe_pct: float | None
    combined_ratio_pct: float | None
    loss_ratio_pct: float | None
    expense_ratio_pct: float | None


class CandorGrades(TypedDict, total=False):
    analyzed_at: str
    skill_version: str
    dim1_grade: str
    dim2_grade: str
    dim3_grade: str
    dim4_grade: str
    dim5_grade: str
    composite_score: float
    composite_grade: str


class Facts(TypedDict, total=False):
    company: str
    ticker: str
    quarter: str
    call_date: str
    metrics: QuarterMetrics
    candor: CandorGrades
    flags: list[str]
    tracking: list[str]


def load_facts(path: Path) -> dict[str, Any]:
    """Load facts.json, returning empty dict if file doesn't exist."""
    if path.exists():
        return json.loads(path.read_text())
    return {}


def save_facts(path: Path, facts: dict[str, Any]) -> None:
    """Write facts.json, creating parent directories as needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(facts, indent=2) + "\n")
