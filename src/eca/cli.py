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
    from eca.processors.ingest_transcript import ingest_transcript

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
