"""label-inbox: dry-run by default; live apply uses a separate modify token."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from email_classifier.auth.oauth import get_gmail_service, modify_token_path
from email_classifier.config import AppConfig
from email_classifier.ingest.db import Database
from email_classifier.label.gmail_labels import add_labels, ensure_allowed_labels
from email_classifier.label.plan import ALLOWED_LABELS, planned_labels
from email_classifier.models.result import ClassificationResult


@dataclass
class LabelAction:
    message_id: str
    labels: list[str]


@dataclass
class LabelReport:
    dry_run: bool
    actions: list[LabelAction] = field(default_factory=list)
    skipped_uncertain: int = 0
    skipped_no_action: int = 0
    applied: int = 0


def collect_actions(cfg: AppConfig, db: Database) -> tuple[list[LabelAction], int, int]:
    actions: list[LabelAction] = []
    uncertain = 0
    no_action = 0
    for row in db.latest_classifications():
        result = ClassificationResult.model_validate_json(row["result_json"])
        if result.category == "uncertain":
            uncertain += 1
            continue
        names = planned_labels(result, cfg.thresholds)
        if not names:
            no_action += 1
            continue
        actions.append(LabelAction(message_id=result.message_id, labels=names))
    return actions, uncertain, no_action


def run_label_inbox(
    cfg: AppConfig,
    *,
    dry_run: bool = True,
    db: Optional[Database] = None,
    gmail_service: Any = None,
) -> LabelReport:
    owns = db is None
    if db is None:
        db = Database(cfg.ingest.db_path)
        db.open()
    try:
        if not db.latest_classifications():
            raise ValueError(
                "No stored classifications. Run `email-classifier classify <id>` first."
            )
        actions, uncertain, no_action = collect_actions(cfg, db)
        report = LabelReport(
            dry_run=dry_run,
            actions=actions,
            skipped_uncertain=uncertain,
            skipped_no_action=no_action,
        )
        if dry_run:
            return report

        if gmail_service is None:
            gmail_service = get_gmail_service(
                credentials_path=cfg.gmail.credentials_path,
                token_path=modify_token_path(cfg.gmail.token_path),
                scopes=cfg.gmail.modify_scopes,
            )
        id_by_name = ensure_allowed_labels(gmail_service)
        for action in actions:
            add_ids = [id_by_name[name] for name in action.labels]
            add_labels(gmail_service, action.message_id, add_ids)
            report.applied += 1
        return report
    finally:
        if owns:
            db.close()


def format_label_report(report: LabelReport) -> str:
    counts = {name: 0 for name in ALLOWED_LABELS}
    for action in report.actions:
        for name in action.labels:
            counts[name] = counts.get(name, 0) + 1
    mode = "dry-run  (no Gmail writes)" if report.dry_run else "applied"
    n = len(report.actions)
    lines = [
        f"label-inbox {mode}",
        f"  messages={n:,}  "
        f"Jev-Spam={counts[ALLOWED_LABELS[0]]:,}  "
        f"Jev-Phishing={counts[ALLOWED_LABELS[1]]:,}  "
        f"Jev-Needs-Reply={counts[ALLOWED_LABELS[2]]:,}",
        f"  skipped uncertain={report.skipped_uncertain:,}  "
        f"no-action={report.skipped_no_action:,}",
    ]
    if not report.dry_run:
        lines.append(f"  wrote {report.applied:,} Gmail modify call(s)  (addLabelIds only)")
    return "\n".join(lines)
