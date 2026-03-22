#!/usr/bin/env python3
"""Jackson framework eval: validate Rittenhouse skill against ground truth.

Eric Jackson identified 3 signals across 6 companies that separate winners
from losers in the Bitcoin-mining-to-AI-infrastructure pivot. This eval tests
whether our analyzer independently arrives at the same conclusions.

Usage:
    python evals/jackson_framework/run_eval.py --phase baseline
    python evals/jackson_framework/run_eval.py --phase longitudinal
    python evals/jackson_framework/run_eval.py --phase report
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Ensure project root is on path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from eca.config import data_dir, skills_dir, get_sector, quarter_dir, COMPANY_NAMES
from eca.processors.analyze import (
    build_system_prompt,
    build_user_message,
    run_analysis,
    extract_and_update_facts,
    find_prior_analysis,
)
from eca.schema import load_facts

JACKSON_PICKS = {"IREN", "CIFR", "HUT"}
JACKSON_AVOIDS = {"WULF", "NBIS", "CRWV"}
ALL_TICKERS = JACKSON_PICKS | JACKSON_AVOIDS

MODEL = "claude-sonnet-4-6"

# Key moments Jackson flagged — used in report to check for detection
JACKSON_SIGNALS = {
    "IREN": {
        "constraint": "Turned down hosting deal at 18 cents — 'easy way out, but a cop-out'",
        "signed": "$9.7B Microsoft contract, $3.6B GPU financing (Goldman/JPM)",
        "candor": "Acknowledged 23% revenue decline directly, no reframing",
    },
    "CIFR": {
        "constraint": "Zero excuses across 12 consecutive earnings calls",
        "signed": "$3B Google, $5.5B AWS, $2B bond (6.5x oversubscribed)",
        "candor": "$734M GAAP loss addressed directly — 'never done until you're done'",
    },
    "HUT": {
        "constraint": "Language tightened over 4 consecutive quarters after institutional counterparties arrived",
        "signed": "$7B NOI contract (Anthropic + Google)",
        "candor": "Had promotional phase, then corrected — structural shift visible in transcripts",
    },
    "WULF": {
        "stasis": "No evolution across transcript pairs — reads like same press release",
    },
    "NBIS": {
        "stasis": "No evolution across transcript pairs — reads like same press release",
    },
    "CRWV": {
        "dismissiveness": "'People who couldn't spell GPU two years ago' — contempt instead of specifics",
        "structural": "Leases power infrastructure (vs. owns) — single third-party delay forced guidance cut",
    },
}


def find_quarters(ticker: str) -> list[str]:
    """Find all quarters with transcripts for a ticker."""
    ticker_path = data_dir() / ticker.lower()
    if not ticker_path.exists():
        return []
    return sorted(
        d.name
        for d in ticker_path.iterdir()
        if d.is_dir() and (d / "transcript.txt").exists()
    )


def run_baseline(tickers: set[str] | None = None):
    """Phase 1: Single-call analysis without prior context."""
    targets = tickers or ALL_TICKERS
    for ticker in sorted(targets):
        quarters = find_quarters(ticker)
        if not quarters:
            print(f"  {ticker}: no transcripts found, skipping")
            continue

        sector = get_sector(ticker)
        skill_version = f"base+{sector}" if sector != "base" else "base"
        system_prompt = build_system_prompt(skills_dir(), sector)

        for q in quarters:
            q_dir = quarter_dir(ticker, q)
            analysis_path = q_dir / "analysis.md"

            if analysis_path.exists():
                print(f"  {ticker} {q}: already analyzed, skipping")
                continue

            print(f"  {ticker} {q}: analyzing...")
            transcript = (q_dir / "transcript.txt").read_text()
            facts = load_facts(q_dir / "facts.json")
            metrics = facts.get("metrics")
            user_message = build_user_message(transcript, metrics)

            analysis = run_analysis(system_prompt, user_message, model=MODEL)
            analysis_path.write_text(analysis)
            extract_and_update_facts(q_dir / "facts.json", analysis, skill_version)
            print(f"    -> {analysis_path}")


def run_longitudinal(tickers: set[str] | None = None):
    """Phase 2: Re-analyze later quarters with --compare-prior context.

    Only re-analyzes quarters that have a prior analysis available.
    Saves longitudinal analysis alongside the original as analysis-longitudinal.md.
    """
    targets = tickers or ALL_TICKERS
    for ticker in sorted(targets):
        quarters = find_quarters(ticker)
        if len(quarters) < 2:
            print(f"  {ticker}: need >= 2 quarters for longitudinal, skipping")
            continue

        sector = get_sector(ticker)
        skill_version = f"base+{sector}" if sector != "base" else "base"
        system_prompt = build_system_prompt(skills_dir(), sector)

        for q in quarters:
            q_dir = quarter_dir(ticker, q)
            longitudinal_path = q_dir / "analysis-longitudinal.md"

            if longitudinal_path.exists():
                print(f"  {ticker} {q}: longitudinal already exists, skipping")
                continue

            prior = find_prior_analysis(ticker, q)
            if not prior:
                print(f"  {ticker} {q}: no prior analysis, skipping")
                continue

            print(f"  {ticker} {q}: longitudinal analysis...")
            transcript = (q_dir / "transcript.txt").read_text()
            facts = load_facts(q_dir / "facts.json")
            metrics = facts.get("metrics")
            user_message = build_user_message(
                transcript, metrics, prior_analysis=prior
            )

            analysis = run_analysis(system_prompt, user_message, model=MODEL)
            longitudinal_path.write_text(analysis)
            print(f"    -> {longitudinal_path}")


def collect_grades() -> dict[str, list[dict]]:
    """Load all facts.json files for eval tickers and return grades by ticker."""
    results: dict[str, list[dict]] = {}
    for ticker in sorted(ALL_TICKERS):
        quarters = find_quarters(ticker)
        ticker_grades = []
        for q in quarters:
            facts_path = quarter_dir(ticker, q) / "facts.json"
            facts = load_facts(facts_path)
            candor = facts.get("candor", {})
            if candor.get("composite_grade"):
                ticker_grades.append(
                    {
                        "quarter": q,
                        "composite_grade": candor["composite_grade"],
                        "composite_score": candor.get("composite_score"),
                        "dim1": candor.get("dim1_grade"),
                        "dim2": candor.get("dim2_grade"),
                        "dim3": candor.get("dim3_grade"),
                        "dim4": candor.get("dim4_grade"),
                        "dim5": candor.get("dim5_grade"),
                    }
                )
        if ticker_grades:
            results[ticker] = ticker_grades
    return results


def run_report():
    """Phase 3: Produce comparison report and check clustering."""
    grades = collect_grades()

    if not grades:
        print("No grades found. Run --phase baseline first.")
        return

    print("=" * 72)
    print("JACKSON FRAMEWORK EVAL REPORT")
    print("=" * 72)

    # Per-ticker summary
    print("\n## Per-Ticker Grade Summary\n")
    ticker_averages: dict[str, float] = {}

    for ticker in sorted(ALL_TICKERS):
        group = "PICK" if ticker in JACKSON_PICKS else "AVOID"
        company = COMPANY_NAMES.get(ticker, ticker)
        ticker_grades = grades.get(ticker, [])

        if not ticker_grades:
            print(f"  {ticker} ({company}) [{group}]: NO DATA")
            continue

        scores = [g["composite_score"] for g in ticker_grades if g["composite_score"]]
        avg = sum(scores) / len(scores) if scores else 0
        ticker_averages[ticker] = avg

        print(f"\n  {ticker} ({company}) [{group}]  avg={avg:.2f}")
        for g in ticker_grades:
            dims = f"  D1={g['dim1']} D2={g['dim2']} D3={g['dim3']} D4={g['dim4']} D5={g['dim5']}"
            print(
                f"    {g['quarter']:10s}  {g['composite_grade']:3s} ({g['composite_score']:.2f}){dims}"
            )

    # Cluster analysis
    print("\n" + "=" * 72)
    print("## Cluster Analysis\n")

    pick_scores = [ticker_averages[t] for t in JACKSON_PICKS if t in ticker_averages]
    avoid_scores = [
        ticker_averages[t] for t in JACKSON_AVOIDS if t in ticker_averages
    ]

    if pick_scores and avoid_scores:
        pick_avg = sum(pick_scores) / len(pick_scores)
        avoid_avg = sum(avoid_scores) / len(avoid_scores)
        gap = pick_avg - avoid_avg

        print(f"  Jackson PICKS avg:  {pick_avg:.2f}")
        for t in sorted(JACKSON_PICKS):
            if t in ticker_averages:
                print(f"    {t}: {ticker_averages[t]:.2f}")

        print(f"  Jackson AVOIDS avg: {avoid_avg:.2f}")
        for t in sorted(JACKSON_AVOIDS):
            if t in ticker_averages:
                print(f"    {t}: {ticker_averages[t]:.2f}")

        print(f"\n  Gap (PICKS - AVOIDS): {gap:+.2f}")

        if gap > 0.5:
            print("  RESULT: STRONG separation — analyzer aligns with Jackson")
        elif gap > 0.2:
            print("  RESULT: MODERATE separation — directionally correct")
        elif gap > 0:
            print("  RESULT: WEAK separation — right direction but not convincing")
        else:
            print("  RESULT: NO separation or INVERTED — skill needs tuning")
    else:
        print("  Insufficient data for cluster analysis.")
        print(
            f"  PICKS with data: {[t for t in JACKSON_PICKS if t in ticker_averages]}"
        )
        print(
            f"  AVOIDS with data: {[t for t in JACKSON_AVOIDS if t in ticker_averages]}"
        )

    # Signal detection check
    print("\n" + "=" * 72)
    print("## Signal Detection (manual review)\n")
    print("Check the analysis.md files for whether the analyzer independently")
    print("detected these Jackson-flagged signals:\n")

    for ticker in sorted(ALL_TICKERS):
        signals = JACKSON_SIGNALS.get(ticker, {})
        group = "PICK" if ticker in JACKSON_PICKS else "AVOID"
        print(f"  {ticker} [{group}]:")
        for signal_type, description in signals.items():
            print(f"    [{signal_type}] {description}")
        print()

    # Write machine-readable results
    report_path = Path(__file__).parent / "results.json"
    report_path.write_text(
        json.dumps(
            {
                "ticker_averages": ticker_averages,
                "pick_avg": sum(pick_scores) / len(pick_scores)
                if pick_scores
                else None,
                "avoid_avg": sum(avoid_scores) / len(avoid_scores)
                if avoid_scores
                else None,
                "gap": (sum(pick_scores) / len(pick_scores))
                - (sum(avoid_scores) / len(avoid_scores))
                if pick_scores and avoid_scores
                else None,
                "grades": {
                    t: grades.get(t, []) for t in sorted(ALL_TICKERS)
                },
            },
            indent=2,
        )
    )
    print(f"Machine-readable results -> {report_path}")


def main():
    parser = argparse.ArgumentParser(description="Jackson framework eval")
    parser.add_argument(
        "--phase",
        choices=["baseline", "longitudinal", "report"],
        required=True,
    )
    parser.add_argument(
        "--ticker",
        help="Run for a single ticker (useful for testing)",
    )
    args = parser.parse_args()

    tickers = {args.ticker.upper()} if args.ticker else None

    if args.phase == "baseline":
        print("Phase 1: Single-call baseline analysis")
        run_baseline(tickers)
    elif args.phase == "longitudinal":
        print("Phase 2: Longitudinal analysis with --compare-prior")
        run_longitudinal(tickers)
    elif args.phase == "report":
        print("Generating eval report...")
        run_report()


if __name__ == "__main__":
    main()
