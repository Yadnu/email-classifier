"""Gmail labeling: Jev-Spam / Jev-Phishing / Jev-Needs-Reply only."""

from email_classifier.label.inbox import (
    LabelReport,
    format_label_report,
    run_label_inbox,
)
from email_classifier.label.plan import ALLOWED_LABELS, planned_labels

__all__ = [
    "ALLOWED_LABELS",
    "LabelReport",
    "format_label_report",
    "planned_labels",
    "run_label_inbox",
]
