"""Typer CLI for the personal Gmail + Jev spam classifier."""
from __future__ import annotations

from typing import Annotated, Optional

import typer

from email_classifier.config import load_config

app = typer.Typer(
    name="email-classifier",
    help="Personal Gmail spam classifier powered by TypeSafe Jev.",
    add_completion=False,
)


# ─── ingest ───────────────────────────────────────────────────────────────────


@app.command()
def ingest(
    full: Annotated[
        bool,
        typer.Option("--full", help="Force a full re-fetch, ignoring saved historyId."),
    ] = False,
    config: Annotated[
        str,
        typer.Option("--config", help="Path to config.yaml.", envvar="CLASSIFIER_CONFIG"),
    ] = "config.yaml",
) -> None:
    """Pull Gmail messages into the local SQLite database."""
    from email_classifier.ingest.runner import run_ingest

    cfg = load_config(config)
    run_ingest(cfg, force_full=full)


# ─── classify  (Stage 3) ──────────────────────────────────────────────────────


@app.command()
def classify(
    message_id: Annotated[str, typer.Argument(help="Gmail message ID to classify.")],
    json_output: Annotated[
        bool, typer.Option("--json", help="Output full JSON instead of a compact line.")
    ] = False,
    config: Annotated[
        str,
        typer.Option("--config", help="Path to config.yaml.", envvar="CLASSIFIER_CONFIG"),
    ] = "config.yaml",
) -> None:
    """Classify a single Gmail message via Jev."""
    from email_classifier.models.result import format_compact
    from email_classifier.pipeline import classify_message

    cfg = load_config(config)
    result = classify_message(message_id, cfg)
    if json_output:
        typer.echo(result.model_dump_json(indent=2))
    else:
        typer.echo(format_compact(result))


# ─── serve  (Stage 4) ─────────────────────────────────────────────────────────


@app.command()
def serve(
    host: Annotated[str, typer.Option(help="Bind address.")] = "127.0.0.1",
    port: Annotated[int, typer.Option(help="Bind port.")] = 8000,
    config: Annotated[
        str,
        typer.Option("--config", help="Path to config.yaml.", envvar="CLASSIFIER_CONFIG"),
    ] = "config.yaml",
) -> None:
    """Run the FastAPI app (POST /classify, GET /metrics)."""
    import os

    import uvicorn

    from email_classifier.observability import setup_observability

    os.environ.setdefault("CLASSIFIER_CONFIG", config)
    setup_observability()
    uvicorn.run("email_classifier.api.app:app", host=host, port=port)


# ─── evaluate  (Stage 5) ──────────────────────────────────────────────────────


@app.command()
def evaluate(
    config: Annotated[
        str,
        typer.Option("--config", help="Path to config.yaml.", envvar="CLASSIFIER_CONFIG"),
    ] = "config.yaml",
) -> None:
    """Evaluate precision/recall/F1 against labeled local classifications."""
    from email_classifier.eval.evaluate import format_evaluate_report, run_evaluate

    cfg = load_config(config)
    try:
        report = run_evaluate(cfg)
    except ValueError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from exc
    typer.echo(format_evaluate_report(report))


# ─── stats  (Stage 5) ─────────────────────────────────────────────────────────


@app.command()
def stats(
    from_date: Annotated[
        Optional[str],
        typer.Option("--from", help="Start date (YYYY-MM-DD)."),
    ] = None,
    to_date: Annotated[
        Optional[str],
        typer.Option("--to", help="End date (YYYY-MM-DD)."),
    ] = None,
    config: Annotated[
        str,
        typer.Option("--config", help="Path to config.yaml.", envvar="CLASSIFIER_CONFIG"),
    ] = "config.yaml",
) -> None:
    """Report latency, category mix, cost, and drift stats for a date range."""
    from email_classifier.eval.stats import (
        format_stats_report,
        parse_date,
        run_stats,
    )

    cfg = load_config(config)
    try:
        parse_date(from_date)
        parse_date(to_date, end_of_day=True)
    except ValueError as exc:
        typer.echo("Dates must be YYYY-MM-DD.", err=True)
        raise typer.Exit(1) from exc
    report = run_stats(cfg, from_date=from_date, to_date=to_date)
    typer.echo(format_stats_report(report))


# ─── label-inbox  (Stage 6) ───────────────────────────────────────────────────


@app.command(name="label-inbox")
def label_inbox(
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run/--no-dry-run", help="Print changes without applying them."),
    ] = True,
    config: Annotated[
        str,
        typer.Option("--config", help="Path to config.yaml.", envvar="CLASSIFIER_CONFIG"),
    ] = "config.yaml",
) -> None:
    """Apply Jev-Spam / Jev-Phishing / Jev-Needs-Reply. Dry-run unless --no-dry-run."""
    from email_classifier.label.inbox import format_label_report, run_label_inbox

    cfg = load_config(config)
    try:
        report = run_label_inbox(cfg, dry_run=dry_run)
    except ValueError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from exc
    typer.echo(format_label_report(report))


if __name__ == "__main__":
    app()
