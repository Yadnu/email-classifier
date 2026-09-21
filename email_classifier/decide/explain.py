"""Plain-English verdict sentence and ordered threshold checklist from stored numbers."""
from __future__ import annotations

from typing import Any

from email_classifier.config import ThresholdsConfig
from email_classifier.models.result import ClassificationResult


def explain_verdict(result: ClassificationResult, thresholds: ThresholdsConfig) -> str:
    """One sentence from decision_path. Never calls a model."""
    path = result.observability.decision_path
    conf = result.category_confidence
    t = thresholds
    spam_p = result.spam_probability
    cred = result.signals.credential_request
    brand = result.signals.brand_impersonation

    if path == "jev_error":
        return "Left uncertain because the Jev call failed."
    if path == "uncertain_floor":
        return (
            f"Left uncertain because category confidence was {conf:.2f}, "
            f"below the {t.uncertain_floor:.2f} uncertain floor."
        )
    if path == "category_phishing":
        return (
            f"Marked phishing because category was phishing with {conf:.2f} confidence, "
            f"above the {t.phishing_category_confidence:.2f} phishing bar."
        )
    if path == "credential_and_impersonation":
        return (
            f"Marked phishing because credential_request was {cred:.2f} "
            f"(above {t.phishing_credential_request:.2f}) and brand_impersonation "
            f"was {brand:.2f} (above {t.phishing_brand_impersonation:.2f})."
        )
    if path == "is_spam_noul":
        return (
            f"Marked spam because is_spam was {spam_p:.2f}, "
            f"above the {t.spam_is_spam:.2f} threshold."
        )
    if path == "category_spam+is_spam_noul":
        return (
            f"Marked spam because category was spam and is_spam was {spam_p:.2f}, "
            f"above the {t.spam_is_spam:.2f} threshold."
        )
    if path == "category_spam":
        return (
            f"Marked spam because category was spam with {conf:.2f} confidence, "
            f"above the {t.spam_category_confidence:.2f} spam-category bar."
        )
    if path.startswith("category_"):
        cat = path.replace("category_", "", 1)
        return (
            f"Labeled {cat} from Jev's category choice "
            f"({conf:.2f} confidence, spam probability {spam_p:.2f})."
        )
    return f"Verdict '{result.category}' via decision path '{path}'."


def decision_trail(result: ClassificationResult, thresholds: ThresholdsConfig) -> list[dict[str, Any]]:
    """Rules in evaluation order: matched True means this rule fired."""
    t = thresholds
    conf = result.category_confidence
    raw = result.category if result.category != "uncertain" else "other"
    # Reconstruct Jev category from probabilities when uncertain.
    probs = result.category_probabilities
    jev_category = max(probs, key=probs.get) if probs else raw
    if result.category != "uncertain":
        jev_category = result.category if result.category != "phishing" else "phishing"

    steps = [
        {
            "id": "uncertain_floor",
            "label": (
                f"Category confidence {conf:.2f} < uncertain floor {t.uncertain_floor:.2f}"
            ),
            "matched": conf < t.uncertain_floor,
        },
        {
            "id": "category_phishing",
            "label": (
                f"Category is phishing and confidence {conf:.2f} > "
                f"{t.phishing_category_confidence:.2f}"
            ),
            "matched": result.observability.decision_path == "category_phishing",
        },
        {
            "id": "credential_and_impersonation",
            "label": (
                f"credential_request {result.signals.credential_request:.2f} > "
                f"{t.phishing_credential_request:.2f} and brand_impersonation "
                f"{result.signals.brand_impersonation:.2f} > "
                f"{t.phishing_brand_impersonation:.2f}"
            ),
            "matched": result.observability.decision_path == "credential_and_impersonation",
        },
        {
            "id": "is_spam_noul",
            "label": (
                f"is_spam {result.spam_probability:.2f} > {t.spam_is_spam:.2f}"
            ),
            "matched": "is_spam_noul" in result.observability.decision_path,
        },
        {
            "id": "spam_category",
            "label": (
                f"Category spam/phishing with confidence {conf:.2f} > "
                f"{t.spam_category_confidence:.2f}"
            ),
            "matched": result.observability.decision_path
            in {"category_spam", "category_phishing"}
            and result.spam,
        },
        {
            "id": "needs_reply",
            "label": (
                f"needs_reply {result.reply_probability:.2f} >= "
                f"{t.needs_reply_label:.2f}"
            ),
            "matched": result.reply_probability >= t.needs_reply_label,
        },
    ]
    return steps
