# Jackson Framework Eval

Validates the Rittenhouse skill against Eric Jackson's three-signal framework
for evaluating Bitcoin-mining-to-AI-infrastructure pivots.

## Ground truth

Jackson analyzed 6 companies across ~12 quarters each and identified three
signals that separate winners from losers:

1. **Constraint under pressure** — disciplined decisions at worst moments
2. **Candor** — honest during bad quarters, zero excuses consistently
3. **Signed vs. aspirational** — named counterparties and real contract values

**Expected winners (Jackson's picks):** IREN, CIFR, HUT
**Expected losers:** WULF, NBIS, CRWV

## Transcript sourcing

Drop earnings call transcripts into `data/<ticker>/<quarter>/transcript.txt`
using `eca ingest-transcript`:

```bash
# Example: ingest 12 quarters for IREN
eca ingest-transcript iren q1-2023 ~/Downloads/iren-q1-2023.txt
eca ingest-transcript iren q2-2023 ~/Downloads/iren-q2-2023.txt
# ... etc
```

Repeat for all 6 tickers. Quarters should span roughly Q1-2023 through Q4-2025
to cover the Bitcoin bear market through AI pivot.

## Running the eval

```bash
# Phase 1: single-call analysis (no prior context)
python evals/jackson_framework/run_eval.py --phase baseline

# Phase 2: longitudinal analysis (with --compare-prior)
python evals/jackson_framework/run_eval.py --phase longitudinal

# Phase 3: produce comparison report
python evals/jackson_framework/run_eval.py --phase report
```

## What success looks like

- IREN/CIFR/HUT composite grades cluster meaningfully above WULF/NBIS/CRWV
- The analyzer independently flags Jackson's key moments (Iren 18-cent discipline,
  Cipher zero-excuses, CoreWeave dismissiveness, Terawulf/Nebius stasis)
- Longitudinal runs detect Hut 8's language tightening and Terawulf/Nebius
  lack of evolution
