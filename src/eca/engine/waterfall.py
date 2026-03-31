"""7-stage consumer distress waterfall engine."""

from __future__ import annotations

from dataclasses import dataclass

from eca.schema import SIGNAL_ENUMS


@dataclass
class StageResult:
    id: str
    label: str
    firing: bool
    triggered_by: list[str]
    evidence: dict[str, str]
    count: str  # e.g. "2/4"


def _severity(field: str, value: str | None) -> int:
    """Return ordinal severity (0 = healthy). Returns -1 for null/unknown."""
    if value is None:
        return -1
    values = SIGNAL_ENUMS.get(field, [])
    try:
        return values.index(value)
    except ValueError:
        return -1


def _get_signal(facts_by_ticker: dict, ticker: str, field: str) -> str | None:
    """Safely get a signal value for a ticker."""
    signals = facts_by_ticker.get(ticker, {}).get("signals", {})
    return signals.get(field)


def _get_evidence(facts_by_ticker: dict, ticker: str, field: str) -> str:
    """Get evidence quote for a signal field."""
    signals = facts_by_ticker.get(ticker, {}).get("signals", {})
    evidence = signals.get("signal_evidence", {})
    return evidence.get(field, "")


# Stage definitions: (id, label, tickers, check_function)
# Each check function takes (facts_by_ticker, ticker) -> bool

STAGE_DEFS: list[dict] = [
    {
        "id": "stage_1",
        "label": "Discretionary Cuts",
        "tickers": ["TGT", "ABNB", "SHOP"],
        "threshold": 2,
        "check": lambda facts, t: (
            _severity("consumer_stress_tier", _get_signal(facts, t, "consumer_stress_tier")) >= 1
            or _severity("pricing_power", _get_signal(facts, t, "pricing_power")) >= 2
        ),
        "evidence_fields": ["consumer_stress_tier", "pricing_power"],
    },
    {
        "id": "stage_2",
        "label": "Essential Trade-Down",
        "tickers": ["WMT", "COST"],
        "threshold": 1,
        "check": lambda facts, t: (
            _severity("consumer_stress_tier", _get_signal(facts, t, "consumer_stress_tier")) >= 2
        ),
        "evidence_fields": ["consumer_stress_tier"],
    },
    {
        "id": "stage_3",
        "label": "Credit Bridging",
        "tickers": ["COF", "JPM", "AXP", "AFRM"],
        "threshold": 2,
        "check": lambda facts, t: (
            _severity("credit_quality_trend", _get_signal(facts, t, "credit_quality_trend")) >= 2
        ),
        "evidence_fields": ["credit_quality_trend"],
    },
    {
        "id": "stage_4",
        "label": "Housing Stress",
        "tickers": ["OPEN"],
        "threshold": 1,
        "check": lambda facts, t: (
            _severity("housing_demand", _get_signal(facts, t, "housing_demand")) >= 2
        ),
        "evidence_fields": ["housing_demand"],
    },
    {
        "id": "stage_5",
        "label": "Services Contraction",
        "tickers": ["UBER", "ABNB", "SHOP"],
        "threshold": 2,
        "check": lambda facts, t: (
            _severity("services_demand", _get_signal(facts, t, "services_demand")) >= 2
        ),
        "evidence_fields": ["services_demand"],
    },
    {
        "id": "stage_6",
        "label": "Auto/Utility Defaults",
        "tickers": ["COF", "JPM"],
        "threshold": 1,
        "check": lambda facts, t: (
            _severity("auto_credit_trend", _get_signal(facts, t, "auto_credit_trend")) >= 2
        ),
        "evidence_fields": ["auto_credit_trend"],
    },
    {
        "id": "stage_7",
        "label": "Subscription Churn",
        "tickers": ["NFLX", "SPOT"],
        "threshold": 1,
        "check": lambda facts, t: (
            _severity("pricing_power", _get_signal(facts, t, "pricing_power")) >= 2
            and _severity("management_tone_shift", _get_signal(facts, t, "management_tone_shift")) >= 2
        ),
        "evidence_fields": ["pricing_power", "management_tone_shift"],
    },
]


def assess_waterfall(facts_by_ticker: dict) -> list[StageResult]:
    """Evaluate each stage against the most recent signals per ticker."""
    results = []
    for stage in STAGE_DEFS:
        triggered_by = []
        evidence = {}
        for ticker in stage["tickers"]:
            if stage["check"](facts_by_ticker, ticker):
                triggered_by.append(ticker)
                # Collect evidence from all relevant fields
                ev_parts = []
                for field in stage["evidence_fields"]:
                    ev = _get_evidence(facts_by_ticker, ticker, field)
                    if ev:
                        ev_parts.append(ev)
                if ev_parts:
                    evidence[ticker] = "; ".join(ev_parts)

        firing = len(triggered_by) >= stage["threshold"]
        count = f"{len(triggered_by)}/{len(stage['tickers'])}"

        results.append(StageResult(
            id=stage["id"],
            label=stage["label"],
            firing=firing,
            triggered_by=triggered_by,
            evidence=evidence,
            count=count,
        ))
    return results


def phase_x_status(stages: list[StageResult]) -> tuple[bool, int, int]:
    """Returns (is_phase_x, stages_firing, total_stages)."""
    firing_stages = [s for s in stages if s.firing]
    stages_firing = len(firing_stages)
    total = len(stages)

    # Phase X requires 5+ stages AND 4+ distinct tickers
    distinct_tickers = set()
    for s in firing_stages:
        distinct_tickers.update(s.triggered_by)

    is_phase_x = stages_firing >= 5 and len(distinct_tickers) >= 4
    return is_phase_x, stages_firing, total


def regime_label(stages_firing: int, is_phase_x: bool) -> str:
    """Map stages firing count to a regime label."""
    if is_phase_x:
        return "Phase X"
    if stages_firing == 0:
        return "Healthy"
    if stages_firing <= 2:
        return "Pre-stress"
    if stages_firing == 3:
        return "Early-stress"
    return "Deteriorating"
