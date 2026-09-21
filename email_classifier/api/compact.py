"""Shape compact message rows for the GUI list/live APIs."""
from __future__ import annotations

import json
from typing import Any, Optional

from email_classifier.ingest.ground_truth import label_for_message
from email_classifier.models.result import ClassificationResult


def sender_domain(from_header: Optional[str]) -> str:
    if not from_header:
        return ""
    addr = from_header
    if "<" in from_header:
        addr = from_header.rsplit("<", 1)[-1].split(">", 1)[0]
    addr = addr.strip().strip('"')
    if "@" in addr:
        return addr.rsplit("@", 1)[-1].strip().lower()
    return ""


def truncate(text: Optional[str], n: int = 80) -> str:
    value = (text or "").replace("\n", " ").strip()
    if len(value) <= n:
        return value
    return value[: n - 1] + "..."


def gmail_spam(label_ids_json: Optional[str]) -> bool:
    try:
        labels = json.loads(label_ids_json or "[]")
    except json.JSONDecodeError:
        return False
    return label_for_message(labels, promotions_as="ham") == "spam"


def compact_row(
    *,
    message_id: str,
    classified_at: str,
    classification_id: int,
    result: ClassificationResult,
    from_header: Optional[str],
    subject: Optional[str],
    label_ids_json: Optional[str],
) -> dict[str, Any]:
    gmail = gmail_spam(label_ids_json)
    return {
        "id": classification_id,
        "message_id": message_id,
        "classified_at": classified_at,
        "category": result.category,
        "category_confidence": result.category_confidence,
        "spam": result.spam,
        "spam_probability": result.spam_probability,
        "reply_probability": result.reply_probability,
        "total_ms": result.classification_time_ms.total,
        "jev_ms": result.classification_time_ms.jev_call,
        "cost_usd": result.observability.cost_usd,
        "sender_domain": sender_domain(from_header),
        "subject": truncate(subject, 80),
        "gmail_spam": gmail,
        "disagreed_with_gmail": result.spam != gmail,
        "decision_path": result.observability.decision_path,
        "model_version": result.observability.model_version,
        "retries": result.observability.retries,
        "rate_limited": result.observability.rate_limited,
    }
