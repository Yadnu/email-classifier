"""Threshold decision logic. No network."""
from __future__ import annotations

from email_classifier.config import ThresholdsConfig
from email_classifier.decide.logic import decide
from email_classifier.jev.client import JevAnswers

T = ThresholdsConfig()


def _answers(**kwargs) -> JevAnswers:
    base = dict(
        model="jev-1.13.0",
        category="legitimate",
        category_confidence=0.9,
        category_probabilities={
            "spam": 0.05,
            "phishing": 0.05,
            "promotional": 0.05,
            "legitimate": 0.8,
            "other": 0.05,
        },
        is_spam=0.1,
        needs_reply=0.2,
        credential_request=0.1,
        brand_impersonation=0.1,
        pressure_score=0.0,
        input_tokens=100,
        retries=0,
        rate_limited=False,
        elapsed_ms=10,
    )
    base.update(kwargs)
    return JevAnswers(**base)


class TestDecide:
    def test_uncertain_floor(self) -> None:
        d = decide(_answers(category="spam", category_confidence=0.4, is_spam=0.2), T)
        assert d.category == "uncertain"
        assert d.may_auto_label is False
        assert d.decision_path == "uncertain_floor"
        assert d.spam is False

    def test_uncertain_still_spam_from_noul(self) -> None:
        d = decide(_answers(category="spam", category_confidence=0.3, is_spam=0.9), T)
        assert d.category == "uncertain"
        assert d.spam is True
        assert d.may_auto_label is False

    def test_phishing_by_category(self) -> None:
        d = decide(_answers(category="phishing", category_confidence=0.91), T)
        assert d.category == "phishing"
        assert d.spam is True
        assert d.decision_path == "category_phishing"
        assert d.may_auto_label is True

    def test_phishing_category_below_high_bar(self) -> None:
        # Above uncertain_floor, below T1 (0.85) and spam_category (0.80).
        d = decide(
            _answers(category="phishing", category_confidence=0.70, is_spam=0.1), T
        )
        assert d.category == "phishing"
        assert d.spam is False
        assert d.may_auto_label is True

    def test_phishing_by_signals(self) -> None:
        d = decide(
            _answers(
                category="legitimate",
                category_confidence=0.7,
                credential_request=0.9,
                brand_impersonation=0.88,
            ),
            T,
        )
        assert d.category == "phishing"
        assert d.spam is True
        assert d.decision_path == "credential_and_impersonation"

    def test_spam_from_noul(self) -> None:
        d = decide(_answers(category="promotional", category_confidence=0.7, is_spam=0.9), T)
        assert d.spam is True
        assert d.decision_path == "is_spam_noul"

    def test_spam_from_category(self) -> None:
        d = decide(_answers(category="spam", category_confidence=0.88, is_spam=0.2), T)
        assert d.category == "spam"
        assert d.spam is True
        assert d.decision_path == "category_spam"

    def test_legitimate_ham(self) -> None:
        d = decide(_answers(), T)
        assert d.category == "legitimate"
        assert d.spam is False
        assert d.decision_path == "category_legitimate"
        assert d.may_auto_label is True

    def test_promotional_below_action_bar(self) -> None:
        d = decide(_answers(category="promotional", category_confidence=0.55), T)
        assert d.category == "promotional"
        assert d.may_auto_label is False
