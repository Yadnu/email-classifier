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
    """Classify a single Gmail message via Jev.  (Stage 3)"""
    typer.echo("classify command is available in Stage 3.", err=True)
    raise typer.Exit(1)


# ─── evaluate  (Stage 5) ──────────────────────────────────────────────────────


@app.command()
def evaluate(
    config: Annotated[
        str,
        typer.Option("--config", help="Path to config.yaml.", envvar="CLASSIFIER_CONFIG"),
    ] = "config.yaml",
) -> None:
    """Evaluate precision/recall/F1 against labeled local dataset.  (Stage 5)"""
    typer.echo("evaluate command is available in Stage 5.", err=True)
    raise typer.Exit(1)


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
    """Report latency, category mix, cost, and drift stats for a date range.  (Stage 5)"""
    typer.echo("stats command is available in Stage 5.", err=True)
    raise typer.Exit(1)


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
    """Apply Jev-Spam / Jev-Phishing / Jev-Needs-Reply Gmail labels.  (Stage 6)"""
    typer.echo("label-inbox command is available in Stage 6.", err=True)
    raise typer.Exit(1)


if __name__ == "__main__":
    app()
