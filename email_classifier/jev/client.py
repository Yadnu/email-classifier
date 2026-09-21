"""TypeSafe Jev client: pinned model, one call, SDK retries, retry counts."""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Optional

from typesafe_sdk import RetryPolicy, TypeSafeClient

from email_classifier.jev.questions import QUESTIONS

PINNED_MODEL = "jev-1.13.0"


class RetryCounter:
    """Counts 429s seen on the wire so observability can record retries."""

    def __init__(self) -> None:
        self.retries = 0
        self.rate_limited = False

    def record_status(self, status_code: int) -> None:
        if status_code == 429:
            self.rate_limited = True
            self.retries += 1


def _build_counting_transport(counter: RetryCounter) -> Any:
    """Wrap httpx2's default transport to count 429 responses."""
    try:
        import httpx2
    except ImportError:  # pragma: no cover
        return None, counter

    class CountingTransport(httpx2.HTTPTransport):
        def handle_request(self, request):  # type: ignore[no-untyped-def]
            response = super().handle_request(request)
            counter.record_status(response.status_code)
            return response

    return CountingTransport(), counter


@dataclass
class JevAnswers:
    model: str
    category: str
    category_confidence: float
    category_probabilities: dict[str, float]
    is_spam: float
    needs_reply: float
    credential_request: float
    brand_impersonation: float
    pressure_score: float
    input_tokens: Optional[int]
    retries: int
    rate_limited: bool
    elapsed_ms: int


def _noul(response: Any, name: str) -> float:
    if hasattr(response, "nouls") and name in response.nouls:
        return float(response.nouls[name].noul)
    return float(response.answers[name].noul)


def _choice(response: Any, name: str) -> Any:
    if hasattr(response, "choices") and name in response.choices:
        return response.choices[name]
    return response.answers[name]


def _score(response: Any, name: str) -> float:
    if hasattr(response, "scores") and name in response.scores:
        return float(response.scores[name].score)
    return float(response.answers[name].score)


def extract_answers(response: Any, counter: RetryCounter, elapsed_ms: int) -> JevAnswers:
    """Pull typed fields from a SystemOneResponse (or a test double)."""
    choice = _choice(response, "category")
    probs = dict(getattr(choice, "probabilities", {}) or {})
    usage = getattr(response, "usage", None)
    tokens = None
    if usage is not None:
        tokens = getattr(usage, "input_tokens", None)
        if tokens is None and isinstance(usage, dict):
            tokens = usage.get("input_tokens")
    model = str(getattr(response, "model", PINNED_MODEL) or PINNED_MODEL)
    pressure = _score(response, "pressure")
    # Score is 0–2 for a 3-level rubric.
    pressure = min(2.0, max(0.0, pressure))
    return JevAnswers(
        model=model,
        category=str(choice.choice),
        category_confidence=float(choice.confidence),
        category_probabilities=probs,
        is_spam=_noul(response, "is_spam"),
        needs_reply=_noul(response, "needs_reply"),
        credential_request=_noul(response, "credential_request"),
        brand_impersonation=_noul(response, "brand_impersonation"),
        pressure_score=pressure,
        input_tokens=int(tokens) if tokens is not None else None,
        retries=counter.retries,
        rate_limited=counter.rate_limited,
        elapsed_ms=elapsed_ms,
    )


class JevClient:
    """Thin wrapper: one system_one call, pinned jev-1.13.0, SDK retries."""

    def __init__(
        self,
        *,
        model: str = PINNED_MODEL,
        sdk_client: Any = None,
        retry: Optional[RetryPolicy] = None,
    ) -> None:
        self.model = model
        self._owned = sdk_client is None
        self._counter = RetryCounter()
        if sdk_client is not None:
            self._sdk = sdk_client
            return
        transport, _ = _build_counting_transport(self._counter)
        kwargs: dict[str, Any] = {
            "model": model,
            "retry": retry or RetryPolicy(),
        }
        if transport is not None:
            kwargs["transport"] = transport
        self._sdk = TypeSafeClient(**kwargs)

    def close(self) -> None:
        if self._owned and hasattr(self._sdk, "close"):
            self._sdk.close()

    def __enter__(self) -> "JevClient":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def classify_state(self, state: dict[str, Any]) -> JevAnswers:
        """One Jev call with every question. Extra questions add almost no latency."""
        started = time.perf_counter()
        response = self._sdk.system_one(state=state, questions=QUESTIONS, model=self.model)
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        answers = extract_answers(response, self._counter, elapsed_ms)
        # Contract: log the model field from every response (caller stores it).
        return answers
