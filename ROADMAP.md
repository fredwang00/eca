# Roadmap

## Short-term: high-value, small scope

### 1. CEO/CFO divergence signal
Add an explicit flag to the analysis output that scores whether the CEO and CFO are telling the same story. Jackson uses this as one of his three core axes. Your framework already instructs the LLM to note speaker differences but doesn't extract it as a structured signal. Add a `ceo_cfo_divergence` field to facts.json (e.g., "aligned", "minor tension", "divergent") with a one-line quote justification. Cheap to implement — it's a schema change plus a few lines added to the skill prompt.

### 2. Confidence score (0–100)
Emit a single headline number alongside the Rittenhouse grades. Map it roughly: composite_score 0.0–4.0 → 0–100, but also instruct the LLM to factor in hedging rate, specificity ratio, and forward commitment strength. The point is a number you can plot on a chart and compare across tickers and time without reading prose. Store as `confidence_score` in facts.json.

### 3. Quarter-over-quarter delta in facts.json
Compute and store `delta_score` (current confidence minus prior quarter) and `delta_grade` (e.g., "+0.4" or "-1.2") at index-build time. Surface this in the CLI output and synthesis. Jackson's product is "24-point drop over three calls" — make that a first-class output.

### 4. Hedging rate as a numeric metric
Ask the LLM to estimate a hedging rate (0–100) alongside the FOG grade: what percentage of forward-looking statements include meaningful caveats vs. unqualified assertions? High hedging + high confidence = genuine conviction. Low hedging + high confidence = the Apple Q4 FY2024 pattern. Store as `hedging_rate` in facts.json. The confidence/hedging gap is Jackson's core signal for the Apple case.

### 5. Backfill transcripts for depth tickers
Pick 3–5 tickers where you want real longitudinal signal (IREN already has 10 quarters, good). Go back 8–12 quarters on your highest-conviction names. The framework is ready; the bottleneck is input data.

### 6. `eca dashboard` CLI command
A simple text-based summary: for each ticker, show the last 4 quarters of confidence scores, deltas, and any active flags. One screen, scannable. No web UI needed — just formatted terminal output.

---

## Medium-term: structural capability expansion

### 7. Baseline fingerprint per CEO
Once a ticker has 8+ quarters, compute a per-CEO baseline: mean confidence score, mean hedging rate, standard deviation for each. Store in `data/TICKER/baseline.json`. Then flag any quarter where the score deviates by >1.5σ as an anomaly. This is the core of what Jackson sells — deviation from the CEO's own norm, not deviation from some absolute standard.

### 8. Prepared remarks vs. Q&A split scoring
Your skill already instructs the LLM to distinguish these zones. Extract separate scores for each: prepared remarks confidence and Q&A confidence. A CEO who sounds great in prepared remarks but hedges or deflects under questioning is a different signal than one who's consistent across both.

### 9. Anomaly alerting
When `eca analyze` runs and the new score deviates significantly from baseline, emit a prominent alert: "ALERT: GOOG Q3 2026 confidence score 38 is 2.1σ below Tim Cook's 20-quarter mean of 61." This is the "we detected Apple's AI collapse one quarter early" feature — automated, not requiring manual synthesis.

### 10. Cross-ticker comparison view
`eca compare IREN CIFR WULF` — side-by-side confidence trajectories, hedging rates, and divergence flags for tickers in the same sector. Useful for relative conviction within a thesis (e.g., which GPU-infra management team is communicating most honestly about their pipeline).

### 11. Sector-level anomaly patterns
Extend synthesis to flag when multiple companies in the same sector show simultaneous confidence drops or hedging spikes. "3 of 6 infra tickers showed >10-point confidence drops this quarter" is a sector-level signal that no single-ticker analysis reveals.

### 12. Historical narrative tracker
Automate the bottleneck migration analysis you did manually for IREN. For each ticker with 6+ quarters, extract the dominant constraint or narrative focus per quarter and track how it shifts. Store as a structured timeline in the ticker brief. This is the "what is management worried about, and how has that changed" view.

### 13. Transcript auto-sourcing
Reduce the manual friction of getting transcripts into the system. Whether that's a scraper, an API integration (Seeking Alpha, Motley Fool, or earnings call transcript providers), or a semi-automated clipboard workflow — the bottleneck to value is getting transcripts in faster.
