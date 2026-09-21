"""Decide which Jev-* Gmail labels a classification may receive.

Uncertain verdicts never produce labels. Live apply only adds
Jev-Spam / Jev-Phishing / Jev-Needs-Reply — never trash/move/delete.
"""
from __future__ import annotations

from email_classifier.config import ThresholdsConfig
from email_classifier.models.result import ClassificationResult

JEV_SPAM = "Jev-Spam"
JEV_PHISHING = "Jev-Phishing"
JEV_NEEDS_REPLY = "Jev-Needs-Reply"
ALLOWED_LABELS = (JEV_SPAM, JEV_PHISHING, JEV_NEEDS_REPLY)


def planned_labels(
    result: ClassificationResult,
    thresholds: ThresholdsConfig,
) -> list[str]:
    """Return the Jev-* label names to add. Empty means skip."""
    if result.category == "uncertain":
        return []

    names: list[str] = []
    if result.category == "phishing":
        names.append(JEV_PHISHING)
    elif result.spam:
        names.append(JEV_SPAM)
    if result.reply_probability >= thresholds.needs_reply_label:
        names.append(JEV_NEEDS_REPLY)
    return names
