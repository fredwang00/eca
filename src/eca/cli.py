import click
from pathlib import Path


@click.group()
def cli():
    """Earnings Call Analyzer - atomic data pipeline for candor analysis."""
    pass


@cli.command("ingest-transcript")
@click.argument("ticker")
@click.argument("quarter")
@click.argument("source", type=click.Path(exists=True, path_type=Path))
def ingest_transcript_cmd(ticker: str, quarter: str, source: Path):
    """Register a transcript and initialize the quarter."""
    from eca.processors.ingest_transcript import ingest_transcript, validate_quarter_slug

    try:
        validate_quarter_slug(quarter)
    except ValueError as e:
        raise click.UsageError(str(e))

    target = ingest_transcript(ticker, quarter, source)
    click.echo(f"Ingested transcript -> {target}")


@cli.command("ingest-metrics")
@click.argument("ticker")
def ingest_metrics_cmd(ticker: str):
    """Fetch quarterly financial metrics from Yahoo Finance."""
    from eca.processors.ingest_metrics import ingest_metrics
    click.echo(f"Fetching metrics for {ticker.upper()} from Yahoo Finance...")
    raw_path = ingest_metrics(ticker)
    click.echo(f"Wrote metrics -> {raw_path}")


@cli.command("migrate")
@click.option("--dry-run", is_flag=True, help="Show what would be migrated")
def migrate_cmd(dry_run: bool):
    """Migrate old directory layout to new data/ layout."""
    from eca.config import project_root
    from eca.processors.migrate import discover_files, migrate

    root = project_root()
    if dry_run:
        entries = discover_files(root)
        for entry in entries:
            click.echo(f"  {entry['ticker']} {entry['quarter_slug']}")
        click.echo(f"\n{len(entries)} quarters to migrate")
        return

    migrate(root)
    click.echo("Migration complete.")


@cli.command("analyze")
@click.argument("ticker")
@click.argument("quarter", required=False)
@click.option("--all", "analyze_all", is_flag=True, help="Analyze all quarters missing analysis")
@click.option("--model", default="claude-sonnet-4-6", help="Model to use (e.g. claude-sonnet-4-6, claude-opus-4-6)")
@click.option("--compare-prior", is_flag=True, help="Include prior quarter's analysis as context for longitudinal comparison")
def analyze_cmd(ticker: str, quarter: str | None, analyze_all: bool, model: str, compare_prior: bool):
    """Run Rittenhouse candor analysis via Anthropic API."""
    from eca.config import data_dir, skills_dir, get_sector, quarter_dir
    from eca.processors.analyze import (
        build_system_prompt, build_user_message, run_analysis,
        extract_and_update_facts, find_prior_analysis,
    )
    from eca.schema import load_facts

    ticker_upper = ticker.upper()
    sector = get_sector(ticker_upper)
    skill_version = f"base+{sector}" if sector != "base" else "base"
    system_prompt = build_system_prompt(skills_dir(), sector)

    if analyze_all:
        ticker_path = data_dir() / ticker.lower()
        if not ticker_path.exists():
            raise click.UsageError(f"No data directory for {ticker_upper}. Run ingest-transcript first.")
        from eca.config import quarter_sort_key
        quarters_to_analyze = sorted(
            (d.name for d in ticker_path.iterdir()
             if d.is_dir() and not (d / "analysis.md").exists()),
            key=quarter_sort_key,
        )
    elif quarter:
        quarters_to_analyze = [quarter]
    else:
        raise click.UsageError("Provide a quarter or use --all")

    for q in quarters_to_analyze:
        q_dir = quarter_dir(ticker_upper, q)
        transcript_path = q_dir / "transcript.txt"
        if not transcript_path.exists():
            click.echo(f"Skipping {q}: no transcript.txt")
            continue

        click.echo(f"Analyzing {ticker_upper} {q}...")
        transcript = transcript_path.read_text()

        facts = load_facts(q_dir / "facts.json")
        metrics = facts.get("metrics")

        prior = None
        if compare_prior:
            prior = find_prior_analysis(ticker_upper, q)
            if prior:
                click.echo("  Including prior analysis for longitudinal comparison")
            else:
                click.echo("  No prior analysis found")

        user_message = build_user_message(transcript, metrics, prior_analysis=prior)

        analysis = run_analysis(system_prompt, user_message, model=model)

        (q_dir / "analysis.md").write_text(analysis)
        extract_and_update_facts(q_dir / "facts.json", analysis, skill_version)
        click.echo(f"  -> {q_dir / 'analysis.md'}")


@cli.command("build-index")
def build_index_cmd():
    """Rebuild SQLite index from facts.json files."""
    from eca.config import data_dir
    from eca.db import rebuild_index

    db_path = data_dir() / "eca.db"
    rebuild_index(db_path)
    click.echo(f"Index rebuilt -> {db_path}")


@cli.command("synthesize")
@click.option("--sector", help="Sector name (e.g. infra, ai, crypto) or 'all'")
@click.option("--list-sectors", is_flag=True, help="List available sectors and exit")
@click.option("--model", default="claude-sonnet-4-6", help="Model to use")
def synthesize_cmd(sector: str | None, list_sectors: bool, model: str):
    """Generate sector-level synthesis from cross-company analysis data."""
    from eca.config import WATCHLIST_SECTORS, data_dir
    from eca.db import rebuild_index
    from eca.processors.synthesize import ticker_brief, sector_synthesis

    if list_sectors:
        for name, tickers in WATCHLIST_SECTORS.items():
            click.echo(f"  {name:12s} {', '.join(tickers)}")
        return

    if not sector:
        raise click.UsageError("Provide --sector <name> or --list-sectors")

    sectors = list(WATCHLIST_SECTORS.keys()) if sector == "all" else [sector]

    for s in sectors:
        if s not in WATCHLIST_SECTORS:
            raise click.UsageError(f"Unknown sector '{s}'. Use --list-sectors to see options.")

    # Rebuild index before synthesis
    db_path = data_dir() / "eca.db"
    click.echo("Rebuilding index...")
    rebuild_index(db_path)

    for s in sectors:
        tickers = WATCHLIST_SECTORS[s]
        click.echo(f"\n=== {s} ({len(tickers)} tickers) ===")

        # Stage 1: ticker briefs
        for ticker in tickers:
            click.echo(f"  {ticker}: generating brief...")
            result = ticker_brief(ticker, model=model)
            if result:
                click.echo(f"    -> {result}")
            else:
                click.echo(f"    (no analyzed data, skipped)")

        # Stage 2: sector synthesis
        click.echo(f"  Synthesizing {s}...")
        result = sector_synthesis(s, model=model)
        if result:
            click.echo(f"  -> {result}")
        else:
            click.echo(f"  (no data for synthesis)")


@cli.command("query")
@click.argument("query_text")
@click.option("--ticker", help="Filter by ticker")
def query_cmd(query_text: str, ticker: str | None):
    """Query across the data tree."""
    from eca.processors.query import query_grades, query_flags, format_grades_table, load_all_facts

    lowered = query_text.lower()

    # Structured: grades
    if "grades" in lowered or "grade" in lowered:
        target = ticker or query_text.split()[-1].upper()
        click.echo(format_grades_table(query_grades(target)))
        return

    # Structured: flags
    if "flag" in lowered:
        for word in query_text.split():
            if "_" in word:
                for r in query_flags(word):
                    click.echo(f"  {r['ticker']} {r['quarter']}: {', '.join(r['flags'])}")
                return

    # Fallback: natural language query via Claude
    import json
    from eca.llm import run_analysis

    all_facts = load_all_facts()
    if not all_facts:
        click.echo("No data found.")
        return

    context = json.dumps(all_facts, indent=2)
    system = "You are a financial data analyst. Answer questions based on the provided earnings call analysis data. Be concise."
    answer = run_analysis(system, f"Data:\n{context}\n\nQuestion: {query_text}")
    click.echo(answer)
