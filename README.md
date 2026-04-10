# Earnings Call Candor Analyzer

Grades earnings call transcripts on executive communication quality using L.J. Rittenhouse's *Investing Between the Lines* framework. Given a transcript, it scores five dimensions — financial candor, strategic clarity, stakeholder balance, linguistic FOG, and long-term vision — with letter grades backed by specific transcript evidence. Designed to help investors distinguish trustworthy disclosure from corporate obfuscation.

## Installation

Requires Python 3.11+.

```bash
pip install -e .
```

This installs the `eca` CLI and its dependencies (click, anthropic, openai, yfinance).

You'll need one of:
- `ANTHROPIC_API_KEY` for direct Anthropic API access, or
- `ECA_API_KEY` + `ECA_BASE_URL` for an OpenAI-compatible gateway

## CLI usage

The `eca` CLI is the primary interface. It implements an atomic data pipeline: ingest transcripts, fetch metrics, run analysis, build indexes, synthesize across sectors, and render a macro dashboard.

```bash
# Ingest a transcript into the data tree
eca ingest-transcript GOOG q1-2025 ~/Downloads/goog-q1-2025.txt

# Fetch quarterly financial metrics from Yahoo Finance
eca ingest-metrics GOOG

# Run Rittenhouse candor analysis on a single quarter
eca analyze GOOG q1-2025

# Analyze all quarters missing analysis for a ticker
eca analyze GOOG --all

# Include prior quarter context for longitudinal comparison
eca analyze GOOG q2-2025 --compare-prior

# Rebuild the SQLite index from all facts.json files
eca build-index

# Generate sector-level synthesis (briefs + cross-company analysis)
eca synthesize --sector consumer
eca synthesize --sector all
eca synthesize --list-sectors

# Render the consumer health dashboard (no LLM call)
eca dashboard

# Dashboard with LLM-generated narrative assessment
eca dashboard --narrative

# Query grades across quarters
eca query "grades GOOG"

# Natural language queries over the full data tree
eca query "which company improved most between Q1 and Q4 2025?"
```

## Claude Code skill

The analyzer also works as a Claude Code skill for interactive use. Add the skill to `~/.claude/settings.json`:

```json
{
  "skills": ["/path/to/earnings-call-analyzer/SKILL.md"]
}
```

Then invoke it from Claude Code:

```
/analyze-conference-call ~/path/to/transcript.txt
```

## Data layout

Each ticker gets a directory under `data/` with one subdirectory per quarter:

```
data/
  goog/
    brief.md            # per-ticker candor trajectory, FOG patterns, key commitments
    q1-2025/
      transcript.txt    # raw earnings call text
      analysis.md       # Rittenhouse framework analysis
      facts.json        # structured grades, signals, metadata
    q2-2025/
    annual-letter-2025/ # annual shareholder letters follow the same structure
      transcript.txt
      analysis.md
      facts.json
    metrics-raw.json    # yfinance financial data (ticker-level)
  synthesis/
    consumer-YYYY-MM-DD.md  # sector-level synthesis output
  eca.db                # SQLite index (rebuilt from facts.json)
  dashboard.md          # latest dashboard render
```

`facts.json` captures per-dimension candor grades, composite scores, financial metrics, and consumer health signals in a machine-readable format for cross-quarter queries and dashboard aggregation.

## Consumer health dashboard

The dashboard aggregates cross-company signals into a macro regime assessment using a 7-stage consumer distress waterfall:

| Stage | What it detects | Key tickers |
|-------|----------------|-------------|
| 1. Discretionary Cuts | Trade-down or pricing capitulation | TGT, ABNB, SHOP, NKE, RH, LULU |
| 2. Essential Trade-Down | Stress reaching essentials | WMT, COST |
| 3. Credit Bridging | Credit quality deteriorating | COF, JPM, AXP, AFRM, SOFI |
| 4. Housing Stress | Housing demand softening | OPEN |
| 5. Services Contraction | Services demand falling | UBER, ABNB, SHOP |
| 6. Auto/Utility Defaults | Auto credit deteriorating | COF, JPM |
| 7. Subscription Churn | Pricing power + tone shift | NFLX, SPOT |

Stages firing simultaneously determine the regime label: Healthy, Pre-stress, Early-stress, Deteriorating, or Phase X (5+ stages, 4+ distinct tickers).

Signal extraction happens automatically during `eca analyze`. The LLM outputs a `SIGNALS` block at the end of each analysis, which the parser extracts into `facts.json`. The dashboard reads the most recent quarter's signals per ticker and runs the waterfall deterministically — no LLM call required for the standing view.

## What it grades

| Dimension | Weight | What it measures |
|---|---|---|
| Capital Stewardship & Financial Candor | 25% | Specificity of financial disclosure, links to prior guidance, capital allocation rationale |
| Strategic Clarity & Accountability | 25% | Coherence of strategy, measurable milestones, consistency across periods |
| Stakeholder Balance & Culture Signals | 15% | Whether all stakeholders are addressed meaningfully, authenticity of voice |
| FOG Index | 20% | Cliches, weasel words, unsupported superlatives, Q&A evasion |
| Vision, Leadership & Long-Term Orientation | 15% | Falsifiable vision, problem disclosure, investor education, dualistic thinking |

Grades are composited into a weighted score (A through F) with full arithmetic shown. Sector-specific overlays (e.g. insurtech) add domain-relevant criteria.

## Background

Based on L.J. Rittenhouse's *Investing Between the Lines: How to Make Smarter Decisions by Decoding CEO Communications*. The core thesis: executive language quality predicts company performance. Candor builds trust; FOG (Fact-deficient, Obfuscating Generalities) destroys it.
