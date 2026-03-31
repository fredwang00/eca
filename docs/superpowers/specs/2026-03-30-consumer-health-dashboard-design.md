# Consumer Health Dashboard — Design Spec

## Problem

The ECA pipeline analyzes 314 earnings call transcripts across 31 tickers and produces per-quarter candor grades, financial metrics, and sector syntheses. But there's no unified view that aggregates cross-company signals into a macro regime assessment. The "consumer distress waterfall" and "Phase X convergence detection" currently exist only as informal analysis in conversation context — not as code, not as a durable artifact.

## Solution

Add three things to ECA:

1. **Structured signal extraction** — new fields extracted by the LLM during `eca analyze`, stored in facts.json
2. **Waterfall engine** — deterministic aggregation of signals into a 7-stage consumer distress model
3. **Dashboard command** — `eca dashboard` renders a standing view (no LLM), writes `data/dashboard.md`, and optionally generates a narrative synthesis (one LLM call)

## Signal Schema

Added to `facts.json` alongside `candor` and `metrics`:

```json
"signals": {
  "extracted_at": "2026-03-30",
  "consumer_stress_tier": "neutral | trade_down | essentials_pressure | credit_bridging",
  "credit_quality_trend": "improving | stable | normalizing | deteriorating",
  "auto_credit_trend": "improving | stable | normalizing | deteriorating",
  "housing_demand": "expanding | stable | softening | contracting",
  "services_demand": "expanding | stable | softening | contracting",
  "capex_direction": "accelerating | stable | decelerating | cutting",
  "pricing_power": "strong | moderate | weak | capitulating",
  "management_tone_shift": "more_confident | consistent | more_cautious | alarmed",
  "signal_evidence": {
    "consumer_stress_tier": "one-line transcript quote justifying the value",
    "pricing_power": "one-line transcript quote justifying the value"
  }
}
```

### Field applicability by sector

| Field | Applies to |
|-------|-----------|
| consumer_stress_tier | WMT, COST, TGT, AFRM, LMND, ROOT |
| credit_quality_trend | JPM, COF, AXP, AFRM |
| auto_credit_trend | COF, JPM |
| housing_demand | OPEN |
| services_demand | UBER, ABNB, SHOP |
| capex_direction | NVDA, MSFT, GOOG, META, AMZN, AAPL, TSLA, IREN, CIFR, WULF, RKLB (informational — powers Capex Landscape section, not used as a waterfall trigger) |
| pricing_power | All tickers |
| management_tone_shift | All tickers |

Null means "not applicable to this ticker." The LLM prompt specifies which fields to populate based on the company. The LLM must populate `signal_evidence` with a one-line transcript quote for every non-null signal field.

### Enum ordering

Values are ordered by severity (0 = healthy, N = worst). The waterfall engine can treat position as a numeric severity level without parsing strings:

- consumer_stress_tier: neutral(0) → trade_down(1) → essentials_pressure(2) → credit_bridging(3)
- credit_quality_trend: improving(0) → stable(1) → normalizing(2) → deteriorating(3)
- auto_credit_trend: improving(0) → stable(1) → normalizing(2) → deteriorating(3)
- housing_demand: expanding(0) → stable(1) → softening(2) → contracting(3)
- services_demand: expanding(0) → stable(1) → softening(2) → contracting(3)
- capex_direction: accelerating(0) → stable(1) → decelerating(2) → cutting(3)
- pricing_power: strong(0) → moderate(1) → weak(2) → capitulating(3)
- management_tone_shift: more_confident(0) → consistent(1) → more_cautious(2) → alarmed(3)

`extracted_at` is metadata (ISO date string), not an ordinal signal.

## Prompt Changes

Append a "Signal Extraction" section to `skills/base.md` after the Composite Grade Calculation. The LLM outputs a fenced code block tagged `SIGNALS` (triple-backtick followed by `SIGNALS`, no colon) at the end of analysis.md, after the Tracking Notes section. The parser matches this as a language-tagged fenced block, analogous to ` ```json `.

```
```SIGNALS
{
  "consumer_stress_tier": "trade_down",
  "credit_quality_trend": null,
  "auto_credit_trend": null,
  "housing_demand": null,
  "services_demand": null,
  "capex_direction": "stable",
  "pricing_power": "moderate",
  "management_tone_shift": "more_cautious",
  "signal_evidence": {
    "consumer_stress_tier": "Guests are choiceful, stretching budgets...",
    "pricing_power": "We recently lowered prices on thousands of items...",
    "management_tone_shift": "Sentiment is at a 3-year low..."
  }
}
```
```

### Parser addition

New function `parse_signals()` in `src/eca/parsers/grades.py` extracts the SIGNALS JSON block. `extract_and_update_facts()` writes it to facts.json.

## Waterfall Engine

New module: `src/eca/engine/waterfall.py`

### 7-stage distress model

| # | Stage | Key Tickers | Trigger Signals | Threshold |
|---|-------|------------|-----------------|-----------|
| 1 | Discretionary Cuts | TGT, ABNB, SHOP | consumer_stress_tier in [trade_down, essentials_pressure, credit_bridging] OR pricing_power in [weak, capitulating] OR services_demand in [softening, contracting] | 2 of 3 |
| 2 | Essential Trade-Down | WMT, COST | consumer_stress_tier in [essentials_pressure, credit_bridging] | 1 of 2 |
| 3 | Credit Bridging | COF, JPM, AXP, AFRM | credit_quality_trend in [normalizing, deteriorating] | 2 of 4 |
| 4 | Housing Stress | OPEN | housing_demand in [softening, contracting] | 1 of 1 |
| 5 | Services Contraction | UBER, ABNB, SHOP | services_demand in [softening, contracting] | 2 of 3 |
| 6 | Auto/Utility Defaults | COF, JPM | auto_credit_trend in [normalizing, deteriorating] | 1 of 2 |
| 7 | Subscription Churn | NFLX, SPOT | pricing_power in [weak, capitulating] AND management_tone_shift in [more_cautious, alarmed] | 1 of 2 |

Stage 7 intentionally requires BOTH conditions (pricing power erosion AND tone shift). A cautious tone alone could reflect content investment concerns, not consumer distress. Both firing together is the late-cycle signal.

### Phase X rule and regime labels

| Stages Firing | Regime Label |
|--------------|-------------|
| 0 | Healthy |
| 1-2 | Pre-stress |
| 3 | Early-stress |
| 4 | Deteriorating |
| 5+ | Phase X |

Phase X requires 5 or more of 7 stages firing simultaneously AND at least 4 distinct tickers contributing (to prevent a single company's bad quarter from triggering multiple stages via overlap — e.g., COF appears in both Stages 3 and 6).

### Engine interface

```python
@dataclass
class StageResult:
    id: str
    label: str
    firing: bool
    triggered_by: list[str]  # ticker symbols that triggered
    evidence: dict[str, str]  # ticker -> evidence quote
    count: str  # e.g., "2/4"

def assess_waterfall(facts_by_ticker: dict) -> list[StageResult]:
    """Read most recent quarter's signals per ticker,
    evaluate each stage, return ordered results.

    'Most recent' = chronologically latest quarter directory
    that has a facts.json with a non-null 'signals' key."""

def phase_x_status(stages: list[StageResult]) -> tuple[bool, int, int]:
    """Returns (is_phase_x, stages_firing, total_stages)."""
```

## Dashboard Command

New CLI command: `eca dashboard`

### Options

| Flag | Effect |
|------|--------|
| (none) | Standing view: waterfall + scores + capex + signals. Terminal output + writes data/dashboard.md |
| --narrative | Adds LLM-generated "what changed" narrative (one API call) |
| --model | Model for narrative (default: claude-sonnet-4-6) |

### Standing view sections (no LLM call)

1. **Distress Waterfall** — 7 stages with firing status, triggering tickers, and threshold counts
2. **Phase X Assessment** — stages firing count, threshold status, one-line regime label (pre-stress / early-stress / deteriorating / Phase X)
3. **Score Trajectories** — last 4 quarters per ticker, avg and trend arrow, grouped by sector
4. **Capex Landscape** — quarterly capex from metrics, Mag 4 aggregate and run-rate
5. **Market Context** — manual annotation section for external signals (HY OAS, Fed Funds, VIX). Placeholder for future FRED API integration.
6. **Signal Detail** — per-ticker signal values with evidence quotes for any non-neutral signals

### Narrative mode (one LLM call)

When `--narrative` is passed, the dashboard assembles the standing view data into a single LLM prompt and asks for a 3-5 paragraph "what changed" assessment. Appended to both terminal output and markdown file under a `## Narrative Assessment` heading.

System prompt for narrative: `skills/dashboard-narrative.md` (new file). Instructs the LLM to synthesize the waterfall status, identify the most important signal changes since last quarter, assess Phase X proximity, and flag what to watch next.

### Markdown artifact

Written to `data/dashboard.md`, overwritten each run. Includes timestamp, all sections, and narrative if requested. Designed to be readable standalone, pasteable into other LLM conversations, or rendered in any markdown viewer.

## Market Context Section

The dashboard includes a manually-updated market context section for external signals that operate on different frequencies than quarterly earnings:

```markdown
## Market Context (external — update manually)

| Signal | Value | Last Updated | Source |
|--------|-------|-------------|--------|
| HY OAS | ___ | ___ | ICE BofA US High Yield Index |
| Fed Funds | ___ | ___ | FRED |
| VIX | ___ | ___ | CBOE |
| 10Y Yield | ___ | ___ | FRED |
```

**Future integration:** These fields are candidates for automated population via the FRED API (Federal Reserve Economic Data, free API key). When implemented, `eca dashboard` would fetch current values at render time. This is explicitly out of scope for v1 but the markdown structure is designed to accommodate it — the table format maps directly to a `market_context` dict that a FRED fetcher would populate.

Credit spreads widening from historical lows (as noted in ICE BofA HY OAS data, March 2026) would serve as a leading indicator upstream of Stage 3 (credit bridging). By the time bank earnings confirm charge-off increases, spread widening has typically been underway for 6-12 months. The market context section allows the user to read "Stage 3: NOT FIRING" alongside "HY OAS: widening" and make the forward-looking judgment.

## Data Flow

```
eca analyze TICKER QUARTER
  └─ LLM extracts candor grades + signals
  └─ writes analysis.md (includes SIGNALS block)
  └─ parser extracts grades + signals
  └─ writes facts.json (candor + signals sections)

eca build-index
  └─ reads all facts.json
  └─ rebuilds eca.db (add signals columns)

eca dashboard [--narrative]
  └─ reads facts.json for most recent quarter per ticker
  └─ runs waterfall engine (deterministic)
  └─ computes score trajectories from eca.db
  └─ computes capex landscape from metrics
  └─ renders terminal output
  └─ writes data/dashboard.md
  └─ (if --narrative) runs one LLM call for narrative synthesis
```

## File Changes Summary

| File | Change |
|------|--------|
| skills/base.md | Add Signal Extraction section to prompt |
| skills/dashboard-narrative.md | New: system prompt for narrative synthesis |
| src/eca/schema.py | Add signals types to schema |
| src/eca/parsers/grades.py | Add parse_signals() function |
| src/eca/processors/analyze.py | Extract signals in extract_and_update_facts() |
| src/eca/engine/__init__.py | New package |
| src/eca/engine/waterfall.py | New: stage definitions + assess_waterfall() + phase_x_status() |
| src/eca/processors/dashboard.py | New: dashboard rendering + markdown generation |
| src/eca/cli.py | Add dashboard command |
| src/eca/db.py | Add signals columns to quarter_facts table |

## Backfill Strategy

Signal extraction requires re-analyzing recent quarters. Strategy:

- Re-analyze only the **most recent 2 quarters** per ticker with data (~44 LLM calls across ~22 tickers that have analyzed data)
- Older quarters get null signals — the dashboard only reads the most recent quarter anyway
- Future analyses automatically include signals going forward
- If deeper historical signal data is desired later, re-analyze selectively

## Out of Scope for v1

- Web UI (future rendering layer on same data)
- FRED API integration (market context is manual for now)
- Configurable stage definitions (hardcoded in code, externalize to YAML later)
- Alerts/notifications when stages change
- Historical dashboard snapshots (overwrite for now, versioned later)
