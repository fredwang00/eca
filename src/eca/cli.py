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
@click.option("--source-provider", help="Name of the transcript provider")
@click.option("--source-url", help="URL the transcript was retrieved from")
@click.option("--retrieved-at", help="Retrieval timestamp (ISO 8601)")
@click.option("--document-date", help="Document date (YYYY-MM-DD)")
@click.option("--call-date", help="Earnings call date (YYYY-MM-DD)")
@click.option("--fiscal-year", type=int, help="Company fiscal year of the document")
@click.option("--fiscal-quarter", type=int, help="Company fiscal quarter (1-4)")
@click.option("--period-start", help="Fiscal period start (YYYY-MM-DD)")
@click.option("--period-end", help="Fiscal period end (YYYY-MM-DD)")
def ingest_transcript_cmd(ticker: str, quarter: str, source: Path, source_provider: str | None,
                          source_url: str | None, retrieved_at: str | None,
                          document_date: str | None, call_date: str | None,
                          fiscal_year: int | None, fiscal_quarter: int | None,
                          period_start: str | None, period_end: str | None):
    """Register a transcript with provenance (raw + normalized + meta + hashes)."""
    from eca.processors.ingest_transcript import ingest_transcript, validate_quarter_slug

    try:
        validate_quarter_slug(quarter)
    except ValueError as e:
        raise click.UsageError(str(e))

    meta = {
        "source_provider": source_provider,
        "source_url": source_url,
        "retrieved_at": retrieved_at,
        "document_date": document_date,
        "call_date": call_date,
        "fiscal_year": fiscal_year,
        "fiscal_quarter": fiscal_quarter,
        "period_start": period_start,
        "period_end": period_end,
    }
    try:
        result = ingest_transcript(ticker, quarter, source, meta=meta)
    except ValueError as e:
        raise click.UsageError(str(e))

    click.echo(f"Ingested transcript -> {result.target}")
    for warning in result.meta["normalization_warnings"]:
        click.echo(f"warning: {warning}", err=True)


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
    from eca.claims import ClaimValidationError
    from eca.config import data_dir
    from eca.db import rebuild_index

    db_path = data_dir() / "eca.db"
    try:
        rebuild_index(db_path)
    except ClaimValidationError as e:
        raise click.ClickException(f"index build failed: {e}")
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


@cli.command("dashboard")
@click.option("--narrative", is_flag=True, help="Add LLM-generated narrative assessment")
@click.option("--model", default="claude-sonnet-4-6", help="Model for narrative")
def dashboard_cmd(narrative: bool, model: str):
    """Render the consumer health dashboard."""
    from eca.config import data_dir, skills_dir
    from eca.db import rebuild_index
    from eca.processors.dashboard import render_dashboard

    db_path = data_dir() / "eca.db"
    click.echo("Rebuilding index...")
    rebuild_index(db_path)

    output = render_dashboard(db_path)

    if narrative:
        click.echo("Generating narrative assessment...")
        from eca.llm import run_analysis

        system_prompt = (skills_dir() / "dashboard-narrative.md").read_text()
        narrative_text = run_analysis(system_prompt, output, model=model)
        output += "\n\n## Narrative Assessment\n\n" + narrative_text

    # Write to data/dashboard.md
    dashboard_path = data_dir() / "dashboard.md"
    dashboard_path.write_text(output + "\n")
    click.echo(output)
    click.echo(f"\nWritten to {dashboard_path}")


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


@cli.command("find")
@click.argument("query", required=False)
@click.option("--topic", type=click.Choice(["capex", "funding", "return"]),
              help="Restrict to a topic")
@click.option("--tickers", help="Comma-separated tickers (e.g. AAPL,AMZN,GOOG)")
@click.option("--sector", help="Sector name (e.g. mag7, ai) or 'all'")
@click.option("--period", help="Described period label (e.g. CY2026, FY2027)")
@click.option("--claim-type", "claim_types", multiple=True,
              type=click.Choice([
                  "reported_actual", "management_guidance", "management_directional",
                  "vendor_estimate", "agent_extrapolation", "scenario",
              ]),
              help="Restrict to claim class (repeatable)")
@click.option("--definition", help="CapEx definition (e.g. cash_capex)")
@click.option("--as-of", help="Only claims known on or before this date (YYYY-MM-DD)")
@click.option("--primary-only", is_flag=True,
              help="Management statements and reported actuals only")
@click.option("--current", "current_only", is_flag=True,
              help="Only the latest non-superseded claim per company and period")
@click.option("--json", "as_json", is_flag=True, help="Emit complete records as JSON")
def find_cmd(query: str | None, topic: str | None, tickers: str | None, sector: str | None,
             period: str | None, claim_types: tuple[str, ...], definition: str | None,
             as_of: str | None, primary_only: bool, current_only: bool, as_json: bool):
    """Deterministically find citation-backed claims."""
    import json

    from eca.config import data_dir
    from eca.db import connect_db, rebuild_index
    from eca.retrieval import find_claims, format_claim, resolve_current

    if sector == "all":
        sector = None
    ticker_list = [t.strip().upper() for t in tickers.split(",")] if tickers else None

    db_path = data_dir() / "eca.db"
    rebuild_index(db_path)
    conn = connect_db(db_path)
    try:
        claims = find_claims(
            conn, text=query, topic=topic, tickers=ticker_list, sector=sector,
            period=period, claim_types=list(claim_types) or None,
            definition=definition, as_of=as_of, primary_only=primary_only,
        )
        if current_only:
            resolution = resolve_current(claims, as_of=as_of)
            claims = resolution["current"]
    finally:
        conn.close()

    if as_json:
        click.echo(json.dumps(claims, indent=2))
        return

    if not claims:
        click.echo("No claims found.")
        return
    for claim in claims:
        click.echo(format_claim(claim))
        click.echo("")


@cli.command("ask")
@click.argument("question")
@click.option("--topic", "topics", multiple=True,
              type=click.Choice(["capex", "funding", "return"]),
              help="Topic to retrieve (repeatable; default capex)")
@click.option("--period", "periods", multiple=True,
              help="Described period label (repeatable; default derives from evidence)")
@click.option("--tickers", help="Comma-separated tickers (e.g. AAPL,AMZN,GOOG)")
@click.option("--sector", help="Sector name (e.g. mag7)")
@click.option("--as-of", help="Answer as of this date (YYYY-MM-DD)")
@click.option("--policy", type=click.Choice(["strict", "broad"]), default="strict",
              help="Aggregation compatibility policy (default strict)")
@click.option("--primary-sources-only", is_flag=True,
              help="Exclude vendor estimates and extrapolations from evidence display")
@click.option("--json", "as_json", is_flag=True,
              help="Emit the evidence packet as JSON; performs no LLM call")
@click.option("--model", default="claude-sonnet-4-6", help="Model for interpretation")
def ask_cmd(question: str, topics: tuple[str, ...], periods: tuple[str, ...], tickers: str | None,
            sector: str | None, as_of: str | None, policy: str, primary_sources_only: bool,
            as_json: bool, model: str):
    """Answer a question from an evidence packet built before any LLM call."""
    import json

    from eca.config import data_dir
    from eca.db import connect_db, rebuild_index
    from eca.llm import run_analysis
    from eca.processors.ask import (
        SYNTHESIS_SYSTEM_PROMPT, build_evidence_packet, render_packet,
    )

    db_path = data_dir() / "eca.db"
    rebuild_index(db_path)
    conn = connect_db(db_path)
    try:
        packet = build_evidence_packet(
            conn, question,
            topics=list(topics) or ["capex"],
            periods=list(periods) or None,
            tickers=[t.strip().upper() for t in tickers.split(",")] if tickers else None,
            sector=None if sector == "all" else sector,
            as_of=as_of, policy=policy, primary_only=primary_sources_only,
        )
    finally:
        conn.close()

    if as_json:
        # Deterministic path: the packet is the answer; no LLM is involved.
        click.echo(json.dumps(packet, indent=2))
        return

    click.echo(render_packet(packet))

    try:
        interpretation = run_analysis(
            SYNTHESIS_SYSTEM_PROMPT, json.dumps(packet, indent=2), model=model,
        )
    except Exception as e:  # LLM failure never destroys the evidence result
        click.echo(f"Synthesis error (evidence above is unaffected): {e}", err=True)
        raise SystemExit(1)

    click.echo("## 4. Interpretation")
    click.echo("")
    click.echo(interpretation)


if __name__ == "__main__":
    cli()
