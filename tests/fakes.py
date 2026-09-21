"""TypeSafeClient test doubles. Never talk to the real API."""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any


class FakeChoice:
    def __init__(
        self,
        choice: str = "spam",
        confidence: float = 0.94,
        probabilities: dict[str, float] | None = None,
    ) -> None:
        self.choice = choice
        self.confidence = confidence
        self.probabilities = probabilities or {
            "spam": 0.94,
            "phishing": 0.03,
            "promotional": 0.01,
            "legitimate": 0.01,
            "other": 0.01,
        }


class FakeNoul:
    def __init__(self, noul: float) -> None:
        self.noul = noul


class FakeScore:
    def __init__(self, score: float) -> None:
        self.score = score


class FakeResponse:
    def __init__(
        self,
        *,
        category: str = "spam",
        confidence: float = 0.94,
        probabilities: dict[str, float] | None = None,
        is_spam: float = 0.97,
        needs_reply: float = 0.02,
        credential_request: float = 0.05,
        brand_impersonation: float = 0.04,
        pressure: float = 0.2,
        model: str = "jev-1.13.0",
        input_tokens: int | None = 400,
    ) -> None:
        self.model = model
        self.usage = SimpleNamespace(input_tokens=input_tokens)
        self.choices = {
            "category": FakeChoice(category, confidence, probabilities),
        }
        self.nouls = {
            "is_spam": FakeNoul(is_spam),
            "needs_reply": FakeNoul(needs_reply),
            "credential_request": FakeNoul(credential_request),
            "brand_impersonation": FakeNoul(brand_impersonation),
        }
        self.scores = {"pressure": FakeScore(pressure)}
        self.answers = {**self.choices, **self.nouls, **self.scores}


class FakeSdk:
    def __init__(self, response: FakeResponse | None = None, error: Exception | None = None) -> None:
        self.response = response or FakeResponse()
        self.error = error
        self.calls: list[dict[str, Any]] = []

    def system_one(self, state: Any, questions: Any, model: str | None = None) -> FakeResponse:
        self.calls.append({"state": state, "questions": questions, "model": model})
        if self.error:
            raise self.error
        return self.response

    def close(self) -> None:
        pass
