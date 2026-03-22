# Earnings Call Candor Analyzer

Grades earnings call transcripts on executive communication quality using L.J. Rittenhouse's *Investing Between the Lines* framework. Given a transcript, it scores five dimensions — financial candor, strategic clarity, stakeholder balance, linguistic FOG, and long-term vision — with letter grades backed by specific transcript evidence. Designed to help investors distinguish trustworthy disclosure from corporate obfuscation.

## Installation

Requires Python 3.11+.

```bash
pip install -e .
```

This installs the `eca` CLI and its dependencies (click, anthropic, openai, yfinance).

You'll need an Anthropic API key (or access to the Hendrix AI gateway) exported as `ANTHROPIC_API_KEY`.

## CLI usage

The `eca` CLI is the primary interface. It implements an atomic data pipeline: ingest transcripts, fetch metrics, run analysis, then query across results.

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

# Use a specific model
eca analyze GOOG q1-2025 --model claude-opus-4-6

# Query grades across quarters
eca query "grades GOOG"

# Natural language queries over the full data tree
eca query "which company improved most between Q1 and Q4 2025?"

# Migrate from the old transcripts/analyses layout to data/
eca migrate --dry-run
eca migrate
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
    q1-2025/
      transcript.txt    # raw earnings call text
      analysis.md       # Rittenhouse framework analysis
      facts.json        # structured grades, metadata, tracking flags
    q2-2025/
    q3-2025/
    q4-2025/
    metrics-raw.json    # yfinance financial data (ticker-level)
```

`facts.json` captures the composite grade, per-dimension grades, company metadata, financial metrics, and tracking notes in a machine-readable format for cross-quarter queries.

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
