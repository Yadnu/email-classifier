"""Pydantic output contract for every classification path."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

Category = Literal[
    "spam", "phishing", "promotional", "legitimate", "other", "uncertain"
]


class Signals(BaseModel):
    credential_request: float = Field(ge=0.0, le=1.0)
    brand_impersonation: float = Field(ge=0.0, le=1.0)
    pressure_score: float = Field(ge=0.0, le=2.0)


class ClassificationTimeMs(BaseModel):
    total: int = Field(ge=0)
    gmail_fetch: int = Field(ge=0)
    parse: int = Field(ge=0)
    state_build: int = Field(ge=0)
    jev_call: int = Field(ge=0)
    decision: int = Field(ge=0)


class ThresholdsApplied(BaseModel):
    spam: float
    phishing: float
    uncertain_floor: float


class Observability(BaseModel):
    request_id: str
    trace_id: str
    model_version: str
    input_tokens: int = Field(ge=0)
    input_tokens_estimated: bool
    cost_usd: float = Field(ge=0.0)
    state_size_chars: int = Field(ge=0)
    body_truncated: bool
    retries: int = Field(ge=0)
    rate_limited: bool
    thresholds_applied: ThresholdsApplied
    decision_path: str
    timestamp: str

    @field_validator("timestamp")
    @classmethod
    def timestamp_is_iso(cls, value: str) -> str:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
        return value


class ClassificationResult(BaseModel):
    message_id: str
    category: Category
    category_confidence: float = Field(ge=0.0, le=1.0)
    category_probabilities: dict[str, float]
    spam: bool
    spam_probability: float = Field(ge=0.0, le=1.0)
    reply_probability: float = Field(ge=0.0, le=1.0)
    signals: Signals
    classification_time_ms: ClassificationTimeMs
    observability: Observability

    @field_validator("category_probabilities")
    @classmethod
    def all_category_keys(cls, value: dict[str, float]) -> dict[str, float]:
        required = ("spam", "phishing", "promotional", "legitimate", "other")
        out = {k: float(value.get(k, 0.0)) for k in required}
        for k in out:
            if not 0.0 <= out[k] <= 1.0:
                raise ValueError(f"probability for {k} out of range")
        return out


def format_compact(result: ClassificationResult) -> str:
    """One-line CLI default: [SPAM 97%] category=spam (0.94) reply=2% …"""
    tag = "SPAM" if result.spam else "HAM"
    spam_pct = round(result.spam_probability * 100)
    reply_pct = round(result.reply_probability * 100)
    t = result.classification_time_ms
    return (
        f"[{tag} {spam_pct}%] category={result.category} "
        f"({result.category_confidence:.2f}) reply={reply_pct}% "
        f"time={t.total}ms (jev {t.jev_call}ms) "
        f"model={result.observability.model_version}"
    )
