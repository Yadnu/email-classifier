"""Combine Jev answers into a verdict using config thresholds.

Decision lives in Python, not in Jev. Phishing labeling uses a higher bar
than tagging promotional mail.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from email_classifier.config import ThresholdsConfig
from email_classifier.jev.client import JevAnswers

FinalCategory = Literal[
    "spam", "phishing", "promotional", "legitimate", "other", "uncertain"
]


@dataclass(frozen=True)
class Decision:
    category: FinalCategory
    category_confidence: float
    spam: bool
    decision_path: str
    """True when Stage 6 may apply a Gmail label (never for uncertain)."""
    may_auto_label: bool


def decide(answers: JevAnswers, thresholds: ThresholdsConfig) -> Decision:
    raw_category = answers.category
    confidence = answers.category_confidence
    t = thresholds

    if raw_category not in {"spam", "phishing", "promotional", "legitimate", "other"}:
        raw_category = "other"

    # Uncertain: low peak confidence. Never auto-label.
    if confidence < t.uncertain_floor:
        spam = answers.is_spam > t.spam_is_spam
        return Decision(
            category="uncertain",
            category_confidence=confidence,
            spam=spam,
            decision_path="uncertain_floor",
            may_auto_label=False,
        )

    # Phishing: category bar (higher) or paired Noul signals.
    if raw_category == "phishing" and confidence > t.phishing_category_confidence:
        return Decision(
            category="phishing",
            category_confidence=confidence,
            spam=True,
            decision_path="category_phishing",
            may_auto_label=True,
        )

    if (
        answers.credential_request > t.phishing_credential_request
        and answers.brand_impersonation > t.phishing_brand_impersonation
    ):
        return Decision(
            category="phishing",
            category_confidence=confidence,
            spam=True,
            decision_path="credential_and_impersonation",
            may_auto_label=True,
        )

    category: FinalCategory = raw_category  # type: ignore[assignment]

    spam = False
    path = f"category_{category}"
    if answers.is_spam > t.spam_is_spam:
        spam = True
        path = "is_spam_noul" if category != "spam" else "category_spam+is_spam_noul"
    elif category in {"spam", "phishing"} and confidence > t.spam_category_confidence:
        spam = True
        path = "category_spam" if category == "spam" else "category_phishing"

    # Promotional tagging uses a lower action bar (Stage 6). Classification
    # still reports Jev's category; may_auto_label is False if promotional
    # confidence is below promotional_action.
    may_label = True
    if category == "promotional" and confidence < t.promotional_action:
        may_label = False

    return Decision(
        category=category,
        category_confidence=confidence,
        spam=spam,
        decision_path=path,
        may_auto_label=may_label,
    )
