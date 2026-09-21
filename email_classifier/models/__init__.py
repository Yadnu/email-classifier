"""Pydantic output contract — ClassificationResult and related types."""

from email_classifier.models.result import (
    ClassificationResult,
    ClassificationTimeMs,
    Observability,
    Signals,
    ThresholdsApplied,
    format_compact,
)

__all__ = [
    "ClassificationResult",
    "ClassificationTimeMs",
    "Observability",
    "Signals",
    "ThresholdsApplied",
    "format_compact",
]
