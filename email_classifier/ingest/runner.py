"""High-level ingest runner: full fetch and incremental historyId sync.

Called by ``email-classifier ingest`` (and ``ingest --full``).

Output contract
---------------
Only counts and the new historyId are printed to stdout — never subjects,
email addresses, or message bodies.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Optional

import typer

from email_classifier.auth.oauth import get_gmail_service
from email_classifier.config import AppConfig
from email_classifier.ingest.db import Database
from email_classifier.ingest.gmail import (
    HistoryExpiredError,
    batch_get_messages,
    get_message,
    get_profile,
    iter_history_changes,
    iter_message_ids,
)
from email_classifier.ingest.ground_truth import label_for_message


@dataclass
class IngestStats:
    fetched: int = 0
    inserted: int = 0
    updated: int = 0
    spam: int = 0
    ham: int = 0
    promotional: int = 0
    skipped: int = 0
    history_id: Optional[str] = None


def _label_counts(label: Optional[str], stats: IngestStats) -> None:
    if label == "spam":
        stats.spam += 1
    elif label == "ham":
        stats.ham += 1
    elif label == "promotional":
        stats.promotional += 1


def _print_stats(stats: IngestStats) -> None:
    typer.echo(
        f"Ingested {stats.inserted:,} new  |  updated {stats.updated:,}  "
        f"|  total fetched {stats.fetched:,}"
    )
    typer.echo(
        f"  spam={stats.spam:,}  ham={stats.ham:,}  "
        f"promotional={stats.promotional:,}  skipped={stats.skipped:,}"
    )
    if stats.history_id:
        typer.echo(f"  historyId={stats.history_id}")


# ─── full fetch ───────────────────────────────────────────────────────────────


def _full_fetch(service, db: Database, cfg: AppConfig) -> IngestStats:
    """Fetch every message from scratch, ignoring any saved historyId."""
    stats = IngestStats()
    ic = cfg.ingest
    jc = cfg.jev  # for body_excerpt_chars (not used yet, but consistent)

    typer.echo("Starting full fetch …")

    # Collect all IDs first so we can show a progress estimate.
    message_ids = list(
        iter_message_ids(
            service,
            page_size=ic.page_size,
            include_spam_trash=ic.include_spam_trash,
            max_messages=ic.max_messages,
        )
    )
    typer.echo(f"  Found {len(message_ids):,} messages in mailbox.")

    # Batch-get RAW bodies in chunks.
    for msg in batch_get_messages(service, message_ids, batch_size=ic.batch_size):
        stats.fetched += 1
        label = label_for_message(
            msg["labelIds"], promotions_as=ic.promotions_as
        )
        if label is None:
            stats.skipped += 1
            continue

        inserted = db.upsert_message(
            message_id=msg["id"],
            thread_id=msg["threadId"],
            internal_date=msg["internalDate"],
            history_id=msg.get("historyId"),
            raw_rfc822=msg["raw_bytes"],
            label_ids=msg["labelIds"],
            from_header=msg.get("from_header"),
            subject=msg.get("subject"),
        )
        if inserted:
            stats.inserted += 1
        else:
            stats.updated += 1
        _label_counts(label, stats)

        if stats.fetched % 200 == 0:
            typer.echo(f"  … {stats.fetched:,} processed", nl=False)
            typer.echo(f"  (inserted {stats.inserted:,})", nl=True)

    return stats


# ─── incremental sync ─────────────────────────────────────────────────────────


def _incremental_sync(
    service, db: Database, cfg: AppConfig, start_history_id: str
) -> IngestStats:
    """Sync only new/changed messages since the last historyId."""
    stats = IngestStats()
    ic = cfg.ingest

    typer.echo(f"Incremental sync from historyId={start_history_id} …")

    try:
        records = list(
            iter_history_changes(
                service,
                start_history_id=start_history_id,
                page_size=ic.page_size,
                max_messages=ic.max_messages,
            )
        )
    except HistoryExpiredError:
        typer.echo(
            f"  historyId {start_history_id} has expired. "
            "Falling back to full fetch …"
        )
        return _full_fetch(service, db, cfg)

    # Collect IDs that need to be fetched/updated.
    ids_to_fetch: set[str] = set()
    label_updates: dict[str, list[str]] = {}  # message_id → new labelIds

    for record in records:
        for added in record.get("messagesAdded", []):
            msg = added.get("message", {})
            ids_to_fetch.add(msg["id"])
        for lbl_change in record.get("labelsAdded", []) + record.get("labelsRemoved", []):
            msg = lbl_change.get("message", {})
            mid = msg.get("id")
            if mid:
                # We'll re-fetch labels below, or update in DB if already present.
                label_updates[mid] = msg.get("labelIds", [])

    # Merge label-only updates that we already have in the DB.
    for mid, new_labels in label_updates.items():
        if mid not in ids_to_fetch and db.message_exists(mid):
            inserted = db.upsert_message(
                message_id=mid,
                thread_id="",   # kept from existing row via UPDATE
                internal_date=None,
                history_id=None,
                raw_rfc822=None,
                label_ids=new_labels,
                from_header=None,
                subject=None,
            )
            stats.fetched += 1
            if not inserted:
                stats.updated += 1

    # Fetch new/updated messages.
    if ids_to_fetch:
        for msg in batch_get_messages(
            service, list(ids_to_fetch), batch_size=ic.batch_size
        ):
            stats.fetched += 1
            label = label_for_message(
                msg["labelIds"], promotions_as=ic.promotions_as
            )
            if label is None:
                stats.skipped += 1
                continue

            inserted = db.upsert_message(
                message_id=msg["id"],
                thread_id=msg["threadId"],
                internal_date=msg["internalDate"],
                history_id=msg.get("historyId"),
                raw_rfc822=msg["raw_bytes"],
                label_ids=msg["labelIds"],
                from_header=msg.get("from_header"),
                subject=msg.get("subject"),
            )
            if inserted:
                stats.inserted += 1
            else:
                stats.updated += 1
            _label_counts(label, stats)

    return stats


# ─── public entry point ───────────────────────────────────────────────────────


def run_ingest(cfg: AppConfig, force_full: bool = False) -> IngestStats:
    """Run the full or incremental ingest pipeline.

    Parameters
    ----------
    cfg:
        Loaded application config.
    force_full:
        If True, ignore any saved historyId and do a fresh full fetch.

    Returns
    -------
    IngestStats
        Counts of fetched / inserted / updated / categorized messages.
    """
    service = get_gmail_service(
        credentials_path=cfg.gmail.credentials_path,
        token_path=cfg.gmail.token_path,
        scopes=cfg.gmail.readonly_scopes,
    )

    with Database(cfg.ingest.db_path) as db:
        # Always get the current profile so we can save the latest historyId.
        profile = get_profile(service)
        current_history_id: str = profile.get("historyId", "")

        saved_history_id = db.get_history_id()

        if force_full or saved_history_id is None:
            stats = _full_fetch(service, db, cfg)
        else:
            stats = _incremental_sync(service, db, cfg, saved_history_id)

        # Persist the historyId we received from the profile call.
        if current_history_id:
            db.set_history_id(current_history_id)
            stats.history_id = current_history_id

    _print_stats(stats)
    return stats
