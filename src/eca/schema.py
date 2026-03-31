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


class SignalEvidence(TypedDict, total=False):
    consumer_stress_tier: str
    credit_quality_trend: str
    auto_credit_trend: str
    housing_demand: str
    services_demand: str
    capex_direction: str
    pricing_power: str
    management_tone_shift: str


class SignalData(TypedDict, total=False):
    extracted_at: str
    consumer_stress_tier: str | None
    credit_quality_trend: str | None
    auto_credit_trend: str | None
    housing_demand: str | None
    services_demand: str | None
    capex_direction: str | None
    pricing_power: str | None
    management_tone_shift: str | None
    signal_evidence: SignalEvidence


# Ordered enums for severity scoring (0 = healthy, N = worst)
SIGNAL_ENUMS: dict[str, list[str]] = {
    "consumer_stress_tier": ["neutral", "trade_down", "essentials_pressure", "credit_bridging"],
    "credit_quality_trend": ["improving", "stable", "normalizing", "deteriorating"],
    "auto_credit_trend": ["improving", "stable", "normalizing", "deteriorating"],
    "housing_demand": ["expanding", "stable", "softening", "contracting"],
    "services_demand": ["expanding", "stable", "softening", "contracting"],
    "capex_direction": ["accelerating", "stable", "decelerating", "cutting"],
    "pricing_power": ["strong", "moderate", "weak", "capitulating"],
    "management_tone_shift": ["more_confident", "consistent", "more_cautious", "alarmed"],
}


class Facts(TypedDict, total=False):
    company: str
    ticker: str
    quarter: str
    call_date: str
    metrics: QuarterMetrics
    candor: CandorGrades
    signals: SignalData
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
